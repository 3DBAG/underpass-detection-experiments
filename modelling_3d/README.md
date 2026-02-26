# Test 3D Intersection

A project for 3D geometry intersection testing using Manifold and optional Rerun visualization.

### TODO
- [ ] maintain semantic surfaces in output, including outerceiling surface for top of the underpass
- [ ] Untriangulate the output meshes
- [ ] process all LoD's? currently only does LoD2.2
- [ ] add geogram boolean difference
- [ ] do benchmarking on large dataset, find failure cases

## Getting Started

### Prerequisites

- [Nix](https://nixos.org/download.html) with flakes enabled

### Quick Build

Build directly with Nix:
```bash
nix build
```
The executable will be at `./result/bin/test_3d_intersection`

### Development Build

1. Enter the development environment:
   ```bash
   nix develop
   ```

2. Build with Zig:
   ```bash
   zig build
   ```
   The executable will be at `./zig-out/bin/test_3d_intersection`

### Build Options

| Option | Default | Description |
|--------|---------|-------------|
| `-Drerun=true/false` | `false` | Enable Rerun visualization support |
| `-Doptimize=Debug/ReleaseFast/ReleaseSafe/ReleaseSmall` | `Debug` | Optimization level |

Example with Rerun enabled:
```bash
zig build -Drerun=true
```

Release build:
```bash
zig build -Doptimize=ReleaseFast
```

## Usage

### Getting sample data

Download a 3DBAG CityJSON tile (default tile: `9-444-728`):
```bash
just download-tile
# or specify a tile id:
just download-tile 10-284-556
```

The tile will be saved to `sample_data/<tile_id>.city.json`.

### Converting CityJSON to FlatCityBuf

Install the `fcb` CLI tool:
```bash
cargo install fcb
```

Convert the downloaded CityJSON tile to FCB for faster streaming:
```bash
fcb ser -i sample_data/9-444-728.city.json -o sample_data/9-444-728.fcb
```

### Running

With CityJSON input (outputs a PLY mesh):
```bash
./zig-out/bin/test_3d_intersection \
  sample_data/9-444-728.city.json \
  sample_data/amsterdam_beemsterstraat_42.gpkg \
  hoogte identificatie manifold
```

With FCB input and FCB output (preserves all metadata, only replaces LoD 2.2 geometry):
```bash
./zig-out/bin/test_3d_intersection \
  sample_data/9-444-728.fcb \
  sample_data/amsterdam_beemsterstraat_42.gpkg \
  hoogte identificatie manifold false \
  sample_data/out.fcb
```

Arguments: `<cityjson_or_fcb> <ogr_source> <height_attr> [id_attr] [method] [undo_offset] [output_fcb]`

| Argument | Default | Description |
|----------|---------|-------------|
| `id_attr` | `identificatie` | Feature ID attribute name |
| `method` | `manifold` | Boolean method: `manifold`, `nef`, or `pmp` |
| `undo_offset` | `false` | Undo global offset before output |
| `output_fcb` | — | FCB output path (only with `.fcb` input) |

### Converting FCB output back to CityJSONL

To inspect or visualize the output (e.g. with [ninja](https://ninja.cityjson.org/)):
```bash
fcb deser -i sample_data/out.fcb -o sample_data/out.city.jsonl
```

## Project Structure

```
.
├── build.zig          # Zig build configuration
├── build.zig.zon      # Zig build dependencies
├── flake.nix          # Nix flake for dependencies
├── flake.lock         # Nix flake lock file
├── justfile           # Task runner recipes
├── src/               # C++ source code
│   ├── main.cpp               # Main entry point
│   ├── OGRVectorReader.cpp    # OGR/GDAL vector data reader
│   ├── OGRVectorReader.h
│   ├── PolygonExtruder.cpp    # Polygon extrusion to 3D
│   ├── PolygonExtruder.h
│   ├── RerunVisualization.cpp # Rerun visualization support
│   └── RerunVisualization.h
├── zityjson/          # CityJSON/FlatCityBuf library (Zig)
│   ├── src/
│   │   ├── zityjson.zig       # CityJSON parser
│   │   └── zfcb.zig           # FCB streaming reader/writer
│   └── include/
└── sample_data/       # Sample input data
```

## Dependencies

Managed via Nix flake:
- **manifold** - 3D geometry processing
- **CGAL** - 3D geometry processing
- **OGR** - Vector data reader
- **rerun** - Visualization (optional)
- **zityjson** - CityJSON parser (built-in)
