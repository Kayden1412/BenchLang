# AltBench

AltBench is a small, self-contained benchmark for **compile, edit/build-cycle,
and runtime performance**, built around one realistic CLI program: `passgen`, a
system-CSPRNG password generator.

Every language implements the same program and receives the same edit, so
build, edit, and runtime costs can be compared under one set of rules. See
[`SPEC.md`](SPEC.md) for the program contract and the exact definitions of
`cold`, `noop`, `edit`, and the runtime workloads.

## Design goals

Compile-time measurements commonly mix together things that should be separate:

* a "cold" build that does not actually remove previous artifacts;
* dependencies, profile-guided optimization, and first-party code in one number;
* per-file incremental builds and whole-program release rebuilds in the same
  "incremental" column;
* failed builds that are logged and then timed anyway.

AltBench measures three separate build events, plus runtime workloads, and
reports them separately:

| Phase | What happens |
|---|---|
| `cold` | remove first-party build artifacts, then build |
| `noop` | build again with no source change |
| `edit` | change one leaf file (`rng.*`), then build |

The edit is the same logical change in every language: a marker comment in the
CSPRNG module. Languages whose release mode is a whole-program rebuild are
labelled `full`, so their `edit` time being close to `cold` is visible instead
of being presented as "incremental".

## Quick start

Requirements: Python 3.9+ to run the harness, and whichever language toolchains
you want to measure. Missing toolchains are skipped, not failed.

```sh
# from this directory
cd /path/to/altbench
python3 harness.py --list

# measure everything available: 3 build samples per phase, 5 runtime samples
python3 harness.py

# more samples of everything
python3 harness.py --only c-cc,rust,zig --samples 5 --runtime-samples 10

# build timings only
python3 harness.py --skip-runtime
```

The run writes:

* `results.json` — full data, including every raw build and runtime sample,
  validation result, and failure;
* `RESULTS.md` — compact build and runtime tables generated from that data.

A sample of the table formats:

| Language | Mode | Cold (ms) | Noop (ms) | Edit (ms) | Edit / Cold | Status |
|---|---|---:|---:|---:|---:|---|
| C (cc) | file | … | … | … | … | ok |
| Rust | full | … | … | … | … | ok |
| Zig | full | … | … | … | … | ok |

| Language | Single (ms) | Bulk (ms) | Bulk net (ms) | Bulk pwd/s | Status |
|---|---:|---:|---:|---:|---|
| C (cc) | … | … | … | … | ok |
| Rust | … | … | … | … | ok |
| Zig | … | … | … | … | ok |

### Continuous integration

[`.github/workflows/altbench.yml`](.github/workflows/altbench.yml) installs
C/C++, Rust, Zig, Go, Python, and Node.js on Ubuntu, runs a shortened benchmark
(`--samples 1 --runtime-samples 3`), fails unless every configured language
passes both build and runtime validation, and uploads `results.json` and
`RESULTS.md` as artifacts.

## Measurement rules

### What `cold` removes

Only first-party build artifacts. Toolchain and dependency caches are kept, so
the metric answers: "a fresh checkout, with the compiler installed and
dependencies already available".

| Language | Removed for `cold` |
|---|---|
| C / C++ | `passgen`, `*.o` |
| Rust | `target/` (`cargo clean` equivalent) |
| Zig | `.zig-cache/`, `zig-out/` |
| Go | the output binary (Go's shared build cache is kept) |
| Python | `__pycache__/` |
| JavaScript | nothing (no build artifacts) |

The clean is done by the harness itself, before the timer starts. It is not
part of the reported build time.

### Timing

* The build commands are timed **externally** with `time.perf_counter()`.
  `/usr/bin/time` output is never parsed, so compiler output cannot corrupt a
  sample.
* A failed build is recorded as a failure. It is never recorded as a time.
* A build that does not produce the expected binary is a failure.
* After every successful build the harness runs the program and validates its
  output before accepting the sample.
* Each phase is repeated `--samples` times (default 3) and the **median** is
  reported. Raw samples and min/max are in `results.json`.
* The spawn floor (median time to run `/bin/true`) is recorded so tiny no-op
  numbers are not over-interpreted.

### Runtime

Runtime is measured by executing the binary from the last successful build
phase (or the source, for interpreted implementations) as a normal CLI process,
with stdout discarded and stderr captured. The edit is a comment-only change, so
that binary has the same behaviour as the baseline.

Two workloads are configured in `languages.json`:

| Workload | Invocation | Purpose |
|---|---|---|
| `single` | `--length 32 --count 1 --format plain` | one password; mostly process startup |
| `bulk` | `--length 32 --count 20000 --format plain` | generation and output at scale |

Each workload is first run once with captured output and validated with the same
property checks used for correct builds. It is then run `--runtime-samples` times
(default 5) and the **median wall-clock time** is reported.

`Bulk net` is `bulk median − single median`. It is an estimate of the work
beyond process startup, not a paired per-run measurement. `Bulk pwd/s` is the
bulk password count divided by that net time. Raw times, failures, and
validation errors are in `results.json`.

### Validation

Password output is intentionally non-deterministic, so there is no golden
string. Instead the harness checks properties:

* the requested number of passwords, each at the requested length;
* every character is in the requested pools;
* every selected class appears at least once in every password;
* `--no-ambiguous` removes `l`, `I`, `1`, `O`, `0`;
* the FNV-1a checksum matches the emitted passwords;
* JSON and plain output both work;
* invalid arguments exit with status 2;
* `--help` exits with status 0;
* two independent runs produce different output (a CSPRNG sanity check).

The full property suite runs once before build timing, and a smaller smoke check
runs after every timed build. Runtime workloads are validated once before their
timed runs.

## Program and randomness

`passgen` has argument parsing, validation, character-class policy, several
modules, two output formats, a checksum, and a CSPRNG. Standard library only:
no package fetch is part of the measurement.

There is no `--seed` flag. A password generator with a reproducible seed is a
security bug, not a feature. Every implementation uses the operating system's
cryptographic random source. All of them fill the same 4096-byte buffer and
consume little-endian 32-bit words, refilling only when fewer than 4 bytes
remain:

| Language | Buffer source |
|---|---|
| C / C++ | `getrandom(2)`, `arc4random_buf` on Android, `/dev/urandom` fallback |
| Rust | `/dev/urandom` |
| Go | `crypto/rand` |
| Zig | `Io.randomSecure` |
| Python | `secrets` |
| JavaScript | `node:crypto` `randomFillSync` |

The shared buffer is deliberate: identical buffer size, word width, byte order,
and refill rule mean every language consumes the CSPRNG in the same pattern, so
runtime differences reflect language/runtime overhead instead of different
numbers of kernel calls.

Uniform selection uses rejection sampling over a 32-bit word with
`limit = (2^32 / n) * n`, and the final password is shuffled with Fisher-Yates.
No `rand()`, `Math.random()`, seeded PRNG, or time-based seed is used.

## Language modes

| Mode | Meaning | Current entries |
|---|---|---|
| `file` | recompiles changed files, then relinks | C, C++ |
| `program` | recompiles a package/program unit, may reuse dependency caches | Go |
| `full` | release build is a whole-program rebuild | Rust, Zig |
| `interpreted` | no native build; `build` is a syntax/bytecode check | Python, JavaScript |

`interpreted` numbers measure the check command, not a native compiler. For
Python that is `python3 -m compileall`; for JavaScript it is a single Node
process that parses both source files. Interpreter startup is part of those
numbers and is usually larger than the parse itself.

## Configuration

Top-level settings in [`languages.json`](languages.json) control the default
sample counts and the runtime workloads:

```json
{
  "samples": 3,
  "runtime": {
    "samples": 5,
    "workloads": [
      {
        "id": "bulk",
        "args": ["--length", "32", "--count", "20000", "--format", "plain"],
        "length": 32,
        "count": 20000,
        "format": "plain",
        "classes": ["lower", "upper", "digit", "symbol"],
        "no_ambiguous": false
      }
    ]
  },
  "languages": [ ... ]
}
```

Each runtime workload declares the invocation, plus the expected output
properties used for validation. The Markdown summary uses the workload ids
`single` and `bulk`; all configured workloads are recorded in `results.json`.

Languages are declared in the same file. Each entry has:

```json
{
  "id": "example",
  "label": "Example",
  "mode": "file",
  "directory": "example",
  "build": [["examplec", "build"]],
  "build_env": {"CC": "examplec"},
  "clean_paths": ["build", "passgen"],
  "binary": "build/passgen",
  "run": ["./build/passgen"],
  "edit_file": "src/rng.*",
  "marker": "ALT_RNG_REV_0",
  "requires": ["examplec", "make"]
}
```

* `build` is a list of argv lists, run in order and timed as one sample.
* `build_env` adds environment variables for the build only.
* `clean_paths` are removed before each `cold` sample.
* `binary`: set to `null` when there is no artifact to check.
* `edit_file` must contain `marker` exactly once.
* `requires` is checked with `shutil.which`; missing tools produce `skipped`.

Runtime workloads are shared by every language, so the comparison uses exactly
the same arguments and output expectations.

To add a language, implement the contract in `SPEC.md`, add a directory, and
add a config entry. The harness does not need language-specific code.

## Caveats

* **Runtime is end-to-end CLI wall clock.** It includes process startup,
  argument parsing, CSPRNG calls, generation, checksumming, and writing 20000
  lines to `/dev/null`. It is not a pure algorithmic benchmark. The `single`
  workload exists so startup can be separated from bulk work, approximately.
* **`Bulk net` subtracts medians, not paired runs.** It is a useful estimate,
  not an exact decomposition; noise in either median affects it.
* **Runtime includes the CSPRNG.** Buffer refills and entropy-source behaviour
  are part of the measured program, not an artefact to remove. All languages
  use the same buffer size and refill rule, so this cost is comparable.
* **Toolchain caches are intentionally kept.** A "cold" run is not a
  compiler-from-scratch run, and it is not a dependency download benchmark.
* **The OS page cache is not dropped.** Removing build artifacts is
  reproducible; dropping page cache requires root and would distort container
  I/O. Repeated samples and medians reduce this noise.
* **Container/proot filesystems are slow and noisy.** On the machine used for
  the recorded run, compiler process startup alone is a large fraction of a
  small C build; the spawn floor is reported for this reason.
* **Zig's `.zig-cache` is a real compiler cache.** Removing it for `cold` can
  force a large rebuild of std, which is why Zig cold times can be much larger
  than a no-op build. That is reported as `full`, not hidden as incremental.
* **`gcc`/`g++` may be aliases.** Some distributions (including Termux) point
  `gcc` at Clang. Both configured compiler entries are measured; check the
  build environment before comparing them as different compilers.
* **Go was not installed on the machine used for the recorded run.** Its entry
  is implemented and configured, but the harness skipped it there.
* **Random output means validation is property-based.** A rare statistical
  property failure would be reported as a validation failure; the tests use
  properties that hold for every valid output, not probabilistic ones.

## Interpreting the numbers

Compare phases within a language before comparing languages.

Build:

* `edit / cold` close to `1.0` means the edit triggers a whole-program rebuild.
* A much smaller `edit / cold` means changed-file or package-level reuse.
* `noop` near the command-spawn floor means the toolchain has a working
  up-to-date check; a `noop` close to `cold` means it always rebuilds.

Runtime:

* A large `single` time is mostly process and interpreter startup, especially
  for Python and JavaScript.
* Compare `bulk net` and `bulk pwd/s` rather than raw `bulk` when startup costs
  differ substantially between languages.
* Runtime is dominated by generation, buffered CSPRNG consumption, and output
  handling, so differences usually reflect interpreter/allocator/IO overhead
  more than the entropy source itself.

Absolute times still depend on the machine, filesystem, and toolchain versions,
so compare runs only when those are comparable.
