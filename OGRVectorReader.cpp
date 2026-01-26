// Copyright (c) 2018-2024 TU Delft 3D geoinformation group, Ravi Peters (3DGI),
// and Balazs Dukai (3DGI)

// This file is part of roofer (https://github.com/3DBAG/roofer)
// Adapted for standalone use.

// geoflow-roofer is free software: you can redistribute it and/or modify it
// under the terms of the GNU General Public License as published by the Free
// Software Foundation, either version 3 of the License, or (at your option) any
// later version. geoflow-roofer is distributed in the hope that it will be
// useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
// Public License for more details. You should have received a copy of the GNU
// General Public License along with geoflow-roofer. If not, see
// <https://www.gnu.org/licenses/>.

// Author(s):
// Ravi Peters

#include "OGRVectorReader.h"

#include <ogrsf_frmts.h>

#include <iostream>
#include <stdexcept>

namespace ogr {

void VectorReader::open(const std::string& source) {
  if (GDALGetDriverCount() == 0) {
    GDALAllRegister();
  }

  poDS_.reset(GDALDataset::Open(source.c_str(), GDAL_OF_VECTOR));
  if (poDS_ == nullptr) {
    auto error_msg = CPLGetLastErrorMsg();
    throw std::runtime_error("[VectorReader] Open failed on " + source +
                             " with error: " + error_msg);
  }

  layer_count_ = poDS_->GetLayerCount();

  // Try to get layer by name first, fall back to layer_id
  if (!layer_name_.empty()) {
    poLayer_ = poDS_->GetLayerByName(layer_name_.c_str());
  }

  if (poLayer_ == nullptr) {
    if (layer_id_ >= layer_count_) {
      throw std::runtime_error(
          "[VectorReader] Illegal layer ID! Layer ID must be less than the "
          "layer count (" +
          std::to_string(layer_count_) + ").");
    }
    if (layer_id_ < 0) {
      throw std::runtime_error(
          "[VectorReader] Illegal layer ID! Layer ID cannot be negative.");
    }
    poLayer_ = poDS_->GetLayer(layer_id_);
  }

  if (poLayer_ == nullptr) {
    throw std::runtime_error("[VectorReader] Could not get the selected layer");
  }

  // Compute layer extent
  OGREnvelope extent;
  auto error = poLayer_->GetExtent(&extent);
  if (error) {
    throw std::runtime_error(
        "[VectorReader] Could not get the extent of the layer");
  }
  layer_extent_ = {extent.MinX, extent.MinY, 0, extent.MaxX, extent.MaxY, 0};
}

void VectorReader::read_polygon(OGRPolygon* poPolygon,
                                std::vector<LinearRing>& polygons) {
  LinearRing gf_polygon;
  OGRPoint poPoint;
  auto ogr_ering = poPolygon->getExteriorRing();

  // Ensure we output CCW exterior ring
  if (ogr_ering->isClockwise()) {
    ogr_ering->reversePoints();
  }

  for (int i = 0; i < ogr_ering->getNumPoints() - 1; ++i) {
    ogr_ering->getPoint(i, &poPoint);
    gf_polygon.push_back(
        {poPoint.getX(), poPoint.getY(), poPoint.getZ()});
  }

  // Read interior rings (holes)
  for (int i = 0; i < poPolygon->getNumInteriorRings(); ++i) {
    auto ogr_iring = poPolygon->getInteriorRing(i);
    // Ensure we output CW interior ring
    if (!ogr_iring->isClockwise()) {
      ogr_iring->reversePoints();
    }
    std::vector<std::array<double, 3>> gf_iring;
    for (int j = 0; j < ogr_iring->getNumPoints() - 1; ++j) {
      ogr_iring->getPoint(j, &poPoint);
      gf_iring.push_back(
          {poPoint.getX(), poPoint.getY(), poPoint.getZ()});
    }
    gf_polygon.interior_rings().push_back(gf_iring);
  }
  polygons.push_back(gf_polygon);
}

std::vector<LinearRing> VectorReader::read_polygons() {
  if (poLayer_ == nullptr) {
    throw std::runtime_error("[VectorReader] Layer is not open");
  }

  std::vector<LinearRing> polygons;

  poLayer_->ResetReading();

  OGRFeature* poFeature;
  while ((poFeature = poLayer_->GetNextFeature()) != nullptr) {
    OGRGeometry* poGeometry = poFeature->GetGeometryRef();

    if (poGeometry == nullptr) {
      OGRFeature::DestroyFeature(poFeature);
      continue;
    }

    if (wkbFlatten(poGeometry->getGeometryType()) == wkbPolygon) {
      OGRPolygon* poPolygon = poGeometry->toPolygon();
      read_polygon(poPolygon, polygons);
    } else if (wkbFlatten(poGeometry->getGeometryType()) == wkbMultiPolygon) {
      OGRMultiPolygon* poMultiPolygon = poGeometry->toMultiPolygon();
      for (auto poly_it = poMultiPolygon->begin();
           poly_it != poMultiPolygon->end(); ++poly_it) {
        read_polygon(*poly_it, polygons);
      }
    }
    // Skip unsupported geometry types silently

    OGRFeature::DestroyFeature(poFeature);
  }

  return polygons;
}

size_t VectorReader::get_feature_count() {
  if (poLayer_ == nullptr) {
    throw std::runtime_error("[VectorReader] Layer is not open");
  }
  return static_cast<size_t>(poLayer_->GetFeatureCount());
}

}  // namespace ogr
