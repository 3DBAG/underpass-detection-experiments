#include <iostream>
#include <format>
#include <cmath>
#include <chrono>
#include <exception>
#include <limits>
#include <string_view>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <cstdio>
#if defined(_WIN32)
#include <io.h>
#endif

#include <manifold/manifold.h>

#include <CGAL/Polygon_mesh_processing/triangulate_faces.h>

#include "BooleanOps.h"
#include "BooleanOpsManifold.h"
#include "MeshConversion.h"
#include "ModelLoaders.h"
#include "PolygonalOutput.h"
#include "zityjson.h"
#include "zfcb.h"
#include "OGRVectorReader.h"
#include "PolygonExtruder.h"
#include "RerunVisualization.h"

using Clock = std::chrono::steady_clock;

static int stdin_fd() {
#if defined(_WIN32)
    return _fileno(stdin);
#else
    return fileno(stdin);
#endif
}

static int stdout_fd() {
#if defined(_WIN32)
    return _fileno(stdout);
#else
    return fileno(stdout);
#endif
}

// SemanticSurfaceType enum values matching FCB geometry.fbs
namespace SemanticSurfaceType {
    constexpr uint8_t RoofSurface = 0;
    constexpr uint8_t GroundSurface = 1;
    constexpr uint8_t WallSurface = 2;
    constexpr uint8_t OuterCeilingSurface = 4;
}

enum class SourceAttributeTarget : uint8_t {
    None = 0,
    Feature = 1,
    Parent = 2,
};

struct SourceAttributeBuffers {
    std::vector<const char*> names;
    std::vector<size_t> name_lens;
    std::vector<uint8_t> types;
    std::vector<int64_t> integer_values;
    std::vector<double> real_values;
    std::vector<const char*> string_values;
    std::vector<size_t> string_value_lens;

    size_t size() const { return names.size(); }
};

static SourceAttributeBuffers source_attribute_buffers(
    const std::vector<ogr::VectorReader::PolygonFeature>& polygon_features,
    const std::vector<size_t>& matched_indices) {
    SourceAttributeBuffers out;
    std::unordered_set<std::string> emitted;
    for (size_t feature_idx : matched_indices) {
        if (feature_idx >= polygon_features.size()) {
            continue;
        }
        for (const auto& attribute : polygon_features[feature_idx].source_attributes) {
            if (attribute.name.empty() || emitted.contains(attribute.name)) {
                continue;
            }
            emitted.insert(attribute.name);
            out.names.push_back(attribute.name.c_str());
            out.name_lens.push_back(attribute.name.size());
            out.types.push_back(static_cast<uint8_t>(attribute.type));
            out.integer_values.push_back(attribute.integer_value);
            out.real_values.push_back(attribute.real_value);
            out.string_values.push_back(attribute.string_value.c_str());
            out.string_value_lens.push_back(attribute.string_value.size());
        }
    }
    return out;
}

// Classify each triangle by face normal orientation and Z-position.
// ground_z: building ground level (local coords).
// underpass_z: underpass ceiling height (local coords).
static constexpr double kNullUnderpassHeightAboveGround = 2.5;
static std::vector<uint8_t> classify_triangle_semantics(
    const manifold::MeshGL& mesh,
    double ground_z,
    double underpass_z,
    double nz_threshold = 0.3,
    double z_tolerance = 0.5)
{
    size_t num_prop = mesh.numProp;
    size_t tri_count = mesh.triVerts.size() / 3;
    std::vector<uint8_t> result(tri_count);

    for (size_t t = 0; t < tri_count; ++t) {
        uint32_t i0 = mesh.triVerts[t * 3 + 0];
        uint32_t i1 = mesh.triVerts[t * 3 + 1];
        uint32_t i2 = mesh.triVerts[t * 3 + 2];

        float x0 = mesh.vertProperties[i0 * num_prop + 0];
        float y0 = mesh.vertProperties[i0 * num_prop + 1];
        float z0 = mesh.vertProperties[i0 * num_prop + 2];
        float x1 = mesh.vertProperties[i1 * num_prop + 0];
        float y1 = mesh.vertProperties[i1 * num_prop + 1];
        float z1 = mesh.vertProperties[i1 * num_prop + 2];
        float x2 = mesh.vertProperties[i2 * num_prop + 0];
        float y2 = mesh.vertProperties[i2 * num_prop + 1];
        float z2 = mesh.vertProperties[i2 * num_prop + 2];

        // Cross product of edges e1 = v1-v0, e2 = v2-v0.
        float ex1 = x1 - x0, ey1 = y1 - y0, ez1 = z1 - z0;
        float ex2 = x2 - x0, ey2 = y2 - y0, ez2 = z2 - z0;
        float nx = ey1 * ez2 - ez1 * ey2;
        float ny = ez1 * ex2 - ex1 * ez2;
        float nz = ex1 * ey2 - ey1 * ex2;

        float len = std::sqrt(nx * nx + ny * ny + nz * nz);
        if (len > 0.0f) nz /= len;

        if (std::abs(nz) < nz_threshold) {
            result[t] = SemanticSurfaceType::WallSurface;
        } else if (nz > 0.0f) {
            result[t] = SemanticSurfaceType::RoofSurface;
        } else {
            // Downward-facing: distinguish ground from outer ceiling by first vertex Z.
            if (std::abs(static_cast<double>(z0) - ground_z) < z_tolerance) {
                result[t] = SemanticSurfaceType::GroundSurface;
            } else {
                result[t] = SemanticSurfaceType::OuterCeilingSurface;
            }
        }
    }
    return result;
}

struct FeatureCarveResult {
    bool any_succeeded = false;
    manifold::MeshGL result_meshgl;
    Surface_mesh result_surface_mesh;
    bool has_polygonal_result = false;
    double house_min_z = std::numeric_limits<double>::quiet_NaN();
    double underpass_z = 0.0;
    size_t processed_count = 0;
    size_t skipped_count = 0;
};

static FeatureCarveResult carve_underpasses_for_feature(
    const LoadedSolidMesh& house_data,
    std::string_view model_feature_id,
    const std::vector<ogr::VectorReader::PolygonFeature>& polygon_features,
    const std::vector<size_t>& matched_indices,
    std::vector<bool>& seen_feature,
    BooleanMethod method,
    bool ignore_holes,
    double global_offset_x,
    double global_offset_y,
    double global_offset_z,
    std::string_view val3dity_suffix,
    std::chrono::duration<double, std::milli>& ds_conversion_ms,
    std::chrono::duration<double, std::milli>& intersection_ms) {
    FeatureCarveResult result;
    result.house_min_z = mesh_min_z(house_data.mesh);
    if (!std::isfinite(result.house_min_z)) {
        for (size_t feature_idx : matched_indices) {
            seen_feature[feature_idx] = true;
            const auto& feature = polygon_features[feature_idx];
            std::cerr << std::format("Skipping feature {} (id='{}'): could not determine house min z{}",
                                     feature_idx, feature.id, val3dity_suffix) << std::endl;
            ++result.skipped_count;
        }
        return result;
    }

    std::vector<Surface_mesh> underpass_meshes;
    underpass_meshes.reserve(matched_indices.size());
    size_t merged_feature_count = 0;
    for (size_t feature_idx : matched_indices) {
        seen_feature[feature_idx] = true;
        const auto& feature = polygon_features[feature_idx];

        auto t_conversion_start = Clock::now();
        double roof_height = (feature.has_absolute_elevation && std::isfinite(feature.absolute_elevation))
            ? feature.absolute_elevation
            : result.house_min_z + kNullUnderpassHeightAboveGround;
        auto offset_polygon = make_offset_polygon(
            feature.polygon,
            global_offset_x,
            global_offset_y,
            global_offset_z);
        Surface_mesh underpass_sm;
        try {
            underpass_sm = extrusion::extrude_polygon(
                offset_polygon, result.house_min_z - 0.1, roof_height, ignore_holes);
        } catch (const std::exception& e) {
            auto t_conversion_end = Clock::now();
            ds_conversion_ms += t_conversion_end - t_conversion_start;
            std::cerr << std::format("Skipping feature {} (id='{}'): underpass extrusion failed ({}){}",
                                     feature_idx, feature.id, e.what(), val3dity_suffix) << std::endl;
            ++result.skipped_count;
            continue;
        } catch (...) {
            auto t_conversion_end = Clock::now();
            ds_conversion_ms += t_conversion_end - t_conversion_start;
            std::cerr << std::format("Skipping feature {} (id='{}'): underpass extrusion failed (unknown exception){}",
                                     feature_idx, feature.id, val3dity_suffix) << std::endl;
            ++result.skipped_count;
            continue;
        }
        auto t_conversion_end = Clock::now();
        ds_conversion_ms += t_conversion_end - t_conversion_start;

        if (underpass_sm.number_of_faces() == 0) {
            std::cerr << std::format("Skipping feature {} (id='{}'): underpass extrusion produced empty mesh{}",
                                     feature_idx, feature.id, val3dity_suffix) << std::endl;
            ++result.skipped_count;
            continue;
        }

        underpass_meshes.push_back(std::move(underpass_sm));
        result.underpass_z = roof_height - global_offset_z;
        ++merged_feature_count;
    }

    if (underpass_meshes.empty()) {
        return result;
    }

    BooleanOpTiming timing;
    bool success = true;
    Surface_mesh house_sm = house_data.mesh;
    if (method == BooleanMethod::Manifold) {
        ManifoldBooleanError error = ManifoldBooleanError::None;
        success = manifold_boolean_difference(
            house_sm, underpass_meshes, result.result_meshgl, &timing, &error);
        if (!success) {
            if (error == ManifoldBooleanError::EmptyInputMesh) {
                std::cerr << std::format("Skipping {} merged features (id='{}'): empty mesh for manifold boolean{}",
                                         merged_feature_count, std::string(model_feature_id), val3dity_suffix) << std::endl;
            } else if (error == ManifoldBooleanError::InvalidInput) {
                std::cerr << std::format("Skipping {} merged features (id='{}'): invalid manifold input{}",
                                         merged_feature_count, std::string(model_feature_id), val3dity_suffix) << std::endl;
            } else {
                std::cerr << std::format("Skipping {} merged features (id='{}'): manifold boolean failed{}",
                                         merged_feature_count, std::string(model_feature_id), val3dity_suffix) << std::endl;
            }
        }
    } else if (method == BooleanMethod::CgalNef) {
        Surface_mesh result_sm = nef_boolean_difference(house_sm, underpass_meshes, &timing);
        auto t_conversion_start_local = Clock::now();
        result.result_surface_mesh = std::move(result_sm);
        result.has_polygonal_result = true;
        auto t_conversion_end_local = Clock::now();
        ds_conversion_ms += t_conversion_end_local - t_conversion_start_local;
#ifdef ENABLE_GEOGRAM
    } else if (method == BooleanMethod::Geogram) {
        Surface_mesh result_sm = geogram_boolean_difference(house_sm, underpass_meshes, &timing);
        auto t_conversion_start_local = Clock::now();
        result.result_meshgl = surface_mesh_to_meshgl(result_sm, false);
        auto t_conversion_end_local = Clock::now();
        ds_conversion_ms += t_conversion_end_local - t_conversion_start_local;
#endif
    } else {
        Surface_mesh result_sm = corefine_boolean_difference(house_sm, underpass_meshes, &timing);
        auto t_conversion_start_local = Clock::now();
        result.result_surface_mesh = std::move(result_sm);
        result.has_polygonal_result = true;
        auto t_conversion_end_local = Clock::now();
        ds_conversion_ms += t_conversion_end_local - t_conversion_start_local;
    }
    intersection_ms += timing.boolean_ms;
    ds_conversion_ms += timing.conversion_ms;

    const bool has_output_mesh =
        result.has_polygonal_result ? result.result_surface_mesh.number_of_faces() > 0
                                    : result.result_meshgl.NumTri() > 0;
    if (success && has_output_mesh) {
        result.any_succeeded = true;
        result.processed_count += merged_feature_count;
    } else {
        if (success) {
            std::cerr << std::format("Skipping {} merged features (id='{}'): boolean produced empty mesh{}",
                                     merged_feature_count, std::string(model_feature_id), val3dity_suffix) << std::endl;
        }
        result.skipped_count += merged_feature_count;
    }

    return result;
}

static std::vector<double> meshgl_to_world_vertices(
    const manifold::MeshGL& meshgl,
    double offset_x,
    double offset_y,
    double offset_z) {
    size_t num_verts = meshgl.NumVert();
    size_t num_prop = meshgl.numProp;
    std::vector<double> world_verts(num_verts * 3);
    for (size_t v = 0; v < num_verts; ++v) {
        world_verts[v * 3 + 0] = static_cast<double>(meshgl.vertProperties[v * num_prop + 0]) + offset_x;
        world_verts[v * 3 + 1] = static_cast<double>(meshgl.vertProperties[v * num_prop + 1]) + offset_y;
        world_verts[v * 3 + 2] = static_cast<double>(meshgl.vertProperties[v * num_prop + 2]) + offset_z;
    }
    return world_verts;
}

struct StreamProcessingContext {
    const std::vector<ogr::VectorReader::PolygonFeature>& polygon_features;
    std::unordered_map<std::string_view, std::vector<size_t>>& features_by_exact_id;
    std::vector<bool>& seen_feature;
    BooleanMethod method;
    SourceAttributeTarget source_attribute_target;
    bool ignore_holes;
    bool& global_offset_set;
    double& global_offset_x;
    double& global_offset_y;
    double& global_offset_z;
    size_t& processed_count;
    size_t& skipped_count;
    std::chrono::duration<double, std::milli>& ds_conversion_ms;
    std::chrono::duration<double, std::milli>& intersection_ms;
    std::chrono::duration<double, std::milli>& output_write_ms;
    std::chrono::duration<double, std::milli>& output_write_changed_ms;
    std::chrono::duration<double, std::milli>& output_write_passthrough_ms;
    std::chrono::duration<double, std::milli>& model_stream_read_ms;
    std::ostream& log_out;
};

struct FcbStreamBackend {
    ZfcbReaderHandle reader = nullptr;
    ZfcbWriterHandle writer = nullptr;
    bool output_to_stdout = false;
    const char* output_path = nullptr;

    const char* stream_label() const { return "FlatCityBuf"; }
    const char* output_label() const { return "FCB"; }
    const char* output_destination() const { return output_to_stdout ? "stdout" : output_path; }
    const char* missing_current_error() const { return "FlatCityBuf stream error: decoded feature unavailable"; }

    bool open_writer() {
        if (output_to_stdout) {
            writer = zfcb_writer_open_from_reader_no_index_fd(reader, stdout_fd(), 0);
        } else {
            writer = zfcb_writer_open_from_reader_no_index(reader, output_path);
        }
        return writer != nullptr;
    }

    void close_writer() {
        if (writer != nullptr) {
            zfcb_writer_destroy(writer);
            writer = nullptr;
        }
    }

    int peek_next_id(const char** out_id, size_t* out_len) {
        return zfcb_peek_next_id(reader, out_id, out_len);
    }

    int next() {
        return zfcb_next(reader);
    }

    bool ensure_current_available() const {
        return true;
    }

    int write_pending_raw() {
        return zfcb_writer_write_pending_raw(reader, writer);
    }

    int write_current_raw() {
        return zfcb_writer_write_current_raw(reader, writer);
    }

    int write_current_replaced_lod22(
        const char* feature_id_ptr,
        size_t feature_id_len,
        const double* vertices_xyz_world,
        size_t vertex_count,
        const uint32_t* triangle_indices,
        size_t triangle_index_count,
        const uint8_t* semantic_types,
        size_t semantic_types_count,
        const SourceAttributeBuffers& source_attributes,
        SourceAttributeTarget source_attribute_target) {
        if (source_attribute_target != SourceAttributeTarget::None) {
            return zfcb_writer_write_current_replaced_lod22_with_attributes(
                reader, writer,
                feature_id_ptr, feature_id_len,
                vertices_xyz_world, vertex_count,
                triangle_indices, triangle_index_count,
                semantic_types, semantic_types_count,
                source_attributes.names.data(),
                source_attributes.name_lens.data(),
                source_attributes.types.data(),
                source_attributes.integer_values.data(),
                source_attributes.real_values.data(),
                source_attributes.string_values.data(),
                source_attributes.string_value_lens.data(),
                source_attributes.size(),
                static_cast<uint8_t>(source_attribute_target));
        }
        return zfcb_writer_write_current_replaced_lod22(
            reader, writer,
            feature_id_ptr, feature_id_len,
            vertices_xyz_world, vertex_count,
            triangle_indices, triangle_index_count,
            semantic_types, semantic_types_count);
    }

    int write_current_replaced_lod22_polygonal(
        const char* feature_id_ptr,
        size_t feature_id_len,
        const double* vertices_xyz_world,
        size_t vertex_count,
        const uint32_t* surface_ring_counts,
        size_t surface_count,
        const uint32_t* ring_vertex_counts,
        size_t ring_count,
        const uint32_t* boundary_indices,
        size_t boundary_index_count,
        const uint8_t* surface_semantic_types,
        size_t surface_semantic_types_count,
        const SourceAttributeBuffers& source_attributes,
        SourceAttributeTarget source_attribute_target) {
        if (source_attribute_target != SourceAttributeTarget::None) {
            return zfcb_writer_write_current_replaced_lod22_polygonal_with_attributes(
                reader, writer,
                feature_id_ptr, feature_id_len,
                vertices_xyz_world, vertex_count,
                surface_ring_counts, surface_count,
                ring_vertex_counts, ring_count,
                boundary_indices, boundary_index_count,
                surface_semantic_types, surface_semantic_types_count,
                source_attributes.names.data(),
                source_attributes.name_lens.data(),
                source_attributes.types.data(),
                source_attributes.integer_values.data(),
                source_attributes.real_values.data(),
                source_attributes.string_values.data(),
                source_attributes.string_value_lens.data(),
                source_attributes.size(),
                static_cast<uint8_t>(source_attribute_target));
        }
        return zfcb_writer_write_current_replaced_lod22_polygonal(
            reader, writer,
            feature_id_ptr, feature_id_len,
            vertices_xyz_world, vertex_count,
            surface_ring_counts, surface_count,
            ring_vertex_counts, ring_count,
            boundary_indices, boundary_index_count,
            surface_semantic_types, surface_semantic_types_count);
    }

    bool prepare_current_feature(
        std::string_view next_id,
        const std::vector<size_t>& matched_indices,
        const std::vector<ogr::VectorReader::PolygonFeature>& polygon_features,
        std::vector<bool>& seen_feature,
        size_t& skipped_count,
        bool& global_offset_set,
        double& global_offset_x,
        double& global_offset_y,
        double& global_offset_z,
        std::chrono::duration<double, std::milli>& output_write_ms,
        std::chrono::duration<double, std::milli>& output_write_passthrough_ms) {
        (void)next_id;
        if (global_offset_set) {
            return true;
        }
        const double* verts = zfcb_current_vertices(reader);
        size_t vert_count = zfcb_current_vertex_count(reader);
        if (verts == nullptr || vert_count == 0) {
            for (size_t feature_idx : matched_indices) {
                seen_feature[feature_idx] = true;
                const auto& feature = polygon_features[feature_idx];
                std::cerr << std::format("Skipping ogr feature {} (id='{}'): invalid FlatCityBuf vertices",
                                         feature_idx, feature.id) << std::endl;
                ++skipped_count;
            }
            auto t_output_write_start_local = Clock::now();
            zfcb_writer_write_current_raw(reader, writer);
            auto t_output_write_end_local = Clock::now();
            auto d_output_write = t_output_write_end_local - t_output_write_start_local;
            output_write_ms += d_output_write;
            output_write_passthrough_ms += d_output_write;
            return false;
        }

        global_offset_x = verts[0];
        global_offset_y = verts[1];
        global_offset_z = verts[2];
        global_offset_set = true;
        return true;
    }

    bool load_current_house_mesh(
        std::string_view next_id,
        LoadedSolidMesh& house,
        double offset_x,
        double offset_y,
        double offset_z,
        std::string& val3dity_suffix) {
        std::string fcb_b3_val3dity_lod22;
        bool loaded = load_fcb_feature_mesh(
            reader, next_id, house, offset_x, offset_y, offset_z, &fcb_b3_val3dity_lod22);
        val3dity_suffix = fcb_b3_val3dity_lod22.empty()
            ? std::string{}
            : std::format(" (b3_val3dity_lod22='{}')", fcb_b3_val3dity_lod22);
        return loaded;
    }
};

struct CjseqStreamBackend {
    CityJSONSeqReaderHandle reader = nullptr;
    CityJSONSeqWriterHandle writer = nullptr;
    const char* output_path = nullptr;

    const char* stream_label() const { return "CityJSONSeq"; }
    const char* output_label() const { return "CityJSONSeq"; }
    const char* output_destination() const { return output_path; }
    const char* missing_current_error() const { return "CityJSONSeq stream error: decoded feature unavailable"; }

    bool open_writer() {
        writer = cityjsonseq_writer_open_from_reader(reader, output_path);
        return writer != nullptr;
    }

    void close_writer() {
        if (writer != nullptr) {
            cityjsonseq_writer_destroy(writer);
            writer = nullptr;
        }
    }

    int peek_next_id(const char** out_id, size_t* out_len) {
        return cityjsonseq_peek_next_id(reader, out_id, out_len);
    }

    int next() {
        return cityjsonseq_next(reader);
    }

    bool ensure_current_available() const {
        return cityjsonseq_current_cityjson(reader) != nullptr;
    }

    int write_pending_raw() {
        return cityjsonseq_writer_write_pending_raw(reader, writer);
    }

    int write_current_raw() {
        return cityjsonseq_writer_write_current_raw(reader, writer);
    }

    int write_current_replaced_lod22(
        const char* feature_id_ptr,
        size_t feature_id_len,
        const double* vertices_xyz_world,
        size_t vertex_count,
        const uint32_t* triangle_indices,
        size_t triangle_index_count,
        const uint8_t* semantic_types,
        size_t semantic_types_count,
        const SourceAttributeBuffers& source_attributes,
        SourceAttributeTarget source_attribute_target) {
        if (source_attribute_target == SourceAttributeTarget::None) {
            return cityjsonseq_writer_write_current_replaced_lod22(
                reader, writer,
                feature_id_ptr, feature_id_len,
                vertices_xyz_world, vertex_count,
                triangle_indices, triangle_index_count,
                semantic_types, semantic_types_count);
        }
        return cityjsonseq_writer_write_current_replaced_lod22_with_attributes(
            reader, writer,
            feature_id_ptr, feature_id_len,
            vertices_xyz_world, vertex_count,
            triangle_indices, triangle_index_count,
            semantic_types, semantic_types_count,
            source_attributes.names.data(),
            source_attributes.name_lens.data(),
            source_attributes.types.data(),
            source_attributes.integer_values.data(),
            source_attributes.real_values.data(),
            source_attributes.string_values.data(),
            source_attributes.string_value_lens.data(),
            source_attributes.size(),
            static_cast<uint8_t>(source_attribute_target));
    }

    int write_current_replaced_lod22_polygonal(
        const char* feature_id_ptr,
        size_t feature_id_len,
        const double* vertices_xyz_world,
        size_t vertex_count,
        const uint32_t* surface_ring_counts,
        size_t surface_count,
        const uint32_t* ring_vertex_counts,
        size_t ring_count,
        const uint32_t* boundary_indices,
        size_t boundary_index_count,
        const uint8_t* surface_semantic_types,
        size_t surface_semantic_types_count,
        const SourceAttributeBuffers& source_attributes,
        SourceAttributeTarget source_attribute_target) {
        if (source_attribute_target == SourceAttributeTarget::None) {
            return cityjsonseq_writer_write_current_replaced_lod22_polygonal(
                reader, writer,
                feature_id_ptr, feature_id_len,
                vertices_xyz_world, vertex_count,
                surface_ring_counts, surface_count,
                ring_vertex_counts, ring_count,
                boundary_indices, boundary_index_count,
                surface_semantic_types, surface_semantic_types_count);
        }
        return cityjsonseq_writer_write_current_replaced_lod22_polygonal_with_attributes(
            reader, writer,
            feature_id_ptr, feature_id_len,
            vertices_xyz_world, vertex_count,
            surface_ring_counts, surface_count,
            ring_vertex_counts, ring_count,
            boundary_indices, boundary_index_count,
            surface_semantic_types, surface_semantic_types_count,
            source_attributes.names.data(),
            source_attributes.name_lens.data(),
            source_attributes.types.data(),
            source_attributes.integer_values.data(),
            source_attributes.real_values.data(),
            source_attributes.string_values.data(),
            source_attributes.string_value_lens.data(),
            source_attributes.size(),
            static_cast<uint8_t>(source_attribute_target));
    }

    bool prepare_current_feature(
        std::string_view next_id,
        const std::vector<size_t>& matched_indices,
        const std::vector<ogr::VectorReader::PolygonFeature>& polygon_features,
        std::vector<bool>& seen_feature,
        size_t& skipped_count,
        bool& global_offset_set,
        double& global_offset_x,
        double& global_offset_y,
        double& global_offset_z,
        std::chrono::duration<double, std::milli>& output_write_ms,
        std::chrono::duration<double, std::milli>& output_write_passthrough_ms) {
        (void)next_id;
        (void)matched_indices;
        (void)polygon_features;
        (void)seen_feature;
        (void)skipped_count;
        (void)output_write_ms;
        (void)output_write_passthrough_ms;
        global_offset_set = true;
        global_offset_x = 0.0;
        global_offset_y = 0.0;
        global_offset_z = 0.0;
        return true;
    }

    bool load_current_house_mesh(
        std::string_view next_id,
        LoadedSolidMesh& house,
        double offset_x,
        double offset_y,
        double offset_z,
        std::string& val3dity_suffix) {
        CityJSONHandle current_feature_cj = cityjsonseq_current_cityjson(reader);
        if (current_feature_cj == nullptr) {
            return false;
        }
        ssize_t object_index = resolve_cityjson_object_index(current_feature_cj, next_id);
        if (object_index < 0) {
            return false;
        }
        val3dity_suffix.clear();
        return load_cityjson_object_mesh(
            current_feature_cj,
            static_cast<size_t>(object_index),
            house,
            offset_x,
            offset_y,
            offset_z);
    }
};

template <typename Backend>
static bool process_stream_features(Backend& backend, StreamProcessingContext& ctx) {
    auto t_output_write_start = Clock::now();
    bool writer_opened = backend.open_writer();
    auto t_output_write_end = Clock::now();
    ctx.output_write_ms += t_output_write_end - t_output_write_start;
    if (!writer_opened) {
        std::cerr << "Failed to open " << backend.output_label()
                  << " writer: " << backend.output_destination() << std::endl;
        return false;
    }
    ctx.log_out << std::format("{} output: {}", backend.output_label(), backend.output_destination()) << std::endl;

    bool stream_error = false;

    while (true) {
        const char* peek_id_ptr = nullptr;
        size_t peek_id_len = 0;
        auto t_stream_read_start = Clock::now();
        int peek_result = backend.peek_next_id(&peek_id_ptr, &peek_id_len);
        auto t_stream_read_end = Clock::now();
        ctx.model_stream_read_ms += t_stream_read_end - t_stream_read_start;
        if (peek_result < 0) {
            std::cerr << backend.stream_label() << " stream error while peeking next feature id" << std::endl;
            stream_error = true;
            break;
        }
        if (peek_result == 0) {
            break;
        }

        std::string_view next_id(peek_id_ptr, peek_id_len);
        auto exact_hint_it = ctx.features_by_exact_id.find(next_id);
        if (exact_hint_it == ctx.features_by_exact_id.end()) {
            auto t_output_write_start_local = Clock::now();
            int write_result = backend.write_pending_raw();
            auto t_output_write_end_local = Clock::now();
            auto d_output_write = t_output_write_end_local - t_output_write_start_local;
            ctx.output_write_ms += d_output_write;
            ctx.output_write_passthrough_ms += d_output_write;
            if (write_result < 0) {
                std::cerr << backend.stream_label() << " stream error while writing pass-through feature" << std::endl;
                stream_error = true;
                break;
            }
            if (write_result == 0) {
                break;
            }
            continue;
        }

        auto t_stream_read_start_next = Clock::now();
        int next_result = backend.next();
        auto t_stream_read_end_next = Clock::now();
        ctx.model_stream_read_ms += t_stream_read_end_next - t_stream_read_start_next;
        if (next_result < 0) {
            std::cerr << backend.stream_label() << " stream error while decoding feature" << std::endl;
            stream_error = true;
            break;
        }
        if (next_result == 0) {
            break;
        }
        if (!backend.ensure_current_available()) {
            std::cerr << backend.missing_current_error() << std::endl;
            stream_error = true;
            break;
        }

        const auto& matched_indices = exact_hint_it->second;
        if (!backend.prepare_current_feature(
                next_id,
                matched_indices,
                ctx.polygon_features,
                ctx.seen_feature,
                ctx.skipped_count,
                ctx.global_offset_set,
                ctx.global_offset_x,
                ctx.global_offset_y,
                ctx.global_offset_z,
                ctx.output_write_ms,
                ctx.output_write_passthrough_ms)) {
            continue;
        }

        LoadedSolidMesh house;
        bool house_mesh_loaded = false;
        std::string house_mesh_error;
        std::string val3dity_suffix;
        auto t_stream_read_start_mesh = Clock::now();
        try {
            house_mesh_loaded = backend.load_current_house_mesh(
                next_id,
                house,
                ctx.global_offset_x,
                ctx.global_offset_y,
                ctx.global_offset_z,
                val3dity_suffix);
        } catch (const std::exception& e) {
            house_mesh_error = e.what();
            house_mesh_loaded = false;
        } catch (...) {
            house_mesh_error = "unknown exception";
            house_mesh_loaded = false;
        }
        if (!house_mesh_loaded) {
            auto t_stream_read_end_mesh = Clock::now();
            ctx.model_stream_read_ms += t_stream_read_end_mesh - t_stream_read_start_mesh;
            for (size_t feature_idx : matched_indices) {
                ctx.seen_feature[feature_idx] = true;
                const auto& feature = ctx.polygon_features[feature_idx];
                if (house_mesh_error.empty()) {
                    std::cerr << std::format("Skipping feature {} (id='{}'): could not build {} mesh{}",
                                             feature_idx, feature.id, backend.stream_label(), val3dity_suffix) << std::endl;
                } else {
                    std::cerr << std::format("Skipping feature {} (id='{}'): failed to build {} mesh ({}){}",
                                             feature_idx, feature.id, backend.stream_label(), house_mesh_error, val3dity_suffix) << std::endl;
                }
                ++ctx.skipped_count;
            }
            auto t_output_write_start_local = Clock::now();
            backend.write_current_raw();
            auto t_output_write_end_local = Clock::now();
            auto d_output_write = t_output_write_end_local - t_output_write_start_local;
            ctx.output_write_ms += d_output_write;
            ctx.output_write_passthrough_ms += d_output_write;
            continue;
        }
        auto t_stream_read_end_mesh = Clock::now();
        ctx.model_stream_read_ms += t_stream_read_end_mesh - t_stream_read_start_mesh;

        auto carve_result = carve_underpasses_for_feature(
            house,
            next_id,
            ctx.polygon_features,
            matched_indices,
            ctx.seen_feature,
            ctx.method,
            ctx.ignore_holes,
            ctx.global_offset_x,
            ctx.global_offset_y,
            ctx.global_offset_z,
            val3dity_suffix,
            ctx.ds_conversion_ms,
            ctx.intersection_ms);
        ctx.processed_count += carve_result.processed_count;
        ctx.skipped_count += carve_result.skipped_count;

        if (carve_result.any_succeeded) {
            std::string feature_id_str(next_id);
            SourceAttributeBuffers source_attributes =
                ctx.source_attribute_target == SourceAttributeTarget::None
                    ? SourceAttributeBuffers{}
                    : source_attribute_buffers(ctx.polygon_features, matched_indices);
            auto t_output_write_start_local = Clock::now();
            int write_result = -1;
            if (ctx.method == BooleanMethod::Manifold && carve_result.result_meshgl.NumTri() > 0) {
                PolygonalOutput polygonal_output;
                if (build_polygonal_output_from_manifold_meshgl(
                        carve_result.result_meshgl,
                        house,
                        carve_result.house_min_z,
                        carve_result.underpass_z,
                        ctx.global_offset_x,
                        ctx.global_offset_y,
                        ctx.global_offset_z,
                        polygonal_output)) {
                    write_result = backend.write_current_replaced_lod22_polygonal(
                        feature_id_str.c_str(), feature_id_str.size(),
                        polygonal_output.vertices_xyz_world.data(), polygonal_output.vertices_xyz_world.size() / 3,
                        polygonal_output.surface_ring_counts.data(), polygonal_output.surface_ring_counts.size(),
                        polygonal_output.ring_vertex_counts.data(), polygonal_output.ring_vertex_counts.size(),
                        polygonal_output.boundary_indices.data(), polygonal_output.boundary_indices.size(),
                        polygonal_output.surface_semantic_types.data(), polygonal_output.surface_semantic_types.size(),
                        source_attributes,
                        ctx.source_attribute_target);
                }
            } else if (carve_result.has_polygonal_result) {
                PolygonalOutput polygonal_output;
                if (build_polygonal_output_from_cgal_mesh(
                        carve_result.result_surface_mesh,
                        house,
                        carve_result.house_min_z,
                        carve_result.underpass_z,
                        ctx.global_offset_x,
                        ctx.global_offset_y,
                        ctx.global_offset_z,
                        polygonal_output)) {
                    write_result = backend.write_current_replaced_lod22_polygonal(
                        feature_id_str.c_str(), feature_id_str.size(),
                        polygonal_output.vertices_xyz_world.data(), polygonal_output.vertices_xyz_world.size() / 3,
                        polygonal_output.surface_ring_counts.data(), polygonal_output.surface_ring_counts.size(),
                        polygonal_output.ring_vertex_counts.data(), polygonal_output.ring_vertex_counts.size(),
                        polygonal_output.boundary_indices.data(), polygonal_output.boundary_indices.size(),
                        polygonal_output.surface_semantic_types.data(), polygonal_output.surface_semantic_types.size(),
                        source_attributes,
                        ctx.source_attribute_target);
                }

                if (write_result < 0) {
                    Surface_mesh triangulated_mesh = carve_result.result_surface_mesh;
                    CGAL::Polygon_mesh_processing::triangulate_faces(triangulated_mesh);
                    carve_result.result_meshgl = surface_mesh_to_meshgl(triangulated_mesh, false);
                }
            }

            if (write_result < 0 && carve_result.result_meshgl.NumTri() > 0) {
                auto world_verts = meshgl_to_world_vertices(
                    carve_result.result_meshgl,
                    ctx.global_offset_x,
                    ctx.global_offset_y,
                    ctx.global_offset_z);
                auto semantics = classify_triangle_semantics(
                    carve_result.result_meshgl, carve_result.house_min_z, carve_result.underpass_z);
                write_result = backend.write_current_replaced_lod22(
                    feature_id_str.c_str(), feature_id_str.size(),
                    world_verts.data(), world_verts.size() / 3,
                    carve_result.result_meshgl.triVerts.data(), carve_result.result_meshgl.triVerts.size(),
                    semantics.data(), semantics.size(),
                    source_attributes,
                    ctx.source_attribute_target);
            }
            auto t_output_write_end_local = Clock::now();
            auto d_output_write = t_output_write_end_local - t_output_write_start_local;
            ctx.output_write_ms += d_output_write;
            ctx.output_write_changed_ms += d_output_write;
            if (write_result < 0) {
                std::cerr << std::format("Warning: failed to write modified feature '{}' to {}, writing raw instead",
                                         feature_id_str, backend.output_label()) << std::endl;
                auto t_fallback_write_start = Clock::now();
                backend.write_current_raw();
                auto t_fallback_write_end = Clock::now();
                auto d_output_write_fallback = t_fallback_write_end - t_fallback_write_start;
                ctx.output_write_ms += d_output_write_fallback;
                ctx.output_write_passthrough_ms += d_output_write_fallback;
            }
        } else {
            auto t_output_write_start_local = Clock::now();
            backend.write_current_raw();
            auto t_output_write_end_local = Clock::now();
            auto d_output_write = t_output_write_end_local - t_output_write_start_local;
            ctx.output_write_ms += d_output_write;
            ctx.output_write_passthrough_ms += d_output_write;
        }
    }

    auto t_output_write_start_local = Clock::now();
    backend.close_writer();
    auto t_output_write_end_local = Clock::now();
    ctx.output_write_ms += t_output_write_end_local - t_output_write_start_local;

    return !stream_error;
}

int main(int argc, char* argv[]) {
    auto t_program_start = Clock::now();

    if (argc < 5) {
        std::cerr << "Usage: " << argv[0]
                  << " <ogr_source> <model_input> <model_output> <absolute_underpass_elevation_attribute> [id_attribute] [method] [copy_source_attributes]" << std::endl;
        std::cerr << "  model formats: .fcb (FlatCityBuf) or .jsonl (CityJSONSeq)" << std::endl;
        std::cerr << "  id_attribute default: identificatie" << std::endl;
        std::cerr << "  missing absolute underpass elevation falls back to 2.5 m above the local ground reference" << std::endl;
        std::cerr << "  method: pmp (default), manifold, nef"
#ifdef ENABLE_GEOGRAM
                  << ", geogram"
#endif
                  << std::endl;
        std::cerr << "  copy_source_attributes: none (default), feature, parent" << std::endl;
        std::cerr << "  use '-' as input to read FCB from stdin" << std::endl;
        std::cerr << "  use '-' as output to write FCB to stdout" << std::endl;
        std::cerr << "  CityJSONSeq stdin/stdout piping is not supported yet" << std::endl;
        return 1;
    }

    const char* ogr_source_path = argv[1];
    const char* model_path = argv[2];
    const char* output_path = argv[3];
    std::string height_attribute = argv[4];
    std::string id_attribute = argc > 5 ? argv[5] : "identificatie";
    std::string method_str = argc > 6 ? argv[6] : "pmp";
    std::string copy_source_attributes_str = argc > 7 ? argv[7] : "none";
    const bool model_from_stdin = std::string_view(model_path) == "-";
    const bool output_to_stdout = std::string_view(output_path) == "-";
    std::ostream& log_out = output_to_stdout ? static_cast<std::ostream&>(std::cerr) : static_cast<std::ostream&>(std::cout);

    BooleanMethod method = BooleanMethod::Manifold;
    if (method_str == "nef") {
        method = BooleanMethod::CgalNef;
    } else if (method_str == "pmp") {
        method = BooleanMethod::CgalPMP;
#ifdef ENABLE_GEOGRAM
    } else if (method_str == "geogram") {
        method = BooleanMethod::Geogram;
#endif
    } else if (method_str != "manifold") {
        std::cerr << "Unknown method: " << method_str << " (use manifold, nef, pmp"
#ifdef ENABLE_GEOGRAM
                  << ", geogram"
#endif
                  << ")" << std::endl;
        return 1;
    }

    SourceAttributeTarget source_attribute_target = SourceAttributeTarget::None;
    if (copy_source_attributes_str == "feature") {
        source_attribute_target = SourceAttributeTarget::Feature;
    } else if (copy_source_attributes_str == "parent") {
        source_attribute_target = SourceAttributeTarget::Parent;
    } else if (copy_source_attributes_str != "none") {
        std::cerr << "Unknown copy_source_attributes: " << copy_source_attributes_str
                  << " (use none, feature, parent)" << std::endl;
        return 1;
    }

    const bool model_is_fcb = model_from_stdin || is_fcb_path(model_path);
    const bool model_is_cityjsonseq = !model_from_stdin && is_cityjsonseq_path(model_path);
    const bool output_is_fcb = output_to_stdout || is_fcb_path(output_path);
    const bool output_is_cityjsonseq = !output_to_stdout && is_cityjsonseq_path(output_path);

    if (!model_is_fcb && !model_is_cityjsonseq) {
        std::cerr << "Unsupported input model format. Use .fcb or .jsonl" << std::endl;
        return 1;
    }
    if (model_is_cityjsonseq && model_from_stdin) {
        std::cerr << "CityJSONSeq stdin input is not supported yet" << std::endl;
        return 1;
    }
    if (model_is_cityjsonseq && output_to_stdout) {
        std::cerr << "CityJSONSeq stdout output is not supported yet" << std::endl;
        return 1;
    }
    if (model_is_fcb && !output_is_fcb) {
        std::cerr << "FCB input currently requires FCB output" << std::endl;
        return 1;
    }
    if (model_is_cityjsonseq && !output_is_cityjsonseq) {
        std::cerr << "CityJSONSeq input currently requires CityJSONSeq (.jsonl) output" << std::endl;
        return 1;
    }

    ZfcbReaderHandle fcb = nullptr;
    CityJSONSeqReaderHandle cjseq_reader = nullptr;

    auto t_model_read_start = Clock::now();
    if (model_is_fcb) {
        if (model_from_stdin) {
            fcb = zfcb_reader_open_fd(stdin_fd(), 0);
        } else {
            fcb = zfcb_reader_open(model_path);
        }
        if (fcb == nullptr) {
            std::cerr << "Failed to open FlatCityBuf stream: " << (model_from_stdin ? "stdin" : model_path) << std::endl;
            return 1;
        }
    } else {
        cjseq_reader = cityjsonseq_reader_open(model_path);
        if (cjseq_reader == nullptr) {
            std::cerr << "Failed to open CityJSONSeq stream: " << model_path << std::endl;
            return 1;
        }
    }
    auto t_model_read_end = Clock::now();

    double model_extent_min[3] = {0.0, 0.0, 0.0};
    double model_extent_max[3] = {0.0, 0.0, 0.0};
    int extent_result = model_is_fcb
        ? zfcb_reader_header_geographical_extent(fcb, model_extent_min, model_extent_max)
        : cityjsonseq_reader_header_geographical_extent(cjseq_reader, model_extent_min, model_extent_max);
    if (extent_result < 0) {
        if (model_is_fcb) {
            std::cerr << "Failed to read FlatCityBuf header geographical_extent; cannot apply OGR extent filter" << std::endl;
            zfcb_reader_destroy(fcb);
        } else {
            std::cerr << "Failed to read CityJSONSeq header geographical_extent; cannot apply OGR extent filter" << std::endl;
            cityjsonseq_reader_destroy(cjseq_reader);
        }
        return 1;
    }

    ogr::VectorReader reader;
    if (extent_result == 1) {
        reader.set_spatial_filter_rect(
            model_extent_min[0], model_extent_min[1], model_extent_max[0], model_extent_max[1]);
    } else {
        log_out << "Warning: model header has no geographical extent; reading OGR without spatial filter" << std::endl;
    }

    auto t_ogr_read_start = Clock::now();
    reader.open(ogr_source_path);
    if (extent_result == 1) {
        log_out << std::format(
            "Applied OGR spatial filter from model extent XY: [{:.3f}, {:.3f}] -> [{:.3f}, {:.3f}]",
            model_extent_min[0], model_extent_min[1], model_extent_max[0], model_extent_max[1]) << std::endl;
    }
    auto polygon_features = reader.read_polygon_features(id_attribute, height_attribute);
    auto t_ogr_read_end = Clock::now();
    log_out << std::format("Read {} OGR features", polygon_features.size()) << std::endl;
    log_out << std::format(
        "Model input: {} ({})",
        model_from_stdin ? "stdin" : model_path,
        model_is_fcb ? "FlatCityBuf stream" : "CityJSONSeq stream") << std::endl;

    bool ignore_holes = false;
    size_t processed_count = 0;
    size_t skipped_count = 0;
    bool global_offset_set = false;
    double global_offset_x = 0.0;
    double global_offset_y = 0.0;
    double global_offset_z = 0.0;
    std::chrono::duration<double, std::milli> ds_conversion_ms{0.0};
    std::chrono::duration<double, std::milli> intersection_ms{0.0};
    std::chrono::duration<double, std::milli> output_write_ms{0.0};
    std::chrono::duration<double, std::milli> output_write_changed_ms{0.0};
    std::chrono::duration<double, std::milli> output_write_passthrough_ms{0.0};
    std::chrono::duration<double, std::milli> model_stream_read_ms{0.0};

    std::unordered_map<std::string_view, std::vector<size_t>> features_by_exact_id;
    std::vector<size_t> valid_feature_indices;
    std::vector<bool> seen_feature(polygon_features.size(), false);
    for (size_t i = 0; i < polygon_features.size(); ++i) {
        const auto& feature = polygon_features[i];
        if (feature.id.empty()) {
            std::cerr << std::format("Skipping feature {}: empty id attribute '{}'", i, id_attribute) << std::endl;
            ++skipped_count;
            continue;
        }
        std::string_view exact_id(feature.id);
        features_by_exact_id[exact_id].push_back(i);
        valid_feature_indices.push_back(i);
    }

    StreamProcessingContext stream_ctx{
        .polygon_features = polygon_features,
        .features_by_exact_id = features_by_exact_id,
        .seen_feature = seen_feature,
        .method = method,
        .source_attribute_target = source_attribute_target,
        .ignore_holes = ignore_holes,
        .global_offset_set = global_offset_set,
        .global_offset_x = global_offset_x,
        .global_offset_y = global_offset_y,
        .global_offset_z = global_offset_z,
        .processed_count = processed_count,
        .skipped_count = skipped_count,
        .ds_conversion_ms = ds_conversion_ms,
        .intersection_ms = intersection_ms,
        .output_write_ms = output_write_ms,
        .output_write_changed_ms = output_write_changed_ms,
        .output_write_passthrough_ms = output_write_passthrough_ms,
        .model_stream_read_ms = model_stream_read_ms,
        .log_out = log_out,
    };

    bool stream_ok = false;
    if (model_is_fcb) {
        FcbStreamBackend backend{
            .reader = fcb,
            .writer = nullptr,
            .output_to_stdout = output_to_stdout,
            .output_path = output_path,
        };
        stream_ok = process_stream_features(backend, stream_ctx);
        if (!stream_ok) {
            zfcb_reader_destroy(fcb);
            return 1;
        }
    } else {
        CjseqStreamBackend backend{
            .reader = cjseq_reader,
            .writer = nullptr,
            .output_path = output_path,
        };
        stream_ok = process_stream_features(backend, stream_ctx);
        if (!stream_ok) {
            cityjsonseq_reader_destroy(cjseq_reader);
            return 1;
        }
    }

    for (size_t feature_idx : valid_feature_indices) {
        if (seen_feature[feature_idx]) {
            continue;
        }
        const auto& feature = polygon_features[feature_idx];
        std::cerr << std::format("Skipping feature {}: {} feature not found for id '{}'",
                                 feature_idx,
                                 model_is_fcb ? "FlatCityBuf" : "CityJSONSeq",
                                 feature.id) << std::endl;
        ++skipped_count;
    }

    if (model_is_fcb) {
        zfcb_reader_destroy(fcb);
    } else {
        cityjsonseq_reader_destroy(cjseq_reader);
    }

    log_out << std::format("Processed underpasses: {}, skipped: {}", processed_count, skipped_count) << std::endl;

    if (processed_count == 0) {
        std::cerr << std::format("Warning: no features were modified; output {} is a copy of input.",
                                 model_is_fcb ? "FCB" : "CityJSONSeq") << std::endl;
    }

    auto ogr_read_ms = std::chrono::duration<double, std::milli>(t_ogr_read_end - t_ogr_read_start).count();
    auto model_read_ms = std::chrono::duration<double, std::milli>(t_model_read_end - t_model_read_start).count() +
                         model_stream_read_ms.count();
    auto output_write_ms_value = output_write_ms.count();
    auto total_ms = std::chrono::duration<double, std::milli>(Clock::now() - t_program_start).count();
    auto accounted_ms = model_read_ms + ogr_read_ms + ds_conversion_ms.count() + intersection_ms.count() + output_write_ms_value;
    auto other_ms = total_ms - accounted_ms;
    if (other_ms < 0.0) {
        other_ms = 0.0;
    }

    log_out << "Timing profile (ms):" << std::endl;
    log_out << std::format("  model reading: {:.3f}", model_read_ms) << std::endl;
    log_out << std::format("  ogr reading: {:.3f}", ogr_read_ms) << std::endl;
    log_out << std::format("  datastructure conversion: {:.3f}", ds_conversion_ms.count()) << std::endl;
    log_out << std::format("  boolean ops: {:.3f}", intersection_ms.count()) << std::endl;
    log_out << std::format("  output writing: {:.3f}", output_write_ms_value) << std::endl;
    log_out << std::format("    changed features: {:.3f}", output_write_changed_ms.count()) << std::endl;
    log_out << std::format("    pass-through features: {:.3f}", output_write_passthrough_ms.count()) << std::endl;
    log_out << std::format("  other: {:.3f}", other_ms) << std::endl;
    log_out << std::format("  total: {:.3f}", total_ms) << std::endl;

    return 0;
}
