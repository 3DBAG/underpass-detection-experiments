#include "MeshConversion.h"

#include <stdexcept>
#include <limits>
#include <vector>

#include <CGAL/Polygon_mesh_processing/triangulate_faces.h>
#include <CGAL/Polygon_mesh_processing/compute_normal.h>

Exact_surface_mesh surface_mesh_to_exact(const Surface_mesh& sm) {
    Exact_surface_mesh esm;

    std::vector<Exact_surface_mesh::Vertex_index> vertex_map;
    vertex_map.reserve(sm.number_of_vertices());

    for (auto v : sm.vertices()) {
        const auto& pt = sm.point(v);
        Exact_kernel::Point_3 exact_pt(pt.x(), pt.y(), pt.z());
        vertex_map.push_back(esm.add_vertex(exact_pt));
    }

    for (auto f : sm.faces()) {
        std::vector<Exact_surface_mesh::Vertex_index> face_vertices;
        for (auto v : sm.vertices_around_face(sm.halfedge(f))) {
            face_vertices.push_back(vertex_map[v]);
        }
        esm.add_face(face_vertices);
    }

    return esm;
}

Surface_mesh exact_to_surface_mesh(const Exact_surface_mesh& esm) {
    Surface_mesh sm;

    std::vector<Surface_mesh::Vertex_index> vertex_map;
    vertex_map.reserve(esm.number_of_vertices());

    for (auto v : esm.vertices()) {
        const auto& pt = esm.point(v);
        K::Point_3 approx_pt(
            CGAL::to_double(pt.x()),
            CGAL::to_double(pt.y()),
            CGAL::to_double(pt.z())
        );
        vertex_map.push_back(sm.add_vertex(approx_pt));
    }

    for (auto f : esm.faces()) {
        std::vector<Surface_mesh::Vertex_index> face_vertices;
        for (auto v : esm.vertices_around_face(esm.halfedge(f))) {
            face_vertices.push_back(vertex_map[v]);
        }
        sm.add_face(face_vertices);
    }

    return sm;
}

manifold::MeshGL surface_mesh_to_meshgl(Surface_mesh& sm, bool compute_normals, bool flip_normals) {
    manifold::MeshGL meshgl;

    if (sm.number_of_faces() == 0) {
        return meshgl;
    }

    meshgl.numProp = compute_normals ? 6 : 3;

    if (compute_normals) {
        meshgl.vertProperties.reserve(sm.number_of_faces() * 3 * meshgl.numProp);
        meshgl.triVerts.reserve(sm.number_of_faces() * 3);

        using face_descriptor = Surface_mesh::Face_index;
        auto fnormals = sm.add_property_map<face_descriptor, K::Vector_3>("f:normals", CGAL::NULL_VECTOR).first;
        CGAL::Polygon_mesh_processing::compute_face_normals(sm, fnormals);

        uint32_t vert_idx = 0;
        for (auto f : sm.faces()) {
            K::Vector_3 normal = fnormals[f];

            auto h = sm.halfedge(f);
            const auto& p0 = sm.point(sm.target(h));
            h = sm.next(h);
            const auto& p1 = sm.point(sm.target(h));
            h = sm.next(h);
            const auto& p2 = sm.point(sm.target(h));

            for (const auto& pt : {p0, p1, p2}) {
                meshgl.vertProperties.push_back(static_cast<float>(pt.x()));
                meshgl.vertProperties.push_back(static_cast<float>(pt.y()));
                meshgl.vertProperties.push_back(static_cast<float>(pt.z()));
                if (flip_normals) {
                  meshgl.vertProperties.push_back(static_cast<float>(-normal.x()));
                  meshgl.vertProperties.push_back(static_cast<float>(-normal.y()));
                  meshgl.vertProperties.push_back(static_cast<float>(-normal.z()));
                } else {
                  meshgl.vertProperties.push_back(static_cast<float>(normal.x()));
                  meshgl.vertProperties.push_back(static_cast<float>(normal.y()));
                  meshgl.vertProperties.push_back(static_cast<float>(normal.z()));
                }
            }

            meshgl.triVerts.push_back(vert_idx);
            meshgl.triVerts.push_back(vert_idx + 1);
            meshgl.triVerts.push_back(vert_idx + 2);
            vert_idx += 3;
        }
    } else {
        meshgl.vertProperties.reserve(sm.number_of_vertices() * meshgl.numProp);
        meshgl.triVerts.reserve(sm.number_of_faces() * 3);

        for (auto v : sm.vertices()) {
            const auto& pt = sm.point(v);
            meshgl.vertProperties.push_back(static_cast<float>(pt.x()));
            meshgl.vertProperties.push_back(static_cast<float>(pt.y()));
            meshgl.vertProperties.push_back(static_cast<float>(pt.z()));
        }

        for (auto f : sm.faces()) {
            auto h = sm.halfedge(f);
            uint32_t v0 = static_cast<uint32_t>(sm.target(h));
            h = sm.next(h);
            uint32_t v1 = static_cast<uint32_t>(sm.target(h));
            h = sm.next(h);
            uint32_t v2 = static_cast<uint32_t>(sm.target(h));

            meshgl.triVerts.push_back(v0);
            meshgl.triVerts.push_back(v1);
            meshgl.triVerts.push_back(v2);
        }
    }

    return meshgl;
}

void append_meshgl(manifold::MeshGL& dst, const manifold::MeshGL& src) {
    if (src.NumTri() == 0) {
        return;
    }
    if (dst.numProp == 0) {
        dst.numProp = src.numProp;
    }
    if (dst.numProp != src.numProp) {
        throw std::runtime_error("Cannot append MeshGL with different numProp");
    }

    uint32_t vertex_offset = static_cast<uint32_t>(dst.vertProperties.size() / dst.numProp);
    dst.vertProperties.insert(dst.vertProperties.end(), src.vertProperties.begin(), src.vertProperties.end());
    dst.triVerts.reserve(dst.triVerts.size() + src.triVerts.size());
    for (uint32_t tri_vert : src.triVerts) {
        dst.triVerts.push_back(vertex_offset + tri_vert);
    }
}

void apply_meshgl_offset(manifold::MeshGL& mesh, double offset_x, double offset_y, double offset_z) {
    if (mesh.numProp < 3) {
        return;
    }
    for (size_t i = 0; i + 2 < mesh.vertProperties.size(); i += mesh.numProp) {
        mesh.vertProperties[i] += static_cast<float>(offset_x);
        mesh.vertProperties[i + 1] += static_cast<float>(offset_y);
        mesh.vertProperties[i + 2] += static_cast<float>(offset_z);
    }
}

double mesh_min_z(const Surface_mesh& sm) {
    double min_z = std::numeric_limits<double>::infinity();
    for (auto v : sm.vertices()) {
        const double z = sm.point(v).z();
        if (z < min_z) {
            min_z = z;
        }
    }
    return min_z;
}
