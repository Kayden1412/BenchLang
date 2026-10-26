//! System CSPRNG wrapper.
//!
//! ALT_RNG_REV_0 -- leaf file used by the incremental edit test.
//!
//! `io.randomSecure` is Zig's interface to the operating system's
//! cryptographically secure random source. No seeded PRNG is used.
//!
//! All implementations read the system CSPRNG through the same 4096-byte
//! buffer and consume little-endian 32-bit words. This keeps the random-value
//! consumption pattern identical across languages; only the OS call used to
//! fill the buffer differs.

const std = @import("std");

const BUFFER_SIZE = 4096;
var buffer: [BUFFER_SIZE]u8 = undefined;
var offset: usize = BUFFER_SIZE;

fn cspFailure() noreturn {
    std.debug.print("passgen: CSPRNG failure\n", .{});
    std.process.exit(2);
}

/// Fills `buf` with bytes from the system CSPRNG.
pub fn fill(io: std.Io, buf: []u8) void {
    io.randomSecure(buf) catch cspFailure();
}

fn refill(io: std.Io) void {
    fill(io, &buffer);
    offset = 0;
}

fn nextU32(io: std.Io) u32 {
    if (offset + 4 > BUFFER_SIZE) {
        refill(io);
    }

    const bytes = buffer[offset..][0..4];
    offset += 4;
    return @as(u32, bytes[0]) |
        (@as(u32, bytes[1]) << 8) |
        (@as(u32, bytes[2]) << 16) |
        (@as(u32, bytes[3]) << 24);
}

/// Uniform integer in `[0, n)` with rejection sampling.
pub fn below(io: std.Io, n: usize) usize {
    if (n <= 1) {
        return 0;
    }

    const limit: u64 = ((@as(u64, 1) << 32) / n) * n;
    while (true) {
        const value: u64 = nextU32(io);
        if (value < limit) {
            return @intCast(value % n);
        }
    }
}
