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

const CJTransform = struct {
    scale: [3]f64,
    translate: [3]f64,

    pub fn apply(self: @This(), v: [3]i64) [3]f64 {
        return .{
            @as(f64, @floatFromInt(v[0])) * self.scale[0] + self.translate[0],
            @as(f64, @floatFromInt(v[1])) * self.scale[1] + self.translate[1],
            @as(f64, @floatFromInt(v[2])) * self.scale[2] + self.translate[2],
        };
    }
};

const CJFile = struct {
    version: []const u8,
    type: []const u8,
    vertices: []const [3]i64,
    CityObjects: std.json.ArrayHashMap(CJObject),
    transform: CJTransform,

    // Methods are fine - JSON parsing ignores them
    pub fn getTransformedVertex(self: @This(), idx: usize) [3]f64 {
        return self.transform.apply(self.vertices[idx]);
    }

    pub fn vertexCount(self: @This()) usize {
        return self.vertices.len;
    }
};

const CJFeature = struct {
    type: []const u8,
    id: []const u8,
    CityObjects: std.json.ArrayHashMap(CJObject),
    vertices: []const [3]i64,
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
    }

    /// Add a new CityObject. Returns the object index.
    pub fn addObject(self: *CityJSON, name: []const u8, object_type: CJObjectType) !usize {
        const owned_key = try self.allocator.dupeZ(u8, name);
        errdefer self.allocator.free(owned_key.ptr[0..owned_key.len + 1]);
        try self.objects.put(owned_key, try StoredCityObject.init(self.allocator, object_type, 0));
        return self.objects.count() - 1;
    }

    /// Add a geometry to an existing object. Returns the geometry index within that object.
    pub fn addGeometry(self: *CityJSON, object_index: usize, geometry_type: CJGeometryType, lod: []const u8) !usize {
        const values = self.objects.values();
        if (object_index >= values.len) return error.IndexOutOfBounds;
        const obj = &values[object_index];
        const old_len = obj.geometries.len;
        const new_geoms = try self.allocator.realloc(obj.geometries, old_len + 1);
        new_geoms[old_len] = try StoredGeometry.init(self.allocator, geometry_type, lod);
        obj.geometries = new_geoms;
        return old_len;
    }

    /// Get the PolygonalMesh for a given object and geometry, for adding vertices and faces.
    pub fn getMesh(self: *CityJSON, object_index: usize, geometry_index: usize) !*PolygonalMesh {
        const values = self.objects.values();
        if (object_index >= values.len) return error.IndexOutOfBounds;
        const geometries = values[object_index].geometries;
        if (geometry_index >= geometries.len) return error.IndexOutOfBounds;
        return &geometries[geometry_index].polygonal_mesh;
    }

    pub fn load(self: *CityJSON, path: []const u8) !void {
        if (std.mem.endsWith(u8, path, ".jsonl")) {
            try self.loadCityJSONSeq(path);
            return;
        }
        try self.loadCityJSON(path);
    }

    fn loadCityJSON(self: *CityJSON, path: []const u8) !void {
        const file = if (std.fs.path.isAbsolute(path))
            try std.fs.openFileAbsolute(path, .{ .mode = .read_only })
        else
            try std.fs.cwd().openFile(path, .{ .mode = .read_only });
        defer file.close();

        var read_buf: [64 * 1024]u8 = undefined;
        var f_reader: std.fs.File.Reader = file.reader(&read_buf);
        var j_reader = std.json.Reader.init(self.allocator, &f_reader.interface);
        defer j_reader.deinit();

        const parsed = try std.json.parseFromTokenSource(CJFile, self.allocator, &j_reader, .{
            .ignore_unknown_fields = true,
        });
        defer parsed.deinit();

        try self.ingestCityObjects(parsed.value.CityObjects, parsed.value.vertices, parsed.value.transform);
    }

    fn loadCityJSONSeq(self: *CityJSON, path: []const u8) !void {
        const file = if (std.fs.path.isAbsolute(path))
            try std.fs.openFileAbsolute(path, .{ .mode = .read_only })
        else
            try std.fs.cwd().openFile(path, .{ .mode = .read_only });
        defer file.close();

        var did_read_header = false;
        var seq_transform: CJTransform = undefined;

        var pending_line: std.ArrayList(u8) = .{};
        defer pending_line.deinit(self.allocator);

        var read_chunk: [8192]u8 = undefined;
        while (true) {
            const bytes_read = try file.read(&read_chunk);
            if (bytes_read == 0) break;

            var start: usize = 0;
            while (start < bytes_read) {
                if (std.mem.indexOfScalar(u8, read_chunk[start..bytes_read], '\n')) |relative_end| {
                    const end = start + relative_end;
                    try pending_line.appendSlice(self.allocator, read_chunk[start..end]);
                    try self.ingestCityJSONSeqLine(pending_line.items, &did_read_header, &seq_transform);
                    pending_line.clearRetainingCapacity();
                    start = end + 1;
                } else {
                    try pending_line.appendSlice(self.allocator, read_chunk[start..bytes_read]);
                    break;
                }
            }
        }

        if (pending_line.items.len > 0) {
            try self.ingestCityJSONSeqLine(pending_line.items, &did_read_header, &seq_transform);
        }

        if (!did_read_header) return error.InvalidCityJSONSeqHeader;
    }

    fn ingestCityJSONSeqLine(
        self: *CityJSON,
        raw_line: []const u8,
        did_read_header: *bool,
        seq_transform: *CJTransform,
    ) !void {
        // Normalize line endings and ignore surrounding whitespace so CRLF files
        // and padded lines still parse as valid JSON lines.
        var line = std.mem.trim(u8, raw_line, " \t\r");
        // CityJSONSeq readers should tolerate empty lines between entries.
        if (line.len == 0) return;

        // Some producers write a UTF-8 BOM at the start of the file. Strip it
        // from the first meaningful line (the CityJSON header) before parsing.
        if (!did_read_header.* and std.mem.startsWith(u8, line, "\xEF\xBB\xBF")) {
            line = line[3..];
        }

        if (!did_read_header.*) {
            const parsed_header = try std.json.parseFromSlice(CJFile, self.allocator, line, .{
                .ignore_unknown_fields = true,
            });
            defer parsed_header.deinit();

            if (!std.mem.eql(u8, parsed_header.value.type, "CityJSON")) {
                return error.InvalidCityJSONSeqHeader;
            }

            seq_transform.* = parsed_header.value.transform;
            did_read_header.* = true;
            return;
        }

        const parsed_feature = try std.json.parseFromSlice(CJFeature, self.allocator, line, .{
            .ignore_unknown_fields = true,
        });
        defer parsed_feature.deinit();

        if (!std.mem.eql(u8, parsed_feature.value.type, "CityJSONFeature")) {
            return error.InvalidCityJSONSeqFeature;
        }
        if (parsed_feature.value.id.len == 0) {
            return error.InvalidCityJSONSeqFeature;
        }
        if (!cityObjectsContainsKey(parsed_feature.value.CityObjects, parsed_feature.value.id)) {
            return error.InvalidCityJSONSeqFeatureParent;
        }

        try self.ingestCityObjects(parsed_feature.value.CityObjects, parsed_feature.value.vertices, seq_transform.*);
    }

    fn cityObjectsContainsKey(city_objs: std.json.ArrayHashMap(CJObject), key: []const u8) bool {
        for (city_objs.map.keys()) |obj_key| {
            if (std.mem.eql(u8, obj_key, key)) return true;
        }
        return false;
    }

    fn ingestCityObjects(
        self: *CityJSON,
        city_objs: std.json.ArrayHashMap(CJObject),
        vertices: []const [3]i64,
        transform: CJTransform,
    ) !void {
        for (city_objs.map.keys(), city_objs.map.values()) |key, obj| {
            const owned_key = try self.allocator.dupeZ(u8, key);
            errdefer self.allocator.free(owned_key.ptr[0..owned_key.len + 1]);

            var entry = try self.objects.getOrPut(owned_key);
            if (entry.found_existing) {
                // Existing entry keeps ownership of its original key allocation.
                self.allocator.free(owned_key.ptr[0..owned_key.len + 1]);
            }

            const new_object = try StoredCityObject.init(self.allocator, obj.type, obj.geometry.len);
            if (entry.found_existing) {
                entry.value_ptr.deinit(self.allocator);
            }
            entry.value_ptr.* = new_object;
            const stored_city_object = entry.value_ptr;

            for (obj.geometry, 0..) |g, i| {
                const geom = &stored_city_object.geometries[i];
                geom.* = try StoredGeometry.init(self.allocator, g.type, g.lod);
                try self.ingestGeometry(&geom.polygonal_mesh, g, vertices, transform);
            }
        }
    }

    fn ingestGeometry(
        self: *CityJSON,
        mesh: *PolygonalMesh,
        g: CJGeometry,
        vertices: []const [3]i64,
        transform: CJTransform,
    ) !void {
        var vertex_remap = std.AutoArrayHashMap(usize, usize).init(self.allocator);
        defer vertex_remap.deinit();
        var ring_indices: std.ArrayList(usize) = .{};
        defer ring_indices.deinit(self.allocator);

        switch (g.type) {
            .MultiSurface => {
                const parsed_ = try std.json.parseFromValue(CJMultiSurfaceBounds, self.allocator, g.boundaries, .{});
                defer parsed_.deinit();
                const bounds = parsed_.value;

                for (bounds) |polygon| {
                    for (polygon) |ring| {
                        for (ring) |vi| {
                            if (vi >= vertices.len) return error.InvalidVertexIndex;
                            const result = try vertex_remap.getOrPut(vi);
                            if (!result.found_existing) {
                                result.value_ptr.* = try mesh.addVertex(transform.apply(vertices[vi]));
                            }
                        }
                    }
                }

                for (bounds) |polygon| {
                    for (polygon) |ring| {
                        ring_indices.clearRetainingCapacity();
                        try ring_indices.ensureTotalCapacity(self.allocator, ring.len);
                        for (ring) |vi| {
                            ring_indices.appendAssumeCapacity(vertex_remap.get(vi).?);
                        }
                        try mesh.addFace(ring_indices.items, .wall);
                    }
                }
            },
            .Solid => {
                const parsed_ = try std.json.parseFromValue(CJSolidBounds, self.allocator, g.boundaries, .{});
                defer parsed_.deinit();
                const bounds = parsed_.value;

                // First pass: collect unique vertices
                for (bounds) |shell| {
                    for (shell) |polygon| {
                        for (polygon) |ring| {
                            for (ring) |vi| {
                                if (vi >= vertices.len) return error.InvalidVertexIndex;
                                const result = try vertex_remap.getOrPut(vi);
                                if (!result.found_existing) {
                                    result.value_ptr.* = try mesh.addVertex(transform.apply(vertices[vi]));
                                }
                            }
                        }
                    }
                }

                // Second pass: add faces with remapped indices
                for (bounds) |shell| {
                    for (shell) |polygon| {
                        for (polygon) |ring| {
                            ring_indices.clearRetainingCapacity();
                            try ring_indices.ensureTotalCapacity(self.allocator, ring.len);
                            for (ring) |vi| {
                                ring_indices.appendAssumeCapacity(vertex_remap.get(vi).?);
                            }
                            try mesh.addFace(ring_indices.items, .wall);
                        }
                    }
                }
            },
        }
    }

    pub fn save(self: *const CityJSON, path: []const u8) !void {
        const scale = [3]f64{ 0.001, 0.001, 0.001 };

        // Compute translate from bounding box minimum of all vertices
        var min = [3]f64{ std.math.floatMax(f64), std.math.floatMax(f64), std.math.floatMax(f64) };
        for (self.objects.values()) |object| {
            for (object.geometries) |geom| {
                const mesh = &geom.polygonal_mesh;
                const vert_count = mesh.vertices.items.len / 3;
                for (0..vert_count) |vi| {
                    const v = mesh.getVertex(vi);
                    for (0..3) |c| {
                        if (v[c] < min[c]) min[c] = v[c];
                    }
                }
            }
        }
        // If no vertices, use zero translate
        const translate = if (min[0] == std.math.floatMax(f64))
            [3]f64{ 0.0, 0.0, 0.0 }
        else
            min;

        // Build per-geometry global offsets (simple concatenation)
        // We need to know each geometry's offset into the global vertex array
        // Store as a flat list parallel to objects × geometries
        var global_vertex_count: usize = 0;
        var geom_offsets: std.ArrayList(usize) = .{};
        defer geom_offsets.deinit(self.allocator);
        for (self.objects.values()) |object| {
            for (object.geometries) |geom| {
                try geom_offsets.append(self.allocator, global_vertex_count);
                global_vertex_count += geom.polygonal_mesh.vertices.items.len / 3;
            }
        }

        // Open file for writing
        const file = if (std.fs.path.isAbsolute(path))
            try std.fs.createFileAbsolute(path, .{ .truncate = true })
        else
            try std.fs.cwd().createFile(path, .{ .truncate = true });
        defer file.close();
        var write_buf: [4096]u8 = undefined;
        var f_writer = file.writer(&write_buf);
        var jw: std.json.Stringify = .{ .writer = &f_writer.interface, .options = .{ .whitespace = .indent_2 } };

        // Root object
        try jw.beginObject();

        // "type"
        try jw.objectField("type");
        try jw.write("CityJSON");

        // "version"
        try jw.objectField("version");
        try jw.write("2.0");

        // "transform"
        try jw.objectField("transform");
        try jw.beginObject();
        try jw.objectField("scale");
        try jw.beginArray();
        for (scale) |s| try jw.write(s);
        try jw.endArray();
        try jw.objectField("translate");
        try jw.beginArray();
        for (translate) |t| try jw.write(t);
        try jw.endArray();
        try jw.endObject();

        // "CityObjects"
        try jw.objectField("CityObjects");
        try jw.beginObject();

        var geom_idx: usize = 0;
        for (self.objects.keys(), self.objects.values()) |key, object| {
            try jw.objectField(key);
            try jw.beginObject();

            try jw.objectField("type");
            try jw.print("\"{s}\"", .{@tagName(object.type)});

            try jw.objectField("geometry");
            try jw.beginArray();

            for (object.geometries) |geom| {
                const offset = geom_offsets.items[geom_idx];
                geom_idx += 1;

                try jw.beginObject();

                try jw.objectField("type");
                try jw.print("\"{s}\"", .{@tagName(geom.type)});

                try jw.objectField("lod");
                try jw.write(geom.lod);

                try jw.objectField("boundaries");
                try self.writeBoundaries(&jw, &geom, offset);

                try jw.endObject();
            }

            try jw.endArray();
            try jw.endObject();
        }

        try jw.endObject(); // end CityObjects

        // "vertices"
        try jw.objectField("vertices");
        try jw.beginArray();
        for (self.objects.values()) |object| {
            for (object.geometries) |geom| {
                const mesh = &geom.polygonal_mesh;
                const vert_count = mesh.vertices.items.len / 3;
                for (0..vert_count) |vi| {
                    const v = mesh.getVertex(vi);
                    try jw.beginArray();
                    for (0..3) |c| {
                        const int_val: i64 = @intFromFloat(@round((v[c] - translate[c]) / scale[c]));
                        try jw.write(int_val);
                    }
                    try jw.endArray();
                }
            }
        }
        try jw.endArray();

        try jw.endObject(); // end root

        // Flush the buffered writer
        try f_writer.interface.flush();
    }

    fn writeBoundaries(self: *const CityJSON, jw: *std.json.Stringify, geom: *const StoredGeometry, global_offset: usize) !void {
        _ = self;
        const mesh = &geom.polygonal_mesh;

        switch (geom.type) {
            .MultiSurface => {
                // boundaries: [ [[idx, ...]], [[idx, ...]], ... ]
                try jw.beginArray();
                for (mesh.faces.items) |face| {
                    const indices = mesh.getFaceIndices(face);
                    // One polygon with one ring
                    try jw.beginArray();
                    try jw.beginArray();
                    for (indices) |idx| {
                        try jw.write(idx + global_offset);
                    }
                    try jw.endArray();
                    try jw.endArray();
                }
                try jw.endArray();
            },
            .Solid => {
                // boundaries: [ [ [[idx, ...]], [[idx, ...]], ... ] ]
                // Single shell containing all faces
                try jw.beginArray();
                try jw.beginArray(); // shell
                for (mesh.faces.items) |face| {
                    const indices = mesh.getFaceIndices(face);
                    try jw.beginArray();
                    try jw.beginArray();
                    for (indices) |idx| {
                        try jw.write(idx + global_offset);
                    }
                    try jw.endArray();
                    try jw.endArray();
                }
                try jw.endArray(); // end shell
                try jw.endArray();
            },
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

/// Save a CityJSON file. Returns 0 on success, non-zero on failure.
export fn cityjson_save(handle: ?CityJSONHandle, path: [*c]const u8) callconv(.c) c_int {
    const cj = handle orelse return -1;
    const path_slice = std.mem.span(path);
    cj.save(path_slice) catch |err| {
        std.debug.print("Error saving CityJSON: {}\n", .{err});
        return -1;
    };
    return 0;
}

// =============================================================================
// Builder API
// =============================================================================

/// Add a new CityObject. Returns the object index, or -1 on failure.
/// object_type: CITYJSON_BUILDING or CITYJSON_BUILDING_PART.
export fn cityjson_add_object(handle: ?CityJSONHandle, name: [*c]const u8, object_type: u8) callconv(.c) isize {
    const cj = handle orelse return -1;
    const name_slice = std.mem.span(name);
    const obj_type = std.meta.intToEnum(CJObjectType, object_type) catch return -1;
    const idx = cj.addObject(name_slice, obj_type) catch return -1;
    return @intCast(idx);
}

/// Add a geometry to an object. Returns the geometry index within that object, or -1 on failure.
/// geometry_type: CITYJSON_MULTISURFACE or CITYJSON_SOLID.
export fn cityjson_add_geometry(handle: ?CityJSONHandle, object_index: usize, geometry_type: u8, lod: [*c]const u8) callconv(.c) isize {
    const cj = handle orelse return -1;
    const geom_type = std.meta.intToEnum(CJGeometryType, geometry_type) catch return -1;
    const lod_slice = std.mem.span(lod);
    const idx = cj.addGeometry(object_index, geom_type, lod_slice) catch return -1;
    return @intCast(idx);
}

/// Add a vertex to a geometry's mesh. Returns the vertex index, or -1 on failure.
export fn cityjson_add_vertex(handle: ?CityJSONHandle, object_index: usize, geometry_index: usize, x: f64, y: f64, z: f64) callconv(.c) isize {
    const cj = handle orelse return -1;
    const mesh = cj.getMesh(object_index, geometry_index) catch return -1;
    const idx = mesh.addVertex(.{ x, y, z }) catch return -1;
    return @intCast(idx);
}

/// Add a face to a geometry's mesh. Returns 0 on success, -1 on failure.
/// vertex_indices: pointer to an array of vertex indices.
/// num_indices: number of vertex indices in the face.
/// face_type: one of ZITYJSON_FACE_WALL, etc.
export fn cityjson_add_face(handle: ?CityJSONHandle, object_index: usize, geometry_index: usize, vertex_indices: [*c]const usize, num_indices: usize, face_type: u8) callconv(.c) c_int {
    const cj = handle orelse return -1;
    const mesh = cj.getMesh(object_index, geometry_index) catch return -1;
    const ft = std.meta.intToEnum(FaceType, face_type) catch return -1;
    const indices_slice = vertex_indices[0..num_indices];
    mesh.addFace(indices_slice, ft) catch return -1;
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

test "save round-trip" {
    const allocator = std.testing.allocator;

    // Build a CityJSON in memory with one Building containing a triangle
    var cj = try CityJSON.init(allocator);
    defer cj.deinit();

    var obj = try CityJSON.StoredCityObject.init(allocator, .Building, 1);
    obj.geometries[0] = try CityJSON.StoredGeometry.init(allocator, .MultiSurface, "1.2");

    const mesh = &obj.geometries[0].polygonal_mesh;
    _ = try mesh.addVertex(.{ 100.0, 200.0, 0.0 });
    _ = try mesh.addVertex(.{ 110.0, 200.0, 0.0 });
    _ = try mesh.addVertex(.{ 105.0, 210.0, 5.0 });
    try mesh.addFace(&.{ 0, 1, 2 }, .wall);

    const key = try allocator.dupeZ(u8, "TestBuilding");
    try cj.objects.put(key, obj);

    // Save to a temp file
    const tmp_path = "/tmp/zityjson_test_output.city.json";
    try cj.save(tmp_path);

    // Load the saved file back
    var cj2 = try CityJSON.init(allocator);
    defer cj2.deinit();
    try cj2.load(tmp_path);

    // Verify: same number of objects
    try std.testing.expectEqual(cj.objects.count(), cj2.objects.count());

    // Verify: same object key exists
    try std.testing.expect(cj2.objects.contains("TestBuilding"));

    const obj2 = cj2.objects.get("TestBuilding").?;
    try std.testing.expectEqual(@as(usize, 1), obj2.geometries.len);
    try std.testing.expectEqual(CJGeometryType.MultiSurface, obj2.geometries[0].type);
    try std.testing.expectEqualStrings("1.2", obj2.geometries[0].lod);

    const mesh2 = &obj2.geometries[0].polygonal_mesh;
    try std.testing.expectEqual(@as(usize, 3), mesh2.vertices.items.len / 3);
    try std.testing.expectEqual(@as(usize, 1), mesh2.faces.items.len);

    // Verify vertex positions within tolerance (0.001 = scale)
    const tolerance = 0.002;
    for (0..3) |vi| {
        const v1 = mesh.getVertex(vi);
        const v2 = mesh2.getVertex(vi);
        for (0..3) |c| {
            try std.testing.expect(@abs(v1[c] - v2[c]) < tolerance);
        }
    }
}

test "builder API round-trip" {
    const allocator = std.testing.allocator;

    var cj = try CityJSON.init(allocator);
    defer cj.deinit();

    // Use builder API to construct a building with two geometries
    const obj_idx = try cj.addObject("MyBuilding", .Building);
    try std.testing.expectEqual(@as(usize, 0), obj_idx);

    const geom_idx = try cj.addGeometry(obj_idx, .MultiSurface, "2.2");
    try std.testing.expectEqual(@as(usize, 0), geom_idx);

    const mesh = try cj.getMesh(obj_idx, geom_idx);
    const v0 = try mesh.addVertex(.{ 0.0, 0.0, 0.0 });
    const v1 = try mesh.addVertex(.{ 10.0, 0.0, 0.0 });
    const v2 = try mesh.addVertex(.{ 10.0, 10.0, 0.0 });
    const v3 = try mesh.addVertex(.{ 0.0, 10.0, 0.0 });
    try mesh.addFace(&.{ v0, v1, v2, v3 }, .floor);

    const v4 = try mesh.addVertex(.{ 0.0, 0.0, 5.0 });
    const v5 = try mesh.addVertex(.{ 10.0, 0.0, 5.0 });
    const v6 = try mesh.addVertex(.{ 10.0, 10.0, 5.0 });
    const v7 = try mesh.addVertex(.{ 0.0, 10.0, 5.0 });
    try mesh.addFace(&.{ v4, v5, v6, v7 }, .roof);

    // Add a second geometry to the same object
    const geom_idx2 = try cj.addGeometry(obj_idx, .Solid, "1.0");
    try std.testing.expectEqual(@as(usize, 1), geom_idx2);

    const mesh2 = try cj.getMesh(obj_idx, geom_idx2);
    _ = try mesh2.addVertex(.{ 0.0, 0.0, 0.0 });
    _ = try mesh2.addVertex(.{ 5.0, 0.0, 0.0 });
    _ = try mesh2.addVertex(.{ 5.0, 5.0, 0.0 });
    try mesh2.addFace(&.{ 0, 1, 2 }, .wall);

    // Add a second object
    const obj_idx2 = try cj.addObject("MyBuildingPart", .BuildingPart);
    try std.testing.expectEqual(@as(usize, 1), obj_idx2);

    // Verify counts
    try std.testing.expectEqual(@as(usize, 2), cj.objects.count());
    try std.testing.expectEqual(@as(usize, 2), cj.objects.values()[0].geometries.len);
    try std.testing.expectEqual(@as(usize, 0), cj.objects.values()[1].geometries.len);

    // Save and reload
    const tmp_path = "/tmp/zityjson_builder_test.city.json";
    try cj.save(tmp_path);

    var cj2 = try CityJSON.init(allocator);
    defer cj2.deinit();
    try cj2.load(tmp_path);

    try std.testing.expectEqual(@as(usize, 2), cj2.objects.count());
    try std.testing.expect(cj2.objects.contains("MyBuilding"));
    try std.testing.expect(cj2.objects.contains("MyBuildingPart"));

    const loaded_obj = cj2.objects.get("MyBuilding").?;
    try std.testing.expectEqual(@as(usize, 2), loaded_obj.geometries.len);
    try std.testing.expectEqual(CJGeometryType.MultiSurface, loaded_obj.geometries[0].type);
    try std.testing.expectEqualStrings("2.2", loaded_obj.geometries[0].lod);
    try std.testing.expectEqual(@as(usize, 2), loaded_obj.geometries[0].polygonal_mesh.faces.items.len);
    try std.testing.expectEqual(@as(usize, 8), loaded_obj.geometries[0].polygonal_mesh.vertices.items.len / 3);

    try std.testing.expectEqual(CJGeometryType.Solid, loaded_obj.geometries[1].type);
    try std.testing.expectEqualStrings("1.0", loaded_obj.geometries[1].lod);
    try std.testing.expectEqual(@as(usize, 1), loaded_obj.geometries[1].polygonal_mesh.faces.items.len);
}

test "load cityjson sequence" {
    const allocator = std.testing.allocator;

    const seq_content =
        \\{"type":"CityJSON","version":"2.0","transform":{"scale":[0.001,0.001,0.001],"translate":[10.0,20.0,30.0]},"CityObjects":{},"vertices":[]}
        \\{"type":"CityJSONFeature","id":"SeqBuilding","CityObjects":{"SeqBuilding":{"type":"Building","geometry":[{"type":"MultiSurface","lod":"1.0","boundaries":[[[0,1,2]]]}]}},"vertices":[[0,0,0],[1000,0,0],[0,1000,0]]}
        \\
    ;

    const tmp_path = "/tmp/zityjson_seq_test.city.jsonl";
    const file = try std.fs.createFileAbsolute(tmp_path, .{ .truncate = true });
    defer file.close();
    try file.writeAll(seq_content);

    var cj = try CityJSON.init(allocator);
    defer cj.deinit();
    try cj.load(tmp_path);

    try std.testing.expectEqual(@as(usize, 1), cj.objects.count());
    try std.testing.expect(cj.objects.contains("SeqBuilding"));

    const obj = cj.objects.get("SeqBuilding").?;
    try std.testing.expectEqual(@as(usize, 1), obj.geometries.len);
    try std.testing.expectEqual(CJGeometryType.MultiSurface, obj.geometries[0].type);
    try std.testing.expectEqualStrings("1.0", obj.geometries[0].lod);

    const mesh = &obj.geometries[0].polygonal_mesh;
    try std.testing.expectEqual(@as(usize, 3), mesh.vertices.items.len / 3);
    try std.testing.expectEqual(@as(usize, 1), mesh.faces.items.len);

    const v0 = mesh.getVertex(0);
    const v1 = mesh.getVertex(1);
    const v2 = mesh.getVertex(2);
    try std.testing.expect(@abs(v0[0] - 10.0) < 0.000001);
    try std.testing.expect(@abs(v0[1] - 20.0) < 0.000001);
    try std.testing.expect(@abs(v0[2] - 30.0) < 0.000001);
    try std.testing.expect(@abs(v1[0] - 11.0) < 0.000001);
    try std.testing.expect(@abs(v2[1] - 21.0) < 0.000001);
}
