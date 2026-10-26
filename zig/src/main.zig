const std = @import("std");
const rng = @import("rng.zig");

const MAX_LENGTH: usize = 1024;
const MAX_COUNT: usize = 100000;

const LOWER = "abcdefghijklmnopqrstuvwxyz";
const UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const DIGIT = "0123456789";
const SYMBOL = "!@#$%^&*()-_=+[]{};:,.?/";

const CLASS_NAMES = [_][]const u8{ "lower", "upper", "digit", "symbol" };
const CLASS_SOURCES = [_][]const u8{ LOWER, UPPER, DIGIT, SYMBOL };

const USAGE =
    \\usage: passgen [options]
    \\
    \\  --length N          password length (default 16)
    \\  --count N           number of passwords (default 5)
    \\  --classes LIST      comma-separated subset of: lower,upper,digit,symbol
    \\  --no-ambiguous      remove l, I, 1, O, 0 from the pools
    \\  --format FORMAT     plain (default) or json
    \\  --help              print this help
    \\
;

const Pool = struct {
    chars: []const u8,
};

fn fail(message: []const u8) noreturn {
    std.debug.print("passgen: {s}\n", .{message});
    std.process.exit(2);
}

fn classIndex(name: []const u8) ?usize {
    for (CLASS_NAMES, 0..) |candidate, index| {
        if (std.mem.eql(u8, candidate, name)) {
            return index;
        }
    }
    return null;
}

fn isAmbiguous(c: u8) bool {
    return c == 'l' or c == 'I' or c == '1' or c == 'O' or c == '0';
}

fn buildPool(source: []const u8, no_ambiguous: bool, buffer: []u8) []const u8 {
    var len: usize = 0;
    for (source) |c| {
        if (no_ambiguous and isAmbiguous(c)) {
            continue;
        }
        buffer[len] = c;
        len += 1;
    }
    return buffer[0..len];
}

fn generate(io: std.Io, length: usize, pools: []const Pool, combined: []const u8, out: []u8) void {
    var position: usize = 0;
    for (pools) |pool| {
        out[position] = pool.chars[rng.below(io, pool.chars.len)];
        position += 1;
    }
    while (position < length) : (position += 1) {
        out[position] = combined[rng.below(io, combined.len)];
    }

    var i = length;
    while (i > 1) : (i -= 1) {
        const j = rng.below(io, i);
        const tmp = out[i - 1];
        out[i - 1] = out[j];
        out[j] = tmp;
    }
}

fn fnv1a(hash: u32, text: []const u8) u32 {
    var h = hash;
    for (text) |byte| {
        h ^= byte;
        h *%= 16777619;
    }
    return h;
}

fn writeChecksum(writer: *std.Io.Writer, value: u32) !void {
    const digits = "0123456789abcdef";
    var buffer: [8]u8 = undefined;
    var v = value;
    var i: usize = buffer.len;
    while (i > 0) {
        i -= 1;
        buffer[i] = digits[v & 0xf];
        v >>= 4;
    }
    try writer.writeAll(&buffer);
}

pub fn main(init: std.process.Init) !void {
    const io = init.io;
    const arena = init.arena.allocator();
    const args = try init.minimal.args.toSlice(arena);

    var stdout_buffer: [4096]u8 = undefined;
    var stdout_writer = std.Io.File.stdout().writer(io, &stdout_buffer);
    const stdout = &stdout_writer.interface;

    var length: usize = 16;
    var count: usize = 5;
    var classes: []const u8 = "lower,upper,digit,symbol";
    var no_ambiguous = false;
    var as_json = false;

    var i: usize = 1;
    while (i < args.len) : (i += 1) {
        const arg = args[i];

        if (std.mem.eql(u8, arg, "--help") or std.mem.eql(u8, arg, "-h")) {
            try stdout.writeAll(USAGE);
            try stdout.flush();
            return;
        }

        if (std.mem.eql(u8, arg, "--no-ambiguous")) {
            no_ambiguous = true;
            continue;
        }

        if (std.mem.eql(u8, arg, "--length") or
            std.mem.eql(u8, arg, "--count") or
            std.mem.eql(u8, arg, "--classes") or
            std.mem.eql(u8, arg, "--format"))
        {
            if (i + 1 >= args.len) {
                fail("option needs a value");
            }
            i += 1;
            const value = args[i];

            if (std.mem.eql(u8, arg, "--classes")) {
                classes = value;
            } else if (std.mem.eql(u8, arg, "--format")) {
                if (std.mem.eql(u8, value, "json")) {
                    as_json = true;
                } else if (std.mem.eql(u8, value, "plain")) {
                    as_json = false;
                } else {
                    fail("--format must be plain or json");
                }
            } else if (std.mem.eql(u8, arg, "--length")) {
                length = std.fmt.parseInt(usize, value, 10) catch
                    fail("--length expects an integer");
                if (length < 1 or length > MAX_LENGTH) {
                    fail("--length must be between 1 and 1024");
                }
            } else {
                count = std.fmt.parseInt(usize, value, 10) catch
                    fail("--count expects an integer");
                if (count < 1 or count > MAX_COUNT) {
                    fail("--count must be between 1 and 100000");
                }
            }
            continue;
        }

        fail("unknown argument");
    }

    var selected = [_]bool{false} ** 4;
    var split = std.mem.splitScalar(u8, classes, ',');
    while (split.next()) |part| {
        const name = std.mem.trim(u8, part, " \t");
        if (name.len == 0) {
            continue;
        }
        const index = classIndex(name) orelse fail("unknown character class");
        selected[index] = true;
    }

    var pool_buffers: [4][64]u8 = undefined;
    var combined_buffer: [256]u8 = undefined;
    var combined_len: usize = 0;
    var pools: [4]Pool = undefined;
    var pool_count: usize = 0;

    for (CLASS_SOURCES, 0..) |source, index| {
        if (!selected[index]) {
            continue;
        }
        const chars = buildPool(source, no_ambiguous, &pool_buffers[index]);
        if (chars.len == 0) {
            fail("class is empty after --no-ambiguous");
        }
        pools[pool_count] = .{ .chars = chars };
        pool_count += 1;

        for (chars) |c| {
            combined_buffer[combined_len] = c;
            combined_len += 1;
        }
    }

    if (pool_count == 0) {
        fail("no character classes selected");
    }
    if (length < pool_count) {
        fail("--length is smaller than the number of selected classes");
    }

    const active_pools = pools[0..pool_count];
    const combined = combined_buffer[0..combined_len];

    var password: [MAX_LENGTH]u8 = undefined;
    var checksum: u32 = 2166136261;

    if (as_json) {
        try stdout.writeAll("{\"passwords\":[");
    }

    var index: usize = 0;
    while (index < count) : (index += 1) {
        generate(io, length, active_pools, combined, password[0..length]);
        checksum = fnv1a(checksum, password[0..length]);
        checksum = fnv1a(checksum, "\n");

        if (as_json) {
            if (index > 0) {
                try stdout.writeAll(",");
            }
            try stdout.writeAll("\"");
            try stdout.writeAll(password[0..length]);
            try stdout.writeAll("\"");
        } else {
            try stdout.writeAll(password[0..length]);
            try stdout.writeAll("\n");
        }
    }

    if (as_json) {
        try stdout.writeAll("],\"checksum\":\"");
        try writeChecksum(stdout, checksum);
        try stdout.writeAll("\"}\n");
    } else {
        try stdout.writeAll("checksum=");
        try writeChecksum(stdout, checksum);
        try stdout.writeAll("\n");
    }

    try stdout.flush();
}
