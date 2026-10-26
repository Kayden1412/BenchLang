# AltBench results

Generated 2026-10-26T09:26:39+00:00 on `Linux-6.17.0-PRoot-Distro-aarch64-with-glibc2.41`.

Median of up to 3 samples per build phase and 5 per runtime workload. Builds and runtime runs are timed externally with a monotonic clock.

| Language | Mode | Cold (ms) | Noop (ms) | Edit (ms) | Edit / Cold | Status |
|---|---|---:|---:|---:|---:|---|
| C (cc) | file | 1609.7 | 102.9 | 1079.3 | 0.67× | ok |
| C (gcc) | file | 1604.7 | 121.7 | 1076.6 | 0.67× | ok |
| C++ (c++) | file | 7889.3 | 97.4 | 1734.6 | 0.22× | ok |
| C++ (g++) | file | 7121.3 | 112.7 | 1242.9 | 0.17× | ok |
| Rust | full | 3786.0 | 235.9 | 2959.8 | 0.78× | ok |
| Zig | full | 92249.2 | 37868.3 | 59771.6 | 0.65× | ok |
| Go | program | — | — | — | — | skipped (go) |
| Python | interpreted | 370.0 | 349.3 | 271.5 | 0.73× | ok |
| JavaScript (Node.js) | interpreted | 552.3 | 514.4 | 564.4 | 1.02× | ok |

Command-spawn floor: 11.6 ms (median of spawning `/bin/true`). Very small no-op numbers are dominated by this floor.

## Runtime

External wall-clock time of complete CLI invocations, with output discarded. The `single` workload generates one password; `bulk` generates 20000 at length 32. `Bulk net` subtracts the median single run from the median bulk run; it is an estimate, not a per-run measurement. Throughput uses that net time.

| Language | Single (ms) | Bulk (ms) | Bulk net (ms) | Bulk pwd/s | Status |
|---|---:|---:|---:|---:|---|
| C (cc) | 67.7 | 163.6 | 95.9 | 208,551 | ok |
| C (gcc) | 49.4 | 173.0 | 123.6 | 161,812 | ok |
| C++ (c++) | 53.5 | 206.0 | 152.5 | 131,148 | ok |
| C++ (g++) | 57.8 | 211.2 | 153.4 | 130,378 | ok |
| Rust | 57.9 | 2175.9 | 2118.0 | 9,443 | ok |
| Zig | 8.6 | 1846.1 | 1837.5 | 10,884 | ok |
| Python | 211.1 | 5783.9 | 5572.8 | 3,589 | ok |
| JavaScript (Node.js) | 746.5 | 1562.7 | 816.2 | 24,504 | ok |

## Toolchains

- `c++`: clang version 21.1.8
- `cargo`: cargo 1.98.0 (797e8a9bc 2026-08-05) (built from a source tarball)
- `cc`: clang version 21.1.8
- `g++`: clang version 21.1.8
- `gcc`: clang version 21.1.8
- `make`: GNU Make 4.4.1
- `node`: v24.17.0
- `python3`: Python 3.13.5
- `zig`: 0.16.0

Modes:

- `file` — the toolchain recompiles changed files and relinks (Make/C/C++).
- `program` — the toolchain recompiles a package/program unit; dependency caches may still be reused (Go).
- `full` — the release build is a whole-program rebuild, so `edit` is expected to be close to `cold` (Rust release, Zig release).
- `interpreted` — there is no native build; the `build` command is a syntax/bytecode check and the numbers measure that check only (Python, JavaScript).

`cold` removes first-party artifacts only; compiler/toolchain caches are kept. A failed build is recorded as a failure, never as a time.

