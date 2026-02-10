// Copyright (c) 2018-2024 TU Delft 3D geoinformation group, Ravi Peters (3DGI),
// and Balazs Dukai (3DGI)

// Adapted for standalone use with CGAL Surface_mesh.

#pragma once

#include <CGAL/Simple_cartesian.h>
#include <CGAL/Surface_mesh.h>

#include <array>
#include <vector>

#include "OGRVectorReader.h"

#ifdef ENABLE_RERUN
#include <rerun.hpp>
#endif

namespace extrusion {

using K = CGAL::Simple_cartesian<double>;
using Point_3 = K::Point_3;
using Surface_mesh = CGAL::Surface_mesh<Point_3>;

// Extrude a 2D polygon (LinearRing) into a 3D solid mesh.
// The polygon is extruded from floor_height to roof_height.
// The resulting mesh includes floor, roof, and wall faces.
// Returns a closed CGAL Surface_mesh.
Surface_mesh extrude_polygon(const ogr::LinearRing& ring, double floor_height,
                             double roof_height, bool ignore_holes = false);

#ifdef ENABLE_RERUN
// Set the rerun recording stream for CDT visualization.
// Call this before extrude_polygon to enable visualization.
void set_rerun_recording_stream(const rerun::RecordingStream* rec);
#endif

}  // namespace extrusion
