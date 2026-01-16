#include <iostream>
#include <manifold/manifold.h>
#include <manifold/meshIO.h>
#include <format>
#include <rerun.hpp>

// Custom collection adapter for Manifold vertex properties to Rerun Position3D
namespace rerun {
  template <>
  struct CollectionAdapter<Position3D, manifold::MeshGL> {
    Collection<Position3D> operator()(const manifold::MeshGL& mesh) {
      // Reinterpret the interleaved vertex properties as Position3D
      // vertProperties has stride numProp (default 3), first 3 values are x,y,z
      return Collection<Position3D>::borrow(
          reinterpret_cast<const Position3D*>(mesh.vertProperties.data()),
          mesh.NumVert()
      );
    }
  };

  // Custom collection adapter for Manifold triangle indices to Rerun TriangleIndices
  template <>
  struct CollectionAdapter<TriangleIndices, manifold::MeshGL> {
    Collection<TriangleIndices> operator()(const manifold::MeshGL& mesh) {
      // Reinterpret the flat triangle indices as TriangleIndices
      // triVerts has 3 indices per triangle
      return Collection<TriangleIndices>::borrow(
          reinterpret_cast<const TriangleIndices*>(mesh.triVerts.data()),
          mesh.NumTri()
      );
    }
  };
}

int main() {
    const auto rec = rerun::RecordingStream("test_3d_intersection");
    rec.spawn().exit_on_failure();

    auto house_ = manifold::ImportMesh("sample_data/house.ply");
    auto underpass_ = manifold::ImportMesh("sample_data/underpass.ply");
    std::cout << std::format("Number of triangles: {}", house_.NumTri()) << std::endl;
    std::cout << std::format("Number of vertices: {}", house_.NumVert()) << std::endl;

    auto house = manifold::Manifold(house_);
    auto underpass = manifold::Manifold(underpass_);

    // Visualize house mesh
    auto houseMeshGL = house.GetMeshGL();
    rec.log(
        "house",
        rerun::Mesh3D(houseMeshGL)
            .with_triangle_indices(houseMeshGL)
            .with_albedo_factor(rerun::Rgba32(200, 100, 100, 255))
    );

    // Visualize underpass mesh
    auto underpassMeshGL = underpass.GetMeshGL();
    rec.log(
        "underpass",
        rerun::Mesh3D(underpassMeshGL)
            .with_triangle_indices(underpassMeshGL)
            .with_albedo_factor(rerun::Rgba32(100, 100, 200, 255))
    );

    auto house_with_underpass = house - underpass;
    // Visualize result mesh
    auto resultMeshGL = house_with_underpass.GetMeshGL();
    rec.log(
        "result",
        rerun::Mesh3D(resultMeshGL)
            .with_triangle_indices(resultMeshGL)
            .with_albedo_factor(rerun::Rgba32(100, 200, 100, 255))
    );

    manifold::ExportMesh("house_with_underpass.ply", house_with_underpass.GetMeshGL(), {});

    return 0;
}
