#include <iostream>
#include <format>

#include <manifold/manifold.h>
#include <manifold/meshIO.h>

#include <CGAL/Simple_cartesian.h>
#include <CGAL/Surface_mesh.h>

#ifdef ENABLE_RERUN
#include <rerun.hpp>
#endif

#include "zityjson.h"

#ifdef ENABLE_RERUN
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
#endif

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0] << " <cityjson_file>" << std::endl;
        return 1;
    }

    CityJSONHandle cj = cityjson_create();
    if (cityjson_load(cj, argv[1]) == 0) {
        size_t count = cityjson_object_count(cj);
        for (size_t i = 0; i < count; i++) {
            const char* name = cityjson_get_object_name(cj, i);
            size_t geom_count = cityjson_get_geometry_count(cj, i);
            for (size_t g = 0; g < geom_count; g++) {
                const double* verts = cityjson_get_vertices(cj, i, g);
                size_t vert_count = cityjson_get_vertex_count(cj, i, g);
                // std::cout << std::format("Object name: {}, geometry: {}", name, g) << std::endl;
            }
        }
        size_t start, end;
        uint8_t type;
        cityjson_get_face_info(cj, 0, 0, 0, &start, &end, &type);
        std::cout << std::format("Face info: start={}, end={}, type={}", start, end, type) << std::endl;
    }
    cityjson_destroy(cj);

#ifdef ENABLE_RERUN
    const auto rec = rerun::RecordingStream("test_3d_intersection");
    rec.spawn().exit_on_failure();
#endif

    auto house_ = manifold::ImportMesh("sample_data/house.ply");
    auto underpass_ = manifold::ImportMesh("sample_data/underpass.ply");
    std::cout << std::format("Number of triangles: {}", house_.NumTri()) << std::endl;
    std::cout << std::format("Number of vertices: {}", house_.NumVert()) << std::endl;

    auto house = manifold::Manifold(house_);
    auto underpass = manifold::Manifold(underpass_);

#ifdef ENABLE_RERUN
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
#endif

    auto house_with_underpass = house - underpass;

#ifdef ENABLE_RERUN
    // Visualize result mesh
    auto resultMeshGL = house_with_underpass.GetMeshGL();
    rec.log(
        "result",
        rerun::Mesh3D(resultMeshGL)
            .with_triangle_indices(resultMeshGL)
            .with_albedo_factor(rerun::Rgba32(100, 200, 100, 255))
    );
#endif

    manifold::ExportMesh("house_with_underpass.ply", house_with_underpass.GetMeshGL(), {});

    return 0;
}
