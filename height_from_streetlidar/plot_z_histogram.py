import csv
import laspy
import matplotlib.pyplot as plt
import numpy as np
import rerun as rr
import sqlite3
from pathlib import Path
from matplotlib.colors import LinearSegmentedColormap
from shapely import wkb


CASES = [
    {
        "las_path": "data/weesperstraat/NL.IMBAG.Pand.0363100012165755.laz",
        "gpkg_path": "data/weesperstraat/NL.IMBAG.Pand.0363100012165755.gpkg"
    },
    {
        "las_path": "data/weesperstraat/NL.IMBAG.Pand.0363100012170850.laz",
        "gpkg_path": "data/weesperstraat/NL.IMBAG.Pand.0363100012170850.gpkg"
    },
    {
        "las_path": "data/beemsterstraat/NL.IMBAG.Pand.0363100012095711.laz",
        "gpkg_path": "data/beemsterstraat/NL.IMBAG.Pand.0363100012095711.gpkg",
    },
    {
        "las_path": "data/beemsterstraat/NL.IMBAG.Pand.0363100012122448.laz",
        "gpkg_path": "data/beemsterstraat/NL.IMBAG.Pand.0363100012122448.gpkg",
    },
    {
        "las_path": "data/beemsterstraat/NL.IMBAG.Pand.0363100012137139.laz",
        "gpkg_path": "data/beemsterstraat/NL.IMBAG.Pand.0363100012137139.gpkg",
    },
    {
        "las_path": "data/beemsterstraat/NL.IMBAG.Pand.0363100012146576.laz",
        "gpkg_path": "data/beemsterstraat/NL.IMBAG.Pand.0363100012146576.gpkg",
    },
]

# Peak-detection and output parameters.
# `HISTOGRAM_BINS` controls the Z histogram resolution used both for plotting
# and for peak detection.
HISTOGRAM_BINS = 100

# XY raster cell size in meters for the per-peak occupancy grids.
GRID_CELLSIZE = 0.5

# Width of the Z band, centered on each selected peak, used to subset LAS
# points for the raster outputs and reported peak windows.
PEAK_BAND_WIDTH_METERS = 1

# Candidate peaks with raw counts below this fraction of the second-highest
# candidate raw count are not shown in the diagnostic plots and are not
# considered for the final two-peak selection.
DISPLAY_PEAK_MIN_RELATIVE_RAW_COUNT = 0.05

# When enabled, the selected peak is snapped from the smoothed local maximum to
# the highest raw histogram bin inside that smoothed peak cluster.
SNAP_PEAK_TO_RAW_BIN_WITHIN_CLUSTER = True

# A cell is treated as a vertical wall when points occupy nearly every
# histogram bin between the two selected underpass peaks.
VERTICAL_WALL_MIN_BIN_FRACTION = 0.85
VERTICAL_WALL_MAX_EMPTY_RUN_BINS = 1

# Optional diagnostic rows in the matplotlib output.
SHOW_EXCLUSIVE_ROW = False
SHOW_RELATED_WALL_ROW = False

# Output filenames, Rerun mode, and visualization colors.
OUTPUT_CSV_PATH = "underpass_heights.csv"
RERUN_OUTPUT_MODE = "viewer"  # "rrd" or "viewer"
RERUN_OUTPUT_SUFFIX = "_peak_planes.rrd"
RERUN_BASE_POINT_COLOR = (150, 150, 150)
PEAK_RGB_COLORS = {
    1: (31, 119, 180),
    2: (255, 127, 14),
    3: (44, 160, 44),
    4: (214, 39, 40),
}
PEAK_CMAP_NAMES = [
    "Blues",
    "Oranges",
    "Greens",
    "Reds",
    "Purples",
    "Greys",
    "YlGnBu",
    "YlOrBr",
]


def find_top_histogram_peaks(values, bins=100, smoothing_window=7, min_separation_bins=10):
    counts, bin_edges = np.histogram(values, bins=bins)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    # Smooth the histogram slightly so one broad mode does not produce several
    # adjacent local maxima from binning noise.
    kernel = np.hanning(smoothing_window)
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


def build_vertical_wall_mask(
    x,
    y,
    z,
    x_edges,
    y_edges,
    bin_edges,
    lower_peak_idx,
    upper_peak_idx,
    min_bin_fraction,
    max_empty_run_bins,
):
    rows = len(y_edges) - 1
    cols = len(x_edges) - 1
    wall_mask = np.zeros((rows, cols), dtype=bool)

    if rows == 0 or cols == 0:
        return wall_mask

    start_idx = min(lower_peak_idx, upper_peak_idx)
    stop_idx = max(lower_peak_idx, upper_peak_idx)
    if stop_idx <= start_idx:
        return wall_mask

    x_idx = np.searchsorted(x_edges, x, side="right") - 1
    y_idx = np.searchsorted(y_edges, y, side="right") - 1
    z_idx = np.searchsorted(bin_edges, z, side="right") - 1

    bin_count = len(bin_edges) - 1
    valid = (
        (x_idx >= 0)
        & (x_idx < cols)
        & (y_idx >= 0)
        & (y_idx < rows)
        & (z_idx >= start_idx)
        & (z_idx <= stop_idx)
        & (z_idx < bin_count)
    )
    if not np.any(valid):
        return wall_mask

    interval_bin_count = stop_idx - start_idx + 1
    occupied_bins = np.zeros((rows * cols, interval_bin_count), dtype=bool)
    flat_cell_idx = y_idx[valid] * cols + x_idx[valid]
    interval_z_idx = z_idx[valid] - start_idx
    occupied_bins[flat_cell_idx, interval_z_idx] = True

    occupied_fraction = occupied_bins.mean(axis=1)
    endpoint_hits = occupied_bins[:, 0] & occupied_bins[:, -1]

    empty_bins = ~occupied_bins
    padded_empty_bins = np.pad(empty_bins.astype(np.int16), ((0, 0), (1, 1)), constant_values=0)
    transitions = np.diff(padded_empty_bins, axis=1)
    run_starts = transitions == 1
    run_stops = transitions == -1
    run_lengths = np.where(run_stops)[1] - np.where(run_starts)[1]
    max_empty_run = np.zeros(rows * cols, dtype=int)
    if len(run_lengths) > 0:
        np.maximum.at(max_empty_run, np.where(run_starts)[0], run_lengths)

    wall_mask.flat[:] = (
        endpoint_hits
        & (occupied_fraction >= min_bin_fraction)
        & (max_empty_run <= max_empty_run_bins)
    )
    return wall_mask


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


def select_underpass_peak_indices(candidate_layers, area_key="largest_component_area"):
    if not candidate_layers:
        return []

    area_ranked_layers = sorted(
        candidate_layers,
        key=lambda layer: (layer[area_key], layer["area"]),
        reverse=True,
    )
    selected_layers = area_ranked_layers[:2]

    selected_layers.sort(key=lambda layer: layer["peak_center"])
    return [layer["peak_idx"] for layer in selected_layers]


def make_truncated_cmap(name, start=0.25, end=1.0):
    base_cmap = plt.get_cmap(name)
    colors = base_cmap(np.linspace(start, end, 256))
    cmap = LinearSegmentedColormap.from_list(f"{name}_truncated", colors)
    cmap.set_bad((0, 0, 0, 0))
    return cmap


def peak_plot_color(peak_number):
    if peak_number <= 10:
        return f"C{(peak_number - 1) % 10}"
    return plt.get_cmap("tab20")((peak_number - 1) % 20)


def peak_rgb_color(peak_number):
    if peak_number in PEAK_RGB_COLORS:
        return PEAK_RGB_COLORS[peak_number]
    rgba = plt.get_cmap("tab20")((peak_number - 1) % 20)
    return tuple(int(round(channel * 255)) for channel in rgba[:3])


def peak_fill_cmap(peak_number):
    return make_truncated_cmap(PEAK_CMAP_NAMES[(peak_number - 1) % len(PEAK_CMAP_NAMES)], start=0.28)


def plot_geometry_outline(ax, geometries):
    label_added = False
    for geometry in geometries:
        for ring in iter_rings(geometry):
            ax.plot(
                ring[:, 0],
                ring[:, 1],
                color="black",
                linewidth=2,
                label="Polygon" if not label_added else None,
            )
            label_added = True


def write_rerun_visualization(
    bag_id,
    x,
    y,
    z,
    min_x,
    min_y,
    max_x,
    max_y,
    peak_layers,
):
    output_path = f"{bag_id}{RERUN_OUTPUT_SUFFIX}"
    send_to_viewer = RERUN_OUTPUT_MODE == "viewer"
    rr.init(
        f"underpass_height_{bag_id}",
        recording_id=bag_id,
        spawn=send_to_viewer,
    )
    if not send_to_viewer:
        rr.save(output_path)

    origin_x = (min_x + max_x) / 2
    origin_y = (min_y + max_y) / 2
    rr.log(
        "metadata/rd_origin",
        rr.TextDocument(
            f"BAG id: {bag_id}\n"
            f"RD origin x: {origin_x:.3f}\n"
            f"RD origin y: {origin_y:.3f}\n"
            "Geometry in this recording is expressed in local coordinates "
            "relative to the origin above."
        ),
    )

    local_x = x - origin_x
    local_y = y - origin_y
    points = np.column_stack((local_x, local_y, z)).astype(np.float32)
    rr.log(
        "local/pointcloud/all",
        rr.Points3D(points, radii=0.02, colors=[RERUN_BASE_POINT_COLOR]),
    )

    for peak_number, layer in enumerate(peak_layers, start=1):
        if np.isclose(layer["z_max"], np.max(z)):
            mask = (z >= layer["z_min"]) & (z <= layer["z_max"])
        else:
            mask = (z >= layer["z_min"]) & (z < layer["z_max"])
        peak_points = np.column_stack((local_x[mask], local_y[mask], z[mask])).astype(np.float32)

        rr.log(
            f"local/pointcloud/peak_{peak_number}",
            rr.Points3D(
                peak_points,
                radii=0.03,
                colors=[peak_rgb_color(peak_number)],
            ),
        )

    rr.disconnect()
    if send_to_viewer:
        print(f"Sent Rerun visualization for {bag_id} to viewer")
    else:
        print(f"Saved Rerun visualization to {output_path}")


def process_case(las_path, gpkg_path):
    bag_id = Path(las_path).stem
    output_path = f"{bag_id}_peak_grids_overlay.png"

    print(f"\n=== {bag_id} ===")

    las = laspy.read(las_path)
    x = np.asarray(las.x, dtype=float)
    y = np.asarray(las.y, dtype=float)
    z = np.asarray(las.z, dtype=float)

    (
        counts,
        bin_edges,
        bin_centers,
        smoothed_counts,
        candidate_peak_indices,
    ) = find_top_histogram_peaks(
        z,
        bins=HISTOGRAM_BINS,
        smoothing_window=7,
        min_separation_bins=10,
    )
    geometries = load_polygon_geometries(gpkg_path)

    min_x, min_y, max_x, max_y = geometry_bounds(geometries)
    x_edges = np.arange(min_x, max_x + GRID_CELLSIZE, GRID_CELLSIZE)
    y_edges = np.arange(min_y, max_y + GRID_CELLSIZE, GRID_CELLSIZE)

    if x_edges[-1] < max_x:
        x_edges = np.append(x_edges, max_x)
    if y_edges[-1] < max_y:
        y_edges = np.append(y_edges, max_y)

    def build_peak_layer(peak_idx):
        refined_peak_idx = peak_idx
        if SNAP_PEAK_TO_RAW_BIN_WITHIN_CLUSTER:
            refined_peak_idx = refine_peak_index_within_cluster(counts, smoothed_counts, peak_idx)
        peak_center = bin_centers[refined_peak_idx]
        z_min, z_max = peak_band_from_center(
            peak_center,
            np.min(z),
            np.max(z),
            PEAK_BAND_WIDTH_METERS,
        )
        mask = band_mask(z, z_min, z_max)
        grid = build_grid(x[mask], y[mask], x_edges, y_edges)
        area = np.count_nonzero(grid) * (GRID_CELLSIZE ** 2)
        return {
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

    candidate_layers_by_idx = {
        peak_idx: build_peak_layer(peak_idx)
        for peak_idx in candidate_peak_indices
    }
    separated_candidate_layers = [
        candidate_layers_by_idx[peak_idx]
        for peak_idx in candidate_peak_indices
    ]
    candidate_layers_by_height = sorted(separated_candidate_layers, key=lambda layer: layer["peak_center"])

    print(f"Number of points: {len(z)}")
    print(f"Z range: [{np.min(z):.2f}, {np.max(z):.2f}]")
    print(f"Z mean: {np.mean(z):.2f}, std: {np.std(z):.2f}")
    print("Candidate peaks ranked by largest contiguous XY area:")
    ranked_candidate_layers = sorted(
        separated_candidate_layers,
        key=lambda layer: (layer["largest_component_area"], layer["area"], layer["smoothed_count"]),
        reverse=True,
    )
    for i, layer in enumerate(ranked_candidate_layers, start=1):
        print(
            f"  Candidate {i}: z ~= {layer['peak_center']:.2f} m, "
            f"largest contiguous area {layer['largest_component_area']:.2f} m^2, "
            f"covered area {layer['area']:.2f} m^2, "
            f"smoothed count {layer['smoothed_count']:.1f}, raw count {layer['raw_count']}"
        )

    candidate_raw_counts = sorted((layer["raw_count"] for layer in separated_candidate_layers), reverse=True)
    if len(candidate_raw_counts) >= 2:
        display_raw_count_threshold = (
            DISPLAY_PEAK_MIN_RELATIVE_RAW_COUNT * candidate_raw_counts[1]
        )
    elif candidate_raw_counts:
        display_raw_count_threshold = DISPLAY_PEAK_MIN_RELATIVE_RAW_COUNT * candidate_raw_counts[0]
    else:
        display_raw_count_threshold = 0.0
    display_peak_layers = [
        layer
        for layer in candidate_layers_by_height
        if layer["raw_count"] >= display_raw_count_threshold
    ]
    if not display_peak_layers and candidate_layers_by_height:
        display_peak_layers = [candidate_layers_by_height[0]]
    print(
        f"Displaying {len(display_peak_layers)} candidate peaks with raw count >= "
        f"{display_raw_count_threshold:.1f} "
        f"(5% of second-highest candidate raw count)."
    )

    occupied_by_lower_non_floor_peaks = np.zeros_like(display_peak_layers[0]["grid"], dtype=bool)
    for display_peak_idx, layer in sorted(
        enumerate(display_peak_layers, start=1),
        key=lambda item: item[1]["peak_center"],
    ):
        if display_peak_idx == 1:
            exclusive_grid = layer["grid"]
        else:
            exclusive_grid = np.where(occupied_by_lower_non_floor_peaks, 0, layer["grid"])
        layer["exclusive_grid"] = exclusive_grid
        layer["exclusive_area"] = np.count_nonzero(exclusive_grid) * (GRID_CELLSIZE ** 2)
        layer["exclusive_largest_component_area"] = largest_contiguous_component_area(
            exclusive_grid,
            GRID_CELLSIZE,
        )
        if display_peak_idx != 1:
            occupied_by_lower_non_floor_peaks |= layer["grid"] > 0
    pairwise_wall_masks = []
    for upper_peak_idx in range(1, len(display_peak_layers)):
        lower_layer = display_peak_layers[upper_peak_idx - 1]
        upper_layer = display_peak_layers[upper_peak_idx]
        pairwise_wall_masks.append(
            build_vertical_wall_mask(
                x,
                y,
                z,
                x_edges,
                y_edges,
                bin_edges,
                lower_layer["refined_peak_idx"],
                upper_layer["refined_peak_idx"],
                min_bin_fraction=VERTICAL_WALL_MIN_BIN_FRACTION,
                max_empty_run_bins=VERTICAL_WALL_MAX_EMPTY_RUN_BINS,
            )
        )
    for display_peak_idx, layer in enumerate(display_peak_layers, start=1):
        related_wall_mask = np.zeros_like(layer["grid"], dtype=bool)
        if display_peak_idx > 1:
            related_wall_mask |= pairwise_wall_masks[display_peak_idx - 2]
        if display_peak_idx < len(display_peak_layers):
            related_wall_mask |= pairwise_wall_masks[display_peak_idx - 1]
        layer["related_wall_grid"] = related_wall_mask.astype(float)
        layer["related_wall_area"] = np.count_nonzero(related_wall_mask) * (GRID_CELLSIZE ** 2)
    for layer in display_peak_layers:
        exclusive_or_wall_grid = np.where(
            (layer["exclusive_grid"] > 0) | (layer["related_wall_grid"] > 0),
            np.maximum(layer["exclusive_grid"], layer["related_wall_grid"]),
            0,
        )
        layer["exclusive_or_wall_grid"] = exclusive_or_wall_grid
        layer["exclusive_or_wall_area"] = np.count_nonzero(exclusive_or_wall_grid) * (GRID_CELLSIZE ** 2)
        layer["exclusive_or_wall_largest_component_area"] = largest_contiguous_component_area(
            exclusive_or_wall_grid,
            GRID_CELLSIZE,
        )

        corrected_grid = np.where(
            (layer["exclusive_grid"] > 0) & (layer["related_wall_grid"] == 0),
            layer["exclusive_grid"],
            0,
        )
        layer["corrected_largest_component_area"] = largest_contiguous_component_area(
            corrected_grid,
            GRID_CELLSIZE,
        )

    peak_indices = select_underpass_peak_indices(
        display_peak_layers,
        area_key="exclusive_or_wall_largest_component_area",
    )
    selected_peak_layers = [
        layer for layer in display_peak_layers
        if layer["peak_idx"] in peak_indices
    ]

    for i, layer in enumerate(display_peak_layers, start=1):
        print(
            f"Peak {i}: z ~= {layer['peak_center']:.2f} m, "
            f"Z range [{layer['z_min']:.2f}, {layer['z_max']:.2f}), "
            f"points {layer['point_count']}, "
            f"area {layer['area']:.2f} m^2, "
            f"largest contiguous area {layer['largest_component_area']:.2f} m^2, "
            f"corrected contiguous area {layer['corrected_largest_component_area']:.2f} m^2"
        )

    underpass_attributes = {
        "underpass_dh": selected_peak_layers[-1]["peak_center"] - selected_peak_layers[0]["peak_center"],
        "underpass_top_area": selected_peak_layers[-1]["area"],
        "underpass_bottom_area": selected_peak_layers[0]["area"],
    }
    underpass_metrics = {
        "identificatie": bag_id,
        "underpass_z_min": selected_peak_layers[0]["z_min"],
        "underpass_z_max": selected_peak_layers[-1]["z_max"],
        "underpass_h": underpass_attributes["underpass_dh"],
    }

    map_width = max_x - min_x
    map_height = max_y - min_y
    map_aspect_ratio = map_width / map_height if map_height > 0 else 1.0
    map_panel_width_ratio = max(0.7, map_aspect_ratio)
    ncols = len(display_peak_layers)
    width_ratios = [map_panel_width_ratio] * ncols
    figure_width = 5 * sum(width_ratios)
    map_row_count = 2 + int(SHOW_EXCLUSIVE_ROW) + int(SHOW_RELATED_WALL_ROW)
    total_rows = 1 + map_row_count
    fig = plt.figure(figsize=(figure_width, 4.5 + 4.0 * total_rows))
    grid_spec = fig.add_gridspec(
        total_rows,
        ncols,
        width_ratios=width_ratios,
        height_ratios=[0.72] + [1.0] * map_row_count,
        wspace=0.06,
        hspace=0.30,
    )
    ax_hist = fig.add_subplot(grid_spec[0, :])
    current_row = 1
    peak_axes = [fig.add_subplot(grid_spec[current_row, idx]) for idx in range(ncols)]
    current_row += 1
    if SHOW_EXCLUSIVE_ROW:
        exclusive_peak_axes = [fig.add_subplot(grid_spec[current_row, idx]) for idx in range(ncols)]
        current_row += 1
    else:
        exclusive_peak_axes = []
    if SHOW_RELATED_WALL_ROW:
        wall_peak_axes = [fig.add_subplot(grid_spec[current_row, idx]) for idx in range(ncols)]
        current_row += 1
    else:
        wall_peak_axes = []
    combined_peak_axes = [fig.add_subplot(grid_spec[current_row, idx]) for idx in range(ncols)]

    def style_peak_map_axis(ax_map, map_idx, show_xlabel):
        if show_xlabel:
            ax_map.set_xlabel("X")
        else:
            ax_map.set_xlabel("")
            ax_map.tick_params(axis="x", which="both", bottom=False, labelbottom=False)
        if map_idx == 1:
            ax_map.set_ylabel("Y")
        else:
            ax_map.set_ylabel("")
            ax_map.tick_params(axis="y", which="both", left=False, labelleft=False)

    ax_hist.hist(
        z,
        bins=HISTOGRAM_BINS,
        color="gray",
        edgecolor="#999999",
        linewidth=0.25,
    )
    ax_hist.plot(
        bin_centers,
        smoothed_counts,
        color="black",
        linewidth=2,
        label="Smoothed histogram",
    )
    for i, layer in enumerate(display_peak_layers, start=1):
        ax_hist.axvline(
            layer["peak_center"],
            linestyle="--",
            linewidth=1.5,
            color=peak_plot_color(i),
        )
        ax_hist.axvspan(
            layer["z_min"],
            layer["z_max"],
            alpha=0.15,
            color=peak_plot_color(i),
        )
    ax_hist.set_xlabel("Z (m)")
    ax_hist.set_ylabel("Count")
    ax_hist.set_title("Histogram of Z values", fontsize=13, pad=8)
    ax_hist.spines["top"].set_visible(False)
    ax_hist.spines["right"].set_visible(False)

    arrow_y = counts.max() * 0.92
    label_y = counts.max() * 0.97
    left_peak = selected_peak_layers[0]["peak_center"]
    right_peak = selected_peak_layers[-1]["peak_center"]
    ax_hist.annotate(
        "",
        xy=(right_peak, arrow_y),
        xytext=(left_peak, arrow_y),
        arrowprops={"arrowstyle": "<->", "color": "black", "linewidth": 1.8},
    )
    ax_hist.text(
        (left_peak + right_peak) / 2,
        label_y,
        f"{underpass_attributes['underpass_dh']:.2f} m",
        ha="center",
        va="bottom",
        fontsize=11,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.8, "pad": 2},
    )

    extent = [x_edges[0], x_edges[-1], y_edges[0], y_edges[-1]]
    for map_idx, (ax_map, layer) in enumerate(zip(peak_axes, display_peak_layers), start=1):
        masked_grid = np.ma.masked_where(layer["grid"] == 0, layer["grid"])
        ax_map.set_facecolor("#f3f3f3")
        ax_map.imshow(
            masked_grid,
            origin="lower",
            extent=extent,
            cmap=peak_fill_cmap(map_idx),
            alpha=0.9,
            interpolation="nearest",
        )
        plot_geometry_outline(ax_map, geometries)
        style_peak_map_axis(ax_map, map_idx, show_xlabel=False)
        ax_map.set_title(
            f"Peak {map_idx}: {layer['peak_center']:.2f} m\n"
            f"Z range [{layer['z_min']:.2f}, {layer['z_max']:.2f})\n"
            f"Total area {layer['area']:.2f} m^2\n"
            f"Largest contiguous area {layer['largest_component_area']:.2f} m^2",
            fontsize=11,
            pad=8,
        )
        ax_map.set_aspect("equal")
        ax_map.legend(loc="best")

    if SHOW_EXCLUSIVE_ROW:
        for map_idx, (ax_map, layer) in enumerate(zip(exclusive_peak_axes, display_peak_layers), start=1):
            masked_grid = np.ma.masked_where(layer["exclusive_grid"] == 0, layer["exclusive_grid"])
            ax_map.set_facecolor("#f3f3f3")
            ax_map.imshow(
                masked_grid,
                origin="lower",
                extent=extent,
                cmap=peak_fill_cmap(map_idx),
                alpha=0.9,
                interpolation="nearest",
            )
            plot_geometry_outline(ax_map, geometries)
            style_peak_map_axis(ax_map, map_idx, show_xlabel=False)
            ax_map.set_title(
                "Masking cells occupied by lower peaks except Peak 1\n"
                f"Total area {layer['exclusive_area']:.2f} m^2\n"
                f"Largest contiguous area {layer['exclusive_largest_component_area']:.2f} m^2",
                fontsize=11,
                pad=8,
            )
            ax_map.set_aspect("equal")
            ax_map.legend(loc="best")

    if SHOW_RELATED_WALL_ROW:
        for map_idx, (ax_map, layer) in enumerate(zip(wall_peak_axes, display_peak_layers), start=1):
            masked_grid = np.ma.masked_where(layer["related_wall_grid"] == 0, layer["related_wall_grid"])
            if map_idx == 1:
                wall_title_line = "Walls between Peak 1 and Peak 2"
            elif map_idx == len(display_peak_layers):
                wall_title_line = f"Walls between Peak {map_idx - 1} and Peak {map_idx}"
            else:
                wall_title_line = (
                    f"Walls between Peaks {map_idx - 1}/{map_idx} and Peaks {map_idx}/{map_idx + 1}"
                )
            ax_map.set_facecolor("#f3f3f3")
            ax_map.imshow(
                masked_grid,
                origin="lower",
                extent=extent,
                cmap=peak_fill_cmap(map_idx),
                alpha=0.95,
                interpolation="nearest",
            )
            plot_geometry_outline(ax_map, geometries)
            style_peak_map_axis(ax_map, map_idx, show_xlabel=False)
            ax_map.set_title(
                f"{wall_title_line}\n"
                f"Related wall area {layer['related_wall_area']:.2f} m^2",
                fontsize=11,
                pad=8,
            )
            ax_map.set_aspect("equal")
            ax_map.legend(loc="best")

    for map_idx, (ax_map, layer) in enumerate(zip(combined_peak_axes, display_peak_layers), start=1):
        masked_grid = np.ma.masked_where(layer["exclusive_or_wall_grid"] == 0, layer["exclusive_or_wall_grid"])
        ax_map.set_facecolor("#f3f3f3")
        ax_map.imshow(
            masked_grid,
            origin="lower",
            extent=extent,
            cmap=peak_fill_cmap(map_idx),
            alpha=0.95,
            interpolation="nearest",
        )
        plot_geometry_outline(ax_map, geometries)
        style_peak_map_axis(ax_map, map_idx, show_xlabel=True)
        ax_map.set_title(
            "Union of exclusive and pairwise wall cells\n"
            f"Total area {layer['exclusive_or_wall_area']:.2f} m^2\n"
            f"Largest contiguous area {layer['exclusive_or_wall_largest_component_area']:.2f} m^2",
            fontsize=11,
            pad=8,
        )
        ax_map.set_aspect("equal")
        ax_map.legend(loc="best")

    fig.suptitle(bag_id, fontsize=15, y=0.985)
    fig.subplots_adjust(left=0.05, right=0.99, bottom=0.06, top=0.90)
    plt.savefig(output_path, dpi=200, transparent=False)
    print(f"Saved overlay figure to {output_path}")
    plt.close(fig)

    write_rerun_visualization(
        bag_id,
        x,
        y,
        z,
        min_x,
        min_y,
        max_x,
        max_y,
        display_peak_layers,
    )
    return underpass_metrics


def write_metrics_csv(rows, output_path):
    with open(output_path, "w", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["identificatie", "underpass_z_min", "underpass_z_max", "underpass_h"],
        )
        writer.writeheader()
        writer.writerows(rows)


def main():
    rows = []
    # for case in CASES[1:2]:
    for case in CASES:
        rows.append(process_case(case["las_path"], case["gpkg_path"]))

    write_metrics_csv(rows, OUTPUT_CSV_PATH)
    print(f"Saved CSV summary to {OUTPUT_CSV_PATH}")


if __name__ == "__main__":
    main()
