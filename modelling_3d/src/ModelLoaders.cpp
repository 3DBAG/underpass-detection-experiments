#include "ModelLoaders.h"

#include <string>
#include <vector>
#include <array>

#include <CGAL/Polygon_mesh_processing/triangulate_faces.h>

#include "zityjson.h"
#include "zfcb.h"

bool is_fcb_path(const std::string_view path) {
    constexpr std::string_view ext = ".fcb";
    if (path.size() < ext.size()) {
        return false;
    }
    return path.substr(path.size() - ext.size()) == ext;
}

ssize_t resolve_cityjson_object_index(CityJSONHandle cj, std::string_view feature_id) {
    // try with '-0' suffix
    std::string id(feature_id);
    std::string with_suffix(id);
    with_suffix += "-0";
    ssize_t idx = cityjson_get_object_index(cj, with_suffix.c_str());
    if (idx >= 0) {
        return idx;
    }

    // try as is
    idx = cityjson_get_object_index(cj, id.c_str());
    if (idx >= 0) {
        return idx;
    }

    // try without '-0' suffix if it already has it
    constexpr std::string_view suffix = "-0";
    if (feature_id.size() >= suffix.size() &&
        feature_id.substr(feature_id.size() - suffix.size()) == suffix) {
        std::string trimmed(feature_id.substr(0, feature_id.size() - suffix.size()));
        return cityjson_get_object_index(cj, trimmed.c_str());
    }

    return -1;
}

bool load_cityjson_object_mesh(
    CityJSONHandle cj,
    size_t object_index,
    Surface_mesh& sm,
    double offset_x,
    double offset_y,
    double offset_z) {
    size_t geom_count = cityjson_get_geometry_count(cj, object_index);
    if (geom_count == 0) {
        return false;
    }

    size_t geom_idx = geom_count - 1;
    const double* verts = cityjson_get_vertices(cj, object_index, geom_idx);
    const size_t* indices = cityjson_get_indices(cj, object_index, geom_idx);
    size_t vert_count = cityjson_get_vertex_count(cj, object_index, geom_idx);
    size_t face_count = cityjson_get_face_count(cj, object_index, geom_idx);

    if (verts == nullptr || indices == nullptr || vert_count == 0 || face_count == 0) {
        return false;
    }

    std::vector<Surface_mesh::Vertex_index> vertex_handles;
    vertex_handles.reserve(vert_count);
    for (size_t v = 0; v < vert_count; ++v) {
        vertex_handles.push_back(sm.add_vertex(K::Point_3(
            verts[v * 3] - offset_x,
            verts[v * 3 + 1] - offset_y,
            verts[v * 3 + 2] - offset_z)));
    }

    for (size_t f = 0; f < face_count; ++f) {
        size_t start = 0;
        size_t count = 0;
        uint8_t face_type = 0;
        if (cityjson_get_face_info(cj, object_index, geom_idx, f, &start, &count, &face_type) != 0) {
            continue;
        }
        std::vector<Surface_mesh::Vertex_index> face_vertices;
        face_vertices.reserve(count);
        for (size_t i = 0; i < count; ++i) {
            face_vertices.push_back(vertex_handles[indices[start + i]]);
        }
        sm.add_face(face_vertices);
    }

    CGAL::Polygon_mesh_processing::triangulate_faces(sm);
    return sm.number_of_faces() > 0;
}

static bool append_fcb_geometry_faces(
    const std::vector<Surface_mesh::Vertex_index>& vertex_handles,
    size_t vertex_count,
    const uint32_t* surfaces,
    size_t surface_count,
    const uint32_t* strings,
    size_t string_count,
    const uint32_t* boundaries,
    size_t boundary_count,
    Surface_mesh& sm) {
    if (surfaces == nullptr || strings == nullptr || boundaries == nullptr) {
        return false;
    }
    if (surface_count == 0 || string_count == 0 || boundary_count == 0) {
        return false;
    }

    size_t ring_cursor = 0;
    size_t boundary_cursor = 0;
    bool added_faces = false;

    for (size_t s = 0; s < surface_count; ++s) {
        if (ring_cursor >= string_count || boundary_cursor >= boundary_count) {
            break;
        }

        size_t rings_in_surface = static_cast<size_t>(surfaces[s]);
        if (rings_in_surface == 0) {
            continue;
        }

        size_t outer_ring_size = static_cast<size_t>(strings[ring_cursor]);
        if (outer_ring_size >= 3 && boundary_cursor + outer_ring_size <= boundary_count) {
            std::vector<Surface_mesh::Vertex_index> face_vertices;
            face_vertices.reserve(outer_ring_size);

            bool valid_face = true;
            for (size_t i = 0; i < outer_ring_size; ++i) {
                uint32_t idx = boundaries[boundary_cursor + i];
                if (idx >= vertex_count) {
                    valid_face = false;
                    break;
                }
                face_vertices.push_back(vertex_handles[idx]);
            }

            if (valid_face) {
                sm.add_face(face_vertices);
                added_faces = true;
            }
        }

        for (size_t r = 0; r < rings_in_surface && ring_cursor < string_count; ++r, ++ring_cursor) {
            size_t ring_size = static_cast<size_t>(strings[ring_cursor]);
            if (boundary_cursor + ring_size > boundary_count) {
                boundary_cursor = boundary_count;
                break;
            }
            boundary_cursor += ring_size;
        }
    }

    return added_faces;
}

bool load_fcb_feature_mesh(
    ZfcbReaderHandle fcb,
    std::string_view feature_id,
    Surface_mesh& sm,
    double offset_x,
    double offset_y,
    double offset_z) {
    size_t vertex_count = zfcb_current_vertex_count(fcb);
    const double* vertices = zfcb_current_vertices(fcb);
    if (vertices == nullptr || vertex_count == 0) {
        return false;
    }

    std::vector<Surface_mesh::Vertex_index> vertex_handles;
    vertex_handles.reserve(vertex_count);
    for (size_t v = 0; v < vertex_count; ++v) {
        vertex_handles.push_back(sm.add_vertex(K::Point_3(
            vertices[v * 3] - offset_x,
            vertices[v * 3 + 1] - offset_y,
            vertices[v * 3 + 2] - offset_z)));
    }

    std::string object_id = std::string(feature_id) + "-0";
    ssize_t object_index = -1;
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
            break;
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

    bool added_faces = append_fcb_geometry_faces(
        vertex_handles,
        vertex_count,
        surfaces,
        surface_count,
        strings,
        string_count,
        boundaries,
        boundary_count,
        sm);
    if (!added_faces) {
        return false;
    }

    CGAL::Polygon_mesh_processing::triangulate_faces(sm);
    return sm.number_of_faces() > 0;
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
