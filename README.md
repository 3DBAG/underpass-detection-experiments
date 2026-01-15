# Test 3D Intersection

This project is configured for container-based development using CLion and Dev Containers.

## Getting Started

### Option 1: Nix Development (Recommended)

1.  **Prerequisites**:
    *   [Nix](https://nixos.org/download.html) installed with flakes enabled.

2.  **Development Shell**:
    *   Run `nix develop` to enter the development environment with all dependencies.
    *   The shell will display the cmake command with proper paths for configuration.
    *   After configuration, build with: `cmake --build build`

3.  **Building with Nix**:
    *   To build the project directly: `nix build`
    *   The executable will be available at `./result/bin/test-3d-intersection`

### Option 2: Dev Containers in CLion

1.  **Prerequisites**:
    *   Docker installed and running.
    *   CLion 2023.2 or later (Support for Dev Containers).

2.  **Open in Dev Container**:
    *   Open this project in CLion.
    *   CLion should automatically detect the `.devcontainer` folder and prompt you to "Create Dev Container and Mount Project".
    *   Alternatively, you can go to `Settings | Build, Execution, Deployment | Dev Containers` to manage your containers.

3.  **Building and Running**:
    *   Once the container is initialized, CLion will use the toolchain from within the container.
    *   You can build and run the `test_3d_intersection` target as usual.

## Project Structure

*   `.devcontainer/`: Configuration for the development container.
    *   `Dockerfile`: Defines the environment (Ubuntu 24.04, CMake, GCC, etc.).
    *   `devcontainer.json`: Configuration for CLion to use the container.
*   `CMakeLists.txt`: Build configuration.
*   `main.cpp`: Main entry point.
