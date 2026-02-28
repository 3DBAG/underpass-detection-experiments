#ifndef ZFCB_H
#define ZFCB_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct Reader* ZfcbReaderHandle;

// Object type values match FlatCityBuf schema enum order.
typedef enum {
    ZFCB_OBJECT_BRIDGE = 0,
    ZFCB_OBJECT_BRIDGE_PART = 1,
    ZFCB_OBJECT_BRIDGE_INSTALLATION = 2,
    ZFCB_OBJECT_BRIDGE_CONSTRUCTIVE_ELEMENT = 3,
    ZFCB_OBJECT_BRIDGE_ROOM = 4,
    ZFCB_OBJECT_BRIDGE_FURNITURE = 5,
    ZFCB_OBJECT_BUILDING = 6,
    ZFCB_OBJECT_BUILDING_PART = 7,
    ZFCB_OBJECT_BUILDING_INSTALLATION = 8,
    ZFCB_OBJECT_BUILDING_CONSTRUCTIVE_ELEMENT = 9,
    ZFCB_OBJECT_BUILDING_FURNITURE = 10,
    ZFCB_OBJECT_BUILDING_STOREY = 11,
    ZFCB_OBJECT_BUILDING_ROOM = 12,
    ZFCB_OBJECT_BUILDING_UNIT = 13,
    ZFCB_OBJECT_CITY_FURNITURE = 14,
    ZFCB_OBJECT_CITY_OBJECT_GROUP = 15,
    ZFCB_OBJECT_GENERIC_CITY_OBJECT = 16,
    ZFCB_OBJECT_LAND_USE = 17,
    ZFCB_OBJECT_OTHER_CONSTRUCTION = 18,
    ZFCB_OBJECT_PLANT_COVER = 19,
    ZFCB_OBJECT_SOLITARY_VEGETATION_OBJECT = 20,
    ZFCB_OBJECT_TIN_RELIEF = 21,
    ZFCB_OBJECT_ROAD = 22,
    ZFCB_OBJECT_RAILWAY = 23,
    ZFCB_OBJECT_WATERWAY = 24,
    ZFCB_OBJECT_TRANSPORT_SQUARE = 25,
    ZFCB_OBJECT_TUNNEL = 26,
    ZFCB_OBJECT_TUNNEL_PART = 27,
    ZFCB_OBJECT_TUNNEL_INSTALLATION = 28,
    ZFCB_OBJECT_TUNNEL_CONSTRUCTIVE_ELEMENT = 29,
    ZFCB_OBJECT_TUNNEL_HOLLOW_SPACE = 30,
    ZFCB_OBJECT_TUNNEL_FURNITURE = 31,
    ZFCB_OBJECT_WATER_BODY = 32,
    ZFCB_OBJECT_EXTENSION_OBJECT = 33
} ZfcbObjectType;

// Geometry type values match FlatCityBuf schema enum order.
typedef enum {
    ZFCB_GEOMETRY_MULTI_POINT = 0,
    ZFCB_GEOMETRY_MULTI_LINE_STRING = 1,
    ZFCB_GEOMETRY_MULTI_SURFACE = 2,
    ZFCB_GEOMETRY_COMPOSITE_SURFACE = 3,
    ZFCB_GEOMETRY_SOLID = 4,
    ZFCB_GEOMETRY_MULTI_SOLID = 5,
    ZFCB_GEOMETRY_COMPOSITE_SOLID = 6,
    ZFCB_GEOMETRY_GEOMETRY_INSTANCE = 7
} ZfcbGeometryType;

// Open / close streaming reader.
// Returns NULL on failure.
ZfcbReaderHandle zfcb_reader_open(const char* path);
// Open reader from an existing Unix file descriptor.
// close_on_destroy: non-zero => close(fd) in zfcb_reader_destroy, 0 => leave fd open.
ZfcbReaderHandle zfcb_reader_open_fd(int fd, int close_on_destroy);
void zfcb_reader_destroy(ZfcbReaderHandle handle);

uint64_t zfcb_feature_count(ZfcbReaderHandle handle);

// Streaming iteration.
// peek/skip/next return:
//   1 => success with data (for peek/next) or feature skipped (skip)
//   0 => end-of-file
//  -1 => error
int zfcb_peek_next_id(ZfcbReaderHandle handle, const char** out_id, size_t* out_len);
int zfcb_skip_next(ZfcbReaderHandle handle);
int zfcb_next(ZfcbReaderHandle handle);

// Current decoded feature data (valid after successful zfcb_next and until next skip/next/destroy).
int zfcb_current_feature_id(ZfcbReaderHandle handle, const char** out_id, size_t* out_len);
size_t zfcb_current_vertex_count(ZfcbReaderHandle handle);
const double* zfcb_current_vertices(ZfcbReaderHandle handle); // xyz packed, length = vertex_count * 3
size_t zfcb_current_object_count(ZfcbReaderHandle handle);

int zfcb_current_object_id(ZfcbReaderHandle handle, size_t object_index, const char** out_id, size_t* out_len);
uint8_t zfcb_current_object_type(ZfcbReaderHandle handle, size_t object_index);
size_t zfcb_current_object_geometry_count(ZfcbReaderHandle handle, size_t object_index);

uint8_t zfcb_current_geometry_type(ZfcbReaderHandle handle, size_t object_index, size_t geometry_index);
int zfcb_current_geometry_lod(
    ZfcbReaderHandle handle,
    size_t object_index,
    size_t geometry_index,
    const char** out_lod,
    size_t* out_len);
size_t zfcb_current_geometry_surface_count(ZfcbReaderHandle handle, size_t object_index, size_t geometry_index);
size_t zfcb_current_geometry_string_count(ZfcbReaderHandle handle, size_t object_index, size_t geometry_index);
size_t zfcb_current_geometry_boundary_count(ZfcbReaderHandle handle, size_t object_index, size_t geometry_index);
const uint32_t* zfcb_current_geometry_surfaces(ZfcbReaderHandle handle, size_t object_index, size_t geometry_index);
const uint32_t* zfcb_current_geometry_strings(ZfcbReaderHandle handle, size_t object_index, size_t geometry_index);
const uint32_t* zfcb_current_geometry_boundaries(ZfcbReaderHandle handle, size_t object_index, size_t geometry_index);

// Writer API – open from an existing reader (copies preamble), write features.
typedef struct Writer* ZfcbWriterHandle;

ZfcbWriterHandle zfcb_writer_open_from_reader(ZfcbReaderHandle reader_handle, const char* output_path);
// Unix fd variant of zfcb_writer_open_from_reader.
// close_on_destroy: non-zero => close(fd) in zfcb_writer_destroy, 0 => leave fd open.
ZfcbWriterHandle zfcb_writer_open_from_reader_fd(
    ZfcbReaderHandle reader_handle,
    int fd,
    int close_on_destroy);
// Like zfcb_writer_open_from_reader but strips the spatial and attribute indexes
// from the output header. Use this when features may be modified (changed byte lengths
// would invalidate the original index offsets).
ZfcbWriterHandle zfcb_writer_open_from_reader_no_index(ZfcbReaderHandle reader_handle, const char* output_path);
// Unix fd variant of zfcb_writer_open_from_reader_no_index.
// close_on_destroy: non-zero => close(fd) in zfcb_writer_destroy, 0 => leave fd open.
ZfcbWriterHandle zfcb_writer_open_from_reader_no_index_fd(
    ZfcbReaderHandle reader_handle,
    int fd,
    int close_on_destroy);
// Open a new FlatCityBuf writer from scratch (no spatial/attribute indexes).
// feature_count in the header is patched automatically on close.
ZfcbWriterHandle zfcb_writer_open_new_no_index(
    const char* output_path,
    double scale_x,
    double scale_y,
    double scale_z,
    double translate_x,
    double translate_y,
    double translate_z);
void zfcb_writer_destroy(ZfcbWriterHandle writer_handle);

// Write the pending (peeked but not yet decoded) raw feature bytes. Returns 1/0/-1.
int zfcb_writer_write_pending_raw(ZfcbReaderHandle reader_handle, ZfcbWriterHandle writer_handle);

// Write the current (decoded) feature's raw bytes. Returns 0/-1.
int zfcb_writer_write_current_raw(ZfcbReaderHandle reader_handle, ZfcbWriterHandle writer_handle);

// Write a full size-prefixed feature payload (4-byte length prefix + feature bytes).
// Returns 0 on success, -1 on error.
int zfcb_writer_write_feature_raw_bytes(
    ZfcbWriterHandle writer_handle,
    const uint8_t* feature_bytes,
    size_t feature_len);

// Write the current feature with its LoD 2.2 Solid geometry replaced by a triangle mesh.
// vertices_xyz_world: flat xyz array (length = vertex_count * 3) in world coordinates.
// triangle_indices: flat triangle index list (length = triangle_index_count, must be multiple of 3).
// semantic_types: per-triangle SemanticSurfaceType enum values (FCB geometry.fbs ordering:
//   0=RoofSurface, 1=GroundSurface, 2=WallSurface, 4=OuterCeilingSurface).
// semantic_types_count: must equal triangle_index_count / 3.
// Returns 0 on success, -1 on error.
// NOTE: This changes the feature byte length, invalidating spatial/attribute indexes.
// Use zfcb_writer_open_from_reader_no_index to create the writer.
int zfcb_writer_write_current_replaced_lod22(
    ZfcbReaderHandle reader_handle,
    ZfcbWriterHandle writer_handle,
    const char* feature_id,
    size_t feature_id_len,
    const double* vertices_xyz_world,
    size_t vertex_count,
    const uint32_t* triangle_indices,
    size_t triangle_index_count,
    const uint8_t* semantic_types,
    size_t semantic_types_count);

#ifdef __cplusplus
}
#endif

#endif // ZFCB_H
