#ifndef MESH_CONVERSION_H
#define MESH_CONVERSION_H

#include <manifold/manifold.h>
#include "BooleanOps.h"

manifold::MeshGL surface_mesh_to_meshgl(Surface_mesh& sm, bool compute_normals = true, bool flip_normals = false);

void append_meshgl(manifold::MeshGL& dst, const manifold::MeshGL& src);
void apply_meshgl_offset(manifold::MeshGL& mesh, double offset_x, double offset_y, double offset_z);
double mesh_min_z(const Surface_mesh& sm);

#endif // MESH_CONVERSION_H
