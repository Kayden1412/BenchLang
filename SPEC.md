# AltBench: `passgen`

A small but realistic CLI program, used to compare **compile/edit/build-cycle
time and runtime performance** under a consistent methodology.

The point is not that a password generator is a heavy program. The point is
that it has the shape of real code: argument parsing, validation, several
modules, a CSPRNG, character-class policy, text/JSON output, and a checksum.
Every language implements the same observable behaviour, so a wrong build is
detected instead of being timed.

## Program contract

```
passgen [options]

  --length N          password length (default 16)
  --count N           number of passwords (default 5)
  --classes LIST      comma-separated subset of: lower,upper,digit,symbol
                      (default: lower,upper,digit,symbol)
  --no-ambiguous      remove l, I, 1, O, 0 from the pools
  --format FORMAT     plain (default) or json
  --help              print usage
```

`plain` output: one password per line, then a final line:

```
checksum=XXXXXXXX
```

`json` output: a single line:

```
{"passwords":["...","..."],"checksum":"XXXXXXXX"}
```

`XXXXXXXX` is the lowercase, zero-padded 8-digit hex FNV-1a 32-bit checksum
of the UTF-8 bytes of every password followed by `\n`, in output order.

Invalid arguments exit with status 2 and print a message to stderr.

## Randomness: system CSPRNG, not a seeded PRNG

This is a password generator, so it must use the operating system's
cryptographic random source. There is deliberately no `--seed` option: a
password generator with a reproducible seed is a vulnerability, not a feature.

Each implementation fills the same 4096-byte buffer from its platform's
CSPRNG, then consumes little-endian 32-bit words from that buffer:

| Language | Buffer source |
|---|---|
| C / C++ | `getrandom(2)` on Linux, `arc4random_buf` on Android, `/dev/urandom` fallback |
| Rust | `/dev/urandom` via `std::fs::File` (no external crates) |
| Go | `crypto/rand` |
| Zig | `Io.randomSecure` (the OS CSPRNG behind Zig's `Io` interface) |
| C3 | `std::crypto::entropy` (`getrandom` on Linux) |
| Python | `secrets` (`os.urandom`) |
| JavaScript | `node:crypto` `randomFillSync` |

The buffer is refilled only when fewer than 4 bytes remain. Buffer size, word
width, byte order, and refill rule are identical in every implementation, so
all languages consume the CSPRNG in the same pattern; only the OS call that
fills the buffer differs. This keeps runtime comparisons about language and
runtime overhead rather than about how often each one happens to call the
kernel.

Uniform selection uses rejection sampling over the 32-bit word with
`limit = (2^32 / n) * n`, so there is no modulo bias. Fisher-Yates is used for
the final shuffle. No `rand()`, `Math.random()`, seeded PRNG, or time-based seed
is used anywhere.

Because the output is intentionally non-deterministic, the harness validates
**properties**, not a fixed golden string:

* the requested number of passwords, each at the requested length;
* every character belongs to the requested pools;
* every selected class appears at least once per password;
* `--no-ambiguous` characters are absent;
* the emitted checksum matches FNV-1a over the emitted passwords;
* two independent runs produce different output (CSPRNG sanity check).

## Character pools

```
lower  = abcdefghijklmnopqrstuvwxyz
upper  = ABCDEFGHIJKLMNOPQRSTUVWXYZ
digit  = 0123456789
symbol = !@#$%^&*()-_=+[]{};:,.?/
```

`--no-ambiguous` removes `l`, `I`, `1`, `O`, `0` from `lower`, `upper`,
`digit` respectively. `symbol` is unchanged.

Classes are always processed in the fixed order `lower, upper, digit, symbol`,
regardless of the order given on the command line. Empty entries in the
comma-separated list are ignored. At least one character from each selected
class is placed in every password; the rest are drawn from the combined pool.
The final string is shuffled with Fisher-Yates.

## Measurement model

Compile-time numbers can easily blend incompatible things: per-file incremental
compilation, whole-program rebuilds, dependency builds, persistent caches, and
failed builds. AltBench therefore measures three separate events with the same
edit for every language:

| Measurement | What happens |
|---|---|
| `cold` | remove first-party build artifacts, then build |
| `noop` | build again with no source change |
| `edit` | change one leaf implementation file (`rng.*`), then build |

`edit` is only labelled "incremental" when the toolchain actually has an
incremental mode. Languages whose release mode is a whole-program rebuild are
reported with `mode: full`, and their `edit` time is expected to be close to
`cold`. The harness never hides that difference in a single "incremental"
column.

### Cold definition

`cold` removes first-party artifacts only (`make clean`, `cargo clean`,
`rm -rf .zig-cache zig-out`, `go clean`). Shared toolchain caches (Go's build
cache, Zig's global cache, Cargo's registry) are kept. This is the same rule for
every language: "a fresh checkout, with the compiler already installed and
dependencies already fetched". Dependency builds are not part of the metric,
because AltBench uses only standard-library code.

### Timing

The harness times the build process externally with a monotonic clock. It does
not parse `/usr/bin/time`, so build output cannot corrupt the sample. A failed
command is recorded as a failure; no time is recorded for it. The harness
checks that the binary was produced, runs it, and validates the output. Every
measurement is repeated and the median is reported.

### Runtime measurement

Runtime is measured by executing the program as a normal CLI process, with
stdout discarded and stderr captured. The invocation is identical for every
language:

| Workload | Arguments | Purpose |
|---|---|---|
| `single` | `--length 32 --count 1 --format plain` | one password; mostly startup |
| `bulk` | `--length 32 --count 20000 --format plain` | generation and output at scale |

Each workload is run once with captured output and validated before its timed
runs. The median wall-clock time over `--runtime-samples` runs (default 5) is
reported. `Bulk net` is the bulk median minus the single median; `Bulk pwd/s`
uses that net time. Both are estimates of work beyond process startup, not
paired per-run measurements.

Runtime failures are recorded like build failures: a non-zero exit status or a
timeout is a failure, and no time is recorded for that sample.
