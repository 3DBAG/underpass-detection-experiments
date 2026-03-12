from pathlib import Path

import pytest
from shapely.geometry import MultiLineString
from shapely.geometry import Polygon

import edge_offset.offset_linework as offset_linework
from edge_offset.geojson import read_feature_collection
from edge_offset.linework import load_polygon_from_edge_geojson
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


@pytest.mark.parametrize(
    ("poly_id", "expected_bounds", "expected_area_gain"),
    [
        (
            118,
            (122316.701, 486210.76316141174, 122328.61480522287, 486240.5630923396),
            8.172817250611665,
        ),
        (
            119,
            (122308.14783881881, 486243.599, 122317.07154682244, 486264.3286552605),
            5.831615628033141,
        ),
    ],
)
@pytest.mark.parametrize("strategy", ["boolean_patch", "linework"])
def test_offset_polygon_from_edge_geojson_limits_near_parallel_miters(
    poly_id: int,
    expected_bounds: tuple[float, float, float, float],
    expected_area_gain: float,
    strategy: str,
) -> None:
    data_dir = Path(__file__).resolve().parent / "data"
    movable_edges_path = (
        data_dir / f"pand_0363100012165490_poly_{poly_id}_movable.geojson"
    )
    fixed_edges_path = data_dir / f"pand_0363100012165490_poly_{poly_id}_fixed.geojson"

    original = load_polygon_from_edge_geojson(
        movable_edges_path=movable_edges_path,
        fixed_edges_path=fixed_edges_path,
    )
    updated = offset_polygon_from_edge_geojson(
        movable_edges_path=movable_edges_path,
        fixed_edges_path=fixed_edges_path,
        distance=0.25,
        strategy=strategy,
    )

    assert updated.is_valid
    assert not updated.equals(original)
    assert updated.bounds == pytest.approx(expected_bounds, abs=1e-6)
    assert updated.area == pytest.approx(
        original.area + expected_area_gain,
        abs=1e-6,
    )
    assert original.hausdorff_distance(updated) < 1.0
