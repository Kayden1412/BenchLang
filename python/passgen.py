#!/usr/bin/env python3
"""Reference implementation of the AltBench passgen contract."""

import sys

import rng

LOWER = b"abcdefghijklmnopqrstuvwxyz"
UPPER = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGIT = b"0123456789"
SYMBOL = b"!@#$%^&*()-_=+[]{};:,.?/"
CLASS_ORDER = ("lower", "upper", "digit", "symbol")
SOURCES = {
    "lower": LOWER,
    "upper": UPPER,
    "digit": DIGIT,
    "symbol": SYMBOL,
}
AMBIGUOUS = frozenset(b"lI1O0")
MAX_LENGTH = 1024
MAX_COUNT = 100000
OUTPUT_SIZE = 4096

USAGE = """usage: passgen [options]

  --length N          password length (default 16)
  --count N           number of passwords (default 5)
  --classes LIST      comma-separated subset of: lower,upper,digit,symbol
  --no-ambiguous      remove l, I, 1, O, 0 from the pools
  --format FORMAT     plain (default) or json
  --help              print this help
"""


def fail(message: str) -> None:
    print(f"passgen: {message}", file=sys.stderr)
    raise SystemExit(2)


def parse_int(value: str, name: str) -> int:
    try:
        return int(value, 10)
    except ValueError:
        fail(f"{name} expects an integer, got {value!r}")


def parse_classes(arg: str, no_ambiguous: bool):
    names = [part.strip() for part in arg.split(",") if part.strip()]
    if not names:
        fail("no character classes selected")
    unknown = [name for name in names if name not in CLASS_ORDER]
    if unknown:
        fail(f"unknown class: {unknown[0]}")
    selected = set(names)

    pools = []
    for name in CLASS_ORDER:
        if name not in selected:
            continue
        chars = SOURCES[name]
        if no_ambiguous:
            chars = bytes(ch for ch in chars if ch not in AMBIGUOUS)
        if not chars:
            fail(f"class {name} is empty after --no-ambiguous")
        pools.append(chars)

    if not pools:
        fail("no character classes selected")
    return pools


def generate(length: int, pools, combined: bytes, out: bytearray) -> None:
    position = 0
    for pool in pools:
        out[position] = pool[rng.below(len(pool))]
        position += 1
    while position < length:
        out[position] = combined[rng.below(len(combined))]
        position += 1
    for i in range(length - 1, 0, -1):
        j = rng.below(i + 1)
        out[i], out[j] = out[j], out[i]


def fnv1a_update(hash_value: int, data, length: int) -> int:
    for i in range(length):
        hash_value ^= data[i]
        hash_value = (hash_value * 16777619) & 0xFFFFFFFF
    return hash_value


class Output:
    __slots__ = ("buf", "n")

    def __init__(self) -> None:
        self.buf = bytearray(OUTPUT_SIZE)
        self.n = 0

    def flush(self) -> None:
        if self.n:
            sys.stdout.buffer.write(memoryview(self.buf)[: self.n])
            self.n = 0

    def write(self, data) -> None:
        size = len(data)
        if size >= OUTPUT_SIZE:
            self.flush()
            sys.stdout.buffer.write(data)
            return
        if self.n + size > OUTPUT_SIZE:
            self.flush()
        self.buf[self.n : self.n + size] = data
        self.n += size

    def write_buffer(self, data, length: int) -> None:
        if length >= OUTPUT_SIZE:
            self.flush()
            sys.stdout.buffer.write(memoryview(data)[:length])
            return
        if self.n + length > OUTPUT_SIZE:
            self.flush()
        self.buf[self.n : self.n + length] = memoryview(data)[:length]
        self.n += length

    def write_hex(self, value: int) -> None:
        self.write(f"{value:08x}".encode())


def main(argv) -> int:
    length = 16
    count = 5
    classes_arg = "lower,upper,digit,symbol"
    no_ambiguous = False
    output_format = "plain"

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-h", "--help"):
            print(USAGE, end="")
            return 0
        if arg == "--no-ambiguous":
            no_ambiguous = True
        elif arg == "--length":
            i += 1
            if i >= len(argv):
                fail("--length needs a value")
            length = parse_int(argv[i], "--length")
        elif arg == "--count":
            i += 1
            if i >= len(argv):
                fail("--count needs a value")
            count = parse_int(argv[i], "--count")
        elif arg == "--classes":
            i += 1
            if i >= len(argv):
                fail("--classes needs a value")
            classes_arg = argv[i]
        elif arg == "--format":
            i += 1
            if i >= len(argv):
                fail("--format needs a value")
            output_format = argv[i]
        else:
            fail(f"unknown argument: {arg}")
        i += 1

    if not 1 <= length <= MAX_LENGTH:
        fail("--length must be between 1 and 1024")
    if not 1 <= count <= MAX_COUNT:
        fail("--count must be between 1 and 100000")
    if output_format not in ("plain", "json"):
        fail("--format must be plain or json")

    pools = parse_classes(classes_arg, no_ambiguous)
    if length < len(pools):
        fail("--length is smaller than the number of selected classes")

    combined = b"".join(pools)
    password = bytearray(MAX_LENGTH)
    checksum = 2166136261
    out = Output()

    if output_format == "json":
        out.write(b'{"passwords":[')

    for index in range(count):
        generate(length, pools, combined, password)
        checksum = fnv1a_update(checksum, password, length)
        checksum = fnv1a_update(checksum, b"\n", 1)

        if output_format == "json":
            if index:
                out.write(b",")
            out.write(b'"')
            out.write_buffer(password, length)
            out.write(b'"')
        else:
            out.write_buffer(password, length)
            out.write(b"\n")

    if output_format == "json":
        out.write(b'],"checksum":"')
        out.write_hex(checksum)
        out.write(b'"}\n')
    else:
        out.write(b"checksum=")
        out.write_hex(checksum)
        out.write(b"\n")

    out.flush()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except BrokenPipeError:
        raise SystemExit(1)
