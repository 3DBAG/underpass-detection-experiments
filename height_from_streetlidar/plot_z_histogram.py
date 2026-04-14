import csv
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

from cases import CASES
from height_estimation import (
    HISTOGRAM_BINS,
    estimate_underpass_height,
    iter_rings,
)

# try:
#     import rerun as rr
# except ImportError:
#     rr = None
rr = None

# Optional diagnostic rows in the matplotlib output.
SHOW_EXCLUSIVE_ROW = False
SHOW_RELATED_WALL_ROW = False

# Figure margins in inches. These are converted to normalized subplot
# fractions based on the current figure size so spacing stays stable when the
# number of columns changes.
FIGURE_MARGIN_LEFT_INCHES = 0.9
FIGURE_MARGIN_RIGHT_INCHES = 0.15
FIGURE_MARGIN_BOTTOM_INCHES = 0.5
FIGURE_MARGIN_TOP_INCHES = 0.75

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
    if rr is None:
        print(f"Skipping Rerun visualization for {bag_id}; rerun-sdk is not installed")
        return

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
    result = estimate_underpass_height(las_path, gpkg_path, verbose=True)
    bag_id = result["bag_id"]
    output_path = f"{bag_id}_peak_grids_overlay.png"
    x = result["x"]
    y = result["y"]
    z = result["z"]
    counts = result["counts"]
    bin_centers = result["bin_centers"]
    smoothed_counts = result["smoothed_counts"]
    geometries = result["geometries"]
    min_x, min_y, max_x, max_y = result["bounds"]
    x_edges = result["x_edges"]
    y_edges = result["y_edges"]
    display_peak_layers = result["display_peak_layers"]
    selected_peak_layers = result["selected_peak_layers"]
    display_raw_count_threshold = result["display_raw_count_threshold"]
    underpass_attributes = result["underpass_attributes"]
    underpass_metrics = result["underpass_metrics"]

    map_width = max_x - min_x
    map_height = max_y - min_y
    map_aspect_ratio = map_width / map_height if map_height > 0 else 1.0
    map_panel_width_ratio = max(0.7, map_aspect_ratio)
    ncols = len(display_peak_layers)
    width_ratios = [map_panel_width_ratio] * ncols
    figure_width = 5 * sum(width_ratios)
    map_row_count = 2 + int(SHOW_EXCLUSIVE_ROW) + int(SHOW_RELATED_WALL_ROW)
    total_rows = 1 + map_row_count
    figure_height = 4.5 + 4.0 * total_rows
    fig = plt.figure(figsize=(figure_width, figure_height))
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
    ax_hist.axhline(
        display_raw_count_threshold,
        color="red",
        linestyle=":",
        linewidth=1.5,
        alpha=0.85,
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
    fig.subplots_adjust(
        left=FIGURE_MARGIN_LEFT_INCHES / figure_width,
        right=1 - (FIGURE_MARGIN_RIGHT_INCHES / figure_width),
        bottom=FIGURE_MARGIN_BOTTOM_INCHES / figure_height,
        top=1 - (FIGURE_MARGIN_TOP_INCHES / figure_height),
    )
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
