# Test 3D Intersection

A project for 3D geometry intersection testing using Manifold and optional Rerun visualization.

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

## Project Structure

```
.
├── build.zig          # Zig build configuration
├── flake.nix          # Nix flake for dependencies
├── main.cpp           # Main entry point
├── zityjson/          # CityJSON parsing library (Zig)
│   ├── src/
│   └── include/
└── sample_data/       # Sample mesh files
```

## Dependencies

Managed via Nix flake:
- **manifold** - 3D geometry processing
- **rerun** - Visualization (optional)
- **zityjson** - CityJSON parser (built-in)
