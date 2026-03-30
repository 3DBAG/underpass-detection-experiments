# zigpip

`zigpip` is a small Zig library that ports Eric Haines' grid-prepared point-in-polygon test from Roofer into Zig, exposes it through a C ABI, and provides a thin Python binding for batch point queries.

The repository also includes a streaming crop script that reads a LAS/LAZ point cloud, loads polygons from a GeoPackage, and writes one cropped point cloud per polygon feature.

## Layout

- `src/ptinpoly.zig`: Zig port of the prepared-grid point-in-polygon algorithm
- `src/capi.zig`: C ABI for Python and other consumers
- `python/zigpip/bindings.py`: NumPy + `ctypes` wrapper
- `scripts/crop_las_by_polygons.py`: LAS/LAZ crop workflow
- `scripts/bench_median.py`: aggregate repeated benchmark runs into a median report
- `scripts/plot_bench.py`: render C vs Zig benchmark charts
- `flake.nix`: development shell with Zig and Python GIS/LAS dependencies

## Dev Shell

```bash
nix develop
```

## Build

```bash
zig build
zig build test
zig build bench
```

The shared library is installed to `zig-out/lib/`.

## Benchmarking

Run the Zig benchmark in release mode:

```bash
zig build -Doptimize=ReleaseFast bench
```

Compile and run the C reference benchmark:

```bash
cc -O3 -o /tmp/ptinpoly_cbench c_ref/bench.c c_ref/ptinpoly.cpp -lm
/tmp/ptinpoly_cbench
```

The repository also includes helper scripts for repeated runs and plotting:

- `scripts/bench_median.py`
- `scripts/plot_bench.py`

Generated benchmark reports and charts are written under `bench_results/`.

## Crop Example

```bash
python scripts/crop_las_by_polygons.py \
  /Users/ravi/git/underpass-detection-experiments/height_from_streetlidar/data/125000_489200.laz \
  /Users/ravi/git/underpass-detection-experiments/height_from_streetlidar/data/beemsterstraat.gpkg \
  output/beemsterstraat
```

Useful options:

- `--layer geometries`
- `--id-field identificatie`
- `--resolution 64`: prepare each polygon ring on a `64 x 64` grid. Higher values usually trade more setup time and memory for faster point queries.
- `--chunk-size 1000000`
- `--reproject-polygons`

The crop script prints a timing summary at the end, including:

- feature preparation (`transform`, `buffer`, `prepare`, `write_gpkg`)
- crop-time work (`coords`, `feature_cull`, `pip`, `write`)
- counters such as chunks processed, active features per chunk, and candidate/hit totals

## Python Binding

```python
import numpy as np
from zigpip import PreparedRing

ring = PreparedRing(
    [
        (0.0, 0.0),
        (10.0, 0.0),
        (10.0, 10.0),
        (0.0, 10.0),
    ],
    resolution=32,
)

mask = ring.contains_many(np.array([1.0, 12.0]), np.array([1.0, 5.0]))
print(mask)  # [ True False ]
```
