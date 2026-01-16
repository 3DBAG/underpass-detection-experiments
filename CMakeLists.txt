cmake_minimum_required(VERSION 3.18)

project(test_3d_intersection)

set(CMAKE_CXX_STANDARD 20)

find_package(CGAL REQUIRED)
find_package(Geogram REQUIRED)
find_package(manifold REQUIRED)
find_package(GDAL REQUIRED)

set(RERUN_DOWNLOAD_AND_BUILD_ARROW OFF)
find_package(rerun_sdk REQUIRED)

add_executable(test_3d_intersection main.cpp)
target_link_libraries(test_3d_intersection PRIVATE manifold::manifold rerun_sdk)

install(TARGETS test_3d_intersection DESTINATION bin)
