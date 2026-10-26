const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const module = b.createModule(.{
        .root_source_file = b.path("src/main.zig"),
        .target = target,
        .optimize = .ReleaseSafe,
    });
    const exe = b.addExecutable(.{
        .name = "passgen",
        .root_module = module,
    });
    b.installArtifact(exe);
}
