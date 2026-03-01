#ifndef MESH_CONVERSION_H
#define MESH_CONVERSION_H

#include <CGAL/Exact_predicates_exact_constructions_kernel.h>
#include <CGAL/Surface_mesh.h>

#include <manifold/manifold.h>
#include "BooleanOps.h"

using Exact_kernel = CGAL::Exact_predicates_exact_constructions_kernel;
using Exact_surface_mesh = CGAL::Surface_mesh<Exact_kernel::Point_3>;

Exact_surface_mesh surface_mesh_to_exact(const Surface_mesh& sm);
Surface_mesh exact_to_surface_mesh(const Exact_surface_mesh& esm);

manifold::MeshGL surface_mesh_to_meshgl(Surface_mesh& sm, bool compute_normals = true, bool flip_normals = false);

void append_meshgl(manifold::MeshGL& dst, const manifold::MeshGL& src);
void apply_meshgl_offset(manifold::MeshGL& mesh, double offset_x, double offset_y, double offset_z);
double mesh_min_z(const Surface_mesh& sm);

#endif // MESH_CONVERSION_H
