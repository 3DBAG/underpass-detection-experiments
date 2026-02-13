// Rerun visualization utilities

#pragma once

#ifdef ENABLE_RERUN

#include <rerun.hpp>
#include <manifold/manifold.h>

#include <string>
#include <vector>

namespace viz {

// Extract positions from MeshGL (handles variable numProp stride)
std::vector<rerun::Position3D> meshgl_positions(const manifold::MeshGL& mesh);

// Extract triangle indices from MeshGL
std::vector<rerun::TriangleIndices> meshgl_triangles(const manifold::MeshGL& mesh);

// Extract vertex normals from MeshGL (assumes numProp >= 6 with normals at indices 3,4,5)
std::vector<rerun::Vector3D> meshgl_normals(const manifold::MeshGL& mesh);

// Log a MeshGL to rerun with optional color
void log_meshgl(const rerun::RecordingStream& rec, const std::string& entity_path,
                const manifold::MeshGL& mesh, rerun::Rgba32 color);

// Visualize a CDT triangulation.
// Triangles inside the domain are colored green, outside are colored red.
// The triangulation is displayed at the given z height.
// CDT must have FaceInfo with in_domain() method.
template<typename CDT>
void visualize_cdt(const rerun::RecordingStream& rec,
                   const std::string& entity_path,
                   const CDT& cdt,
                   double z_height) {
    // Collect triangles for inside and outside domains separately
    std::vector<rerun::Position3D> inside_positions;
    std::vector<rerun::TriangleIndices> inside_triangles;
    std::vector<rerun::Position3D> outside_positions;
    std::vector<rerun::TriangleIndices> outside_triangles;

    uint32_t inside_idx = 0;
    uint32_t outside_idx = 0;

    for (auto fit = cdt.finite_faces_begin(); fit != cdt.finite_faces_end(); ++fit) {
        auto v0 = fit->vertex(0)->point();
        auto v1 = fit->vertex(1)->point();
        auto v2 = fit->vertex(2)->point();

        if (fit->info().in_domain()) {
            inside_positions.push_back(rerun::Position3D(v0.x(), v0.y(), z_height));
            inside_positions.push_back(rerun::Position3D(v1.x(), v1.y(), z_height));
            inside_positions.push_back(rerun::Position3D(v2.x(), v2.y(), z_height));
            inside_triangles.push_back(rerun::TriangleIndices(inside_idx, inside_idx + 1, inside_idx + 2));
            inside_idx += 3;
        } else {
            outside_positions.push_back(rerun::Position3D(v0.x(), v0.y(), z_height));
            outside_positions.push_back(rerun::Position3D(v1.x(), v1.y(), z_height));
            outside_positions.push_back(rerun::Position3D(v2.x(), v2.y(), z_height));
            outside_triangles.push_back(rerun::TriangleIndices(outside_idx, outside_idx + 1, outside_idx + 2));
            outside_idx += 3;
        }
    }

    // Log inside triangles (green)
    if (!inside_triangles.empty()) {
        rec.log(
            entity_path + "/inside",
            rerun::Mesh3D(inside_positions)
                .with_triangle_indices(inside_triangles)
                .with_albedo_factor(rerun::Rgba32(100, 200, 100, 255))
        );
    }

    // Log outside triangles (red)
    if (!outside_triangles.empty()) {
        rec.log(
            entity_path + "/outside",
            rerun::Mesh3D(outside_positions)
                .with_triangle_indices(outside_triangles)
                .with_albedo_factor(rerun::Rgba32(200, 100, 100, 255))
        );
    }
}

}  // namespace viz

#endif  // ENABLE_RERUN
