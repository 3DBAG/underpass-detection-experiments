cmake_minimum_required(VERSION 3.18)

project(test_3d_intersection)

set(CMAKE_CXX_STANDARD 20)

find_package(CGAL REQUIRED)
find_package(Geogram REQUIRED)
find_package(manifold REQUIRED)
find_package(GDAL REQUIRED)

add_executable(test_3d_intersection main.cpp)

install(TARGETS test_3d_intersection DESTINATION bin)
