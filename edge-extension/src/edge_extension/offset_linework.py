from dataclasses import dataclass
from math import isclose
from math import sqrt
from pathlib import Path

from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

from edge_extension.geojson import Feature
from edge_extension.geojson import write_feature_collection
from edge_extension.rings import BoundaryRing
from edge_extension.rings import ClassifiedPolygon
from edge_extension.rings import Point
from edge_extension.rings import classify_polygon_from_edge_geojson


@dataclass(frozen=True, slots=True)
class _OffsetLine:
    point: Point
    direction: Point


def offset_polygon_from_edge_geojson(
    *,
    movable_edges_path: Path,
    fixed_edges_path: Path,
    distance: float,
    output_path: Path | None = None,
    tolerance: float = 1e-6,
) -> Polygon:
    classified_polygon = classify_polygon_from_edge_geojson(
        movable_edges_path=movable_edges_path,
        fixed_edges_path=fixed_edges_path,
        tolerance=tolerance,
    )
    polygon = offset_polygon_from_classified_polygon(
        classified_polygon,
        distance=distance,
        tolerance=tolerance,
    )
    if output_path is not None:
        write_feature_collection(
            [
                Feature(
                    geometry=polygon,
                    properties={"offset_distance": distance},
                )
            ],
            path=output_path,
        )
    return polygon


def offset_polygon_from_classified_polygon(
    classified_polygon: ClassifiedPolygon,
    *,
    distance: float,
    tolerance: float = 1e-6,
) -> Polygon:
    if tolerance <= 0:
        raise ValueError("Offset tolerance must be greater than zero.")

    if classified_polygon.polygon.is_empty or isclose(distance, 0.0, abs_tol=tolerance):
        return classified_polygon.polygon

    rebuilt_rings = [
        _offset_ring(
            ring,
            distance=distance,
            tolerance=tolerance,
        )
        for ring in classified_polygon.rings
    ]
    shell = rebuilt_rings[0]
    holes = rebuilt_rings[1:]

    polygon = orient(Polygon(shell=shell, holes=holes), sign=1.0)
    if not polygon.is_valid:
        raise ValueError("Offset edges produced an invalid polygon.")

    return polygon


def _offset_ring(
    ring: BoundaryRing,
    *,
    distance: float,
    tolerance: float,
) -> list[Point]:
    if len(ring.vertices) < 3:
        raise ValueError("Polygon rings must contain at least three vertices.")

    lines = [
        _build_offset_line(
            start=segment.start,
            end=segment.end,
            distance=distance if segment.is_movable else 0.0,
            is_counter_clockwise=ring.is_counter_clockwise,
        )
        for segment in ring.segments
    ]

    return [
        _resolve_vertex(
            original_vertex=ring.vertices[index],
            previous_line=lines[index - 1],
            current_line=lines[index],
            tolerance=tolerance,
        )
        for index in range(len(lines))
    ]


def _build_offset_line(
    *,
    start: Point,
    end: Point,
    distance: float,
    is_counter_clockwise: bool,
) -> _OffsetLine:
    direction = (end[0] - start[0], end[1] - start[1])
    length = sqrt((direction[0] ** 2) + (direction[1] ** 2))
    if isclose(length, 0.0):
        raise ValueError("Polygon contains a zero-length edge.")

    unit_direction = (direction[0] / length, direction[1] / length)
    if is_counter_clockwise:
        outward_normal = (unit_direction[1], -unit_direction[0])
    else:
        outward_normal = (-unit_direction[1], unit_direction[0])

    return _OffsetLine(
        point=(
            start[0] + (outward_normal[0] * distance),
            start[1] + (outward_normal[1] * distance),
        ),
        direction=unit_direction,
    )


def _resolve_vertex(
    *,
    original_vertex: Point,
    previous_line: _OffsetLine,
    current_line: _OffsetLine,
    tolerance: float,
) -> Point:
    denominator = _cross(previous_line.direction, current_line.direction)
    if not isclose(denominator, 0.0, abs_tol=tolerance):
        delta = (
            current_line.point[0] - previous_line.point[0],
            current_line.point[1] - previous_line.point[1],
        )
        distance = _cross(delta, current_line.direction) / denominator
        return (
            previous_line.point[0] + (distance * previous_line.direction[0]),
            previous_line.point[1] + (distance * previous_line.direction[1]),
        )

    if not _parallel_lines_are_compatible(previous_line, current_line, tolerance=tolerance):
        raise ValueError("Adjacent offset edges are parallel and cannot be reconnected.")

    return _project_point_onto_line(original_vertex, previous_line)


def _parallel_lines_are_compatible(
    first: _OffsetLine,
    second: _OffsetLine,
    *,
    tolerance: float,
) -> bool:
    delta = (
        second.point[0] - first.point[0],
        second.point[1] - first.point[1],
    )
    return isclose(_cross(delta, first.direction), 0.0, abs_tol=tolerance)


def _project_point_onto_line(point: Point, line: _OffsetLine) -> Point:
    delta = (
        point[0] - line.point[0],
        point[1] - line.point[1],
    )
    scale = _dot(delta, line.direction)
    return (
        line.point[0] + (scale * line.direction[0]),
        line.point[1] + (scale * line.direction[1]),
    )


def _cross(first: Point, second: Point) -> float:
    return (first[0] * second[1]) - (first[1] * second[0])


def _dot(first: Point, second: Point) -> float:
    return (first[0] * second[0]) + (first[1] * second[1])
