# Underpass Height From Street LiDAR

This directory contains a Python workflow for estimating underpass height from cropped LAS/LAZ point clouds and matching polygons stored in GeoPackages.

> The cropped point clouds were generated using the script in `../crop_las_by_polygons`:

The script loops over a list of BAG cases, reads each LAS/LAZ file and its matching
GeoPackage polygon, and detects Z-peak candidates from a smoothed histogram. The
elevation histogram uses fixed-width bins anchored at global elevation `0`;
configure their width with `HISTOGRAM_BIN_WIDTH_METERS`. After terrain rejection,
phase 1 applies the absolute and relative histogram-count thresholds. Phase 2
rasterizes and applies the lower-peak-masked area threshold.

The PostGIS street-lidar runner also samples the Mapterhorn AHN5 5 m filled DTM at zoom 14. It transforms each original underpass polygon from RD New to Web Mercator, decodes every intersecting Terrarium pixel whose centre falls inside the polygon, and uses the 90th-percentile pixel elevation as the NAP terrain reference. Peaks within an absolute 2 m of that reference are excluded. Very small polygons with no enclosed pixel centre fall back to all intersecting pixels. Downloaded WebP tiles are cached persistently and terrain sampling details are stored under `underpass_metadata.terrain`.

Phase 1 retains terrain-eligible candidates whose raw peak-bin count is at least
`1000` and at least `5%` of the second-highest terrain-eligible raw count. Each
phase-1 peak uses a fixed `1.0 m` vertical band and is rasterized at `0.5 m`
resolution. Cells occupied by every lower phase-1 peak are then masked out.

Phase 2 requires masked total area to be at least the greater of `4 m²` and
`20%` of the polygon area. Selected peaks are ranked by masked largest contiguous
area, then masked total area, then smoothed histogram count. All phase-1 peaks remain
in diagnostic plots, including phase-2 rejections. All detected peaks remain in
the detailed debug JSON; candidates rejected before rasterization have null area
values. Vertical-wall masks are not applied.

Configure the eligibility thresholds with `PEAK_MIN_RAW_COUNT`,
`DISPLAY_PEAK_MIN_RELATIVE_RAW_COUNT`, `PEAK_MIN_MASK_AREA_M2`, and
`PEAK_MIN_MASK_AREA_POLYGON_FRACTION` in `height_estimation.py`.

## What The Script Produces

- A histogram with the Mapterhorn terrain reference and every phase-1 peak
- A metrics table with one column per phase-1 peak, ordered left-to-right by
  elevation; its rows include the phase-2 production rank or `Not selected` and
  the raw point count in the peak's full Z-band; area rows also show the area as
  a percentage of polygon area
- Two XY raster rows per phase-1 peak: the raw mask followed by the mask after
  cells occupied by lower phase-1 peaks have been removed
- A figure title containing the case identifier and polygon area
- One PNG per BAG id, named `<bag_id>_peak_grids_overlay.png`
- A CSV summary written to `underpass_heights.csv`, with the production field
  `underpass_candidate_elevations` containing only threshold-passing candidate elevations,
  ordered by descending masked contiguous area, plus detailed
  `underpass_metadata` JSON for debugging
- A Rerun visualization sent to the viewer by default

## Example Cases

The `images/` directory contains point-cloud screenshots and matching script outputs for several BAG ids.

### `NL.IMBAG.Pand.0363100012095711`

Point cloud:

![NL.IMBAG.Pand.0363100012095711 point cloud](images/NL.IMBAG.Pand.0363100012095711.png)

Script output:

![NL.IMBAG.Pand.0363100012095711 output](images/NL.IMBAG.Pand.0363100012095711_peak_grids_overlay.png)

### `NL.IMBAG.Pand.0363100012122448`

Point cloud:

![NL.IMBAG.Pand.0363100012122448 point cloud](images/NL.IMBAG.Pand.0363100012122448.png)

Script output:

![NL.IMBAG.Pand.0363100012122448 output](images/NL.IMBAG.Pand.0363100012122448_peak_grids_overlay.png)

### `NL.IMBAG.Pand.0363100012137139`

Point cloud:

![NL.IMBAG.Pand.0363100012137139 point cloud](images/NL.IMBAG.Pand.0363100012137139.png)

Script output:

![NL.IMBAG.Pand.0363100012137139 output](images/NL.IMBAG.Pand.0363100012137139_peak_grids_overlay.png)

### `NL.IMBAG.Pand.0363100012146576`

Point cloud:

![NL.IMBAG.Pand.0363100012146576 point cloud](images/NL.IMBAG.Pand.0363100012146576.png)

Script output:

![NL.IMBAG.Pand.0363100012146576 output](images/NL.IMBAG.Pand.0363100012146576_peak_grids_overlay.png)

### `NL.IMBAG.Pand.0363100012165755`

Point cloud:

![NL.IMBAG.Pand.0363100012165755 point cloud](images/NL.IMBAG.Pand.0363100012165755.png)

Script output:

![NL.IMBAG.Pand.0363100012165755 output](images/NL.IMBAG.Pand.0363100012165755_peak_grids_overlay.png)

### `NL.IMBAG.Pand.0363100012170850`

Point cloud:

![NL.IMBAG.Pand.0363100012170850 point cloud](images/NL.IMBAG.Pand.0363100012170850.png)

Script output:

![NL.IMBAG.Pand.0363100012170850 output](images/NL.IMBAG.Pand.0363100012170850_peak_grids_overlay.png)

## Run With Nix

From this directory:

```bash
nix develop -c python3 estimate_heights.py
```

Run the diagnostic plot/Rerun workflow:

```bash
nix develop -c python3 plot_z_histogram.py
```

## Run Without Nix

Use Python 3. Then install the required packages:

```bash
python3 -m pip install laspy matplotlib numpy pillow pyproj shapely
```

Rerun visualization is optional:

```bash
python3 -m pip install rerun-sdk
```

Run the script:

```bash
python3 estimate_heights.py
```

Run the diagnostic plot/Rerun workflow:

```bash
python3 plot_z_histogram.py
```

## Files

- `height_estimation.py`: plot-free height estimation core
- `estimate_heights.py`: height-only CSV script
- `plot_z_histogram.py`: diagnostic plotting and Rerun script
- `cases.py`: shared input case list
- `flake.nix`: Nix development shell with Python dependencies
- `underpass_heights.csv`: CSV summary written by the script
- `images/`: example point-cloud screenshots and BAG-specific script outputs
