const std = @import("std");

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
const VT_OBJECT_GEOMETRY: u16 = 12;
const VT_OBJECT_ATTRIBUTES: u16 = 16;
const VT_OBJECT_COLUMNS: u16 = 18;

const VT_GEOMETRY_TYPE: u16 = 4;
const VT_GEOMETRY_LOD: u16 = 6;
const VT_GEOMETRY_SOLIDS: u16 = 8;
const VT_GEOMETRY_SHELLS: u16 = 10;
const VT_GEOMETRY_SURFACES: u16 = 12;
const VT_GEOMETRY_STRINGS: u16 = 14;
const VT_GEOMETRY_BOUNDARIES: u16 = 16;

const NODE_ITEM_SIZE_BYTES: u64 = 40;

const EMPTY_COLUMNS: []const ColumnSchema = &[_]ColumnSchema{};
const EMPTY_OBJECTS: []const ObjectView = &[_]ObjectView{};
const EMPTY_VERTICES: []const [3]f64 = &[_][3]f64{};
const EMPTY_U32: []const u32 = &[_]u32{};

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

    transform: Transform = .{},
    feature_count: u64 = 0,

    header_buf: []u8 = &[_]u8{},
    owns_header_buf: bool = false,
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

        var reader = Reader{
            .allocator = allocator,
            .file = file,
        };
        errdefer reader.deinit();
        try reader.readHeader();
        return reader;
    }

    pub fn deinit(self: *Reader) void {
        self.file.close();

        self.feature_buf.deinit(self.allocator);
        self.scratch_vertices.deinit(self.allocator);
        self.scratch_objects.deinit(self.allocator);
        self.scratch_geometries.deinit(self.allocator);
        self.scratch_attributes.deinit(self.allocator);
        self.scratch_columns.deinit(self.allocator);
        self.scratch_column_types.deinit(self.allocator);
        self.scratch_u32.deinit(self.allocator);

        if (self.pending_id_owned) |id| self.allocator.free(id);
        if (self.owns_root_columns) self.allocator.free(self.root_columns);
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
        try skipBytes(&self.file, to_skip);
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

        const feature_table = try fb.sizePrefixedRootTable(self.feature_buf.items);
        const feature_id = try fb.getRequiredString(self.feature_buf.items, feature_table, VT_FEATURE_ID);

        const vertex_count = try self.countFeatureVertices(feature_table);
        const totals = try self.countFeatureObjectData(feature_table);
        try self.scratch_vertices.ensureTotalCapacity(self.allocator, vertex_count);
        try self.scratch_objects.ensureTotalCapacity(self.allocator, totals.object_count);
        try self.scratch_geometries.ensureTotalCapacity(self.allocator, totals.geometry_count);
        try self.scratch_attributes.ensureTotalCapacity(self.allocator, totals.attribute_count);
        try self.scratch_u32.ensureTotalCapacity(self.allocator, totals.u32_count);

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
        }) |field| {
            if (try fb.getVectorInfo(self.feature_buf.items, geom_table, field)) |vec| {
                totals.u32_count = try checkedAdd(totals.u32_count, vec.len);
            }
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

        try self.scratch_geometries.append(self.allocator, .{
            .geometry_type = geometry_type,
            .lod = lod,
            .solids = solids,
            .shells = shells,
            .surfaces = surfaces,
            .strings = strings,
            .boundaries = boundaries,
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

// =============================================================================
// C API exports
// =============================================================================

var c_allocator: std.mem.Allocator = std.heap.c_allocator;

pub const ZfcbReaderHandle = *Reader;

fn getCurrentObject(reader: *Reader, object_index: usize) ?*const ObjectView {
    if (object_index >= reader.current_feature.objects.len) return null;
    return &reader.current_feature.objects[object_index];
}

fn getCurrentGeometry(reader: *Reader, object_index: usize, geometry_index: usize) ?*const GeometryView {
    const obj = getCurrentObject(reader, object_index) orelse return null;
    if (geometry_index >= obj.geometries.len) return null;
    return &obj.geometries[geometry_index];
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
