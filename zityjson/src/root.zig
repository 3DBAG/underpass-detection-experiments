const std = @import("std");

// Face type attribute
pub const FaceType = enum(u8) {
    wall,
    floor,
    ceiling,
    roof,
    window,
    door,
    // Add more as needed
};

// A face is a polygon defined by indices into the vertex array
pub const PolygonalFace = struct {
    start: usize,      // Start index into indices array
    count: usize,      // Number of vertices in this face
    face_type: FaceType,

    // Optional: add more face-level attributes here
    // material_id: u16,
    // normal: [3]f64,
};

pub const PolygonalMesh = struct {
    allocator: std.mem.Allocator,

    // Vertex positions (x, y, z triplets)
    vertices: std.ArrayList(f64),

    // Vertex indices for all faces (stored contiguously)
    indices: std.ArrayList(usize),

    // Face definitions
    faces: std.ArrayList(PolygonalFace),

    pub fn init(allocator: std.mem.Allocator) PolygonalMesh {
        return .{
            .allocator = allocator,
            .vertices = .{},
            .indices = .{},
            .faces = .{},
        };
    }

    pub fn deinit(self: *PolygonalMesh) void {
        self.vertices.deinit(self.allocator);
        self.indices.deinit(self.allocator);
        self.faces.deinit(self.allocator);
    }

    // Add a vertex, returns its index
    pub fn addVertex(self: *PolygonalMesh, v:[3]f64) !usize {
        const idx: usize = @intCast(self.vertices.items.len / 3);
        try self.vertices.appendSlice(self.allocator, &.{ v[0], v[1], v[2] });
        return idx;
    }

    // Add a face from vertex indices
    pub fn addFace(self: *PolygonalMesh, vertex_indices: []const usize, face_type: FaceType) !void {
        const start: usize = @intCast(self.indices.items.len);
        try self.indices.appendSlice(self.allocator, vertex_indices);
        try self.faces.append(self.allocator, .{
            .start = start,
            .count = @intCast(vertex_indices.len),
            .face_type = face_type,
        });
    }

    // Get vertex indices for a face
    pub fn getFaceIndices(self: *const PolygonalMesh, face: PolygonalFace) []const usize {
        return self.indices.items[face.start..][0..face.count];
    }

    // Get vertex position by index
    pub fn getVertex(self: *const PolygonalMesh, idx: usize) [3]f64 {
        const i = idx * 3;
        return .{
            self.vertices.items[i],
            self.vertices.items[i + 1],
            self.vertices.items[i + 2],
        };
    }
};

pub const CJGeometry = struct {
    type: CJGeometryType,
    lod: []const u8,
    boundaries: std.json.Value,
};

pub const CJObject = struct {
    type: CJObjectType,
    geometry: []const CJGeometry,
};

const CJFile = struct {
    version: []const u8,
    type: []const u8,
    vertices: []const [3]i64,
    CityObjects: std.json.ArrayHashMap(CJObject),
    transform: struct {
        scale: [3]f64,
        translate: [3]f64,
    },

    // Methods are fine - JSON parsing ignores them
    pub fn getTransformedVertex(self: @This(), idx: usize) [3]f64 {
        const v = self.vertices[idx];
        return .{
            @as(f64, @floatFromInt(v[0])) * self.transform.scale[0] + self.transform.translate[0],
            @as(f64, @floatFromInt(v[1])) * self.transform.scale[1] + self.transform.translate[1],
            @as(f64, @floatFromInt(v[2])) * self.transform.scale[2] + self.transform.translate[2],
        };
    }

    pub fn vertexCount(self: @This()) usize {
        return self.vertices.len;
    }
};

const CJMultiSurfaceBounds = []const []const []usize;
const CJSolidBounds = []const []const []const []usize;

const CJGeometryType = enum { MultiSurface, Solid };
const CJObjectType = enum { Building, BuildingPart };

pub const CityJSON = struct {

    pub const StoredCityObject = struct {
        type: CJObjectType,
        geometries: [] StoredGeometry,

        pub fn init(allocator: std.mem.Allocator, object_type: CJObjectType, num_geometries: usize) !StoredCityObject {
            return StoredCityObject{
                .type = object_type,
                .geometries = try allocator.alloc(StoredGeometry, num_geometries),
            };
        }

        pub fn deinit(self: *StoredCityObject, allocator: std.mem.Allocator) void {
          for (self.geometries) |*geometry| {
            geometry.deinit(allocator);
          }
          allocator.free(self.geometries);
        }
    };

    pub const StoredGeometry = struct {
        type: CJGeometryType,
        lod: []const u8,
        polygonal_mesh: PolygonalMesh,

        pub fn init(allocator: std.mem.Allocator, geometry_type: CJGeometryType, lod: []const u8) !StoredGeometry {
            return StoredGeometry{
                .type = geometry_type,
                .lod = try allocator.dupe(u8, lod),
                .polygonal_mesh = PolygonalMesh.init(allocator),
            };
        }

        pub fn deinit(self: *StoredGeometry, allocator: std.mem.Allocator) void {
          allocator.free(self.lod);
          self.polygonal_mesh.deinit();
        }
    };

    allocator: std.mem.Allocator,
    // file: CJFile,
    objects: std.StringArrayHashMap(StoredCityObject),

    pub fn init(allocator: std.mem.Allocator) !CityJSON {
        return CityJSON{
            .allocator = allocator,
            // .file = undefined,
            .objects = .init(allocator),
        };
    }

    pub fn deinit(self: *CityJSON) void {
        for (self.objects.keys(), self.objects.values()) |key, *object| {
            object.deinit(self.allocator);
            // need to add 1 to account for null terminator (needed for C api)
            self.allocator.free(key.ptr[0..key.len + 1]);
        }
        self.objects.deinit();
        // self.file.CityObjects.deinit();
        // self.file.vertices.deinit();
        // self.file.transform.scale.deinit();
        // self.file.transform.translate.deinit();
        // self.file.version.deinit();
        // self.file.type.deinit();
    }

    pub fn load(self: *CityJSON, path: []const u8) !void {
      const file = if (std.fs.path.isAbsolute(path))
          try std.fs.openFileAbsolute(path, .{ .mode = .read_only })
      else
          try std.fs.cwd().openFile(path, .{ .mode = .read_only });
      defer file.close();
      var read_buf: [2048]u8 = undefined;
      var f_reader: std.fs.File.Reader = file.reader(&read_buf);

      var j_reader = std.json.Reader.init(self.allocator, &f_reader.interface);
      defer j_reader.deinit();

      // Parse into the struct
      const parsed = try std.json.parseFromTokenSource(CJFile, self.allocator, &j_reader, .{
          .ignore_unknown_fields = true,
      });
      defer parsed.deinit();

      const cj = parsed.value;
      // std.debug.print("File version: {s}, type: {s}, Nr of vertices: {d}\n", .{
          // cj.version, cj.type, cj.vertices.len
      // });
      // print first 5 vertices
      // for (cj.vertices[0..5]) |vertex| {
      //     std.debug.print("{d}, {d}, {d}\n",
      //       .{  @as(f64, @floatFromInt(vertex[0]))*cj.transform.scale[0] + cj.transform.translate[0],
      //           @as(f64, @floatFromInt(vertex[1]))*cj.transform.scale[1] + cj.transform.translate[1],
      //           @as(f64, @floatFromInt(vertex[2]))*cj.transform.scale[2] + cj.transform.translate[2]
      //       });
      // }
      // print transform
      // std.debug.print("Scale: {d}, {d}, {d}\n", .{ cj.transform.scale[0], cj.transform.scale[1], cj.transform.scale[2] });
      // std.debug.print("Translate: {d}, {d}, {d}\n", .{ cj.transform.translate[0], cj.transform.translate[1], cj.transform.translate[2] });

      // Accessing the dynamic part:
      const city_objs = parsed.value.CityObjects; // It's an ArrayHashMap
      for (city_objs.map.keys(), city_objs.map.values()) |key, obj| {
          // std.debug.print("\nID: {s}\n", .{key});
          // std.debug.print("Type: {s}\n", .{@tagName(obj.type)});

          const owned_key = try self.allocator.dupeZ(u8, key);
          try self.objects.put(owned_key, try StoredCityObject.init(self.allocator, obj.type, obj.geometry.len));
          const stored_city_object = self.objects.getPtr(key).?;

          for (obj.geometry, 0..) |g, i| {
              // std.debug.print("Geometry Type: {s}\n", .{@tagName(g.type)});
              // std.debug.print("LOD: {s}\n", .{g.lod});

              const geom = &stored_city_object.geometries[i];
              geom.* = try StoredGeometry.init(self.allocator, g.type, g.lod);

              switch (g.type) {
                  .MultiSurface => {
                    const parsed_ = std.json.parseFromValue(CJMultiSurfaceBounds, self.allocator, g.boundaries, .{}) catch |err| {
                        std.debug.print("Error parsing bounds: {any}\n", .{err});
                        return;
                    };
                    defer parsed_.deinit();
                    const bounds = parsed_.value;
                    for (bounds) |polygon| {
                        for (polygon) |ring| {
                            // Collect vertex indices for this ring
                            var ring_indices = try std.ArrayList(usize).initCapacity(self.allocator, ring.len);
                            defer ring_indices.deinit(self.allocator);

                            // TODO: handle holes better
                            for (ring) |vi| {
                                const vertex_idx = try geom.polygonal_mesh.addVertex(cj.getTransformedVertex(vi));
                                try ring_indices.append(self.allocator, vertex_idx);
                            }

                            // Add the face for this ring
                            try geom.polygonal_mesh.addFace(ring_indices.items, .wall);  // or appropriate FaceType
                        }
                    }
                  },
                  .Solid => {
                    // std.debug.print("Solid type\n", .{});
                    const parsed_ = std.json.parseFromValue(CJSolidBounds, self.allocator, g.boundaries, .{}) catch |err| {
                        std.debug.print("Error parsing bounds: {any}\n", .{err});
                        return;
                    };
                    defer parsed_.deinit();
                    const bounds = parsed_.value;
                    // todo handle interiot vs exterior shells
                    for (bounds) |shell| {
                        for (shell) |polygon| {
                            for (polygon) |ring| {
                                // Collect vertex indices for this ring
                                var ring_indices = try std.ArrayList(usize).initCapacity(self.allocator, ring.len);
                                defer ring_indices.deinit(self.allocator);

                                // TODO: handle holes better vs exterior ring
                                for (ring) |vi| {
                                    const vertex_idx = try geom.polygonal_mesh.addVertex(cj.getTransformedVertex(vi));
                                    try ring_indices.append(self.allocator, vertex_idx);
                                }

                                // Add the face for this ring
                                try geom.polygonal_mesh.addFace(ring_indices.items, .wall);  // or appropriate FaceType
                            }
                        }
                    }
                  },
              }

              // std.debug.print("Mesh has {d} faces\n", .{geom.polygonal_mesh.faces.items.len});
              // std.debug.print("Mesh has {d} vertices\n", .{geom.polygonal_mesh.vertices.items.len/3});
          }
      }
    }

};

// // =============================================================================
// // C API exports
// // =============================================================================

var c_allocator: std.mem.Allocator = std.heap.c_allocator;

// C API opaque handle
pub const CityJSONHandle = *CityJSON;

/// Create a new CityJSON instance. Returns null on failure.
export fn cityjson_create() callconv(.c) ?CityJSONHandle {
    const cj = c_allocator.create(CityJSON) catch return null;
    cj.* = CityJSON.init(c_allocator) catch {
        c_allocator.destroy(cj);
        return null;
    };
    return cj;
}

/// Destroy a CityJSON instance and free all associated memory.
export fn cityjson_destroy(handle: ?CityJSONHandle) callconv(.c) void {
    if (handle) |cj| {
        cj.deinit();
        c_allocator.destroy(cj);
    }
}

/// Load a CityJSON file. Returns 0 on success, non-zero on failure.
export fn cityjson_load(handle: ?CityJSONHandle, path: [*c]const u8) callconv(.c) c_int {
    const cj = handle orelse return -1;
    const path_slice = std.mem.span(path);
    // std.debug.print("Loading CityJSON: {s}\n", .{path});
    cj.load(path_slice) catch |err| {
        std.debug.print("Error loading CityJSON: {}\n", .{err});
        return -1;
    };
    return 0;
}

/// Get the number of objects in the CityJSON.
export fn cityjson_object_count(handle: ?CityJSONHandle) callconv(.c) usize {
    const cj = handle orelse return 0;
    return cj.objects.count();
}

/// Get the name of an object by index. Returns null if index is out of bounds.
export fn cityjson_get_object_name(handle: ?CityJSONHandle, index: usize) callconv(.c) [*c]const u8 {
    const cj = handle orelse return null;
    const keys = cj.objects.keys();
    if (index >= keys.len) return null;
    return keys[index].ptr;
}

/// Get the index of an object by its key (name). Returns -1 if not found.
export fn cityjson_get_object_index(handle: ?CityJSONHandle, key: [*c]const u8) callconv(.c) isize {
    const cj = handle orelse return -1;
    const key_slice = std.mem.span(key);
    const index = cj.objects.getIndex(key_slice);
    if (index) |idx| {
        return @intCast(idx);
    }
    return -1;
}

/// Get the geometry count for an object by index.
export fn cityjson_get_geometry_count(handle: ?CityJSONHandle, object_index: usize) callconv(.c) usize {
    const cj = handle orelse return 0;
    const values = cj.objects.values();
    if (object_index >= values.len) return 0;
    return values[object_index].geometries.len;
}

/// Get the vertex count for a geometry by object and geometry index.
export fn cityjson_get_vertex_count(handle: ?CityJSONHandle, object_index: usize, geometry_index: usize) callconv(.c) usize {
    const cj = handle orelse return 0;
    const values = cj.objects.values();
    if (object_index >= values.len) return 0;
    const geometries = values[object_index].geometries;
    if (geometry_index >= geometries.len) return 0;
    return geometries[geometry_index].polygonal_mesh.vertices.items.len / 3;
}

/// Get the face count for a geometry by object and geometry index.
export fn cityjson_get_face_count(handle: ?CityJSONHandle, object_index: usize, geometry_index: usize) callconv(.c) usize {
    const cj = handle orelse return 0;
    const values = cj.objects.values();
    if (object_index >= values.len) return 0;
    const geometries = values[object_index].geometries;
    if (geometry_index >= geometries.len) return 0;
    return geometries[geometry_index].polygonal_mesh.faces.items.len;
}

/// Get pointer to vertex data (x, y, z triplets as f64) for a geometry by object and geometry index.
export fn cityjson_get_vertices(handle: ?CityJSONHandle, object_index: usize, geometry_index: usize) callconv(.c) [*c]const f64 {
    const cj = handle orelse return null;
    const values = cj.objects.values();
    if (object_index >= values.len) return null;
    const geometries = values[object_index].geometries;
    if (geometry_index >= geometries.len) return null;
    return geometries[geometry_index].polygonal_mesh.vertices.items.ptr;
}

/// Get pointer to index data for a geometry by object and geometry index.
export fn cityjson_get_indices(handle: ?CityJSONHandle, object_index: usize, geometry_index: usize) callconv(.c) [*c]const usize {
    const cj = handle orelse return null;
    const values = cj.objects.values();
    if (object_index >= values.len) return null;
    const geometries = values[object_index].geometries;
    if (geometry_index >= geometries.len) return null;
    return geometries[geometry_index].polygonal_mesh.indices.items.ptr;
}

/// Get the index count for a geometry by object and geometry index.
export fn cityjson_get_index_count(handle: ?CityJSONHandle, object_index: usize, geometry_index: usize) callconv(.c) usize {
    const cj = handle orelse return 0;
    const values = cj.objects.values();
    if (object_index >= values.len) return 0;
    const geometries = values[object_index].geometries;
    if (geometry_index >= geometries.len) return 0;
    return geometries[geometry_index].polygonal_mesh.indices.items.len;
}

/// Get face info: start index and vertex count. Returns 0 on success, -1 on failure.
export fn cityjson_get_face_info(
    handle: ?CityJSONHandle,
    object_index: usize,
    geometry_index: usize,
    face_index: usize,
    out_start: *usize,
    out_count: *usize,
    out_face_type: *u8,
) callconv(.c) c_int {
    const cj = handle orelse return -1;
    const values = cj.objects.values();
    if (object_index >= values.len) return -1;
    const geometries = values[object_index].geometries;
    if (geometry_index >= geometries.len) return -1;
    const mesh = &geometries[geometry_index].polygonal_mesh;
    if (face_index >= mesh.faces.items.len) return -1;
    const face = mesh.faces.items[face_index];
    out_start.* = face.start;
    out_count.* = face.count;
    out_face_type.* = @intFromEnum(face.face_type);
    return 0;
}
