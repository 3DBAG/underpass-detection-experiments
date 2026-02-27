#ifndef MODEL_LOADERS_H
#define MODEL_LOADERS_H

#include <string_view>

#include "BooleanOps.h"
#include "OGRVectorReader.h"

// Forward declarations for opaque handles.
typedef struct CityJSON* CityJSONHandle;
typedef struct Reader* ZfcbReaderHandle;

bool is_fcb_path(std::string_view path);

ssize_t resolve_cityjson_object_index(CityJSONHandle cj, std::string_view feature_id);

bool load_cityjson_object_mesh(
    CityJSONHandle cj,
    size_t object_index,
    Surface_mesh& sm,
    double offset_x,
    double offset_y,
    double offset_z);

bool load_fcb_feature_mesh(
    ZfcbReaderHandle fcb,
    std::string_view feature_id,
    Surface_mesh& sm,
    double offset_x,
    double offset_y,
    double offset_z);

ogr::LinearRing make_offset_polygon(
    const ogr::LinearRing& polygon,
    double offset_x,
    double offset_y,
    double offset_z);

#endif // MODEL_LOADERS_H
