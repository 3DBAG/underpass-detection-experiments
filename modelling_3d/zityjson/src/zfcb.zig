const std = @import("std");
const builtin = @import("builtin");

pub const MAGIC_BYTES = [_]u8{ 'f', 'c', 'b', 1, 'f', 'c', 'b', 0 };
pub const HEADER_MAX_BUFFER_SIZE: usize = 512 * 1024 * 1024; // 512MB

const VT_HEADER_TRANSFORM: u16 = 4;
const VT_HEADER_COLUMNS: u16 = 8;
const VT_HEADER_FEATURES_COUNT: u16 = 12;
const VT_HEADER_INDEX_NODE_SIZE: u16 = 14;
const VT_HEADER_ATTRIBUTE_INDEX: u16 = 16;

const VT_COLUMN_INDEX: u16 = 4;
const VT_COLUMN_NAME: u16 = 6;
const VT_COLUMN_TYPE: u16 = 8;

const VT_FEATURE_ID: u16 = 4;
const VT_FEATURE_OBJECTS: u16 = 6;
const VT_FEATURE_VERTICES: u16 = 8;

const VT_OBJECT_TYPE: u16 = 4;
const VT_OBJECT_EXTENSION_TYPE: u16 = 6;
const VT_OBJECT_ID: u16 = 8;
const VT_OBJECT_GEOGRAPHICAL_EXTENT: u16 = 10;
const VT_OBJECT_GEOMETRY: u16 = 12;
const VT_OBJECT_GEOMETRY_INSTANCES: u16 = 14;
const VT_OBJECT_ATTRIBUTES: u16 = 16;
const VT_OBJECT_COLUMNS: u16 = 18;
const VT_OBJECT_CHILDREN: u16 = 20;
const VT_OBJECT_CHILDREN_ROLES: u16 = 22;
const VT_OBJECT_PARENTS: u16 = 24;

const VT_GEOMETRY_TYPE: u16 = 4;
const VT_GEOMETRY_LOD: u16 = 6;
const VT_GEOMETRY_SOLIDS: u16 = 8;
const VT_GEOMETRY_SHELLS: u16 = 10;
const VT_GEOMETRY_SURFACES: u16 = 12;
const VT_GEOMETRY_STRINGS: u16 = 14;
const VT_GEOMETRY_BOUNDARIES: u16 = 16;
const VT_GEOMETRY_SEMANTICS: u16 = 18;
const VT_GEOMETRY_SEMANTICS_OBJECTS: u16 = 20;
const VT_SEMANTIC_OBJECT_TYPE: u16 = 4;

const NODE_ITEM_SIZE_BYTES: u64 = 40;

const EMPTY_COLUMNS: []const ColumnSchema = &[_]ColumnSchema{};
const EMPTY_OBJECTS: []const ObjectView = &[_]ObjectView{};
const EMPTY_VERTICES: []const [3]f64 = &[_][3]f64{};
const EMPTY_U32: []const u32 = &[_]u32{};
const EMPTY_U8: []const u8 = &[_]u8{};
const EMPTY_STRINGS: []const []const u8 = &[_][]const u8{};
const EMPTY_U32_MUT: []u32 = @constCast(&[_]u32{});

pub const Transform = struct {
    scale: [3]f64 = .{ 1.0, 1.0, 1.0 },
    translate: [3]f64 = .{ 0.0, 0.0, 0.0 },

    pub fn apply(self: Transform, v: [3]i32) [3]f64 {
        return .{
            @as(f64, @floatFromInt(v[0])) * self.scale[0] + self.translate[0],
            @as(f64, @floatFromInt(v[1])) * self.scale[1] + self.translate[1],
            @as(f64, @floatFromInt(v[2])) * self.scale[2] + self.translate[2],
        };
    }
};

pub const ColumnType = enum(u8) {
    Byte = 0,
    UByte = 1,
    Bool = 2,
    Short = 3,
    UShort = 4,
    Int = 5,
    UInt = 6,
    Long = 7,
    ULong = 8,
    Float = 9,
    Double = 10,
    String = 11,
    Json = 12,
    DateTime = 13,
    Binary = 14,
    _,
};

pub const ColumnSchema = struct {
    index: u16,
    name: []const u8,
    column_type: ColumnType,
};

pub const AttributeValue = union(enum) {
    byte: i8,
    ubyte: u8,
    bool: bool,
    short: i16,
    ushort: u16,
    int: i32,
    uint: u32,
    long: i64,
    ulong: u64,
    float: f32,
    double: f64,
    string: []const u8,
    json: []const u8,
    datetime: []const u8,
    binary: []const u8,
};

pub const Attribute = struct {
    name: []const u8,
    value: AttributeValue,
};

pub const GeometryType = enum(u8) {
    MultiPoint = 0,
    MultiLineString = 1,
    MultiSurface = 2,
    CompositeSurface = 3,
    Solid = 4,
    MultiSolid = 5,
    CompositeSolid = 6,
    GeometryInstance = 7,
    _,
};

pub const ObjectType = enum(u8) {
    Bridge = 0,
    BridgePart = 1,
    BridgeInstallation = 2,
    BridgeConstructiveElement = 3,
    BridgeRoom = 4,
    BridgeFurniture = 5,
    Building = 6,
    BuildingPart = 7,
    BuildingInstallation = 8,
    BuildingConstructiveElement = 9,
    BuildingFurniture = 10,
    BuildingStorey = 11,
    BuildingRoom = 12,
    BuildingUnit = 13,
    CityFurniture = 14,
    CityObjectGroup = 15,
    GenericCityObject = 16,
    LandUse = 17,
    OtherConstruction = 18,
    PlantCover = 19,
    SolitaryVegetationObject = 20,
    TINRelief = 21,
    Road = 22,
    Railway = 23,
    Waterway = 24,
    TransportSquare = 25,
    Tunnel = 26,
    TunnelPart = 27,
    TunnelInstallation = 28,
    TunnelConstructiveElement = 29,
    TunnelHollowSpace = 30,
    TunnelFurniture = 31,
    WaterBody = 32,
    ExtensionObject = 33,
    _,
};

pub const GeometryView = struct {
    geometry_type: GeometryType,
    lod: ?[]const u8,
    solids: []const u32,
    shells: []const u32,
    surfaces: []const u32,
    strings: []const u32,
    boundaries: []const u32,
    semantics: []const u32,
    semantics_objects: []const u8,

    pub fn ringCount(self: GeometryView) usize {
        return self.strings.len;
    }

    pub fn ringIndices(self: GeometryView, ring_index: usize) ?[]const u32 {
        if (ring_index >= self.strings.len) return null;
        var start: usize = 0;
        for (self.strings[0..ring_index]) |len| {
            start += len;
        }
        const ring_len = self.strings[ring_index];
        if (start + ring_len > self.boundaries.len) return null;
        return self.boundaries[start..][0..ring_len];
    }
};

pub const ObjectView = struct {
    id: []const u8,
    object_type: ObjectType,
    extension_type: ?[]const u8,
    geometries: []const GeometryView,
    attributes: []const Attribute,
};

pub const FeatureView = struct {
    id: []const u8,
    vertices: []const [3]f64,
    objects: []const ObjectView,
};

pub const Reader = struct {
    allocator: std.mem.Allocator,
    file: std.fs.File,
    owns_file: bool = true,

    transform: Transform = .{},
    feature_count: u64 = 0,

    header_buf: []u8 = &[_]u8{},
    owns_header_buf: bool = false,
    preamble_buf: []u8 = &[_]u8{},
    owns_preamble_buf: bool = false,
    root_columns: []const ColumnSchema = EMPTY_COLUMNS,
    owns_root_columns: bool = false,

    feature_buf: std.ArrayList(u8) = .{},
    scratch_vertices: std.ArrayList([3]f64) = .{},
    scratch_objects: std.ArrayList(ObjectView) = .{},
    scratch_geometries: std.ArrayList(GeometryView) = .{},
    scratch_attributes: std.ArrayList(Attribute) = .{},
    scratch_columns: std.ArrayList(ColumnSchema) = .{},
    scratch_column_types: std.ArrayList(ColumnTypeByIndex) = .{},
    scratch_u32: std.ArrayList(u32) = .{},
    scratch_u8: std.ArrayList(u8) = .{},

    pending_loaded: bool = false,
    pending_id_owned: ?[]u8 = null,
    reached_eof: bool = false,

    current_feature: FeatureView = .{
        .id = "",
        .vertices = EMPTY_VERTICES,
        .objects = EMPTY_OBJECTS,
    },

    pub fn openPath(allocator: std.mem.Allocator, path: []const u8) !Reader {
        const file = if (std.fs.path.isAbsolute(path))
            try std.fs.openFileAbsolute(path, .{ .mode = .read_only })
        else
            try std.fs.cwd().openFile(path, .{ .mode = .read_only });

        return openFile(allocator, file, true);
    }

    pub fn openFile(allocator: std.mem.Allocator, file: std.fs.File, owns_file: bool) !Reader {
        var reader = Reader{
            .allocator = allocator,
            .file = file,
            .owns_file = owns_file,
        };
        errdefer reader.deinit();
        try reader.readHeader();
        return reader;
    }

    pub fn deinit(self: *Reader) void {
        if (self.owns_file) {
            self.file.close();
        }

        self.feature_buf.deinit(self.allocator);
        self.scratch_vertices.deinit(self.allocator);
        self.scratch_objects.deinit(self.allocator);
        self.scratch_geometries.deinit(self.allocator);
        self.scratch_attributes.deinit(self.allocator);
        self.scratch_columns.deinit(self.allocator);
        self.scratch_column_types.deinit(self.allocator);
        self.scratch_u32.deinit(self.allocator);
        self.scratch_u8.deinit(self.allocator);

        if (self.pending_id_owned) |id| self.allocator.free(id);
        if (self.owns_root_columns) self.allocator.free(self.root_columns);
        if (self.owns_preamble_buf) self.allocator.free(self.preamble_buf);
        if (self.owns_header_buf) self.allocator.free(self.header_buf);
    }

    pub fn featureCount(self: *const Reader) u64 {
        return self.feature_count;
    }

    pub fn headerTransform(self: *const Reader) Transform {
        return self.transform;
    }

    pub fn rootColumns(self: *const Reader) []const ColumnSchema {
        return self.root_columns;
    }

    pub fn preamble(self: *const Reader) []const u8 {
        return self.preamble_buf;
    }

    pub fn headerSize(self: *const Reader) usize {
        // header_buf includes a 4-byte size prefix; the rest is the flatbuffer data.
        return self.header_buf.len - 4;
    }

    pub fn peekNextId(self: *Reader) !?[]const u8 {
        if (!try self.ensurePending()) return null;
        return self.pending_id_owned;
    }

    pub fn skipNext(self: *Reader) !bool {
        if (!try self.ensurePending()) return false;
        self.pending_loaded = false;
        return true;
    }

    pub fn next(self: *Reader) !?*const FeatureView {
        if (!try self.ensurePending()) return null;
        try self.decodePendingFeature();
        self.pending_loaded = false;
        return &self.current_feature;
    }

    fn readHeader(self: *Reader) !void {
        var magic: [8]u8 = undefined;
        try readExact(&self.file, &magic);
        if (!std.mem.eql(u8, &magic, &MAGIC_BYTES)) return error.MissingMagicBytes;

        var header_size_buf: [4]u8 = undefined;
        try readExact(&self.file, &header_size_buf);
        const header_size: usize = @intCast(std.mem.readInt(u32, &header_size_buf, .little));
        if (header_size < 8 or header_size > HEADER_MAX_BUFFER_SIZE) return error.IllegalHeaderSize;

        self.header_buf = try self.allocator.alloc(u8, header_size + 4);
        self.owns_header_buf = true;
        @memcpy(self.header_buf[0..4], &header_size_buf);
        try readExact(&self.file, self.header_buf[4..]);

        const header_table = try fb.sizePrefixedRootTable(self.header_buf);
        self.transform = try readHeaderTransform(self.header_buf, header_table);
        self.feature_count = try fb.getScalarU64Default(self.header_buf, header_table, VT_HEADER_FEATURES_COUNT, 0);
        const index_node_size = try fb.getScalarU16Default(self.header_buf, header_table, VT_HEADER_INDEX_NODE_SIZE, 16);

        try self.loadRootColumns(header_table);

        const attr_index_size = try self.readAttributeIndexSize(header_table);
        const rtree_index_size = if (index_node_size > 0 and self.feature_count > 0)
            try packedRtreeIndexSize(self.feature_count, index_node_size)
        else
            0;
        const to_skip = try checkedAddU64(rtree_index_size, attr_index_size);
        const to_skip_usize: usize = @intCast(to_skip);

        const preamble_len = try checkedAdd(try checkedAdd(12, header_size), to_skip_usize);
        self.preamble_buf = try self.allocator.alloc(u8, preamble_len);
        self.owns_preamble_buf = true;
        @memcpy(self.preamble_buf[0..8], &magic);
        @memcpy(self.preamble_buf[8..12], &header_size_buf);
        @memcpy(self.preamble_buf[12 .. 12 + header_size], self.header_buf[4..][0..header_size]);
        if (to_skip_usize > 0) {
            try readExact(&self.file, self.preamble_buf[12 + header_size ..]);
        }
    }

    fn ensurePending(self: *Reader) !bool {
        if (self.reached_eof) return false;
        if (self.pending_loaded) return true;

        var size_buf: [4]u8 = undefined;
        const size_read = try self.file.read(&size_buf);
        if (size_read == 0) {
            self.reached_eof = true;
            return false;
        }
        var have: usize = size_read;
        while (have < size_buf.len) {
            const n = try self.file.read(size_buf[have..]);
            if (n == 0) return error.UnexpectedEndOfStream;
            have += n;
        }

        const feature_size: usize = @intCast(std.mem.readInt(u32, &size_buf, .little));
        try self.feature_buf.resize(self.allocator, feature_size + 4);
        @memcpy(self.feature_buf.items[0..4], &size_buf);
        try readExact(&self.file, self.feature_buf.items[4..]);

        const feature_table = try fb.sizePrefixedRootTable(self.feature_buf.items);
        const pending_id = try fb.getRequiredString(self.feature_buf.items, feature_table, VT_FEATURE_ID);
        const pending_id_copy = try self.allocator.dupe(u8, pending_id);
        errdefer self.allocator.free(pending_id_copy);
        if (self.pending_id_owned) |old| self.allocator.free(old);
        self.pending_id_owned = pending_id_copy;
        self.pending_loaded = true;
        return true;
    }

    fn decodePendingFeature(self: *Reader) !void {
        self.scratch_vertices.clearRetainingCapacity();
        self.scratch_objects.clearRetainingCapacity();
        self.scratch_geometries.clearRetainingCapacity();
        self.scratch_attributes.clearRetainingCapacity();
        self.scratch_columns.clearRetainingCapacity();
        self.scratch_column_types.clearRetainingCapacity();
        self.scratch_u32.clearRetainingCapacity();
        self.scratch_u8.clearRetainingCapacity();

        const feature_table = try fb.sizePrefixedRootTable(self.feature_buf.items);
        const feature_id = try fb.getRequiredString(self.feature_buf.items, feature_table, VT_FEATURE_ID);

        const vertex_count = try self.countFeatureVertices(feature_table);
        const totals = try self.countFeatureObjectData(feature_table);
        try self.scratch_vertices.ensureTotalCapacity(self.allocator, vertex_count);
        try self.scratch_objects.ensureTotalCapacity(self.allocator, totals.object_count);
        try self.scratch_geometries.ensureTotalCapacity(self.allocator, totals.geometry_count);
        try self.scratch_attributes.ensureTotalCapacity(self.allocator, totals.attribute_count);
        try self.scratch_u32.ensureTotalCapacity(self.allocator, totals.u32_count);
        try self.scratch_u8.ensureTotalCapacity(self.allocator, totals.semantic_object_count);

        try self.decodeVertices(feature_table);
        try self.decodeObjects(feature_table);

        self.current_feature = .{
            .id = feature_id,
            .vertices = self.scratch_vertices.items,
            .objects = self.scratch_objects.items,
        };
    }

    const CountTotals = struct {
        object_count: usize = 0,
        geometry_count: usize = 0,
        attribute_count: usize = 0,
        u32_count: usize = 0,
        semantic_object_count: usize = 0,
    };

    const ColumnTypeByIndex = struct {
        index: u16,
        column_type: ColumnType,
    };
    const EMPTY_COLUMN_TYPES: []const ColumnTypeByIndex = &[_]ColumnTypeByIndex{};

    fn countFeatureVertices(self: *Reader, feature_table: usize) !usize {
        const maybe_vec = try fb.getVectorInfo(self.feature_buf.items, feature_table, VT_FEATURE_VERTICES);
        return if (maybe_vec) |vec| vec.len else 0;
    }

    fn countFeatureObjectData(self: *Reader, feature_table: usize) !CountTotals {
        var totals: CountTotals = .{};
        const maybe_objects = try fb.getVectorInfo(self.feature_buf.items, feature_table, VT_FEATURE_OBJECTS);
        if (maybe_objects == null) return totals;
        const objects_vec = maybe_objects.?;

        totals.object_count = objects_vec.len;
        for (0..objects_vec.len) |i| {
            const obj_table = try fb.vectorTableAt(self.feature_buf.items, objects_vec, i);
            try self.countObjectData(obj_table, &totals);
        }
        return totals;
    }

    fn countObjectData(self: *Reader, obj_table: usize, totals: *CountTotals) !void {
        if (try fb.getVectorInfo(self.feature_buf.items, obj_table, VT_OBJECT_GEOMETRY)) |geom_vec| {
            totals.geometry_count = try checkedAdd(totals.geometry_count, geom_vec.len);
            for (0..geom_vec.len) |i| {
                const geom_table = try fb.vectorTableAt(self.feature_buf.items, geom_vec, i);
                try self.countGeometryData(geom_table, totals);
            }
        }

        self.scratch_column_types.clearRetainingCapacity();
        try self.parseColumnTypesInto(self.feature_buf.items, obj_table, VT_OBJECT_COLUMNS, &self.scratch_column_types);
        const attr_schema = if (self.scratch_column_types.items.len > 0) self.scratch_column_types.items else EMPTY_COLUMN_TYPES;
        if (try fb.getVectorBytes(self.feature_buf.items, obj_table, VT_OBJECT_ATTRIBUTES)) |attr_bytes| {
            if (attr_bytes.len > 0 and attr_schema.len == 0 and self.root_columns.len == 0) {
                return error.MissingAttributeSchema;
            }
            const attr_count = try countAttributes(self.root_columns, attr_schema, attr_bytes);
            totals.attribute_count = try checkedAdd(totals.attribute_count, attr_count);
        }
    }

    fn countGeometryData(self: *Reader, geom_table: usize, totals: *CountTotals) !void {
        inline for ([_]u16{
            VT_GEOMETRY_SOLIDS,
            VT_GEOMETRY_SHELLS,
            VT_GEOMETRY_SURFACES,
            VT_GEOMETRY_STRINGS,
            VT_GEOMETRY_BOUNDARIES,
            VT_GEOMETRY_SEMANTICS,
        }) |field| {
            if (try fb.getVectorInfo(self.feature_buf.items, geom_table, field)) |vec| {
                totals.u32_count = try checkedAdd(totals.u32_count, vec.len);
            }
        }
        if (try fb.getVectorInfo(self.feature_buf.items, geom_table, VT_GEOMETRY_SEMANTICS_OBJECTS)) |vec| {
            totals.semantic_object_count = try checkedAdd(totals.semantic_object_count, vec.len);
        }
    }

    fn decodeVertices(self: *Reader, feature_table: usize) !void {
        const maybe_vec = try fb.getVectorInfo(self.feature_buf.items, feature_table, VT_FEATURE_VERTICES);
        if (maybe_vec == null) return;
        const vec = maybe_vec.?;

        const total_bytes = try checkedMul(vec.len, 12);
        const end = try checkedAdd(vec.start, total_bytes);
        if (end > self.feature_buf.items.len) return error.InvalidFlatBuffer;

        try self.scratch_vertices.ensureTotalCapacity(self.allocator, vec.len);
        for (0..vec.len) |i| {
            const pos = try checkedAdd(vec.start, try checkedMul(i, 12));
            const v = [3]i32{
                try fb.readI32Le(self.feature_buf.items, pos),
                try fb.readI32Le(self.feature_buf.items, pos + 4),
                try fb.readI32Le(self.feature_buf.items, pos + 8),
            };
            self.scratch_vertices.appendAssumeCapacity(self.transform.apply(v));
        }
    }

    fn decodeObjects(self: *Reader, feature_table: usize) !void {
        const maybe_objects = try fb.getVectorInfo(self.feature_buf.items, feature_table, VT_FEATURE_OBJECTS);
        if (maybe_objects == null) return;
        const objects_vec = maybe_objects.?;

        try self.scratch_objects.ensureTotalCapacity(self.allocator, objects_vec.len);
        for (0..objects_vec.len) |i| {
            const obj_table = try fb.vectorTableAt(self.feature_buf.items, objects_vec, i);
            try self.decodeObject(obj_table);
        }
    }

    fn decodeObject(self: *Reader, obj_table: usize) !void {
        const object_id = try fb.getRequiredString(self.feature_buf.items, obj_table, VT_OBJECT_ID);
        const object_type_raw = try fb.getScalarU8Default(self.feature_buf.items, obj_table, VT_OBJECT_TYPE, 0);
        const object_type: ObjectType = @enumFromInt(object_type_raw);
        const extension_type = try fb.getString(self.feature_buf.items, obj_table, VT_OBJECT_EXTENSION_TYPE);

        const geom_start = self.scratch_geometries.items.len;
        if (try fb.getVectorInfo(self.feature_buf.items, obj_table, VT_OBJECT_GEOMETRY)) |geom_vec| {
            for (0..geom_vec.len) |i| {
                const geom_table = try fb.vectorTableAt(self.feature_buf.items, geom_vec, i);
                try self.decodeGeometry(geom_table);
            }
        }
        const geometries = self.scratch_geometries.items[geom_start..];

        const attr_start = self.scratch_attributes.items.len;
        try self.parseColumnsInto(self.feature_buf.items, obj_table, VT_OBJECT_COLUMNS, &self.scratch_columns);
        const attr_schema = if (self.scratch_columns.items.len > 0) self.scratch_columns.items else self.root_columns;
        if (try fb.getVectorBytes(self.feature_buf.items, obj_table, VT_OBJECT_ATTRIBUTES)) |attr_bytes| {
            if (attr_bytes.len > 0 and attr_schema.len == 0) return error.MissingAttributeSchema;
            try self.decodeAttributes(attr_schema, attr_bytes);
        }
        const attributes = self.scratch_attributes.items[attr_start..];

        try self.scratch_objects.append(self.allocator, .{
            .id = object_id,
            .object_type = object_type,
            .extension_type = extension_type,
            .geometries = geometries,
            .attributes = attributes,
        });
    }

    fn decodeGeometry(self: *Reader, geom_table: usize) !void {
        const geometry_type_raw = try fb.getScalarU8Default(self.feature_buf.items, geom_table, VT_GEOMETRY_TYPE, 0);
        const geometry_type: GeometryType = @enumFromInt(geometry_type_raw);
        const lod = try fb.getString(self.feature_buf.items, geom_table, VT_GEOMETRY_LOD);

        const solids = try self.appendVectorU32(self.feature_buf.items, geom_table, VT_GEOMETRY_SOLIDS);
        const shells = try self.appendVectorU32(self.feature_buf.items, geom_table, VT_GEOMETRY_SHELLS);
        const surfaces = try self.appendVectorU32(self.feature_buf.items, geom_table, VT_GEOMETRY_SURFACES);
        const strings = try self.appendVectorU32(self.feature_buf.items, geom_table, VT_GEOMETRY_STRINGS);
        const boundaries = try self.appendVectorU32(self.feature_buf.items, geom_table, VT_GEOMETRY_BOUNDARIES);
        const semantics = try self.appendVectorU32(self.feature_buf.items, geom_table, VT_GEOMETRY_SEMANTICS);
        const semantics_objects = try self.appendSemanticObjectTypes(self.feature_buf.items, geom_table, VT_GEOMETRY_SEMANTICS_OBJECTS);

        try self.scratch_geometries.append(self.allocator, .{
            .geometry_type = geometry_type,
            .lod = lod,
            .solids = solids,
            .shells = shells,
            .surfaces = surfaces,
            .strings = strings,
            .boundaries = boundaries,
            .semantics = semantics,
            .semantics_objects = semantics_objects,
        });
    }

    fn appendVectorU32(self: *Reader, buf: []const u8, table_pos: usize, vtable_offset: u16) ![]const u32 {
        if (try fb.getVectorInfo(buf, table_pos, vtable_offset)) |vec| {
            const start = self.scratch_u32.items.len;
            try self.scratch_u32.ensureTotalCapacity(self.allocator, start + vec.len);
            for (0..vec.len) |i| {
                const pos = try checkedAdd(vec.start, try checkedMul(i, 4));
                const value = try fb.readU32Le(buf, pos);
                self.scratch_u32.appendAssumeCapacity(value);
            }
            return self.scratch_u32.items[start..][0..vec.len];
        }
        return EMPTY_U32;
    }

    fn appendSemanticObjectTypes(self: *Reader, buf: []const u8, table_pos: usize, vtable_offset: u16) ![]const u8 {
        if (try fb.getVectorInfo(buf, table_pos, vtable_offset)) |vec| {
            const start = self.scratch_u8.items.len;
            try self.scratch_u8.ensureTotalCapacity(self.allocator, start + vec.len);
            for (0..vec.len) |i| {
                const obj_table = try fb.vectorTableAt(buf, vec, i);
                const semantic_type = try fb.getScalarU8Default(buf, obj_table, VT_SEMANTIC_OBJECT_TYPE, 0);
                self.scratch_u8.appendAssumeCapacity(semantic_type);
            }
            return self.scratch_u8.items[start..][0..vec.len];
        }
        return EMPTY_U8;
    }

    fn decodeAttributes(self: *Reader, schema: []const ColumnSchema, attr_bytes: []const u8) !void {
        var offset: usize = 0;
        while (offset < attr_bytes.len) {
            if (offset + 2 > attr_bytes.len) return error.InvalidAttributeEncoding;
            const column_index = try fb.readU16Le(attr_bytes, offset);
            offset += 2;

            const column = findColumn(schema, column_index) orelse return error.UnknownColumnIndex;
            const attribute = Attribute{
                .name = column.name,
                .value = switch (column.column_type) {
                    .Byte => blk: {
                        if (offset + 1 > attr_bytes.len) return error.InvalidAttributeEncoding;
                        const value = try fb.readI8(attr_bytes, offset);
                        offset += 1;
                        break :blk .{ .byte = value };
                    },
                    .UByte => blk: {
                        if (offset + 1 > attr_bytes.len) return error.InvalidAttributeEncoding;
                        const value = attr_bytes[offset];
                        offset += 1;
                        break :blk .{ .ubyte = value };
                    },
                    .Bool => blk: {
                        if (offset + 1 > attr_bytes.len) return error.InvalidAttributeEncoding;
                        const value = attr_bytes[offset] != 0;
                        offset += 1;
                        break :blk .{ .bool = value };
                    },
                    .Short => blk: {
                        if (offset + 2 > attr_bytes.len) return error.InvalidAttributeEncoding;
                        const value = try fb.readI16Le(attr_bytes, offset);
                        offset += 2;
                        break :blk .{ .short = value };
                    },
                    .UShort => blk: {
                        if (offset + 2 > attr_bytes.len) return error.InvalidAttributeEncoding;
                        const value = try fb.readU16Le(attr_bytes, offset);
                        offset += 2;
                        break :blk .{ .ushort = value };
                    },
                    .Int => blk: {
                        if (offset + 4 > attr_bytes.len) return error.InvalidAttributeEncoding;
                        const value = try fb.readI32Le(attr_bytes, offset);
                        offset += 4;
                        break :blk .{ .int = value };
                    },
                    .UInt => blk: {
                        if (offset + 4 > attr_bytes.len) return error.InvalidAttributeEncoding;
                        const value = try fb.readU32Le(attr_bytes, offset);
                        offset += 4;
                        break :blk .{ .uint = value };
                    },
                    .Long => blk: {
                        if (offset + 8 > attr_bytes.len) return error.InvalidAttributeEncoding;
                        const value = try fb.readI64Le(attr_bytes, offset);
                        offset += 8;
                        break :blk .{ .long = value };
                    },
                    .ULong => blk: {
                        if (offset + 8 > attr_bytes.len) return error.InvalidAttributeEncoding;
                        const value = try fb.readU64Le(attr_bytes, offset);
                        offset += 8;
                        break :blk .{ .ulong = value };
                    },
                    .Float => blk: {
                        if (offset + 4 > attr_bytes.len) return error.InvalidAttributeEncoding;
                        const value = @as(f32, @bitCast(try fb.readU32Le(attr_bytes, offset)));
                        offset += 4;
                        break :blk .{ .float = value };
                    },
                    .Double => blk: {
                        if (offset + 8 > attr_bytes.len) return error.InvalidAttributeEncoding;
                        const value = @as(f64, @bitCast(try fb.readU64Le(attr_bytes, offset)));
                        offset += 8;
                        break :blk .{ .double = value };
                    },
                    .String => blk: {
                        const value = try readLengthPrefixedBytes(attr_bytes, &offset);
                        break :blk .{ .string = value };
                    },
                    .Json => blk: {
                        const value = try readLengthPrefixedBytes(attr_bytes, &offset);
                        break :blk .{ .json = value };
                    },
                    .DateTime => blk: {
                        const value = try readLengthPrefixedBytes(attr_bytes, &offset);
                        break :blk .{ .datetime = value };
                    },
                    .Binary => blk: {
                        const value = try readLengthPrefixedBytes(attr_bytes, &offset);
                        break :blk .{ .binary = value };
                    },
                    else => return error.UnsupportedColumnType,
                },
            };
            try self.scratch_attributes.append(self.allocator, attribute);
        }
    }

    fn loadRootColumns(self: *Reader, header_table: usize) !void {
        if (try fb.getVectorInfo(self.header_buf, header_table, VT_HEADER_COLUMNS)) |columns_vec| {
            var root_cols = try self.allocator.alloc(ColumnSchema, columns_vec.len);
            errdefer self.allocator.free(root_cols);
            self.owns_root_columns = true;
            for (0..columns_vec.len) |i| {
                const col_table = try fb.vectorTableAt(self.header_buf, columns_vec, i);
                root_cols[i] = .{
                    .index = try fb.getScalarU16Default(self.header_buf, col_table, VT_COLUMN_INDEX, 0),
                    .name = try fb.getRequiredString(self.header_buf, col_table, VT_COLUMN_NAME),
                    .column_type = @enumFromInt(try fb.getScalarU8Default(self.header_buf, col_table, VT_COLUMN_TYPE, 0)),
                };
            }
            self.root_columns = root_cols;
        } else {
            self.root_columns = try self.allocator.alloc(ColumnSchema, 0);
            self.owns_root_columns = true;
        }
    }

    fn parseColumnsInto(
        self: *Reader,
        buf: []const u8,
        table_pos: usize,
        vtable_offset: u16,
        out: *std.ArrayList(ColumnSchema),
    ) !void {
        out.clearRetainingCapacity();
        if (try fb.getVectorInfo(buf, table_pos, vtable_offset)) |columns_vec| {
            try out.ensureTotalCapacity(self.allocator, columns_vec.len);
            for (0..columns_vec.len) |i| {
                const col_table = try fb.vectorTableAt(buf, columns_vec, i);
                out.appendAssumeCapacity(.{
                    .index = try fb.getScalarU16Default(buf, col_table, VT_COLUMN_INDEX, 0),
                    .name = try fb.getRequiredString(buf, col_table, VT_COLUMN_NAME),
                    .column_type = @enumFromInt(try fb.getScalarU8Default(buf, col_table, VT_COLUMN_TYPE, 0)),
                });
            }
        }
    }

    fn parseColumnTypesInto(
        self: *Reader,
        buf: []const u8,
        table_pos: usize,
        vtable_offset: u16,
        out: *std.ArrayList(ColumnTypeByIndex),
    ) !void {
        out.clearRetainingCapacity();
        if (try fb.getVectorInfo(buf, table_pos, vtable_offset)) |columns_vec| {
            try out.ensureTotalCapacity(self.allocator, columns_vec.len);
            for (0..columns_vec.len) |i| {
                const col_table = try fb.vectorTableAt(buf, columns_vec, i);
                out.appendAssumeCapacity(.{
                    .index = try fb.getScalarU16Default(buf, col_table, VT_COLUMN_INDEX, 0),
                    .column_type = @enumFromInt(try fb.getScalarU8Default(buf, col_table, VT_COLUMN_TYPE, 0)),
                });
            }
        }
    }

    fn readAttributeIndexSize(self: *Reader, header_table: usize) !u64 {
        if (try fb.getVectorInfo(self.header_buf, header_table, VT_HEADER_ATTRIBUTE_INDEX)) |attr_vec| {
            const bytes_len = try checkedMul(attr_vec.len, 16);
            const end = try checkedAdd(attr_vec.start, bytes_len);
            if (end > self.header_buf.len) return error.InvalidFlatBuffer;

            var total: u64 = 0;
            for (0..attr_vec.len) |i| {
                const entry_pos = try checkedAdd(attr_vec.start, try checkedMul(i, 16));
                const length = try fb.readU32Le(self.header_buf, entry_pos + 4);
                total = try checkedAddU64(total, length);
            }
            return total;
        }
        return 0;
    }
};

fn findColumn(schema: []const ColumnSchema, index: u16) ?ColumnSchema {
    for (schema) |column| {
        if (column.index == index) return column;
    }
    return null;
}

fn findColumnType(
    root_schema: []const ColumnSchema,
    object_schema: []const Reader.ColumnTypeByIndex,
    index: u16,
) ?ColumnType {
    if (object_schema.len > 0) {
        for (object_schema) |column| {
            if (column.index == index) return column.column_type;
        }
        return null;
    }
    for (root_schema) |column| {
        if (column.index == index) return column.column_type;
    }
    return null;
}

fn countAttributes(
    root_schema: []const ColumnSchema,
    object_schema: []const Reader.ColumnTypeByIndex,
    attr_bytes: []const u8,
) !usize {
    var offset: usize = 0;
    var count: usize = 0;
    while (offset < attr_bytes.len) {
        if (offset + 2 > attr_bytes.len) return error.InvalidAttributeEncoding;
        const column_index = try fb.readU16Le(attr_bytes, offset);
        offset += 2;

        const column_type = findColumnType(root_schema, object_schema, column_index) orelse {
            return error.UnknownColumnIndex;
        };
        try skipAttributeValue(column_type, attr_bytes, &offset);
        count = try checkedAdd(count, 1);
    }
    return count;
}

fn skipAttributeValue(column_type: ColumnType, bytes: []const u8, offset: *usize) !void {
    switch (column_type) {
        .Byte, .UByte, .Bool => {
            if (offset.* + 1 > bytes.len) return error.InvalidAttributeEncoding;
            offset.* += 1;
        },
        .Short, .UShort => {
            if (offset.* + 2 > bytes.len) return error.InvalidAttributeEncoding;
            offset.* += 2;
        },
        .Int, .UInt, .Float => {
            if (offset.* + 4 > bytes.len) return error.InvalidAttributeEncoding;
            offset.* += 4;
        },
        .Long, .ULong, .Double => {
            if (offset.* + 8 > bytes.len) return error.InvalidAttributeEncoding;
            offset.* += 8;
        },
        .String, .Json, .DateTime, .Binary => {
            _ = try readLengthPrefixedBytes(bytes, offset);
        },
        else => return error.UnsupportedColumnType,
    }
}

fn readLengthPrefixedBytes(bytes: []const u8, offset: *usize) ![]const u8 {
    if (offset.* + 4 > bytes.len) return error.InvalidAttributeEncoding;
    const len: usize = @intCast(try fb.readU32Le(bytes, offset.*));
    offset.* += 4;
    const end = try checkedAdd(offset.*, len);
    if (end > bytes.len) return error.InvalidAttributeEncoding;
    const out = bytes[offset.*..end];
    offset.* = end;
    return out;
}

fn readHeaderTransform(header_buf: []const u8, header_table: usize) !Transform {
    if (try fb.tableFieldPos(header_buf, header_table, VT_HEADER_TRANSFORM)) |field_pos| {
        if (field_pos + 48 > header_buf.len) return error.InvalidFlatBuffer;
        return .{
            .scale = .{
                try fb.readF64Le(header_buf, field_pos + 0),
                try fb.readF64Le(header_buf, field_pos + 8),
                try fb.readF64Le(header_buf, field_pos + 16),
            },
            .translate = .{
                try fb.readF64Le(header_buf, field_pos + 24),
                try fb.readF64Le(header_buf, field_pos + 32),
                try fb.readF64Le(header_buf, field_pos + 40),
            },
        };
    }
    return .{};
}

fn packedRtreeIndexSize(feature_count: u64, node_size: u16) !u64 {
    if (feature_count == 0) return 0;
    if (node_size < 2) return error.InvalidNodeSize;

    const node_size_clamped: u64 = @as(u64, @intCast(node_size));
    var n: u64 = feature_count;
    var node_count: u64 = n;

    while (true) {
        n = (n + node_size_clamped - 1) / node_size_clamped;
        node_count = try checkedAddU64(node_count, n);
        if (n == 1) break;
    }
    return try checkedMulU64(node_count, NODE_ITEM_SIZE_BYTES);
}

fn skipBytes(file: *std.fs.File, count: u64) !void {
    var remaining = count;
    var buf: [4096]u8 = undefined;
    while (remaining > 0) {
        const chunk: usize = @intCast(@min(remaining, buf.len));
        try readExact(file, buf[0..chunk]);
        remaining -= chunk;
    }
}

fn readExact(file: *std.fs.File, out: []u8) !void {
    var read_total: usize = 0;
    while (read_total < out.len) {
        const n = try file.read(out[read_total..]);
        if (n == 0) return error.UnexpectedEndOfStream;
        read_total += n;
    }
}

fn checkedAdd(a: usize, b: usize) !usize {
    if (a > std.math.maxInt(usize) - b) return error.IntegerOverflow;
    return a + b;
}

fn checkedMul(a: usize, b: usize) !usize {
    if (a != 0 and b > std.math.maxInt(usize) / a) return error.IntegerOverflow;
    return a * b;
}

fn checkedAddU64(a: u64, b: u64) !u64 {
    if (a > std.math.maxInt(u64) - b) return error.IntegerOverflow;
    return a + b;
}

fn checkedMulU64(a: u64, b: u64) !u64 {
    if (a != 0 and b > std.math.maxInt(u64) / a) return error.IntegerOverflow;
    return a * b;
}

const fb = struct {
    const VectorInfo = struct {
        start: usize,
        len: usize,
    };

    fn sizePrefixedRootTable(buf: []const u8) !usize {
        if (buf.len < 8) return error.InvalidFlatBuffer;
        const root_rel: usize = @intCast(try readU32Le(buf, 4));
        const table_pos = try checkedAdd(4, root_rel);
        if (table_pos + 4 > buf.len) return error.InvalidFlatBuffer;
        return table_pos;
    }

    fn tableFieldPos(buf: []const u8, table_pos: usize, vtable_offset: u16) !?usize {
        if (table_pos + 4 > buf.len) return error.InvalidFlatBuffer;
        const vtable_back = try readI32Le(buf, table_pos);
        const table_isize: isize = @intCast(table_pos);
        const vtable_isize = table_isize - @as(isize, vtable_back);
        if (vtable_isize < 0) return error.InvalidFlatBuffer;
        const vtable_pos: usize = @intCast(vtable_isize);
        if (vtable_pos + 4 > buf.len) return error.InvalidFlatBuffer;

        const vtable_len = try readU16Le(buf, vtable_pos);
        if (vtable_offset >= vtable_len) return null;

        const rel = try readU16Le(buf, vtable_pos + vtable_offset);
        if (rel == 0) return null;

        const field_pos = try checkedAdd(table_pos, rel);
        if (field_pos > buf.len) return error.InvalidFlatBuffer;
        return field_pos;
    }

    fn derefUOffset(buf: []const u8, pos: usize) !usize {
        const rel: usize = @intCast(try readU32Le(buf, pos));
        const target = try checkedAdd(pos, rel);
        if (target + 4 > buf.len) return error.InvalidFlatBuffer;
        return target;
    }

    fn getString(buf: []const u8, table_pos: usize, vtable_offset: u16) !?[]const u8 {
        const field_pos = try tableFieldPos(buf, table_pos, vtable_offset);
        if (field_pos == null) return null;
        const str_pos = try derefUOffset(buf, field_pos.?);
        const str_len: usize = @intCast(try readU32Le(buf, str_pos));
        const start = try checkedAdd(str_pos, 4);
        const end = try checkedAdd(start, str_len);
        if (end > buf.len) return error.InvalidFlatBuffer;
        return buf[start..end];
    }

    fn getRequiredString(buf: []const u8, table_pos: usize, vtable_offset: u16) ![]const u8 {
        return (try getString(buf, table_pos, vtable_offset)) orelse error.MissingRequiredField;
    }

    fn getVectorInfo(buf: []const u8, table_pos: usize, vtable_offset: u16) !?VectorInfo {
        const field_pos = try tableFieldPos(buf, table_pos, vtable_offset);
        if (field_pos == null) return null;
        const vec_pos = try derefUOffset(buf, field_pos.?);
        const len: usize = @intCast(try readU32Le(buf, vec_pos));
        const start = try checkedAdd(vec_pos, 4);
        if (start > buf.len) return error.InvalidFlatBuffer;
        return .{ .start = start, .len = len };
    }

    fn vectorTableAt(buf: []const u8, vec: VectorInfo, index: usize) !usize {
        if (index >= vec.len) return error.IndexOutOfBounds;
        const slot = try checkedAdd(vec.start, try checkedMul(index, 4));
        if (slot + 4 > buf.len) return error.InvalidFlatBuffer;
        return derefUOffset(buf, slot);
    }

    fn getVectorBytes(buf: []const u8, table_pos: usize, vtable_offset: u16) !?[]const u8 {
        if (try getVectorInfo(buf, table_pos, vtable_offset)) |vec| {
            const end = try checkedAdd(vec.start, vec.len);
            if (end > buf.len) return error.InvalidFlatBuffer;
            return buf[vec.start..end];
        }
        return null;
    }

    fn getScalarU8Default(buf: []const u8, table_pos: usize, vtable_offset: u16, default: u8) !u8 {
        if (try tableFieldPos(buf, table_pos, vtable_offset)) |field_pos| {
            if (field_pos + 1 > buf.len) return error.InvalidFlatBuffer;
            return buf[field_pos];
        }
        return default;
    }

    fn getScalarU16Default(buf: []const u8, table_pos: usize, vtable_offset: u16, default: u16) !u16 {
        if (try tableFieldPos(buf, table_pos, vtable_offset)) |field_pos| {
            return readU16Le(buf, field_pos);
        }
        return default;
    }

    fn getScalarU64Default(buf: []const u8, table_pos: usize, vtable_offset: u16, default: u64) !u64 {
        if (try tableFieldPos(buf, table_pos, vtable_offset)) |field_pos| {
            return readU64Le(buf, field_pos);
        }
        return default;
    }

    fn readI8(buf: []const u8, pos: usize) !i8 {
        if (pos + 1 > buf.len) return error.InvalidFlatBuffer;
        return @bitCast(buf[pos]);
    }

    fn readU16Le(buf: []const u8, pos: usize) !u16 {
        if (pos + 2 > buf.len) return error.InvalidFlatBuffer;
        return std.mem.readInt(u16, buf[pos..][0..2], .little);
    }

    fn readI16Le(buf: []const u8, pos: usize) !i16 {
        if (pos + 2 > buf.len) return error.InvalidFlatBuffer;
        return std.mem.readInt(i16, buf[pos..][0..2], .little);
    }

    fn readU32Le(buf: []const u8, pos: usize) !u32 {
        if (pos + 4 > buf.len) return error.InvalidFlatBuffer;
        return std.mem.readInt(u32, buf[pos..][0..4], .little);
    }

    fn readI32Le(buf: []const u8, pos: usize) !i32 {
        if (pos + 4 > buf.len) return error.InvalidFlatBuffer;
        return std.mem.readInt(i32, buf[pos..][0..4], .little);
    }

    fn readU64Le(buf: []const u8, pos: usize) !u64 {
        if (pos + 8 > buf.len) return error.InvalidFlatBuffer;
        return std.mem.readInt(u64, buf[pos..][0..8], .little);
    }

    fn readI64Le(buf: []const u8, pos: usize) !i64 {
        if (pos + 8 > buf.len) return error.InvalidFlatBuffer;
        return std.mem.readInt(i64, buf[pos..][0..8], .little);
    }

    fn readF64Le(buf: []const u8, pos: usize) !f64 {
        return @bitCast(try readU64Le(buf, pos));
    }
};

pub const Writer = struct {
    file: std.fs.File,
    owns_file: bool = true,
    transform: Transform = .{},
    feature_count_patch_pos: ?u64 = null,
    written_feature_count: u64 = 0,

    pub fn openPathFromReader(reader: *const Reader, path: []const u8) !Writer {
        const file = if (std.fs.path.isAbsolute(path))
            try std.fs.createFileAbsolute(path, .{ .truncate = true })
        else
            try std.fs.cwd().createFile(path, .{ .truncate = true });
        errdefer file.close();

        return openFileFromReader(reader, file, true);
    }

    pub fn openFileFromReader(reader: *const Reader, file: std.fs.File, owns_file: bool) !Writer {
        if (owns_file) {
            errdefer file.close();
        }
        if (reader.preamble().len == 0) return error.MissingReaderPreamble;
        try file.writeAll(reader.preamble());
        return .{
            .file = file,
            .owns_file = owns_file,
            .transform = reader.transform,
        };
    }

    pub fn deinit(self: *Writer) void {
        if (self.feature_count_patch_pos) |pos| {
            self.file.seekTo(pos) catch {};
            var tmp: [8]u8 = undefined;
            std.mem.writeInt(u64, &tmp, self.written_feature_count, .little);
            _ = self.file.writeAll(&tmp) catch {};
        }
        if (self.owns_file) {
            self.file.close();
        }
    }

    /// Opens a writer that copies the header from the reader but strips the spatial
    /// index and attribute indexes from the preamble. Use this variant when features
    /// may be modified (e.g. via FeatureBuilder-based rewrites), since changed
    /// feature byte lengths invalidate the original index offsets.
    pub fn openPathFromReaderNoIndex(reader: *const Reader, path: []const u8) !Writer {
        var file = if (std.fs.path.isAbsolute(path))
            try std.fs.createFileAbsolute(path, .{ .truncate = true })
        else
            try std.fs.cwd().createFile(path, .{ .truncate = true });
        errdefer file.close();

        return openFileFromReaderNoIndex(reader, file, true);
    }

    pub fn openFileFromReaderNoIndex(reader: *const Reader, file: std.fs.File, owns_file: bool) !Writer {
        if (owns_file) {
            errdefer file.close();
        }
        if (reader.header_buf.len < 8) return error.MissingReaderPreamble;

        const header_size = reader.headerSize();
        // Preamble without indexes: magic(8) + header_size_buf(4) + header_data(header_size).
        const base_preamble_len = 12 + header_size;
        if (reader.preamble_buf.len < base_preamble_len) return error.MissingReaderPreamble;

        // Work on a mutable copy so we can patch before writing.
        // Reserve 2 extra bytes in case we need to append a zero u16 for index_node_size.
        const allocator = std.heap.page_allocator;
        const buf = try allocator.alloc(u8, base_preamble_len + 2);
        defer allocator.free(buf);
        @memcpy(buf[0..base_preamble_len], reader.preamble_buf[0..base_preamble_len]);
        buf[base_preamble_len] = 0;
        buf[base_preamble_len + 1] = 0;
        var write_len: usize = base_preamble_len;

        // Positions in header_buf map to buf positions as: buf_pos = hb_pos + 8.
        const header_table = try fb.sizePrefixedRootTable(reader.header_buf);

        // Locate the vtable (needed for both index_node_size and attribute_index patches).
        if (header_table + 4 > reader.header_buf.len) return error.InvalidFlatBuffer;
        const vtable_back = try fb.readI32Le(reader.header_buf, header_table);
        const table_isize: isize = @intCast(header_table);
        const vtable_isize = table_isize - @as(isize, vtable_back);
        if (vtable_isize < 0) return error.InvalidFlatBuffer;
        const vtable_pos: usize = @intCast(vtable_isize);
        if (vtable_pos + 4 > reader.header_buf.len) return error.InvalidFlatBuffer;
        const vtable_len = try fb.readU16Le(reader.header_buf, vtable_pos);

        // Patch index_node_size to 0 to indicate no spatial index.
        if (try fb.tableFieldPos(reader.header_buf, header_table, VT_HEADER_INDEX_NODE_SIZE)) |field_pos| {
            // Field is explicitly stored; overwrite its value with 0.
            const pos = field_pos + 8;
            buf[pos] = 0;
            buf[pos + 1] = 0;
        } else if (VT_HEADER_INDEX_NODE_SIZE + 2 <= vtable_len) {
            // Field absent (vtable entry is 0, flatbuffer default 16 applies).
            // Append 2 zero bytes and point the vtable entry at them.
            write_len = base_preamble_len + 2;

            // Update header size in the size-prefix at buf[8..12].
            const new_header_size: u32 = @intCast(header_size + 2);
            std.mem.writeInt(u32, buf[8..12], new_header_size, .little);

            // Set vtable entry to the relative offset from table_pos to the new bytes.
            // New bytes are at header_buf position: 4 + header_size (end of original fb data).
            const new_field_hb_pos: usize = 4 + header_size;
            const rel: u16 = @intCast(new_field_hb_pos - header_table);
            const vt_entry_buf_pos = vtable_pos + VT_HEADER_INDEX_NODE_SIZE + 8;
            std.mem.writeInt(u16, buf[vt_entry_buf_pos..][0..2], rel, .little);
        }

        // Nullify the attribute_index vtable entry (make the field appear absent).
        if (VT_HEADER_ATTRIBUTE_INDEX + 2 <= vtable_len) {
            const pos = vtable_pos + VT_HEADER_ATTRIBUTE_INDEX + 8;
            buf[pos] = 0;
            buf[pos + 1] = 0;
        }

        try file.writeAll(buf[0..write_len]);
        return .{
            .file = file,
            .owns_file = owns_file,
            .transform = reader.transform,
        };
    }

    pub fn openPathNewNoIndex(path: []const u8, transform: Transform, root_columns: []const ColumnSchema) !Writer {
        const file = if (std.fs.path.isAbsolute(path))
            try std.fs.createFileAbsolute(path, .{ .truncate = true })
        else
            try std.fs.cwd().createFile(path, .{ .truncate = true });
        errdefer file.close();

        const header = try buildHeaderNoIndex(std.heap.page_allocator, transform, root_columns);
        defer std.heap.page_allocator.free(header.bytes);

        try file.writeAll(&MAGIC_BYTES);
        try file.writeAll(header.bytes);

        const patch_pos = try checkedAddU64(8, header.feature_count_field_pos);
        return .{
            .file = file,
            .owns_file = true,
            .transform = transform,
            .feature_count_patch_pos = patch_pos,
        };
    }

    pub fn writeFeatureRaw(self: *Writer, feature_bytes: []const u8) !void {
        try self.file.writeAll(feature_bytes);
        if (self.feature_count_patch_pos != null) {
            self.written_feature_count = try checkedAddU64(self.written_feature_count, 1);
        }
    }

    pub fn writeFeatureBuilt(self: *Writer, allocator: std.mem.Allocator, feature: *const FeatureBuilder) !void {
        var feature_bytes = std.ArrayList(u8){};
        defer feature_bytes.deinit(allocator);
        try feature.encodeFeature(&feature_bytes);
        try self.writeFeatureRaw(feature_bytes.items);
    }
};

fn alignAppend(buf: *std.ArrayList(u8), allocator: std.mem.Allocator, alignment: usize) !void {
    std.debug.assert(alignment != 0 and std.math.isPowerOfTwo(alignment));
    const rem = buf.items.len & (alignment - 1);
    if (rem == 0) return;
    const pad = alignment - rem;
    try buf.appendNTimes(allocator, 0, pad);
}

fn alignAppend4(buf: *std.ArrayList(u8), allocator: std.mem.Allocator) !void {
    try alignAppend(buf, allocator, 4);
}

fn appendU32Le(buf: *std.ArrayList(u8), allocator: std.mem.Allocator, value: u32) !void {
    var tmp: [4]u8 = undefined;
    std.mem.writeInt(u32, &tmp, value, .little);
    try buf.appendSlice(allocator, &tmp);
}

fn appendI32Le(buf: *std.ArrayList(u8), allocator: std.mem.Allocator, value: i32) !void {
    var tmp: [4]u8 = undefined;
    std.mem.writeInt(i32, &tmp, value, .little);
    try buf.appendSlice(allocator, &tmp);
}

fn appendU16Le(buf: *std.ArrayList(u8), allocator: std.mem.Allocator, value: u16) !void {
    var tmp: [2]u8 = undefined;
    std.mem.writeInt(u16, &tmp, value, .little);
    try buf.appendSlice(allocator, &tmp);
}

fn appendU64Le(buf: *std.ArrayList(u8), allocator: std.mem.Allocator, value: u64) !void {
    var tmp: [8]u8 = undefined;
    std.mem.writeInt(u64, &tmp, value, .little);
    try buf.appendSlice(allocator, &tmp);
}

fn appendF64Le(buf: *std.ArrayList(u8), allocator: std.mem.Allocator, value: f64) !void {
    try appendU64Le(buf, allocator, @bitCast(value));
}

fn appendString(buf: *std.ArrayList(u8), allocator: std.mem.Allocator, value: []const u8) !usize {
    try alignAppend4(buf, allocator);
    const start = buf.items.len;
    try appendU32Le(buf, allocator, @intCast(value.len));
    try buf.appendSlice(allocator, value);
    try buf.append(allocator, 0); // null terminator
    return start;
}

fn appendVectorBytes(buf: *std.ArrayList(u8), allocator: std.mem.Allocator, values: []const u8) !usize {
    try alignAppend4(buf, allocator);
    const start = buf.items.len;
    try appendU32Le(buf, allocator, @intCast(values.len));
    try buf.appendSlice(allocator, values);
    return start;
}

fn appendVectorStrings(
    buf: *std.ArrayList(u8),
    allocator: std.mem.Allocator,
    values: []const []const u8,
) !usize {
    try alignAppend4(buf, allocator);
    const vec_start = buf.items.len;
    try appendU32Le(buf, allocator, @intCast(values.len));
    const offsets_start = buf.items.len;
    for (0..values.len) |_| {
        try appendU32Le(buf, allocator, 0);
    }
    for (values, 0..) |s, i| {
        const str_start = try appendString(buf, allocator, s);
        const offset_pos = offsets_start + i * 4;
        const rel: u32 = @intCast(str_start - offset_pos);
        std.mem.writeInt(u32, buf.items[offset_pos..][0..4], rel, .little);
    }
    return vec_start;
}

fn appendVectorU32Values(
    buf: *std.ArrayList(u8),
    allocator: std.mem.Allocator,
    values: []const u32,
) !usize {
    try alignAppend4(buf, allocator);
    const start = buf.items.len;
    try appendU32Le(buf, allocator, @intCast(values.len));
    for (values) |v| {
        try appendU32Le(buf, allocator, v);
    }
    return start;
}

fn appendVectorU32Repeated(
    buf: *std.ArrayList(u8),
    allocator: std.mem.Allocator,
    count: usize,
    value: u32,
) !usize {
    try alignAppend4(buf, allocator);
    const start = buf.items.len;
    try appendU32Le(buf, allocator, @intCast(count));
    for (0..count) |_| {
        try appendU32Le(buf, allocator, value);
    }
    return start;
}

fn quantizeCoordinate(value: f64, scale: f64, translate: f64) !i32 {
    if (!std.math.isFinite(value)) return error.InvalidCoordinate;
    if (scale == 0.0) return error.InvalidTransformScale;
    const qf = std.math.round((value - translate) / scale);
    if (!std.math.isFinite(qf)) return error.InvalidCoordinate;

    const min_i32 = @as(f64, @floatFromInt(std.math.minInt(i32)));
    const max_i32 = @as(f64, @floatFromInt(std.math.maxInt(i32)));
    if (qf < min_i32 or qf > max_i32) return error.CoordinateOutOfRange;
    return @intFromFloat(qf);
}

const QuantizedVertex = struct {
    x: i32,
    y: i32,
    z: i32,
};

fn appendVectorVerticesQuantized(
    buf: *std.ArrayList(u8),
    allocator: std.mem.Allocator,
    transform: Transform,
    vertices_xyz: []const f64,
) !usize {
    if (vertices_xyz.len % 3 != 0) return error.InvalidVertexArray;
    const vertex_count = vertices_xyz.len / 3;

    try alignAppend4(buf, allocator);
    const start = buf.items.len;
    try appendU32Le(buf, allocator, @intCast(vertex_count));
    for (0..vertex_count) |i| {
        const x = vertices_xyz[i * 3];
        const y = vertices_xyz[i * 3 + 1];
        const z = vertices_xyz[i * 3 + 2];
        try appendI32Le(buf, allocator, try quantizeCoordinate(x, transform.scale[0], transform.translate[0]));
        try appendI32Le(buf, allocator, try quantizeCoordinate(y, transform.scale[1], transform.translate[1]));
        try appendI32Le(buf, allocator, try quantizeCoordinate(z, transform.scale[2], transform.translate[2]));
    }
    return start;
}

fn appendVectorVerticesQuantizedRaw(
    buf: *std.ArrayList(u8),
    allocator: std.mem.Allocator,
    vertices: []const QuantizedVertex,
) !usize {
    try alignAppend4(buf, allocator);
    const start = buf.items.len;
    try appendU32Le(buf, allocator, @intCast(vertices.len));
    for (vertices) |v| {
        try appendI32Le(buf, allocator, v.x);
        try appendI32Le(buf, allocator, v.y);
        try appendI32Le(buf, allocator, v.z);
    }
    return start;
}

const TableField = struct {
    vtable_offset: u16,
    relative_offset: u16,
};

const TableInfo = struct {
    vtable_pos: usize,
    table_pos: usize,
};

fn appendTableSkeleton(
    buf: *std.ArrayList(u8),
    allocator: std.mem.Allocator,
    table_alignment: usize,
    table_data_len: u16,
    vtable_len: u16,
    fields: []const TableField,
) !TableInfo {
    if (table_data_len < 4 or vtable_len < 4) return error.InvalidFlatBuffer;
    try alignAppend4(buf, allocator);

    const vtable_pos = buf.items.len;
    const vtable_bytes = try allocator.alloc(u8, vtable_len);
    defer allocator.free(vtable_bytes);
    @memset(vtable_bytes, 0);
    std.mem.writeInt(u16, vtable_bytes[0..2], vtable_len, .little);
    std.mem.writeInt(u16, vtable_bytes[2..4], table_data_len, .little);
    for (fields) |field| {
        if (field.vtable_offset + 2 > vtable_len) return error.InvalidFlatBuffer;
        std.mem.writeInt(u16, vtable_bytes[field.vtable_offset..][0..2], field.relative_offset, .little);
    }
    try buf.appendSlice(allocator, vtable_bytes);

    try alignAppend(buf, allocator, table_alignment);
    const table_pos = buf.items.len;
    try buf.appendNTimes(allocator, 0, table_data_len);
    const vtable_back: i32 = @intCast(table_pos - vtable_pos);
    std.mem.writeInt(i32, buf.items[table_pos..][0..4], vtable_back, .little);

    return .{
        .vtable_pos = vtable_pos,
        .table_pos = table_pos,
    };
}

fn patchUOffset(buf: []u8, field_pos: usize, target_pos: usize) !void {
    if (target_pos <= field_pos) return error.InvalidRewriteOffset;
    const rel = try checkedAdd(target_pos, 0) - field_pos;
    var tmp: [4]u8 = undefined;
    std.mem.writeInt(u32, &tmp, @intCast(rel), .little);
    @memcpy(buf[field_pos .. field_pos + 4], &tmp);
}

/// Builds a flatbuffer vector of SemanticObject tables and appends it to the buffer.
/// Each SemanticObject contains only a `type` field (u8, VT offset 4).
/// Returns the start position of the vector (the u32 length prefix).
fn appendSemanticObjectsVector(
    buf: *std.ArrayList(u8),
    allocator: std.mem.Allocator,
    types: []const u8,
) !usize {
    // Each SemanticObject is a flatbuffer table.
    // Layout per object:
    //   vtable (8 bytes): vtable_len=8 u16, table_data_len=8 u16, type_rel=4 u16, pad=0 u16
    //   table  (8 bytes): vtable_back i32, type u8, 3 bytes padding
    // Total: 16 bytes per object, 4-byte aligned.
    //
    // The vector is: [u32 count] [u32 offset_0] [u32 offset_1] ... then the table data.

    try alignAppend4(buf, allocator);

    // Reserve space for the offset vector: count + N offsets.
    const vec_start = buf.items.len;
    try appendU32Le(buf, allocator, @intCast(types.len));
    // Placeholder offsets — we'll patch them after writing the tables.
    const offsets_start = buf.items.len;
    for (0..types.len) |_| {
        try appendU32Le(buf, allocator, 0); // placeholder
    }

    // Write each SemanticObject table and patch its offset.
    for (0..types.len) |i| {
        try alignAppend4(buf, allocator);

        // vtable: 8 bytes
        const vtable_pos = buf.items.len;
        var vtable: [8]u8 = undefined;
        std.mem.writeInt(u16, vtable[0..2], 8, .little); // vtable_len
        std.mem.writeInt(u16, vtable[2..4], 8, .little); // table_data_len
        std.mem.writeInt(u16, vtable[4..6], 4, .little); // type field at offset 4 from table start
        std.mem.writeInt(u16, vtable[6..8], 0, .little); // no more fields
        try buf.appendSlice(allocator, &vtable);

        // table: 8 bytes (vtable_back i32, type u8, 3 pad)
        const table_pos = buf.items.len;
        var table: [8]u8 = .{0} ** 8;
        const vtable_back: i32 = @intCast(table_pos - vtable_pos);
        std.mem.writeInt(i32, table[0..4], vtable_back, .little);
        table[4] = types[i]; // SemanticSurfaceType enum value
        try buf.appendSlice(allocator, &table);

        // Patch the offset in the vector. Offsets in flatbuffer vectors of tables
        // are u32 relative to the offset's own position.
        const offset_pos = offsets_start + i * 4;
        const rel: u32 = @intCast(table_pos - offset_pos);
        std.mem.writeInt(u32, buf.items[offset_pos..][0..4], rel, .little);
    }

    return vec_start;
}

const FeatureGeometryData = struct {
    geometry_type: GeometryType,
    lod: ?[]const u8,
    solids: []const u32,
    has_solids: bool,
    shells: []const u32,
    has_shells: bool,
    surfaces: []const u32,
    has_surfaces: bool,
    strings: []const u32,
    has_strings: bool,
    boundaries: []const u32,
    has_boundaries: bool,
    semantics: []const u32,
    has_semantics: bool,
    semantics_objects: []const u8,
    has_semantics_objects: bool,

    fn deinit(self: *FeatureGeometryData, allocator: std.mem.Allocator) void {
        if (self.solids.len > 0) allocator.free(self.solids);
        if (self.shells.len > 0) allocator.free(self.shells);
        if (self.surfaces.len > 0) allocator.free(self.surfaces);
        if (self.strings.len > 0) allocator.free(self.strings);
        if (self.boundaries.len > 0) allocator.free(self.boundaries);
        if (self.semantics.len > 0) allocator.free(self.semantics);
        if (self.semantics_objects.len > 0) allocator.free(self.semantics_objects);
        self.* = undefined;
    }
};

const FeatureObjectData = struct {
    id: []const u8,
    object_type: ObjectType,
    extension_type: ?[]const u8,
    geometries: []FeatureGeometryData,
    has_geometries: bool,
    attributes_raw: []const u8,
    has_attributes: bool,
    columns: []const ColumnSchema,
    has_columns: bool,
    children: []const []const u8,
    has_children: bool,
    children_roles: []const []const u8,
    has_children_roles: bool,
    parents: []const []const u8,
    has_parents: bool,

    fn deinit(self: *FeatureObjectData, allocator: std.mem.Allocator) void {
        for (self.geometries) |*geom| {
            geom.deinit(allocator);
        }
        if (self.geometries.len > 0) allocator.free(self.geometries);
        if (self.attributes_raw.len > 0) allocator.free(self.attributes_raw);
        if (self.columns.len > 0) allocator.free(self.columns);
        if (self.children.len > 0) {
            for (self.children) |s| allocator.free(s);
            allocator.free(self.children);
        }
        if (self.children_roles.len > 0) {
            for (self.children_roles) |s| allocator.free(s);
            allocator.free(self.children_roles);
        }
        if (self.parents.len > 0) {
            for (self.parents) |s| allocator.free(s);
            allocator.free(self.parents);
        }
        self.* = undefined;
    }
};

const EMPTY_QUANTIZED_VERTICES: []QuantizedVertex = @constCast(&[_]QuantizedVertex{});
const EMPTY_FEATURE_GEOMETRIES: []FeatureGeometryData = @constCast(&[_]FeatureGeometryData{});
const EMPTY_FEATURE_OBJECTS: []FeatureObjectData = @constCast(&[_]FeatureObjectData{});

const OwnedU32Vector = struct {
    values: []const u32,
    present: bool,
};

const OwnedU8Vector = struct {
    values: []const u8,
    present: bool,
};

const OwnedColumns = struct {
    values: []const ColumnSchema,
    present: bool,
};

const OwnedStrings = struct {
    values: []const []const u8,
    present: bool,
};

pub const FeatureBuilder = struct {
    allocator: std.mem.Allocator,
    transform: Transform,
    feature_id: []const u8 = "",
    vertices_q: []QuantizedVertex = EMPTY_QUANTIZED_VERTICES,
    has_vertices: bool = false,
    objects: []FeatureObjectData = EMPTY_FEATURE_OBJECTS,
    has_objects: bool = false,

    pub fn init(allocator: std.mem.Allocator, transform: Transform) FeatureBuilder {
        return .{
            .allocator = allocator,
            .transform = transform,
        };
    }

    pub fn deinit(self: *FeatureBuilder) void {
        self.clear();
    }

    pub fn clear(self: *FeatureBuilder) void {
        if (self.vertices_q.len > 0) self.allocator.free(self.vertices_q);
        for (self.objects) |*obj| {
            obj.deinit(self.allocator);
        }
        if (self.objects.len > 0) self.allocator.free(self.objects);
        self.feature_id = "";
        self.vertices_q = EMPTY_QUANTIZED_VERTICES;
        self.has_vertices = false;
        self.objects = EMPTY_FEATURE_OBJECTS;
        self.has_objects = false;
    }

    pub fn loadCurrentFromReader(self: *FeatureBuilder, reader: *Reader) !void {
        self.clear();

        const feature_table = try fb.sizePrefixedRootTable(reader.feature_buf.items);
        self.feature_id = try fb.getRequiredString(reader.feature_buf.items, feature_table, VT_FEATURE_ID);

        if (try fb.getVectorInfo(reader.feature_buf.items, feature_table, VT_FEATURE_VERTICES)) |verts_vec| {
            self.has_vertices = true;
            if (verts_vec.len == 0) {
                self.vertices_q = EMPTY_QUANTIZED_VERTICES;
            } else {
                const total_bytes = try checkedMul(verts_vec.len, 12);
                const end = try checkedAdd(verts_vec.start, total_bytes);
                if (end > reader.feature_buf.items.len) return error.InvalidFlatBuffer;
                const verts = try self.allocator.alloc(QuantizedVertex, verts_vec.len);
                errdefer self.allocator.free(verts);
                for (0..verts_vec.len) |i| {
                    const pos = try checkedAdd(verts_vec.start, try checkedMul(i, 12));
                    verts[i] = .{
                        .x = try fb.readI32Le(reader.feature_buf.items, pos),
                        .y = try fb.readI32Le(reader.feature_buf.items, pos + 4),
                        .z = try fb.readI32Le(reader.feature_buf.items, pos + 8),
                    };
                }
                self.vertices_q = verts;
            }
        }

        if (try fb.getVectorInfo(reader.feature_buf.items, feature_table, VT_FEATURE_OBJECTS)) |objects_vec| {
            self.has_objects = true;
            if (objects_vec.len == 0) {
                self.objects = EMPTY_FEATURE_OBJECTS;
                return;
            }

            const objects = try self.allocator.alloc(FeatureObjectData, objects_vec.len);
            var built: usize = 0;
            errdefer {
                for (objects[0..built]) |*obj| obj.deinit(self.allocator);
                self.allocator.free(objects);
            }

            for (0..objects_vec.len) |i| {
                const obj_table = try fb.vectorTableAt(reader.feature_buf.items, objects_vec, i);
                objects[i] = try decodeFeatureObject(self.allocator, reader.feature_buf.items, obj_table);
                built += 1;
            }
            self.objects = objects;
        }
    }

    pub fn replaceLod22Solid(
        self: *FeatureBuilder,
        feature_id: []const u8,
        vertices_xyz_world: []const f64,
        triangle_indices: []const u32,
        semantic_types: []const u8,
    ) !void {
        if (triangle_indices.len % 3 != 0) return error.InvalidTriangleIndexArray;
        if (vertices_xyz_world.len % 3 != 0) return error.InvalidVertexArray;
        const new_vertex_count = vertices_xyz_world.len / 3;
        if (new_vertex_count == 0) return error.InvalidVertexArray;
        const tri_count = triangle_indices.len / 3;
        if (semantic_types.len != tri_count) return error.InvalidSemanticTypesArray;
        for (triangle_indices) |idx| {
            if (idx >= new_vertex_count) return error.InvalidTriangleIndexArray;
        }

        if (!self.has_objects) return error.TargetObjectNotFound;
        const object_id = try buildObjectId(self.allocator, feature_id);
        defer self.allocator.free(object_id);

        var target_geom: ?*FeatureGeometryData = null;
        for (self.objects) |*obj| {
            if (!std.mem.eql(u8, obj.id, object_id)) continue;
            for (obj.geometries) |*geom| {
                const solid_like = geom.geometry_type == .Solid or geom.geometry_type == .MultiSolid or geom.geometry_type == .CompositeSolid;
                if (!solid_like) continue;
                const lod = geom.lod orelse continue;
                if (std.mem.eql(u8, lod, "2.2")) {
                    target_geom = geom;
                    break;
                }
            }
            if (target_geom != null) break;
            return error.TargetGeometryNotFound;
        }
        const geom = target_geom orelse return error.TargetObjectNotFound;

        if (self.vertices_q.len > std.math.maxInt(u32)) return error.IntegerOverflow;
        var quantized_to_index = std.AutoHashMap(QuantizedVertex, u32).init(self.allocator);
        defer quantized_to_index.deinit();
        for (self.vertices_q, 0..) |q, i| {
            const gop = try quantized_to_index.getOrPut(q);
            if (!gop.found_existing) gop.value_ptr.* = @intCast(i);
        }

        const unresolved = std.math.maxInt(u32);
        const src_to_final = try self.allocator.alloc(u32, new_vertex_count);
        defer self.allocator.free(src_to_final);
        @memset(src_to_final, unresolved);

        var appended_vertices = std.ArrayList(QuantizedVertex){};
        defer appended_vertices.deinit(self.allocator);
        var remapped_boundaries = std.ArrayList(u32){};
        defer remapped_boundaries.deinit(self.allocator);
        try remapped_boundaries.ensureTotalCapacity(self.allocator, triangle_indices.len);

        for (triangle_indices) |src_idx_u32| {
            const src_idx: usize = @intCast(src_idx_u32);
            var final_idx = src_to_final[src_idx];
            if (final_idx == unresolved) {
                const q = QuantizedVertex{
                    .x = try quantizeCoordinate(vertices_xyz_world[src_idx * 3], self.transform.scale[0], self.transform.translate[0]),
                    .y = try quantizeCoordinate(vertices_xyz_world[src_idx * 3 + 1], self.transform.scale[1], self.transform.translate[1]),
                    .z = try quantizeCoordinate(vertices_xyz_world[src_idx * 3 + 2], self.transform.scale[2], self.transform.translate[2]),
                };
                if (quantized_to_index.get(q)) |existing| {
                    final_idx = existing;
                } else {
                    const next_index = try checkedAdd(self.vertices_q.len, appended_vertices.items.len);
                    if (next_index > std.math.maxInt(u32)) return error.IntegerOverflow;
                    final_idx = @intCast(next_index);
                    try appended_vertices.append(self.allocator, q);
                    try quantized_to_index.put(q, final_idx);
                }
                src_to_final[src_idx] = final_idx;
            }
            remapped_boundaries.appendAssumeCapacity(final_idx);
        }

        if (appended_vertices.items.len > 0) {
            const total_vertex_count = try checkedAdd(self.vertices_q.len, appended_vertices.items.len);
            const updated_vertices = try self.allocator.alloc(QuantizedVertex, total_vertex_count);
            @memcpy(updated_vertices[0..self.vertices_q.len], self.vertices_q);
            @memcpy(updated_vertices[self.vertices_q.len..], appended_vertices.items);
            if (self.vertices_q.len > 0) self.allocator.free(self.vertices_q);
            self.vertices_q = updated_vertices;
        }
        self.has_vertices = true;

        var unique_types: [256]bool = .{false} ** 256;
        for (semantic_types) |t| unique_types[t] = true;
        var type_to_obj_index: [256]u32 = .{std.math.maxInt(u32)} ** 256;
        var object_types = std.ArrayList(u8){};
        defer object_types.deinit(self.allocator);
        for (0..256) |t| {
            if (unique_types[t]) {
                type_to_obj_index[t] = @intCast(object_types.items.len);
                try object_types.append(self.allocator, @intCast(t));
            }
        }

        const solids = try self.allocator.alloc(u32, 1);
        solids[0] = 1;
        const shells = try self.allocator.alloc(u32, 1);
        shells[0] = @intCast(tri_count);
        const surfaces = try self.allocator.alloc(u32, tri_count);
        @memset(surfaces, 1);
        const strings = try self.allocator.alloc(u32, tri_count);
        @memset(strings, 3);
        const boundaries = try self.allocator.alloc(u32, remapped_boundaries.items.len);
        @memcpy(boundaries, remapped_boundaries.items);

        const semantics = try self.allocator.alloc(u32, semantic_types.len);
        for (semantic_types, 0..) |t, i| {
            semantics[i] = type_to_obj_index[t];
        }
        const semantics_objects = try self.allocator.alloc(u8, object_types.items.len);
        @memcpy(semantics_objects, object_types.items);

        if (geom.solids.len > 0) self.allocator.free(geom.solids);
        if (geom.shells.len > 0) self.allocator.free(geom.shells);
        if (geom.surfaces.len > 0) self.allocator.free(geom.surfaces);
        if (geom.strings.len > 0) self.allocator.free(geom.strings);
        if (geom.boundaries.len > 0) self.allocator.free(geom.boundaries);
        if (geom.semantics.len > 0) self.allocator.free(geom.semantics);
        if (geom.semantics_objects.len > 0) self.allocator.free(geom.semantics_objects);

        geom.solids = solids;
        geom.has_solids = true;
        geom.shells = shells;
        geom.has_shells = true;
        geom.surfaces = surfaces;
        geom.has_surfaces = true;
        geom.strings = strings;
        geom.has_strings = true;
        geom.boundaries = boundaries;
        geom.has_boundaries = true;
        geom.semantics = semantics;
        geom.has_semantics = true;
        geom.semantics_objects = semantics_objects;
        geom.has_semantics_objects = true;

        try self.compactVertices();
    }

    fn compactVertices(self: *FeatureBuilder) !void {
        if (self.vertices_q.len == 0) return;

        const used = try self.allocator.alloc(bool, self.vertices_q.len);
        defer self.allocator.free(used);
        @memset(used, false);

        for (self.objects) |obj| {
            for (obj.geometries) |geom| {
                if (!geom.has_boundaries) continue;
                for (geom.boundaries) |idx| {
                    if (idx >= self.vertices_q.len) return error.InvalidFlatBuffer;
                    used[idx] = true;
                }
            }
        }

        var used_count: usize = 0;
        for (used) |u| {
            if (u) used_count += 1;
        }
        if (used_count == self.vertices_q.len) return;

        const old_to_new = try self.allocator.alloc(u32, self.vertices_q.len);
        defer self.allocator.free(old_to_new);
        @memset(old_to_new, std.math.maxInt(u32));

        const compacted_vertices = if (used_count == 0)
            EMPTY_QUANTIZED_VERTICES
        else
            try self.allocator.alloc(QuantizedVertex, used_count);
        var next_index: usize = 0;
        for (self.vertices_q, 0..) |v, old_i| {
            if (!used[old_i]) continue;
            old_to_new[old_i] = @intCast(next_index);
            compacted_vertices[next_index] = v;
            next_index += 1;
        }

        for (self.objects) |*obj| {
            for (obj.geometries) |*geom| {
                if (!geom.has_boundaries) continue;
                const remapped: []u32 = if (geom.boundaries.len == 0)
                    EMPTY_U32_MUT
                else
                    try self.allocator.alloc(u32, geom.boundaries.len);
                for (geom.boundaries, 0..) |old_idx, i| {
                    const mapped = old_to_new[old_idx];
                    if (mapped == std.math.maxInt(u32)) return error.InvalidFlatBuffer;
                    remapped[i] = mapped;
                }
                if (geom.boundaries.len > 0) self.allocator.free(geom.boundaries);
                geom.boundaries = remapped;
            }
        }

        if (self.vertices_q.len > 0) self.allocator.free(self.vertices_q);
        self.vertices_q = compacted_vertices;
    }

    pub fn encodeFeature(self: *const FeatureBuilder, out: *std.ArrayList(u8)) !void {
        out.clearRetainingCapacity();
        try out.appendNTimes(self.allocator, 0, 8);

        const feature_table = try encodeFeatureTable(self.allocator, out, self);
        if (feature_table <= 4) return error.InvalidFlatBuffer;
        std.mem.writeInt(u32, out.items[4..8], @intCast(feature_table - 4), .little);
        std.mem.writeInt(u32, out.items[0..4], @intCast(out.items.len - 4), .little);
    }
};

fn decodeFeatureObject(allocator: std.mem.Allocator, buf: []const u8, obj_table: usize) !FeatureObjectData {
    const object_id = try fb.getRequiredString(buf, obj_table, VT_OBJECT_ID);
    const object_type: ObjectType = @enumFromInt(try fb.getScalarU8Default(buf, obj_table, VT_OBJECT_TYPE, 0));
    const extension_type = try fb.getString(buf, obj_table, VT_OBJECT_EXTENSION_TYPE);

    var geometries: []FeatureGeometryData = EMPTY_FEATURE_GEOMETRIES;
    var has_geometries = false;
    if (try fb.getVectorInfo(buf, obj_table, VT_OBJECT_GEOMETRY)) |geom_vec| {
        has_geometries = true;
        if (geom_vec.len > 0) {
            geometries = try allocator.alloc(FeatureGeometryData, geom_vec.len);
            var built: usize = 0;
            errdefer {
                for (geometries[0..built]) |*geom| geom.deinit(allocator);
                allocator.free(geometries);
            }
            for (0..geom_vec.len) |i| {
                const geom_table = try fb.vectorTableAt(buf, geom_vec, i);
                geometries[i] = try decodeFeatureGeometry(allocator, buf, geom_table);
                built += 1;
            }
        }
    }

    const attributes = try dupVectorBytesWithPresence(allocator, buf, obj_table, VT_OBJECT_ATTRIBUTES);
    errdefer if (attributes.values.len > 0) allocator.free(attributes.values);
    const columns = try dupColumnsWithPresence(allocator, buf, obj_table, VT_OBJECT_COLUMNS);
    errdefer if (columns.values.len > 0) allocator.free(columns.values);
    const children = try dupVectorStringsWithPresence(allocator, buf, obj_table, VT_OBJECT_CHILDREN);
    errdefer {
        if (children.values.len > 0) {
            for (children.values) |s| allocator.free(s);
            allocator.free(children.values);
        }
    }
    const children_roles = try dupVectorStringsWithPresence(allocator, buf, obj_table, VT_OBJECT_CHILDREN_ROLES);
    errdefer {
        if (children_roles.values.len > 0) {
            for (children_roles.values) |s| allocator.free(s);
            allocator.free(children_roles.values);
        }
    }
    const parents = try dupVectorStringsWithPresence(allocator, buf, obj_table, VT_OBJECT_PARENTS);
    errdefer {
        if (parents.values.len > 0) {
            for (parents.values) |s| allocator.free(s);
            allocator.free(parents.values);
        }
    }

    return .{
        .id = object_id,
        .object_type = object_type,
        .extension_type = extension_type,
        .geometries = geometries,
        .has_geometries = has_geometries,
        .attributes_raw = attributes.values,
        .has_attributes = attributes.present,
        .columns = columns.values,
        .has_columns = columns.present,
        .children = children.values,
        .has_children = children.present,
        .children_roles = children_roles.values,
        .has_children_roles = children_roles.present,
        .parents = parents.values,
        .has_parents = parents.present,
    };
}

fn decodeFeatureGeometry(allocator: std.mem.Allocator, buf: []const u8, geom_table: usize) !FeatureGeometryData {
    const geometry_type: GeometryType = @enumFromInt(try fb.getScalarU8Default(buf, geom_table, VT_GEOMETRY_TYPE, 0));
    const lod = try fb.getString(buf, geom_table, VT_GEOMETRY_LOD);

    const solids = try dupVectorU32WithPresence(allocator, buf, geom_table, VT_GEOMETRY_SOLIDS);
    errdefer if (solids.values.len > 0) allocator.free(solids.values);
    const shells = try dupVectorU32WithPresence(allocator, buf, geom_table, VT_GEOMETRY_SHELLS);
    errdefer if (shells.values.len > 0) allocator.free(shells.values);
    const surfaces = try dupVectorU32WithPresence(allocator, buf, geom_table, VT_GEOMETRY_SURFACES);
    errdefer if (surfaces.values.len > 0) allocator.free(surfaces.values);
    const strings = try dupVectorU32WithPresence(allocator, buf, geom_table, VT_GEOMETRY_STRINGS);
    errdefer if (strings.values.len > 0) allocator.free(strings.values);
    const boundaries = try dupVectorU32WithPresence(allocator, buf, geom_table, VT_GEOMETRY_BOUNDARIES);
    errdefer if (boundaries.values.len > 0) allocator.free(boundaries.values);
    const semantics = try dupVectorU32WithPresence(allocator, buf, geom_table, VT_GEOMETRY_SEMANTICS);
    errdefer if (semantics.values.len > 0) allocator.free(semantics.values);
    const semantics_objects = try dupSemanticObjectTypesWithPresence(allocator, buf, geom_table, VT_GEOMETRY_SEMANTICS_OBJECTS);
    errdefer if (semantics_objects.values.len > 0) allocator.free(semantics_objects.values);

    return .{
        .geometry_type = geometry_type,
        .lod = lod,
        .solids = solids.values,
        .has_solids = solids.present,
        .shells = shells.values,
        .has_shells = shells.present,
        .surfaces = surfaces.values,
        .has_surfaces = surfaces.present,
        .strings = strings.values,
        .has_strings = strings.present,
        .boundaries = boundaries.values,
        .has_boundaries = boundaries.present,
        .semantics = semantics.values,
        .has_semantics = semantics.present,
        .semantics_objects = semantics_objects.values,
        .has_semantics_objects = semantics_objects.present,
    };
}

fn dupVectorU32WithPresence(
    allocator: std.mem.Allocator,
    buf: []const u8,
    table_pos: usize,
    vtable_offset: u16,
) !OwnedU32Vector {
    if (try fb.getVectorInfo(buf, table_pos, vtable_offset)) |vec| {
        if (vec.len == 0) return .{ .values = EMPTY_U32, .present = true };
        const out = try allocator.alloc(u32, vec.len);
        for (0..vec.len) |i| {
            const pos = try checkedAdd(vec.start, try checkedMul(i, 4));
            out[i] = try fb.readU32Le(buf, pos);
        }
        return .{ .values = out, .present = true };
    }
    return .{ .values = EMPTY_U32, .present = false };
}

fn dupVectorBytesWithPresence(
    allocator: std.mem.Allocator,
    buf: []const u8,
    table_pos: usize,
    vtable_offset: u16,
) !OwnedU8Vector {
    if (try fb.getVectorBytes(buf, table_pos, vtable_offset)) |bytes| {
        if (bytes.len == 0) return .{ .values = EMPTY_U8, .present = true };
        const out = try allocator.alloc(u8, bytes.len);
        @memcpy(out, bytes);
        return .{ .values = out, .present = true };
    }
    return .{ .values = EMPTY_U8, .present = false };
}

fn dupSemanticObjectTypesWithPresence(
    allocator: std.mem.Allocator,
    buf: []const u8,
    table_pos: usize,
    vtable_offset: u16,
) !OwnedU8Vector {
    if (try fb.getVectorInfo(buf, table_pos, vtable_offset)) |vec| {
        if (vec.len == 0) return .{ .values = EMPTY_U8, .present = true };
        const out = try allocator.alloc(u8, vec.len);
        for (0..vec.len) |i| {
            const obj_table = try fb.vectorTableAt(buf, vec, i);
            out[i] = try fb.getScalarU8Default(buf, obj_table, VT_SEMANTIC_OBJECT_TYPE, 0);
        }
        return .{ .values = out, .present = true };
    }
    return .{ .values = EMPTY_U8, .present = false };
}

fn dupColumnsWithPresence(
    allocator: std.mem.Allocator,
    buf: []const u8,
    table_pos: usize,
    vtable_offset: u16,
) !OwnedColumns {
    if (try fb.getVectorInfo(buf, table_pos, vtable_offset)) |columns_vec| {
        if (columns_vec.len == 0) return .{ .values = EMPTY_COLUMNS, .present = true };
        const out = try allocator.alloc(ColumnSchema, columns_vec.len);
        for (0..columns_vec.len) |i| {
            const col_table = try fb.vectorTableAt(buf, columns_vec, i);
            out[i] = .{
                .index = try fb.getScalarU16Default(buf, col_table, VT_COLUMN_INDEX, 0),
                .name = try fb.getRequiredString(buf, col_table, VT_COLUMN_NAME),
                .column_type = @enumFromInt(try fb.getScalarU8Default(buf, col_table, VT_COLUMN_TYPE, 0)),
            };
        }
        return .{ .values = out, .present = true };
    }
    return .{ .values = EMPTY_COLUMNS, .present = false };
}

fn dupVectorStringsWithPresence(
    allocator: std.mem.Allocator,
    buf: []const u8,
    table_pos: usize,
    vtable_offset: u16,
) !OwnedStrings {
    if (try fb.getVectorInfo(buf, table_pos, vtable_offset)) |vec| {
        if (vec.len == 0) return .{ .values = EMPTY_STRINGS, .present = true };
        const out = try allocator.alloc([]const u8, vec.len);
        var built: usize = 0;
        errdefer {
            for (out[0..built]) |s| allocator.free(s);
            allocator.free(out);
        }
        for (0..vec.len) |i| {
            const slot = try checkedAdd(vec.start, try checkedMul(i, 4));
            const str_pos = try fb.derefUOffset(buf, slot);
            if (str_pos + 4 > buf.len) return error.InvalidFlatBuffer;
            const str_len: usize = @intCast(try fb.readU32Le(buf, str_pos));
            const start = try checkedAdd(str_pos, 4);
            const end = try checkedAdd(start, str_len);
            if (end > buf.len) return error.InvalidFlatBuffer;
            out[i] = try allocator.dupe(u8, buf[start..end]);
            built += 1;
        }
        return .{ .values = out, .present = true };
    }
    return .{ .values = EMPTY_STRINGS, .present = false };
}

fn encodeFeatureTable(
    allocator: std.mem.Allocator,
    buf: *std.ArrayList(u8),
    feature: *const FeatureBuilder,
) !usize {
    const rel_id: u16 = 4;
    const rel_objects: u16 = 8;
    const rel_vertices: u16 = 12;
    var fields: [3]TableField = undefined;
    var field_count: usize = 0;
    fields[field_count] = .{ .vtable_offset = VT_FEATURE_ID, .relative_offset = rel_id };
    field_count += 1;
    if (feature.has_objects) {
        fields[field_count] = .{ .vtable_offset = VT_FEATURE_OBJECTS, .relative_offset = rel_objects };
        field_count += 1;
    }
    if (feature.has_vertices) {
        fields[field_count] = .{ .vtable_offset = VT_FEATURE_VERTICES, .relative_offset = rel_vertices };
        field_count += 1;
    }

    const table = try appendTableSkeleton(buf, allocator, 4, 16, VT_FEATURE_VERTICES + 2, fields[0..field_count]);

    const id_start = try appendString(buf, allocator, feature.feature_id);
    try patchUOffset(buf.items, table.table_pos + rel_id, id_start);

    if (feature.has_objects) {
        try alignAppend4(buf, allocator);
        const objects_start = buf.items.len;
        try appendU32Le(buf, allocator, @intCast(feature.objects.len));
        const offsets_start = buf.items.len;
        for (0..feature.objects.len) |_| {
            try appendU32Le(buf, allocator, 0);
        }
        for (feature.objects, 0..) |obj, i| {
            const obj_table = try encodeObjectTable(allocator, buf, &obj);
            const offset_pos = offsets_start + i * 4;
            const rel: u32 = @intCast(obj_table - offset_pos);
            std.mem.writeInt(u32, buf.items[offset_pos..][0..4], rel, .little);
        }
        try patchUOffset(buf.items, table.table_pos + rel_objects, objects_start);
    }

    if (feature.has_vertices) {
        const vertices_start = try appendVectorVerticesQuantizedRaw(buf, allocator, feature.vertices_q);
        try patchUOffset(buf.items, table.table_pos + rel_vertices, vertices_start);
    }
    return table.table_pos;
}

fn encodeObjectTable(
    allocator: std.mem.Allocator,
    buf: *std.ArrayList(u8),
    object: *const FeatureObjectData,
) !usize {
    const rel_type: u16 = 4;
    const rel_extension_type: u16 = 8;
    const rel_id: u16 = 12;
    const rel_geometry: u16 = 16;
    const rel_attributes: u16 = 20;
    const rel_columns: u16 = 24;
    const rel_children: u16 = 28;
    const rel_children_roles: u16 = 32;
    const rel_parents: u16 = 36;

    var fields: [9]TableField = undefined;
    var field_count: usize = 0;
    fields[field_count] = .{ .vtable_offset = VT_OBJECT_TYPE, .relative_offset = rel_type };
    field_count += 1;
    fields[field_count] = .{ .vtable_offset = VT_OBJECT_ID, .relative_offset = rel_id };
    field_count += 1;
    if (object.extension_type != null) {
        fields[field_count] = .{ .vtable_offset = VT_OBJECT_EXTENSION_TYPE, .relative_offset = rel_extension_type };
        field_count += 1;
    }
    if (object.has_geometries) {
        fields[field_count] = .{ .vtable_offset = VT_OBJECT_GEOMETRY, .relative_offset = rel_geometry };
        field_count += 1;
    }
    if (object.has_attributes) {
        fields[field_count] = .{ .vtable_offset = VT_OBJECT_ATTRIBUTES, .relative_offset = rel_attributes };
        field_count += 1;
    }
    if (object.has_columns) {
        fields[field_count] = .{ .vtable_offset = VT_OBJECT_COLUMNS, .relative_offset = rel_columns };
        field_count += 1;
    }
    if (object.has_children) {
        fields[field_count] = .{ .vtable_offset = VT_OBJECT_CHILDREN, .relative_offset = rel_children };
        field_count += 1;
    }
    if (object.has_children_roles) {
        fields[field_count] = .{ .vtable_offset = VT_OBJECT_CHILDREN_ROLES, .relative_offset = rel_children_roles };
        field_count += 1;
    }
    if (object.has_parents) {
        fields[field_count] = .{ .vtable_offset = VT_OBJECT_PARENTS, .relative_offset = rel_parents };
        field_count += 1;
    }

    const table = try appendTableSkeleton(buf, allocator, 4, 40, VT_OBJECT_PARENTS + 2, fields[0..field_count]);
    buf.items[table.table_pos + rel_type] = @intFromEnum(object.object_type);

    const id_start = try appendString(buf, allocator, object.id);
    try patchUOffset(buf.items, table.table_pos + rel_id, id_start);

    if (object.extension_type) |extension_type| {
        const extension_start = try appendString(buf, allocator, extension_type);
        try patchUOffset(buf.items, table.table_pos + rel_extension_type, extension_start);
    }

    if (object.has_geometries) {
        try alignAppend4(buf, allocator);
        const geometries_start = buf.items.len;
        try appendU32Le(buf, allocator, @intCast(object.geometries.len));
        const offsets_start = buf.items.len;
        for (0..object.geometries.len) |_| {
            try appendU32Le(buf, allocator, 0);
        }
        for (object.geometries, 0..) |geom, i| {
            const geom_table = try encodeGeometryTable(allocator, buf, &geom);
            const offset_pos = offsets_start + i * 4;
            const rel: u32 = @intCast(geom_table - offset_pos);
            std.mem.writeInt(u32, buf.items[offset_pos..][0..4], rel, .little);
        }
        try patchUOffset(buf.items, table.table_pos + rel_geometry, geometries_start);
    }

    if (object.has_attributes) {
        const attributes_start = try appendVectorBytes(buf, allocator, object.attributes_raw);
        try patchUOffset(buf.items, table.table_pos + rel_attributes, attributes_start);
    }

    if (object.has_columns) {
        try alignAppend4(buf, allocator);
        const columns_start = buf.items.len;
        try appendU32Le(buf, allocator, @intCast(object.columns.len));
        const offsets_start = buf.items.len;
        for (0..object.columns.len) |_| {
            try appendU32Le(buf, allocator, 0);
        }
        for (object.columns, 0..) |col, i| {
            const col_table = try encodeColumnTable(allocator, buf, col);
            const offset_pos = offsets_start + i * 4;
            const rel: u32 = @intCast(col_table - offset_pos);
            std.mem.writeInt(u32, buf.items[offset_pos..][0..4], rel, .little);
        }
        try patchUOffset(buf.items, table.table_pos + rel_columns, columns_start);
    }
    if (object.has_children) {
        const children_start = try appendVectorStrings(buf, allocator, object.children);
        try patchUOffset(buf.items, table.table_pos + rel_children, children_start);
    }
    if (object.has_children_roles) {
        const children_roles_start = try appendVectorStrings(buf, allocator, object.children_roles);
        try patchUOffset(buf.items, table.table_pos + rel_children_roles, children_roles_start);
    }
    if (object.has_parents) {
        const parents_start = try appendVectorStrings(buf, allocator, object.parents);
        try patchUOffset(buf.items, table.table_pos + rel_parents, parents_start);
    }
    return table.table_pos;
}

fn encodeGeometryTable(
    allocator: std.mem.Allocator,
    buf: *std.ArrayList(u8),
    geometry: *const FeatureGeometryData,
) !usize {
    const rel_type: u16 = 4;
    const rel_lod: u16 = 8;
    const rel_solids: u16 = 12;
    const rel_shells: u16 = 16;
    const rel_surfaces: u16 = 20;
    const rel_strings: u16 = 24;
    const rel_boundaries: u16 = 28;
    const rel_semantics: u16 = 32;
    const rel_semantics_objects: u16 = 36;

    var fields: [9]TableField = undefined;
    var field_count: usize = 0;
    fields[field_count] = .{ .vtable_offset = VT_GEOMETRY_TYPE, .relative_offset = rel_type };
    field_count += 1;
    if (geometry.lod != null) {
        fields[field_count] = .{ .vtable_offset = VT_GEOMETRY_LOD, .relative_offset = rel_lod };
        field_count += 1;
    }
    if (geometry.has_solids) {
        fields[field_count] = .{ .vtable_offset = VT_GEOMETRY_SOLIDS, .relative_offset = rel_solids };
        field_count += 1;
    }
    if (geometry.has_shells) {
        fields[field_count] = .{ .vtable_offset = VT_GEOMETRY_SHELLS, .relative_offset = rel_shells };
        field_count += 1;
    }
    if (geometry.has_surfaces) {
        fields[field_count] = .{ .vtable_offset = VT_GEOMETRY_SURFACES, .relative_offset = rel_surfaces };
        field_count += 1;
    }
    if (geometry.has_strings) {
        fields[field_count] = .{ .vtable_offset = VT_GEOMETRY_STRINGS, .relative_offset = rel_strings };
        field_count += 1;
    }
    if (geometry.has_boundaries) {
        fields[field_count] = .{ .vtable_offset = VT_GEOMETRY_BOUNDARIES, .relative_offset = rel_boundaries };
        field_count += 1;
    }
    if (geometry.has_semantics) {
        fields[field_count] = .{ .vtable_offset = VT_GEOMETRY_SEMANTICS, .relative_offset = rel_semantics };
        field_count += 1;
    }
    if (geometry.has_semantics_objects) {
        fields[field_count] = .{ .vtable_offset = VT_GEOMETRY_SEMANTICS_OBJECTS, .relative_offset = rel_semantics_objects };
        field_count += 1;
    }

    const table = try appendTableSkeleton(buf, allocator, 4, 40, VT_GEOMETRY_SEMANTICS_OBJECTS + 2, fields[0..field_count]);
    buf.items[table.table_pos + rel_type] = @intFromEnum(geometry.geometry_type);

    if (geometry.lod) |lod| {
        const lod_start = try appendString(buf, allocator, lod);
        try patchUOffset(buf.items, table.table_pos + rel_lod, lod_start);
    }
    if (geometry.has_solids) {
        const start = try appendVectorU32Values(buf, allocator, geometry.solids);
        try patchUOffset(buf.items, table.table_pos + rel_solids, start);
    }
    if (geometry.has_shells) {
        const start = try appendVectorU32Values(buf, allocator, geometry.shells);
        try patchUOffset(buf.items, table.table_pos + rel_shells, start);
    }
    if (geometry.has_surfaces) {
        const start = try appendVectorU32Values(buf, allocator, geometry.surfaces);
        try patchUOffset(buf.items, table.table_pos + rel_surfaces, start);
    }
    if (geometry.has_strings) {
        const start = try appendVectorU32Values(buf, allocator, geometry.strings);
        try patchUOffset(buf.items, table.table_pos + rel_strings, start);
    }
    if (geometry.has_boundaries) {
        const start = try appendVectorU32Values(buf, allocator, geometry.boundaries);
        try patchUOffset(buf.items, table.table_pos + rel_boundaries, start);
    }
    if (geometry.has_semantics) {
        const start = try appendVectorU32Values(buf, allocator, geometry.semantics);
        try patchUOffset(buf.items, table.table_pos + rel_semantics, start);
    }
    if (geometry.has_semantics_objects) {
        const start = try appendSemanticObjectsVector(buf, allocator, geometry.semantics_objects);
        try patchUOffset(buf.items, table.table_pos + rel_semantics_objects, start);
    }
    return table.table_pos;
}

fn encodeColumnTable(allocator: std.mem.Allocator, buf: *std.ArrayList(u8), column: ColumnSchema) !usize {
    const rel_index: u16 = 4;
    const rel_name: u16 = 8;
    const rel_type: u16 = 12;
    const table = try appendTableSkeleton(
        buf,
        allocator,
        4,
        16,
        VT_COLUMN_TYPE + 2,
        &.{
            .{ .vtable_offset = VT_COLUMN_INDEX, .relative_offset = rel_index },
            .{ .vtable_offset = VT_COLUMN_NAME, .relative_offset = rel_name },
            .{ .vtable_offset = VT_COLUMN_TYPE, .relative_offset = rel_type },
        },
    );
    std.mem.writeInt(u16, buf.items[table.table_pos + rel_index ..][0..2], column.index, .little);
    buf.items[table.table_pos + rel_type] = @intFromEnum(column.column_type);
    const name_start = try appendString(buf, allocator, column.name);
    try patchUOffset(buf.items, table.table_pos + rel_name, name_start);
    return table.table_pos;
}

const HeaderBuild = struct {
    bytes: []u8,
    feature_count_field_pos: u64,
};

const HeaderTableBuild = struct {
    table_pos: usize,
    feature_count_field_pos: usize,
};

fn buildHeaderNoIndex(
    allocator: std.mem.Allocator,
    transform: Transform,
    root_columns: []const ColumnSchema,
) !HeaderBuild {
    var header = std.ArrayList(u8){};
    errdefer header.deinit(allocator);
    try header.appendNTimes(allocator, 0, 8);

    const table = try encodeHeaderTableNoIndex(allocator, &header, transform, root_columns);
    if (table.table_pos <= 4) return error.InvalidFlatBuffer;

    std.mem.writeInt(u32, header.items[4..8], @intCast(table.table_pos - 4), .little);
    std.mem.writeInt(u32, header.items[0..4], @intCast(header.items.len - 4), .little);

    const out = try header.toOwnedSlice(allocator);
    return .{
        .bytes = out,
        .feature_count_field_pos = @intCast(table.feature_count_field_pos),
    };
}

fn encodeHeaderTableNoIndex(
    allocator: std.mem.Allocator,
    buf: *std.ArrayList(u8),
    transform: Transform,
    root_columns: []const ColumnSchema,
) !HeaderTableBuild {
    const rel_columns: u16 = 4;
    const rel_transform: u16 = 8;
    const rel_feature_count: u16 = 56;
    const rel_index_node_size: u16 = 64;

    var fields: [4]TableField = undefined;
    var field_count: usize = 0;
    if (root_columns.len > 0) {
        fields[field_count] = .{ .vtable_offset = VT_HEADER_COLUMNS, .relative_offset = rel_columns };
        field_count += 1;
    }
    fields[field_count] = .{ .vtable_offset = VT_HEADER_TRANSFORM, .relative_offset = rel_transform };
    field_count += 1;
    fields[field_count] = .{ .vtable_offset = VT_HEADER_FEATURES_COUNT, .relative_offset = rel_feature_count };
    field_count += 1;
    fields[field_count] = .{ .vtable_offset = VT_HEADER_INDEX_NODE_SIZE, .relative_offset = rel_index_node_size };
    field_count += 1;

    const table = try appendTableSkeleton(buf, allocator, 8, 72, VT_HEADER_ATTRIBUTE_INDEX + 2, fields[0..field_count]);
    var pos = table.table_pos + rel_transform;
    inline for ([_]f64{
        transform.scale[0],
        transform.scale[1],
        transform.scale[2],
        transform.translate[0],
        transform.translate[1],
        transform.translate[2],
    }) |v| {
        std.mem.writeInt(u64, buf.items[pos..][0..8], @bitCast(v), .little);
        pos += 8;
    }
    std.mem.writeInt(u64, buf.items[table.table_pos + rel_feature_count ..][0..8], 0, .little);
    std.mem.writeInt(u16, buf.items[table.table_pos + rel_index_node_size ..][0..2], 0, .little);

    if (root_columns.len > 0) {
        try alignAppend4(buf, allocator);
        const columns_start = buf.items.len;
        try appendU32Le(buf, allocator, @intCast(root_columns.len));
        const offsets_start = buf.items.len;
        for (0..root_columns.len) |_| {
            try appendU32Le(buf, allocator, 0);
        }
        for (root_columns, 0..) |column, i| {
            const col_table = try encodeColumnTable(allocator, buf, column);
            const offset_pos = offsets_start + i * 4;
            const rel: u32 = @intCast(col_table - offset_pos);
            std.mem.writeInt(u32, buf.items[offset_pos..][0..4], rel, .little);
        }
        try patchUOffset(buf.items, table.table_pos + rel_columns, columns_start);
    }

    return .{
        .table_pos = table.table_pos,
        .feature_count_field_pos = table.table_pos + rel_feature_count,
    };
}

fn buildObjectId(allocator: std.mem.Allocator, feature_id: []const u8) ![]u8 {
    const out = try allocator.alloc(u8, feature_id.len + 2);
    @memcpy(out[0..feature_id.len], feature_id);
    out[feature_id.len] = '-';
    out[feature_id.len + 1] = '0';
    return out;
}

// =============================================================================
// C API exports
// =============================================================================

var c_allocator: std.mem.Allocator = std.heap.c_allocator;

pub const ZfcbReaderHandle = *Reader;
pub const ZfcbWriterHandle = *Writer;

fn getCurrentObject(reader: *Reader, object_index: usize) ?*const ObjectView {
    if (object_index >= reader.current_feature.objects.len) return null;
    return &reader.current_feature.objects[object_index];
}

fn getCurrentGeometry(reader: *Reader, object_index: usize, geometry_index: usize) ?*const GeometryView {
    const obj = getCurrentObject(reader, object_index) orelse return null;
    if (geometry_index >= obj.geometries.len) return null;
    return &obj.geometries[geometry_index];
}

fn fileFromFd(fd: c_int) ?std.fs.File {
    if (fd < 0) return null;
    if (builtin.os.tag == .windows) return null;
    const handle: std.fs.File.Handle = @as(std.posix.fd_t, @intCast(fd));
    return .{ .handle = handle };
}

export fn zfcb_reader_open(path: [*c]const u8) callconv(.c) ?ZfcbReaderHandle {
    const path_slice = std.mem.span(path);
    const reader = c_allocator.create(Reader) catch return null;
    reader.* = Reader.openPath(c_allocator, path_slice) catch {
        c_allocator.destroy(reader);
        return null;
    };
    return reader;
}

// Opens a reader from an existing Unix file descriptor.
// close_on_destroy: non-zero => close(fd) in zfcb_reader_destroy, 0 => leave open.
export fn zfcb_reader_open_fd(fd: c_int, close_on_destroy: c_int) callconv(.c) ?ZfcbReaderHandle {
    const file = fileFromFd(fd) orelse return null;
    const reader = c_allocator.create(Reader) catch return null;
    reader.* = Reader.openFile(c_allocator, file, close_on_destroy != 0) catch {
        c_allocator.destroy(reader);
        return null;
    };
    return reader;
}

export fn zfcb_reader_destroy(handle: ?ZfcbReaderHandle) callconv(.c) void {
    if (handle) |reader| {
        reader.deinit();
        c_allocator.destroy(reader);
    }
}

export fn zfcb_feature_count(handle: ?ZfcbReaderHandle) callconv(.c) u64 {
    const reader = handle orelse return 0;
    return reader.featureCount();
}

// Returns: 1 when an ID is available, 0 at EOF, -1 on error.
export fn zfcb_peek_next_id(
    handle: ?ZfcbReaderHandle,
    out_id: *[*c]const u8,
    out_len: *usize,
) callconv(.c) c_int {
    out_id.* = null;
    out_len.* = 0;

    const reader = handle orelse return -1;
    const maybe_id = reader.peekNextId() catch return -1;
    if (maybe_id) |id| {
        out_id.* = id.ptr;
        out_len.* = id.len;
        return 1;
    }
    return 0;
}

// Returns: 1 when skipped, 0 at EOF, -1 on error.
export fn zfcb_skip_next(handle: ?ZfcbReaderHandle) callconv(.c) c_int {
    const reader = handle orelse return -1;
    const skipped = reader.skipNext() catch return -1;
    return if (skipped) 1 else 0;
}

// Returns: 1 when a feature was loaded, 0 at EOF, -1 on error.
export fn zfcb_next(handle: ?ZfcbReaderHandle) callconv(.c) c_int {
    const reader = handle orelse return -1;
    const maybe_feature = reader.next() catch return -1;
    return if (maybe_feature != null) 1 else 0;
}

// Returns 0 on success, -1 on error.
export fn zfcb_current_feature_id(
    handle: ?ZfcbReaderHandle,
    out_id: *[*c]const u8,
    out_len: *usize,
) callconv(.c) c_int {
    out_id.* = null;
    out_len.* = 0;

    const reader = handle orelse return -1;
    const id = reader.current_feature.id;
    if (id.len == 0) return 0;
    out_id.* = id.ptr;
    out_len.* = id.len;
    return 0;
}

export fn zfcb_current_vertex_count(handle: ?ZfcbReaderHandle) callconv(.c) usize {
    const reader = handle orelse return 0;
    return reader.current_feature.vertices.len;
}

// Returns pointer to packed xyz triplets (length = vertex_count * 3 doubles).
// Pointer remains valid until the next zfcb_next / zfcb_skip_next / destroy.
export fn zfcb_current_vertices(handle: ?ZfcbReaderHandle) callconv(.c) [*c]const f64 {
    const reader = handle orelse return null;
    const vertices = reader.current_feature.vertices;
    if (vertices.len == 0) return null;
    return @ptrCast(vertices.ptr);
}

export fn zfcb_current_object_count(handle: ?ZfcbReaderHandle) callconv(.c) usize {
    const reader = handle orelse return 0;
    return reader.current_feature.objects.len;
}

// Returns 0 on success, -1 on invalid object index/handle.
export fn zfcb_current_object_id(
    handle: ?ZfcbReaderHandle,
    object_index: usize,
    out_id: *[*c]const u8,
    out_len: *usize,
) callconv(.c) c_int {
    out_id.* = null;
    out_len.* = 0;

    const reader = handle orelse return -1;
    const obj = getCurrentObject(reader, object_index) orelse return -1;
    out_id.* = obj.id.ptr;
    out_len.* = obj.id.len;
    return 0;
}

export fn zfcb_current_object_type(handle: ?ZfcbReaderHandle, object_index: usize) callconv(.c) u8 {
    const reader = handle orelse return 255;
    const obj = getCurrentObject(reader, object_index) orelse return 255;
    return @intFromEnum(obj.object_type);
}

export fn zfcb_current_object_geometry_count(handle: ?ZfcbReaderHandle, object_index: usize) callconv(.c) usize {
    const reader = handle orelse return 0;
    const obj = getCurrentObject(reader, object_index) orelse return 0;
    return obj.geometries.len;
}

export fn zfcb_current_geometry_type(
    handle: ?ZfcbReaderHandle,
    object_index: usize,
    geometry_index: usize,
) callconv(.c) u8 {
    const reader = handle orelse return 255;
    const geom = getCurrentGeometry(reader, object_index, geometry_index) orelse return 255;
    return @intFromEnum(geom.geometry_type);
}

// Returns 0 on success, -1 on invalid indices/handle.
export fn zfcb_current_geometry_lod(
    handle: ?ZfcbReaderHandle,
    object_index: usize,
    geometry_index: usize,
    out_lod: *[*c]const u8,
    out_len: *usize,
) callconv(.c) c_int {
    out_lod.* = null;
    out_len.* = 0;

    const reader = handle orelse return -1;
    const geom = getCurrentGeometry(reader, object_index, geometry_index) orelse return -1;
    if (geom.lod) |lod| {
        out_lod.* = lod.ptr;
        out_len.* = lod.len;
    }
    return 0;
}

export fn zfcb_current_geometry_surface_count(
    handle: ?ZfcbReaderHandle,
    object_index: usize,
    geometry_index: usize,
) callconv(.c) usize {
    const reader = handle orelse return 0;
    const geom = getCurrentGeometry(reader, object_index, geometry_index) orelse return 0;
    return geom.surfaces.len;
}

export fn zfcb_current_geometry_string_count(
    handle: ?ZfcbReaderHandle,
    object_index: usize,
    geometry_index: usize,
) callconv(.c) usize {
    const reader = handle orelse return 0;
    const geom = getCurrentGeometry(reader, object_index, geometry_index) orelse return 0;
    return geom.strings.len;
}

export fn zfcb_current_geometry_boundary_count(
    handle: ?ZfcbReaderHandle,
    object_index: usize,
    geometry_index: usize,
) callconv(.c) usize {
    const reader = handle orelse return 0;
    const geom = getCurrentGeometry(reader, object_index, geometry_index) orelse return 0;
    return geom.boundaries.len;
}

// Vector pointers remain valid until the next zfcb_next / zfcb_skip_next / destroy.
export fn zfcb_current_geometry_surfaces(
    handle: ?ZfcbReaderHandle,
    object_index: usize,
    geometry_index: usize,
) callconv(.c) [*c]const u32 {
    const reader = handle orelse return null;
    const geom = getCurrentGeometry(reader, object_index, geometry_index) orelse return null;
    if (geom.surfaces.len == 0) return null;
    return geom.surfaces.ptr;
}

export fn zfcb_current_geometry_strings(
    handle: ?ZfcbReaderHandle,
    object_index: usize,
    geometry_index: usize,
) callconv(.c) [*c]const u32 {
    const reader = handle orelse return null;
    const geom = getCurrentGeometry(reader, object_index, geometry_index) orelse return null;
    if (geom.strings.len == 0) return null;
    return geom.strings.ptr;
}

export fn zfcb_current_geometry_boundaries(
    handle: ?ZfcbReaderHandle,
    object_index: usize,
    geometry_index: usize,
) callconv(.c) [*c]const u32 {
    const reader = handle orelse return null;
    const geom = getCurrentGeometry(reader, object_index, geometry_index) orelse return null;
    if (geom.boundaries.len == 0) return null;
    return geom.boundaries.ptr;
}

export fn zfcb_writer_open_from_reader(
    reader_handle: ?ZfcbReaderHandle,
    output_path: [*c]const u8,
) callconv(.c) ?ZfcbWriterHandle {
    const reader = reader_handle orelse return null;
    const output_path_slice = std.mem.span(output_path);

    const writer = c_allocator.create(Writer) catch return null;
    writer.* = Writer.openPathFromReader(reader, output_path_slice) catch {
        c_allocator.destroy(writer);
        return null;
    };
    return writer;
}

// Opens a writer from an existing Unix file descriptor and copies the full
// preamble from reader (including indexes).
// close_on_destroy: non-zero => close(fd) in zfcb_writer_destroy, 0 => leave open.
export fn zfcb_writer_open_from_reader_fd(
    reader_handle: ?ZfcbReaderHandle,
    fd: c_int,
    close_on_destroy: c_int,
) callconv(.c) ?ZfcbWriterHandle {
    const reader = reader_handle orelse return null;
    const file = fileFromFd(fd) orelse return null;

    const writer = c_allocator.create(Writer) catch return null;
    writer.* = Writer.openFileFromReader(reader, file, close_on_destroy != 0) catch {
        c_allocator.destroy(writer);
        return null;
    };
    return writer;
}

export fn zfcb_writer_open_from_reader_no_index(
    reader_handle: ?ZfcbReaderHandle,
    output_path: [*c]const u8,
) callconv(.c) ?ZfcbWriterHandle {
    const reader = reader_handle orelse return null;
    const output_path_slice = std.mem.span(output_path);

    const writer = c_allocator.create(Writer) catch return null;
    writer.* = Writer.openPathFromReaderNoIndex(reader, output_path_slice) catch {
        c_allocator.destroy(writer);
        return null;
    };
    return writer;
}

// Opens a writer from an existing Unix file descriptor and writes a header with
// no spatial/attribute indexes.
// close_on_destroy: non-zero => close(fd) in zfcb_writer_destroy, 0 => leave open.
export fn zfcb_writer_open_from_reader_no_index_fd(
    reader_handle: ?ZfcbReaderHandle,
    fd: c_int,
    close_on_destroy: c_int,
) callconv(.c) ?ZfcbWriterHandle {
    const reader = reader_handle orelse return null;
    const file = fileFromFd(fd) orelse return null;

    const writer = c_allocator.create(Writer) catch return null;
    writer.* = Writer.openFileFromReaderNoIndex(reader, file, close_on_destroy != 0) catch {
        c_allocator.destroy(writer);
        return null;
    };
    return writer;
}

export fn zfcb_writer_open_new_no_index(
    output_path: [*c]const u8,
    scale_x: f64,
    scale_y: f64,
    scale_z: f64,
    translate_x: f64,
    translate_y: f64,
    translate_z: f64,
) callconv(.c) ?ZfcbWriterHandle {
    const output_path_slice = std.mem.span(output_path);
    const writer = c_allocator.create(Writer) catch return null;
    writer.* = Writer.openPathNewNoIndex(
        output_path_slice,
        .{
            .scale = .{ scale_x, scale_y, scale_z },
            .translate = .{ translate_x, translate_y, translate_z },
        },
        EMPTY_COLUMNS,
    ) catch {
        c_allocator.destroy(writer);
        return null;
    };
    return writer;
}

export fn zfcb_writer_destroy(writer_handle: ?ZfcbWriterHandle) callconv(.c) void {
    if (writer_handle) |writer| {
        writer.deinit();
        c_allocator.destroy(writer);
    }
}

// Returns: 1 when a feature was written, 0 at EOF, -1 on error.
export fn zfcb_writer_write_pending_raw(
    reader_handle: ?ZfcbReaderHandle,
    writer_handle: ?ZfcbWriterHandle,
) callconv(.c) c_int {
    const reader = reader_handle orelse return -1;
    const writer = writer_handle orelse return -1;

    const has_pending = reader.ensurePending() catch return -1;
    if (!has_pending) return 0;

    writer.writeFeatureRaw(reader.feature_buf.items) catch return -1;
    reader.pending_loaded = false;
    return 1;
}

// Returns 0 on success, -1 on error.
export fn zfcb_writer_write_current_raw(
    reader_handle: ?ZfcbReaderHandle,
    writer_handle: ?ZfcbWriterHandle,
) callconv(.c) c_int {
    const reader = reader_handle orelse return -1;
    const writer = writer_handle orelse return -1;
    if (reader.feature_buf.items.len < 4) return -1;
    writer.writeFeatureRaw(reader.feature_buf.items) catch return -1;
    return 0;
}

// Writes a complete size-prefixed feature payload (4-byte length + feature bytes).
// Returns 0 on success, -1 on error.
export fn zfcb_writer_write_feature_raw_bytes(
    writer_handle: ?ZfcbWriterHandle,
    feature_bytes: [*c]const u8,
    feature_len: usize,
) callconv(.c) c_int {
    const writer = writer_handle orelse return -1;
    if (feature_bytes == null or feature_len < 4) return -1;
    writer.writeFeatureRaw(feature_bytes[0..feature_len]) catch return -1;
    return 0;
}

// Replaces feature vertices and the target Solid/LoD2.2 geometry for object "<feature_id>-0".
// triangle_indices is a flat triangle index list (multiple of 3).
// Returns 0 on success, -1 on error.
// NOTE: This changes the feature byte length, invalidating spatial/attribute indexes.
// Use zfcb_writer_open_from_reader_no_index to create the writer.
export fn zfcb_writer_write_current_replaced_lod22(
    reader_handle: ?ZfcbReaderHandle,
    writer_handle: ?ZfcbWriterHandle,
    feature_id_ptr: [*c]const u8,
    feature_id_len: usize,
    vertices_xyz_world_ptr: [*c]const f64,
    vertex_count: usize,
    triangle_indices_ptr: [*c]const u32,
    triangle_index_count: usize,
    semantic_types_ptr: [*c]const u8,
    semantic_types_count: usize,
) callconv(.c) c_int {
    const reader = reader_handle orelse return -1;
    const writer = writer_handle orelse return -1;
    if (feature_id_ptr == null or feature_id_len == 0) return -1;
    if (vertices_xyz_world_ptr == null or vertex_count == 0) return -1;
    if (triangle_indices_ptr == null or triangle_index_count == 0 or triangle_index_count % 3 != 0) return -1;
    if (semantic_types_ptr == null or semantic_types_count != triangle_index_count / 3) return -1;

    const feature_id = feature_id_ptr[0..feature_id_len];
    const vertices_xyz_world = vertices_xyz_world_ptr[0 .. vertex_count * 3];
    const triangle_indices = triangle_indices_ptr[0..triangle_index_count];
    const semantic_types = semantic_types_ptr[0..semantic_types_count];

    var builder = FeatureBuilder.init(c_allocator, reader.transform);
    defer builder.deinit();
    builder.loadCurrentFromReader(reader) catch return -1;
    builder.replaceLod22Solid(feature_id, vertices_xyz_world, triangle_indices, semantic_types) catch return -1;

    var rewritten_feature = std.ArrayList(u8){};
    defer rewritten_feature.deinit(c_allocator);
    builder.encodeFeature(&rewritten_feature) catch return -1;
    writer.writeFeatureRaw(rewritten_feature.items) catch return -1;
    return 0;
}

fn openSampleReader(allocator: std.mem.Allocator) !Reader {
    const candidates = [_][]const u8{
        "../sample_data/9-444-728.fcb",
        "sample_data/9-444-728.fcb",
    };

    for (candidates) |path| {
        const reader = Reader.openPath(allocator, path) catch |err| switch (err) {
            error.FileNotFound => continue,
            else => return err,
        };
        return reader;
    }
    return error.FileNotFound;
}

fn buildSyntheticFeatureBuilder(
    allocator: std.mem.Allocator,
    transform: Transform,
    include_unused_vertices: bool,
) !FeatureBuilder {
    var builder = FeatureBuilder.init(allocator, transform);
    errdefer builder.deinit();

    builder.feature_id = "synthetic-feature";
    builder.has_vertices = true;
    const vertex_count: usize = if (include_unused_vertices) 5 else 3;
    builder.vertices_q = try allocator.alloc(QuantizedVertex, vertex_count);
    builder.vertices_q[0] = .{ .x = 0, .y = 0, .z = 0 };
    builder.vertices_q[1] = .{ .x = 10, .y = 0, .z = 0 };
    builder.vertices_q[2] = .{ .x = 0, .y = 10, .z = 0 };
    if (include_unused_vertices) {
        builder.vertices_q[3] = .{ .x = 50, .y = 50, .z = 10 };
        builder.vertices_q[4] = .{ .x = 100, .y = 100, .z = 20 };
    }

    builder.has_objects = true;
    builder.objects = try allocator.alloc(FeatureObjectData, 1);
    builder.objects[0] = .{
        .id = "synthetic-feature-0",
        .object_type = .Building,
        .extension_type = null,
        .geometries = try allocator.alloc(FeatureGeometryData, 1),
        .has_geometries = true,
        .attributes_raw = EMPTY_U8,
        .has_attributes = false,
        .columns = EMPTY_COLUMNS,
        .has_columns = false,
        .children = EMPTY_STRINGS,
        .has_children = false,
        .children_roles = EMPTY_STRINGS,
        .has_children_roles = false,
        .parents = EMPTY_STRINGS,
        .has_parents = false,
    };

    const solids = try allocator.alloc(u32, 1);
    solids[0] = 1;
    const shells = try allocator.alloc(u32, 1);
    shells[0] = 1;
    const surfaces = try allocator.alloc(u32, 1);
    surfaces[0] = 1;
    const strings = try allocator.alloc(u32, 1);
    strings[0] = 3;
    const boundaries = try allocator.alloc(u32, 3);
    boundaries[0] = 0;
    boundaries[1] = 1;
    boundaries[2] = 2;
    const semantics = try allocator.alloc(u32, 1);
    semantics[0] = 0;
    const semantics_objects = try allocator.alloc(u8, 1);
    semantics_objects[0] = 2;

    builder.objects[0].geometries[0] = .{
        .geometry_type = .Solid,
        .lod = "2.2",
        .solids = solids,
        .has_solids = true,
        .shells = shells,
        .has_shells = true,
        .surfaces = surfaces,
        .has_surfaces = true,
        .strings = strings,
        .has_strings = true,
        .boundaries = boundaries,
        .has_boundaries = true,
        .semantics = semantics,
        .has_semantics = true,
        .semantics_objects = semantics_objects,
        .has_semantics_objects = true,
    };

    return builder;
}

test "stream fcb with peek and next" {
    var reader = try openSampleReader(std.testing.allocator);
    defer reader.deinit();

    try std.testing.expect(reader.featureCount() > 0);

    const peeked_id = (try reader.peekNextId()).?;
    try std.testing.expect(peeked_id.len > 0);

    const first = (try reader.next()).?;
    try std.testing.expectEqualStrings(peeked_id, first.id);
    try std.testing.expect(first.objects.len > 0);
    try std.testing.expect(first.vertices.len > 0);

    const first_object = first.objects[0];
    try std.testing.expect(first_object.geometries.len > 0);
}

test "skip next feature by id" {
    var reader = try openSampleReader(std.testing.allocator);
    defer reader.deinit();

    const first_id = (try reader.peekNextId()).?;
    const first_id_copy = try std.testing.allocator.dupe(u8, first_id);
    defer std.testing.allocator.free(first_id_copy);
    try std.testing.expect(try reader.skipNext());

    const second_id = (try reader.peekNextId()).?;
    try std.testing.expect(second_id.len > 0);
    try std.testing.expect(!std.mem.eql(u8, first_id_copy, second_id));
}

test "stream all features and aggregate geometry safely" {
    var reader = try openSampleReader(std.testing.allocator);
    defer reader.deinit();

    var feature_count: u64 = 0;
    var object_count: u64 = 0;
    var geometry_count: u64 = 0;
    var attribute_count: u64 = 0;
    var ring_count: u64 = 0;
    var boundary_index_count: u64 = 0;

    while (try reader.next()) |feature| {
        feature_count += 1;
        object_count += @intCast(feature.objects.len);

        for (feature.objects) |obj| {
            geometry_count += @intCast(obj.geometries.len);
            attribute_count += @intCast(obj.attributes.len);
            for (obj.geometries) |geom| {
                ring_count += @intCast(geom.ringCount());
                boundary_index_count += @intCast(geom.boundaries.len);
            }
        }
    }

    try std.testing.expectEqual(reader.featureCount(), feature_count);
    try std.testing.expect(object_count > 0);
    try std.testing.expect(geometry_count > 0);
    try std.testing.expect(ring_count > 0);
    try std.testing.expect(boundary_index_count > 0);
    // Dataset-specific sanity check from sample_data/9-444-728.fcb.
    try std.testing.expectEqual(@as(u64, 6057), object_count);
    try std.testing.expect(attribute_count > 0);
}

test "feature builder encode/decode preserves geometry semantics" {
    var builder = try buildSyntheticFeatureBuilder(std.testing.allocator, .{}, false);
    defer builder.deinit();

    var feature_bytes = std.ArrayList(u8){};
    defer feature_bytes.deinit(std.testing.allocator);
    try builder.encodeFeature(&feature_bytes);

    var path_buf: [256]u8 = undefined;
    const path = try std.fmt.bufPrint(
        &path_buf,
        "/tmp/zfcb_semantics_roundtrip_{d}.fcb",
        .{std.time.milliTimestamp()},
    );
    defer std.fs.deleteFileAbsolute(path) catch {};

    var writer = try Writer.openPathNewNoIndex(path, .{}, EMPTY_COLUMNS);
    try writer.writeFeatureRaw(feature_bytes.items);
    writer.deinit();

    var reader = try Reader.openPath(std.testing.allocator, path);
    defer reader.deinit();

    try std.testing.expectEqual(@as(u64, 1), reader.featureCount());
    const feature = (try reader.next()).?;
    try std.testing.expectEqual(@as(usize, 1), feature.objects.len);
    try std.testing.expectEqual(@as(usize, 1), feature.objects[0].geometries.len);
    const geom = feature.objects[0].geometries[0];
    try std.testing.expectEqual(@as(usize, 1), geom.semantics.len);
    try std.testing.expectEqual(@as(usize, 1), geom.semantics_objects.len);
    try std.testing.expectEqual(@as(u32, 0), geom.semantics[0]);
    try std.testing.expectEqual(@as(u8, 2), geom.semantics_objects[0]);
}

test "feature builder replace lod22 compacts unused vertices" {
    var builder = try buildSyntheticFeatureBuilder(std.testing.allocator, .{}, true);
    defer builder.deinit();

    const replacement_vertices = [_]f64{
        0, 0, 0,
        10, 0, 0,
        0, 10, 0,
        0, 10, 0, // duplicate
        99, 99, 99, // unused
    };
    const replacement_triangles = [_]u32{ 0, 1, 2, 0, 2, 3 };
    const replacement_semantics = [_]u8{ 1, 2 };

    try builder.replaceLod22Solid(
        "synthetic-feature",
        &replacement_vertices,
        &replacement_triangles,
        &replacement_semantics,
    );

    const geom = builder.objects[0].geometries[0];
    try std.testing.expectEqual(@as(usize, 2), geom.semantics.len);
    try std.testing.expectEqual(@as(usize, 2), geom.semantics_objects.len);

    const used = try std.testing.allocator.alloc(bool, builder.vertices_q.len);
    defer std.testing.allocator.free(used);
    @memset(used, false);
    for (builder.objects) |obj| {
        for (obj.geometries) |g| {
            if (!g.has_boundaries) continue;
            for (g.boundaries) |idx| {
                used[idx] = true;
            }
        }
    }
    for (used) |u| {
        try std.testing.expect(u);
    }
}

test "feature builder encoded tables are aligned" {
    var builder = try buildSyntheticFeatureBuilder(std.testing.allocator, .{}, false);
    defer builder.deinit();

    var feature_bytes = std.ArrayList(u8){};
    defer feature_bytes.deinit(std.testing.allocator);
    try builder.encodeFeature(&feature_bytes);

    const feature_table = try fb.sizePrefixedRootTable(feature_bytes.items);
    try std.testing.expectEqual(@as(usize, 0), feature_table & 3);

    const objects_vec = (try fb.getVectorInfo(feature_bytes.items, feature_table, VT_FEATURE_OBJECTS)).?;
    for (0..objects_vec.len) |obj_i| {
        const obj_table = try fb.vectorTableAt(feature_bytes.items, objects_vec, obj_i);
        try std.testing.expectEqual(@as(usize, 0), obj_table & 3);

        if (try fb.getVectorInfo(feature_bytes.items, obj_table, VT_OBJECT_GEOMETRY)) |geom_vec| {
            for (0..geom_vec.len) |geom_i| {
                const geom_table = try fb.vectorTableAt(feature_bytes.items, geom_vec, geom_i);
                try std.testing.expectEqual(@as(usize, 0), geom_table & 3);
            }
        }
    }
}

test "feature builder preserves object parent child links" {
    var reader = try openSampleReader(std.testing.allocator);
    defer reader.deinit();
    _ = (try reader.next()) orelse return error.MissingRequiredField;

    var builder = FeatureBuilder.init(std.testing.allocator, reader.transform);
    defer builder.deinit();
    try builder.loadCurrentFromReader(&reader);

    var feature_bytes = std.ArrayList(u8){};
    defer feature_bytes.deinit(std.testing.allocator);
    try builder.encodeFeature(&feature_bytes);

    const feature_table = try fb.sizePrefixedRootTable(feature_bytes.items);
    const objects_vec = (try fb.getVectorInfo(feature_bytes.items, feature_table, VT_FEATURE_OBJECTS)) orelse {
        return error.MissingRequiredField;
    };

    var found_children = false;
    var found_parents = false;
    for (0..objects_vec.len) |obj_i| {
        const obj_table = try fb.vectorTableAt(feature_bytes.items, objects_vec, obj_i);
        const obj_id = try fb.getRequiredString(feature_bytes.items, obj_table, VT_OBJECT_ID);

        if (std.mem.endsWith(u8, obj_id, "-0")) {
            if (try fb.getVectorInfo(feature_bytes.items, obj_table, VT_OBJECT_PARENTS)) |parents_vec| {
                if (parents_vec.len > 0) found_parents = true;
            }
        } else {
            if (try fb.getVectorInfo(feature_bytes.items, obj_table, VT_OBJECT_CHILDREN)) |children_vec| {
                if (children_vec.len > 0) found_children = true;
            }
        }
    }

    try std.testing.expect(found_children);
    try std.testing.expect(found_parents);
}

test "writer open new no index patches feature count on close" {
    var builder = try buildSyntheticFeatureBuilder(std.testing.allocator, .{}, false);
    defer builder.deinit();

    var path_buf: [256]u8 = undefined;
    const path = try std.fmt.bufPrint(
        &path_buf,
        "/tmp/zfcb_new_writer_{d}.fcb",
        .{std.time.milliTimestamp()},
    );
    defer std.fs.deleteFileAbsolute(path) catch {};

    var writer = try Writer.openPathNewNoIndex(path, .{}, EMPTY_COLUMNS);
    try writer.writeFeatureBuilt(std.testing.allocator, &builder);
    try writer.writeFeatureBuilt(std.testing.allocator, &builder);
    writer.deinit();

    var reader = try Reader.openPath(std.testing.allocator, path);
    defer reader.deinit();
    try std.testing.expectEqual(@as(u64, 2), reader.featureCount());

    var streamed_count: u64 = 0;
    while (try reader.next()) |_| {
        streamed_count += 1;
    }
    try std.testing.expectEqual(@as(u64, 2), streamed_count);
}
