#include <iostream>
#include <format>
#include <cmath>
#include <chrono>
#include <string_view>
#include <unordered_map>
#include <vector>

#include <manifold/manifold.h>
#include <manifold/meshIO.h>

#include <CGAL/Polygon_mesh_processing/triangulate_faces.h>

#include "BooleanOps.h"
#include "MeshConversion.h"
#include "ModelLoaders.h"
#include "zityjson.h"
#include "zfcb.h"
#include "OGRVectorReader.h"
#include "PolygonExtruder.h"
#include "RerunVisualization.h"

using Clock = std::chrono::steady_clock;

int main(int argc, char* argv[]) {
    auto t_program_start = Clock::now();

    if (argc < 4) {
        std::cerr << "Usage: " << argv[0]
                  << " <cityjson_or_fcb_file> <ogr_source> <height_attribute> [id_attribute] [method] [output_fcb]" << std::endl;
        std::cerr << "  id_attribute default: identificatie" << std::endl;
        std::cerr << "  method: manifold (default), nef, pmp" << std::endl;
        std::cerr << "  output_fcb: path for FCB output (only used when input is .fcb)" << std::endl;
        return 1;
    }

    const char* model_path = argv[1];
    const char* ogr_source_path = argv[2];
    std::string height_attribute = argv[3];
    std::string id_attribute = argc > 4 ? argv[4] : "identificatie";
    std::string method_str = argc > 5 ? argv[5] : "manifold";
    bool undo_offset = false;
    const char* output_fcb_path = argc > 6 ? argv[6] : nullptr;

    BooleanMethod method = BooleanMethod::Manifold;
    if (method_str == "nef") {
        method = BooleanMethod::CgalNef;
    } else if (method_str == "pmp") {
        method = BooleanMethod::CgalPMP;
    } else if (method_str != "manifold") {
        std::cerr << "Unknown method: " << method_str << " (use manifold, nef, or pmp)" << std::endl;
        return 1;
    }

    const bool use_fcb_input = is_fcb_path(model_path);

    ogr::VectorReader reader;
    auto t_ogr_read_start = Clock::now();
    reader.open(ogr_source_path);
    auto polygon_features = reader.read_polygon_features(id_attribute, height_attribute);
    auto t_ogr_read_end = Clock::now();
    std::cout << std::format("Read {} polygon features", polygon_features.size()) << std::endl;
    std::cout << std::format("Model input: {} ({})",
                             model_path,
                             use_fcb_input ? "FlatCityBuf stream" : "CityJSON") << std::endl;

    CityJSONHandle cj = nullptr;
    ZfcbReaderHandle fcb = nullptr;
    auto t_model_read_start = Clock::now();
    if (use_fcb_input) {
        fcb = zfcb_reader_open(model_path);
        if (fcb == nullptr) {
            std::cerr << "Failed to open FlatCityBuf stream: " << model_path << std::endl;
            return 1;
        }
    } else {
        cj = cityjson_create();
        if (cj == nullptr) {
            std::cerr << "Failed to create CityJSON handle" << std::endl;
            return 1;
        }
        int json_load_result = cityjson_load(cj, model_path);
        if (json_load_result != 0) {
            std::cerr << "Failed to load CityJSON: " << model_path << std::endl;
            cityjson_destroy(cj);
            return 1;
        }
    }
    auto t_model_read_end = Clock::now();

    bool ignore_holes = false;
    manifold::MeshGL combined_result_meshgl;
    size_t processed_count = 0;
    size_t skipped_count = 0;
    bool global_offset_set = false;
    double global_offset_x = 0.0;
    double global_offset_y = 0.0;
    double global_offset_z = 0.0;
    std::chrono::duration<double, std::milli> ds_conversion_ms{0.0};
    std::chrono::duration<double, std::milli> intersection_ms{0.0};

    if (!use_fcb_input) {
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

            ssize_t idx = resolve_cityjson_object_index(cj, feature.id);
            if (idx < 0) {
                std::cerr << std::format("Skipping feature {}: CityJSON object not found for id '{}'",
                                         i, feature.id) << std::endl;
                ++skipped_count;
                continue;
            }

            if (!global_offset_set) {
                size_t obj_idx = static_cast<size_t>(idx);
                size_t geom_count = cityjson_get_geometry_count(cj, obj_idx);
                if (geom_count == 0) {
                    std::cerr << std::format("Skipping feature {} (id='{}'): no CityJSON geometry", i, feature.id)
                              << std::endl;
                    ++skipped_count;
                    continue;
                }
                // get the last geometry index. We're Assuming it is the lod2.2 geometry here.
                size_t geom_idx = geom_count - 1;
                const double* verts = cityjson_get_vertices(cj, obj_idx, geom_idx);
                size_t vert_count = cityjson_get_vertex_count(cj, obj_idx, geom_idx);
                if (verts == nullptr || vert_count == 0) {
                    std::cerr << std::format("Skipping feature {} (id='{}'): invalid CityJSON vertices", i, feature.id)
                              << std::endl;
                    ++skipped_count;
                    continue;
                }
                global_offset_x = verts[0];
                global_offset_y = verts[1];
                global_offset_z = verts[2];
                global_offset_set = true;
                std::cout << std::format("Global offset set to ({}, {}, {})",
                                         global_offset_x, global_offset_y, global_offset_z) << std::endl;
            }

            auto t_conversion_start = Clock::now();
            Surface_mesh house_sm;
            if (!load_cityjson_object_mesh(cj, static_cast<size_t>(idx), house_sm,
                                           global_offset_x, global_offset_y, global_offset_z)) {
                std::cerr << std::format("Skipping feature {} (id='{}'): could not build CityJSON mesh", i, feature.id)
                          << std::endl;
                ++skipped_count;
                continue;
            }

            const double house_min_z_local = mesh_min_z(house_sm);
            if (!std::isfinite(house_min_z_local)) {
                std::cerr << std::format("Skipping feature {} (id='{}'): could not determine house min z", i, feature.id)
                          << std::endl;
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
                                             i, feature.id) << std::endl;
                    ++skipped_count;
                    continue;
                }

                manifold::Manifold house(house_meshgl);
                manifold::Manifold underpass(underpass_meshgl);
                if (house.Status() != manifold::Manifold::Error::NoError ||
                    underpass.Status() != manifold::Manifold::Error::NoError) {
                    std::cerr << std::format("Skipping feature {} (id='{}'): invalid manifold input", i, feature.id)
                              << std::endl;
                    ++skipped_count;
                    continue;
                }

                auto result = house - underpass;
                if (result.Status() != manifold::Manifold::Error::NoError) {
                    std::cerr << std::format("Skipping feature {} (id='{}'): manifold boolean failed", i, feature.id)
                              << std::endl;
                    ++skipped_count;
                    continue;
                }
                result_meshgl = result.GetMeshGL();
            } else if (method == BooleanMethod::CgalNef) {
                Surface_mesh result_sm = nef_boolean_difference(house_sm, underpass_sm);
                CGAL::Polygon_mesh_processing::triangulate_faces(result_sm);
                result_meshgl = surface_mesh_to_meshgl(result_sm, false);
            } else {
                Surface_mesh result_sm = corefine_boolean_difference(house_sm, underpass_sm);
                CGAL::Polygon_mesh_processing::triangulate_faces(result_sm);
                result_meshgl = surface_mesh_to_meshgl(result_sm, false);
            }
            auto t_intersection_end = Clock::now();
            intersection_ms += t_intersection_end - t_intersection_start;

            if (result_meshgl.NumTri() == 0) {
                std::cerr << std::format("Skipping feature {} (id='{}'): boolean produced empty mesh", i, feature.id)
                          << std::endl;
                ++skipped_count;
                continue;
            }

            append_meshgl(combined_result_meshgl, result_meshgl);
            ++processed_count;
        }
    } else {
        // FCB streaming mode: read features, process matching ones, write all to output.
        ZfcbWriterHandle fcb_writer = nullptr;
        if (output_fcb_path != nullptr) {
            fcb_writer = zfcb_writer_open_from_reader_no_index(fcb, output_fcb_path);
            if (fcb_writer == nullptr) {
                std::cerr << "Failed to open FCB writer: " << output_fcb_path << std::endl;
                zfcb_reader_destroy(fcb);
                return 1;
            }
            std::cout << std::format("FCB output: {}", output_fcb_path) << std::endl;
        }

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
            int peek_result = zfcb_peek_next_id(fcb, &peek_id_ptr, &peek_id_len);
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
                // Non-matching feature: pass through raw to output.
                if (fcb_writer != nullptr) {
                    int write_result = zfcb_writer_write_pending_raw(fcb, fcb_writer);
                    if (write_result < 0) {
                        std::cerr << "FlatCityBuf stream error while writing pass-through feature" << std::endl;
                        stream_error = true;
                        break;
                    }
                    if (write_result == 0) {
                        break;
                    }
                } else {
                    int skip_result = zfcb_skip_next(fcb);
                    if (skip_result < 0) {
                        std::cerr << "FlatCityBuf stream error while skipping feature" << std::endl;
                        stream_error = true;
                        break;
                    }
                    if (skip_result == 0) {
                        break;
                    }
                }
                continue;
            }

            int next_result = zfcb_next(fcb);
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
                    if (fcb_writer != nullptr) {
                        zfcb_writer_write_current_raw(fcb, fcb_writer);
                    }
                    continue;
                }
                global_offset_x = verts[0];
                global_offset_y = verts[1];
                global_offset_z = verts[2];
                global_offset_set = true;
                std::cout << std::format("Global offset set to ({}, {}, {})",
                                         global_offset_x, global_offset_y, global_offset_z) << std::endl;
            }

            Surface_mesh house_sm;
            if (!load_fcb_feature_mesh(fcb, next_id, house_sm, global_offset_x, global_offset_y, global_offset_z)) {
                for (size_t feature_idx : matched_indices) {
                    seen_feature[feature_idx] = true;
                    const auto& feature = polygon_features[feature_idx];
                    std::cerr << std::format("Skipping feature {} (id='{}'): could not build FlatCityBuf mesh",
                                             feature_idx, feature.id) << std::endl;
                    ++skipped_count;
                }
                // Write unmodified feature to output.
                if (fcb_writer != nullptr) {
                    zfcb_writer_write_current_raw(fcb, fcb_writer);
                }
                continue;
            }

            // Track whether any polygon feature succeeded for this FCB feature.
            bool any_succeeded = false;
            manifold::MeshGL last_result_meshgl;

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
                } else {
                    Surface_mesh result_sm = corefine_boolean_difference(house_sm, underpass_sm);
                    CGAL::Polygon_mesh_processing::triangulate_faces(result_sm);
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

                append_meshgl(combined_result_meshgl, result_meshgl);
                last_result_meshgl = std::move(result_meshgl);
                any_succeeded = true;
                ++processed_count;
            }

            // Write the feature to FCB output.
            if (fcb_writer != nullptr) {
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

                    std::string feature_id_str(next_id);
                    int write_result = zfcb_writer_write_current_replaced_lod22(
                        fcb, fcb_writer,
                        feature_id_str.c_str(), feature_id_str.size(),
                        world_verts.data(), num_verts,
                        last_result_meshgl.triVerts.data(), last_result_meshgl.triVerts.size());
                    if (write_result < 0) {
                        std::cerr << std::format("Warning: failed to write modified feature '{}' to FCB, writing raw instead",
                                                 feature_id_str) << std::endl;
                        zfcb_writer_write_current_raw(fcb, fcb_writer);
                    }
                } else {
                    // No successful boolean: write original feature.
                    zfcb_writer_write_current_raw(fcb, fcb_writer);
                }
            }
        }

        if (fcb_writer != nullptr) {
            zfcb_writer_destroy(fcb_writer);
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
    }

    if (use_fcb_input) {
        zfcb_reader_destroy(fcb);
    } else {
        cityjson_destroy(cj);
    }

    std::cout << std::format("Processed features: {}, skipped: {}", processed_count, skipped_count) << std::endl;

    auto t_output_write_start = Clock::now();
    if (use_fcb_input && output_fcb_path != nullptr) {
        // FCB output was already written during streaming.
        if (processed_count == 0) {
            std::cerr << "Warning: no features were modified; output FCB is a copy of input." << std::endl;
        }
    } else {
        if (processed_count == 0 || combined_result_meshgl.NumTri() == 0) {
            std::cerr << "No meshes processed successfully; no output written." << std::endl;
            return 1;
        }

        std::cout << std::format("Final mesh - triangles: {}, vertices: {}",
                                 combined_result_meshgl.NumTri(), combined_result_meshgl.NumVert()) << std::endl;

        if (undo_offset && global_offset_set) {
            apply_meshgl_offset(combined_result_meshgl, global_offset_x, global_offset_y, global_offset_z);
        }

        manifold::ExportMesh("house_with_underpass.ply", combined_result_meshgl, {});
    }
    auto t_output_write_end = Clock::now();

    auto ogr_read_ms = std::chrono::duration<double, std::milli>(t_ogr_read_end - t_ogr_read_start).count();
    auto model_read_ms = std::chrono::duration<double, std::milli>(t_model_read_end - t_model_read_start).count();
    auto output_write_ms = std::chrono::duration<double, std::milli>(t_output_write_end - t_output_write_start).count();
    auto total_ms = std::chrono::duration<double, std::milli>(t_output_write_end - t_program_start).count();

    std::cout << "Timing profile (ms):" << std::endl;
    std::cout << std::format("  model reading: {:.3f}", model_read_ms) << std::endl;
    std::cout << std::format("  ogr reading: {:.3f}", ogr_read_ms) << std::endl;
    std::cout << std::format("  datastructure conversion: {:.3f}", ds_conversion_ms.count()) << std::endl;
    std::cout << std::format("  intersecting: {:.3f}", intersection_ms.count()) << std::endl;
    std::cout << std::format("  output writing: {:.3f}", output_write_ms) << std::endl;
    std::cout << std::format("  total: {:.3f}", total_ms) << std::endl;

    return 0;
}
