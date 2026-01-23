#include <iostream>
#include <format>

#include <manifold/manifold.h>
#include <manifold/meshIO.h>

#include <CGAL/Simple_cartesian.h>
#include <CGAL/Surface_mesh.h>
#include <CGAL/Polygon_mesh_processing/triangulate_faces.h>
#include <CGAL/Polygon_mesh_processing/compute_normal.h>

#ifdef ENABLE_RERUN
#include <rerun.hpp>
#endif

#include "zityjson.h"

#ifdef ENABLE_RERUN
// Custom collection adapter for Manifold vertex properties to Rerun Position3D
namespace rerun {
  template <>
  struct CollectionAdapter<Position3D, manifold::MeshGL> {
    Collection<Position3D> operator()(const manifold::MeshGL& mesh) {
      // Reinterpret the interleaved vertex properties as Position3D
      // vertProperties has stride numProp (default 3), first 3 values are x,y,z
      return Collection<Position3D>::borrow(
          reinterpret_cast<const Position3D*>(mesh.vertProperties.data()),
          mesh.NumVert()
      );
    }
  };

  // Custom collection adapter for Manifold triangle indices to Rerun TriangleIndices
  template <>
  struct CollectionAdapter<TriangleIndices, manifold::MeshGL> {
    Collection<TriangleIndices> operator()(const manifold::MeshGL& mesh) {
      // Reinterpret the flat triangle indices as TriangleIndices
      // triVerts has 3 indices per triangle
      return Collection<TriangleIndices>::borrow(
          reinterpret_cast<const TriangleIndices*>(mesh.triVerts.data()),
          mesh.NumTri()
      );
    }
  };
}
#endif

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0] << " <cityjson_file>" << std::endl;
        return 1;
    }

    CityJSONHandle cj = cityjson_create();
    if (cityjson_load(cj, argv[1]) == 0) {
        size_t count = cityjson_object_count(cj);
        for (size_t i = 0; i < count; i++) {
            const char* oid = cityjson_get_object_name(cj, i);
            size_t geom_count = cityjson_get_geometry_count(cj, i);
            for (size_t g = 0; g < geom_count; g++) {
                const double* verts = cityjson_get_vertices(cj, i, g);
                size_t vert_count = cityjson_get_vertex_count(cj, i, g);
                // std::cout << std::format("Object name: {}, geometry: {}", oid, g) << std::endl;
            }
        }
        size_t start, end;
        uint8_t type;
        cityjson_get_face_info(cj, 0, 0, 0, &start, &end, &type);
        std::cout << std::format("Face info: start={}, end={}, type={}", start, end, type) << std::endl;
    }

    typedef CGAL::Simple_cartesian<double> K;
    typedef CGAL::Surface_mesh<K::Point_3> Surface_mesh;

    Surface_mesh sm;

    ssize_t idx = cityjson_get_object_index(cj, "NL.IMBAG.Pand.1783100000021598-0");
    if (idx >= 0) {
        size_t obj_idx = static_cast<size_t>(idx);
        size_t geom_count = cityjson_get_geometry_count(cj, obj_idx);
        std::cout << std::format("Geometry count: {}", geom_count) << std::endl;

        if (geom_count > 0) {
            size_t last_geom = geom_count - 1;
            const double* verts = cityjson_get_vertices(cj, obj_idx, last_geom);
            size_t vert_count = cityjson_get_vertex_count(cj, obj_idx, last_geom);
            size_t face_count = cityjson_get_face_count(cj, obj_idx, last_geom);
            const size_t* indices = cityjson_get_indices(cj, obj_idx, last_geom);

            // Get the first vertex as offset (to bring coordinates near origin)
            double offset_x = verts[0];
            double offset_y = verts[1];
            double offset_z = verts[2];

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

            std::cout << std::format("CGAL Surface_mesh: {} vertices, {} faces",
                sm.number_of_vertices(), sm.number_of_faces()) << std::endl;

            // Triangulate the mesh
            CGAL::Polygon_mesh_processing::triangulate_faces(sm);
            std::cout << std::format("After triangulation: {} vertices, {} faces",
                sm.number_of_vertices(), sm.number_of_faces()) << std::endl;

            // Compute vertex normals
            auto vnormals = sm.add_property_map<Surface_mesh::Vertex_index, K::Vector_3>(
                "v:normals", CGAL::NULL_VECTOR).first;
            CGAL::Polygon_mesh_processing::compute_vertex_normals(sm, vnormals);
        }
    }
    cityjson_destroy(cj);

#ifdef ENABLE_RERUN
    const auto rec = rerun::RecordingStream("test_3d_intersection");
    rec.spawn().exit_on_failure();

    // Visualize the triangulated CityJSON mesh
    if (sm.number_of_faces() > 0) {
        std::vector<rerun::Position3D> positions;
        std::vector<rerun::TriangleIndices> triangles;
        std::vector<rerun::Vector3D> normals;

        // Get the vertex normals property map
        auto vnormals = sm.property_map<Surface_mesh::Vertex_index, K::Vector_3>("v:normals").value();

        positions.reserve(sm.number_of_vertices());
        normals.reserve(sm.number_of_vertices());
        for (auto v : sm.vertices()) {
            const auto& pt = sm.point(v);
            positions.push_back(rerun::Position3D(pt.x(), pt.y(), pt.z()));
            const auto& n = vnormals[v];
            normals.push_back(rerun::Vector3D(n.x(), n.y(), n.z()));
        }

        triangles.reserve(sm.number_of_faces());
        for (auto f : sm.faces()) {
            auto h = sm.halfedge(f);
            auto v0 = sm.target(h);
            h = sm.next(h);
            auto v1 = sm.target(h);
            h = sm.next(h);
            auto v2 = sm.target(h);
            triangles.push_back(rerun::TriangleIndices(
                static_cast<uint32_t>(v0),
                static_cast<uint32_t>(v1),
                static_cast<uint32_t>(v2)
            ));
        }

        rec.log(
            "cityjson_building",
            rerun::Mesh3D(positions)
                .with_triangle_indices(triangles)
                .with_vertex_normals(normals)
                .with_albedo_factor(rerun::Rgba32(200, 200, 100, 255))
        );
    }
#endif

    auto house_ = manifold::ImportMesh("sample_data/house.ply");
    auto underpass_ = manifold::ImportMesh("sample_data/underpass.ply");
    std::cout << std::format("Number of triangles: {}", house_.NumTri()) << std::endl;
    std::cout << std::format("Number of vertices: {}", house_.NumVert()) << std::endl;

    auto house = manifold::Manifold(house_);
    auto underpass = manifold::Manifold(underpass_);

#ifdef ENABLE_RERUN
    // Visualize house mesh
    auto houseMeshGL = house.GetMeshGL();
    rec.log(
        "house",
        rerun::Mesh3D(houseMeshGL)
            .with_triangle_indices(houseMeshGL)
            .with_albedo_factor(rerun::Rgba32(200, 100, 100, 255))
    );

    // Visualize underpass mesh
    auto underpassMeshGL = underpass.GetMeshGL();
    rec.log(
        "underpass",
        rerun::Mesh3D(underpassMeshGL)
            .with_triangle_indices(underpassMeshGL)
            .with_albedo_factor(rerun::Rgba32(100, 100, 200, 255))
    );
#endif

    auto house_with_underpass = house - underpass;

#ifdef ENABLE_RERUN
    // Visualize result mesh
    auto resultMeshGL = house_with_underpass.GetMeshGL();
    rec.log(
        "result",
        rerun::Mesh3D(resultMeshGL)
            .with_triangle_indices(resultMeshGL)
            .with_albedo_factor(rerun::Rgba32(100, 200, 100, 255))
    );
#endif

    manifold::ExportMesh("house_with_underpass.ply", house_with_underpass.GetMeshGL(), {});

    return 0;
}
