#include <filesystem>
#include <CGAL/Exact_predicates_inexact_constructions_kernel.h>
#ifdef USE_POLYHEDRON
#include <CGAL/Polyhedron_3.h>
#else
#include <CGAL/Surface_mesh.h>
#endif
#include <CGAL/Shape_detection/Region_growing/Region_growing.h>
#include <CGAL/Shape_detection/Region_growing/Polygon_mesh.h>
#include <CGAL/IO/polygon_mesh_io.h>
#include "include/utils.h"

 
// Typedefs.
using Kernel  = CGAL::Exact_predicates_inexact_constructions_kernel;
using FT      = typename Kernel::FT;
using Point_3 = typename Kernel::Point_3;
 
#ifdef USE_POLYHEDRON
using Polygon_mesh   = CGAL::Polyhedron_3<Kernel>;
#else
using Polygon_mesh   = CGAL::Surface_mesh<Point_3>;
#endif
 
using Neighbor_query = CGAL::Shape_detection::Polygon_mesh::One_ring_neighbor_query<Polygon_mesh>;
using Region_type    = CGAL::Shape_detection::Polygon_mesh::Least_squares_plane_fit_region<Kernel, Polygon_mesh>;
using Sorting        = CGAL::Shape_detection::Polygon_mesh::Least_squares_plane_fit_sorting<Kernel, Polygon_mesh, Neighbor_query>;
using Region_growing = CGAL::Shape_detection::Region_growing<Neighbor_query, Region_type>;
 
int main(int argc, char *argv[]) {
 
  // Load data either from a local folder or a user-provided file.
  const bool is_default_input = argc > 1 ? false : true;
  const std::string filename = "data/region_growing/almere_0034100000050540.obj";
  std::ifstream in(filename);
  CGAL::IO::set_ascii_mode(in); 

  // Debug code
  std::ifstream test(filename);
  if (!test.is_open()) {
    std::cerr << "Cannot open file: " << filename << std::endl;
  } else {
    std::cout << "File opened successfully!" << std::endl;
  }
 
  Polygon_mesh polygon_mesh;

  try {
        if (!CGAL::IO::read_polygon_mesh(filename, polygon_mesh)) {
            std::cerr << "CGAL read_polygon_mesh returned false: file could not be parsed\n";
        } else {
            std::cout << "Mesh loaded successfully!\n";
        }
    } catch (const std::exception& e) {
        std::cerr << "Exception while reading mesh: " << e.what() << std::endl;
    } catch (...) {
        std::cerr << "Unknown exception while reading mesh" << std::endl;
    }

  // CGAL::IO::read_polygon_mesh(filename, polygon_mesh);
  // if (!CGAL::IO::read_polygon_mesh(filename, polygon_mesh)) {
  //   std::cerr << "ERROR: cannot read the input file!" << std::endl;
  //   return EXIT_FAILURE;
  // }
  const auto& face_range = faces(polygon_mesh);
  std::cout << "* number of input faces: " << face_range.size() << std::endl;
  // assert(!is_default_input || face_range.size() == 32245);
 
  // Default parameter values for the data file building.off.
  const FT          max_distance    = FT(1);
  const FT          max_angle       = FT(90);
  const std::size_t min_region_size = 1;
 
  // Create instances of the classes Neighbor_query and Region_type.
  Neighbor_query neighbor_query(polygon_mesh);
 
  Region_type region_type(
    polygon_mesh,
    CGAL::parameters::
    maximum_distance(max_distance).
    maximum_angle(max_angle).
    minimum_region_size(min_region_size));
 
  // Sort face indices.
  Sorting sorting(
    polygon_mesh, neighbor_query);
  sorting.sort();
 
  // Create an instance of the region growing class.
  Region_growing region_growing(
    face_range, sorting.ordered(), neighbor_query, region_type);
 
  // Run the algorithm.
  std::vector<typename Region_growing::Primitive_and_region> regions;
  region_growing.detect(std::back_inserter(regions));
  std::cout << "* number of found planes: " << regions.size() << std::endl;
  // assert(!is_default_input || regions.size() == 365);
 
  const Region_growing::Region_map& map = region_growing.region_map();
 
  for (std::size_t i = 0; i < regions.size(); i++)
    for (auto& item : regions[i].second) {
      if (i != get(map, item)) {
        std::cout << "Region map incorrect" << std::endl;
      }
    }
 
  std::vector<typename Region_growing::Item> unassigned;
  region_growing.unassigned_items(face_range, std::back_inserter(unassigned));
 
  for (auto& item : unassigned) {
    if (std::size_t(-1) != get(map, item)) {
      std::cout << "Region map for unassigned incorrect" << std::endl;
    }
  }
 
  // Save regions to a file.
  const std::string fullpath = (argc > 2 ? argv[2] : "output/region_growing/almere_0034100000050540_lod22_walls.off");
  utils::save_polygon_mesh_regions(polygon_mesh, regions, fullpath);
 
  return EXIT_SUCCESS;
}

































// #include "functions.h"

// #include <CGAL/Simple_cartesian.h>
// #include <CGAL/Surface_mesh.h>

// #include <CGAL/Shape_detection/Region_growing/Region_growing.h>

// #include <vector>
// #include <iostream>

// typedef CGAL::Simple_cartesian<double> Kernel;
// typedef Kernel::Point_3   Point;
// typedef Kernel::Plane_3   Plane;

// typedef CGAL::Surface_mesh<Point> Mesh;

// namespace SD = CGAL::Shape_detection;

// int main(int argc, char** argv){

//     // Read obj to mesh
//     Mesh obj_mesh = *obj_to_mesh(argv[1]);

//     // Use region growing algorithm to obtain planar regions

    

    
//     return 0;
// }