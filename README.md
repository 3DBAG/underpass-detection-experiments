# Test 3D Intersection

This project is configured for container-based development using CLion and Dev Containers.

## Getting Started with Dev Containers in CLion

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
