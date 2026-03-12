"""edge_extension package."""

from edge_extension.linework import build_polygon_from_edge_sets
from edge_extension.linework import coerce_multiline_geometry
from edge_extension.linework import load_polygon_from_edge_geojson
from edge_extension.linework import merge_multiline_geometries
from edge_extension.linework import write_polygon_from_edge_geojson
from edge_extension.offset_linework import offset_polygon_from_classified_polygon
from edge_extension.offset_linework import offset_polygon_from_edge_geojson
from edge_extension.postgis import load_edge_records_from_db
from edge_extension.postgis import offset_polygon_features_from_db
from edge_extension.postgis import write_offset_polygons_from_db
from edge_extension.rings import classify_polygon_from_edge_geojson
from edge_extension.rings import classify_polygon_from_edge_sets

__all__ = [
    "build_polygon_from_edge_sets",
    "classify_polygon_from_edge_geojson",
    "classify_polygon_from_edge_sets",
    "coerce_multiline_geometry",
    "load_polygon_from_edge_geojson",
    "load_edge_records_from_db",
    "merge_multiline_geometries",
    "offset_polygon_from_classified_polygon",
    "offset_polygon_from_edge_geojson",
    "offset_polygon_features_from_db",
    "write_offset_polygons_from_db",
    "write_polygon_from_edge_geojson",
]
