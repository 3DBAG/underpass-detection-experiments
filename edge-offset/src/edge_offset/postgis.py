from dataclasses import dataclass
from pathlib import Path
from typing import Any

from psycopg import Connection
from psycopg.sql import Identifier
from psycopg.sql import SQL
from shapely import from_wkb
from shapely.geometry import MultiLineString

from edge_offset.geojson import Feature
from edge_offset.geojson import write_feature_collection
from edge_offset.linework import coerce_multiline_geometry
from edge_offset.linework import merge_multiline_geometries
from edge_offset.offset_linework import offset_polygon_from_classified_polygon
from edge_offset.rings import classify_polygon_from_edge_sets


@dataclass(frozen=True, slots=True)
class EdgeRecord:
    identificatie: str
    underpass_id: int
    movable_edges: MultiLineString
    fixed_edges: MultiLineString


def load_edge_records_from_db(
    connection: Connection[Any],
    *,
    edges_table: Identifier,
) -> tuple[EdgeRecord, ...]:
    query = SQL(
        """
        SELECT
            identificatie::text,
            underpass_id,
            ST_AsBinary(ST_CollectionExtract(exterior_edges, 2)) AS exterior_edges_wkb,
            ST_AsBinary(ST_CollectionExtract(shared_edges, 2)) AS shared_edges_wkb,
            ST_AsBinary(ST_CollectionExtract(interior_edges, 2)) AS interior_edges_wkb
        FROM {edges_table}
        ORDER BY identificatie, underpass_id
        """
    ).format(edges_table=edges_table)

    records: list[EdgeRecord] = []
    with connection.cursor() as cursor:
        cursor.execute(query)
        for row in cursor.fetchall():
            identificatie, underpass_id, movable_wkb, shared_wkb, interior_wkb = row
            movable_edges = _load_multiline_from_wkb(movable_wkb)
            fixed_edges = merge_multiline_geometries(
                _load_geometry_from_wkb(shared_wkb),
                _load_geometry_from_wkb(interior_wkb),
            )
            records.append(
                EdgeRecord(
                    identificatie=str(identificatie),
                    underpass_id=int(underpass_id),
                    movable_edges=movable_edges,
                    fixed_edges=fixed_edges,
                )
            )

    return tuple(records)


def offset_polygon_features_from_db(
    connection: Connection[Any],
    *,
    edges_table: Identifier,
    distance: float,
    tolerance: float = 1e-6,
    strategy: str = "boolean_patch",
) -> list[Feature]:
    records = load_edge_records_from_db(
        connection,
        edges_table=edges_table,
    )

    features: list[Feature] = []
    for record in records:
        classified_polygon = classify_polygon_from_edge_sets(
            movable_edges=record.movable_edges,
            fixed_edges=record.fixed_edges,
            tolerance=tolerance,
        )
        polygon = offset_polygon_from_classified_polygon(
            classified_polygon,
            distance=distance,
            tolerance=tolerance,
            strategy=strategy,
        )
        features.append(
            Feature(
                geometry=polygon,
                properties={
                    "identificatie": record.identificatie,
                    "underpass_id": record.underpass_id,
                    "offset_distance": distance,
                    "strategy": strategy,
                },
            )
        )

    return features


def write_offset_polygons_from_db(
    connection: Connection[Any],
    *,
    edges_table: Identifier,
    distance: float,
    output_path: Path,
    tolerance: float = 1e-6,
    strategy: str = "boolean_patch",
) -> list[Feature]:
    features = offset_polygon_features_from_db(
        connection,
        edges_table=edges_table,
        distance=distance,
        tolerance=tolerance,
        strategy=strategy,
    )
    write_feature_collection(features, path=output_path)
    return features


def _load_multiline_from_wkb(value: bytes | memoryview | None) -> MultiLineString:
    return coerce_multiline_geometry(_load_geometry_from_wkb(value))


def _load_geometry_from_wkb(value: bytes | memoryview | None):
    if value is None:
        return None
    return from_wkb(bytes(value))
