#include "ModelLoaders.h"

#include <CGAL/Constrained_Delaunay_triangulation_2.h>
#include <CGAL/Exact_predicates_inexact_constructions_kernel.h>
#include <CGAL/Projection_traits_3.h>
#include <CGAL/Triangulation_face_base_with_info_2.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <exception>
#include <iostream>
#include <string>
#include <unordered_map>
#include <vector>

#include "CdtDomainMarking.h"
#include "zityjson.h"
#include "zfcb.h"

namespace {

constexpr uint8_t kDefaultSemanticType = 2;

struct FaceInfo {
    int nesting_level = -1;
    bool in_domain() const { return nesting_level % 2 == 1; }
};

K::Vector_3 compute_newell_normal(
    const std::vector<size_t>& ring,
    const std::vector<Surface_mesh::Vertex_index>& vertex_handles,
    const Surface_mesh& sm) {
    double nx = 0.0;
    double ny = 0.0;
    double nz = 0.0;
    const size_t n = ring.size();
    if (n < 3) {
        return K::Vector_3(0.0, 0.0, 0.0);
    }

    for (size_t i = 0; i < n; ++i) {
        const size_t j = (i + 1) % n;
        const auto& p = sm.point(vertex_handles[ring[i]]);
        const auto& q = sm.point(vertex_handles[ring[j]]);
        nx += (p.y() - q.y()) * (p.z() + q.z());
        ny += (p.z() - q.z()) * (p.x() + q.x());
        nz += (p.x() - q.x()) * (p.y() + q.y());
    }
    return K::Vector_3(nx, ny, nz);
}

double ring_orientation_sign(
    const std::vector<size_t>& ring,
    const std::vector<Surface_mesh::Vertex_index>& vertex_handles,
    const Surface_mesh& sm,
    const K::Vector_3& normal) {
    const size_t n = ring.size();
    if (n < 3) {
        return 0.0;
    }

    double sx = 0.0;
    double sy = 0.0;
    double sz = 0.0;
    for (size_t i = 0; i < n; ++i) {
        const size_t j = (i + 1) % n;
        const auto& p = sm.point(vertex_handles[ring[i]]);
        const auto& q = sm.point(vertex_handles[ring[j]]);
        sx += p.y() * q.z() - p.z() * q.y();
        sy += p.z() * q.x() - p.x() * q.z();
        sz += p.x() * q.y() - p.y() * q.x();
    }
    return sx * normal.x() + sy * normal.y() + sz * normal.z();
}

std::vector<size_t> deduplicate_ring_indices(const std::vector<size_t>& ring) {
    std::vector<size_t> cleaned;
    cleaned.reserve(ring.size());
    for (size_t idx : ring) {
        if (!cleaned.empty() && cleaned.back() == idx) {
            continue;
        }
        cleaned.push_back(idx);
    }
    if (cleaned.size() >= 2 && cleaned.front() == cleaned.back()) {
        cleaned.pop_back();
    }
    return cleaned;
}

bool triangulate_surface_with_holes(
    std::vector<std::vector<size_t>> rings,
    const std::vector<Surface_mesh::Vertex_index>& vertex_handles,
    Surface_mesh& sm,
    std::string* failure_reason) {
    if (failure_reason != nullptr) {
        failure_reason->clear();
    }
    if (rings.empty()) {
        if (failure_reason != nullptr) {
            *failure_reason = "no rings in surface";
        }
        return false;
    }
    for (auto& ring : rings) {
        ring = deduplicate_ring_indices(ring);
    }
    if (rings[0].size() < 3) {
        if (failure_reason != nullptr) {
            *failure_reason = "outer ring has fewer than 3 unique vertices";
        }
        return false;
    }

    K::Vector_3 normal = compute_newell_normal(rings[0], vertex_handles, sm);
    const double normal_len_sq = normal.squared_length();
    if (!std::isfinite(normal_len_sq) || normal_len_sq <= 1e-18) {
        if (failure_reason != nullptr) {
            *failure_reason = "surface normal is degenerate";
        }
        return false;
    }

    const double outer_sign = ring_orientation_sign(rings[0], vertex_handles, sm, normal);
    if (outer_sign < 0.0) {
        std::reverse(rings[0].begin(), rings[0].end());
    }
    for (size_t i = 1; i < rings.size(); ++i) {
        const double hole_sign = ring_orientation_sign(rings[i], vertex_handles, sm, normal);
        if (hole_sign > 0.0) {
            std::reverse(rings[i].begin(), rings[i].end());
        }
    }

    using CDT_K = CGAL::Exact_predicates_inexact_constructions_kernel;
    using Projection_traits = CGAL::Projection_traits_3<CDT_K>;
    using VertexBase = CGAL::Triangulation_vertex_base_2<Projection_traits>;
    using FaceBase = CGAL::Constrained_triangulation_face_base_2<Projection_traits>;
    using FaceBaseWithInfo = CGAL::Triangulation_face_base_with_info_2<FaceInfo, Projection_traits, FaceBase>;
    using TDS = CGAL::Triangulation_data_structure_2<VertexBase, FaceBaseWithInfo>;
    using CDT = CGAL::Constrained_Delaunay_triangulation_2<Projection_traits, TDS, CGAL::Exact_predicates_tag>;

    try {
        const CDT_K::Vector_3 normal_epick(normal.x(), normal.y(), normal.z());
        Projection_traits traits(normal_epick);
        CDT cdt(traits);
        std::unordered_map<std::uintptr_t, size_t> source_vertex_by_handle;

        for (const auto& ring : rings) {
            if (ring.size() < 3) {
                continue;
            }
            std::vector<CDT::Vertex_handle> handles;
            handles.reserve(ring.size());
            for (size_t idx : ring) {
                if (idx >= vertex_handles.size()) {
                    continue;
                }
                const auto& p = sm.point(vertex_handles[idx]);
                auto vh = cdt.insert(CDT_K::Point_3(p.x(), p.y(), p.z()));
                source_vertex_by_handle.try_emplace(reinterpret_cast<std::uintptr_t>(&*vh), idx);
                handles.push_back(vh);
            }
            if (handles.size() < 3) {
                continue;
            }
            for (size_t i = 0; i < handles.size(); ++i) {
                const size_t j = (i + 1) % handles.size();
                if (handles[i] != handles[j]) {
                    cdt.insert_constraint(handles[i], handles[j]);
                }
            }
        }

        if (cdt.number_of_faces() == 0) {
            if (failure_reason != nullptr) {
                *failure_reason = "CDT produced no faces";
            }
            return false;
        }

        cdt_domain_marking::mark_domains(cdt);

        bool added = false;
        for (auto fit = cdt.finite_faces_begin(); fit != cdt.finite_faces_end(); ++fit) {
            if (!fit->info().in_domain()) {
                continue;
            }

            const auto it0 = source_vertex_by_handle.find(reinterpret_cast<std::uintptr_t>(&*(fit->vertex(0))));
            const auto it1 = source_vertex_by_handle.find(reinterpret_cast<std::uintptr_t>(&*(fit->vertex(1))));
            const auto it2 = source_vertex_by_handle.find(reinterpret_cast<std::uintptr_t>(&*(fit->vertex(2))));
            if (it0 == source_vertex_by_handle.end() ||
                it1 == source_vertex_by_handle.end() ||
                it2 == source_vertex_by_handle.end()) {
                continue;
            }

            const size_t i0 = it0->second;
            const size_t i1 = it1->second;
            const size_t i2 = it2->second;
            if (i0 >= vertex_handles.size() || i1 >= vertex_handles.size() || i2 >= vertex_handles.size()) {
                continue;
            }
            if (i0 == i1 || i1 == i2 || i0 == i2) {
                continue;
            }

            if (sm.add_face(vertex_handles[i0], vertex_handles[i1], vertex_handles[i2]) != Surface_mesh::null_face()) {
                added = true;
            }
        }

        if (!added && failure_reason != nullptr) {
            *failure_reason = "no valid in-domain triangles after triangulation";
        }
        return added;
    } catch (const std::exception&) {
        if (failure_reason != nullptr) {
            *failure_reason = "CDT threw an exception";
        }
        return false;
    } catch (...) {
        if (failure_reason != nullptr) {
            *failure_reason = "CDT threw an unknown exception";
        }
        return false;
    }
}

template <typename T, typename SemanticGetter>
bool append_ringed_geometry_faces(
    const std::vector<Surface_mesh::Vertex_index>& vertex_handles,
    size_t vertex_count,
    const T* surfaces,
    size_t surface_count,
    const T* strings,
    size_t string_count,
    const T* boundaries,
    size_t boundary_count,
    Surface_mesh& sm,
    std::vector<SemanticSurface>* semantic_surfaces,
    SemanticGetter&& get_surface_semantic_type,
    std::string_view mesh_context) {
    if (surfaces == nullptr || strings == nullptr || boundaries == nullptr) {
        std::cerr << "Skipping all surfaces for " << mesh_context
                  << ": missing surfaces/strings/boundaries arrays" << std::endl;
        return false;
    }
    if (surface_count == 0 || string_count == 0 || boundary_count == 0) {
        std::cerr << "Skipping all surfaces for " << mesh_context
                  << ": empty surfaces/strings/boundaries arrays" << std::endl;
        return false;
    }

    size_t ring_cursor = 0;
    size_t boundary_cursor = 0;
    bool added_faces = false;

    for (size_t s = 0; s < surface_count; ++s) {
        const size_t rings_in_surface = static_cast<size_t>(surfaces[s]);
        if (rings_in_surface == 0) {
            continue;
        }

        std::vector<std::vector<size_t>> rings;
        rings.reserve(rings_in_surface);

        bool malformed = false;
        size_t parsed_ring_count = 0;
        for (; parsed_ring_count < rings_in_surface && ring_cursor < string_count; ++parsed_ring_count, ++ring_cursor) {
            const size_t ring_size = static_cast<size_t>(strings[ring_cursor]);
            if (ring_size > boundary_count - boundary_cursor) {
                malformed = true;
                boundary_cursor = boundary_count;
                std::cerr << "Skipping surface " << s << " for " << mesh_context
                          << ": ring size exceeds boundary array" << std::endl;
                break;
            }

            std::vector<size_t> ring;
            ring.reserve(ring_size);
            bool ring_valid = ring_size >= 3;
            for (size_t i = 0; i < ring_size; ++i) {
                const size_t idx = static_cast<size_t>(boundaries[boundary_cursor + i]);
                if (idx >= vertex_count) {
                    ring_valid = false;
                }
                ring.push_back(idx);
            }
            boundary_cursor += ring_size;

            if (parsed_ring_count == 0 && !ring_valid) {
                malformed = true;
                std::cerr << "Skipping surface " << s << " for " << mesh_context
                          << ": outer ring has invalid vertex indices or <3 vertices" << std::endl;
            }
            if (ring_valid) {
                rings.push_back(std::move(ring));
            }
        }

        if (parsed_ring_count != rings_in_surface) {
            malformed = true;
            std::cerr << "Skipping surface " << s << " for " << mesh_context
                      << ": truncated ring list for surface" << std::endl;
        }
        if (malformed || rings.empty()) {
            if (!malformed) {
                std::cerr << "Skipping surface " << s << " for " << mesh_context
                          << ": no valid rings in surface" << std::endl;
            }
            continue;
        }

        auto rings_copy = rings;
        std::string tri_failure;
        if (triangulate_surface_with_holes(std::move(rings), vertex_handles, sm, &tri_failure)) {
            added_faces = true;
            if (semantic_surfaces != nullptr) {
                uint8_t semantic_type = kDefaultSemanticType;
                get_surface_semantic_type(s, semantic_type);
                semantic_surfaces->push_back(SemanticSurface{
                    .rings = std::move(rings_copy),
                    .semantic_type = semantic_type,
                });
            }
        } else {
            std::cerr << "Skipping surface " << s << " for " << mesh_context
                      << ": " << (tri_failure.empty() ? "triangulation failed" : tri_failure) << std::endl;
        }
    }

    return added_faces;
}

} // namespace

bool is_fcb_path(const std::string_view path) {
    constexpr std::string_view ext = ".fcb";
    if (path.size() < ext.size()) {
        return false;
    }
    return path.substr(path.size() - ext.size()) == ext;
}

bool is_cityjsonseq_path(const std::string_view path) {
    constexpr std::string_view jsonl_ext = ".jsonl";
    constexpr std::string_view cityjsonl_ext = ".city.jsonl";
    if (path.size() >= cityjsonl_ext.size() &&
        path.substr(path.size() - cityjsonl_ext.size()) == cityjsonl_ext) {
        return true;
    }
    if (path.size() >= jsonl_ext.size() &&
        path.substr(path.size() - jsonl_ext.size()) == jsonl_ext) {
        return true;
    }
    return false;
}

ssize_t resolve_cityjson_object_index(CityJSONHandle cj, std::string_view feature_id) {
    if (cj == nullptr || feature_id.empty()) {
        return -1;
    }

    std::string feature_id_str(feature_id);
    std::string object_id = feature_id_str + "-0";
    ssize_t object_index = cityjson_get_object_index(cj, object_id.c_str());
    if (object_index >= 0) {
        return object_index;
    }
    return cityjson_get_object_index(cj, feature_id_str.c_str());
}

bool load_cityjson_object_mesh(
    CityJSONHandle cj,
    size_t object_index,
    LoadedSolidMesh& out,
    double offset_x,
    double offset_y,
    double offset_z) {
    out.mesh.clear();
    out.semantic_surfaces.clear();
    if (cj == nullptr) {
        return false;
    }

    ssize_t geometry_index = -1;
    size_t geom_count = cityjson_get_geometry_count(cj, object_index);
    for (size_t geom_idx = 0; geom_idx < geom_count; ++geom_idx) {
        uint8_t geom_type = cityjson_get_geometry_type(cj, object_index, geom_idx);
        if (geom_type != CITYJSON_SOLID) {
            continue;
        }

        const char* lod_ptr = nullptr;
        size_t lod_len = 0;
        if (cityjson_get_geometry_lod(cj, object_index, geom_idx, &lod_ptr, &lod_len) != 1) {
            continue;
        }
        std::string_view lod = (lod_ptr != nullptr) ? std::string_view(lod_ptr, lod_len) : std::string_view{};
        if (lod == "2.2") {
            geometry_index = static_cast<ssize_t>(geom_idx);
            break;
        }
    }
    if (geometry_index < 0) {
        return false;
    }

    const size_t geom_idx = static_cast<size_t>(geometry_index);
    size_t vertex_count = cityjson_get_vertex_count(cj, object_index, geom_idx);
    const double* vertices = cityjson_get_vertices(cj, object_index, geom_idx);
    if (vertices == nullptr || vertex_count == 0) {
        return false;
    }

    std::vector<Surface_mesh::Vertex_index> vertex_handles;
    vertex_handles.reserve(vertex_count);
    for (size_t v = 0; v < vertex_count; ++v) {
        vertex_handles.push_back(out.mesh.add_vertex(K::Point_3(
            vertices[v * 3] - offset_x,
            vertices[v * 3 + 1] - offset_y,
            vertices[v * 3 + 2] - offset_z)));
    }

    const size_t surface_count = cityjson_get_geometry_surface_count(cj, object_index, geom_idx);
    const size_t string_count = cityjson_get_geometry_string_count(cj, object_index, geom_idx);
    const size_t boundary_count = cityjson_get_geometry_boundary_count(cj, object_index, geom_idx);
    const size_t* surfaces = cityjson_get_geometry_surfaces(cj, object_index, geom_idx);
    const size_t* strings = cityjson_get_geometry_strings(cj, object_index, geom_idx);
    const size_t* boundaries = cityjson_get_geometry_boundaries(cj, object_index, geom_idx);

    const std::string mesh_context =
        std::string("CityJSON object_index=") + std::to_string(object_index) +
        " geometry_index=" + std::to_string(geom_idx);

    auto semantic_getter = [&](size_t surface_index, uint8_t& semantic_type) {
        semantic_type = kDefaultSemanticType;
        (void)cityjson_get_geometry_surface_semantic_type(
            cj, object_index, geom_idx, surface_index, &semantic_type);
    };

    return append_ringed_geometry_faces(
        vertex_handles,
        vertex_count,
        surfaces,
        surface_count,
        strings,
        string_count,
        boundaries,
        boundary_count,
        out.mesh,
        &out.semantic_surfaces,
        semantic_getter,
        mesh_context);
}

bool load_cityjson_object_mesh(
    CityJSONHandle cj,
    size_t object_index,
    Surface_mesh& sm,
    double offset_x,
    double offset_y,
    double offset_z) {
    LoadedSolidMesh loaded;
    if (!load_cityjson_object_mesh(cj, object_index, loaded, offset_x, offset_y, offset_z)) {
        return false;
    }
    sm = std::move(loaded.mesh);
    return true;
}

bool load_fcb_feature_mesh(
    ZfcbReaderHandle fcb,
    std::string_view feature_id,
    LoadedSolidMesh& out,
    double offset_x,
    double offset_y,
    double offset_z,
    std::string* out_b3_val3dity_lod22) {
    out.mesh.clear();
    out.semantic_surfaces.clear();
    if (out_b3_val3dity_lod22 != nullptr) {
        out_b3_val3dity_lod22->clear();
    }

    size_t vertex_count = zfcb_current_vertex_count(fcb);
    const double* vertices = zfcb_current_vertices(fcb);
    if (vertices == nullptr || vertex_count == 0) {
        return false;
    }

    std::vector<Surface_mesh::Vertex_index> vertex_handles;
    vertex_handles.reserve(vertex_count);
    for (size_t v = 0; v < vertex_count; ++v) {
        vertex_handles.push_back(out.mesh.add_vertex(K::Point_3(
            vertices[v * 3] - offset_x,
            vertices[v * 3 + 1] - offset_y,
            vertices[v * 3 + 2] - offset_z)));
    }

    const std::string object_id = std::string(feature_id) + "-0";
    ssize_t object_index = -1;
    ssize_t feature_object_index = -1;
    size_t object_count = zfcb_current_object_count(fcb);
    for (size_t obj_idx = 0; obj_idx < object_count; ++obj_idx) {
        const char* current_obj_id_ptr = nullptr;
        size_t current_obj_id_len = 0;
        if (zfcb_current_object_id(fcb, obj_idx, &current_obj_id_ptr, &current_obj_id_len) != 0) {
            continue;
        }
        std::string_view current_obj_id(current_obj_id_ptr, current_obj_id_len);
        if (current_obj_id == object_id) {
            object_index = static_cast<ssize_t>(obj_idx);
        }
        if (current_obj_id == feature_id) {
            feature_object_index = static_cast<ssize_t>(obj_idx);
        }
        if (object_index >= 0 &&
            (out_b3_val3dity_lod22 == nullptr || feature_object_index >= 0)) {
            break;
        }
    }

    if (out_b3_val3dity_lod22 != nullptr && feature_object_index >= 0) {
        constexpr std::string_view kB3Val3dityLod22 = "b3_val3dity_lod22";
        const char* attr_value_ptr = nullptr;
        size_t attr_value_len = 0;
        int attr_result = zfcb_current_object_string_attribute(
            fcb,
            static_cast<size_t>(feature_object_index),
            kB3Val3dityLod22.data(),
            kB3Val3dityLod22.size(),
            &attr_value_ptr,
            &attr_value_len);
        if (attr_result == 1 && attr_value_ptr != nullptr) {
            *out_b3_val3dity_lod22 = std::string(attr_value_ptr, attr_value_len);
        }
    }

    if (object_index < 0) {
        return false;
    }

    ssize_t geometry_index = -1;
    size_t geom_count = zfcb_current_object_geometry_count(fcb, static_cast<size_t>(object_index));
    for (size_t geom_idx = 0; geom_idx < geom_count; ++geom_idx) {
        uint8_t geom_type = zfcb_current_geometry_type(fcb, static_cast<size_t>(object_index), geom_idx);
        bool solid_like = geom_type == ZFCB_GEOMETRY_SOLID ||
                          geom_type == ZFCB_GEOMETRY_MULTI_SOLID ||
                          geom_type == ZFCB_GEOMETRY_COMPOSITE_SOLID;
        if (!solid_like) {
            continue;
        }

        const char* lod_ptr = nullptr;
        size_t lod_len = 0;
        if (zfcb_current_geometry_lod(fcb, static_cast<size_t>(object_index), geom_idx, &lod_ptr, &lod_len) != 0) {
            continue;
        }
        std::string_view lod = (lod_ptr != nullptr) ? std::string_view(lod_ptr, lod_len) : std::string_view{};
        if (lod == "2.2") {
            geometry_index = static_cast<ssize_t>(geom_idx);
            break;
        }
    }
    if (geometry_index < 0) {
        return false;
    }

    size_t geom_idx = static_cast<size_t>(geometry_index);
    size_t surface_count = zfcb_current_geometry_surface_count(fcb, static_cast<size_t>(object_index), geom_idx);
    size_t string_count = zfcb_current_geometry_string_count(fcb, static_cast<size_t>(object_index), geom_idx);
    size_t boundary_count = zfcb_current_geometry_boundary_count(fcb, static_cast<size_t>(object_index), geom_idx);
    const uint32_t* surfaces = zfcb_current_geometry_surfaces(fcb, static_cast<size_t>(object_index), geom_idx);
    const uint32_t* strings = zfcb_current_geometry_strings(fcb, static_cast<size_t>(object_index), geom_idx);
    const uint32_t* boundaries = zfcb_current_geometry_boundaries(fcb, static_cast<size_t>(object_index), geom_idx);

    const std::string mesh_context =
        std::string("FCB feature='") + std::string(feature_id) +
        "' object_index=" + std::to_string(object_index) +
        " geometry_index=" + std::to_string(geom_idx);

    auto semantic_getter = [&](size_t surface_index, uint8_t& semantic_type) {
        semantic_type = kDefaultSemanticType;
        (void)zfcb_current_geometry_surface_semantic_type(
            fcb, static_cast<size_t>(object_index), geom_idx, surface_index, &semantic_type);
    };

    return append_ringed_geometry_faces(
        vertex_handles,
        vertex_count,
        surfaces,
        surface_count,
        strings,
        string_count,
        boundaries,
        boundary_count,
        out.mesh,
        &out.semantic_surfaces,
        semantic_getter,
        mesh_context);
}

bool load_fcb_feature_mesh(
    ZfcbReaderHandle fcb,
    std::string_view feature_id,
    Surface_mesh& sm,
    double offset_x,
    double offset_y,
    double offset_z,
    std::string* out_b3_val3dity_lod22) {
    LoadedSolidMesh loaded;
    if (!load_fcb_feature_mesh(
            fcb, feature_id, loaded, offset_x, offset_y, offset_z, out_b3_val3dity_lod22)) {
        return false;
    }
    sm = std::move(loaded.mesh);
    return true;
}

ogr::LinearRing make_offset_polygon(
    const ogr::LinearRing& polygon,
    double offset_x,
    double offset_y,
    double offset_z) {
    ogr::LinearRing offset_polygon;
    offset_polygon.reserve(polygon.size());
    for (const auto& pt : polygon) {
        offset_polygon.push_back({pt[0] - offset_x, pt[1] - offset_y, pt[2] - offset_z});
    }
    for (const auto& hole : polygon.interior_rings()) {
        std::vector<std::array<double, 3>> offset_hole;
        offset_hole.reserve(hole.size());
        for (const auto& pt : hole) {
            offset_hole.push_back({pt[0] - offset_x, pt[1] - offset_y, pt[2] - offset_z});
        }
        offset_polygon.interior_rings().push_back(std::move(offset_hole));
    }
    return offset_polygon;
}
