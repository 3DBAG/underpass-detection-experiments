#ifndef ZITYJSON_H
#define ZITYJSON_H

#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>

#ifdef __cplusplus
extern "C" {
#endif

// Opaque handle to a CityJSON instance
typedef struct CityJSON* CityJSONHandle;
typedef struct CityJSONSeqReader* CityJSONSeqReaderHandle;
typedef struct CityJSONSeqWriter* CityJSONSeqWriterHandle;

// Face type enumeration (matches Zig FaceType enum)
typedef enum {
    ZITYJSON_FACE_WALL = 0,
    ZITYJSON_FACE_FLOOR = 1,
    ZITYJSON_FACE_CEILING = 2,
    ZITYJSON_FACE_ROOF = 3,
    ZITYJSON_FACE_WINDOW = 4,
    ZITYJSON_FACE_DOOR = 5
} ZityJsonFaceType;

// Create a new CityJSON instance.
// Returns NULL on failure.
CityJSONHandle cityjson_create(void);

// Destroy a CityJSON instance and free all associated memory.
void cityjson_destroy(CityJSONHandle handle);

// Load a CityJSON file.
// Returns 0 on success, non-zero on failure.
int cityjson_load(CityJSONHandle handle, const char* path);

// Save a CityJSON file.
// Returns 0 on success, non-zero on failure.
int cityjson_save(CityJSONHandle handle, const char* path);

// ---------------------------------------------------------------------------
// Builder API — construct CityJSON from scratch
// ---------------------------------------------------------------------------

// Object type constants
#define CITYJSON_BUILDING       0
#define CITYJSON_BUILDING_PART  1

// Geometry type constants
#define CITYJSON_MULTISURFACE   0
#define CITYJSON_SOLID          1

// Add a new CityObject.
// object_type: CITYJSON_BUILDING or CITYJSON_BUILDING_PART.
// Returns the object index, or -1 on failure.
ssize_t cityjson_add_object(CityJSONHandle handle, const char* name, uint8_t object_type);

// Add a geometry to an object.
// geometry_type: CITYJSON_MULTISURFACE or CITYJSON_SOLID.
// lod: level of detail string, e.g. "1.2".
// Returns the geometry index within that object, or -1 on failure.
ssize_t cityjson_add_geometry(CityJSONHandle handle, size_t object_index, uint8_t geometry_type, const char* lod);

// Add a vertex to a geometry.
// Returns the vertex index, or -1 on failure.
ssize_t cityjson_add_vertex(CityJSONHandle handle, size_t object_index, size_t geometry_index, double x, double y, double z);

// Add a surface polygon (single ring) to a geometry.
// vertex_indices: array of ring vertex indices for the outer ring.
// num_indices: number of ring indices.
// face_type: one of ZITYJSON_FACE_WALL, ZITYJSON_FACE_FLOOR, etc.
// Returns 0 on success, -1 on failure.
int cityjson_add_face(CityJSONHandle handle, size_t object_index, size_t geometry_index, const size_t* vertex_indices, size_t num_indices, uint8_t face_type);

// Get the number of objects in the CityJSON.
size_t cityjson_object_count(CityJSONHandle handle);

// Get the name of an object by index.
// Returns NULL if index is out of bounds.
const char* cityjson_get_object_name(CityJSONHandle handle, size_t index);

// Get the index of an object by its key (name).
// Returns -1 if not found.
ssize_t cityjson_get_object_index(CityJSONHandle handle, const char* key);

// Get the geometry count for an object by index.
size_t cityjson_get_geometry_count(CityJSONHandle handle, size_t object_index);

// Get geometry type for a geometry by object and geometry index.
// Returns CITYJSON_MULTISURFACE, CITYJSON_SOLID, or 255 on invalid indices.
uint8_t cityjson_get_geometry_type(CityJSONHandle handle, size_t object_index, size_t geometry_index);

// Get geometry LoD string for a geometry by object and geometry index.
// Returns 1 on success, 0 on failure.
int cityjson_get_geometry_lod(
    CityJSONHandle handle,
    size_t object_index,
    size_t geometry_index,
    const char** out_lod,
    size_t* out_len
);

// Ringed geometry accessors, aligned with FlatCityBuf geometry vectors.
size_t cityjson_get_geometry_surface_count(CityJSONHandle handle, size_t object_index, size_t geometry_index);
size_t cityjson_get_geometry_string_count(CityJSONHandle handle, size_t object_index, size_t geometry_index);
size_t cityjson_get_geometry_boundary_count(CityJSONHandle handle, size_t object_index, size_t geometry_index);
const size_t* cityjson_get_geometry_surfaces(CityJSONHandle handle, size_t object_index, size_t geometry_index);
const size_t* cityjson_get_geometry_strings(CityJSONHandle handle, size_t object_index, size_t geometry_index);
const size_t* cityjson_get_geometry_boundaries(CityJSONHandle handle, size_t object_index, size_t geometry_index);
// Returns:
//   1 => semantic type returned
//   0 => geometry/surface exists but has no semantic assignment
//  -1 => invalid args/handle/indices
int cityjson_get_geometry_surface_semantic_type(
    CityJSONHandle handle,
    size_t object_index,
    size_t geometry_index,
    size_t surface_index,
    uint8_t* out_semantic_type
);

// Get the vertex count for a geometry by object and geometry index.
size_t cityjson_get_vertex_count(CityJSONHandle handle, size_t object_index, size_t geometry_index);

// Get the surface count for a geometry by object and geometry index.
size_t cityjson_get_face_count(CityJSONHandle handle, size_t object_index, size_t geometry_index);

// Get pointer to vertex data (x, y, z triplets as double) for a geometry by object and geometry index.
// Returns NULL if index is out of bounds.
const double* cityjson_get_vertices(CityJSONHandle handle, size_t object_index, size_t geometry_index);

// Get pointer to index data for a geometry by object and geometry index.
// Returns NULL if index is out of bounds.
const size_t* cityjson_get_indices(CityJSONHandle handle, size_t object_index, size_t geometry_index);

// Get the index count for a geometry by object and geometry index.
size_t cityjson_get_index_count(CityJSONHandle handle, size_t object_index, size_t geometry_index);

// Get face info: start index, vertex count, and face type.
// Returns 0 on success, -1 on failure.
int cityjson_get_face_info(
    CityJSONHandle handle,
    size_t object_index,
    size_t geometry_index,
    size_t face_index,
    size_t* out_start,
    size_t* out_count,
    uint8_t* out_face_type
);

// ---------------------------------------------------------------------------
// CityJSONSeq streaming reader/writer API
// ---------------------------------------------------------------------------

// Open / close a CityJSONSeq reader.
CityJSONSeqReaderHandle cityjsonseq_reader_open(const char* path);
void cityjsonseq_reader_destroy(CityJSONSeqReaderHandle handle);

// Get world-coordinate extent from the CityJSONSeq header metadata.geographicalExtent.
// Returns:
//   1 => success, extent available
//   0 => no extent available
//  -1 => error
int cityjsonseq_reader_header_geographical_extent(
    CityJSONSeqReaderHandle handle,
    double* out_min_xyz,
    double* out_max_xyz
);

// Streaming iteration.
// Returns:
//   1 => success with data
//   0 => end-of-file
//  -1 => error
int cityjsonseq_peek_next_id(CityJSONSeqReaderHandle handle, const char** out_id, size_t* out_len);
int cityjsonseq_next(CityJSONSeqReaderHandle handle);
int cityjsonseq_current_feature_id(CityJSONSeqReaderHandle handle, const char** out_id, size_t* out_len);

// Access decoded CityJSON for the current feature (valid until next/peek/destroy).
CityJSONHandle cityjsonseq_current_cityjson(CityJSONSeqReaderHandle handle);

// Open / close a CityJSONSeq writer from an existing reader (writes the header).
CityJSONSeqWriterHandle cityjsonseq_writer_open_from_reader(
    CityJSONSeqReaderHandle reader_handle,
    const char* output_path
);
void cityjsonseq_writer_destroy(CityJSONSeqWriterHandle writer_handle);

// Write pending/current raw feature lines.
// cityjsonseq_writer_write_pending_raw returns 1/0/-1.
// cityjsonseq_writer_write_current_raw returns 0/-1.
int cityjsonseq_writer_write_pending_raw(
    CityJSONSeqReaderHandle reader_handle,
    CityJSONSeqWriterHandle writer_handle
);
int cityjsonseq_writer_write_current_raw(
    CityJSONSeqReaderHandle reader_handle,
    CityJSONSeqWriterHandle writer_handle
);

// Write current feature with LoD 2.2 Solid geometry replaced by a triangle mesh.
// Semantics type values match zfcb semantic enum values:
//   0=RoofSurface, 1=GroundSurface, 2=WallSurface, 4=OuterCeilingSurface.
// Returns 0 on success, -1 on failure.
int cityjsonseq_writer_write_current_replaced_lod22(
    CityJSONSeqReaderHandle reader_handle,
    CityJSONSeqWriterHandle writer_handle,
    const char* feature_id,
    size_t feature_id_len,
    const double* vertices_xyz_world,
    size_t vertex_count,
    const uint32_t* triangle_indices,
    size_t triangle_index_count,
    const uint8_t* semantic_types,
    size_t semantic_types_count
);

// Write current feature with LoD 2.2 Solid geometry replaced by polygonal
// surfaces with optional holes.
// Semantics type values match zfcb semantic enum values:
//   0=RoofSurface, 1=GroundSurface, 2=WallSurface, 4=OuterCeilingSurface.
// surface_ring_counts: length = surface_count.
// ring_vertex_counts: length = ring_count, where ring_count is the sum of
//   surface_ring_counts.
// boundary_indices: flat vertex indices for every ring vertex.
// surface_semantic_types_count must equal surface_count.
// Returns 0 on success, -1 on failure.
int cityjsonseq_writer_write_current_replaced_lod22_polygonal(
    CityJSONSeqReaderHandle reader_handle,
    CityJSONSeqWriterHandle writer_handle,
    const char* feature_id,
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
    size_t surface_semantic_types_count
);

#ifdef __cplusplus
}
#endif

#endif // ZITYJSON_H
