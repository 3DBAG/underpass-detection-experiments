import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
from pyproj import Transformer
from shapely.geometry import box
from shapely.ops import transform

import mapterhorn_terrain
from height_estimation import (
    add_lower_peak_masked_grids,
    estimate_underpass_height_from_points,
)


def encode_terrarium(height):
    shifted = float(height) + 32768.0
    integer = int(np.floor(shifted))
    return np.array(
        [integer // 256, integer % 256, int((shifted - integer) * 256)],
        dtype=np.uint8,
    )


class MapterhornTerrainTests(unittest.TestCase):
    def test_samples_polygon_pixels_and_uses_p90(self):
        zoom = 14
        tile_x = 8415
        tile_y = 5384
        local_col = 100
        local_row = 200
        global_col = tile_x * mapterhorn_terrain.MAPTERHORN_TILE_SIZE + local_col
        global_row = tile_y * mapterhorn_terrain.MAPTERHORN_TILE_SIZE + local_row
        scale = mapterhorn_terrain._global_pixel_scale(zoom)
        half_world = mapterhorn_terrain.WEB_MERCATOR_HALF_WORLD_M
        left = global_col / scale - half_world
        right = (global_col + 2) / scale - half_world
        top = half_world - global_row / scale
        bottom = half_world - (global_row + 2) / scale
        to_rd = Transformer.from_crs("EPSG:3857", "EPSG:28992", always_xy=True)
        geometry_rd = transform(to_rd.transform, box(left, bottom, right, top))

        rgb = np.zeros((512, 512, 3), dtype=np.uint8)
        heights = [0.0, 10.0, 20.0, 30.0]
        for height, (x, y) in zip(
            heights,
            [
                (local_col, local_row),
                (local_col + 1, local_row),
                (local_col, local_row + 1),
                (local_col + 1, local_row + 1),
            ],
            strict=True,
        ):
            rgb[y, x] = encode_terrarium(height)

        with TemporaryDirectory() as cache_dir, patch.object(
            mapterhorn_terrain,
            "load_mapterhorn_tile",
            return_value=rgb,
        ):
            sample = mapterhorn_terrain.sample_polygon_terrain(
                geometry_rd,
                zoom=zoom,
                percentile=90.0,
                cache_dir=Path(cache_dir),
            )

        self.assertEqual(sample.pixel_count, 4)
        self.assertEqual(sample.tile_count, 1)
        self.assertEqual(sample.selection, "pixel_centers")
        self.assertAlmostEqual(sample.elevation_m_nap, 27.0)

    def test_terrarium_decode(self):
        rgb = np.array([[128, 1, 128]], dtype=np.uint8)
        self.assertAlmostEqual(float(mapterhorn_terrain.decode_terrarium(rgb)[0]), 1.5)


class TerrainPeakFilterTests(unittest.TestCase):
    def test_peak_within_two_metres_is_disqualified(self):
        cell_centers = np.array([0.25, 0.75, 1.25, 1.75])
        grid_x, grid_y = np.meshgrid(cell_centers, cell_centers)
        surface_x = np.repeat(grid_x.ravel(), 100)
        surface_y = np.repeat(grid_y.ravel(), 100)
        x = np.concatenate((surface_x, surface_x))
        y = np.concatenate((surface_y, surface_y))
        z = np.concatenate(
            (
                np.full(surface_x.size, 1.0),
                np.full(surface_x.size, 5.0),
            )
        )

        result = estimate_underpass_height_from_points(
            "test",
            x,
            y,
            z,
            [box(0.0, 0.0, 2.0, 2.0)],
            verbose=False,
            terrain_elevation=1.0,
            terrain_metadata={"percentile": 90.0},
            terrain_peak_exclusion_distance_meters=2.0,
        )

        elevations = result["underpass_metrics"]["underpass_candidate_elevations"]
        self.assertEqual(len(elevations), 1)
        self.assertAlmostEqual(elevations[0], 5.025)
        terrain = result["underpass_metrics"]["underpass_metadata"]["terrain"]
        self.assertEqual(terrain["disqualified_peak_count"], 1)
        self.assertEqual(terrain["peak_exclusion_distance_m"], 2.0)

        from plot_z_histogram import plot_height_estimation_result

        with TemporaryDirectory() as output_dir:
            plot_height_estimation_result(
                result, output_dir=output_dir, write_rerun=False
            )
            self.assertTrue(
                (Path(output_dir) / "test_peak_grids_overlay.png").is_file()
            )


class TwoPhaseSelectionTests(unittest.TestCase):
    def test_phase_two_rejection_remains_in_plot(self):
        cell_centers = np.array([0.25, 0.75, 1.25, 1.75])
        grid_x, grid_y = np.meshgrid(cell_centers, cell_centers)
        surface_x = np.repeat(grid_x.ravel(), 100)
        surface_y = np.repeat(grid_y.ravel(), 100)
        x = np.tile(surface_x, 3)
        y = np.tile(surface_y, 3)
        z = np.concatenate(
            (
                np.full(surface_x.size, 1.0),
                np.full(surface_x.size, 5.0),
                np.full(surface_x.size, 9.0),
            )
        )

        result = estimate_underpass_height_from_points(
            "two-phase",
            x,
            y,
            z,
            [box(0.0, 0.0, 2.0, 2.0)],
            verbose=False,
            terrain_elevation=1.0,
            terrain_metadata={"percentile": 90.0},
        )

        self.assertEqual(len(result["terrain_disqualified_layers"]), 1)
        self.assertEqual(len(result["phase_one_layers"]), 2)
        self.assertEqual(len(result["display_peak_layers"]), 2)
        self.assertEqual(len(result["ranked_output_layers"]), 1)

        lower_layer, upper_layer = result["display_peak_layers"]
        self.assertEqual(np.count_nonzero(lower_layer["lower_peak_masked_grid"]), 16)
        self.assertEqual(np.count_nonzero(upper_layer["lower_peak_masked_grid"]), 0)

        summaries = result["underpass_metrics"]["underpass_metadata"]["candidate_peaks"]
        phase_one_summaries = [
            summary for summary in summaries if summary["area_m2"] is not None
        ]
        self.assertEqual(
            [summary["rank"] for summary in phase_one_summaries],
            [1, None],
        )

        from plot_z_histogram import plot_height_estimation_result

        with TemporaryDirectory() as output_dir:
            plot_height_estimation_result(result, output_dir, write_rerun=False)
            self.assertTrue(
                (Path(output_dir) / "two-phase_peak_grids_overlay.png").is_file()
            )


class LowerPeakMaskTests(unittest.TestCase):
    def test_masks_every_lower_peak(self):
        lowest_grid = np.array([[1.0, 1.0, 0.0, 0.0]])
        middle_grid = np.array([[1.0, 0.0, 1.0, 0.0]])
        upper_grid = np.array([[1.0, 1.0, 1.0, 1.0]])
        layers = [
            {"peak_center": 5.0, "grid": upper_grid},
            {"peak_center": 1.0, "grid": lowest_grid},
            {"peak_center": 3.0, "grid": middle_grid},
        ]

        add_lower_peak_masked_grids(layers, cellsize=0.5)

        np.testing.assert_array_equal(
            layers[1]["lower_peak_masked_grid"],
            lowest_grid,
        )
        np.testing.assert_array_equal(
            layers[2]["lower_peak_masked_grid"],
            np.array([[0.0, 0.0, 1.0, 0.0]]),
        )
        np.testing.assert_array_equal(
            layers[0]["lower_peak_masked_grid"],
            np.array([[0.0, 0.0, 0.0, 1.0]]),
        )
        self.assertAlmostEqual(layers[0]["lower_peak_masked_area"], 0.25)
        self.assertAlmostEqual(
            layers[0]["lower_peak_masked_largest_component_area"],
            0.25,
        )


if __name__ == "__main__":
    unittest.main()
