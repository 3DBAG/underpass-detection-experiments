#ifndef POLYGONAL_OUTPUT_H
#define POLYGONAL_OUTPUT_H

#include <cstdint>
#include <vector>

#include "BooleanOps.h"
#include "ModelLoaders.h"

struct PolygonalOutput {
    std::vector<double> vertices_xyz_world;
    std::vector<uint32_t> surface_ring_counts;
    std::vector<uint32_t> ring_vertex_counts;
    std::vector<uint32_t> boundary_indices;
    std::vector<uint8_t> surface_semantic_types;
};

bool build_polygonal_output_from_cgal_mesh(
    const Surface_mesh& result_mesh,
    const LoadedSolidMesh& source_mesh,
    double house_min_z,
    double underpass_z,
    double offset_x,
    double offset_y,
    double offset_z,
    PolygonalOutput& out);

#endif // POLYGONAL_OUTPUT_H
