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

#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string_view>

namespace {

std::string quote_identifier(std::string_view ident) {
  std::string out;
  out.reserve(ident.size() + 2);
  out.push_back('"');
  for (char ch : ident) {
    if (ch == '"') {
      out.push_back('"');
      out.push_back('"');
    } else {
      out.push_back(ch);
    }
  }
  out.push_back('"');
  return out;
}

std::string quote_qualified_name(std::string_view name) {
  if (name.empty()) {
    return {};
  }

  std::string out;
  size_t start = 0;
  while (start <= name.size()) {
    size_t dot = name.find('.', start);
    std::string_view part = (dot == std::string_view::npos)
                                ? name.substr(start)
                                : name.substr(start, dot - start);
    if (!out.empty()) {
      out.push_back('.');
    }
    out += quote_identifier(part);
    if (dot == std::string_view::npos) {
      break;
    }
    start = dot + 1;
  }
  return out;
}

std::string make_pg_bbox_query(OGRLayer* layer,
                               const std::string& id_attribute,
                               const std::string& height_attribute,
                               double min_x,
                               double min_y,
                               double max_x,
                               double max_y) {
  std::string layer_name = layer != nullptr && layer->GetName() != nullptr
                               ? layer->GetName()
                               : std::string();

  std::string geom_col = "geom";
  if (layer != nullptr) {
    OGRFeatureDefn* defn = layer->GetLayerDefn();
    if (defn != nullptr && defn->GetGeomFieldCount() > 0) {
      OGRGeomFieldDefn* geom_defn = defn->GetGeomFieldDefn(0);
      if (geom_defn != nullptr && geom_defn->GetNameRef() != nullptr &&
          geom_defn->GetNameRef()[0] != '\0') {
        geom_col = geom_defn->GetNameRef();
      }
    }
  }

  std::ostringstream sql;
  sql << std::setprecision(17);
  sql << "SELECT " << quote_identifier(id_attribute) << ", "
      << quote_identifier(height_attribute) << ", " << quote_identifier(geom_col)
      << " FROM " << quote_qualified_name(layer_name) << " WHERE "
      << quote_identifier(geom_col) << " && ST_MakeEnvelope(" << min_x << ", "
      << min_y << ", " << max_x << ", " << max_y << ")";
  return sql.str();
}

}  // namespace

namespace ogr {

void VectorReader::set_spatial_filter_rect(double min_x,
                                           double min_y,
                                           double max_x,
                                           double max_y) {
  has_spatial_filter_ = true;
  spatial_filter_extent_ = {min_x, min_y, 0, max_x, max_y, 0};
  if (poLayer_ != nullptr) {
    poLayer_->SetSpatialFilterRect(min_x, min_y, max_x, max_y);
  }
}

void VectorReader::clear_spatial_filter() {
  has_spatial_filter_ = false;
  spatial_filter_extent_ = {0, 0, 0, 0, 0, 0};
  if (poLayer_ != nullptr) {
    poLayer_->SetSpatialFilter(nullptr);
  }
}

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

  if (has_spatial_filter_) {
    poLayer_->SetSpatialFilterRect(spatial_filter_extent_[0],
                                   spatial_filter_extent_[1],
                                   spatial_filter_extent_[3],
                                   spatial_filter_extent_[4]);
  } else {
    poLayer_->SetSpatialFilter(nullptr);
  }

  // Compute layer extent from fast metadata path only.
  // On database-backed layers (e.g. PostGIS), forcing extent computation can
  // trigger a full-table scan and stall startup.
  OGREnvelope extent;
  auto error = poLayer_->GetExtent(&extent, false);
  if (!error) {
    layer_extent_ = {extent.MinX, extent.MinY, 0, extent.MaxX, extent.MaxY, 0};
  } else {
    layer_extent_ = {0, 0, 0, 0, 0, 0};
  }
}

void VectorReader::read_polygon(OGRPolygon* poPolygon,
                                std::vector<LinearRing>& polygons) {
  if (poPolygon == nullptr) {
    return;
  }

  LinearRing gf_polygon;
  OGRPoint poPoint;
  auto ogr_ering = poPolygon->getExteriorRing();
  if (ogr_ering == nullptr) {
    return;
  }

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
    if (ogr_iring == nullptr) {
      continue;
    }
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

void VectorReader::read_polygon_feature(
    OGRPolygon* poPolygon,
    const std::string& id,
    double absolute_elevation,
    bool has_absolute_elevation,
    std::vector<PolygonFeature>& features) {
  if (poPolygon == nullptr) {
    return;
  }

  LinearRing polygon;
  OGRPoint poPoint;
  auto ogr_ering = poPolygon->getExteriorRing();
  if (ogr_ering == nullptr) {
    return;
  }

  // Ensure we output CCW exterior ring
  if (ogr_ering->isClockwise()) {
    ogr_ering->reversePoints();
  }

  for (int i = 0; i < ogr_ering->getNumPoints() - 1; ++i) {
    ogr_ering->getPoint(i, &poPoint);
    polygon.push_back({poPoint.getX(), poPoint.getY(), poPoint.getZ()});
  }

  // Read interior rings (holes)
  for (int i = 0; i < poPolygon->getNumInteriorRings(); ++i) {
    auto ogr_iring = poPolygon->getInteriorRing(i);
    if (ogr_iring == nullptr) {
      continue;
    }
    // Ensure we output CW interior ring
    if (!ogr_iring->isClockwise()) {
      ogr_iring->reversePoints();
    }
    std::vector<std::array<double, 3>> hole;
    for (int j = 0; j < ogr_iring->getNumPoints() - 1; ++j) {
      ogr_iring->getPoint(j, &poPoint);
      hole.push_back({poPoint.getX(), poPoint.getY(), poPoint.getZ()});
    }
    polygon.interior_rings().push_back(std::move(hole));
  }

  PolygonFeature feature;
  feature.polygon = std::move(polygon);
  feature.id = id;
  feature.absolute_elevation = absolute_elevation;
  feature.has_absolute_elevation = has_absolute_elevation;
  features.push_back(std::move(feature));
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

std::vector<VectorReader::PolygonFeature> VectorReader::read_polygon_features(
    const std::string& id_attribute,
    const std::string& height_attribute) {
  if (poLayer_ == nullptr) {
    throw std::runtime_error("[VectorReader] Layer is not open");
  }

  std::vector<PolygonFeature> features;
  OGRLayer* read_layer = poLayer_;
  OGRLayer* sql_layer = nullptr;
  if (has_spatial_filter_ && poDS_ != nullptr && poDS_->GetDriver() != nullptr &&
      poDS_->GetDriver()->GetDescription() != nullptr &&
      std::string_view(poDS_->GetDriver()->GetDescription()) == "PostgreSQL") {
    const std::string sql = make_pg_bbox_query(poLayer_,
                                               id_attribute,
                                               height_attribute,
                                               spatial_filter_extent_[0],
                                               spatial_filter_extent_[1],
                                               spatial_filter_extent_[3],
                                               spatial_filter_extent_[4]);
    sql_layer = poDS_->ExecuteSQL(sql.c_str(), nullptr, nullptr);
    if (sql_layer != nullptr) {
      read_layer = sql_layer;
    }
  }

  read_layer->ResetReading();

  OGRFeature* poFeature;
  while ((poFeature = read_layer->GetNextFeature()) != nullptr) {
    OGRGeometry* poGeometry = poFeature->GetGeometryRef();
    if (poGeometry == nullptr) {
      OGRFeature::DestroyFeature(poFeature);
      continue;
    }

    std::string id;
    int id_field_idx = poFeature->GetFieldIndex(id_attribute.c_str());
    if (id_field_idx >= 0 && poFeature->IsFieldSetAndNotNull(id_field_idx)) {
      id = poFeature->GetFieldAsString(id_field_idx);
    }

    double absolute_elevation = 0.0;
    bool has_absolute_elevation = false;
    int h_field_idx = poFeature->GetFieldIndex(height_attribute.c_str());
    if (h_field_idx >= 0 && poFeature->IsFieldSetAndNotNull(h_field_idx)) {
      absolute_elevation = poFeature->GetFieldAsDouble(h_field_idx);
      has_absolute_elevation = true;
    }

    if (wkbFlatten(poGeometry->getGeometryType()) == wkbPolygon) {
      OGRPolygon* poPolygon = poGeometry->toPolygon();
      read_polygon_feature(poPolygon, id, absolute_elevation, has_absolute_elevation, features);
    } else if (wkbFlatten(poGeometry->getGeometryType()) == wkbMultiPolygon) {
      OGRMultiPolygon* poMultiPolygon = poGeometry->toMultiPolygon();
      for (auto poly_it = poMultiPolygon->begin();
           poly_it != poMultiPolygon->end(); ++poly_it) {
        read_polygon_feature(*poly_it, id, absolute_elevation, has_absolute_elevation, features);
      }
    }

    OGRFeature::DestroyFeature(poFeature);
  }

  if (sql_layer != nullptr) {
    poDS_->ReleaseResultSet(sql_layer);
  }

  return features;
}

size_t VectorReader::get_feature_count() {
  if (poLayer_ == nullptr) {
    throw std::runtime_error("[VectorReader] Layer is not open");
  }
  return static_cast<size_t>(poLayer_->GetFeatureCount());
}

}  // namespace ogr
