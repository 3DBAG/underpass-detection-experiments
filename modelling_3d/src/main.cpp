#include <iostream>
#include <format>
#include <cmath>
#include <stdexcept>
#include <chrono>
#include <string_view>
#include <unordered_map>
#include <vector>
#include <limits>

#include <manifold/manifold.h>
#include <manifold/meshIO.h>

#include <CGAL/Simple_cartesian.h>
#include <CGAL/Surface_mesh.h>
#include <CGAL/Polygon_mesh_processing/triangulate_faces.h>
#include <CGAL/Polygon_mesh_processing/compute_normal.h>
#include <CGAL/Exact_predicates_exact_constructions_kernel.h>
#include <CGAL/Nef_polyhedron_3.h>
#include <CGAL/Polyhedron_3.h>
#include <CGAL/boost/graph/convert_nef_polyhedron_to_polygon_mesh.h>
#include <CGAL/Polygon_mesh_processing/polygon_soup_to_polygon_mesh.h>
#include <CGAL/Polygon_mesh_processing/corefinement.h>

#include "zityjson.h"
#include "zfcb.h"
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
using Clock = std::chrono::steady_clock;

// Convert CGAL Surface_mesh to Manifold MeshGL
// The mesh must be triangulated before calling this function.
// If compute_normals is true, uses flat shading (face normals) by duplicating vertices per face.
manifold::MeshGL surface_mesh_to_meshgl(Surface_mesh& sm, bool compute_normals = true, bool flip_normals = false) {
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
                if (flip_normals) {
                  meshgl.vertProperties.push_back(static_cast<float>(-normal.x()));
                  meshgl.vertProperties.push_back(static_cast<float>(-normal.y()));
                  meshgl.vertProperties.push_back(static_cast<float>(-normal.z()));
                } else {
                  meshgl.vertProperties.push_back(static_cast<float>(normal.x()));
                  meshgl.vertProperties.push_back(static_cast<float>(normal.y()));
                  meshgl.vertProperties.push_back(static_cast<float>(normal.z()));
                }
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

bool is_fcb_path(const std::string_view path) {
    constexpr std::string_view ext = ".fcb";
    if (path.size() < ext.size()) {
        return false;
    }
    return path.substr(path.size() - ext.size()) == ext;
}

ssize_t resolve_cityjson_object_index(CityJSONHandle cj, std::string_view feature_id) {
    // try with '-0' suffix
    std::string id(feature_id);
    std::string with_suffix(id);
    with_suffix += "-0";
    ssize_t idx = cityjson_get_object_index(cj, with_suffix.c_str());
    if (idx >= 0) {
        return idx;
    }

    // try as is
    idx = cityjson_get_object_index(cj, id.c_str());
    if (idx >= 0) {
        return idx;
    }

    // try without '-0' suffix if it already has it
    constexpr std::string_view suffix = "-0";
    if (feature_id.size() >= suffix.size() &&
        feature_id.substr(feature_id.size() - suffix.size()) == suffix) {
        std::string trimmed(feature_id.substr(0, feature_id.size() - suffix.size()));
        return cityjson_get_object_index(cj, trimmed.c_str());
    }

    return -1;
}

bool load_cityjson_object_mesh(
    CityJSONHandle cj,
    size_t object_index,
    Surface_mesh& sm,
    double offset_x,
    double offset_y,
    double offset_z) {
    size_t geom_count = cityjson_get_geometry_count(cj, object_index);
    if (geom_count == 0) {
        return false;
    }

    size_t geom_idx = geom_count - 1;
    const double* verts = cityjson_get_vertices(cj, object_index, geom_idx);
    const size_t* indices = cityjson_get_indices(cj, object_index, geom_idx);
    size_t vert_count = cityjson_get_vertex_count(cj, object_index, geom_idx);
    size_t face_count = cityjson_get_face_count(cj, object_index, geom_idx);

    if (verts == nullptr || indices == nullptr || vert_count == 0 || face_count == 0) {
        return false;
    }

    std::vector<Surface_mesh::Vertex_index> vertex_handles;
    vertex_handles.reserve(vert_count);
    for (size_t v = 0; v < vert_count; ++v) {
        vertex_handles.push_back(sm.add_vertex(K::Point_3(
            verts[v * 3] - offset_x,
            verts[v * 3 + 1] - offset_y,
            verts[v * 3 + 2] - offset_z)));
    }

    for (size_t f = 0; f < face_count; ++f) {
        size_t start = 0;
        size_t count = 0;
        uint8_t face_type = 0;
        if (cityjson_get_face_info(cj, object_index, geom_idx, f, &start, &count, &face_type) != 0) {
            continue;
        }
        std::vector<Surface_mesh::Vertex_index> face_vertices;
        face_vertices.reserve(count);
        for (size_t i = 0; i < count; ++i) {
            face_vertices.push_back(vertex_handles[indices[start + i]]);
        }
        sm.add_face(face_vertices);
    }

    CGAL::Polygon_mesh_processing::triangulate_faces(sm);
    return sm.number_of_faces() > 0;
}

bool append_fcb_geometry_faces(
    const std::vector<Surface_mesh::Vertex_index>& vertex_handles,
    size_t vertex_count,
    const uint32_t* surfaces,
    size_t surface_count,
    const uint32_t* strings,
    size_t string_count,
    const uint32_t* boundaries,
    size_t boundary_count,
    Surface_mesh& sm) {
    if (surfaces == nullptr || strings == nullptr || boundaries == nullptr) {
        return false;
    }
    if (surface_count == 0 || string_count == 0 || boundary_count == 0) {
        return false;
    }

    size_t ring_cursor = 0;
    size_t boundary_cursor = 0;
    bool added_faces = false;

    for (size_t s = 0; s < surface_count; ++s) {
        if (ring_cursor >= string_count || boundary_cursor >= boundary_count) {
            break;
        }

        size_t rings_in_surface = static_cast<size_t>(surfaces[s]);
        if (rings_in_surface == 0) {
            continue;
        }

        size_t outer_ring_size = static_cast<size_t>(strings[ring_cursor]);
        if (outer_ring_size >= 3 && boundary_cursor + outer_ring_size <= boundary_count) {
            std::vector<Surface_mesh::Vertex_index> face_vertices;
            face_vertices.reserve(outer_ring_size);

            bool valid_face = true;
            for (size_t i = 0; i < outer_ring_size; ++i) {
                uint32_t idx = boundaries[boundary_cursor + i];
                if (idx >= vertex_count) {
                    valid_face = false;
                    break;
                }
                face_vertices.push_back(vertex_handles[idx]);
            }

            if (valid_face) {
                sm.add_face(face_vertices);
                added_faces = true;
            }
        }

        for (size_t r = 0; r < rings_in_surface && ring_cursor < string_count; ++r, ++ring_cursor) {
            size_t ring_size = static_cast<size_t>(strings[ring_cursor]);
            if (boundary_cursor + ring_size > boundary_count) {
                boundary_cursor = boundary_count;
                break;
            }
            boundary_cursor += ring_size;
        }
    }

    return added_faces;
}

bool load_fcb_feature_mesh(
    ZfcbReaderHandle fcb,
    std::string_view feature_id,
    Surface_mesh& sm,
    double offset_x,
    double offset_y,
    double offset_z) {
    size_t vertex_count = zfcb_current_vertex_count(fcb);
    const double* vertices = zfcb_current_vertices(fcb);
    if (vertices == nullptr || vertex_count == 0) {
        return false;
    }

    std::vector<Surface_mesh::Vertex_index> vertex_handles;
    vertex_handles.reserve(vertex_count);
    for (size_t v = 0; v < vertex_count; ++v) {
        vertex_handles.push_back(sm.add_vertex(K::Point_3(
            vertices[v * 3] - offset_x,
            vertices[v * 3 + 1] - offset_y,
            vertices[v * 3 + 2] - offset_z)));
    }

    std::string object_id = std::string(feature_id) + "-0";
    ssize_t object_index = -1;
    size_t object_count = zfcb_current_object_count(fcb);
    for (size_t obj_idx = 0; obj_idx < object_count; ++obj_idx) {
        const char* current_obj_id_ptr = nullptr;
        size_t current_obj_id_len = 0;
        if (zfcb_current_object_id(fcb, obj_idx, &current_obj_id_ptr, &current_obj_id_len) != 0) {
            continue;
        }
        std::string_view current_obj_id(current_obj_id_ptr, current_obj_id_len);
        if (current_obj_id == object_id) {
            object_index = static_cast<ssize_t>(obj_idx);
            break;
        }
    }
    if (object_index < 0) {
        return false;
    }

    ssize_t geometry_index = -1;
    size_t geom_count = zfcb_current_object_geometry_count(fcb, static_cast<size_t>(object_index));
    for (size_t geom_idx = 0; geom_idx < geom_count; ++geom_idx) {
        uint8_t geom_type = zfcb_current_geometry_type(fcb, static_cast<size_t>(object_index), geom_idx);
        bool solid_like = geom_type == ZFCB_GEOMETRY_SOLID ||
                          geom_type == ZFCB_GEOMETRY_MULTI_SOLID ||
                          geom_type == ZFCB_GEOMETRY_COMPOSITE_SOLID;
        if (!solid_like) {
            continue;
        }

        const char* lod_ptr = nullptr;
        size_t lod_len = 0;
        if (zfcb_current_geometry_lod(fcb, static_cast<size_t>(object_index), geom_idx, &lod_ptr, &lod_len) != 0) {
            continue;
        }
        std::string_view lod = (lod_ptr != nullptr) ? std::string_view(lod_ptr, lod_len) : std::string_view{};
        if (lod == "2.2") {
            geometry_index = static_cast<ssize_t>(geom_idx);
            break;
        }
    }
    if (geometry_index < 0) {
        return false;
    }

    size_t geom_idx = static_cast<size_t>(geometry_index);
    size_t surface_count = zfcb_current_geometry_surface_count(fcb, static_cast<size_t>(object_index), geom_idx);
    size_t string_count = zfcb_current_geometry_string_count(fcb, static_cast<size_t>(object_index), geom_idx);
    size_t boundary_count = zfcb_current_geometry_boundary_count(fcb, static_cast<size_t>(object_index), geom_idx);
    const uint32_t* surfaces = zfcb_current_geometry_surfaces(fcb, static_cast<size_t>(object_index), geom_idx);
    const uint32_t* strings = zfcb_current_geometry_strings(fcb, static_cast<size_t>(object_index), geom_idx);
    const uint32_t* boundaries = zfcb_current_geometry_boundaries(fcb, static_cast<size_t>(object_index), geom_idx);

    bool added_faces = append_fcb_geometry_faces(
        vertex_handles,
        vertex_count,
        surfaces,
        surface_count,
        strings,
        string_count,
        boundaries,
        boundary_count,
        sm);
    if (!added_faces) {
        return false;
    }

    CGAL::Polygon_mesh_processing::triangulate_faces(sm);
    return sm.number_of_faces() > 0;
}

double mesh_min_z(const Surface_mesh& sm) {
    double min_z = std::numeric_limits<double>::infinity();
    for (auto v : sm.vertices()) {
        const double z = sm.point(v).z();
        if (z < min_z) {
            min_z = z;
        }
    }
    return min_z;
}

ogr::LinearRing make_offset_polygon(
    const ogr::LinearRing& polygon,
    double offset_x,
    double offset_y,
    double offset_z) {
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
    return offset_polygon;
}

void append_meshgl(manifold::MeshGL& dst, const manifold::MeshGL& src) {
    if (src.NumTri() == 0) {
        return;
    }
    if (dst.numProp == 0) {
        dst.numProp = src.numProp;
    }
    if (dst.numProp != src.numProp) {
        throw std::runtime_error("Cannot append MeshGL with different numProp");
    }

    uint32_t vertex_offset = static_cast<uint32_t>(dst.vertProperties.size() / dst.numProp);
    dst.vertProperties.insert(dst.vertProperties.end(), src.vertProperties.begin(), src.vertProperties.end());
    dst.triVerts.reserve(dst.triVerts.size() + src.triVerts.size());
    for (uint32_t tri_vert : src.triVerts) {
        dst.triVerts.push_back(vertex_offset + tri_vert);
    }
}

void apply_meshgl_offset(manifold::MeshGL& mesh, double offset_x, double offset_y, double offset_z) {
    if (mesh.numProp < 3) {
        return;
    }
    for (size_t i = 0; i + 2 < mesh.vertProperties.size(); i += mesh.numProp) {
        mesh.vertProperties[i] += static_cast<float>(offset_x);
        mesh.vertProperties[i + 1] += static_cast<float>(offset_y);
        mesh.vertProperties[i + 2] += static_cast<float>(offset_z);
    }
}

int main(int argc, char* argv[]) {
    auto t_program_start = Clock::now();

    if (argc < 4) {
        std::cerr << "Usage: " << argv[0]
                  << " <cityjson_or_fcb_file> <ogr_source> <height_attribute> [id_attribute] [method] [output_fcb]" << std::endl;
        std::cerr << "  id_attribute default: identificatie" << std::endl;
        std::cerr << "  method: manifold (default), nef, pmp" << std::endl;
        std::cerr << "  output_fcb: path for FCB output (only used when input is .fcb)" << std::endl;
        return 1;
    }

    const char* model_path = argv[1];
    const char* ogr_source_path = argv[2];
    std::string height_attribute = argv[3];
    std::string id_attribute = argc > 4 ? argv[4] : "identificatie";
    std::string method_str = argc > 5 ? argv[5] : "manifold";
    bool undo_offset = false;
    const char* output_fcb_path = argc > 6 ? argv[6] : nullptr;

    BooleanMethod method = BooleanMethod::Manifold;
    if (method_str == "nef") {
        method = BooleanMethod::CgalNef;
    } else if (method_str == "pmp") {
        method = BooleanMethod::CgalPMP;
    } else if (method_str != "manifold") {
        std::cerr << "Unknown method: " << method_str << " (use manifold, nef, or pmp)" << std::endl;
        return 1;
    }

    const bool use_fcb_input = is_fcb_path(model_path);

    ogr::VectorReader reader;
    auto t_ogr_read_start = Clock::now();
    reader.open(ogr_source_path);
    auto polygon_features = reader.read_polygon_features(id_attribute, height_attribute);
    auto t_ogr_read_end = Clock::now();
    std::cout << std::format("Read {} polygon features", polygon_features.size()) << std::endl;
    std::cout << std::format("Model input: {} ({})",
                             model_path,
                             use_fcb_input ? "FlatCityBuf stream" : "CityJSON") << std::endl;

    CityJSONHandle cj = nullptr;
    ZfcbReaderHandle fcb = nullptr;
    auto t_model_read_start = Clock::now();
    if (use_fcb_input) {
        fcb = zfcb_reader_open(model_path);
        if (fcb == nullptr) {
            std::cerr << "Failed to open FlatCityBuf stream: " << model_path << std::endl;
            return 1;
        }
    } else {
        cj = cityjson_create();
        if (cj == nullptr) {
            std::cerr << "Failed to create CityJSON handle" << std::endl;
            return 1;
        }
        int json_load_result = cityjson_load(cj, model_path);
        if (json_load_result != 0) {
            std::cerr << "Failed to load CityJSON: " << model_path << std::endl;
            cityjson_destroy(cj);
            return 1;
        }
    }
    auto t_model_read_end = Clock::now();

    bool ignore_holes = false;
    manifold::MeshGL combined_result_meshgl;
    size_t processed_count = 0;
    size_t skipped_count = 0;
    bool global_offset_set = false;
    double global_offset_x = 0.0;
    double global_offset_y = 0.0;
    double global_offset_z = 0.0;
    std::chrono::duration<double, std::milli> ds_conversion_ms{0.0};
    std::chrono::duration<double, std::milli> intersection_ms{0.0};

    if (!use_fcb_input) {
        for (size_t i = 0; i < polygon_features.size(); ++i) {
            const auto& feature = polygon_features[i];
            if (feature.id.empty()) {
                std::cerr << std::format("Skipping feature {}: empty id attribute '{}'", i, id_attribute) << std::endl;
                ++skipped_count;
                continue;
            }
            if (!std::isfinite(feature.extrusion_height)) {
                std::cerr << std::format("Skipping feature {} (id='{}'): invalid height attribute '{}'",
                                         i, feature.id, height_attribute) << std::endl;
                ++skipped_count;
                continue;
            }

            ssize_t idx = resolve_cityjson_object_index(cj, feature.id);
            if (idx < 0) {
                std::cerr << std::format("Skipping feature {}: CityJSON object not found for id '{}'",
                                         i, feature.id) << std::endl;
                ++skipped_count;
                continue;
            }

            if (!global_offset_set) {
                size_t obj_idx = static_cast<size_t>(idx);
                size_t geom_count = cityjson_get_geometry_count(cj, obj_idx);
                if (geom_count == 0) {
                    std::cerr << std::format("Skipping feature {} (id='{}'): no CityJSON geometry", i, feature.id)
                              << std::endl;
                    ++skipped_count;
                    continue;
                }
                // get the last geometry index. We're Assuming it is the lod2.2 geometry here.
                size_t geom_idx = geom_count - 1;
                const double* verts = cityjson_get_vertices(cj, obj_idx, geom_idx);
                size_t vert_count = cityjson_get_vertex_count(cj, obj_idx, geom_idx);
                if (verts == nullptr || vert_count == 0) {
                    std::cerr << std::format("Skipping feature {} (id='{}'): invalid CityJSON vertices", i, feature.id)
                              << std::endl;
                    ++skipped_count;
                    continue;
                }
                global_offset_x = verts[0];
                global_offset_y = verts[1];
                global_offset_z = verts[2];
                global_offset_set = true;
                std::cout << std::format("Global offset set to ({}, {}, {})",
                                         global_offset_x, global_offset_y, global_offset_z) << std::endl;
            }

            auto t_conversion_start = Clock::now();
            Surface_mesh house_sm;
            if (!load_cityjson_object_mesh(cj, static_cast<size_t>(idx), house_sm,
                                           global_offset_x, global_offset_y, global_offset_z)) {
                std::cerr << std::format("Skipping feature {} (id='{}'): could not build CityJSON mesh", i, feature.id)
                          << std::endl;
                ++skipped_count;
                continue;
            }

            const double house_min_z_local = mesh_min_z(house_sm);
            if (!std::isfinite(house_min_z_local)) {
                std::cerr << std::format("Skipping feature {} (id='{}'): could not determine house min z", i, feature.id)
                          << std::endl;
                ++skipped_count;
                continue;
            }
            auto offset_polygon = make_offset_polygon(
                feature.polygon,
                global_offset_x,
                global_offset_y,
                global_offset_z);
            auto underpass_sm = extrusion::extrude_polygon(
                offset_polygon, house_min_z_local-0.1, feature.extrusion_height + 0.1, ignore_holes);
            auto t_conversion_end = Clock::now();
            ds_conversion_ms += t_conversion_end - t_conversion_start;

            manifold::MeshGL result_meshgl;
            auto t_intersection_start = Clock::now();
            if (method == BooleanMethod::Manifold) {
                auto house_meshgl = surface_mesh_to_meshgl(house_sm, false);
                auto underpass_meshgl = surface_mesh_to_meshgl(underpass_sm, false);
                if (house_meshgl.NumTri() == 0 || underpass_meshgl.NumTri() == 0) {
                    std::cerr << std::format("Skipping feature {} (id='{}'): empty house or underpass mesh",
                                             i, feature.id) << std::endl;
                    ++skipped_count;
                    continue;
                }

                manifold::Manifold house(house_meshgl);
                manifold::Manifold underpass(underpass_meshgl);
                if (house.Status() != manifold::Manifold::Error::NoError ||
                    underpass.Status() != manifold::Manifold::Error::NoError) {
                    std::cerr << std::format("Skipping feature {} (id='{}'): invalid manifold input", i, feature.id)
                              << std::endl;
                    ++skipped_count;
                    continue;
                }

                auto result = house - underpass;
                if (result.Status() != manifold::Manifold::Error::NoError) {
                    std::cerr << std::format("Skipping feature {} (id='{}'): manifold boolean failed", i, feature.id)
                              << std::endl;
                    ++skipped_count;
                    continue;
                }
                result_meshgl = result.GetMeshGL();
            } else if (method == BooleanMethod::CgalNef) {
                Surface_mesh result_sm = nef_boolean_difference(house_sm, underpass_sm);
                CGAL::Polygon_mesh_processing::triangulate_faces(result_sm);
                result_meshgl = surface_mesh_to_meshgl(result_sm, false);
            } else {
                Surface_mesh result_sm = corefine_boolean_difference(house_sm, underpass_sm);
                CGAL::Polygon_mesh_processing::triangulate_faces(result_sm);
                result_meshgl = surface_mesh_to_meshgl(result_sm, false);
            }
            auto t_intersection_end = Clock::now();
            intersection_ms += t_intersection_end - t_intersection_start;

            if (result_meshgl.NumTri() == 0) {
                std::cerr << std::format("Skipping feature {} (id='{}'): boolean produced empty mesh", i, feature.id)
                          << std::endl;
                ++skipped_count;
                continue;
            }

            append_meshgl(combined_result_meshgl, result_meshgl);
            ++processed_count;
        }
    } else {
        // FCB streaming mode: read features, process matching ones, write all to output.
        ZfcbWriterHandle fcb_writer = nullptr;
        if (output_fcb_path != nullptr) {
            fcb_writer = zfcb_writer_open_from_reader(fcb, output_fcb_path);
            if (fcb_writer == nullptr) {
                std::cerr << "Failed to open FCB writer: " << output_fcb_path << std::endl;
                zfcb_reader_destroy(fcb);
                return 1;
            }
            std::cout << std::format("FCB output: {}", output_fcb_path) << std::endl;
        }

        std::unordered_map<std::string_view, std::vector<size_t>> features_by_exact_id;
        std::vector<size_t> valid_feature_indices;
        std::vector<bool> seen_feature(polygon_features.size(), false);
        for (size_t i = 0; i < polygon_features.size(); ++i) {
            const auto& feature = polygon_features[i];
            if (feature.id.empty()) {
                std::cerr << std::format("Skipping feature {}: empty id attribute '{}'", i, id_attribute) << std::endl;
                ++skipped_count;
                continue;
            }
            if (!std::isfinite(feature.extrusion_height)) {
                std::cerr << std::format("Skipping feature {} (id='{}'): invalid height attribute '{}'",
                                         i, feature.id, height_attribute) << std::endl;
                ++skipped_count;
                continue;
            }
            std::string_view exact_id(feature.id);
            features_by_exact_id[exact_id].push_back(i);
            valid_feature_indices.push_back(i);
        }

        bool stream_error = false;
        while (true) {
            const char* peek_id_ptr = nullptr;
            size_t peek_id_len = 0;
            int peek_result = zfcb_peek_next_id(fcb, &peek_id_ptr, &peek_id_len);
            if (peek_result < 0) {
                std::cerr << "FlatCityBuf stream error while peeking next feature id" << std::endl;
                stream_error = true;
                break;
            }
            if (peek_result == 0) {
                break;
            }

            std::string_view next_id(peek_id_ptr, peek_id_len);
            auto exact_hint_it = features_by_exact_id.find(next_id);
            if (exact_hint_it == features_by_exact_id.end()) {
                // Non-matching feature: pass through raw to output.
                if (fcb_writer != nullptr) {
                    int write_result = zfcb_writer_write_pending_raw(fcb, fcb_writer);
                    if (write_result < 0) {
                        std::cerr << "FlatCityBuf stream error while writing pass-through feature" << std::endl;
                        stream_error = true;
                        break;
                    }
                    if (write_result == 0) {
                        break;
                    }
                } else {
                    int skip_result = zfcb_skip_next(fcb);
                    if (skip_result < 0) {
                        std::cerr << "FlatCityBuf stream error while skipping feature" << std::endl;
                        stream_error = true;
                        break;
                    }
                    if (skip_result == 0) {
                        break;
                    }
                }
                continue;
            }

            int next_result = zfcb_next(fcb);
            if (next_result < 0) {
                std::cerr << "FlatCityBuf stream error while decoding feature" << std::endl;
                stream_error = true;
                break;
            }
            if (next_result == 0) {
                break;
            }

            const auto& matched_indices = exact_hint_it->second;

            const double* verts = zfcb_current_vertices(fcb);
            size_t vert_count = zfcb_current_vertex_count(fcb);
            if (!global_offset_set) {
                if (verts == nullptr || vert_count == 0) {
                    for (size_t feature_idx : matched_indices) {
                        seen_feature[feature_idx] = true;
                        const auto& feature = polygon_features[feature_idx];
                        std::cerr << std::format("Skipping ogr feature {} (id='{}'): invalid FlatCityBuf vertices",
                                                 feature_idx, feature.id) << std::endl;
                        ++skipped_count;
                    }
                    if (fcb_writer != nullptr) {
                        zfcb_writer_write_current_raw(fcb, fcb_writer);
                    }
                    continue;
                }
                global_offset_x = verts[0];
                global_offset_y = verts[1];
                global_offset_z = verts[2];
                global_offset_set = true;
                std::cout << std::format("Global offset set to ({}, {}, {})",
                                         global_offset_x, global_offset_y, global_offset_z) << std::endl;
            }

            Surface_mesh house_sm;
            if (!load_fcb_feature_mesh(fcb, next_id, house_sm, global_offset_x, global_offset_y, global_offset_z)) {
                for (size_t feature_idx : matched_indices) {
                    seen_feature[feature_idx] = true;
                    const auto& feature = polygon_features[feature_idx];
                    std::cerr << std::format("Skipping feature {} (id='{}'): could not build FlatCityBuf mesh",
                                             feature_idx, feature.id) << std::endl;
                    ++skipped_count;
                }
                // Write unmodified feature to output.
                if (fcb_writer != nullptr) {
                    zfcb_writer_write_current_raw(fcb, fcb_writer);
                }
                continue;
            }

            // Track whether any polygon feature succeeded for this FCB feature.
            bool any_succeeded = false;
            manifold::MeshGL last_result_meshgl;

            for (size_t feature_idx : matched_indices) {
                seen_feature[feature_idx] = true;
                const auto& feature = polygon_features[feature_idx];

                auto t_conversion_start = Clock::now();
                const double house_min_z_local = mesh_min_z(house_sm);
                if (!std::isfinite(house_min_z_local)) {
                    std::cerr << std::format("Skipping feature {} (id='{}'): could not determine house min z",
                                             feature_idx, feature.id) << std::endl;
                    ++skipped_count;
                    continue;
                }
                auto offset_polygon = make_offset_polygon(
                    feature.polygon,
                    global_offset_x,
                    global_offset_y,
                    global_offset_z);
                auto underpass_sm = extrusion::extrude_polygon(
                    offset_polygon, house_min_z_local-0.1, feature.extrusion_height + 0.1, ignore_holes);
                auto t_conversion_end = Clock::now();
                ds_conversion_ms += t_conversion_end - t_conversion_start;

                manifold::MeshGL result_meshgl;
                auto t_intersection_start = Clock::now();
                if (method == BooleanMethod::Manifold) {
                    auto house_meshgl = surface_mesh_to_meshgl(house_sm, false);
                    auto underpass_meshgl = surface_mesh_to_meshgl(underpass_sm, false);
                    if (house_meshgl.NumTri() == 0 || underpass_meshgl.NumTri() == 0) {
                        std::cerr << std::format("Skipping feature {} (id='{}'): empty house or underpass mesh",
                                                 feature_idx, feature.id) << std::endl;
                        ++skipped_count;
                        continue;
                    }

                    manifold::Manifold house(house_meshgl);
                    manifold::Manifold underpass(underpass_meshgl);
                    if (house.Status() != manifold::Manifold::Error::NoError ||
                        underpass.Status() != manifold::Manifold::Error::NoError) {
                        std::cerr << std::format("Skipping feature {} (id='{}'): invalid manifold input",
                                                 feature_idx, feature.id) << std::endl;
                        ++skipped_count;
                        continue;
                    }

                    auto result = house - underpass;
                    if (result.Status() != manifold::Manifold::Error::NoError) {
                        std::cerr << std::format("Skipping feature {} (id='{}'): manifold boolean failed",
                                                 feature_idx, feature.id) << std::endl;
                        ++skipped_count;
                        continue;
                    }
                    result_meshgl = result.GetMeshGL();
                } else if (method == BooleanMethod::CgalNef) {
                    Surface_mesh result_sm = nef_boolean_difference(house_sm, underpass_sm);
                    CGAL::Polygon_mesh_processing::triangulate_faces(result_sm);
                    result_meshgl = surface_mesh_to_meshgl(result_sm, false);
                } else {
                    Surface_mesh result_sm = corefine_boolean_difference(house_sm, underpass_sm);
                    CGAL::Polygon_mesh_processing::triangulate_faces(result_sm);
                    result_meshgl = surface_mesh_to_meshgl(result_sm, false);
                }
                auto t_intersection_end = Clock::now();
                intersection_ms += t_intersection_end - t_intersection_start;

                if (result_meshgl.NumTri() == 0) {
                    std::cerr << std::format("Skipping feature {} (id='{}'): boolean produced empty mesh",
                                             feature_idx, feature.id) << std::endl;
                    ++skipped_count;
                    continue;
                }

                append_meshgl(combined_result_meshgl, result_meshgl);
                last_result_meshgl = std::move(result_meshgl);
                any_succeeded = true;
                ++processed_count;
            }

            // Write the feature to FCB output.
            if (fcb_writer != nullptr) {
                if (any_succeeded && last_result_meshgl.NumTri() > 0) {
                    // Extract world-coordinate vertices from result mesh
                    // (undo the global offset that was subtracted during loading).
                    size_t num_verts = last_result_meshgl.NumVert();
                    size_t num_prop = last_result_meshgl.numProp;
                    std::vector<double> world_verts(num_verts * 3);
                    for (size_t v = 0; v < num_verts; ++v) {
                        world_verts[v * 3 + 0] = static_cast<double>(last_result_meshgl.vertProperties[v * num_prop + 0]) + global_offset_x;
                        world_verts[v * 3 + 1] = static_cast<double>(last_result_meshgl.vertProperties[v * num_prop + 1]) + global_offset_y;
                        world_verts[v * 3 + 2] = static_cast<double>(last_result_meshgl.vertProperties[v * num_prop + 2]) + global_offset_z;
                    }

                    std::string feature_id_str(next_id);
                    int write_result = zfcb_writer_write_current_replaced_lod22(
                        fcb, fcb_writer,
                        feature_id_str.c_str(), feature_id_str.size(),
                        world_verts.data(), num_verts,
                        last_result_meshgl.triVerts.data(), last_result_meshgl.triVerts.size());
                    if (write_result < 0) {
                        std::cerr << std::format("Warning: failed to write modified feature '{}' to FCB, writing raw instead",
                                                 feature_id_str) << std::endl;
                        zfcb_writer_write_current_raw(fcb, fcb_writer);
                    }
                } else {
                    // No successful boolean: write original feature.
                    zfcb_writer_write_current_raw(fcb, fcb_writer);
                }
            }
        }

        if (fcb_writer != nullptr) {
            zfcb_writer_destroy(fcb_writer);
        }

        if (stream_error) {
            zfcb_reader_destroy(fcb);
            return 1;
        }

        for (size_t feature_idx : valid_feature_indices) {
            if (seen_feature[feature_idx]) {
                continue;
            }
            const auto& feature = polygon_features[feature_idx];
            std::cerr << std::format("Skipping feature {}: FlatCityBuf feature not found for id '{}'",
                                     feature_idx, feature.id) << std::endl;
            ++skipped_count;
        }
    }

    if (use_fcb_input) {
        zfcb_reader_destroy(fcb);
    } else {
        cityjson_destroy(cj);
    }

    std::cout << std::format("Processed features: {}, skipped: {}", processed_count, skipped_count) << std::endl;

    auto t_output_write_start = Clock::now();
    if (use_fcb_input && output_fcb_path != nullptr) {
        // FCB output was already written during streaming.
        if (processed_count == 0) {
            std::cerr << "Warning: no features were modified; output FCB is a copy of input." << std::endl;
        }
    } else {
        if (processed_count == 0 || combined_result_meshgl.NumTri() == 0) {
            std::cerr << "No meshes processed successfully; no output written." << std::endl;
            return 1;
        }

        std::cout << std::format("Final mesh - triangles: {}, vertices: {}",
                                 combined_result_meshgl.NumTri(), combined_result_meshgl.NumVert()) << std::endl;

        if (undo_offset && global_offset_set) {
            apply_meshgl_offset(combined_result_meshgl, global_offset_x, global_offset_y, global_offset_z);
        }

        manifold::ExportMesh("house_with_underpass.ply", combined_result_meshgl, {});
    }
    auto t_output_write_end = Clock::now();

    auto ogr_read_ms = std::chrono::duration<double, std::milli>(t_ogr_read_end - t_ogr_read_start).count();
    auto model_read_ms = std::chrono::duration<double, std::milli>(t_model_read_end - t_model_read_start).count();
    auto output_write_ms = std::chrono::duration<double, std::milli>(t_output_write_end - t_output_write_start).count();
    auto total_ms = std::chrono::duration<double, std::milli>(t_output_write_end - t_program_start).count();

    std::cout << "Timing profile (ms):" << std::endl;
    std::cout << std::format("  model reading: {:.3f}", model_read_ms) << std::endl;
    std::cout << std::format("  ogr reading: {:.3f}", ogr_read_ms) << std::endl;
    std::cout << std::format("  datastructure conversion: {:.3f}", ds_conversion_ms.count()) << std::endl;
    std::cout << std::format("  intersecting: {:.3f}", intersection_ms.count()) << std::endl;
    std::cout << std::format("  output writing: {:.3f}", output_write_ms) << std::endl;
    std::cout << std::format("  total: {:.3f}", total_ms) << std::endl;

    return 0;
}
