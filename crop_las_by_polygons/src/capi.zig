const std = @import("std");
const pip = @import("ptinpoly.zig");

pub export fn zp_polygon_create(vertices_ptr: ?[*]const pip.Point, vertex_count: usize, resolution: usize) ?*pip.PreparedPolygon {
    const ptr = vertices_ptr orelse return null;
    if (vertex_count < 3) return null;

    const polygon = std.heap.c_allocator.create(pip.PreparedPolygon) catch return null;
    polygon.* = pip.PreparedPolygon.init(std.heap.c_allocator, ptr[0..vertex_count], resolution) catch {
        std.heap.c_allocator.destroy(polygon);
        return null;
    };
    return polygon;
}

pub export fn zp_polygon_destroy(polygon: ?*pip.PreparedPolygon) void {
    const handle = polygon orelse return;
    handle.deinit();
    std.heap.c_allocator.destroy(handle);
}

pub export fn zp_polygon_contains(polygon: ?*const pip.PreparedPolygon, x: f64, y: f64) c_int {
    const handle = polygon orelse return -1;
    return if (handle.contains(.{ .x = x, .y = y })) 1 else 0;
}

pub export fn zp_polygon_contains_many(
    polygon: ?*const pip.PreparedPolygon,
    xs_ptr: ?[*]const f64,
    ys_ptr: ?[*]const f64,
    count: usize,
    out_ptr: ?[*]u8,
) c_int {
    const handle = polygon orelse return -1;
    const xs = xs_ptr orelse return -1;
    const ys = ys_ptr orelse return -1;
    const out = out_ptr orelse return -1;

    for (0..count) |i| {
        out[i] = @intFromBool(handle.contains(.{ .x = xs[i], .y = ys[i] }));
    }

    return 0;
}

pub export fn zp_polygon_contains_indexed(
    polygon: ?*const pip.PreparedPolygon,
    xs_ptr: ?[*]const f64,
    ys_ptr: ?[*]const f64,
    idx_ptr: ?[*]const usize,
    count: usize,
    out_ptr: ?[*]u8,
) c_int {
    const handle = polygon orelse return -1;
    if (count == 0) return 0;

    const xs = xs_ptr orelse return -1;
    const ys = ys_ptr orelse return -1;
    const idx = idx_ptr orelse return -1;
    const out = out_ptr orelse return -1;

    for (0..count) |i| {
        const j = idx[i];
        out[i] = @intFromBool(handle.contains(.{ .x = xs[j], .y = ys[j] }));
    }

    return 0;
}
