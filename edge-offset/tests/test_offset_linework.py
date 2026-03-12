from pathlib import Path

from shapely.geometry import MultiLineString
from shapely.geometry import Polygon

import edge_offset.offset_linework as offset_linework
from edge_offset.geojson import read_feature_collection
from edge_offset.offset_linework import offset_polygon_from_classified_polygon
from edge_offset.offset_linework import offset_polygon_from_edge_geojson
from edge_offset.rings import classify_polygon_from_edge_sets


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


def test_offset_polygon_from_classified_polygon_supports_linework_strategy() -> None:
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
        strategy="linework",
    )

    assert updated.equals(Polygon([(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)]))


def test_offset_polygon_from_edge_geojson_writes_output() -> None:
    data_dir = Path(__file__).resolve().parent / "data"
    output_path = (
        Path(__file__).resolve().parent / "output" / "offset_polygon_from_edges.geojson"
    )

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
    written_features = read_feature_collection(output_path)
    assert written_features[0].properties["strategy"] == "boolean_patch"


def test_offset_polygon_falls_back_to_original_polygon_when_result_is_invalid(
    monkeypatch,
) -> None:
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
    original_polygon = classified.polygon

    def invalid_offset(
        classified_polygon,
        *,
        distance: float,
        tolerance: float,
    ) -> Polygon:
        del classified_polygon, distance, tolerance
        return Polygon([(0.0, 0.0), (4.0, 4.0), (4.0, 0.0), (0.0, 4.0)])

    monkeypatch.setattr(
        offset_linework, "_offset_polygon_with_boolean_patches", invalid_offset
    )

    updated = offset_polygon_from_classified_polygon(
        classified,
        distance=1.0,
    )

    assert updated.equals(original_polygon)
