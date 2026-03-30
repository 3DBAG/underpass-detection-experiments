const std = @import("std");
const ptinpoly = @import("ptinpoly.zig");
const Point = ptinpoly.Point;
const PreparedPolygon = ptinpoly.PreparedPolygon;

/// Crossings-multiply reference implementation matching the C baseline.
fn naiveContains(vertices: []const Point, point: Point) bool {
    const tx = point.x;
    const ty = point.y;

    var inside = false;
    var previous = vertices[vertices.len - 1];
    var yflag0 = previous.y >= ty;

    for (vertices) |current| {
        const yflag1 = current.y >= ty;
        if (yflag0 != yflag1) {
            const lhs = (current.y - ty) * (previous.x - current.x);
            const rhs = (current.x - tx) * (previous.y - current.y);
            if ((lhs >= rhs) == yflag1) inside = !inside;
        }

        yflag0 = yflag1;
        previous = current;
    }

    return inside;
}

/// Star polygon with `n_tips` arms, alternating between outer_r and inner_r.
fn buildStar(allocator: std.mem.Allocator, n_tips: usize, outer_r: f64, inner_r: f64) ![]Point {
    const n = n_tips * 2;
    const pts = try allocator.alloc(Point, n);
    for (0..n) |i| {
        const angle = std.math.pi * 2.0 * @as(f64, @floatFromInt(i)) / @as(f64, @floatFromInt(n)) - std.math.pi / 2.0;
        const r = if (i % 2 == 0) outer_r else inner_r;
        pts[i] = .{ .x = r * @cos(angle), .y = r * @sin(angle) };
    }
    return pts;
}

const BenchCase = struct {
    name: []const u8,
    polygon: []const Point,
};

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();

    const stdout = std.fs.File.stdout().deprecatedWriter();

    const N: usize = 1_000_000;

    // Generate fixed random query points in [-1.2, 1.2]^2.
    var prng = std.Random.DefaultPrng.init(0xdeadbeef);
    const rng = prng.random();

    const xs = try allocator.alloc(f64, N);
    defer allocator.free(xs);
    const ys = try allocator.alloc(f64, N);
    defer allocator.free(ys);

    for (xs, ys) |*x, *y| {
        x.* = rng.float(f64) * 2.4 - 1.2;
        y.* = rng.float(f64) * 2.4 - 1.2;
    }

    const square = [_]Point{
        .{ .x = -1.0, .y = -1.0 },
        .{ .x = 1.0, .y = -1.0 },
        .{ .x = 1.0, .y = 1.0 },
        .{ .x = -1.0, .y = 1.0 },
    };

    const star10 = try buildStar(allocator, 10, 1.0, 0.45);
    defer allocator.free(star10);
    const star100 = try buildStar(allocator, 100, 1.0, 0.45);
    defer allocator.free(star100);
    const star500 = try buildStar(allocator, 500, 1.0, 0.45);
    defer allocator.free(star500);

    const cases = [_]BenchCase{
        .{ .name = "square (4 edges)", .polygon = &square },
        .{ .name = "star (20 edges)", .polygon = star10 },
        .{ .name = "star (200 edges)", .polygon = star100 },
        .{ .name = "star (1000 edges)", .polygon = star500 },
    };

    try stdout.print("Benchmarking {d} queries per case\n", .{N});
    try stdout.print("{s:<24} {s:<18} {s:>14}  {s:>10}  {s}\n", .{
        "polygon", "strategy", "ns/query", "prep (us)", "inside",
    });
    try stdout.print("{s}\n", .{"-" ** 86});

    for (cases) |c| {
        // ---- naive ----
        {
            var timer = try std.time.Timer.start();
            var hits: u64 = 0;
            for (0..N) |i| {
                if (naiveContains(c.polygon, .{ .x = xs[i], .y = ys[i] })) hits += 1;
            }
            const ns = timer.read();
            try stdout.print("{s:<24} {s:<18} {d:>14.1}  {s:>10}  {d}\n", .{
                c.name, "naive", nsPerQuery(ns, N), "-", hits,
            });
        }

        // ---- grid, several resolutions ----
        inline for (.{ 4, 8, 16, 32, 64, 128 }) |res| {
            var prep_timer = try std.time.Timer.start();
            var prepared = try PreparedPolygon.init(allocator, c.polygon, res);
            const prep_ns = prep_timer.read();
            defer prepared.deinit();

            // warm-up pass (avoids cold-cache bias on first timing)
            var warmup: u64 = 0;
            for (0..N / 10) |i| {
                if (prepared.contains(.{ .x = xs[i], .y = ys[i] })) warmup += 1;
            }
            if (warmup > N) unreachable; // prevent optimization

            var timer = try std.time.Timer.start();
            var hits: u64 = 0;
            for (0..N) |i| {
                if (prepared.contains(.{ .x = xs[i], .y = ys[i] })) hits += 1;
            }
            const ns = timer.read();
            const label = std.fmt.comptimePrint("grid res={d}", .{res});
            try stdout.print("{s:<24} {s:<18} {d:>14.1}  {d:>10.1}  {d}\n", .{
                "", label, nsPerQuery(ns, N), @as(f64, @floatFromInt(prep_ns)) / 1000.0, hits,
            });
        }

        try stdout.print("\n", .{});
    }
}

fn nsPerQuery(total_ns: u64, n: usize) f64 {
    return @as(f64, @floatFromInt(total_ns)) / @as(f64, @floatFromInt(n));
}
