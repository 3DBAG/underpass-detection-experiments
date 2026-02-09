// Copyright (c) 2018-2024 TU Delft 3D geoinformation group, Ravi Peters (3DGI),
// and Balazs Dukai (3DGI)

// Adapted for standalone use with CGAL Surface_mesh.

#include "PolygonExtruder.h"
#include "RerunVisualization.h"

#include <CGAL/Constrained_Delaunay_triangulation_2.h>
#include <CGAL/Exact_predicates_inexact_constructions_kernel.h>
#include <CGAL/Triangulation_face_base_with_info_2.h>

#include <algorithm>
#include <format>
#include <iostream>
#include <list>
#include <map>

namespace extrusion {

// Internal kernel for CDT (needs exact predicates)
using CDT_K = CGAL::Exact_predicates_inexact_constructions_kernel;
using Point_2 = CDT_K::Point_2;

struct FaceInfo {
  int nesting_level = -1;
  bool in_domain() const { return nesting_level % 2 == 1; }
};

using VertexBase = CGAL::Triangulation_vertex_base_2<CDT_K>;
using FaceBase = CGAL::Constrained_triangulation_face_base_2<CDT_K>;
using FaceBaseWithInfo = CGAL::Triangulation_face_base_with_info_2<FaceInfo, CDT_K, FaceBase>;
using TDS = CGAL::Triangulation_data_structure_2<VertexBase, FaceBaseWithInfo>;
using CDT = CGAL::Constrained_Delaunay_triangulation_2<CDT_K, TDS, CGAL::Exact_predicates_tag>;

// Global rerun recording stream for visualization (set externally)
#ifdef ENABLE_RERUN
static const rerun::RecordingStream* g_rec = nullptr;
static int g_polygon_index = 0;

void set_rerun_recording_stream(const rerun::RecordingStream* rec) {
  g_rec = rec;
  g_polygon_index = 0;
}
#endif

// Mark domains using flood fill from infinite face
static void mark_domains(CDT& ct, CDT::Face_handle start, int index,
                         std::list<CDT::Edge>& border) {
  if (start->info().nesting_level != -1) {
    return;
  }
  std::list<CDT::Face_handle> queue;
  queue.push_back(start);
  while (!queue.empty()) {
    CDT::Face_handle fh = queue.front();
    queue.pop_front();
    if (fh->info().nesting_level == -1) {
      fh->info().nesting_level = index;
      for (int i = 0; i < 3; i++) {
        CDT::Edge e(fh, i);
        CDT::Face_handle n = fh->neighbor(i);
        if (n->info().nesting_level == -1) {
          if (ct.is_constrained(e))
            border.push_back(e);
          else
            queue.push_back(n);
        }
      }
    }
  }
}

// Mark triangles that are inside the polygon (odd nesting level)
static void mark_domains(CDT& cdt) {
  std::list<CDT::Edge> border;
  mark_domains(cdt, cdt.infinite_face(), 0, border);
  while (!border.empty()) {
    CDT::Edge e = border.front();
    border.pop_front();
    CDT::Face_handle n = e.first->neighbor(e.second);
    if (n->info().nesting_level == -1) {
      mark_domains(cdt, n, e.first->info().nesting_level + 1, border);
    }
  }
}

// Insert a ring as constrained edges into the CDT.
// Returns vertex handles in the same order as the input ring.
// The ring is assumed to be open (no repeated closing point).
static std::vector<CDT::Vertex_handle> insert_ring(
    const std::vector<std::array<double, 3>>& ring, CDT& cdt) {
  std::vector<CDT::Vertex_handle> handles;
  if (ring.size() < 3) return handles;

  handles.reserve(ring.size());

  // Insert all vertices
  for (const auto& pt : ring) {
    handles.push_back(cdt.insert(Point_2(pt[0], pt[1])));
  }

  // Insert constrained edges forming a closed ring
  for (size_t i = 0; i < handles.size(); ++i) {
    size_t j = (i + 1) % handles.size();
    cdt.insert_constraint(handles[i], handles[j]);
  }

  return handles;
}

// Triangulate a polygon with holes using CDT.
// Populates ring_handles: first element is the exterior ring, followed by one
// element per interior ring (hole). Handles refer to vertices in cdt.
static void triangulate_polygon(const ogr::LinearRing& ring, CDT& cdt,
                                std::vector<std::vector<CDT::Vertex_handle>>& ring_handles) {
  // Insert exterior ring
  ring_handles.push_back(insert_ring(ring, cdt));

  // Insert interior rings (holes)
  for (const auto& hole : ring.interior_rings()) {
    ring_handles.push_back(insert_ring(hole, cdt));
  }

  if (cdt.number_of_faces() == 0) return;

  mark_domains(cdt);
}

Surface_mesh extrude_polygon(const ogr::LinearRing& ring, double floor_height,
                             double roof_height) {
  Surface_mesh mesh;

  if (ring.size() < 3) {
    return mesh;
  }

  // Triangulate the polygon with holes
  CDT cdt;
  std::vector<std::vector<CDT::Vertex_handle>> ring_handles;
  triangulate_polygon(ring, cdt, ring_handles);

#ifdef ENABLE_RERUN
  if (g_rec) {
    viz::visualize_cdt(*g_rec, std::format("triangulation/{}", g_polygon_index++), cdt, floor_height);
  }
#endif

  // Map from CDT vertices to mesh vertices (floor and roof)
  std::map<CDT::Vertex_handle, Surface_mesh::Vertex_index> floor_vertex_map;
  std::map<CDT::Vertex_handle, Surface_mesh::Vertex_index> roof_vertex_map;

  // Add vertices for all CDT vertices (both floor and roof levels)
  for (auto vit = cdt.finite_vertices_begin(); vit != cdt.finite_vertices_end(); ++vit) {
    Point_2 p = vit->point();
    floor_vertex_map[vit] = mesh.add_vertex(Point_3(p.x(), p.y(), floor_height));
    roof_vertex_map[vit] = mesh.add_vertex(Point_3(p.x(), p.y(), roof_height));
  }

  std::cerr << std::format("input polygon: exterior ring size={}, interior rings={}\n",
      ring.size(), ring.interior_rings().size());
  for (size_t i = 0; i < ring.interior_rings().size(); ++i) {
    std::cerr << std::format("  hole[{}] size={}\n", i, ring.interior_rings()[i].size());
  }

  std::cerr << std::format("CDT vertices: {}, floor_map: {}, roof_map: {}, ring_handles[0]: {}\n",
      cdt.number_of_vertices(), floor_vertex_map.size(), roof_vertex_map.size(), ring_handles[0].size());
  for (size_t ri = 1; ri < ring_handles.size(); ++ri) {
    std::cerr << std::format("  ring_handles[{}]: {}\n", ri, ring_handles[ri].size());
  }

  // Add triangulated floor and roof faces
  for (auto fit = cdt.finite_faces_begin(); fit != cdt.finite_faces_end(); ++fit) {
    if (!fit->info().in_domain()) continue;

    CDT::Vertex_handle v0 = fit->vertex(0);
    CDT::Vertex_handle v1 = fit->vertex(1);
    CDT::Vertex_handle v2 = fit->vertex(2);

    // Roof face: CCW winding (normal points down)
    mesh.add_face(roof_vertex_map[v0], roof_vertex_map[v1], roof_vertex_map[v2]);

    // Floor face: CW winding (normal points up) - reverse order
    mesh.add_face(floor_vertex_map[v2], floor_vertex_map[v1], floor_vertex_map[v0]);
  }

  // Add wall faces for exterior ring
  const size_t n = ring_handles[0].size();
  // Wall faces for exterior ring (two triangles per wall segment)
  // Exterior ring is CCW, walls face outward
  // we iterate over the cdt vertices that form the exterior ring in the order of the original ring
  // then we look up the corresponding vertices in the floor and roof maps
  // Then we add two triangles (each in CCW orientation) per wall segment:
  // a     b
  // o-----o  roof
  // |    /|
  // |   / |
  // |  /  |
  // | /   |
  // |/    |
  // o-----o  floor
  // a     b
  for (size_t i = 0; i < n; ++i) {
    size_t j = (i + 1) % n;
    auto& v_floor_a = floor_vertex_map.at(ring_handles[0][i]);
    auto& v_floor_b = floor_vertex_map.at(ring_handles[0][j]);
    auto& v_roof_a = roof_vertex_map.at(ring_handles[0][i]);
    auto& v_roof_b = roof_vertex_map.at(ring_handles[0][j]);
    mesh.add_face(v_floor_a, v_floor_b, v_roof_b);
    mesh.add_face(v_floor_a, v_roof_b, v_roof_a);
  }

  // Add wall faces for interior rings (holes)
  for (size_t ri = 1; ri < ring_handles.size(); ++ri) {
    const auto& hole_handles = ring_handles[ri];
    size_t hn = hole_handles.size();

    // Hole rings are CW, walls should face into the hole (outward from solid)
    for (size_t i = 0; i < hn; ++i) {
      size_t j = (i + 1) % hn;
      auto& v_floor_a = floor_vertex_map[hole_handles[i]];
      auto& v_floor_b = floor_vertex_map[hole_handles[j]];
      auto& v_roof_a = roof_vertex_map[hole_handles[i]];
      auto& v_roof_b = roof_vertex_map[hole_handles[j]];
      mesh.add_face(v_floor_a, v_floor_b, v_roof_b);
      mesh.add_face(v_roof_a, v_floor_a, v_roof_b);
    }
  }

  return mesh;
}

}  // namespace extrusion
