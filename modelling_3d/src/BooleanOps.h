#ifndef BOOLEAN_OPS_H
#define BOOLEAN_OPS_H

#include <chrono>
#include <vector>

#include <CGAL/Simple_cartesian.h>
#include <CGAL/Surface_mesh.h>

// Shared type aliases
using K = CGAL::Simple_cartesian<double>;
using Surface_mesh = CGAL::Surface_mesh<K::Point_3>;

enum class BooleanMethod {
    Manifold,
    CgalNef,
    CgalPMP,
    Geogram
};

struct BooleanOpTiming {
    std::chrono::duration<double, std::milli> conversion_ms{0.0};
    std::chrono::duration<double, std::milli> boolean_ms{0.0};
};

// Nef polyhedra boolean difference
Surface_mesh nef_boolean_difference(
    const Surface_mesh& mesh_a,
    const Surface_mesh& mesh_b,
    BooleanOpTiming* timing = nullptr);
Surface_mesh nef_boolean_difference(
    const Surface_mesh& mesh_a,
    const std::vector<Surface_mesh>& meshes_b,
    BooleanOpTiming* timing = nullptr);

// PMP corefinement boolean difference
Surface_mesh corefine_boolean_difference(
    const Surface_mesh& mesh_a,
    const Surface_mesh& mesh_b,
    BooleanOpTiming* timing = nullptr);
Surface_mesh corefine_boolean_difference(
    const Surface_mesh& mesh_a,
    const std::vector<Surface_mesh>& meshes_b,
    BooleanOpTiming* timing = nullptr);

// Geogram mesh boolean difference
Surface_mesh geogram_boolean_difference(
    const Surface_mesh& mesh_a,
    const Surface_mesh& mesh_b,
    BooleanOpTiming* timing = nullptr);
Surface_mesh geogram_boolean_difference(
    const Surface_mesh& mesh_a,
    const std::vector<Surface_mesh>& meshes_b,
    BooleanOpTiming* timing = nullptr);

#endif // BOOLEAN_OPS_H
