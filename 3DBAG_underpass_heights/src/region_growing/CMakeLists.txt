cmake_minimum_required(VERSION 3.10)
project(region_growing)

find_package(CGAL REQUIRED)
find_package(Eigen3 REQUIRED)

add_executable(region_growing main.cpp)

target_include_directories(region_growing PRIVATE /usr/include/eigen3)

target_link_libraries(region_growing
    CGAL::CGAL
)





