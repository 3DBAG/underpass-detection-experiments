const std = @import("std");

fn addGeogramIncludePathFromNixFlags(b: *std.Build, module: *std.Build.Module) void {
    if (std.process.getEnvVarOwned(b.allocator, "NIX_CFLAGS_COMPILE")) |nix_cflags| {
        defer b.allocator.free(nix_cflags);

        var it = std.mem.tokenizeAny(u8, nix_cflags, " \t\r\n");
        var expect_path = false;
        while (it.next()) |token| {
            if (expect_path) {
                if (std.mem.indexOf(u8, token, "geogram-") != null and std.mem.endsWith(u8, token, "/include")) {
                    const geogram_include = std.fmt.allocPrint(b.allocator, "{s}/geogram1", .{token}) catch @panic("OOM");
                    module.addSystemIncludePath(.{ .cwd_relative = geogram_include });
                    return;
                }
                expect_path = false;
                continue;
            }

            if (std.mem.eql(u8, token, "-isystem") or std.mem.eql(u8, token, "-I")) {
                expect_path = true;
                continue;
            }

            if (std.mem.startsWith(u8, token, "-isystem")) {
                const path = token["-isystem".len..];
                if (path.len > 0 and std.mem.indexOf(u8, path, "geogram-") != null and std.mem.endsWith(u8, path, "/include")) {
                    const geogram_include = std.fmt.allocPrint(b.allocator, "{s}/geogram1", .{path}) catch @panic("OOM");
                    module.addSystemIncludePath(.{ .cwd_relative = geogram_include });
                    return;
                }
                continue;
            }

            if (std.mem.startsWith(u8, token, "-I")) {
                const path = token[2..];
                if (path.len > 0 and std.mem.indexOf(u8, path, "geogram-") != null and std.mem.endsWith(u8, path, "/include")) {
                    const geogram_include = std.fmt.allocPrint(b.allocator, "{s}/geogram1", .{path}) catch @panic("OOM");
                    module.addSystemIncludePath(.{ .cwd_relative = geogram_include });
                    return;
                }
            }
        }
    } else |_| {}
}

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
            .root_source_file = b.path("zityjson/src/zityjson.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    zityjson_lib.bundle_compiler_rt = true;

    // Build zfcb static library (streaming FlatCityBuf reader)
    const zfcb_lib = b.addLibrary(.{
        .name = "zfcb",
        .linkage = .static,
        .root_module = b.createModule(.{
            .root_source_file = b.path("zityjson/src/zfcb.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    zfcb_lib.bundle_compiler_rt = true;

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
        .name = "add_underpass",
        .root_module = exe_mod,
    });
    addGeogramIncludePathFromNixFlags(b, exe.root_module);

    // 1. C++ Setup
    exe.root_module.addCSourceFile(.{
        .file = b.path("src/main.cpp"),
        .flags = cpp_flags,
    });
    exe.root_module.addCSourceFile(.{
        .file = b.path("src/OGRVectorReader.cpp"),
        .flags = cpp_flags,
    });
    exe.root_module.addCSourceFile(.{
        .file = b.path("src/PolygonExtruder.cpp"),
        .flags = cpp_flags,
    });
    exe.root_module.addCSourceFile(.{
        .file = b.path("src/RerunVisualization.cpp"),
        .flags = cpp_flags,
    });
    exe.root_module.addCSourceFile(.{
        .file = b.path("src/BooleanOps.cpp"),
        .flags = cpp_flags,
    });
    exe.root_module.addCSourceFile(.{
        .file = b.path("src/MeshConversion.cpp"),
        .flags = cpp_flags,
    });
    exe.root_module.addCSourceFile(.{
        .file = b.path("src/ModelLoaders.cpp"),
        .flags = cpp_flags,
    });

    // 2. Linking System Libraries
    // Note: Zig automatically picks up NIX_CFLAGS_COMPILE and NIX_LDFLAGS from the environment
    exe.root_module.linkSystemLibrary("manifold", .{});
    exe.root_module.linkSystemLibrary("geogram", .{});

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
    exe.linkLibrary(zfcb_lib);
    exe.root_module.addIncludePath(b.path("zityjson/include"));

    // 5. Installation
    b.installArtifact(exe);

    // Optionally install zityjson/zfcb libraries and zityjson header separately
    const install_lib = b.step("lib", "Build and install zityjson/zfcb libraries");
    install_lib.dependOn(&b.addInstallArtifact(zityjson_lib, .{}).step);
    install_lib.dependOn(&b.addInstallArtifact(zfcb_lib, .{}).step);
    install_lib.dependOn(&b.addInstallFileWithDir(
        b.path("zityjson/include/zityjson.h"),
        .header,
        "zityjson.h",
    ).step);
    install_lib.dependOn(&b.addInstallFileWithDir(
        b.path("zityjson/include/zfcb.h"),
        .header,
        "zfcb.h",
    ).step);

}
