# add_underpass

A project for 3D geometry intersection testing using Manifold and optional Rerun visualization.

### Limitations
- Mesh processing:
  - [ ] Untriangulate the output meshes
  - [ ] currently only processes the LoD2.2 geometries
  - [ ] geogram boolean difference method not implemented and untested

## Getting Started

### Prerequisites

- [Nix](https://nixos.org/download.html) with flakes enabled

### Quick Build

Build directly with Nix:
```bash
nix build
```
The executable will be at `./result/bin/add_underpass`

### Development Build

1. Enter the development environment:
   ```bash
   nix develop
   ```

2. Build with Zig:
   ```bash
   zig build
   ```
   The executable will be at `./zig-out/bin/add_underpass`

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

### Running

With CityJSON input (outputs a mesh file, e.g. PLY):
```bash
./zig-out/bin/add_underpass \
  sample_data/amsterdam_beemsterstraat_42.gpkg \
  sample_data/9-444-728.city.json \
  sample_data/out.ply \
  hoogte identificatie manifold
```

With FCB input and FCB output (preserves all metadata, only replaces LoD 2.2 geometry):
```bash
./zig-out/bin/add_underpass \
  sample_data/amsterdam_beemsterstraat_42.gpkg \
  sample_data/9-444-728_sm.fcb \
  sample_data/out.fcb \
  hoogte identificatie manifold
```

Arguments: `<ogr_source> <cityjson_or_fcb_input> <output_path_or_-> <height_attr> [id_attr] [method]`

| Argument | Default | Description |
|----------|---------|-------------|
| `ogr_source` | — | Input OGR datasource path |
| `cityjson_or_fcb_input` | — | Input model path (`.city.json/.city.jsonl/.fcb`) or `-` for FCB stdin |
| `output_path_or_-` | — | Output path (mesh path for CityJSON input, FCB path for FCB input) or `-` for FCB stdout |
| `height_attr` | — | OGR height attribute name |
| `id_attr` | `identificatie` | Feature ID attribute name |
| `method` | `manifold` | Boolean method: `manifold`, `nef`, or `pmp` |

### Converting CityJSON to FlatCityBuf

Install the [`fcb` CLI tool](https://github.com/cityjson/flatcitybuf/tree/main):
```bash
cargo install fcb
```

Convert the downloaded CityJSON tile to FCB for faster streaming:
```bash
fcb ser -i sample_data/9-444-728_sm.city.json -o sample_data/9-444-728_sm.fcb
```

To go from FCB to CityJSONL:
```bash
fcb deser -i sample_data/out.fcb -o sample_data/out.city.jsonl
```

### FCB piping with stdin/stdout

`add_underpass` supports Unix-style FCB streaming with `-`:
- Use `-` as input path (second argument) to read FCB from stdin.
- Use `-` as output path (third argument) to write FCB to stdout.
- When writing binary FCB to stdout, logs/timing are written to stderr.

Examples:

FCB file -> stdout (pipe to deser):
```bash
./zig-out/bin/add_underpass \
  sample_data/amsterdam_beemsterstraat_42.gpkg \
  sample_data/9-444-728_sm.fcb \
  - \
  hoogte identificatie pmp \
| fcb deser -i - -o sample_data/out.city.jsonl
```

stdin -> stdout full pipeline:
```bash
fcb ser -i sample_data/9-444-728.city.jsonl -o - \
| ./zig-out/bin/add_underpass \
    sample_data/amsterdam_beemsterstraat_42.gpkg \
    - \
    - \
    hoogte identificatie pmp \
| fcb deser -i - -o sample_data/out.city.jsonl
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
