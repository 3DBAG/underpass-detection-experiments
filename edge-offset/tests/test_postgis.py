from pathlib import Path

from psycopg.sql import Identifier
from shapely import to_wkb
from shapely.geometry import LineString
from shapely.geometry import MultiLineString
from shapely.geometry import Polygon

from edge_offset.geojson import read_feature_collection
from edge_offset.postgis import load_edge_records_from_db
from edge_offset.postgis import offset_polygon_features_from_db
from edge_offset.postgis import write_offset_polygons_from_db


class FakeCursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows
        self.executed_query = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        del exc_type, exc_value, traceback

    def execute(self, query) -> None:
        self.executed_query = query

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


class FakeConnection:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows
        self.cursor_instance = FakeCursor(rows)

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


def test_load_edge_records_from_db_combines_shared_and_interior_edges() -> None:
    connection = FakeConnection(
        [
            # Multiple edge rows for one underpass
            ("building-1", 7, "exterior", to_wkb(LineString([(4.0, 0.0), (4.0, 4.0)]))),
            ("building-1", 7, "exterior", to_wkb(LineString([(4.0, 4.0), (0.0, 4.0)]))),
            ("building-1", 7, "shared", to_wkb(LineString([(0.0, 4.0), (0.0, 0.0)]))),
            ("building-1", 7, "interior", to_wkb(LineString([(0.0, 0.0), (4.0, 0.0)]))),
        ]
    )

    records = load_edge_records_from_db(
        connection,
        edges_table=Identifier("underpasses", "edges"),
    )

    assert len(records) == 1
    assert records[0].identificatie == "building-1"
    assert records[0].underpass_id == 7
    assert len(records[0].movable_edges.geoms) == 2
    assert len(records[0].fixed_edges.geoms) == 2
    assert connection.cursor_instance.executed_query is not None


def test_offset_polygon_features_from_db_offsets_all_rows() -> None:
    connection = FakeConnection(
        [
            # Multiple edge rows for one underpass
            ("building-1", 7, "exterior", to_wkb(LineString([(4.0, 0.0), (4.0, 4.0)]))),
            ("building-1", 7, "exterior", to_wkb(LineString([(4.0, 4.0), (0.0, 4.0)]))),
            ("building-1", 7, "shared", to_wkb(LineString([(0.0, 4.0), (0.0, 0.0)]))),
            ("building-1", 7, "interior", to_wkb(LineString([(0.0, 0.0), (4.0, 0.0)]))),
        ]
    )

    features = offset_polygon_features_from_db(
        connection,
        edges_table=Identifier("underpasses", "edges"),
        distance=1.0,
    )

    assert len(features) == 1
    assert features[0].geometry.equals(
        Polygon([(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)])
    )
    assert features[0].properties["identificatie"] == "building-1"
    assert features[0].properties["underpass_id"] == 7
    assert features[0].properties["strategy"] == "boolean_patch"


def test_write_offset_polygons_from_db_writes_feature_collection(
    tmp_path: Path,
) -> None:
    connection = FakeConnection(
        [
            # Multiple edge rows for one underpass
            ("building-1", 7, "exterior", to_wkb(LineString([(4.0, 0.0), (4.0, 4.0)]))),
            ("building-1", 7, "exterior", to_wkb(LineString([(4.0, 4.0), (0.0, 4.0)]))),
            ("building-1", 7, "shared", to_wkb(LineString([(0.0, 4.0), (0.0, 0.0)]))),
            ("building-1", 7, "interior", to_wkb(LineString([(0.0, 0.0), (4.0, 0.0)]))),
        ]
    )
    output_path = tmp_path / "offset_polygons.geojson"

    features = write_offset_polygons_from_db(
        connection,
        edges_table=Identifier("underpasses", "edges"),
        distance=1.0,
        output_path=output_path,
    )
    written_features = read_feature_collection(output_path)

    assert len(features) == 1
    assert output_path.exists()
    assert len(written_features) == 1
    assert written_features[0].geometry.equals(features[0].geometry)
