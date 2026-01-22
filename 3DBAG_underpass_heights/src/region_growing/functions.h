#include <iostream>
#include <fstream>
#include <optional>

#include <CGAL/Simple_cartesian.h>
#include <CGAL/Surface_mesh.h>
#include <CGAL/IO/OBJ.h> 

typedef CGAL::Simple_cartesian<double> Kernel;
typedef Kernel::Point_3               Point;
typedef CGAL::Surface_mesh<Point>     Mesh;


std::optional<Mesh> obj_to_mesh(std::string obj_filename){
    // Open obj file
    std::ifstream obj(obj_filename);
    if(!obj.is_open()){
        std::cerr << "Cannot open obj file\n";
        return std::nullopt;
    }

    // Read obj file to polygon soup
    std::vector<Point> points;
    std::vector<std::vector<std::size_t>> polygons;
    if (!CGAL::IO::read_OBJ(obj, points, polygons)){
        std::cerr << "Failed to read obj file" << std::endl;
        return std::nullopt;
    }

    // Check features
    std::cout << "OBJ loaded\n";
    std::cout << "Number of vertices = " << points.size() << "\n";
    std::cout << "Number of faces = " << polygons.size() << "\n";

    // Convert polygon soup to mesh
    Mesh mesh;
    // Create vector which will contain vertex indices
    std::vector<Mesh::vertex_index> vertex_indices;
    // Add vertices to mesh. Keep track of vertex indices 
    for (const auto& p : points){
        vertex_indices.push_back(mesh.add_vertex(p));
    }
    // Iterate over polygon soup
    for (const auto& polygon : polygons){
        // Define empty vector to store mesh
        std::vector<Mesh::vertex_index> face;
        // For each point defining the polygon, retrieve point index and append it to face vector 
        for (const auto& index : polygon){
            face.push_back(vertex_indices[index]);
        }
        // Add face to mesh
        mesh.add_face(face);
    }

    return mesh;
}


// bool is_coplanar(Mesh::Face_index face1, Mesh::Face_index face2, Mesh mesh){
//     /* Boolean function to determine if two faces are coplanar or not*/
//     // Compute distance between to planes

// }


// std::vector<Mesh> classify_surfaces(Mesh mesh){
//     /*Returns a vector of meshes. Each mesh is a segmented region

//     */
   
//     // Iterate over the faces of the input mesh to find seed faces
//     // Initialize vector to keep track of visited surfaces
//     std::vector<Mesh::Face_index> visited_faces;
//     // Iterate over faces, mesh.faces() is a Mesh::Face_index. For each face index:
//     for (const auto& face_descriptor : mesh.faces()){
//         // If the face has not been visited yet:
//         if(face_descriptor not in visited_faces){
//             // Declare vector of vertex descriptors to store face vertices
//             std::vector<Mesh::Vertex_index> face_vertices;
//             // Iterate over the vertices retrieved from the half edges of the face
//             for (const auto& vertex_descriptor : vertices_around_face(mesh.halfedges(face_descriptor), mesh)){
//                 // retrieve the point using the vertex descriptor
//                 Point p = mesh.point(vertex_descriptor);
//                 // Add point to region mesh. Retrieve the new vertex descriptor for the region mesh
//                 Mesh::Vertex_index region_vertex_descriptor = region.add_vertex(p);
//                 // Apend vertex descriptor to face_vertices
//                 face_vertices.push_back(region_vertex_descriptor);
//             }
//             // Initialize mesh for the region and add seed face
//             Mesh region;
//             region.add_face(face_vertices);
//             // Keep track of visited faces
//             visited_faces.push_back(face_descriptor)

//             // Iterate over the neighbors of the seed face
//             for (const auto& neighbor_descriptor : CGAL::faces_around_face(face_descriptor, mesh)){
//                 // If the neighbor has not been visited yet:
//                 if(neighbor_descriptor not in visited_faces){
//                     // Perform coplanarity checks
//                     if(is_coplanar(neighbor_descriptor, face_descriptor, mesh)){
//                         // Add vertices to the mesh
//                         // Add face to the mesh
//                         // Keep track of visited faces
//                         visited_faces.push_back(neighbor_descriptor);
//                     }
//                 }
//             }


//             // Retrieve neighbors of
//         }
//     }
// }
