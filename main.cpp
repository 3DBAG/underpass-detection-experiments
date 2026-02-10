#include <iostream>
#include <fstream>
#include <format>

#include <manifold/manifold.h>
#include <manifold/meshIO.h>

#include <CGAL/Simple_cartesian.h>
#include <CGAL/Surface_mesh.h>
#include <CGAL/Polygon_mesh_processing/triangulate_faces.h>
#include <CGAL/IO/PLY.h>
#include <CGAL/Polygon_mesh_processing/compute_normal.h>
#include <CGAL/Exact_predicates_exact_constructions_kernel.h>
#include <CGAL/Nef_polyhedron_3.h>
#include <CGAL/Polyhedron_3.h>
#include <CGAL/boost/graph/convert_nef_polyhedron_to_polygon_mesh.h>
#include <CGAL/Polygon_mesh_processing/polygon_soup_to_polygon_mesh.h>
#include <CGAL/Polygon_mesh_processing/corefinement.h>

#include "zityjson.h"
#include "OGRVectorReader.h"
#include "PolygonExtruder.h"
#include "RerunVisualization.h"

// Enum to select boolean operation method
enum class BooleanMethod {
    Manifold,       // Use Manifold library (faster, floating-point)
    CgalNef,        // Use CGAL Nef polyhedra (slower, exact arithmetic)
    CgalPMP    // Use CGAL PMP corefine_and_compute_difference (robust, exact)
};

// Type aliases for CGAL
using K = CGAL::Simple_cartesian<double>;
using Surface_mesh = CGAL::Surface_mesh<K::Point_3>;

// Exact kernel types for Nef polyhedra
using Exact_kernel = CGAL::Exact_predicates_exact_constructions_kernel;
using Nef_polyhedron = CGAL::Nef_polyhedron_3<Exact_kernel>;
using Exact_polyhedron = CGAL::Polyhedron_3<Exact_kernel>;
using Exact_surface_mesh = CGAL::Surface_mesh<Exact_kernel::Point_3>;

// Convert CGAL Surface_mesh to Manifold MeshGL
// The mesh must be triangulated before calling this function.
// If compute_normals is true, uses flat shading (face normals) by duplicating vertices per face.
manifold::MeshGL surface_mesh_to_meshgl(Surface_mesh& sm, bool compute_normals = true) {
    manifold::MeshGL meshgl;

    if (sm.number_of_faces() == 0) {
        return meshgl;
    }

    // Set up vertex properties: 3 for position, optionally 3 more for normals
    meshgl.numProp = compute_normals ? 6 : 3;

    if (compute_normals) {
        // Flat shading: duplicate vertices per face, each with the face normal
        meshgl.vertProperties.reserve(sm.number_of_faces() * 3 * meshgl.numProp);
        meshgl.triVerts.reserve(sm.number_of_faces() * 3);

        // Compute all face normals using CGAL
        using face_descriptor = Surface_mesh::Face_index;
        auto fnormals = sm.add_property_map<face_descriptor, K::Vector_3>("f:normals", CGAL::NULL_VECTOR).first;
        CGAL::Polygon_mesh_processing::compute_face_normals(sm, fnormals);

        uint32_t vert_idx = 0;
        for (auto f : sm.faces()) {
            K::Vector_3 normal = fnormals[f];

            // Get the three vertices of the face
            auto h = sm.halfedge(f);
            const auto& p0 = sm.point(sm.target(h));
            h = sm.next(h);
            const auto& p1 = sm.point(sm.target(h));
            h = sm.next(h);
            const auto& p2 = sm.point(sm.target(h));

            // Add three vertices with the same face normal (reversed for Manifold/PLY compatibility)
            for (const auto& pt : {p0, p1, p2}) {
                meshgl.vertProperties.push_back(static_cast<float>(pt.x()));
                meshgl.vertProperties.push_back(static_cast<float>(pt.y()));
                meshgl.vertProperties.push_back(static_cast<float>(pt.z()));
                meshgl.vertProperties.push_back(static_cast<float>(normal.x()));
                meshgl.vertProperties.push_back(static_cast<float>(normal.y()));
                meshgl.vertProperties.push_back(static_cast<float>(normal.z()));
            }

            // Add triangle indices
            meshgl.triVerts.push_back(vert_idx);
            meshgl.triVerts.push_back(vert_idx + 1);
            meshgl.triVerts.push_back(vert_idx + 2);
            vert_idx += 3;
        }
    } else {
        // No normals: share vertices
        meshgl.vertProperties.reserve(sm.number_of_vertices() * meshgl.numProp);
        meshgl.triVerts.reserve(sm.number_of_faces() * 3);

        // Copy vertices without normals
        for (auto v : sm.vertices()) {
            const auto& pt = sm.point(v);
            meshgl.vertProperties.push_back(static_cast<float>(pt.x()));
            meshgl.vertProperties.push_back(static_cast<float>(pt.y()));
            meshgl.vertProperties.push_back(static_cast<float>(pt.z()));
        }

        // Copy triangles (reverse winding order for Manifold/PLY compatibility)
        for (auto f : sm.faces()) {
            auto h = sm.halfedge(f);
            uint32_t v0 = static_cast<uint32_t>(sm.target(h));
            h = sm.next(h);
            uint32_t v1 = static_cast<uint32_t>(sm.target(h));
            h = sm.next(h);
            uint32_t v2 = static_cast<uint32_t>(sm.target(h));

            meshgl.triVerts.push_back(v0);
            meshgl.triVerts.push_back(v1);
            meshgl.triVerts.push_back(v2);
        }
    }

    return meshgl;
}

// Convert Surface_mesh (Simple_cartesian) to Exact_surface_mesh (Exact kernel)
Exact_surface_mesh surface_mesh_to_exact(const Surface_mesh& sm) {
    Exact_surface_mesh esm;

    // Map from original vertex indices to new vertex indices
    std::vector<Exact_surface_mesh::Vertex_index> vertex_map;
    vertex_map.reserve(sm.number_of_vertices());

    // Copy vertices with exact coordinates
    for (auto v : sm.vertices()) {
        const auto& pt = sm.point(v);
        Exact_kernel::Point_3 exact_pt(pt.x(), pt.y(), pt.z());
        vertex_map.push_back(esm.add_vertex(exact_pt));
    }

    // Copy faces
    for (auto f : sm.faces()) {
        std::vector<Exact_surface_mesh::Vertex_index> face_vertices;
        for (auto v : sm.vertices_around_face(sm.halfedge(f))) {
            face_vertices.push_back(vertex_map[v]);
        }
        esm.add_face(face_vertices);
    }

    return esm;
}

// Convert Exact_surface_mesh back to Surface_mesh (Simple_cartesian)
Surface_mesh exact_to_surface_mesh(const Exact_surface_mesh& esm) {
    Surface_mesh sm;

    std::vector<Surface_mesh::Vertex_index> vertex_map;
    vertex_map.reserve(esm.number_of_vertices());

    for (auto v : esm.vertices()) {
        const auto& pt = esm.point(v);
        K::Point_3 approx_pt(
            CGAL::to_double(pt.x()),
            CGAL::to_double(pt.y()),
            CGAL::to_double(pt.z())
        );
        vertex_map.push_back(sm.add_vertex(approx_pt));
    }

    for (auto f : esm.faces()) {
        std::vector<Surface_mesh::Vertex_index> face_vertices;
        for (auto v : esm.vertices_around_face(esm.halfedge(f))) {
            face_vertices.push_back(vertex_map[v]);
        }
        sm.add_face(face_vertices);
    }

    return sm;
}

// Boolean difference using CGAL Nef polyhedra
// Takes two Surface_mesh objects and returns their difference (mesh_a - mesh_b)
Surface_mesh nef_boolean_difference(const Surface_mesh& mesh_a, const Surface_mesh& mesh_b) {
    // Convert to exact kernel surface meshes
    auto exact_a = surface_mesh_to_exact(mesh_a);
    auto exact_b = surface_mesh_to_exact(mesh_b);

    // Convert to Nef polyhedra
    Nef_polyhedron nef_a(exact_a);
    Nef_polyhedron nef_b(exact_b);

    // Perform boolean difference
    Nef_polyhedron nef_result = nef_b - nef_a;

    // Convert result back to surface mesh
    Exact_surface_mesh exact_result;
    CGAL::convert_nef_polyhedron_to_polygon_mesh(nef_result, exact_result);

    // Convert back to simple cartesian kernel
    return exact_to_surface_mesh(exact_result);
}

// Boolean difference using CGAL Nef polyhedra (overload for multiple meshes to subtract)
Surface_mesh nef_boolean_difference(const Surface_mesh& mesh_a, const std::vector<Surface_mesh>& meshes_b) {
    // Convert mesh_a to exact kernel
    auto exact_a = surface_mesh_to_exact(mesh_a);
    Nef_polyhedron nef_result(exact_a);

    // Subtract each mesh in meshes_b
    for (const auto& mesh_b : meshes_b) {
        auto exact_b = surface_mesh_to_exact(mesh_b);
        Nef_polyhedron nef_b(exact_b);
        nef_result = nef_result - nef_b;
    }

    // Convert result back to surface mesh
    Exact_surface_mesh exact_result;
    CGAL::convert_nef_polyhedron_to_polygon_mesh(nef_result, exact_result);

    return exact_to_surface_mesh(exact_result);
}

// Boolean difference using CGAL PMP corefinement
Surface_mesh corefine_boolean_difference(const Surface_mesh& mesh_a, const Surface_mesh& mesh_b) {
    auto exact_a = surface_mesh_to_exact(mesh_a);
    auto exact_b = surface_mesh_to_exact(mesh_b);

    Exact_surface_mesh exact_result;
    bool success = CGAL::Polygon_mesh_processing::corefine_and_compute_difference(
        exact_a, exact_b, exact_result);

    if (!success) {
        std::cerr << "Warning: corefine_and_compute_difference failed" << std::endl;
    }

    return exact_to_surface_mesh(exact_result);
}

// Boolean difference using CGAL PMP corefinement (overload for multiple meshes to subtract)
Surface_mesh corefine_boolean_difference(const Surface_mesh& mesh_a, const std::vector<Surface_mesh>& meshes_b) {
    auto exact_a = surface_mesh_to_exact(mesh_a);

    for (const auto& mesh_b : meshes_b) {
        auto exact_b = surface_mesh_to_exact(mesh_b);

        Exact_surface_mesh exact_result;
        bool success = CGAL::Polygon_mesh_processing::corefine_and_compute_difference(
            exact_a, exact_b, exact_result);

        if (!success) {
            std::cerr << "Warning: corefine_and_compute_difference failed" << std::endl;
        }
        exact_a = std::move(exact_result);
    }

    return exact_to_surface_mesh(exact_a);
}

int main(int argc, char* argv[]) {
    if (argc < 5) {
        std::cerr << "Usage: " << argv[0] << " <cityjson_file> <cityjson_id> <ogr_source> <extrusion_height>" << std::endl;
        return 1;
    }

    Surface_mesh sm;
    bool ignore_holes = false;

    // Offset to bring coordinates near origin (set from first vertex)
    double offset_x = 0.0;
    double offset_y = 0.0;
    double offset_z = 0.0;

    const char* cityjson_id = argv[2];
    const char* ogr_source_path = argv[3];
    double extrusion_height = std::stod(argv[4]);

    CityJSONHandle cj = cityjson_create();
    if (cityjson_load(cj, argv[1]) == 0) {
      ssize_t idx = cityjson_get_object_index(cj, cityjson_id);
      if (idx >= 0) {
          size_t obj_idx = static_cast<size_t>(idx);
          size_t geom_count = cityjson_get_geometry_count(cj, obj_idx);
          std::cout << std::format("CJ Geometry count: {}", geom_count) << std::endl;

          if (geom_count > 0) {
              size_t last_geom = geom_count - 1; // select lod2 model...
              const double* verts = cityjson_get_vertices(cj, obj_idx, last_geom);
              size_t vert_count = cityjson_get_vertex_count(cj, obj_idx, last_geom);
              size_t face_count = cityjson_get_face_count(cj, obj_idx, last_geom);
              const size_t* indices = cityjson_get_indices(cj, obj_idx, last_geom);

              // print vert count
              std::cout << std::format("CJ Vertex count: {}", vert_count) << std::endl;
              // print face count
              std::cout << std::format("CJ Face count: {}", face_count) << std::endl;

              // Get the first vertex as offset (to bring coordinates near origin)
              offset_x = verts[0];
              offset_y = verts[1];
              offset_z = verts[2];

              // Add vertices to surface mesh with offset applied
              std::vector<Surface_mesh::Vertex_index> vertex_handles;
              vertex_handles.reserve(vert_count);
              for (size_t v = 0; v < vert_count; v++) {
                  K::Point_3 pt(
                      verts[v * 3] - offset_x,
                      verts[v * 3 + 1] - offset_y,
                      verts[v * 3 + 2] - offset_z
                  );
                  vertex_handles.push_back(sm.add_vertex(pt));
              }

              // Add faces to surface mesh
              for (size_t f = 0; f < face_count; f++) {
                  size_t start, count;
                  uint8_t face_type;
                  if (cityjson_get_face_info(cj, obj_idx, last_geom, f, &start, &count, &face_type) == 0) {
                      std::vector<Surface_mesh::Vertex_index> face_vertices;
                      face_vertices.reserve(count);
                      for (size_t i = 0; i < count; i++) {
                          face_vertices.push_back(vertex_handles[indices[start + i]]);
                      }
                      sm.add_face(face_vertices);
                  }
              }

              std::cout << std::format("House CGAL Surface_mesh- faces: {}, vertices: {}",
                  sm.number_of_faces(), sm.number_of_vertices()) << std::endl;

              // Write mesh to PLY file
              std::string ply_filename = std::format("house_{}_polygonal.ply", obj_idx);
              std::ofstream ply_out_(ply_filename, std::ios::binary);
              if (CGAL::IO::write_PLY(ply_out_, sm, std::format("CityJSON object {}", obj_idx))) {
                  std::cout << std::format("Wrote mesh to {}", ply_filename) << std::endl;
              } else {
                  std::cerr << std::format("Failed to write {}", ply_filename) << std::endl;
              }

              // Triangulate the mesh
              CGAL::Polygon_mesh_processing::triangulate_faces(sm);
              std::cout << std::format("After triangulation - faces: {}, vertices: {}",
                  sm.number_of_faces(), sm.number_of_vertices()) << std::endl;

              // Write mesh to PLY file
              ply_filename = std::format("house_{}.ply", obj_idx);
              std::ofstream ply_out(ply_filename, std::ios::binary);
              if (CGAL::IO::write_PLY(ply_out, sm, std::format("CityJSON object {}", obj_idx))) {
                  std::cout << std::format("Wrote mesh to {}", ply_filename) << std::endl;
              } else {
                  std::cerr << std::format("Failed to write {}", ply_filename) << std::endl;
              }
          }
      }
      cityjson_destroy(cj);
    }


    ogr::VectorReader reader;
    reader.open(ogr_source_path);
    auto polygons = reader.read_polygons();

#ifdef ENABLE_RERUN
    const auto rec = rerun::RecordingStream("test_3d_intersection");
    rec.spawn().exit_on_failure();
    extrusion::set_rerun_recording_stream(&rec);
#endif

    std::vector<extrusion::Surface_mesh> extruded_meshes;
    extruded_meshes.reserve(polygons.size());

    for (const auto& polygon : polygons) {
        // Apply offset to polygon coordinates
        ogr::LinearRing offset_polygon;
        offset_polygon.reserve(polygon.size());
        for (const auto& pt : polygon) {
            offset_polygon.push_back({pt[0] - offset_x, pt[1] - offset_y, pt[2] - offset_z});
        }
        for (const auto& hole : polygon.interior_rings()) {
            std::vector<std::array<double, 3>> offset_hole;
            offset_hole.reserve(hole.size());
            for (const auto& pt : hole) {
                offset_hole.push_back({pt[0] - offset_x, pt[1] - offset_y, pt[2] - offset_z});
            }
            offset_polygon.interior_rings().push_back(std::move(offset_hole));
        }

        auto extruded_mesh = extrusion::extrude_polygon(offset_polygon, -1.0, extrusion_height, ignore_holes);
        // CGAL::Polygon_mesh_processing::triangulate_faces(extruded_mesh);
        extruded_meshes.push_back(std::move(extruded_mesh));
        std::cout << "polygon has " << polygon.size() << " vertices and " << polygon.interior_rings().size() << " holes" << std::endl;
    }

    // Convert CityJSON mesh (house) to MeshGL with normals
    auto house_meshgl = surface_mesh_to_meshgl(sm, false);
    std::cout << std::format("House MeshGL - triangles: {}, vertices: {}, numProp: {}",
        house_meshgl.NumTri(), house_meshgl.NumVert(), house_meshgl.numProp) << std::endl;

    // Convert extruded meshes to MeshGL with normals
    std::vector<manifold::MeshGL> underpass_meshgls;
    for (size_t i = 0; i < extruded_meshes.size(); ++i) {
        auto& extruded_mesh = extruded_meshes[i];
        std::cout << std::format("Extruded mesh {} - CGAL faces: {}, vertices: {}",
            i, extruded_mesh.number_of_faces(), extruded_mesh.number_of_vertices()) << std::endl;
        auto meshgl = surface_mesh_to_meshgl(extruded_mesh, false);
        std::cout << std::format("  MeshGL triangles: {}, vertices: {}",
            meshgl.NumTri(), meshgl.NumVert()) << std::endl;
        if (meshgl.NumTri() > 0) {
            underpass_meshgls.push_back(meshgl);
        }
    }
    std::cout << std::format("Underpass MeshGLs count: {}", underpass_meshgls.size()) << std::endl;

#ifdef ENABLE_RERUN
    // Visualize house mesh (CityJSON building)
    viz::log_meshgl(rec, "house", house_meshgl, rerun::Rgba32(200, 200, 100, 255));

    // Visualize underpass meshes (extruded polygons)
    for (size_t i = 0; i < underpass_meshgls.size(); ++i) {
        viz::log_meshgl(rec, std::format("underpass/{}", i), underpass_meshgls[i],
                        rerun::Rgba32(100, 180, 220, 255));
    }
#endif

    // Select boolean operation method
    BooleanMethod method = BooleanMethod::CgalPMP;

    manifold::MeshGL result_meshgl;

    if (method == BooleanMethod::Manifold) {
        std::cout << "Using Manifold for boolean operations" << std::endl;

        // Convert to Manifold for boolean operations
        auto house = manifold::Manifold(house_meshgl);
        std::cout << std::format("House Manifold - status: {}, triangles: {}",
            static_cast<int>(house.Status()), house.NumTri()) << std::endl;

        manifold::Manifold underpass;
        for (const auto& meshgl : underpass_meshgls) {
            auto m = manifold::Manifold(meshgl);
            std::cout << std::format("  Underpass part - status: {}, triangles: {}",
                static_cast<int>(m.Status()), m.NumTri()) << std::endl;
            if (m.Status() == manifold::Manifold::Error::NoError) {
                underpass += m;
            }
        }
        std::cout << std::format("Underpass Manifold - triangles: {}", underpass.NumTri()) << std::endl;

        auto house_with_underpass = house - underpass;
        std::cout << std::format("Result Manifold - status: {}, triangles: {}",
            static_cast<int>(house_with_underpass.Status()), house_with_underpass.NumTri()) << std::endl;

        // Get the mesh and recompute with flat normals
        result_meshgl = house_with_underpass.GetMeshGL();

    } else if (method == BooleanMethod::CgalNef) {
        std::cout << "Using CGAL Nef polyhedra for boolean operations" << std::endl;

        // Collect underpass meshes as Surface_mesh
        std::vector<Surface_mesh> underpass_surfaces;
        underpass_surfaces.reserve(extruded_meshes.size());
        for (const auto& extruded_mesh : extruded_meshes) {
            underpass_surfaces.push_back(extruded_mesh);
        }

        std::cout << std::format("House Surface_mesh - faces: {}, vertices: {}",
            sm.number_of_faces(), sm.number_of_vertices()) << std::endl;
        std::cout << std::format("Underpass meshes count: {}", underpass_surfaces.size()) << std::endl;

        // Perform boolean difference using Nef polyhedra
        Surface_mesh result_sm = nef_boolean_difference(sm, underpass_surfaces);

        // Triangulate the result (Nef conversion may produce non-triangular faces)
        CGAL::Polygon_mesh_processing::triangulate_faces(result_sm);

        std::cout << std::format("Result Surface_mesh - faces: {}, vertices: {}",
            result_sm.number_of_faces(), result_sm.number_of_vertices()) << std::endl;

        // Convert to MeshGL for visualization and export (flip normals - Nef output has reversed winding)
        result_meshgl = surface_mesh_to_meshgl(result_sm, false);

    } else if (method == BooleanMethod::CgalPMP) {
        std::cout << "Using CGAL PMP corefinement for boolean operations" << std::endl;

        // Collect underpass meshes as Surface_mesh
        std::vector<Surface_mesh> underpass_surfaces;
        underpass_surfaces.reserve(extruded_meshes.size());
        for (const auto& extruded_mesh : extruded_meshes) {
            underpass_surfaces.push_back(extruded_mesh);
        }

        std::cout << std::format("House Surface_mesh - faces: {}, vertices: {}",
            sm.number_of_faces(), sm.number_of_vertices()) << std::endl;
        std::cout << std::format("Underpass meshes count: {}", underpass_surfaces.size()) << std::endl;

        // Perform boolean difference using PMP corefinement
        Surface_mesh result_sm = corefine_boolean_difference(sm, underpass_surfaces);

        std::cout << std::format("Result Surface_mesh - faces: {}, vertices: {}",
            result_sm.number_of_faces(), result_sm.number_of_vertices()) << std::endl;

        result_meshgl = surface_mesh_to_meshgl(result_sm, false);
    }

    std::cout << std::format("Result MeshGL - triangles: {}, vertices: {}, numProp: {}",
        result_meshgl.NumTri(), result_meshgl.NumVert(), result_meshgl.numProp) << std::endl;

#ifdef ENABLE_RERUN
    // Visualize result mesh (boolean difference)
    viz::log_meshgl(rec, "result", result_meshgl, rerun::Rgba32(100, 200, 100, 255));
#endif
    manifold::ExportMesh("house.ply", house_meshgl, {});
    manifold::ExportMesh("underpass.ply", underpass_meshgls.front(), {});
    manifold::ExportMesh("house_with_underpass.ply", result_meshgl, {});

    return 0;
}
