#include <iostream>
#include <manifold/manifold.h>
#include <manifold/meshIO.h>
#include <format>

int main() {
    auto house_ = manifold::ImportMesh("sample_data/house.ply");
    auto underpass_ = manifold::ImportMesh("sample_data/underpass.ply");
    std::cout << std::format("Number of triangles: {}", house_.NumTri()) << std::endl;
    std::cout << std::format("Number of vertices: {}", house_.NumVert()) << std::endl;

    auto house = manifold::Manifold(house_);
    auto underpass = manifold::Manifold(underpass_);
    auto house_with_underpass = house - underpass;

    manifold::ExportMesh("house_with_underpass.ply", house_with_underpass.GetMeshGL(), {});

    return 0;
}
