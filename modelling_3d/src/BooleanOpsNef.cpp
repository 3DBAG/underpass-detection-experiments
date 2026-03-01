#include "BooleanOps.h"
#include "MeshConversion.h"

#include <chrono>

#include <CGAL/Nef_polyhedron_3.h>
#include <CGAL/boost/graph/convert_nef_polyhedron_to_polygon_mesh.h>

using Nef_polyhedron = CGAL::Nef_polyhedron_3<Exact_kernel>;
using Clock = std::chrono::steady_clock;

Surface_mesh nef_boolean_difference(
    const Surface_mesh& mesh_a,
    const Surface_mesh& mesh_b,
    BooleanOpTiming* timing) {
    auto t_conversion_start = Clock::now();
    auto exact_a = surface_mesh_to_exact(mesh_a);
    auto exact_b = surface_mesh_to_exact(mesh_b);

    Nef_polyhedron nef_a(exact_a);
    Nef_polyhedron nef_b(exact_b);
    auto t_conversion_end = Clock::now();
    if (timing != nullptr) {
        timing->conversion_ms += t_conversion_end - t_conversion_start;
    }

    auto t_boolean_start = Clock::now();
    Nef_polyhedron nef_result = nef_b - nef_a;
    auto t_boolean_end = Clock::now();
    if (timing != nullptr) {
        timing->boolean_ms += t_boolean_end - t_boolean_start;
    }

    t_conversion_start = Clock::now();
    Exact_surface_mesh exact_result;
    CGAL::convert_nef_polyhedron_to_polygon_mesh(nef_result, exact_result);
    Surface_mesh result = exact_to_surface_mesh(exact_result);
    t_conversion_end = Clock::now();
    if (timing != nullptr) {
        timing->conversion_ms += t_conversion_end - t_conversion_start;
    }
    return result;
}

Surface_mesh nef_boolean_difference(
    const Surface_mesh& mesh_a,
    const std::vector<Surface_mesh>& meshes_b,
    BooleanOpTiming* timing) {
    auto t_conversion_start = Clock::now();
    auto exact_a = surface_mesh_to_exact(mesh_a);
    Nef_polyhedron nef_result(exact_a);
    auto t_conversion_end = Clock::now();
    if (timing != nullptr) {
        timing->conversion_ms += t_conversion_end - t_conversion_start;
    }

    for (const auto& mesh_b : meshes_b) {
        t_conversion_start = Clock::now();
        auto exact_b = surface_mesh_to_exact(mesh_b);
        Nef_polyhedron nef_b(exact_b);
        t_conversion_end = Clock::now();
        if (timing != nullptr) {
            timing->conversion_ms += t_conversion_end - t_conversion_start;
        }

        auto t_boolean_start = Clock::now();
        nef_result = nef_result - nef_b;
        auto t_boolean_end = Clock::now();
        if (timing != nullptr) {
            timing->boolean_ms += t_boolean_end - t_boolean_start;
        }
    }

    t_conversion_start = Clock::now();
    Exact_surface_mesh exact_result;
    CGAL::convert_nef_polyhedron_to_polygon_mesh(nef_result, exact_result);
    Surface_mesh result = exact_to_surface_mesh(exact_result);
    t_conversion_end = Clock::now();
    if (timing != nullptr) {
        timing->conversion_ms += t_conversion_end - t_conversion_start;
    }
    return result;
}
