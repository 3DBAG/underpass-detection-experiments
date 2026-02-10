// Rerun visualization utilities

#include "RerunVisualization.h"

#ifdef ENABLE_RERUN

namespace viz {

std::vector<rerun::Position3D> meshgl_positions(const manifold::MeshGL& mesh) {
    std::vector<rerun::Position3D> positions;
    positions.reserve(mesh.NumVert());
    for (size_t i = 0; i < mesh.NumVert(); ++i) {
        size_t offset = i * mesh.numProp;
        positions.push_back(rerun::Position3D(
            mesh.vertProperties[offset],
            mesh.vertProperties[offset + 1],
            mesh.vertProperties[offset + 2]
        ));
    }
    return positions;
}

std::vector<rerun::TriangleIndices> meshgl_triangles(const manifold::MeshGL& mesh) {
    std::vector<rerun::TriangleIndices> triangles;
    triangles.reserve(mesh.NumTri());
    for (size_t i = 0; i < mesh.NumTri(); ++i) {
        triangles.push_back(rerun::TriangleIndices(
            mesh.triVerts[i * 3],
            mesh.triVerts[i * 3 + 1],
            mesh.triVerts[i * 3 + 2]
        ));
    }
    return triangles;
}

std::vector<rerun::Vector3D> meshgl_normals(const manifold::MeshGL& mesh) {
    std::vector<rerun::Vector3D> normals;
    if (mesh.numProp < 6) {
        return normals;  // No normals stored
    }
    normals.reserve(mesh.NumVert());
    for (size_t i = 0; i < mesh.NumVert(); ++i) {
        size_t offset = i * mesh.numProp;
        normals.push_back(rerun::Vector3D(
            mesh.vertProperties[offset + 3],
            mesh.vertProperties[offset + 4],
            mesh.vertProperties[offset + 5]
        ));
    }
    return normals;
}

void log_meshgl(const rerun::RecordingStream& rec, const std::string& entity_path,
                const manifold::MeshGL& mesh, rerun::Rgba32 color) {
    if (mesh.NumTri() == 0) return;
    
    auto normals = meshgl_normals(mesh);
    if (!normals.empty()) {
        rec.log(entity_path,
            rerun::Mesh3D(meshgl_positions(mesh))
                .with_triangle_indices(meshgl_triangles(mesh))
                .with_vertex_normals(normals)
                .with_albedo_factor(color));
    } else {
        rec.log(entity_path,
            rerun::Mesh3D(meshgl_positions(mesh))
                .with_triangle_indices(meshgl_triangles(mesh))
                .with_albedo_factor(color));
    }
}

}  // namespace viz

#endif  // ENABLE_RERUN
