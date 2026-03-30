#ifndef ZIGPIP_H
#define ZIGPIP_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
  double x;
  double y;
} ZpPoint;

typedef struct ZpPreparedPolygon ZpPreparedPolygon;

ZpPreparedPolygon *zp_polygon_create(const ZpPoint *vertices, size_t vertex_count,
                                     size_t resolution);
void zp_polygon_destroy(ZpPreparedPolygon *polygon);
int zp_polygon_contains(const ZpPreparedPolygon *polygon, double x, double y);
int zp_polygon_contains_many(const ZpPreparedPolygon *polygon, const double *xs,
                             const double *ys, size_t count, uint8_t *out);

#ifdef __cplusplus
}
#endif

#endif
