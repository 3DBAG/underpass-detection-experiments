"""Geometry operations for underpass detection."""

from typing import Union

from shapely import make_valid
from shapely.geometry import (
    MultiPolygon,
    Polygon,
)
from shapely.ops import snap, unary_union


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
    geom1: Union[Polygon, MultiPolygon],
    geom2: Union[Polygon, MultiPolygon],
) -> Union[Polygon, MultiPolygon]:
    if geom1 is None or geom1.is_empty:
        return Polygon()
    if geom2 is None or geom2.is_empty:
        return geom1

    try:
        diff = geom1.difference(geom2)

        if diff is None or diff.is_empty:
            return Polygon()

        if isinstance(diff, (Polygon, MultiPolygon)):
            return diff

        return Polygon()
    except Exception:
        return Polygon()


def extract_polygons(
    geom: Union[Polygon, MultiPolygon],
) -> Union[Polygon, MultiPolygon]:
    if geom is None or geom.is_empty:
        return Polygon()

    if isinstance(geom, Polygon):
        return geom

    if isinstance(geom, MultiPolygon):
        polygons = [g for g in geom.geoms if isinstance(g, Polygon) and not g.is_empty]
        if not polygons:
            return Polygon()
        if len(polygons) == 1:
            return polygons[0]
        return MultiPolygon(polygons)

    return Polygon()


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
        if dilated.is_empty:
            return Polygon()

        if isinstance(dilated, (Polygon, MultiPolygon)):
            return dilated

        return Polygon()
    except Exception:
        return Polygon()


def snap_pair(
    geom1: Union[Polygon, MultiPolygon],
    geom2: Union[Polygon, MultiPolygon],
    tolerance: float = 0.01,
) -> tuple[Union[Polygon, MultiPolygon], Union[Polygon, MultiPolygon]]:
    if geom1 is None or geom1.is_empty or geom2 is None or geom2.is_empty:
        return geom1, geom2

    try:
        snap1 = snap(geom1, geom2, tolerance)
        snap2 = snap(geom2, geom1, tolerance)
        snap1 = make_valid(snap1)
        snap2 = make_valid(snap2)
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
