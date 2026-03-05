# add_underpass

A program to carve out underpasses from 2.5D building models by using boolean mesh operations. 2D underpass polygons are read from an OGR source and extruded using a height attribute. Then the boolean mesh difference between 2.5D building model and extruded underpass polygons is computed.

### Limitations
- Mesh processing:
  - [ ] Output meshes get triangulated, even if input has polygonal faces.
  - [ ] assumes input building features are structured as outputed by roofer/3DBAG.
    - [ ] currently only processes the LoD "2.2" geometries
    - [ ] hardcoded to look for the object id BAGID+"-0" of each feature
  - [ ] May crash with problematic input geometries (most robust atm: manifold method in debug mode)

## Getting Started

### Prerequisites

- [Nix](https://nixos.org/download.html) with flakes enabled

### Quick Build

Build directly with Nix:
```bash
nix build
```
The executable will be at `./result/bin/add_underpass`.

This will always rebuild from scratch, so it's recommended to use the development environment for incremental builds.

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

With FCB input and FCB output (preserves all metadata, only replaces LoD 2.2 geometry):
```bash
./zig-out/bin/add_underpass \
  sample_data/amsterdam_beemsterstraat_42.gpkg \
  sample_data/9-444-728_sm.fcb \
  sample_data/out.fcb \
  hoogte identificatie manifold
```

With CityJSONSeq (`.jsonl`) input and output:
```bash
./zig-out/bin/add_underpass \
  sample_data/amsterdam_beemsterstraat_42.gpkg \
  sample_data/9-444-728_sm.city.jsonl \
  sample_data/out.city.jsonl \
  hoogte identificatie manifold
```

With PostgreSQL/PostGIS as OGR source:
```bash
./zig-out/bin/add_underpass \
  "PG:dbname='baseregisters' host=localhost port=5432 user=superson password='supassword' tables=bgt.underpasses_with_height(geom)" \
  sample_data/9-320-584.tmp.fcb \
  sample_data/out.fcb \
  h_underpass identificatie manifold
```

Arguments: `<ogr_source> <model_input> <model_output> <height_attr> [id_attr] [method]`

| Argument | Default | Description |
|----------|---------|-------------|
| `ogr_source` | — | Input OGR datasource path that contains 2D underpass polygons |
| `model_input` | — | Input path with 2.5D building model (`.fcb` or `.jsonl`). Use `-` only for FCB stdin. |
| `model_output` | — | Output path (`.fcb` or `.jsonl`). Use `-` only for FCB stdout. |
| `height_attr` | — | OGR height attribute name |
| `id_attr` | `identificatie` | OGR Feature ID attribute name. This is used to match with ID of the building models. |
| `method` | `manifold` | Boolean method: `manifold`, `nef`, `pmp`, or `geogram` |

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
- CityJSONSeq (`.jsonl`) stdin/stdout piping is not supported yet.

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
│   ├── BooleanOps.h
│   ├── BooleanOpsNef.cpp      # CGAL Nef backend
│   ├── BooleanOpsPMP.cpp      # CGAL PMP corefinement backend
│   ├── BooleanOpsGeogram.cpp  # Geogram backend
│   ├── BooleanOpsManifold.cpp # Manifold backend
│   ├── MeshConversion.cpp     # Surface_mesh conversions (exact + MeshGL helpers)
│   ├── MeshConversion.h
│   ├── ModelLoaders.cpp       # Mesh loaders for FlatCityBuf features
│   ├── ModelLoaders.h
│   ├── main.cpp               # Main entry point (FCB streaming pipeline)
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
