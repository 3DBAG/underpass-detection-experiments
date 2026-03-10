import laspy
import matplotlib.pyplot as plt
import numpy as np
import sqlite3
from shapely import wkb


LAS_PATH = "data/roofer-out/objects/0/crop/0_.las"
GPKG_PATH = "data/roofer-out/objects/0/crop/0.gpkg"
HISTOGRAM_BINS = 100
GRID_CELLSIZE = 0.5
OUTPUT_PATH = "peak_grids_overlay.png"


def find_top_histogram_peaks(values, bins=100, smoothing_window=7, min_separation_bins=10):
    counts, bin_edges = np.histogram(values, bins=bins)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    # Smooth the histogram slightly so one broad mode does not produce several
    # adjacent local maxima from binning noise.
    kernel = np.hanning(smoothing_window)
    kernel /= kernel.sum()
    smoothed_counts = np.convolve(counts, kernel, mode="same")

    candidate_indices = np.where(
        (smoothed_counts[1:-1] > smoothed_counts[:-2])
        & (smoothed_counts[1:-1] >= smoothed_counts[2:])
    )[0] + 1

    ranked_candidates = candidate_indices[np.argsort(smoothed_counts[candidate_indices])[::-1]]

    peak_indices = []
    for idx in ranked_candidates:
        if all(abs(idx - existing) >= min_separation_bins for existing in peak_indices):
            peak_indices.append(idx)
        if len(peak_indices) == 2:
            break

    peak_indices.sort(key=lambda idx: bin_centers[idx])
    return counts, bin_edges, bin_centers, smoothed_counts, peak_indices


def peak_cluster_from_index(bin_edges, smoothed_counts, peak_idx):
    left_idx = peak_idx
    while left_idx > 0 and smoothed_counts[left_idx - 1] <= smoothed_counts[left_idx]:
        left_idx -= 1

    right_idx = peak_idx
    max_idx = len(smoothed_counts) - 1
    while right_idx < max_idx and smoothed_counts[right_idx + 1] <= smoothed_counts[right_idx]:
        right_idx += 1

    return bin_edges[left_idx], bin_edges[right_idx + 1]


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


def main():
    las = laspy.read(LAS_PATH)
    x = np.asarray(las.x, dtype=float)
    y = np.asarray(las.y, dtype=float)
    z = np.asarray(las.z, dtype=float)

    counts, bin_edges, bin_centers, smoothed_counts, peak_indices = find_top_histogram_peaks(
        z,
        bins=HISTOGRAM_BINS,
        smoothing_window=7,
        min_separation_bins=10,
    )
    geometries = load_polygon_geometries(GPKG_PATH)

    min_x, min_y, max_x, max_y = geometry_bounds(geometries)
    x_edges = np.arange(min_x, max_x + GRID_CELLSIZE, GRID_CELLSIZE)
    y_edges = np.arange(min_y, max_y + GRID_CELLSIZE, GRID_CELLSIZE)

    if x_edges[-1] < max_x:
        x_edges = np.append(x_edges, max_x)
    if y_edges[-1] < max_y:
        y_edges = np.append(y_edges, max_y)

    print(f"Number of points: {len(z)}")
    print(f"Z range: [{np.min(z):.2f}, {np.max(z):.2f}]")
    print(f"Z mean: {np.mean(z):.2f}, std: {np.std(z):.2f}")

    peak_layers = []
    for i, peak_idx in enumerate(peak_indices, start=1):
        z_min, z_max = peak_cluster_from_index(bin_edges, smoothed_counts, peak_idx)
        if np.isclose(z_max, bin_edges[-1]):
            mask = (z >= z_min) & (z <= z_max)
        else:
            mask = (z >= z_min) & (z < z_max)
        grid = build_grid(x[mask], y[mask], x_edges, y_edges)
        area = np.count_nonzero(grid) * (GRID_CELLSIZE ** 2)
        peak_layers.append((i, peak_idx, z_min, z_max, grid, area))

        print(
            f"Peak {i}: z ~= {bin_centers[peak_idx]:.2f} m, "
            f"window [{z_min:.2f}, {z_max:.2f}), "
            f"points {np.count_nonzero(mask)}, "
            f"area {area:.2f} m^2"
        )

    underpass_attributes = {
        "underpass_dh": bin_centers[peak_indices[-1]] - bin_centers[peak_indices[0]],
        "underpass_top_area": peak_layers[-1][-1],
        "underpass_bottom_area": peak_layers[0][-1],
    }
    update_gpkg_attributes(GPKG_PATH, underpass_attributes)
    print(
        "Updated GPKG attributes: "
        f"underpass_dh={underpass_attributes['underpass_dh']:.2f}, "
        f"underpass_top_area={underpass_attributes['underpass_top_area']:.2f}, "
        f"underpass_bottom_area={underpass_attributes['underpass_bottom_area']:.2f}"
    )

    fig, axes = plt.subplots(1, 1 + len(peak_layers), figsize=(7 * (1 + len(peak_layers)), 7))
    ax_hist = axes[0]

    ax_hist.hist(z, bins=HISTOGRAM_BINS, edgecolor="black", linewidth=0.3)
    for i, peak_idx, z_min, z_max, _, _ in peak_layers:
        ax_hist.axvline(
            bin_centers[peak_idx],
            linestyle="--",
            linewidth=2,
            color="C0" if i == 1 else "C1",
        )
        ax_hist.axvspan(
            z_min,
            z_max,
            alpha=0.15,
            color="C0" if i == 1 else "C1",
        )
    ax_hist.set_xlabel("Z (m)")
    ax_hist.set_ylabel("Count")
    ax_hist.set_title("Histogram of Z values")

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
    color_maps = {1: "Blues", 2: "Oranges"}

    for ax_map, (i, peak_idx, z_min, z_max, grid, area) in zip(axes[1:], peak_layers):
        masked_grid = np.ma.masked_where(grid == 0, grid)
        ax_map.imshow(
            masked_grid,
            origin="lower",
            extent=extent,
            cmap=color_maps[i],
            alpha=0.65,
            interpolation="nearest",
        )
        plot_geometry_outline(ax_map, geometries)
        ax_map.set_xlabel("X")
        ax_map.set_ylabel("Y")
        ax_map.set_title(
            f"Peak {i}: {bin_centers[peak_idx]:.2f} m\n"
            f"Window [{z_min:.2f}, {z_max:.2f}) | Area {area:.2f} m^2"
        )
        ax_map.set_aspect("equal")
        ax_map.legend(loc="best")

    plt.tight_layout()
    if "agg" in plt.get_backend().lower():
        plt.savefig(OUTPUT_PATH, dpi=200)
        print(f"Saved overlay figure to {OUTPUT_PATH}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
