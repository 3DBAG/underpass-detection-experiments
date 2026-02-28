const std = @import("std");
const zj = @import("zityjson");

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();

    var cj = try zj.CityJSON.init(allocator);
    defer cj.deinit();

    try cj.load("../sample_data/9-444-728.city.jsonl");

    for (cj.objects.keys(), cj.objects.values()) |key, object| {
        std.debug.print("Object {s} has {d} faces\n", .{ key, object.geometries.len });
        // std.debug.print("Object {s} has {d} vertices\n", .{ key, mesh.vertices.items.len/3 });
    }
}

// test "simple test" {
//     const gpa = std.testing.allocator;
//     var list: std.ArrayList(i32) = .empty;
//     defer list.deinit(gpa); // Try commenting this out and see if zig detects the memory leak!
//     try list.append(gpa, 42);
//     try std.testing.expectEqual(@as(i32, 42), list.pop());
// }

// test "fuzz example" {
//     const Context = struct {
//         fn testOne(context: @This(), input: []const u8) anyerror!void {
//             _ = context;
//             // Try passing `--fuzz` to `zig build test` and see if it manages to fail this test case!
//             try std.testing.expect(!std.mem.eql(u8, "canyoufindme", input));
//         }
//     };
//     try std.testing.fuzz(Context{}, Context.testOne, .{});
// }
