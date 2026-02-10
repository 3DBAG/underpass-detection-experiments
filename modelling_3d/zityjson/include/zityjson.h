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

// Add a vertex to a geometry's mesh.
// Returns the vertex index, or -1 on failure.
ssize_t cityjson_add_vertex(CityJSONHandle handle, size_t object_index, size_t geometry_index, double x, double y, double z);

// Add a face to a geometry's mesh.
// vertex_indices: array of vertex indices for this face.
// num_indices: number of indices.
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

// Get the vertex count for a geometry by object and geometry index.
size_t cityjson_get_vertex_count(CityJSONHandle handle, size_t object_index, size_t geometry_index);

// Get the face count for a geometry by object and geometry index.
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

#ifdef __cplusplus
}
#endif

#endif // ZITYJSON_H
