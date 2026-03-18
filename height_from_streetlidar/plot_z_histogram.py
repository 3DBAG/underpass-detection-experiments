import csv
import laspy
import matplotlib.pyplot as plt
import numpy as np
import rerun as rr
import sqlite3
from pathlib import Path
from matplotlib.colors import LinearSegmentedColormap, ListedColormap
from matplotlib.patches import Patch
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

# If the lowest-Z peak has less than this fraction of the dominant peak's
# contiguous raster area, it is treated as insignificant and not forced in as
# one of the two main underpass peaks.
LOWEST_PEAK_MIN_RELATIVE_AREA = 0.1

# Width of the Z band, centered on each selected peak, used to subset LAS
# points for the raster outputs and reported peak windows.
PEAK_BAND_WIDTH_METERS = 0.5

# Number of peak layers to display in the diagnostic output. The first two are
# the selected underpass peaks; any additional peaks are diagnostic only.
DISPLAY_PEAK_COUNT = 4

# When enabled, the selected peak is snapped from the smoothed local maximum to
# the highest raw histogram bin inside that smoothed peak cluster.
SNAP_PEAK_TO_RAW_BIN_WITHIN_CLUSTER = False

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
        ranked_candidates.tolist(),
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


def peak_cluster_from_index(bin_edges, smoothed_counts, peak_idx):
    left_idx, right_idx = peak_cluster_index_bounds(smoothed_counts, peak_idx)
    return bin_edges[left_idx], bin_edges[right_idx + 1]


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


def update_gpkg_attributes(path, attributes):
    table_name = feature_table_name(path)

    with connect_gpkg(path) as con:
        existing_columns = {
            row[1] for row in con.execute(f'pragma table_info("{table_name}")').fetchall()
        }

        for column_name in attributes:
            if column_name not in existing_columns:
                con.execute(f'alter table "{table_name}" add column "{column_name}" REAL')

        assignments = ", ".join(f'"{column_name}" = ?' for column_name in attributes)
        con.execute(f'update "{table_name}" set {assignments}', tuple(attributes.values()))
        con.commit()


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


def build_min_z_grid(x, y, z, x_edges, y_edges):
    rows = len(y_edges) - 1
    cols = len(x_edges) - 1
    min_grid = np.full((rows, cols), np.nan, dtype=float)

    x_idx = np.searchsorted(x_edges, x, side="right") - 1
    y_idx = np.searchsorted(y_edges, y, side="right") - 1
    valid = (
        (x_idx >= 0)
        & (x_idx < cols)
        & (y_idx >= 0)
        & (y_idx < rows)
    )
    if not np.any(valid):
        return min_grid

    flat_indices = y_idx[valid] * cols + x_idx[valid]
    flat_min = np.full(rows * cols, np.inf, dtype=float)
    np.minimum.at(flat_min, flat_indices, z[valid])
    flat_min[np.isinf(flat_min)] = np.nan
    return flat_min.reshape(rows, cols)


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


def select_underpass_peak_indices(candidate_layers, bin_centers):
    if not candidate_layers:
        return []

    area_ranked_layers = sorted(
        candidate_layers,
        key=lambda layer: (layer["largest_component_area"], layer["area"]),
        reverse=True,
    )
    dominant_layer = area_ranked_layers[0]
    lowest_layer = min(candidate_layers, key=lambda layer: layer["peak_center"])
    lowest_peak_ratio = (
        lowest_layer["largest_component_area"] / dominant_layer["largest_component_area"]
        if dominant_layer["largest_component_area"] > 0
        else 0.0
    )

    if len(candidate_layers) == 1:
        selected_layers = [lowest_layer]
    elif lowest_peak_ratio >= LOWEST_PEAK_MIN_RELATIVE_AREA:
        selected_layers = [lowest_layer]
        for layer in area_ranked_layers:
            if layer["peak_idx"] != lowest_layer["peak_idx"]:
                selected_layers.append(layer)
                break
    else:
        selected_layers = area_ranked_layers[:2]

    selected_layers.sort(key=lambda layer: layer["peak_center"])
    return [layer["peak_idx"] for layer in selected_layers]


def make_truncated_cmap(name, start=0.25, end=1.0):
    base_cmap = plt.get_cmap(name)
    colors = base_cmap(np.linspace(start, end, 256))
    cmap = LinearSegmentedColormap.from_list(f"{name}_truncated", colors)
    cmap.set_bad((0, 0, 0, 0))
    return cmap


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

    center_x = ((min_x + max_x) / 2) - origin_x
    center_y = ((min_y + max_y) / 2) - origin_y
    half_size_x = (max_x - min_x) / 2
    half_size_y = (max_y - min_y) / 2

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
                colors=[PEAK_RGB_COLORS[peak_number]],
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
        ranked_candidate_indices,
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

    candidate_layer_by_idx = {
        peak_idx: build_peak_layer(peak_idx)
        for peak_idx in ranked_candidate_indices
    }
    separated_candidate_layers = [
        candidate_layer_by_idx[peak_idx]
        for peak_idx in candidate_peak_indices
    ]
    peak_indices = select_underpass_peak_indices(separated_candidate_layers, bin_centers)
    selected_peak_layers = [candidate_layer_by_idx[peak_idx] for peak_idx in peak_indices]

    print(f"Number of points: {len(z)}")
    print(f"Z range: [{np.min(z):.2f}, {np.max(z):.2f}]")
    print(f"Z mean: {np.mean(z):.2f}, std: {np.std(z):.2f}")
    print("Candidate peaks ranked by largest contiguous XY area:")
    ranked_candidate_layers = sorted(
        (candidate_layer_by_idx[peak_idx] for peak_idx in ranked_candidate_indices),
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

    display_peak_indices = list(peak_indices)
    area_ranked_candidate_indices = [layer["peak_idx"] for layer in ranked_candidate_layers]
    between_peak_candidates = [
        peak_idx
        for peak_idx in area_ranked_candidate_indices
        if peak_idx not in display_peak_indices
        and bin_centers[peak_indices[0]] < bin_centers[peak_idx] < bin_centers[peak_indices[-1]]
    ]
    for peak_idx in between_peak_candidates:
        if len(display_peak_indices) >= DISPLAY_PEAK_COUNT:
            break
        display_peak_indices.append(peak_idx)

    for peak_idx in area_ranked_candidate_indices:
        if len(display_peak_indices) >= DISPLAY_PEAK_COUNT:
            break
        if peak_idx not in display_peak_indices:
            display_peak_indices.append(peak_idx)
    display_peak_layers = [candidate_layer_by_idx[peak_idx] for peak_idx in display_peak_indices]
    floor_excluded_mask = ~band_mask(
        z,
        selected_peak_layers[0]["z_min"],
        selected_peak_layers[0]["z_max"],
    )
    min_z_excluding_floor_grid = build_min_z_grid(
        x[floor_excluded_mask],
        y[floor_excluded_mask],
        z[floor_excluded_mask],
        x_edges,
        y_edges,
    )
    higher_peak_cell_mask = np.zeros_like(min_z_excluding_floor_grid, dtype=bool)
    for layer in display_peak_layers[1:]:
        higher_peak_cell_mask |= layer["grid"] > 0
    peak_origin_grid = np.full(min_z_excluding_floor_grid.shape, np.nan, dtype=float)
    for display_peak_idx, layer in sorted(
        enumerate(display_peak_layers[1:], start=2),
        key=lambda item: item[1]["peak_center"],
    ):
        layer_cell_mask = (layer["grid"] > 0) & np.isnan(peak_origin_grid)
        peak_origin_grid[layer_cell_mask] = display_peak_idx
    min_z_excluding_floor_grid = np.where(
        higher_peak_cell_mask,
        min_z_excluding_floor_grid,
        np.nan,
    )
    min_z_excluding_floor_values = min_z_excluding_floor_grid[~np.isnan(min_z_excluding_floor_grid)]
    if len(min_z_excluding_floor_values) > 0:
        min_z_hist_counts, min_z_hist_edges = np.histogram(
            min_z_excluding_floor_values,
            bins=HISTOGRAM_BINS,
        )
        min_z_hist_centers = (min_z_hist_edges[:-1] + min_z_hist_edges[1:]) / 2
        min_z_hist_widths = np.diff(min_z_hist_edges)
    else:
        min_z_hist_counts = np.array([0.0], dtype=float)
        min_z_hist_centers = np.array([0.0], dtype=float)
        min_z_hist_widths = np.array([1.0], dtype=float)

    for i, layer in enumerate(display_peak_layers, start=1):
        print(
            f"Peak {i}: z ~= {layer['peak_center']:.2f} m, "
            f"Z range [{layer['z_min']:.2f}, {layer['z_max']:.2f}), "
            f"points {layer['point_count']}, "
            f"area {layer['area']:.2f} m^2, "
            f"largest contiguous area {layer['largest_component_area']:.2f} m^2"
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
    update_gpkg_attributes(gpkg_path, underpass_attributes)
    print(
        "Updated GPKG attributes: "
        f"underpass_dh={underpass_attributes['underpass_dh']:.2f}, "
        f"underpass_top_area={underpass_attributes['underpass_top_area']:.2f}, "
        f"underpass_bottom_area={underpass_attributes['underpass_bottom_area']:.2f}"
    )

    map_width = max_x - min_x
    map_height = max_y - min_y
    map_aspect_ratio = map_width / map_height if map_height > 0 else 1.0
    map_panel_width_ratio = max(0.7, map_aspect_ratio)
    ncols = len(display_peak_layers)
    width_ratios = [map_panel_width_ratio] * ncols
    figure_width = 5 * sum(width_ratios)
    fig = plt.figure(figsize=(figure_width, 15))
    bottom_map_stop = max(1, ncols - 2)
    grid_spec = fig.add_gridspec(
        3,
        ncols,
        width_ratios=width_ratios,
        height_ratios=[1.0, 1.0, 1.0],
        wspace=0.06,
        hspace=0.32,
    )
    ax_hist = fig.add_subplot(grid_spec[0, :])
    peak_axes = [fig.add_subplot(grid_spec[1, idx]) for idx in range(ncols)]
    ax_min_z = fig.add_subplot(grid_spec[2, :bottom_map_stop])
    ax_peak_origin = fig.add_subplot(grid_spec[2, bottom_map_stop])
    ax_min_z_hist = fig.add_subplot(grid_spec[2, bottom_map_stop + 1])

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
    peak_colors = {1: "C0", 2: "C1", 3: "C2", 4: "C3"}
    for i, layer in enumerate(display_peak_layers, start=1):
        ax_hist.axvline(
            layer["peak_center"],
            linestyle="--",
            linewidth=1.5,
            color=peak_colors.get(i, "C3"),
        )
        ax_hist.axvspan(
            layer["z_min"],
            layer["z_max"],
            alpha=0.15,
            color=peak_colors.get(i, "C3"),
        )
    ax_hist.set_xlabel("Z (m)")
    ax_hist.set_ylabel("Count")
    ax_hist.set_title("Histogram of Z values", fontsize=13, pad=8)
    ax_hist.spines["top"].set_visible(False)
    ax_hist.spines["right"].set_visible(False)

    arrow_y = counts.max() * 0.92
    label_y = counts.max() * 0.97
    left_peak = bin_centers[peak_indices[0]]
    right_peak = bin_centers[peak_indices[-1]]
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
    color_maps = {
        1: make_truncated_cmap("Blues", start=0.28),
        2: make_truncated_cmap("Oranges", start=0.30),
        3: make_truncated_cmap("Greens", start=0.30),
        4: make_truncated_cmap("Reds", start=0.30),
        "min_z": make_truncated_cmap("cividis", start=0.20),
    }

    for map_idx, (ax_map, layer) in enumerate(zip(peak_axes, display_peak_layers), start=1):
        masked_grid = np.ma.masked_where(layer["grid"] == 0, layer["grid"])
        ax_map.set_facecolor("#f3f3f3")
        ax_map.imshow(
            masked_grid,
            origin="lower",
            extent=extent,
            cmap=color_maps[map_idx],
            alpha=0.9,
            interpolation="nearest",
        )
        plot_geometry_outline(ax_map, geometries)
        ax_map.set_xlabel("X")
        if map_idx == 1:
            ax_map.set_ylabel("Y")
        else:
            ax_map.set_ylabel("")
            ax_map.tick_params(axis="y", which="both", left=False, labelleft=False)
        ax_map.set_title(
            f"Peak {map_idx}: {layer['peak_center']:.2f} m\n"
            f"Z range [{layer['z_min']:.2f}, {layer['z_max']:.2f})\n"
            f"Covered area {layer['area']:.2f} m^2\n"
            f"Largest contiguous area {layer['largest_component_area']:.2f} m^2",
            fontsize=11,
            pad=8,
        )
        ax_map.set_aspect("equal")
        ax_map.legend(loc="best")

    masked_min_z_grid = np.ma.masked_invalid(min_z_excluding_floor_grid)
    ax_min_z.set_facecolor("#f3f3f3")
    min_z_image = ax_min_z.imshow(
        masked_min_z_grid,
        origin="lower",
        extent=extent,
        cmap=color_maps["min_z"],
        alpha=0.95,
        interpolation="nearest",
    )
    plot_geometry_outline(ax_min_z, geometries)
    ax_min_z.set_xlabel("X")
    ax_min_z.set_ylabel("Y")
    if len(min_z_excluding_floor_values) > 0:
        min_z_range_text = (
            f"Cell min Z range "
            f"[{np.min(min_z_excluding_floor_values):.2f}, {np.max(min_z_excluding_floor_values):.2f}]"
        )
    else:
        min_z_range_text = "No cells after floor exclusion"
    ax_min_z.set_title(
        "Min elevation per cell\n"
        f"Cells from Peaks 2-{len(display_peak_layers)}; excluding Peak 1 "
        f"[{selected_peak_layers[0]['z_min']:.2f}, {selected_peak_layers[0]['z_max']:.2f})\n"
        f"{min_z_range_text}",
        fontsize=11,
        pad=8,
    )
    ax_min_z.set_aspect("equal")
    ax_min_z.legend(loc="best")
    colorbar = fig.colorbar(min_z_image, ax=ax_min_z, fraction=0.046, pad=0.04)
    colorbar.set_label("Min Z (m)")

    peak_origin_colors = [
        peak_colors.get(display_peak_idx, "C3")
        for display_peak_idx in range(2, len(display_peak_layers) + 1)
    ]
    masked_peak_origin_grid = np.ma.masked_invalid(peak_origin_grid)
    ax_peak_origin.set_facecolor("#f3f3f3")
    ax_peak_origin.imshow(
        masked_peak_origin_grid,
        origin="lower",
        extent=extent,
        cmap=ListedColormap(peak_origin_colors),
        interpolation="nearest",
        vmin=1.5,
        vmax=len(display_peak_layers) + 0.5,
    )
    plot_geometry_outline(ax_peak_origin, geometries)
    ax_peak_origin.set_xlabel("X")
    ax_peak_origin.set_ylabel("")
    ax_peak_origin.tick_params(axis="y", which="both", left=False, labelleft=False)
    ax_peak_origin.set_title(
        "Peak origin per cell\n"
        f"Lowest occupying peak among Peaks 2-{len(display_peak_layers)}",
        fontsize=11,
        pad=8,
    )
    ax_peak_origin.set_aspect("equal")
    peak_origin_legend = [
        Patch(
            facecolor=peak_colors.get(display_peak_idx, "C3"),
            edgecolor="none",
            label=f"Peak {display_peak_idx}",
        )
        for display_peak_idx in range(2, len(display_peak_layers) + 1)
    ]
    ax_peak_origin.legend(handles=peak_origin_legend, loc="best")

    ax_min_z_hist.hist(
        min_z_excluding_floor_values,
        bins=HISTOGRAM_BINS,
        color="lightgray",
        edgecolor="#999999",
        linewidth=0.25,
    )
    ax_min_z_hist.set_xlabel("Cell min Z (m)")
    ax_min_z_hist.set_ylabel("Cell count")
    ax_min_z_hist.set_title(
        f"Histogram of cell min Z\ncells from Peaks 2-{len(display_peak_layers)}",
        fontsize=11,
        pad=8,
    )
    ax_min_z_hist.spines["top"].set_visible(False)
    ax_min_z_hist.spines["right"].set_visible(False)

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
