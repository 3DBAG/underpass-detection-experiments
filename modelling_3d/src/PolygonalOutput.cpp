#include "PolygonalOutput.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <queue>
#include <unordered_map>
#include <utility>
#include <vector>

namespace {

constexpr uint8_t kRoofSurface = 0;
constexpr uint8_t kGroundSurface = 1;
constexpr uint8_t kWallSurface = 2;
constexpr uint8_t kOuterCeilingSurface = 4;

constexpr double kNormalDotTolerance = 1e-4;
constexpr double kPlaneDistanceTolerance = 1e-2;
constexpr double kSemanticNzThreshold = 0.3;
constexpr double kGroundZTolerance = 0.5;

struct Vec2 {
    double x = 0.0;
    double y = 0.0;
};

struct FaceGeometry {
    std::vector<Surface_mesh::Vertex_index> vertices;
    K::Point_3 centroid;
    K::Vector_3 unit_normal;
    double avg_z = 0.0;
};

struct PreparedSourceSurface {
    uint8_t semantic_type = kWallSurface;
    K::Point_3 plane_point;
    K::Vector_3 unit_normal;
    int drop_axis = 2;
    std::vector<std::vector<Vec2>> rings;
};

struct BoundaryEdge {
    uint32_t from = 0;
    uint32_t to = 0;
};

size_t descriptor_id(Surface_mesh::Vertex_index v) {
    return static_cast<size_t>(v);
}

size_t descriptor_id(Surface_mesh::Face_index f) {
    return static_cast<size_t>(f);
}

K::Vector_3 normalize_vector(const K::Vector_3& v) {
    const double len_sq = v.squared_length();
    if (!std::isfinite(len_sq) || len_sq <= 1e-18) {
        return K::Vector_3(0.0, 0.0, 0.0);
    }
    const double inv_len = 1.0 / std::sqrt(len_sq);
    return K::Vector_3(v.x() * inv_len, v.y() * inv_len, v.z() * inv_len);
}

int choose_drop_axis(const K::Vector_3& normal) {
    const double ax = std::abs(normal.x());
    const double ay = std::abs(normal.y());
    const double az = std::abs(normal.z());
    if (ax >= ay && ax >= az) {
        return 0;
    }
    if (ay >= az) {
        return 1;
    }
    return 2;
}

Vec2 project_point(const K::Point_3& p, int drop_axis) {
    switch (drop_axis) {
        case 0:
            return {p.y(), p.z()};
        case 1:
            return {p.x(), p.z()};
        default:
            return {p.x(), p.y()};
    }
}

double signed_area_2d(const std::vector<Vec2>& ring) {
    if (ring.size() < 3) {
        return 0.0;
    }
    double area = 0.0;
    for (size_t i = 0; i < ring.size(); ++i) {
        const size_t j = (i + 1) % ring.size();
        area += ring[i].x * ring[j].y - ring[j].x * ring[i].y;
    }
    return 0.5 * area;
}

bool point_in_ring(const Vec2& p, const std::vector<Vec2>& ring) {
    if (ring.size() < 3) {
        return false;
    }

    bool inside = false;
    for (size_t i = 0, j = ring.size() - 1; i < ring.size(); j = i++) {
        const auto& a = ring[i];
        const auto& b = ring[j];
        const bool intersects = ((a.y > p.y) != (b.y > p.y)) &&
            (p.x < (b.x - a.x) * (p.y - a.y) / ((b.y - a.y) == 0.0 ? 1e-18 : (b.y - a.y)) + a.x);
        if (intersects) {
            inside = !inside;
        }
    }
    return inside;
}

bool point_in_surface(const Vec2& p, const PreparedSourceSurface& surface) {
    if (surface.rings.empty() || !point_in_ring(p, surface.rings.front())) {
        return false;
    }
    for (size_t i = 1; i < surface.rings.size(); ++i) {
        if (point_in_ring(p, surface.rings[i])) {
            return false;
        }
    }
    return true;
}

K::Vector_3 compute_ring_normal(
    const std::vector<Surface_mesh::Vertex_index>& ring,
    const Surface_mesh& mesh) {
    double nx = 0.0;
    double ny = 0.0;
    double nz = 0.0;
    const size_t n = ring.size();
    if (n < 3) {
        return K::Vector_3(0.0, 0.0, 0.0);
    }

    for (size_t i = 0; i < n; ++i) {
        const size_t j = (i + 1) % n;
        const auto& p = mesh.point(ring[i]);
        const auto& q = mesh.point(ring[j]);
        nx += (p.y() - q.y()) * (p.z() + q.z());
        ny += (p.z() - q.z()) * (p.x() + q.x());
        nz += (p.x() - q.x()) * (p.y() + q.y());
    }
    return K::Vector_3(nx, ny, nz);
}

FaceGeometry compute_face_geometry(const Surface_mesh& mesh, Surface_mesh::Face_index face) {
    FaceGeometry geom;
    double cx = 0.0;
    double cy = 0.0;
    double cz = 0.0;
    for (auto v : mesh.vertices_around_face(mesh.halfedge(face))) {
        geom.vertices.push_back(v);
        const auto& p = mesh.point(v);
        cx += p.x();
        cy += p.y();
        cz += p.z();
    }

    if (geom.vertices.empty()) {
        geom.centroid = K::Point_3(0.0, 0.0, 0.0);
        geom.unit_normal = K::Vector_3(0.0, 0.0, 0.0);
        return geom;
    }

    const double inv_n = 1.0 / static_cast<double>(geom.vertices.size());
    geom.centroid = K::Point_3(cx * inv_n, cy * inv_n, cz * inv_n);
    geom.avg_z = cz * inv_n;
    geom.unit_normal = normalize_vector(compute_ring_normal(geom.vertices, mesh));
    return geom;
}

std::vector<PreparedSourceSurface> prepare_source_surfaces(const LoadedSolidMesh& source_mesh) {
    std::vector<PreparedSourceSurface> prepared;
    prepared.reserve(source_mesh.semantic_surfaces.size());

    for (const auto& surface : source_mesh.semantic_surfaces) {
        if (surface.rings.empty() || surface.rings.front().size() < 3) {
            continue;
        }

        std::vector<Surface_mesh::Vertex_index> outer_ring;
        outer_ring.reserve(surface.rings.front().size());
        for (size_t idx : surface.rings.front()) {
            outer_ring.push_back(Surface_mesh::Vertex_index(idx));
        }

        const auto normal = normalize_vector(compute_ring_normal(outer_ring, source_mesh.mesh));
        if (normal == CGAL::NULL_VECTOR) {
            continue;
        }

        PreparedSourceSurface prepared_surface;
        prepared_surface.semantic_type = surface.semantic_type;
        prepared_surface.plane_point = source_mesh.mesh.point(outer_ring.front());
        prepared_surface.unit_normal = normal;
        prepared_surface.drop_axis = choose_drop_axis(normal);

        for (const auto& ring_indices : surface.rings) {
            if (ring_indices.size() < 3) {
                continue;
            }
            std::vector<Vec2> ring_2d;
            ring_2d.reserve(ring_indices.size());
            for (size_t idx : ring_indices) {
                ring_2d.push_back(project_point(source_mesh.mesh.point(Surface_mesh::Vertex_index(idx)),
                                                prepared_surface.drop_axis));
            }
            prepared_surface.rings.push_back(std::move(ring_2d));
        }

        if (!prepared_surface.rings.empty()) {
            prepared.push_back(std::move(prepared_surface));
        }
    }

    return prepared;
}

uint8_t classify_face_semantic(const FaceGeometry& geom, double house_min_z) {
    const double nz = geom.unit_normal.z();
    if (std::abs(nz) < kSemanticNzThreshold) {
        return kWallSurface;
    }
    if (nz > 0.0) {
        return kRoofSurface;
    }
    if (std::abs(geom.avg_z - house_min_z) < kGroundZTolerance) {
        return kGroundSurface;
    }
    return kOuterCeilingSurface;
}

uint8_t infer_face_semantic(
    const FaceGeometry& geom,
    const std::vector<PreparedSourceSurface>& source_surfaces,
    double house_min_z) {
    for (const auto& source : source_surfaces) {
        const double dot = geom.unit_normal * source.unit_normal;
        if (!std::isfinite(dot) || std::abs(std::abs(dot) - 1.0) > kNormalDotTolerance) {
            continue;
        }

        const auto plane_vec = geom.centroid - source.plane_point;
        const double plane_distance = std::abs(plane_vec * source.unit_normal);
        if (plane_distance > kPlaneDistanceTolerance) {
            continue;
        }

        if (point_in_surface(project_point(geom.centroid, source.drop_axis), source)) {
            return source.semantic_type;
        }
    }

    return classify_face_semantic(geom, house_min_z);
}

bool face_is_coplanar_with_group(
    const Surface_mesh& mesh,
    const FaceGeometry& candidate,
    const K::Point_3& plane_point,
    const K::Vector_3& plane_normal) {
    const double dot = candidate.unit_normal * plane_normal;
    if (!std::isfinite(dot) || std::abs(std::abs(dot) - 1.0) > kNormalDotTolerance) {
        return false;
    }
    for (auto v : candidate.vertices) {
        const double distance = std::abs((mesh.point(v) - plane_point) * plane_normal);
        if (distance > kPlaneDistanceTolerance) {
            return false;
        }
    }
    return true;
}

std::vector<std::vector<uint32_t>> extract_group_cycles(
    const Surface_mesh& mesh,
    const std::vector<Surface_mesh::Face_index>& group_faces,
    const std::unordered_map<size_t, size_t>& face_group,
    size_t group_id,
    const std::unordered_map<size_t, uint32_t>& vertex_to_dense) {
    std::vector<BoundaryEdge> boundary_edges;

    for (auto face : group_faces) {
        for (auto h : mesh.halfedges_around_face(mesh.halfedge(face))) {
            const auto opposite = mesh.opposite(h);
            const auto opposite_face = mesh.face(opposite);
            const bool boundary = opposite_face == Surface_mesh::null_face() ||
                face_group.find(descriptor_id(opposite_face)) == face_group.end() ||
                face_group.at(descriptor_id(opposite_face)) != group_id;
            if (!boundary) {
                continue;
            }

            const auto from_it = vertex_to_dense.find(descriptor_id(mesh.source(h)));
            const auto to_it = vertex_to_dense.find(descriptor_id(mesh.target(h)));
            if (from_it == vertex_to_dense.end() || to_it == vertex_to_dense.end()) {
                continue;
            }
            boundary_edges.push_back(BoundaryEdge{
                .from = from_it->second,
                .to = to_it->second,
            });
        }
    }

    std::unordered_map<uint32_t, std::vector<size_t>> outgoing;
    for (size_t edge_idx = 0; edge_idx < boundary_edges.size(); ++edge_idx) {
        outgoing[boundary_edges[edge_idx].from].push_back(edge_idx);
    }

    std::vector<bool> visited(boundary_edges.size(), false);
    std::vector<std::vector<uint32_t>> cycles;

    for (size_t edge_idx = 0; edge_idx < boundary_edges.size(); ++edge_idx) {
        if (visited[edge_idx]) {
            continue;
        }

        std::vector<uint32_t> ring;
        const uint32_t start_vertex = boundary_edges[edge_idx].from;
        uint32_t current_vertex = start_vertex;
        size_t current_edge = edge_idx;

        for (size_t step = 0; step <= boundary_edges.size(); ++step) {
            if (visited[current_edge]) {
                break;
            }
            visited[current_edge] = true;
            if (ring.empty()) {
                ring.push_back(boundary_edges[current_edge].from);
            }
            ring.push_back(boundary_edges[current_edge].to);
            current_vertex = boundary_edges[current_edge].to;
            if (current_vertex == start_vertex) {
                ring.pop_back();
                break;
            }

            auto next_it = outgoing.find(current_vertex);
            if (next_it == outgoing.end()) {
                ring.clear();
                break;
            }

            bool found_next = false;
            for (size_t candidate_edge : next_it->second) {
                if (!visited[candidate_edge]) {
                    current_edge = candidate_edge;
                    found_next = true;
                    break;
                }
            }
            if (!found_next) {
                ring.clear();
                break;
            }
        }

        if (ring.size() >= 3) {
            cycles.push_back(std::move(ring));
        }
    }

    return cycles;
}

void orient_cycles(
    const std::vector<K::Point_3>& dense_vertices,
    const K::Vector_3& normal,
    std::vector<std::vector<uint32_t>>& cycles) {
    if (cycles.empty()) {
        return;
    }

    const int drop_axis = choose_drop_axis(normal);
    size_t outer_index = 0;
    double largest_area = 0.0;
    std::vector<double> signed_areas(cycles.size(), 0.0);

    for (size_t i = 0; i < cycles.size(); ++i) {
        std::vector<Vec2> ring_2d;
        ring_2d.reserve(cycles[i].size());
        for (uint32_t idx : cycles[i]) {
            ring_2d.push_back(project_point(dense_vertices[idx], drop_axis));
        }
        signed_areas[i] = signed_area_2d(ring_2d);
        if (std::abs(signed_areas[i]) > largest_area) {
            largest_area = std::abs(signed_areas[i]);
            outer_index = i;
        }
    }

    if (outer_index != 0) {
        std::swap(cycles[0], cycles[outer_index]);
        std::swap(signed_areas[0], signed_areas[outer_index]);
    }

    const double outer_sign = signed_areas[0];
    for (size_t i = 1; i < cycles.size(); ++i) {
        if ((signed_areas[i] >= 0.0) == (outer_sign >= 0.0)) {
            std::reverse(cycles[i].begin(), cycles[i].end());
        }
    }
}

} // namespace

bool build_polygonal_output_from_cgal_mesh(
    const Surface_mesh& result_mesh,
    const LoadedSolidMesh& source_mesh,
    double house_min_z,
    double underpass_z,
    double offset_x,
    double offset_y,
    double offset_z,
    PolygonalOutput& out) {
    (void)underpass_z;
    out = {};
    if (result_mesh.number_of_faces() == 0 || result_mesh.number_of_vertices() == 0) {
        return false;
    }

    std::unordered_map<size_t, uint32_t> vertex_to_dense;
    vertex_to_dense.reserve(result_mesh.number_of_vertices());
    std::vector<K::Point_3> dense_vertices;
    dense_vertices.reserve(result_mesh.number_of_vertices());
    for (auto v : result_mesh.vertices()) {
        const uint32_t dense_index = static_cast<uint32_t>(dense_vertices.size());
        vertex_to_dense.emplace(descriptor_id(v), dense_index);
        const auto& p = result_mesh.point(v);
        dense_vertices.push_back(K::Point_3(p.x(), p.y(), p.z()));
        out.vertices_xyz_world.push_back(p.x() + offset_x);
        out.vertices_xyz_world.push_back(p.y() + offset_y);
        out.vertices_xyz_world.push_back(p.z() + offset_z);
    }

    const auto prepared_sources = prepare_source_surfaces(source_mesh);

    std::unordered_map<size_t, FaceGeometry> face_geometry;
    std::unordered_map<size_t, uint8_t> face_semantic;
    face_geometry.reserve(result_mesh.number_of_faces());
    face_semantic.reserve(result_mesh.number_of_faces());
    for (auto face : result_mesh.faces()) {
        auto geom = compute_face_geometry(result_mesh, face);
        const size_t face_id = descriptor_id(face);
        face_semantic.emplace(face_id, infer_face_semantic(geom, prepared_sources, house_min_z));
        face_geometry.emplace(face_id, std::move(geom));
    }

    std::unordered_map<size_t, size_t> face_group;
    face_group.reserve(result_mesh.number_of_faces());
    std::vector<std::vector<Surface_mesh::Face_index>> groups;

    for (auto seed_face : result_mesh.faces()) {
        const size_t seed_id = descriptor_id(seed_face);
        if (face_group.find(seed_id) != face_group.end()) {
            continue;
        }

        const auto& seed_geom = face_geometry.at(seed_id);
        const uint8_t seed_semantic = face_semantic.at(seed_id);
        const size_t group_id = groups.size();

        std::queue<Surface_mesh::Face_index> queue;
        std::vector<Surface_mesh::Face_index> group_faces;
        queue.push(seed_face);
        face_group.emplace(seed_id, group_id);

        while (!queue.empty()) {
            const auto face = queue.front();
            queue.pop();
            group_faces.push_back(face);

            for (auto h : result_mesh.halfedges_around_face(result_mesh.halfedge(face))) {
                const auto neighbor = result_mesh.face(result_mesh.opposite(h));
                if (neighbor == Surface_mesh::null_face()) {
                    continue;
                }
                const size_t neighbor_id = descriptor_id(neighbor);
                if (face_group.find(neighbor_id) != face_group.end()) {
                    continue;
                }
                if (face_semantic.at(neighbor_id) != seed_semantic) {
                    continue;
                }
                if (!face_is_coplanar_with_group(
                        result_mesh,
                        face_geometry.at(neighbor_id),
                        seed_geom.centroid,
                        seed_geom.unit_normal)) {
                    continue;
                }

                face_group.emplace(neighbor_id, group_id);
                queue.push(neighbor);
            }
        }

        groups.push_back(std::move(group_faces));
    }

    for (size_t group_id = 0; group_id < groups.size(); ++group_id) {
        if (groups[group_id].empty()) {
            continue;
        }

        auto cycles = extract_group_cycles(result_mesh, groups[group_id], face_group, group_id, vertex_to_dense);
        if (cycles.empty()) {
            continue;
        }

        const auto& seed_geom = face_geometry.at(descriptor_id(groups[group_id].front()));
        orient_cycles(dense_vertices, seed_geom.unit_normal, cycles);

        out.surface_ring_counts.push_back(static_cast<uint32_t>(cycles.size()));
        out.surface_semantic_types.push_back(face_semantic.at(descriptor_id(groups[group_id].front())));
        for (const auto& cycle : cycles) {
            out.ring_vertex_counts.push_back(static_cast<uint32_t>(cycle.size()));
            out.boundary_indices.insert(out.boundary_indices.end(), cycle.begin(), cycle.end());
        }
    }

    return !out.surface_ring_counts.empty() && !out.boundary_indices.empty();
}
