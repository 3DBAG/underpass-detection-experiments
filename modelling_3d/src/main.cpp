#include <iostream>
#include <format>
#include <cmath>
#include <chrono>
#include <string_view>
#include <unordered_map>
#include <vector>
#include <cstdio>
#if defined(_WIN32)
#include <io.h>
#endif

#include <manifold/manifold.h>
#include <manifold/meshIO.h>

#include <CGAL/Polygon_mesh_processing/triangulate_faces.h>

#include "BooleanOps.h"
#include "MeshConversion.h"
#include "ModelLoaders.h"
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

// Classify each triangle by face normal orientation and Z-position.
// ground_z: building ground level (local coords).
// underpass_z: underpass ceiling height (local coords).
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

int main(int argc, char* argv[]) {
    auto t_program_start = Clock::now();

    if (argc < 5) {
        std::cerr << "Usage: " << argv[0]
                  << " <ogr_source> <fcb_input-> <fcb_output-> <height_attribute> [id_attribute] [method]" << std::endl;
        std::cerr << "  id_attribute default: identificatie" << std::endl;
        std::cerr << "  method: pmp (default), manifold, nef, geogram" << std::endl;
        std::cerr << "  use '-' as input to read FCB from stdin" << std::endl;
        std::cerr << "  use '-' as output to write FCB to stdout" << std::endl;
        return 1;
    }

    const char* ogr_source_path = argv[1];
    const char* model_path = argv[2];
    const char* output_path = argv[3];
    std::string height_attribute = argv[4];
    std::string id_attribute = argc > 5 ? argv[5] : "identificatie";
    std::string method_str = argc > 6 ? argv[6] : "pmp";
    const bool model_from_stdin = std::string_view(model_path) == "-";
    const bool output_to_stdout = std::string_view(output_path) == "-";
    std::ostream& log_out = output_to_stdout ? static_cast<std::ostream&>(std::cerr) : static_cast<std::ostream&>(std::cout);

    BooleanMethod method = BooleanMethod::Manifold;
    if (method_str == "nef") {
        method = BooleanMethod::CgalNef;
    } else if (method_str == "pmp") {
        method = BooleanMethod::CgalPMP;
    } else if (method_str == "geogram") {
        method = BooleanMethod::Geogram;
    } else if (method_str != "manifold") {
        std::cerr << "Unknown method: " << method_str << " (use manifold, nef, pmp, or geogram)" << std::endl;
        return 1;
    }

    ogr::VectorReader reader;
    auto t_ogr_read_start = Clock::now();
    reader.open(ogr_source_path);
    auto polygon_features = reader.read_polygon_features(id_attribute, height_attribute);
    auto t_ogr_read_end = Clock::now();
    log_out << std::format("Read {} OGR features", polygon_features.size()) << std::endl;
    log_out << std::format("Model input: {} (FlatCityBuf stream)", model_from_stdin ? "stdin" : model_path) << std::endl;

    ZfcbReaderHandle fcb = nullptr;
    auto t_model_read_start = Clock::now();
    if (model_from_stdin) {
        fcb = zfcb_reader_open_fd(stdin_fd(), 0);
    } else {
        fcb = zfcb_reader_open(model_path);
    }
    if (fcb == nullptr) {
        std::cerr << "Failed to open FlatCityBuf stream: " << (model_from_stdin ? "stdin" : model_path) << std::endl;
        return 1;
    }
    auto t_model_read_end = Clock::now();

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
    std::chrono::duration<double, std::milli> output_write_fcb_changed_ms{0.0};
    std::chrono::duration<double, std::milli> output_write_fcb_passthrough_ms{0.0};
    std::chrono::duration<double, std::milli> fcb_stream_read_ms{0.0};

    // FCB streaming mode: read features, process matching ones, write all to output.
    ZfcbWriterHandle fcb_writer = nullptr;
    auto t_output_write_start = Clock::now();
    if (output_to_stdout) {
        fcb_writer = zfcb_writer_open_from_reader_no_index_fd(fcb, stdout_fd(), 0);
    } else {
        fcb_writer = zfcb_writer_open_from_reader_no_index(fcb, output_path);
    }
    auto t_output_write_end = Clock::now();
    output_write_ms += t_output_write_end - t_output_write_start;
    if (fcb_writer == nullptr) {
        std::cerr << "Failed to open FCB writer: " << (output_to_stdout ? "stdout" : output_path) << std::endl;
        zfcb_reader_destroy(fcb);
        return 1;
    }
    log_out << std::format("FCB output: {}", output_to_stdout ? "stdout" : output_path) << std::endl;

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
        if (!std::isfinite(feature.extrusion_height)) {
            std::cerr << std::format("Skipping feature {} (id='{}'): invalid height attribute '{}'",
                                     i, feature.id, height_attribute) << std::endl;
            ++skipped_count;
            continue;
        }
        std::string_view exact_id(feature.id);
        features_by_exact_id[exact_id].push_back(i);
        valid_feature_indices.push_back(i);
    }

    bool stream_error = false;
    while (true) {
        const char* peek_id_ptr = nullptr;
        size_t peek_id_len = 0;
        auto t_stream_read_start = Clock::now();
        int peek_result = zfcb_peek_next_id(fcb, &peek_id_ptr, &peek_id_len);
        auto t_stream_read_end = Clock::now();
        fcb_stream_read_ms += t_stream_read_end - t_stream_read_start;
        if (peek_result < 0) {
            std::cerr << "FlatCityBuf stream error while peeking next feature id" << std::endl;
            stream_error = true;
            break;
        }
        if (peek_result == 0) {
            break;
        }

        std::string_view next_id(peek_id_ptr, peek_id_len);
        auto exact_hint_it = features_by_exact_id.find(next_id);
        if (exact_hint_it == features_by_exact_id.end()) {
            auto t_output_write_start_local = Clock::now();
            int write_result = zfcb_writer_write_pending_raw(fcb, fcb_writer);
            auto t_output_write_end_local = Clock::now();
            auto d_output_write = t_output_write_end_local - t_output_write_start_local;
            output_write_ms += d_output_write;
            output_write_fcb_passthrough_ms += d_output_write;
            if (write_result < 0) {
                std::cerr << "FlatCityBuf stream error while writing pass-through feature" << std::endl;
                stream_error = true;
                break;
            }
            if (write_result == 0) {
                break;
            }
            continue;
        }

        auto t_stream_read_start_next = Clock::now();
        int next_result = zfcb_next(fcb);
        auto t_stream_read_end_next = Clock::now();
        fcb_stream_read_ms += t_stream_read_end_next - t_stream_read_start_next;
        if (next_result < 0) {
            std::cerr << "FlatCityBuf stream error while decoding feature" << std::endl;
            stream_error = true;
            break;
        }
        if (next_result == 0) {
            break;
        }

        const auto& matched_indices = exact_hint_it->second;

        const double* verts = zfcb_current_vertices(fcb);
        size_t vert_count = zfcb_current_vertex_count(fcb);
        if (!global_offset_set) {
            if (verts == nullptr || vert_count == 0) {
                for (size_t feature_idx : matched_indices) {
                    seen_feature[feature_idx] = true;
                    const auto& feature = polygon_features[feature_idx];
                    std::cerr << std::format("Skipping ogr feature {} (id='{}'): invalid FlatCityBuf vertices",
                                             feature_idx, feature.id) << std::endl;
                    ++skipped_count;
                }
                auto t_output_write_start_local = Clock::now();
                zfcb_writer_write_current_raw(fcb, fcb_writer);
                auto t_output_write_end_local = Clock::now();
                auto d_output_write = t_output_write_end_local - t_output_write_start_local;
                output_write_ms += d_output_write;
                output_write_fcb_passthrough_ms += d_output_write;
                continue;
            }
            global_offset_x = verts[0];
            global_offset_y = verts[1];
            global_offset_z = verts[2];
            global_offset_set = true;
        }

        Surface_mesh house_sm;
        auto t_stream_read_start_mesh = Clock::now();
        if (!load_fcb_feature_mesh(fcb, next_id, house_sm, global_offset_x, global_offset_y, global_offset_z)) {
            auto t_stream_read_end_mesh = Clock::now();
            fcb_stream_read_ms += t_stream_read_end_mesh - t_stream_read_start_mesh;
            for (size_t feature_idx : matched_indices) {
                seen_feature[feature_idx] = true;
                const auto& feature = polygon_features[feature_idx];
                std::cerr << std::format("Skipping feature {} (id='{}'): could not build FlatCityBuf mesh",
                                         feature_idx, feature.id) << std::endl;
                ++skipped_count;
            }
            // Write unmodified feature to output.
            auto t_output_write_start_local = Clock::now();
            zfcb_writer_write_current_raw(fcb, fcb_writer);
            auto t_output_write_end_local = Clock::now();
            auto d_output_write = t_output_write_end_local - t_output_write_start_local;
            output_write_ms += d_output_write;
            output_write_fcb_passthrough_ms += d_output_write;
            continue;
        }
        auto t_stream_read_end_mesh = Clock::now();
        fcb_stream_read_ms += t_stream_read_end_mesh - t_stream_read_start_mesh;

        // Track whether any polygon feature succeeded for this FCB feature.
        bool any_succeeded = false;
        manifold::MeshGL last_result_meshgl;
        double last_house_min_z = 0.0;
        double last_underpass_z = 0.0;

        for (size_t feature_idx : matched_indices) {
            seen_feature[feature_idx] = true;
            const auto& feature = polygon_features[feature_idx];

            auto t_conversion_start = Clock::now();
            const double house_min_z_local = mesh_min_z(house_sm);
            if (!std::isfinite(house_min_z_local)) {
                std::cerr << std::format("Skipping feature {} (id='{}'): could not determine house min z",
                                         feature_idx, feature.id) << std::endl;
                ++skipped_count;
                continue;
            }
            auto offset_polygon = make_offset_polygon(
                feature.polygon,
                global_offset_x,
                global_offset_y,
                global_offset_z);
            auto underpass_sm = extrusion::extrude_polygon(
                offset_polygon, house_min_z_local-0.1, feature.extrusion_height + 0.1, ignore_holes);
            auto t_conversion_end = Clock::now();
            ds_conversion_ms += t_conversion_end - t_conversion_start;

            manifold::MeshGL result_meshgl;
            auto t_intersection_start = Clock::now();
            if (method == BooleanMethod::Manifold) {
                auto house_meshgl = surface_mesh_to_meshgl(house_sm, false);
                auto underpass_meshgl = surface_mesh_to_meshgl(underpass_sm, false);
                if (house_meshgl.NumTri() == 0 || underpass_meshgl.NumTri() == 0) {
                    std::cerr << std::format("Skipping feature {} (id='{}'): empty house or underpass mesh",
                                             feature_idx, feature.id) << std::endl;
                    ++skipped_count;
                    continue;
                }

                manifold::Manifold house(house_meshgl);
                manifold::Manifold underpass(underpass_meshgl);
                if (house.Status() != manifold::Manifold::Error::NoError ||
                    underpass.Status() != manifold::Manifold::Error::NoError) {
                    std::cerr << std::format("Skipping feature {} (id='{}'): invalid manifold input",
                                             feature_idx, feature.id) << std::endl;
                    ++skipped_count;
                    continue;
                }

                auto result = house - underpass;
                if (result.Status() != manifold::Manifold::Error::NoError) {
                    std::cerr << std::format("Skipping feature {} (id='{}'): manifold boolean failed",
                                             feature_idx, feature.id) << std::endl;
                    ++skipped_count;
                    continue;
                }
                result_meshgl = result.GetMeshGL();
            } else if (method == BooleanMethod::CgalNef) {
                Surface_mesh result_sm = nef_boolean_difference(house_sm, underpass_sm);
                CGAL::Polygon_mesh_processing::triangulate_faces(result_sm);
                result_meshgl = surface_mesh_to_meshgl(result_sm, false);
            } else if (method == BooleanMethod::Geogram) {
                Surface_mesh result_sm = geogram_boolean_difference(house_sm, underpass_sm);
                result_meshgl = surface_mesh_to_meshgl(result_sm, false);
            } else {
                Surface_mesh result_sm = corefine_boolean_difference(house_sm, underpass_sm);
                result_meshgl = surface_mesh_to_meshgl(result_sm, false);
            }
            auto t_intersection_end = Clock::now();
            intersection_ms += t_intersection_end - t_intersection_start;

            if (result_meshgl.NumTri() == 0) {
                std::cerr << std::format("Skipping feature {} (id='{}'): boolean produced empty mesh",
                                         feature_idx, feature.id) << std::endl;
                ++skipped_count;
                continue;
            }

            last_result_meshgl = std::move(result_meshgl);
            last_house_min_z = house_min_z_local;
            last_underpass_z = feature.extrusion_height - global_offset_z;
            any_succeeded = true;
            ++processed_count;
        }

        // Write the feature to FCB output.
        if (any_succeeded && last_result_meshgl.NumTri() > 0) {
            // Extract world-coordinate vertices from result mesh
            // (undo the global offset that was subtracted during loading).
            size_t num_verts = last_result_meshgl.NumVert();
            size_t num_prop = last_result_meshgl.numProp;
            std::vector<double> world_verts(num_verts * 3);
            for (size_t v = 0; v < num_verts; ++v) {
                world_verts[v * 3 + 0] = static_cast<double>(last_result_meshgl.vertProperties[v * num_prop + 0]) + global_offset_x;
                world_verts[v * 3 + 1] = static_cast<double>(last_result_meshgl.vertProperties[v * num_prop + 1]) + global_offset_y;
                world_verts[v * 3 + 2] = static_cast<double>(last_result_meshgl.vertProperties[v * num_prop + 2]) + global_offset_z;
            }

            auto semantics = classify_triangle_semantics(
                last_result_meshgl, last_house_min_z, last_underpass_z);

            std::string feature_id_str(next_id);
            auto t_output_write_start_local = Clock::now();
            int write_result = zfcb_writer_write_current_replaced_lod22(
                fcb, fcb_writer,
                feature_id_str.c_str(), feature_id_str.size(),
                world_verts.data(), num_verts,
                last_result_meshgl.triVerts.data(), last_result_meshgl.triVerts.size(),
                semantics.data(), semantics.size());
            auto t_output_write_end_local = Clock::now();
            auto d_output_write = t_output_write_end_local - t_output_write_start_local;
            output_write_ms += d_output_write;
            output_write_fcb_changed_ms += d_output_write;
            if (write_result < 0) {
                std::cerr << std::format("Warning: failed to write modified feature '{}' to FCB, writing raw instead",
                                         feature_id_str) << std::endl;
                auto t_fallback_write_start = Clock::now();
                zfcb_writer_write_current_raw(fcb, fcb_writer);
                auto t_fallback_write_end = Clock::now();
                auto d_output_write_fallback = t_fallback_write_end - t_fallback_write_start;
                output_write_ms += d_output_write_fallback;
                output_write_fcb_passthrough_ms += d_output_write_fallback;
            }
        } else {
            // No successful boolean: write original feature.
            auto t_output_write_start_local = Clock::now();
            zfcb_writer_write_current_raw(fcb, fcb_writer);
            auto t_output_write_end_local = Clock::now();
            auto d_output_write = t_output_write_end_local - t_output_write_start_local;
            output_write_ms += d_output_write;
            output_write_fcb_passthrough_ms += d_output_write;
        }
    }

    if (fcb_writer != nullptr) {
        auto t_output_write_start_local = Clock::now();
        zfcb_writer_destroy(fcb_writer);
        auto t_output_write_end_local = Clock::now();
        output_write_ms += t_output_write_end_local - t_output_write_start_local;
    }

    if (stream_error) {
        zfcb_reader_destroy(fcb);
        return 1;
    }

    for (size_t feature_idx : valid_feature_indices) {
        if (seen_feature[feature_idx]) {
            continue;
        }
        const auto& feature = polygon_features[feature_idx];
        std::cerr << std::format("Skipping feature {}: FlatCityBuf feature not found for id '{}'",
                                 feature_idx, feature.id) << std::endl;
        ++skipped_count;
    }

    zfcb_reader_destroy(fcb);

    log_out << std::format("Processed features: {}, skipped: {}", processed_count, skipped_count) << std::endl;

    // FCB output was already written during streaming.
    if (processed_count == 0) {
        std::cerr << "Warning: no features were modified; output FCB is a copy of input." << std::endl;
    }

    auto ogr_read_ms = std::chrono::duration<double, std::milli>(t_ogr_read_end - t_ogr_read_start).count();
    auto model_read_ms = std::chrono::duration<double, std::milli>(t_model_read_end - t_model_read_start).count() +
                         fcb_stream_read_ms.count();
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
    log_out << std::format("  intersecting: {:.3f}", intersection_ms.count()) << std::endl;
    log_out << std::format("  output writing: {:.3f}", output_write_ms_value) << std::endl;
    log_out << std::format("    changed features: {:.3f}", output_write_fcb_changed_ms.count()) << std::endl;
    log_out << std::format("    pass-through features: {:.3f}", output_write_fcb_passthrough_ms.count()) << std::endl;
    log_out << std::format("  other: {:.3f}", other_ms) << std::endl;
    log_out << std::format("  total: {:.3f}", total_ms) << std::endl;

    return 0;
}
