# Underpass Height From Street LiDAR

This directory contains a Python workflow for estimating an underpass height from a cropped LAS/LAZ point cloud and a matching polygon stored in a GeoPackage.

> The cropped point cloud was generated using roofer:
> ```
> roofer --ceil-point-density 100 --crop-only --crop-output  122200_486000.laz voormaligeStadstimmertuin.gpkg data/roofer-out
> ```
> The GPKG file contains the underpass polygon of interest from the 2D detection pipeline. The pointcloud is one of the files Amsterdam gave to us. To save space, these two files are not included in this repository, but the relvant roofer output is included.

The script loops over a list of BAG cases, reads each LAS/LAZ file and its matching GeoPackage polygon, finds two Z peaks, rasterizes the corresponding point subsets onto the XY plane at `0.5 m` resolution, and overlays those rasters with the polygon footprint.

It also writes the derived attributes back into the GeoPackage feature table:

- `underpass_dh`: difference between the two detected peak heights
- `underpass_top_area`: occupied raster area for the upper peak cluster
- `underpass_bottom_area`: occupied raster area for the lower peak cluster

## What The Script Produces

- A histogram of Z values with the raw histogram, the smoothed histogram, the two selected peak lines, fixed `0.5 m` selection bands, and a double-headed height-difference annotation
- One XY raster subplot for the lower peak and one for the upper peak, each overlaid with the polygon outline
- One PNG per BAG id, named `<bag_id>_peak_grids_overlay.png`
- Updated attributes in each input GeoPackage:
  - `underpass_dh`
  - `underpass_top_area`
  - `underpass_bottom_area`

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
nix develop -c python3 plot_z_histogram.py
```

## Run Without Nix

Use Python 3. Then install the required packages:

```bash
python3 -m pip install laspy matplotlib numpy shapely
```

Run the script:

```bash
python3 plot_z_histogram.py
```

## Files

- [`plot_z_histogram.py`](/Users/ravi/git/underpass-detection-experiments/height_from_streetlidar/plot_z_histogram.py): main analysis and plotting script
- [`flake.nix`](/Users/ravi/git/underpass-detection-experiments/height_from_streetlidar/flake.nix): Nix development shell with Python dependencies
- [`images/`](/Users/ravi/git/underpass-detection-experiments/height_from_streetlidar/images): example point-cloud screenshots and BAG-specific script outputs
