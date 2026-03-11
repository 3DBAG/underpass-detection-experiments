from pathlib import Path

from shapely.geometry import MultiLineString
from shapely.geometry import Polygon

from edge_extension.offset_linework import offset_polygon_from_classified_polygon
from edge_extension.offset_linework import offset_polygon_from_edge_geojson
from edge_extension.rings import classify_polygon_from_edge_sets


def test_offset_polygon_from_classified_polygon_moves_only_movable_edges() -> None:
    movable_edges = MultiLineString(
        [
            [(4.0, 0.0), (4.0, 4.0)],
            [(4.0, 4.0), (0.0, 4.0)],
        ]
    )
    fixed_edges = MultiLineString(
        [
            [(0.0, 4.0), (0.0, 0.0)],
            [(0.0, 0.0), (4.0, 0.0)],
        ]
    )
    classified = classify_polygon_from_edge_sets(
        movable_edges=movable_edges,
        fixed_edges=fixed_edges,
    )

    updated = offset_polygon_from_classified_polygon(
        classified,
        distance=1.0,
    )

    assert updated.equals(Polygon([(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)]))


def test_offset_polygon_from_edge_geojson_writes_output() -> None:
    data_dir = Path(__file__).resolve().parent / "data"
    output_path = Path(__file__).resolve().parent / "output" / "offset_polygon_from_edges.geojson"

    updated = offset_polygon_from_edge_geojson(
        movable_edges_path=data_dir / "exterior_one.geojson",
        fixed_edges_path=data_dir / "interior_one.geojson",
        distance=0.25,
        output_path=output_path,
    )

    assert output_path.exists()
    assert updated.is_valid
    assert len(updated.interiors) == 1
    assert updated.area > 0
