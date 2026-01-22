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

const CityJSONFile = struct {
    version: []const u8,
    type: []const u8,
    vertices: []const [3]usize,
    CityObjects: std.json.Value,
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

const GeomHandler = enum { multi_surface, solid };

const geom_types = std.StaticStringMap(GeomHandler).initComptime(.{
    .{ "MultiSurface", .multi_surface },
    .{ "Solid", .solid },
});

// C API opaque handle
pub const CityJSONHandle = *CityJSON;

pub const CityJSON = struct {
    allocator: std.mem.Allocator,
    // file: CityJSONFile,
    objects: std.StringArrayHashMap(PolygonalMesh),

    pub fn init(allocator: std.mem.Allocator) !CityJSON {
        return CityJSON{
            .allocator = allocator,
            // .file = undefined,
            .objects = .init(allocator),
        };
    }

    pub fn deinit(self: *CityJSON) void {
        for (self.objects.keys(), self.objects.values()) |key, *mesh| {
            mesh.deinit();
            self.allocator.free(key);
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
      const file = try std.fs.cwd().openFile(path, .{ .mode = .read_only });
      defer file.close();
      var read_buf: [2048]u8 = undefined;
      var f_reader: std.fs.File.Reader = file.reader(&read_buf);

      var j_reader = std.json.Reader.init(self.allocator, &f_reader.interface);
      defer j_reader.deinit();

      // Parse into the struct
      const parsed = try std.json.parseFromTokenSource(CityJSONFile, self.allocator, &j_reader, .{
          .ignore_unknown_fields = true,
      });
      defer parsed.deinit();

      const cj = parsed.value;
      std.debug.print("File version: {s}, type: {s}, Nr of vertices: {d}\n", .{
          cj.version, cj.type, cj.vertices.len
      });
      // print first 5 vertices
      for (cj.vertices[0..5]) |vertex| {
          std.debug.print("{d}, {d}, {d}\n",
            .{  @as(f64, @floatFromInt(vertex[0]))*cj.transform.scale[0] + cj.transform.translate[0],
                @as(f64, @floatFromInt(vertex[1]))*cj.transform.scale[1] + cj.transform.translate[1],
                @as(f64, @floatFromInt(vertex[2]))*cj.transform.scale[2] + cj.transform.translate[2]
            });
      }
      // print transform
      std.debug.print("Scale: {d}, {d}, {d}\n", .{ cj.transform.scale[0], cj.transform.scale[1], cj.transform.scale[2] });
      std.debug.print("Translate: {d}, {d}, {d}\n", .{ cj.transform.translate[0], cj.transform.translate[1], cj.transform.translate[2] });

      // Accessing the dynamic part:
      const city_objs = parsed.value.CityObjects.object; // It's a StringHashMap
      for (city_objs.keys(), city_objs.values()) |key, obj| {
          std.debug.print("Key: {s}\n", .{key});
          const geom = obj.object.get("geometry").?;
          // geom.dump();
          const geom_objs = geom.array;
          for (geom_objs.items) |geom_obj| {
              if (geom_obj.object.get("lod")) |lod_value| {
                  std.debug.print("LOD: {s}\n", .{lod_value.string});
              }

              var mesh = PolygonalMesh.init(self.allocator);

              const geomtype = geom_obj.object.get("type").?.string;
              if (geom_types.get(geomtype)) |handler| {
                  switch (handler) {
                      .multi_surface => {
                        std.debug.print("MultiSurface type\n", .{});
                        const parsed_ = std.json.parseFromValue(CJMultiSurfaceBounds, self.allocator, geom_obj.object.get("boundaries").?, .{}) catch |err| {
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
                                    const vertex_idx = try mesh.addVertex(cj.getTransformedVertex(vi));
                                    try ring_indices.append(self.allocator, vertex_idx);
                                }

                                // Add the face for this ring
                                try mesh.addFace(ring_indices.items, .wall);  // or appropriate FaceType
                            }
                        }
                      },
                      .solid => {
                        std.debug.print("Solid type\n", .{});
                        const parsed_ = std.json.parseFromValue(CJSolidBounds, self.allocator, geom_obj.object.get("boundaries").?, .{}) catch |err| {
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
                                        const vertex_idx = try mesh.addVertex(cj.getTransformedVertex(vi));
                                        try ring_indices.append(self.allocator, vertex_idx);
                                    }

                                    // Add the face for this ring
                                    try mesh.addFace(ring_indices.items, .wall);  // or appropriate FaceType
                                }
                            }
                        }
                      },
                  }
              } else {
                  std.debug.print("Unknown type\n", .{});
              }

              std.debug.print("Mesh has {d} faces\n", .{mesh.faces.items.len});
              std.debug.print("Mesh has {d} vertices\n", .{mesh.vertices.items.len/3});
              if (self.objects.getPtr(key)) |existing_mesh| {
                  existing_mesh.deinit();
              }
              const owned_key = try self.allocator.dupe(u8, key);
              try self.objects.put(owned_key, mesh);

          }
      }
    }

};

// =============================================================================
// C API exports
// =============================================================================

var c_allocator: std.mem.Allocator = std.heap.c_allocator;

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
    cj.load(path_slice) catch return -1;
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

/// Get the vertex count for an object by index.
export fn cityjson_get_vertex_count(handle: ?CityJSONHandle, index: usize) callconv(.c) usize {
    const cj = handle orelse return 0;
    const values = cj.objects.values();
    if (index >= values.len) return 0;
    return values[index].vertices.items.len / 3;
}

/// Get the face count for an object by index.
export fn cityjson_get_face_count(handle: ?CityJSONHandle, index: usize) callconv(.c) usize {
    const cj = handle orelse return 0;
    const values = cj.objects.values();
    if (index >= values.len) return 0;
    return values[index].faces.items.len;
}

/// Get pointer to vertex data (x, y, z triplets as f64) for an object by index.
export fn cityjson_get_vertices(handle: ?CityJSONHandle, index: usize) callconv(.c) [*c]const f64 {
    const cj = handle orelse return null;
    const values = cj.objects.values();
    if (index >= values.len) return null;
    return values[index].vertices.items.ptr;
}

/// Get pointer to index data for an object by index.
export fn cityjson_get_indices(handle: ?CityJSONHandle, index: usize) callconv(.c) [*c]const usize {
    const cj = handle orelse return null;
    const values = cj.objects.values();
    if (index >= values.len) return null;
    return values[index].indices.items.ptr;
}

/// Get the index count for an object by index.
export fn cityjson_get_index_count(handle: ?CityJSONHandle, index: usize) callconv(.c) usize {
    const cj = handle orelse return 0;
    const values = cj.objects.values();
    if (index >= values.len) return 0;
    return values[index].indices.items.len;
}

/// Get face info: start index and vertex count. Returns 0 on success, -1 on failure.
export fn cityjson_get_face_info(
    handle: ?CityJSONHandle,
    object_index: usize,
    face_index: usize,
    out_start: *usize,
    out_count: *usize,
    out_face_type: *u8,
) callconv(.c) c_int {
    const cj = handle orelse return -1;
    const values = cj.objects.values();
    if (object_index >= values.len) return -1;
    const mesh = values[object_index];
    if (face_index >= mesh.faces.items.len) return -1;
    const face = mesh.faces.items[face_index];
    out_start.* = face.start;
    out_count.* = face.count;
    out_face_type.* = @intFromEnum(face.face_type);
    return 0;
}
