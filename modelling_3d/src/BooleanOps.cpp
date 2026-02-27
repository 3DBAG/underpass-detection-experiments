#include "BooleanOps.h"

#include <iostream>

#include <CGAL/Exact_predicates_exact_constructions_kernel.h>
#include <CGAL/Nef_polyhedron_3.h>
#include <CGAL/Polyhedron_3.h>
#include <CGAL/boost/graph/convert_nef_polyhedron_to_polygon_mesh.h>
#include <CGAL/Polygon_mesh_processing/polygon_soup_to_polygon_mesh.h>
#include <CGAL/Polygon_mesh_processing/corefinement.h>

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
