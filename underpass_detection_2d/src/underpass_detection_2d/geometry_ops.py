"""Geometry operations for underpass detection."""

from typing import Union

from shapely import make_valid
from shapely.geometry import (
    GeometryCollection,
    MultiPolygon,
    Polygon,
)
from shapely.ops import snap, unary_union


def _extract_polygonal(geom: Union[Polygon, MultiPolygon, GeometryCollection]) -> Union[Polygon, MultiPolygon]:
    """Extract polygon parts from any geometry, discarding non-polygonal components."""
    if geom is None or geom.is_empty:
        return Polygon()
    if isinstance(geom, Polygon):
        return geom
    if isinstance(geom, MultiPolygon):
        polys = [g for g in geom.geoms if isinstance(g, Polygon) and not g.is_empty]
        if not polys:
            return Polygon()
        if len(polys) == 1:
            return polys[0]
        return MultiPolygon(polys)
    if isinstance(geom, GeometryCollection):
        polys = [g for g in geom.geoms if isinstance(g, Polygon) and not g.is_empty]
        if not polys:
            return Polygon()
        if len(polys) == 1:
            return polys[0]
        return MultiPolygon(polys)
    return Polygon()


def union_geometries(
    geoms: list[Union[Polygon, MultiPolygon]],
) -> Union[Polygon, MultiPolygon]:
    if not geoms:
        return Polygon()

    valid_geoms = [g for g in geoms if g is not None and not g.is_empty]
    if not valid_geoms:
        return Polygon()

    result = unary_union(valid_geoms)
    if result.is_empty:
        return Polygon()

    return result


def safe_difference(
    geom1: Union[Polygon, MultiPolygon, GeometryCollection],
    geom2: Union[Polygon, MultiPolygon, GeometryCollection],
) -> Union[Polygon, MultiPolygon]:
    if geom1 is None or geom1.is_empty:
        return Polygon()
    if geom2 is None or geom2.is_empty:
        return _extract_polygonal(geom1)

    try:
        diff = geom1.difference(geom2)
        return _extract_polygonal(diff)
    except Exception:
        return Polygon()


def extract_polygons(
    geom: Union[Polygon, MultiPolygon, GeometryCollection],
) -> Union[Polygon, MultiPolygon]:
    return _extract_polygonal(geom)


def double_buffer_filter(
    geom: Union[Polygon, MultiPolygon],
    distance: float = 0.2,
) -> Union[Polygon, MultiPolygon]:
    if geom is None or geom.is_empty:
        return Polygon()

    try:
        eroded = geom.buffer(-distance)
        if eroded.is_empty:
            return Polygon()
        dilated = eroded.buffer(distance)
        return _extract_polygonal(dilated)
    except Exception:
        return Polygon()


def snap_pair(
    geom1: Union[Polygon, MultiPolygon],
    geom2: Union[Polygon, MultiPolygon],
    tolerance: float = 0.03,
) -> tuple[Union[Polygon, MultiPolygon], Union[Polygon, MultiPolygon]]:
    if geom1 is None or geom1.is_empty or geom2 is None or geom2.is_empty:
        return geom1, geom2

    try:
        snap1 = snap(geom1, geom2, tolerance)
        snap2 = snap(geom2, geom1, tolerance)
        snap1 = _extract_polygonal(make_valid(snap1))
        snap2 = _extract_polygonal(make_valid(snap2))
        return snap1, snap2
    except Exception:
        return geom1, geom2


def dump_multi_to_polygons(
    geom: Union[Polygon, MultiPolygon],
) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []

    if isinstance(geom, Polygon):
        return [geom] if not geom.is_empty else []

    if isinstance(geom, MultiPolygon):
        return [p for p in geom.geoms if isinstance(p, Polygon) and not p.is_empty]

    return []
