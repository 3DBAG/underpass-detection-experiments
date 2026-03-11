from pathlib import Path

from shapely import build_area
from shapely.geometry import LineString
from shapely.geometry import MultiLineString
from shapely.geometry import Polygon
from shapely.ops import unary_union

from edge_extension.geojson import Feature
from edge_extension.geojson import read_feature_collection
from edge_extension.geojson import write_feature_collection


def load_polygon_from_edge_geojson(
    *,
    movable_edges_path: Path,
    fixed_edges_path: Path,
) -> Polygon:
    movable_edges = read_multiline_feature(movable_edges_path)
    fixed_edges = read_multiline_feature(fixed_edges_path)
    return build_polygon_from_edge_sets(
        movable_edges=movable_edges,
        fixed_edges=fixed_edges,
    )


def write_polygon_from_edge_geojson(
    *,
    movable_edges_path: Path,
    fixed_edges_path: Path,
    output_path: Path,
) -> Polygon:
    polygon = load_polygon_from_edge_geojson(
        movable_edges_path=movable_edges_path,
        fixed_edges_path=fixed_edges_path,
    )
    write_feature_collection(
        [
            Feature(
                geometry=polygon,
                properties={},
            )
        ],
        path=output_path,
    )
    return polygon


def read_multiline_feature(path: Path) -> MultiLineString:
    features = read_feature_collection(path)
    if len(features) != 1:
        raise ValueError("GeoJSON edge input must contain exactly one feature.")

    geometry = features[0].geometry
    if isinstance(geometry, MultiLineString):
        return geometry
    if isinstance(geometry, LineString):
        return MultiLineString([geometry.coords])

    raise ValueError("GeoJSON edge input must contain a LineString or MultiLineString feature.")


def build_polygon_from_edge_sets(
    *,
    movable_edges: MultiLineString,
    fixed_edges: MultiLineString,
) -> Polygon:
    merged_linework = unary_union([movable_edges, fixed_edges])
    area_geometry = build_area(merged_linework)

    if isinstance(area_geometry, Polygon):
        return area_geometry

    if area_geometry.geom_type == "MultiPolygon" and len(area_geometry.geoms) == 1:
        polygon = area_geometry.geoms[0]
        if isinstance(polygon, Polygon):
            return polygon

    raise ValueError("Edge linework did not resolve to a single polygon.")
