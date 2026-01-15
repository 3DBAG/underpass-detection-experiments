# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Test 3D Intersection is a C++20 project for testing and developing 3D geometric intersection operations. The project includes a comprehensive set of computational geometry and geospatial libraries configured through vcpkg.

## Building and Running

**Build the project:**
```bash
cmake -B cmake-build-debug -G Ninja
cmake --build cmake-build-debug
```

**Run the executable:**
```bash
./cmake-build-debug/test_3d_intersection
```

**Using CLion IDE (recommended):**
- CLion automatically detects the project and integrates with the dev container
- Build: `Build > Build Project` or Shift+F10
- Run: `Run > Run 'test_3d_intersection'` or Shift+F10 after building
- Debug: `Run > Debug 'test_3d_intersection'` or Shift+F9

## Development Environment

**Primary Workflow: Dev Container in CLion**

The project uses a containerized development environment for consistency:

1. **Setup**: Open project in CLion 2023.2+ with Docker installed
2. **Container Detection**: CLion auto-detects `.devcontainer/` and prompts to create container
3. **Toolchain**: Ubuntu 24.04 with GCC, CMake 3.28+, Ninja, and all dependencies pre-installed

**Key Container Configuration**:
- Base image: `mcr.microsoft.com/devcontainers/cpp:ubuntu-24.04`
- Remote user: `devuser`
- vcpkg binary cache mounted at `/home/devuser/.cache/vcpkg` for faster rebuilds
- Features: Node.js LTS, Zsh shell

**Note**: There's a typo in `.devcontainer/devcontainer.json` line 32: `bashaddi` should be `bash`. Fix this before using the container:
```json
"postCreateCommand": "set -e; npm install -g @openai/codex; curl -fsSL https://claude.ai/install.sh | bash"
```

**Local Development (without container)**:
- Install: CMake 3.28+, GCC 11+, Ninja, vcpkg
- Set `VCPKG_ROOT` environment variable
- Build: `cmake -B cmake-build-debug && cmake --build cmake-build-debug`

## Project Structure

- **CMakeLists.txt**: CMake build configuration (C++20, single executable target)
- **main.cpp**: Entry point (currently CLion template, 274 bytes)
- **vcpkg.json**: Dependency manifest with version string "0.1.0"
- **.devcontainer/**: Container-based development configuration
  - `Dockerfile`: Ubuntu 24.04 base with C++ toolchain
  - `devcontainer.json`: CLion integration (fix the typo mentioned above)

## Dependencies and Libraries

The project includes seven major dependencies configured in `vcpkg.json`:

**3D Geometry & Mesh Operations**:
- **CGAL**: Computational Geometry Algorithms Library - industry standard for geometric algorithms, triangulation, intersection detection
- **Manifold**: High-performance mesh operations and boolean operations on 3D models
- **Eigen3**: Linear algebra library underlying vector/matrix operations in geometry computations

**Advanced Mesh Processing**:
- **Geogram**: Geometric algorithms including Voronoi diagrams, Delaunay triangulation, spatial data structures

**Geospatial Data Handling**:
- **GDAL**: Geospatial Data Abstraction Library with SQLite3, PostgreSQL, and GEOS support for raster/vector data
- **GEOS**: Geometry Engine Open Source for spatial relationship operations and WKT/WKB parsing

**Utilities**:
- **nlohmann-json**: JSON serialization/deserialization for configuration and data interchange

## Architecture Notes

**Current State**: The project is in scaffolding phase with template code. The extensive library selection suggests the intended implementation will combine:
- CGAL for theoretical geometric algorithms
- Manifold for robust, practical 3D mesh operations
- GDAL/GEOS for geospatial data loading and processing
- Eigen3 for foundational linear algebra across all operations

**Workspace Structure**:
- Single executable target: `test_3d_intersection`
- All source code in project root (currently just main.cpp)
- Build artifacts in `cmake-build-debug/` (git-ignored)
- vcpkg cache in `.vcpkg-cache/` (git-ignored, mounted for persistence)

## Common Tasks

**Clean rebuild:**
```bash
rm -rf cmake-build-debug
cmake -B cmake-build-debug -G Ninja
cmake --build cmake-build-debug
```

**Adding dependencies**: Edit `vcpkg.json` and rebuild. vcpkg will resolve and install new packages.

**Debugging in CLion**: Set breakpoints directly in code, then run Debug configuration (Shift+F9).
