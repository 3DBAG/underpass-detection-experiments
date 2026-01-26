const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    // Build options
    const enable_rerun = b.option(bool, "rerun", "Enable Rerun visualization support (only tested on macOS arm64)") orelse false;

    // Build zityjson static library
    const zityjson_lib = b.addLibrary(.{
        .name = "zityjson",
        .linkage = .static,
        .root_module = b.createModule(.{
            .root_source_file = b.path("zityjson/src/root.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    zityjson_lib.bundle_compiler_rt = true;

    // C++ flags
    const cpp_flags: []const []const u8 = if (enable_rerun)
        &.{ "-std=c++20", "-DENABLE_RERUN=1" }
    else
        &.{"-std=c++20"};

    // Create the main executable module
    const exe_mod = b.createModule(.{
        .target = target,
        .optimize = optimize,
        .link_libcpp = true,
    });

    const exe = b.addExecutable(.{
        .name = "test_3d_intersection",
        .root_module = exe_mod,
    });

    // 1. C++ Setup
    exe.root_module.addCSourceFile(.{
        .file = b.path("main.cpp"),
        .flags = cpp_flags,
    });
    exe.root_module.addCSourceFile(.{
        .file = b.path("OGRVectorReader.cpp"),
        .flags = cpp_flags,
    });
    exe.root_module.addCSourceFile(.{
        .file = b.path("PolygonExtruder.cpp"),
        .flags = cpp_flags,
    });

    // 2. Linking System Libraries
    // Note: Zig automatically picks up NIX_CFLAGS_COMPILE and NIX_LDFLAGS from the environment
    exe.root_module.linkSystemLibrary("manifold", .{});

    // CGAL dependencies
    exe.root_module.linkSystemLibrary("gmp", .{});
    exe.root_module.linkSystemLibrary("mpfr", .{});

    // GDAL
    exe.root_module.linkSystemLibrary("gdal", .{});

    // 3. Rerun dependencies (optional)
    if (enable_rerun) {
        const resolved_target = target.result;
        const is_macos = resolved_target.os.tag == .macos;
        const is_linux = resolved_target.os.tag == .linux;
        const is_aarch64 = resolved_target.cpu.arch == .aarch64;
        const is_x86_64 = resolved_target.cpu.arch == .x86_64;

        exe.root_module.linkSystemLibrary("rerun_sdk", .{});
        exe.root_module.linkSystemLibrary("arrow", .{});

        if (is_macos) {
            // macOS frameworks required by rerun
            if (std.process.getEnvVarOwned(b.allocator, "SDKROOT")) |sdk_root| {
                const framework_path = std.fmt.allocPrint(b.allocator, "{s}/System/Library/Frameworks", .{sdk_root}) catch @panic("OOM");
                exe.root_module.addFrameworkPath(.{ .cwd_relative = framework_path });
            } else |_| {}
            exe.root_module.linkFramework("CoreFoundation", .{});
            exe.root_module.linkFramework("IOKit", .{});
            exe.root_module.linkFramework("Security", .{});

            if (is_aarch64) {
                exe.root_module.linkSystemLibrary("rerun_c__macos_arm64", .{});
            } else if (is_x86_64) {
                exe.root_module.linkSystemLibrary("rerun_c__macos_x64", .{});
            }
        } else if (is_linux) {
            if (is_aarch64) {
                exe.root_module.linkSystemLibrary("rerun_c__linux_arm64", .{});
            } else if (is_x86_64) {
                exe.root_module.linkSystemLibrary("rerun_c__linux_x64", .{});
            }
        }
    }

    // 4. Link zityjson
    exe.linkLibrary(zityjson_lib);
    exe.root_module.addIncludePath(b.path("zityjson/include"));

    // 5. Installation
    b.installArtifact(exe);

    // Optionally install zityjson library and header separately
    const install_lib = b.step("lib", "Build and install zityjson library");
    install_lib.dependOn(&b.addInstallArtifact(zityjson_lib, .{}).step);
    install_lib.dependOn(&b.addInstallFileWithDir(
        b.path("zityjson/include/zityjson.h"),
        .header,
        "zityjson.h",
    ).step);
}
