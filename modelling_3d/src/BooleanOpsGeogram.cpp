#include "BooleanOps.h"

#include <chrono>
#include <vector>

#include <geogram/basic/common.h>
#include <geogram/mesh/mesh_surface_intersection.h>

using Clock = std::chrono::steady_clock;

void ensure_geogram_initialized() {
    static const bool initialized = []() {
        GEO::initialize(GEO::GEOGRAM_INSTALL_NONE);
        return true;
    }();
    (void)initialized;
}

void surface_mesh_to_geogram_mesh(const Surface_mesh& sm, GEO::Mesh& geo_mesh) {
    geo_mesh.clear();

    GEO::vector<double> vertices;
    vertices.reserve(sm.number_of_vertices() * 3);
    std::vector<GEO::index_t> vertex_map(sm.number_of_vertices(), GEO::NO_INDEX);
    GEO::index_t next_vertex = 0;

    for (auto v : sm.vertices()) {
        const auto& pt = sm.point(v);
        vertices.push_back(pt.x());
        vertices.push_back(pt.y());
        vertices.push_back(pt.z());
        vertex_map[v] = next_vertex++;
    }

    GEO::vector<GEO::index_t> triangles;
    triangles.reserve(sm.number_of_faces() * 3);

    for (auto f : sm.faces()) {
        std::vector<GEO::index_t> face_vertices;
        for (auto v : sm.vertices_around_face(sm.halfedge(f))) {
            face_vertices.push_back(vertex_map[v]);
        }
        if (face_vertices.size() < 3) {
            continue;
        }
        for (size_t i = 1; i + 1 < face_vertices.size(); ++i) {
            triangles.push_back(face_vertices[0]);
            triangles.push_back(face_vertices[i]);
            triangles.push_back(face_vertices[i + 1]);
        }
    }

    geo_mesh.facets.assign_triangle_mesh(3, vertices, triangles, true);
}

Surface_mesh geogram_mesh_to_surface_mesh(const GEO::Mesh& geo_mesh) {
    Surface_mesh sm;

    std::vector<Surface_mesh::Vertex_index> vertex_map;
    vertex_map.reserve(geo_mesh.vertices.nb());

    for (GEO::index_t v = 0; v < geo_mesh.vertices.nb(); ++v) {
        const double* pt = geo_mesh.vertices.point_ptr(v);
        vertex_map.push_back(sm.add_vertex(K::Point_3(pt[0], pt[1], pt[2])));
    }

    for (GEO::index_t f = 0; f < geo_mesh.facets.nb(); ++f) {
        const GEO::index_t face_size = geo_mesh.facets.nb_vertices(f);
        if (face_size < 3) {
            continue;
        }
        std::vector<Surface_mesh::Vertex_index> face_vertices;
        face_vertices.reserve(static_cast<size_t>(face_size));
        bool valid = true;
        for (GEO::index_t lv = 0; lv < face_size; ++lv) {
            GEO::index_t gv = geo_mesh.facets.vertex(f, lv);
            if (gv >= vertex_map.size()) {
                valid = false;
                break;
            }
            face_vertices.push_back(vertex_map[gv]);
        }
        if (valid) {
            sm.add_face(face_vertices);
        }
    }

    return sm;
}

Surface_mesh geogram_boolean_difference(
    const Surface_mesh& mesh_a,
    const std::vector<Surface_mesh>& meshes_b,
    BooleanOpTiming* timing) {
    ensure_geogram_initialized();

    GEO::Mesh geo_current;
    auto t_conversion_start = Clock::now();
    surface_mesh_to_geogram_mesh(mesh_a, geo_current);
    auto t_conversion_end = Clock::now();
    if (timing != nullptr) {
        timing->conversion_ms += t_conversion_end - t_conversion_start;
    }
    for (const auto& mesh_b : meshes_b) {
        GEO::Mesh geo_b;
        t_conversion_start = Clock::now();
        surface_mesh_to_geogram_mesh(mesh_b, geo_b);
        t_conversion_end = Clock::now();
        if (timing != nullptr) {
            timing->conversion_ms += t_conversion_end - t_conversion_start;
        }
        GEO::Mesh geo_result;
        auto t_boolean_start = Clock::now();
        GEO::mesh_difference(geo_result, geo_current, geo_b, GEO::MESH_BOOL_OPS_DEFAULT);
        auto t_boolean_end = Clock::now();
        if (timing != nullptr) {
            timing->boolean_ms += t_boolean_end - t_boolean_start;
        }
        t_conversion_start = Clock::now();
        geo_current.copy(geo_result);
        t_conversion_end = Clock::now();
        if (timing != nullptr) {
            timing->conversion_ms += t_conversion_end - t_conversion_start;
        }
    }

    t_conversion_start = Clock::now();
    Surface_mesh result = geogram_mesh_to_surface_mesh(geo_current);
    t_conversion_end = Clock::now();
    if (timing != nullptr) {
        timing->conversion_ms += t_conversion_end - t_conversion_start;
    }
    return result;
}
