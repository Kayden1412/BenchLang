#!/usr/bin/env python3
"""Reference implementation of the AltBench passgen contract."""

import json
import sys

import rng

LOWER = "abcdefghijklmnopqrstuvwxyz"
UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGIT = "0123456789"
SYMBOL = "!@#$%^&*()-_=+[]{};:,.?/"
CLASS_ORDER = ("lower", "upper", "digit", "symbol")
AMBIGUOUS = frozenset("lI1O0")

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
        if name == "lower":
            chars = LOWER
        elif name == "upper":
            chars = UPPER
        elif name == "digit":
            chars = DIGIT
        else:
            chars = SYMBOL
        if no_ambiguous:
            chars = "".join(ch for ch in chars if ch not in AMBIGUOUS)
        if not chars:
            fail(f"class {name} is empty after --no-ambiguous")
        pools.append(chars)

    if not pools:
        fail("no character classes selected")
    return pools


def generate(length: int, pools) -> str:
    pool = "".join(pools)
    chars = [p[rng.below(len(p))] for p in pools]
    while len(chars) < length:
        chars.append(pool[rng.below(len(pool))])
    for i in range(len(chars) - 1, 0, -1):
        j = rng.below(i + 1)
        chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


def fnv1a(data: bytes) -> int:
    h = 2166136261
    for byte in data:
        h ^= byte
        h = (h * 16777619) & 0xFFFFFFFF
    return h


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

    if not 1 <= length <= 1024:
        fail("--length must be between 1 and 1024")
    if not 1 <= count <= 100000:
        fail("--count must be between 1 and 100000")
    if output_format not in ("plain", "json"):
        fail("--format must be plain or json")

    pools = parse_classes(classes_arg, no_ambiguous)
    if length < len(pools):
        fail("--length is smaller than the number of selected classes")

    passwords = [generate(length, pools) for _ in range(count)]
    payload = "".join(password + "\n" for password in passwords).encode()
    checksum = f"{fnv1a(payload):08x}"

    if output_format == "json":
        print(
            json.dumps(
                {"passwords": passwords, "checksum": checksum},
                separators=(",", ":"),
            )
        )
    else:
        for password in passwords:
            print(password)
        print(f"checksum={checksum}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except BrokenPipeError:
        raise SystemExit(1)
