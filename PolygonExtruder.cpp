// Copyright (c) 2018-2024 TU Delft 3D geoinformation group, Ravi Peters (3DGI),
// and Balazs Dukai (3DGI)

// Adapted for standalone use with CGAL Surface_mesh.

#include "PolygonExtruder.h"

#include <algorithm>
#include <iostream>

namespace extrusion {

Surface_mesh extrude_polygon(const ogr::LinearRing& ring, double floor_height,
                             double roof_height) {
  Surface_mesh mesh;

  if (ring.size() < 3) {
    return mesh;  // Need at least 3 points
  }

  const size_t n = ring.size();
  const size_t num_holes = ring.interior_rings().size();

  // Count total vertices needed for holes
  size_t total_hole_verts = 0;
  for (const auto& hole : ring.interior_rings()) {
    total_hole_verts += hole.size();
  }

  // Add floor and roof vertices for exterior ring
  // Floor vertices: indices [0, n)
  // Roof vertices: indices [n, 2n)
  std::vector<Surface_mesh::Vertex_index> floor_verts;
  std::vector<Surface_mesh::Vertex_index> roof_verts;
  floor_verts.reserve(n);
  roof_verts.reserve(n);

  for (size_t i = 0; i < n; ++i) {
    const auto& pt = ring[i];
    floor_verts.push_back(mesh.add_vertex(Point_3(pt[0], pt[1], floor_height)));
    roof_verts.push_back(mesh.add_vertex(Point_3(pt[0], pt[1], roof_height)));
  }

  // Add vertices for holes
  std::vector<std::vector<Surface_mesh::Vertex_index>> hole_floor_verts;
  std::vector<std::vector<Surface_mesh::Vertex_index>> hole_roof_verts;
  hole_floor_verts.reserve(num_holes);
  hole_roof_verts.reserve(num_holes);

  for (const auto& hole : ring.interior_rings()) {
    std::vector<Surface_mesh::Vertex_index> hf, hr;
    hf.reserve(hole.size());
    hr.reserve(hole.size());
    for (const auto& pt : hole) {
      hf.push_back(mesh.add_vertex(Point_3(pt[0], pt[1], floor_height)));
      hr.push_back(mesh.add_vertex(Point_3(pt[0], pt[1], roof_height)));
    }
    hole_floor_verts.push_back(std::move(hf));
    hole_roof_verts.push_back(std::move(hr));
  }

  // For outward-facing normals on all faces:
  // - Roof: CW (reversed) -> normal points up when viewed from outside
  // - Floor: CCW (as-is) -> normal points down when viewed from outside
  // - Walls: can then have outward normals

  // Add roof face (reversed to CW for outward normal pointing up)
  std::vector<Surface_mesh::Vertex_index> roof_reversed(roof_verts.rbegin(),
                                                        roof_verts.rend());
  auto roof_face = mesh.add_face(roof_reversed);
  // std::cerr << "Roof face: " << (roof_face.is_valid() ? "OK" : "FAILED") << std::endl;

  // Add wall faces for exterior ring
  // Roof edge (reversed) goes j->i. Wall must use that edge in reverse: i->j
  // Wall winds: roof[i] -> roof[j] -> floor[j] -> floor[i] for outward normal
  for (size_t i = 0; i < n; ++i) {
    size_t j = (i + 1) % n;
    auto wall_face = mesh.add_face(roof_verts[i], roof_verts[j], floor_verts[j], floor_verts[i]);
    // std::cerr << "Wall face " << i << ": " << (wall_face.is_valid() ? "OK" : "FAILED") << std::endl;
  }

  // Add wall faces for holes
  // Holes are CW (from OGR reader), walls should face into the hole (outward from solid)
  for (size_t h = 0; h < num_holes; ++h) {
    const auto& hf = hole_floor_verts[h];
    const auto& hr = hole_roof_verts[h];
    size_t hn = hf.size();
    for (size_t i = 0; i < hn; ++i) {
      size_t j = (i + 1) % hn;
      auto hole_wall_face = mesh.add_face(hf[j], hr[j], hr[i], hf[i]);
      // std::cerr << "Hole " << h << " wall " << i << ": " << (hole_wall_face.is_valid() ? "OK" : "FAILED") << std::endl;
    }
  }

  // Add floor face (CCW as-is, normal points down)
  auto floor_face = mesh.add_face(floor_verts);
  // std::cerr << "Floor face: " << (floor_face.is_valid() ? "OK" : "FAILED") << std::endl;

  return mesh;
}

}  // namespace extrusion
