const std = @import("std");
const zfcb = @import("zfcb.zig");

const object_type_names = [_][]const u8{
    "Bridge",
    "BridgePart",
    "BridgeInstallation",
    "BridgeConstructiveElement",
    "BridgeRoom",
    "BridgeFurniture",
    "Building",
    "BuildingPart",
    "BuildingInstallation",
    "BuildingConstructiveElement",
    "BuildingFurniture",
    "BuildingStorey",
    "BuildingRoom",
    "BuildingUnit",
    "CityFurniture",
    "CityObjectGroup",
    "GenericCityObject",
    "LandUse",
    "OtherConstruction",
    "PlantCover",
    "SolitaryVegetationObject",
    "TINRelief",
    "Road",
    "Railway",
    "Waterway",
    "TransportSquare",
    "Tunnel",
    "TunnelPart",
    "TunnelInstallation",
    "TunnelConstructiveElement",
    "TunnelHollowSpace",
    "TunnelFurniture",
    "WaterBody",
    "ExtensionObject",
};

const geometry_type_names = [_][]const u8{
    "MultiPoint",
    "MultiLineString",
    "MultiSurface",
    "CompositeSurface",
    "Solid",
    "MultiSolid",
    "CompositeSolid",
    "GeometryInstance",
};

const OpenedReader = struct {
    reader: zfcb.Reader,
    path: []const u8,
};

const Stats = struct {
    features: u64 = 0,
    objects: u64 = 0,
    geometries: u64 = 0,
    vertices: u64 = 0,
    attributes: u64 = 0,
    rings: u64 = 0,
    boundary_indices: u64 = 0,

    min: [3]f64 = .{ std.math.inf(f64), std.math.inf(f64), std.math.inf(f64) },
    max: [3]f64 = .{ -std.math.inf(f64), -std.math.inf(f64), -std.math.inf(f64) },
    has_bbox: bool = false,
};

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();

    const args = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, args);

    if (args.len > 2) {
        const exe = args[0];
        std.debug.print("Usage: {s} [path/to/file.fcb]\n", .{exe});
        return error.InvalidArguments;
    }

    var opened = try openReader(allocator, if (args.len == 2) args[1] else null);
    defer opened.reader.deinit();

    var stdout_buf: [4096]u8 = undefined;
    var stdout_writer = std.fs.File.stdout().writer(&stdout_buf);
    const out = &stdout_writer.interface;

    var stats: Stats = .{};
    var object_counts: [256]u64 = [_]u64{0} ** 256;
    var geometry_counts: [256]u64 = [_]u64{0} ** 256;
    while (try opened.reader.next()) |feature| {
        stats.features += 1;
        if (stats.features == 1) {
            try printFirstFeatureDetail(out, feature);
        }
        stats.vertices += @intCast(feature.vertices.len);

        for (feature.vertices) |v| {
            stats.has_bbox = true;
            inline for (0..3) |i| {
                if (v[i] < stats.min[i]) stats.min[i] = v[i];
                if (v[i] > stats.max[i]) stats.max[i] = v[i];
            }
        }

        for (feature.objects) |obj| {
            stats.objects += 1;

            const obj_idx: usize = @intFromEnum(obj.object_type);
            object_counts[obj_idx] += 1;

            stats.attributes += @intCast(obj.attributes.len);
            stats.geometries += @intCast(obj.geometries.len);
            for (obj.geometries) |geom| {
                const geom_idx: usize = @intFromEnum(geom.geometry_type);
                geometry_counts[geom_idx] += 1;
                stats.rings += @intCast(geom.ringCount());
                stats.boundary_indices += @intCast(geom.boundaries.len);
            }
        }
    }

    try out.print("FlatCityBuf summary\n", .{});
    try out.print("  file: {s}\n", .{opened.path});
    try out.print("  header.declared_features: {d}\n", .{opened.reader.featureCount()});
    try out.print("  header.root_columns: {d}\n", .{opened.reader.rootColumns().len});
    try out.print("  streamed.features: {d}\n", .{stats.features});
    try out.print("  streamed.objects: {d}\n", .{stats.objects});
    try out.print("  streamed.geometries: {d}\n", .{stats.geometries});
    try out.print("  streamed.vertices: {d}\n", .{stats.vertices});
    try out.print("  streamed.attributes: {d}\n", .{stats.attributes});
    try out.print("  streamed.rings: {d}\n", .{stats.rings});
    try out.print("  streamed.boundary_indices: {d}\n", .{stats.boundary_indices});

    if (stats.has_bbox) {
        try out.print(
            "  bbox.min: [{d:.3}, {d:.3}, {d:.3}]\n",
            .{ stats.min[0], stats.min[1], stats.min[2] },
        );
        try out.print(
            "  bbox.max: [{d:.3}, {d:.3}, {d:.3}]\n",
            .{ stats.max[0], stats.max[1], stats.max[2] },
        );
    } else {
        try out.print("  bbox: (none)\n", .{});
    }

    try out.print("\nObject types:\n", .{});
    for (object_counts, 0..) |count, idx| {
        if (count == 0) continue;
        const name = if (idx < object_type_names.len) object_type_names[idx] else "UnknownObjectType";
        try out.print("  {s}: {d}\n", .{ name, count });
    }

    try out.print("\nGeometry types:\n", .{});
    for (geometry_counts, 0..) |count, idx| {
        if (count == 0) continue;
        const name = if (idx < geometry_type_names.len) geometry_type_names[idx] else "UnknownGeometryType";
        try out.print("  {s}: {d}\n", .{ name, count });
    }

    try out.flush();
}

fn printFirstFeatureDetail(out: anytype, feature: *const zfcb.FeatureView) !void {
    try out.print("First feature detail\n", .{});
    try out.print("  id: {s}\n", .{feature.id});
    try out.print("  vertices: {d}\n", .{feature.vertices.len});
    try out.print("  objects: {d}\n", .{feature.objects.len});

    for (feature.objects, 0..) |obj, object_idx| {
        try out.print(
            "  object[{d}] id={s} type={s}\n",
            .{ object_idx, obj.id, objectTypeName(obj.object_type) },
        );
        if (obj.extension_type) |ext_type| {
            try out.print("    extension_type: {s}\n", .{ext_type});
        }

        try out.print("    attributes ({d}):\n", .{obj.attributes.len});
        if (obj.attributes.len == 0) {
            try out.print("      (none)\n", .{});
        } else {
            for (obj.attributes) |attr| {
                try out.print("      {s} = ", .{attr.name});
                try printAttributeValue(out, attr.value);
                try out.print("\n", .{});
            }
        }

        try out.print("    geometries ({d}):\n", .{obj.geometries.len});
        if (obj.geometries.len == 0) {
            try out.print("      (none)\n", .{});
        } else {
            for (obj.geometries, 0..) |geom, geom_idx| {
                const lod = geom.lod orelse "-";
                const ring_stats = summarizeRings(geom);
                try out.print(
                    "      [{d}] type={s} lod={s} solids={d} shells={d} surfaces={d} strings={d} boundaries={d} rings={d}",
                    .{
                        geom_idx,
                        geometryTypeName(geom.geometry_type),
                        lod,
                        geom.solids.len,
                        geom.shells.len,
                        geom.surfaces.len,
                        geom.strings.len,
                        geom.boundaries.len,
                        geom.ringCount(),
                    },
                );
                if (ring_stats.count > 0) {
                    try out.print(
                        " ring_size[min={d}, max={d}, avg={d:.2}]",
                        .{ ring_stats.min, ring_stats.max, ring_stats.avg },
                    );
                }
                try out.print("\n", .{});
            }
        }
    }
    try out.print("\n", .{});
}

const RingSummary = struct {
    count: usize,
    min: usize,
    max: usize,
    avg: f64,
};

fn summarizeRings(geom: zfcb.GeometryView) RingSummary {
    if (geom.strings.len == 0) {
        return .{ .count = 0, .min = 0, .max = 0, .avg = 0.0 };
    }

    var min_val: usize = std.math.maxInt(usize);
    var max_val: usize = 0;
    var sum: usize = 0;
    for (geom.strings) |n| {
        if (n < min_val) min_val = n;
        if (n > max_val) max_val = n;
        sum += n;
    }
    return .{
        .count = geom.strings.len,
        .min = min_val,
        .max = max_val,
        .avg = @as(f64, @floatFromInt(sum)) / @as(f64, @floatFromInt(geom.strings.len)),
    };
}

fn printAttributeValue(out: anytype, value: zfcb.AttributeValue) !void {
    switch (value) {
        .byte => |v| try out.print("{d}", .{v}),
        .ubyte => |v| try out.print("{d}", .{v}),
        .bool => |v| try out.print("{}", .{v}),
        .short => |v| try out.print("{d}", .{v}),
        .ushort => |v| try out.print("{d}", .{v}),
        .int => |v| try out.print("{d}", .{v}),
        .uint => |v| try out.print("{d}", .{v}),
        .long => |v| try out.print("{d}", .{v}),
        .ulong => |v| try out.print("{d}", .{v}),
        .float => |v| try out.print("{d}", .{v}),
        .double => |v| try out.print("{d}", .{v}),
        .string => |v| try out.print("{s}", .{v}),
        .json => |v| try out.print("{s}", .{v}),
        .datetime => |v| try out.print("{s}", .{v}),
        .binary => |v| {
            const preview_len: usize = @min(v.len, 16);
            try out.print("<binary len={d} hex=", .{v.len});
            for (v[0..preview_len]) |b| {
                try out.print("{x:0>2}", .{b});
            }
            if (v.len > preview_len) try out.print("...", .{});
            try out.print(">", .{});
        },
    }
}

fn objectTypeName(object_type: zfcb.ObjectType) []const u8 {
    const idx: usize = @intFromEnum(object_type);
    return if (idx < object_type_names.len) object_type_names[idx] else "UnknownObjectType";
}

fn geometryTypeName(geometry_type: zfcb.GeometryType) []const u8 {
    const idx: usize = @intFromEnum(geometry_type);
    return if (idx < geometry_type_names.len) geometry_type_names[idx] else "UnknownGeometryType";
}

fn openReader(allocator: std.mem.Allocator, maybe_path: ?[]const u8) !OpenedReader {
    if (maybe_path) |path| {
        return .{
            .reader = try zfcb.Reader.openPath(allocator, path),
            .path = path,
        };
    }

    const defaults = [_][]const u8{
        "sample_data/9-444-728.fcb",
        "../sample_data/9-444-728.fcb",
    };

    for (defaults) |path| {
        const reader = zfcb.Reader.openPath(allocator, path) catch |err| switch (err) {
            error.FileNotFound => continue,
            else => return err,
        };
        return .{
            .reader = reader,
            .path = path,
        };
    }

    return error.FileNotFound;
}
