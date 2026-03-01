#include "BooleanOps.h"
#include "MeshConversion.h"

#include <chrono>
#include <iostream>

#include <CGAL/Polygon_mesh_processing/corefinement.h>

using Clock = std::chrono::steady_clock;

Surface_mesh corefine_boolean_difference(
    const Surface_mesh& mesh_a,
    const Surface_mesh& mesh_b,
    BooleanOpTiming* timing) {
    auto t_conversion_start = Clock::now();
    auto exact_a = surface_mesh_to_exact(mesh_a);
    auto exact_b = surface_mesh_to_exact(mesh_b);
    auto t_conversion_end = Clock::now();
    if (timing != nullptr) {
        timing->conversion_ms += t_conversion_end - t_conversion_start;
    }

    Exact_surface_mesh exact_result;
    auto t_boolean_start = Clock::now();
    bool success = CGAL::Polygon_mesh_processing::corefine_and_compute_difference(
        exact_a, exact_b, exact_result);
    auto t_boolean_end = Clock::now();
    if (timing != nullptr) {
        timing->boolean_ms += t_boolean_end - t_boolean_start;
    }

    if (!success) {
        std::cerr << "Warning: corefine_and_compute_difference failed" << std::endl;
    }

    t_conversion_start = Clock::now();
    Surface_mesh result = exact_to_surface_mesh(exact_result);
    t_conversion_end = Clock::now();
    if (timing != nullptr) {
        timing->conversion_ms += t_conversion_end - t_conversion_start;
    }
    return result;
}

Surface_mesh corefine_boolean_difference(
    const Surface_mesh& mesh_a,
    const std::vector<Surface_mesh>& meshes_b,
    BooleanOpTiming* timing) {
    auto t_conversion_start = Clock::now();
    auto exact_a = surface_mesh_to_exact(mesh_a);
    auto t_conversion_end = Clock::now();
    if (timing != nullptr) {
        timing->conversion_ms += t_conversion_end - t_conversion_start;
    }

    for (const auto& mesh_b : meshes_b) {
        t_conversion_start = Clock::now();
        auto exact_b = surface_mesh_to_exact(mesh_b);
        t_conversion_end = Clock::now();
        if (timing != nullptr) {
            timing->conversion_ms += t_conversion_end - t_conversion_start;
        }

        Exact_surface_mesh exact_result;
        auto t_boolean_start = Clock::now();
        bool success = CGAL::Polygon_mesh_processing::corefine_and_compute_difference(
            exact_a, exact_b, exact_result);
        auto t_boolean_end = Clock::now();
        if (timing != nullptr) {
            timing->boolean_ms += t_boolean_end - t_boolean_start;
        }

        if (!success) {
            std::cerr << "Warning: corefine_and_compute_difference failed" << std::endl;
        }
        exact_a = std::move(exact_result);
    }

    t_conversion_start = Clock::now();
    Surface_mesh result = exact_to_surface_mesh(exact_a);
    t_conversion_end = Clock::now();
    if (timing != nullptr) {
        timing->conversion_ms += t_conversion_end - t_conversion_start;
    }
    return result;
}
