import laspy
import numpy as np
import sqlite3
from pathlib import Path
from shapely import wkb
from shapely.ops import unary_union


# Peak-detection and output parameters.
# Use fixed-width Z bins whose edges are global elevation multiples. This makes
# a bin represent the same elevation interval in every case, independently of
# that case's Z range.
HISTOGRAM_BIN_WIDTH_METERS = 0.15
HISTOGRAM_ANCHOR_ELEVATION_METERS = 0.0

# XY raster cell size in meters for the per-peak occupancy grids.
GRID_CELLSIZE = 0.5

# Width of the Z band, centered on each selected peak, used to subset LAS
# points for the raster outputs and reported peak windows.
PEAK_BAND_WIDTH_METERS = 1

# Minimum separtion between subsequent peaks
PEAK_MIN_SEPARATION_BINS = 5

# A candidate must satisfy both absolute thresholds to enter production output.
PEAK_MIN_RAW_COUNT = 1000
PEAK_MIN_MASK_AREA_M2 = 4.0
PEAK_MIN_MASK_AREA_POLYGON_FRACTION = 0.20

# Candidates must also reach this fraction of the second-highest candidate raw
# peak-bin count to enter diagnostic plots and production output.
PEAK_MIN_RELATIVE_RAW_COUNT = 0.05

# When enabled, the candidate peak is snapped from the smoothed local maximum to
# the highest raw histogram bin inside that smoothed peak cluster.
SNAP_PEAK_TO_RAW_BIN_WITHIN_CLUSTER = True


def anchored_histogram_bin_edges(
    values,
    bin_width_meters=HISTOGRAM_BIN_WIDTH_METERS,
    anchor_elevation_meters=HISTOGRAM_ANCHOR_ELEVATION_METERS,
):
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        raise ValueError("Cannot construct histogram bins without values")
    if not np.all(np.isfinite(values)):
        raise ValueError("Histogram values must be finite")
    if not np.isfinite(bin_width_meters) or bin_width_meters <= 0:
        raise ValueError("Histogram bin width must be a positive finite number")
    if not np.isfinite(anchor_elevation_meters):
        raise ValueError("Histogram anchor elevation must be finite")

    lower_bin_idx = int(
        np.floor((np.min(values) - anchor_elevation_meters) / bin_width_meters)
    )
    # Keep the upper edge strictly above the maximum. In particular, an
    # elevation exactly on a global boundary belongs to the bin beginning at
    # that boundary, rather than numpy.histogram's special inclusive last bin.
    upper_bin_idx = (
        int(np.floor((np.max(values) - anchor_elevation_meters) / bin_width_meters))
        + 1
    )

    bin_indices = np.arange(lower_bin_idx, upper_bin_idx + 1, dtype=np.int64)
    return anchor_elevation_meters + bin_indices * bin_width_meters


def relative_raw_count_threshold(
    candidate_raw_counts,
    fraction=PEAK_MIN_RELATIVE_RAW_COUNT,
):
    if not np.isfinite(fraction) or fraction < 0:
        raise ValueError("Relative raw-count fraction must be finite and non-negative")

    ranked_counts = sorted(candidate_raw_counts, reverse=True)
    if len(ranked_counts) >= 2:
        reference_count = ranked_counts[1]
    elif ranked_counts:
        reference_count = ranked_counts[0]
    else:
        return 0.0
    return fraction * reference_count


def polygon_relative_mask_area_threshold(
    polygon_area_m2,
    fraction=PEAK_MIN_MASK_AREA_POLYGON_FRACTION,
):
    if not np.isfinite(polygon_area_m2) or polygon_area_m2 <= 0:
        raise ValueError("Polygon area must be a positive finite number")
    if not np.isfinite(fraction) or not 0 <= fraction <= 1:
        raise ValueError("Polygon-area fraction must be between 0 and 1")
    return fraction * polygon_area_m2


def find_top_histogram_peaks(
    values,
    bin_width_meters=HISTOGRAM_BIN_WIDTH_METERS,
    anchor_elevation_meters=HISTOGRAM_ANCHOR_ELEVATION_METERS,
    smoothing_window=7,
    min_separation_bins=PEAK_MIN_SEPARATION_BINS,
):
    bin_edges = anchored_histogram_bin_edges(
        values,
        bin_width_meters=bin_width_meters,
        anchor_elevation_meters=anchor_elevation_meters,
    )
    counts, _ = np.histogram(values, bins=bin_edges)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    # Smooth the histogram slightly so one broad mode does not produce several
    # adjacent local maxima from binning noise.
    effective_smoothing_window = min(smoothing_window, len(counts))
    if effective_smoothing_window % 2 == 0:
        effective_smoothing_window -= 1
    if effective_smoothing_window < 3:
        smoothed_counts = counts.astype(float)
    else:
        kernel = np.hanning(effective_smoothing_window)
        kernel /= kernel.sum()
        smoothed_counts = np.convolve(counts, kernel, mode="same")

    candidate_indices = []
    if len(smoothed_counts) == 1:
        candidate_indices = [0]
    else:
        if smoothed_counts[0] > smoothed_counts[1]:
            candidate_indices.append(0)

        interior_candidates = np.where(
            (smoothed_counts[1:-1] > smoothed_counts[:-2])
            & (smoothed_counts[1:-1] >= smoothed_counts[2:])
        )[0] + 1
        candidate_indices.extend(interior_candidates.tolist())

        if smoothed_counts[-1] > smoothed_counts[-2]:
            candidate_indices.append(len(smoothed_counts) - 1)

    candidate_indices = np.asarray(candidate_indices, dtype=int)

    ranked_candidates = candidate_indices[np.argsort(smoothed_counts[candidate_indices])[::-1]]

    separated_candidates = []
    for idx in ranked_candidates:
        if all(abs(idx - existing) >= min_separation_bins for existing in separated_candidates):
            separated_candidates.append(idx)

    return (
        counts,
        bin_edges,
        bin_centers,
        smoothed_counts,
        separated_candidates,
    )


def peak_cluster_index_bounds(smoothed_counts, peak_idx):
    left_idx = peak_idx
    while left_idx > 0 and smoothed_counts[left_idx - 1] <= smoothed_counts[left_idx]:
        left_idx -= 1

    right_idx = peak_idx
    max_idx = len(smoothed_counts) - 1
    while right_idx < max_idx and smoothed_counts[right_idx + 1] <= smoothed_counts[right_idx]:
        right_idx += 1

    return left_idx, right_idx


def refine_peak_index_within_cluster(counts, smoothed_counts, peak_idx):
    left_idx, right_idx = peak_cluster_index_bounds(smoothed_counts, peak_idx)
    cluster_counts = counts[left_idx:right_idx + 1]
    max_count = np.max(cluster_counts)
    max_indices = np.flatnonzero(cluster_counts == max_count) + left_idx
    refined_peak_idx = max_indices[np.argmin(np.abs(max_indices - peak_idx))]
    return refined_peak_idx


def peak_band_from_center(peak_center, values_min, values_max, band_width_meters):
    half_width = band_width_meters / 2
    z_min = max(values_min, peak_center - half_width)
    z_max = min(values_max, peak_center + half_width)
    return z_min, z_max


def feature_table_name(path):
    with sqlite3.connect(path) as con:
        row = con.execute(
            "select table_name from gpkg_contents where data_type = 'features' limit 1"
        ).fetchone()

    if row is None:
        raise ValueError(f"No feature table found in {path}")

    return row[0]


def gpkg_blob_to_geometry(blob):
    blob = bytes(blob)
    if blob[:2] != b"GP":
        raise ValueError("Geometry blob is not in GeoPackage binary format")

    flags = blob[3]
    envelope_indicator = (flags >> 1) & 0b111
    envelope_sizes = {
        0: 0,
        1: 32,
        2: 48,
        3: 48,
        4: 64,
    }
    if envelope_indicator not in envelope_sizes:
        raise ValueError(f"Unsupported GeoPackage envelope type: {envelope_indicator}")

    wkb_offset = 8 + envelope_sizes[envelope_indicator]
    return wkb.loads(blob[wkb_offset:])


def connect_gpkg(path):
    con = sqlite3.connect(path)

    def geometry_or_none(blob):
        if blob is None:
            return None
        return gpkg_blob_to_geometry(blob)

    con.create_function(
        "ST_IsEmpty",
        1,
        lambda blob: int((geometry_or_none(blob) is not None) and geometry_or_none(blob).is_empty),
    )
    con.create_function(
        "ST_MinX",
        1,
        lambda blob: None if geometry_or_none(blob) is None else geometry_or_none(blob).bounds[0],
    )
    con.create_function(
        "ST_MaxX",
        1,
        lambda blob: None if geometry_or_none(blob) is None else geometry_or_none(blob).bounds[2],
    )
    con.create_function(
        "ST_MinY",
        1,
        lambda blob: None if geometry_or_none(blob) is None else geometry_or_none(blob).bounds[1],
    )
    con.create_function(
        "ST_MaxY",
        1,
        lambda blob: None if geometry_or_none(blob) is None else geometry_or_none(blob).bounds[3],
    )
    return con


def load_polygon_geometries(path):
    table_name = feature_table_name(path)
    with connect_gpkg(path) as con:
        rows = con.execute(f'select geom from "{table_name}" where geom is not null').fetchall()

    return [gpkg_blob_to_geometry(row[0]) for row in rows]


def iter_rings(geometry):
    if geometry.geom_type == "Polygon":
        yield np.asarray(geometry.exterior.coords, dtype=float)
        for ring in geometry.interiors:
            yield np.asarray(ring.coords, dtype=float)
        return

    if geometry.geom_type == "MultiPolygon":
        for polygon in geometry.geoms:
            yield np.asarray(polygon.exterior.coords, dtype=float)
            for ring in polygon.interiors:
                yield np.asarray(ring.coords, dtype=float)
        return

    raise ValueError(f"Unsupported geometry type: {geometry.geom_type}")


def geometry_bounds(geometries):
    min_x = min(geometry.bounds[0] for geometry in geometries)
    min_y = min(geometry.bounds[1] for geometry in geometries)
    max_x = max(geometry.bounds[2] for geometry in geometries)
    max_y = max(geometry.bounds[3] for geometry in geometries)
    return min_x, min_y, max_x, max_y


def build_grid(x, y, x_edges, y_edges):
    grid, _, _ = np.histogram2d(x, y, bins=[x_edges, y_edges])
    return grid.T


def precompute_point_grid_indices(x, y, x_edges, y_edges):
    rows = len(y_edges) - 1
    cols = len(x_edges) - 1

    x_idx = np.searchsorted(x_edges, x, side="right") - 1
    y_idx = np.searchsorted(y_edges, y, side="right") - 1
    # Match numpy.histogram2d edge semantics: include points exactly on the
    # final edge in the last bin.
    grid_x_idx = np.where((x_idx == cols) & (x == x_edges[-1]), cols - 1, x_idx)
    grid_y_idx = np.where((y_idx == rows) & (y == y_edges[-1]), rows - 1, y_idx)

    valid = (
        (grid_x_idx >= 0)
        & (grid_x_idx < cols)
        & (grid_y_idx >= 0)
        & (grid_y_idx < rows)
    )
    flat_cell_idx = grid_y_idx * cols + grid_x_idx
    return rows, cols, flat_cell_idx, valid


def build_grid_from_precomputed_indices(flat_cell_idx, valid_xy, z_mask, rows, cols):
    valid = valid_xy & z_mask
    grid = np.bincount(flat_cell_idx[valid], minlength=rows * cols).reshape(rows, cols)
    return grid.astype(float)


def band_mask(values, value_min, value_max):
    mask = values >= value_min
    if np.isclose(value_max, np.max(values)):
        return mask & (values <= value_max)
    return mask & (values < value_max)


def largest_contiguous_component_area(grid, cellsize):
    occupied = grid > 0
    if not np.any(occupied):
        return 0.0

    visited = np.zeros_like(occupied, dtype=bool)
    rows, cols = occupied.shape
    largest_component_cells = 0

    for row in range(rows):
        for col in range(cols):
            if not occupied[row, col] or visited[row, col]:
                continue

            stack = [(row, col)]
            visited[row, col] = True
            component_cells = 0

            while stack:
                current_row, current_col = stack.pop()
                component_cells += 1

                for neighbor_row in range(max(0, current_row - 1), min(rows, current_row + 2)):
                    for neighbor_col in range(max(0, current_col - 1), min(cols, current_col + 2)):
                        if neighbor_row == current_row and neighbor_col == current_col:
                            continue
                        if occupied[neighbor_row, neighbor_col] and not visited[neighbor_row, neighbor_col]:
                            visited[neighbor_row, neighbor_col] = True
                            stack.append((neighbor_row, neighbor_col))

            largest_component_cells = max(largest_component_cells, component_cells)

    return largest_component_cells * (cellsize ** 2)


def candidate_peak_summary(layer, output_rank_by_peak_idx):
    peak_idx = layer["peak_idx"]
    output_rank = output_rank_by_peak_idx.get(peak_idx)
    return {
        "rank": None if output_rank is None else int(output_rank),
        "peak_idx": int(peak_idx),
        "elevation": float(layer["peak_center"]),
        "z_min": float(layer["z_min"]),
        "z_max": float(layer["z_max"]),
        "point_count": int(layer["point_count"]),
        "area_m2": float(layer["area"]),
        "largest_contiguous_area_m2": float(layer["largest_component_area"]),
        "raw_count": int(layer["raw_count"]),
        "smoothed_count": float(layer["smoothed_count"]),
    }


def estimate_underpass_height_from_points(identifier, x, y, z, geometries, verbose=True):
    bag_id = str(identifier)

    if verbose:
        print(f"\n=== {bag_id} ===")

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = np.asarray(z, dtype=float)
    if x.shape != y.shape or x.shape != z.shape:
        raise ValueError("x, y, and z arrays must have the same shape")

    finite = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    if not finite.all():
        x = x[finite]
        y = y[finite]
        z = z[finite]
    if z.size == 0:
        raise ValueError("No finite points available for height estimation")

    geometries = [geometry for geometry in geometries if geometry is not None and not geometry.is_empty]
    if not geometries:
        raise ValueError("No polygon geometries available for height estimation")

    polygon_area_m2 = float(unary_union(geometries).area)
    polygon_relative_mask_area_threshold_m2 = polygon_relative_mask_area_threshold(
        polygon_area_m2
    )
    effective_mask_area_threshold_m2 = max(
        PEAK_MIN_MASK_AREA_M2,
        polygon_relative_mask_area_threshold_m2,
    )

    (
        counts,
        bin_edges,
        bin_centers,
        smoothed_counts,
        candidate_peak_indices,
    ) = find_top_histogram_peaks(
        z,
        bin_width_meters=HISTOGRAM_BIN_WIDTH_METERS,
        anchor_elevation_meters=HISTOGRAM_ANCHOR_ELEVATION_METERS,
        smoothing_window=7,
        min_separation_bins=PEAK_MIN_SEPARATION_BINS,
    )
    if not candidate_peak_indices:
        raise ValueError("No Z histogram peaks found")

    min_x, min_y, max_x, max_y = geometry_bounds(geometries)
    x_edges = np.arange(min_x, max_x + GRID_CELLSIZE, GRID_CELLSIZE)
    y_edges = np.arange(min_y, max_y + GRID_CELLSIZE, GRID_CELLSIZE)

    if x_edges[-1] < max_x:
        x_edges = np.append(x_edges, max_x)
    if y_edges[-1] < max_y:
        y_edges = np.append(y_edges, max_y)

    (
        grid_rows,
        grid_cols,
        flat_grid_cell_idx,
        valid_grid_xy,
    ) = precompute_point_grid_indices(
        x,
        y,
        x_edges,
        y_edges,
    )

    z_min_all = np.min(z)
    z_max_all = np.max(z)

    def build_peak_layer(peak_idx):
        refined_peak_idx = peak_idx
        if SNAP_PEAK_TO_RAW_BIN_WITHIN_CLUSTER:
            refined_peak_idx = refine_peak_index_within_cluster(counts, smoothed_counts, peak_idx)
        peak_center = bin_centers[refined_peak_idx]
        z_min, z_max = peak_band_from_center(
            peak_center,
            z_min_all,
            z_max_all,
            PEAK_BAND_WIDTH_METERS,
        )
        mask = band_mask(z, z_min, z_max)
        grid = build_grid_from_precomputed_indices(
            flat_grid_cell_idx,
            valid_grid_xy,
            mask,
            grid_rows,
            grid_cols,
        )
        area = np.count_nonzero(grid) * (GRID_CELLSIZE ** 2)
        layer = {
            "peak_idx": peak_idx,
            "refined_peak_idx": refined_peak_idx,
            "peak_center": peak_center,
            "z_min": z_min,
            "z_max": z_max,
            "point_count": np.count_nonzero(mask),
            "grid": grid,
            "area": area,
            "largest_component_area": largest_contiguous_component_area(grid, GRID_CELLSIZE),
            "smoothed_count": smoothed_counts[peak_idx],
            "raw_count": counts[refined_peak_idx],
        }
        return layer

    candidate_layers_by_idx = {
        peak_idx: build_peak_layer(peak_idx)
        for peak_idx in candidate_peak_indices
    }
    separated_candidate_layers = [
        candidate_layers_by_idx[peak_idx]
        for peak_idx in candidate_peak_indices
    ]
    candidate_layers_by_height = sorted(separated_candidate_layers, key=lambda layer: layer["peak_center"])

    ranked_candidate_layers = sorted(
        separated_candidate_layers,
        key=lambda layer: (layer["largest_component_area"], layer["area"], layer["smoothed_count"]),
        reverse=True,
    )
    if verbose:
        print(f"Number of points: {len(z)}")
        print(f"Z range: [{z_min_all:.2f}, {z_max_all:.2f}]")
        print(f"Z mean: {np.mean(z):.2f}, std: {np.std(z):.2f}")
        print("Candidate peaks ranked by largest contiguous XY area:")
        for i, layer in enumerate(ranked_candidate_layers, start=1):
            print(
                f"  Candidate {i}: z ~= {layer['peak_center']:.2f} m, "
                f"largest contiguous area {layer['largest_component_area']:.2f} m^2, "
                f"covered area {layer['area']:.2f} m^2, "
                f"smoothed count {layer['smoothed_count']:.1f}, raw count {layer['raw_count']}"
            )

    display_raw_count_threshold = relative_raw_count_threshold(
        layer["raw_count"] for layer in separated_candidate_layers
    )
    effective_raw_count_threshold = max(
        PEAK_MIN_RAW_COUNT,
        display_raw_count_threshold,
    )

    ranked_output_layers = [
        layer
        for layer in ranked_candidate_layers
        if (
            layer["raw_count"] >= effective_raw_count_threshold
            and layer["area"] >= effective_mask_area_threshold_m2
        )
    ]
    display_peak_layers = sorted(
        ranked_output_layers,
        key=lambda layer: layer["peak_center"],
    )
    if verbose:
        print(
            f"Selected {len(ranked_output_layers)} candidate peaks with raw count >= "
            f"{effective_raw_count_threshold:.1f} (max of absolute {PEAK_MIN_RAW_COUNT} "
            f"and relative {display_raw_count_threshold:.1f}) and total mask area >= "
            f"{effective_mask_area_threshold_m2:.2f} m^2 (max of absolute "
            f"{PEAK_MIN_MASK_AREA_M2:.2f} m^2 and "
            f"{PEAK_MIN_MASK_AREA_POLYGON_FRACTION:.0%} of polygon area, "
            f"{polygon_relative_mask_area_threshold_m2:.2f} m^2)."
        )

    output_rank_by_peak_idx = {
        layer["peak_idx"]: rank
        for rank, layer in enumerate(ranked_output_layers, start=1)
    }
    candidate_peak_summaries = [
        candidate_peak_summary(layer, output_rank_by_peak_idx)
        for layer in ranked_candidate_layers
    ]

    if verbose:
        for i, layer in enumerate(display_peak_layers, start=1):
            print(
                f"Peak {i}: z ~= {layer['peak_center']:.2f} m, "
                f"Z range [{layer['z_min']:.2f}, {layer['z_max']:.2f}), "
                f"points {layer['point_count']}, "
                f"area {layer['area']:.2f} m^2, "
                f"largest contiguous area {layer['largest_component_area']:.2f} m^2"
            )

    underpass_metrics = {
        "identificatie": bag_id,
        "underpass_candidate_elevations": [
            float(layer["peak_center"]) for layer in ranked_output_layers
        ],
        "underpass_metadata": {
            "candidate_peaks": candidate_peak_summaries,
        },
    }

    return {
        "bag_id": bag_id,
        "x": x,
        "y": y,
        "z": z,
        "counts": counts,
        "bin_edges": bin_edges,
        "bin_centers": bin_centers,
        "smoothed_counts": smoothed_counts,
        "candidate_peak_indices": candidate_peak_indices,
        "geometries": geometries,
        "bounds": (min_x, min_y, max_x, max_y),
        "x_edges": x_edges,
        "y_edges": y_edges,
        "candidate_layers": separated_candidate_layers,
        "candidate_layers_by_height": candidate_layers_by_height,
        "ranked_candidate_layers": ranked_candidate_layers,
        "ranked_output_layers": ranked_output_layers,
        "display_peak_layers": display_peak_layers,
        "peak_min_raw_count": PEAK_MIN_RAW_COUNT,
        "display_peak_min_relative_raw_count": PEAK_MIN_RELATIVE_RAW_COUNT,
        "display_raw_count_threshold": display_raw_count_threshold,
        "effective_raw_count_threshold": effective_raw_count_threshold,
        "peak_min_mask_area_m2": PEAK_MIN_MASK_AREA_M2,
        "polygon_area_m2": polygon_area_m2,
        "peak_min_mask_area_polygon_fraction": PEAK_MIN_MASK_AREA_POLYGON_FRACTION,
        "polygon_relative_mask_area_threshold_m2": polygon_relative_mask_area_threshold_m2,
        "effective_mask_area_threshold_m2": effective_mask_area_threshold_m2,
        "underpass_metrics": underpass_metrics,
    }


def estimate_underpass_height(las_path, gpkg_path, verbose=True):
    las = laspy.read(las_path)
    geometries = load_polygon_geometries(gpkg_path)
    return estimate_underpass_height_from_points(
        Path(las_path).stem,
        np.asarray(las.x, dtype=float),
        np.asarray(las.y, dtype=float),
        np.asarray(las.z, dtype=float),
        geometries,
        verbose=verbose,
    )
