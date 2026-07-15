#ifndef POLYGONAL_OUTPUT_H
#define POLYGONAL_OUTPUT_H

#include <cstdint>
#include <cstddef>
#include <vector>

#include <manifold/manifold.h>

#include "BooleanOps.h"
#include "ModelLoaders.h"

struct UnderpassSurfaceSource {
    size_t polygon_feature_index = 0;
    const ogr::LinearRing* polygon = nullptr;
    double roof_z_local = 0.0;
};

struct PolygonalOutput {
    std::vector<double> vertices_xyz_world;
    std::vector<uint32_t> surface_ring_counts;
    std::vector<uint32_t> ring_vertex_counts;
    std::vector<uint32_t> boundary_indices;
    std::vector<uint8_t> surface_semantic_types;
    // Index into the UnderpassSurfaceSource vector, or -1 when the surface was
    // not produced by an underpass roof.
    std::vector<int32_t> surface_underpass_indices;
};

bool build_polygonal_output_from_cgal_mesh(
    const Surface_mesh& result_mesh,
    const LoadedSolidMesh& source_mesh,
    double house_min_z,
    double underpass_z,
    const std::vector<UnderpassSurfaceSource>& underpasses,
    double offset_x,
    double offset_y,
    double offset_z,
    PolygonalOutput& out);

bool build_polygonal_output_from_manifold_meshgl(
    const manifold::MeshGL& result_meshgl,
    const LoadedSolidMesh& source_mesh,
    double house_min_z,
    double underpass_z,
    const std::vector<UnderpassSurfaceSource>& underpasses,
    double offset_x,
    double offset_y,
    double offset_z,
    PolygonalOutput& out);

std::vector<int32_t> match_triangle_outer_ceiling_surfaces(
    const manifold::MeshGL& mesh,
    const std::vector<uint8_t>& semantic_types,
    const std::vector<UnderpassSurfaceSource>& underpasses,
    double offset_x,
    double offset_y);

#endif // POLYGONAL_OUTPUT_H
