#include "BooleanOps.h"

#include <iostream>

#include <CGAL/Exact_predicates_exact_constructions_kernel.h>
#include <CGAL/Nef_polyhedron_3.h>
#include <CGAL/Polyhedron_3.h>
#include <CGAL/boost/graph/convert_nef_polyhedron_to_polygon_mesh.h>
#include <CGAL/Polygon_mesh_processing/polygon_soup_to_polygon_mesh.h>
#include <CGAL/Polygon_mesh_processing/corefinement.h>
#include <geogram/basic/common.h>
#include <geogram/mesh/mesh.h>
#include <geogram/mesh/mesh_surface_intersection.h>

using Exact_kernel = CGAL::Exact_predicates_exact_constructions_kernel;
using Nef_polyhedron = CGAL::Nef_polyhedron_3<Exact_kernel>;
using Exact_surface_mesh = CGAL::Surface_mesh<Exact_kernel::Point_3>;

static Exact_surface_mesh surface_mesh_to_exact(const Surface_mesh& sm) {
    Exact_surface_mesh esm;

    std::vector<Exact_surface_mesh::Vertex_index> vertex_map;
    vertex_map.reserve(sm.number_of_vertices());

    for (auto v : sm.vertices()) {
        const auto& pt = sm.point(v);
        Exact_kernel::Point_3 exact_pt(pt.x(), pt.y(), pt.z());
        vertex_map.push_back(esm.add_vertex(exact_pt));
    }

    for (auto f : sm.faces()) {
        std::vector<Exact_surface_mesh::Vertex_index> face_vertices;
        for (auto v : sm.vertices_around_face(sm.halfedge(f))) {
            face_vertices.push_back(vertex_map[v]);
        }
        esm.add_face(face_vertices);
    }

    return esm;
}

static Surface_mesh exact_to_surface_mesh(const Exact_surface_mesh& esm) {
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

static void ensure_geogram_initialized() {
    static const bool initialized = []() {
        GEO::initialize(GEO::GEOGRAM_INSTALL_NONE);
        return true;
    }();
    (void)initialized;
}

static void surface_mesh_to_geogram_mesh(const Surface_mesh& sm, GEO::Mesh& geo_mesh) {
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

static Surface_mesh geogram_mesh_to_surface_mesh(const GEO::Mesh& geo_mesh) {
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

Surface_mesh nef_boolean_difference(const Surface_mesh& mesh_a, const Surface_mesh& mesh_b) {
    auto exact_a = surface_mesh_to_exact(mesh_a);
    auto exact_b = surface_mesh_to_exact(mesh_b);

    Nef_polyhedron nef_a(exact_a);
    Nef_polyhedron nef_b(exact_b);

    Nef_polyhedron nef_result = nef_b - nef_a;

    Exact_surface_mesh exact_result;
    CGAL::convert_nef_polyhedron_to_polygon_mesh(nef_result, exact_result);

    return exact_to_surface_mesh(exact_result);
}

Surface_mesh nef_boolean_difference(const Surface_mesh& mesh_a, const std::vector<Surface_mesh>& meshes_b) {
    auto exact_a = surface_mesh_to_exact(mesh_a);
    Nef_polyhedron nef_result(exact_a);

    for (const auto& mesh_b : meshes_b) {
        auto exact_b = surface_mesh_to_exact(mesh_b);
        Nef_polyhedron nef_b(exact_b);
        nef_result = nef_result - nef_b;
    }

    Exact_surface_mesh exact_result;
    CGAL::convert_nef_polyhedron_to_polygon_mesh(nef_result, exact_result);

    return exact_to_surface_mesh(exact_result);
}

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

Surface_mesh geogram_boolean_difference(const Surface_mesh& mesh_a, const Surface_mesh& mesh_b) {
    ensure_geogram_initialized();

    GEO::Mesh geo_a;
    GEO::Mesh geo_b;
    surface_mesh_to_geogram_mesh(mesh_a, geo_a);
    surface_mesh_to_geogram_mesh(mesh_b, geo_b);
    GEO::Mesh geo_result;
    GEO::mesh_difference(geo_result, geo_a, geo_b, GEO::MESH_BOOL_OPS_DEFAULT);

    return geogram_mesh_to_surface_mesh(geo_result);
}

Surface_mesh geogram_boolean_difference(const Surface_mesh& mesh_a, const std::vector<Surface_mesh>& meshes_b) {
    ensure_geogram_initialized();

    GEO::Mesh geo_current;
    surface_mesh_to_geogram_mesh(mesh_a, geo_current);
    for (const auto& mesh_b : meshes_b) {
        GEO::Mesh geo_b;
        surface_mesh_to_geogram_mesh(mesh_b, geo_b);
        GEO::Mesh geo_result;
        GEO::mesh_difference(geo_result, geo_current, geo_b, GEO::MESH_BOOL_OPS_DEFAULT);
        geo_current.copy(geo_result);
    }

    return geogram_mesh_to_surface_mesh(geo_current);
}
