const std = @import("std");

pub const Point = extern struct {
    x: f64,
    y: f64,
};

// SIMD vector length for edge processing.
const VL = 4;
const Vf = @Vector(VL, f64);
const Vu1 = @Vector(VL, u1);
const Vu32 = @Vector(VL, u32);

/// Grid cell: 16 bytes (matches the C original), so 4 cells fit per cache line.
/// SoA edge buffer laid out as N_FIELDS contiguous blocks of `cap` f64s:
///   [minx:cap][maxx:cap][miny:cap][maxy:cap][xa:cap][ya:cap]
///   [slope:cap][inv_slope:cap][ax:cap][ay:cap]
/// `cap` is always a multiple of VL; padding slots have minx/miny = +inf
/// so that range checks always fail, eliminating scalar tail loops.
const GridCell = struct {
    // ptr at offset 0 (8 bytes) — largest alignment field first.
    ptr: [*]f64 = undefined,
    gc_flags: u16 = 0, // offset 8
    len: u16 = 0, // offset 10  (u16: cells rarely exceed a few hundred edges)
    cap: u16 = 0, // offset 12
    // 2 bytes implicit padding → sizeof == 16, @alignOf == 8

    const N_FIELDS = 10;
    const F_MINX: usize = 0;
    const F_MAXX: usize = 1;
    const F_MINY: usize = 2;
    const F_MAXY: usize = 3;
    const F_XA: usize = 4;
    const F_YA: usize = 5;
    const F_SLOPE: usize = 6;
    const F_INV_SLOPE: usize = 7;
    const F_AX: usize = 8;
    const F_AY: usize = 9;

    fn field(self: GridCell, comptime idx: usize) [*]const f64 {
        return self.ptr + idx * @as(usize, self.cap);
    }

    fn paddedLen(self: GridCell) usize {
        return (@as(usize, self.len) + VL - 1) & ~@as(usize, VL - 1);
    }

    fn append(self: *GridCell, allocator: std.mem.Allocator, vals: [N_FIELDS]f64) !void {
        if (self.len == self.cap) try self.grow(allocator);
        const c: usize = self.cap;
        inline for (0..N_FIELDS) |f| {
            self.ptr[f * c + self.len] = vals[f];
        }
        self.len += 1;
    }

    fn grow(self: *GridCell, allocator: std.mem.Allocator) !void {
        const old_cap: usize = self.cap;
        const new_cap = if (old_cap == 0) VL else old_cap + VL;
        const new_buf = try allocator.alloc(f64, N_FIELDS * new_cap);

        // Fill padding: set minx and miny to +inf so range checks fail.
        @memset(new_buf[F_MINX * new_cap ..][0..new_cap], std.math.inf(f64));
        @memset(new_buf[F_MINY * new_cap ..][0..new_cap], std.math.inf(f64));
        // Zero remaining fields (safe: padding never passes range check).
        inline for ([_]usize{ F_MAXX, F_MAXY, F_XA, F_YA, F_SLOPE, F_INV_SLOPE, F_AX, F_AY }) |f| {
            @memset(new_buf[f * new_cap ..][0..new_cap], 0.0);
        }

        if (old_cap > 0) {
            const n: usize = self.len;
            inline for (0..N_FIELDS) |f| {
                @memcpy(new_buf[f * new_cap ..][0..n], self.ptr[f * old_cap ..][0..n]);
            }
            allocator.free(self.ptr[0 .. N_FIELDS * old_cap]);
        }

        self.ptr = new_buf.ptr;
        self.cap = @intCast(new_cap);
    }

    fn freeEdges(self: *GridCell, allocator: std.mem.Allocator) void {
        if (self.cap != 0) {
            allocator.free(self.ptr[0 .. N_FIELDS * @as(usize, self.cap)]);
        }
    }
};

const gc_bl_in: u16 = 0x0001;
const gc_br_in: u16 = 0x0002;
const gc_tl_in: u16 = 0x0004;
const gc_tr_in: u16 = 0x0008;
const gc_l_edge_hit: u16 = 0x0010;
const gc_r_edge_hit: u16 = 0x0020;
const gc_b_edge_hit: u16 = 0x0040;
const gc_t_edge_hit: u16 = 0x0080;
const gc_b_edge_parity: u16 = 0x0100;
const gc_t_edge_parity: u16 = 0x0200;
const gc_aim_l: u16 = 0 << 10;
const gc_aim_b: u16 = 1 << 10;
const gc_aim_r: u16 = 2 << 10;
const gc_aim_t: u16 = 3 << 10;
const gc_aim_c: u16 = 4 << 10;
const gc_aim: u16 = 0x1c00;

const gc_l_edge_clear: u16 = gc_l_edge_hit;
const gc_r_edge_clear: u16 = gc_r_edge_hit;
const gc_b_edge_clear: u16 = gc_b_edge_hit;
const gc_t_edge_clear: u16 = gc_t_edge_hit;
const gc_all_edge_clear: u16 = gc_l_edge_hit | gc_r_edge_hit | gc_b_edge_hit | gc_t_edge_hit;

const epsilon = 0.00001;
const max_retry_count = 16;

pub const PreparedPolygon = struct {
    allocator: std.mem.Allocator,
    xres: usize = 0,
    yres: usize = 0,
    tot_cells: usize = 0,
    minx: f64 = 0.0,
    maxx: f64 = 0.0,
    miny: f64 = 0.0,
    maxy: f64 = 0.0,
    xdelta: f64 = 0.0,
    ydelta: f64 = 0.0,
    inv_xdelta: f64 = 0.0,
    inv_ydelta: f64 = 0.0,
    glx: []f64 = &.{},
    gly: []f64 = &.{},
    gc: []GridCell = &.{},

    pub fn init(allocator: std.mem.Allocator, vertices: []const Point, resolution: usize) !PreparedPolygon {
        if (vertices.len < 3) return error.InvalidPolygon;
        if (resolution == 0) return error.InvalidResolution;

        var polygon = PreparedPolygon{
            .allocator = allocator,
            .xres = resolution,
            .yres = resolution,
            .tot_cells = resolution * resolution,
        };

        polygon.glx = try allocator.alloc(f64, resolution + 1);
        errdefer allocator.free(polygon.glx);

        polygon.gly = try allocator.alloc(f64, resolution + 1);
        errdefer allocator.free(polygon.gly);

        polygon.gc = try allocator.alloc(GridCell, polygon.tot_cells);
        errdefer allocator.free(polygon.gc);

        for (polygon.gc) |*cell| {
            cell.* = .{};
        }

        try polygon.setup(vertices);
        return polygon;
    }

    pub fn deinit(self: *PreparedPolygon) void {
        for (self.gc) |*cell| {
            cell.freeEdges(self.allocator);
            cell.* = .{};
        }

        if (self.gc.len != 0) self.allocator.free(self.gc);
        if (self.glx.len != 0) self.allocator.free(self.glx);
        if (self.gly.len != 0) self.allocator.free(self.gly);

        self.* = .{
            .allocator = self.allocator,
        };
    }

    pub fn contains(self: *const PreparedPolygon, point: Point) bool {
        const tx = point.x;
        const ty = point.y;

        if (ty < self.miny or ty >= self.maxy or tx < self.minx or tx >= self.maxx) {
            return false;
        }

        const ycell = (ty - self.miny) * self.inv_ydelta;
        const xcell = (tx - self.minx) * self.inv_xdelta;
        const row_offset = @as(usize, @intFromFloat(ycell)) * self.xres;
        const cell = &self.gc[row_offset + @as(usize, @intFromFloat(xcell))];

        if (cell.len == 0) {
            return (cell.gc_flags & gc_bl_in) != 0;
        }

        const gc_flags = cell.gc_flags;
        const e = cell.*;
        const n = e.paddedLen();

        switch (gc_flags & gc_aim) {
            gc_aim_l => {
                const base: u1 = @intFromBool((gc_flags & gc_bl_in) != 0);
                var parity: u32 = 0;
                const vty: Vf = @splat(ty);
                const vtx: Vf = @splat(tx);
                var i: usize = 0;
                while (i < n) : (i += VL) {
                    const vminy: Vf = e.field(GridCell.F_MINY)[i..][0..VL].*;
                    const vmaxy: Vf = e.field(GridCell.F_MAXY)[i..][0..VL].*;
                    const vmaxx: Vf = e.field(GridCell.F_MAXX)[i..][0..VL].*;
                    const vminx: Vf = e.field(GridCell.F_MINX)[i..][0..VL].*;
                    const vxa: Vf = e.field(GridCell.F_XA)[i..][0..VL].*;
                    const vya: Vf = e.field(GridCell.F_YA)[i..][0..VL].*;
                    const vslp: Vf = e.field(GridCell.F_SLOPE)[i..][0..VL].*;

                    const in_y = @as(Vu1, @bitCast(vty >= vminy)) & @as(Vu1, @bitCast(vty < vmaxy));
                    const gt_maxx = @as(Vu1, @bitCast(vtx > vmaxx));
                    const gt_minx = @as(Vu1, @bitCast(vtx > vminx));
                    const cross = @as(Vu1, @bitCast((vxa - (vya - vty) * vslp) < vtx));
                    const hit = in_y & (gt_maxx | (gt_minx & cross));
                    parity += @reduce(.Add, @as(Vu32, hit));
                }
                return (base ^ @as(u1, @truncate(parity))) != 0;
            },
            gc_aim_b => {
                const base: u1 = @intFromBool((gc_flags & gc_bl_in) != 0);
                var parity: u32 = 0;
                const vty: Vf = @splat(ty);
                const vtx: Vf = @splat(tx);
                var i: usize = 0;
                while (i < n) : (i += VL) {
                    const vminx: Vf = e.field(GridCell.F_MINX)[i..][0..VL].*;
                    const vmaxx: Vf = e.field(GridCell.F_MAXX)[i..][0..VL].*;
                    const vminy: Vf = e.field(GridCell.F_MINY)[i..][0..VL].*;
                    const vmaxy: Vf = e.field(GridCell.F_MAXY)[i..][0..VL].*;
                    const vxa: Vf = e.field(GridCell.F_XA)[i..][0..VL].*;
                    const vya: Vf = e.field(GridCell.F_YA)[i..][0..VL].*;
                    const vinv: Vf = e.field(GridCell.F_INV_SLOPE)[i..][0..VL].*;

                    const in_x = @as(Vu1, @bitCast(vtx >= vminx)) & @as(Vu1, @bitCast(vtx < vmaxx));
                    const gt_maxy = @as(Vu1, @bitCast(vty > vmaxy));
                    const gt_miny = @as(Vu1, @bitCast(vty > vminy));
                    const cross = @as(Vu1, @bitCast((vya - (vxa - vtx) * vinv) < vty));
                    const hit = in_x & (gt_maxy | (gt_miny & cross));
                    parity += @reduce(.Add, @as(Vu32, hit));
                }
                return (base ^ @as(u1, @truncate(parity))) != 0;
            },
            gc_aim_r => {
                const base: u1 = @intFromBool((gc_flags & gc_tr_in) != 0);
                var parity: u32 = 0;
                const vty: Vf = @splat(ty);
                const vtx: Vf = @splat(tx);
                var i: usize = 0;
                while (i < n) : (i += VL) {
                    const vminy: Vf = e.field(GridCell.F_MINY)[i..][0..VL].*;
                    const vmaxy: Vf = e.field(GridCell.F_MAXY)[i..][0..VL].*;
                    const vminx: Vf = e.field(GridCell.F_MINX)[i..][0..VL].*;
                    const vmaxx: Vf = e.field(GridCell.F_MAXX)[i..][0..VL].*;
                    const vxa: Vf = e.field(GridCell.F_XA)[i..][0..VL].*;
                    const vya: Vf = e.field(GridCell.F_YA)[i..][0..VL].*;
                    const vslp: Vf = e.field(GridCell.F_SLOPE)[i..][0..VL].*;

                    const in_y = @as(Vu1, @bitCast(vty >= vminy)) & @as(Vu1, @bitCast(vty < vmaxy));
                    const le_minx = @as(Vu1, @bitCast(vtx <= vminx));
                    const le_maxx = @as(Vu1, @bitCast(vtx <= vmaxx));
                    const cross = @as(Vu1, @bitCast((vxa - (vya - vty) * vslp) >= vtx));
                    const hit = in_y & (le_minx | (le_maxx & cross));
                    parity += @reduce(.Add, @as(Vu32, hit));
                }
                return (base ^ @as(u1, @truncate(parity))) != 0;
            },
            gc_aim_t => {
                const base: u1 = @intFromBool((gc_flags & gc_tr_in) != 0);
                var parity: u32 = 0;
                const vty: Vf = @splat(ty);
                const vtx: Vf = @splat(tx);
                var i: usize = 0;
                while (i < n) : (i += VL) {
                    const vminx: Vf = e.field(GridCell.F_MINX)[i..][0..VL].*;
                    const vmaxx: Vf = e.field(GridCell.F_MAXX)[i..][0..VL].*;
                    const vminy: Vf = e.field(GridCell.F_MINY)[i..][0..VL].*;
                    const vmaxy: Vf = e.field(GridCell.F_MAXY)[i..][0..VL].*;
                    const vxa: Vf = e.field(GridCell.F_XA)[i..][0..VL].*;
                    const vya: Vf = e.field(GridCell.F_YA)[i..][0..VL].*;
                    const vinv: Vf = e.field(GridCell.F_INV_SLOPE)[i..][0..VL].*;

                    const in_x = @as(Vu1, @bitCast(vtx >= vminx)) & @as(Vu1, @bitCast(vtx < vmaxx));
                    const le_miny = @as(Vu1, @bitCast(vty <= vminy));
                    const le_maxy = @as(Vu1, @bitCast(vty <= vmaxy));
                    const cross = @as(Vu1, @bitCast((vya - (vxa - vtx) * vinv) >= vty));
                    const hit = in_x & (le_miny | (le_maxy & cross));
                    parity += @reduce(.Add, @as(Vu32, hit));
                }
                return (base ^ @as(u1, @truncate(parity))) != 0;
            },
            gc_aim_c => {
                // Rare case (all 4 cell edges crossed) — scalar.
                var inside = (gc_flags & gc_bl_in) == gc_bl_in;
                var init_flag = true;
                var bx: f64 = 0.0;
                var by: f64 = 0.0;
                const cornerx = self.glx[@as(usize, @intFromFloat(xcell))];
                const cornery = self.gly[@as(usize, @intFromFloat(ycell))];

                for (0..e.len) |i| {
                    const e_minx = e.field(GridCell.F_MINX)[i];
                    const e_miny = e.field(GridCell.F_MINY)[i];
                    if (tx >= e_minx and ty >= e_miny) {
                        if (init_flag) {
                            bx = tx - cornerx;
                            by = ty - cornery;
                            init_flag = false;
                        }

                        const e_ax = e.field(GridCell.F_AX)[i];
                        const e_ay = e.field(GridCell.F_AY)[i];
                        const e_xa = e.field(GridCell.F_XA)[i];
                        const e_ya = e.field(GridCell.F_YA)[i];

                        const denom = e_ay * bx - e_ax * by;
                        if (denom == 0.0) continue;

                        const cx = e_xa - tx;
                        const cy = e_ya - ty;
                        const alpha = by * cx - bx * cy;

                        if (denom > 0.0) {
                            if (alpha < 0.0 or alpha >= denom) continue;
                            const beta = e_ax * cy - e_ay * cx;
                            if (beta < 0.0 or beta >= denom) continue;
                        } else {
                            if (alpha > 0.0 or alpha <= denom) continue;
                            const beta = e_ax * cy - e_ay * cx;
                            if (beta > 0.0 or beta <= denom) continue;
                        }

                        inside = !inside;
                    }
                }
                return inside;
            },
            else => unreachable,
        }
    }

    fn setup(self: *PreparedPolygon, vertices: []const Point) !void {
        var minx = vertices[0].x;
        var maxx = vertices[0].x;
        var miny = vertices[0].y;
        var maxy = vertices[0].y;

        for (vertices[1..]) |vertex| {
            minx = @min(minx, vertex.x);
            maxx = @max(maxx, vertex.x);
            miny = @min(miny, vertex.y);
            maxy = @max(maxy, vertex.y);
        }

        const gxdiff = maxx - minx;
        const gydiff = maxy - miny;
        if (gxdiff <= 0.0 or gydiff <= 0.0) return error.InvalidPolygon;

        minx -= epsilon * gxdiff;
        maxx += epsilon * gxdiff;
        miny -= epsilon * gydiff;
        maxy += epsilon * gydiff;

        const eps = 1e-9 * (gxdiff + gydiff);

        var attempt: usize = 0;
        while (attempt < max_retry_count) : (attempt += 1) {
            self.minx = minx;
            self.maxx = maxx;
            self.miny = miny;
            self.maxy = maxy;

            self.resetCells();
            self.rebuildGridLines();

            self.populateGrid(vertices, eps) catch |err| switch (err) {
                error.CornerCrossing => {
                    minx -= epsilon * gxdiff * 0.24;
                    miny -= epsilon * gydiff * 0.10;
                    continue;
                },
                else => return err,
            };

            self.computeCornerFlags();
            self.computeAimFlags();
            return;
        }

        return error.CornerCrossing;
    }

    fn rebuildGridLines(self: *PreparedPolygon) void {
        self.xdelta = (self.maxx - self.minx) / @as(f64, @floatFromInt(self.xres));
        self.inv_xdelta = 1.0 / self.xdelta;

        self.ydelta = (self.maxy - self.miny) / @as(f64, @floatFromInt(self.yres));
        self.inv_ydelta = 1.0 / self.ydelta;

        for (0..self.xres) |i| {
            self.glx[i] = self.minx + @as(f64, @floatFromInt(i)) * self.xdelta;
        }
        self.glx[self.xres] = self.maxx;

        for (0..self.yres) |i| {
            self.gly[i] = self.miny + @as(f64, @floatFromInt(i)) * self.ydelta;
        }
        self.gly[self.yres] = self.maxy;
    }

    fn resetCells(self: *PreparedPolygon) void {
        for (self.gc) |*cell| {
            cell.freeEdges(self.allocator);
            cell.* = .{};
        }
    }

    fn populateGrid(self: *PreparedPolygon, vertices: []const Point, eps: f64) !void {
        var previous = vertices[vertices.len - 1];

        for (vertices) |current| {
            const ordered = if (previous.y < current.y) .{ previous, current } else .{ current, previous };
            const vtxa = ordered[0];
            const vtxb = ordered[1];
            const xdiff = vtxb.x - vtxa.x;
            const ydiff = vtxb.y - vtxa.y;
            const tmax = std.math.sqrt(xdiff * xdiff + ydiff * ydiff);

            if (tmax == 0.0) {
                previous = current;
                continue;
            }

            const xdir = xdiff / tmax;
            const ydir = ydiff / tmax;

            var gcx: isize = @as(isize, @intFromFloat((vtxa.x - self.minx) * self.inv_xdelta));
            var gcy: usize = @as(usize, @intFromFloat((vtxa.y - self.miny) * self.inv_ydelta));

            var tx = std.math.inf(f64);
            var ty = std.math.inf(f64);
            var tgcx: f64 = 0.0;
            var tgcy: f64 = 0.0;
            var sign_x: isize = 0;

            if (vtxa.x != vtxb.x) {
                const inv_x = tmax / xdiff;
                tx = self.xdelta * @as(f64, @floatFromInt(gcx)) + self.minx - vtxa.x;
                if (vtxa.x < vtxb.x) {
                    sign_x = 1;
                    tx += self.xdelta;
                    tgcx = self.xdelta * inv_x;
                } else {
                    sign_x = -1;
                    tgcx = -self.xdelta * inv_x;
                }
                tx *= inv_x;
            }

            if (vtxa.y != vtxb.y) {
                const inv_y = tmax / ydiff;
                ty = (self.ydelta * @as(f64, @floatFromInt(gcy + 1)) + self.miny - vtxa.y) * inv_y;
                tgcy = self.ydelta * inv_y;
            }

            var cell = self.cellMut(@as(usize, @intCast(gcx)), gcy);
            var vx0 = vtxa.x;
            var vy0 = vtxa.y;
            var t_near: f64 = 0.0;

            while (true) {
                var vx1: f64 = undefined;
                var vy1: f64 = undefined;
                var y_flag = false;

                if (tx <= ty) {
                    gcx += sign_x;
                    ty -= tx;
                    t_near += tx;
                    tx = tgcx;

                    if (t_near < tmax) {
                        if (sign_x > 0) {
                            cell.gc_flags |= gc_r_edge_hit;
                            vx1 = self.glx[@as(usize, @intCast(gcx))];
                        } else {
                            cell.gc_flags |= gc_l_edge_hit;
                            vx1 = self.glx[@as(usize, @intCast(gcx + 1))];
                        }
                        vy1 = t_near * ydir + vtxa.y;
                    } else {
                        vx1 = vtxb.x;
                        vy1 = vtxb.y;
                    }
                } else {
                    gcy += 1;
                    tx -= ty;
                    t_near += ty;
                    ty = tgcy;

                    if (t_near < tmax) {
                        cell.gc_flags |= gc_t_edge_hit;
                        cell.gc_flags ^= gc_t_edge_parity;
                        vx1 = t_near * xdir + vtxa.x;
                        vy1 = self.gly[gcy];
                    } else {
                        vx1 = vtxb.x;
                        vy1 = vtxb.y;
                    }

                    y_flag = true;
                }

                try self.addEdge(cell, vx0, vy0, vx1, vy1, eps);

                if (t_near < tmax) {
                    cell = self.cellMut(@as(usize, @intCast(gcx)), gcy);
                    if (y_flag) {
                        cell.gc_flags |= gc_b_edge_hit;
                        cell.gc_flags ^= gc_b_edge_parity;
                    } else {
                        cell.gc_flags |= if (sign_x > 0) gc_l_edge_hit else gc_r_edge_hit;
                    }
                }

                vx0 = vx1;
                vy0 = vy1;
                if (!(t_near < tmax)) break;
            }

            previous = current;
        }
    }

    fn computeCornerFlags(self: *PreparedPolygon) void {
        var row: usize = 1;
        while (row < self.yres) : (row += 1) {
            var io_state = false;

            for (0..self.xres) |column| {
                const top_index = (row - 1) * self.xres + column;
                const bottom_index = row * self.xres + column;
                const top_cell = &self.gc[top_index];
                const bottom_cell = &self.gc[bottom_index];

                if (io_state) {
                    top_cell.gc_flags |= gc_tl_in;
                    bottom_cell.gc_flags |= gc_bl_in;
                }

                if ((top_cell.gc_flags & gc_t_edge_parity) != 0) {
                    io_state = !io_state;
                }

                if (io_state) {
                    top_cell.gc_flags |= gc_tr_in;
                    bottom_cell.gc_flags |= gc_br_in;
                }
            }
        }
    }

    fn computeAimFlags(self: *PreparedPolygon) void {
        for (self.gc) |*cell| {
            const clear_flags = cell.gc_flags ^ gc_all_edge_clear;
            if ((clear_flags & gc_l_edge_clear) != 0) {
                cell.gc_flags |= gc_aim_l;
            } else if ((clear_flags & gc_b_edge_clear) != 0) {
                cell.gc_flags |= gc_aim_b;
            } else if ((clear_flags & gc_r_edge_clear) != 0) {
                cell.gc_flags |= gc_aim_r;
            } else if ((clear_flags & gc_t_edge_clear) != 0) {
                cell.gc_flags |= gc_aim_t;
            } else {
                cell.gc_flags |= gc_aim_c;
            }
        }
    }

    fn addEdge(self: *PreparedPolygon, cell: *GridCell, xa: f64, ya: f64, xb: f64, yb: f64, eps: f64) !void {
        var slope: f64 = 0.0;
        var inv_slope: f64 = 0.0;

        if (near(ya, yb, eps)) {
            if (near(xa, xb, eps)) {
                return error.CornerCrossing;
            }
            slope = std.math.inf(f64);
            inv_slope = 0.0;
        } else if (near(xa, xb, eps)) {
            slope = 0.0;
            inv_slope = std.math.inf(f64);
        } else {
            slope = (xb - xa) / (yb - ya);
            inv_slope = (yb - ya) / (xb - xa);
        }

        try cell.append(self.allocator, .{
            @min(xa, xb), // minx
            @max(xa, xb), // maxx
            @min(ya, yb), // miny
            @max(ya, yb), // maxy
            xa,
            ya,
            slope,
            inv_slope,
            xb - xa, // ax
            yb - ya, // ay
        });
    }

    fn cellMut(self: *PreparedPolygon, x: usize, y: usize) *GridCell {
        return &self.gc[y * self.xres + x];
    }
};

fn near(a: f64, b: f64, eps: f64) bool {
    return ((b - eps) < a) and ((a - eps) < b);
}

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

test "prepared polygon matches naive ray casting for a concave polygon" {
    const polygon = [_]Point{
        .{ .x = 0.0, .y = 0.0 },
        .{ .x = 8.0, .y = 0.0 },
        .{ .x = 8.0, .y = 4.0 },
        .{ .x = 4.0, .y = 2.0 },
        .{ .x = 0.0, .y = 4.0 },
    };

    var prepared = try PreparedPolygon.init(std.testing.allocator, &polygon, 32);
    defer prepared.deinit();

    var prng = std.Random.DefaultPrng.init(0xdecafbad);
    const random = prng.random();

    var i: usize = 0;
    while (i < 2_000) : (i += 1) {
        const point = Point{
            .x = random.float(f64) * 10.0 - 1.0,
            .y = random.float(f64) * 6.0 - 1.0,
        };

        try std.testing.expectEqual(naiveContains(&polygon, point), prepared.contains(point));
    }
}
