// Copyright (c) 2018-2024 TU Delft 3D geoinformation group, Ravi Peters (3DGI),
// and Balazs Dukai (3DGI)

// Adapted for standalone use.

#pragma once

#include <gdal_priv.h>
#include <ogrsf_frmts.h>

#include <array>
#include <memory>
#include <string>
#include <vector>

namespace ogr {

// A linear ring representing a polygon exterior with optional interior rings
// (holes). Points are stored as 3D coordinates (x, y, z).
class LinearRing : public std::vector<std::array<double, 3>> {
 public:
  using std::vector<std::array<double, 3>>::vector;

  std::vector<std::vector<std::array<double, 3>>>& interior_rings() {
    return interior_rings_;
  }
  const std::vector<std::vector<std::array<double, 3>>>& interior_rings()
      const {
    return interior_rings_;
  }

 private:
  std::vector<std::vector<std::array<double, 3>>> interior_rings_;
};

// Layer extent: {minX, minY, minZ, maxX, maxY, maxZ}
using Extent = std::array<double, 6>;

class VectorReader {
 public:
  VectorReader() = default;
  ~VectorReader() = default;

  // Non-copyable
  VectorReader(const VectorReader&) = delete;
  VectorReader& operator=(const VectorReader&) = delete;

  // Movable
  VectorReader(VectorReader&&) = default;
  VectorReader& operator=(VectorReader&&) = default;

  // Open a vector data source (shapefile, GeoPackage, GeoJSON, etc.)
  void open(const std::string& source);

  // Read all polygons from the layer
  std::vector<LinearRing> read_polygons();

  // Get the number of features in the layer
  size_t get_feature_count();

  // Configuration setters (call before open())
  void set_layer_id(int id) { layer_id_ = id; }
  void set_layer_name(const std::string& name) { layer_name_ = name; }

  // Getters
  const Extent& layer_extent() const { return layer_extent_; }
  int layer_count() const { return layer_count_; }

 private:
  void read_polygon(OGRPolygon* poPolygon, std::vector<LinearRing>& polygons);

  GDALDatasetUniquePtr poDS_;
  OGRLayer* poLayer_ = nullptr;

  int layer_count_ = 0;
  int layer_id_ = 0;
  std::string layer_name_;
  Extent layer_extent_ = {0, 0, 0, 0, 0, 0};
};

}  // namespace ogr
