#!/usr/bin/env python3
"""AltBench: measure cold, no-op, and edit builds of the `passgen` program.

The harness times build commands externally with a monotonic clock, records
failures instead of pretending they are timings, and validates that each build
produced a working password generator before accepting a sample.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "languages.json"
DEFAULT_OUTPUT = ROOT / "results.json"
DEFAULT_MARKDOWN = ROOT / "RESULTS.md"

CLASS_ORDER = ("lower", "upper", "digit", "symbol")
POOLS = {
    "lower": "abcdefghijklmnopqrstuvwxyz",
    "upper": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "digit": "0123456789",
    "symbol": "!@#$%^&*()-_=+[]{};:,.?/",
}
AMBIGUOUS = frozenset("lI1O0")
PHASES = ("cold", "noop", "edit")


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def fnv1a(data: bytes) -> int:
    value = 2166136261
    for byte in data:
        value ^= byte
        value = (value * 16777619) & 0xFFFFFFFF
    return value


def expected_pools(classes: list[str], no_ambiguous: bool) -> list[tuple[str, str]]:
    pools = []
    for name in CLASS_ORDER:
        if name not in classes:
            continue
        chars = POOLS[name]
        if no_ambiguous:
            chars = "".join(ch for ch in chars if ch not in AMBIGUOUS)
        pools.append((name, chars))
    return pools


def parse_plain(stdout: str) -> tuple[list[str], str]:
    lines = stdout.splitlines()
    if not lines:
        raise ValueError("empty output")
    checksum_line = lines[-1]
    if not checksum_line.startswith("checksum="):
        raise ValueError("last line is not a checksum line")
    checksum = checksum_line.split("=", 1)[1]
    return lines[:-1], checksum


def parse_json(stdout: str) -> tuple[list[str], str]:
    document = json.loads(stdout)
    if set(document) != {"passwords", "checksum"}:
        raise ValueError("JSON keys must be exactly passwords and checksum")
    passwords = document["passwords"]
    checksum = document["checksum"]
    if not isinstance(passwords, list) or not all(isinstance(p, str) for p in passwords):
        raise ValueError("passwords must be a list of strings")
    if not isinstance(checksum, str):
        raise ValueError("checksum must be a string")
    return passwords, checksum


def check_output(
    stdout: str,
    output_format: str,
    length: int,
    count: int,
    classes: list[str],
    no_ambiguous: bool,
) -> list[str]:
    errors: list[str] = []

    try:
        if output_format == "json":
            passwords, checksum = parse_json(stdout)
        else:
            passwords, checksum = parse_plain(stdout)
    except (ValueError, json.JSONDecodeError) as exc:
        return [f"could not parse output: {exc}"]

    if len(passwords) != count:
        errors.append(f"expected {count} passwords, got {len(passwords)}")

    pools = expected_pools(classes, no_ambiguous)
    if len(pools) != len(classes):
        errors.append("internal: requested class is unknown")

    allowed = set("".join(chars for _, chars in pools))
    for index, password in enumerate(passwords):
        if len(password) != length:
            errors.append(
                f"password {index} has length {len(password)}, expected {length}"
            )
        outside = sorted(set(password) - allowed)
        if outside:
            errors.append(
                f"password {index} contains characters outside the pools: {outside!r}"
            )
        if no_ambiguous:
            present = sorted(set(password) & AMBIGUOUS)
            if present:
                errors.append(
                    f"password {index} contains ambiguous characters: {present!r}"
                )
        for name, chars in pools:
            if not any(ch in chars for ch in password):
                errors.append(f"password {index} is missing class {name!r}")

    if not re.fullmatch(r"[0-9a-f]{8}", checksum):
        errors.append(f"checksum {checksum!r} is not 8 lowercase hex digits")

    payload = "".join(password + "\n" for password in passwords).encode("utf-8")
    expected_checksum = f"{fnv1a(payload):08x}"
    if checksum != expected_checksum:
        errors.append(
            f"checksum {checksum!r} does not match FNV-1a of the output "
            f"({expected_checksum})"
        )

    return errors


class Language:
    def __init__(self, spec: dict, config_dir: Path):
        self.spec = spec
        self.id = spec["id"]
        self.label = spec["label"]
        self.mode = spec["mode"]
        self.directory = config_dir / spec["directory"]
        self.build_commands = spec["build"]
        self.clean_paths = spec.get("clean_paths", [])
        self.binary = spec.get("binary")
        self.run_command = spec["run"]
        self.edit_file = spec.get("edit_file")
        self.marker = spec.get("marker")
        self.requires = spec.get("requires", [])
        self.build_env = spec.get("build_env", {})

    def missing_requirements(self) -> list[str]:
        return [name for name in self.requires if shutil.which(name) is None]

    def environment(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(self.build_env)
        env.setdefault("LC_ALL", "C")
        env.setdefault("TERM", "dumb")
        env.setdefault("NO_COLOR", "1")
        return env

    def clean(self) -> None:
        for relative in self.clean_paths:
            path = self.directory / relative
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            elif path.exists() or path.is_symlink():
                path.unlink()

        if self.binary:
            binary_path = self.directory / self.binary
            if binary_path.is_file() or binary_path.is_symlink():
                binary_path.unlink()


def run_program(language: Language, args: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*language.run_command, *args],
        cwd=language.directory,
        env=language.environment(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def timed_build(language: Language, timeout: int) -> tuple[bool, float, dict | None]:
    """Run the configured build commands and time the whole sequence."""
    env = language.environment()
    started = time.perf_counter()
    elapsed_ms = 0.0

    for command in language.build_commands:
        try:
            process = subprocess.run(
                command,
                cwd=language.directory,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return False, elapsed_ms, {
                "kind": "missing-command",
                "command": " ".join(command),
                "message": f"executable not found: {command[0]}",
            }
        except subprocess.TimeoutExpired:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return False, elapsed_ms, {
                "kind": "timeout",
                "command": " ".join(command),
                "message": f"timed out after {timeout}s",
            }

        if process.returncode != 0:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return False, elapsed_ms, {
                "kind": "build-failed",
                "command": " ".join(command),
                "returncode": process.returncode,
                "stdout_tail": process.stdout[-1500:],
                "stderr_tail": process.stderr[-1500:],
            }

    elapsed_ms = (time.perf_counter() - started) * 1000.0

    if language.binary:
        binary_path = language.directory / language.binary
        if not binary_path.is_file():
            return False, elapsed_ms, {
                "kind": "missing-binary",
                "message": f"build succeeded but {language.binary} was not produced",
            }

    return True, elapsed_ms, None


def validate_program(language: Language, full: bool, timeout: int) -> dict:
    checks: list[dict] = []
    failures: list[str] = []

    if full:
        cases = [
            {
                "name": "default plain",
                "args": [],
                "format": "plain",
                "length": 16,
                "count": 5,
                "classes": list(CLASS_ORDER),
                "no_ambiguous": False,
            },
            {
                "name": "json, no ambiguous",
                "args": ["--length", "24", "--count", "3", "--no-ambiguous", "--format", "json"],
                "format": "json",
                "length": 24,
                "count": 3,
                "classes": list(CLASS_ORDER),
                "no_ambiguous": True,
            },
            {
                "name": "class subset",
                "args": ["--length", "4", "--count", "2", "--classes", "lower,digit", "--format", "json"],
                "format": "json",
                "length": 4,
                "count": 2,
                "classes": ["lower", "digit"],
                "no_ambiguous": False,
            },
        ]
    else:
        cases = [
            {
                "name": "smoke: json, no ambiguous",
                "args": ["--length", "20", "--count", "4", "--no-ambiguous", "--format", "json"],
                "format": "json",
                "length": 20,
                "count": 4,
                "classes": list(CLASS_ORDER),
                "no_ambiguous": True,
            }
        ]

    for case in cases:
        errors: list[str] = []
        try:
            process = run_program(language, case["args"], timeout)
        except subprocess.TimeoutExpired:
            errors.append(f"program timed out after {timeout}s")
        else:
            if process.returncode != 0:
                errors.append(
                    f"exit status {process.returncode}; stderr: {process.stderr.strip()[:500]}"
                )
            else:
                errors.extend(
                    check_output(
                        process.stdout,
                        case["format"],
                        case["length"],
                        case["count"],
                        case["classes"],
                        case["no_ambiguous"],
                    )
                )

        checks.append({"name": case["name"], "ok": not errors, "errors": errors})
        failures.extend(f"{case['name']}: {error}" for error in errors)

    if full:
        try:
            help_process = run_program(language, ["--help"], timeout)
            if help_process.returncode != 0 or "usage:" not in help_process.stdout.lower():
                failures.append("--help did not print usage with exit status 0")
                checks.append({"name": "--help", "ok": False, "errors": ["bad help output"]})
            else:
                checks.append({"name": "--help", "ok": True, "errors": []})
        except subprocess.TimeoutExpired:
            failures.append("--help timed out")
            checks.append({"name": "--help", "ok": False, "errors": ["timeout"]})

        try:
            invalid_process = run_program(language, ["--length", "0"], timeout)
            invalid_ok = (
                invalid_process.returncode == 2
                and bool(invalid_process.stderr.strip())
            )
            checks.append(
                {
                    "name": "invalid length exits 2",
                    "ok": invalid_ok,
                    "errors": [] if invalid_ok else [
                        f"exit status {invalid_process.returncode}, stderr {invalid_process.stderr.strip()[:200]!r}"
                    ],
                }
            )
            if not invalid_ok:
                failures.append("invalid --length did not exit 2 with a stderr message")
        except subprocess.TimeoutExpired:
            failures.append("invalid-argument run timed out")
            checks.append({"name": "invalid length exits 2", "ok": False, "errors": ["timeout"]})

        try:
            first = run_program(language, ["--length", "24", "--count", "2"], timeout)
            second = run_program(language, ["--length", "24", "--count", "2"], timeout)
            distinct = (
                first.returncode == 0
                and second.returncode == 0
                and first.stdout != second.stdout
            )
            checks.append(
                {
                    "name": "two runs differ (CSPRNG)",
                    "ok": distinct,
                    "errors": [] if distinct else ["two runs produced identical output"],
                }
            )
            if not distinct:
                failures.append("two runs produced identical output; CSPRNG check failed")
        except subprocess.TimeoutExpired:
            failures.append("CSPRNG two-run check timed out")
            checks.append({"name": "two runs differ (CSPRNG)", "ok": False, "errors": ["timeout"]})

    return {"ok": not failures, "checks": checks, "errors": failures}


def measure_language(language: Language, samples: int, timeout: int) -> dict:
    result: dict = {
        "id": language.id,
        "label": language.label,
        "mode": language.mode,
        "directory": str(language.directory.relative_to(ROOT)),
        "build_commands": language.build_commands,
        "build_env": language.build_env,
        "clean_paths": language.clean_paths,
        "binary": language.binary,
        "run": language.run_command,
        "requires": language.requires,
        "status": "unknown",
        "phases": {},
    }

    missing = language.missing_requirements()
    if missing:
        result["status"] = "skipped"
        result["missing_requirements"] = missing
        log(f"[{language.id}] skipped, missing: {', '.join(missing)}")
        return result

    if not language.directory.is_dir():
        result["status"] = "failed"
        result["setup_error"] = f"missing directory: {language.directory}"
        return result

    edit_path = None
    original = None
    if language.edit_file:
        edit_path = language.directory / language.edit_file
        try:
            original = edit_path.read_text()
        except OSError as exc:
            result["status"] = "failed"
            result["setup_error"] = f"cannot read edit file: {exc}"
            return result

        if not language.marker or original.count(language.marker) != 1:
            result["status"] = "failed"
            result["setup_error"] = (
                f"edit marker must occur exactly once in {language.edit_file}"
            )
            return result

    result["edit"] = {
        "file": language.edit_file,
        "marker": language.marker,
    }

    phases = {
        phase: {"samples_ms": [], "failures": []} for phase in PHASES
    }
    result["phases"] = phases

    log(f"[{language.id}] warmup: clean + build")
    language.clean()
    ok, elapsed, failure = timed_build(language, timeout)
    if not ok:
        failure = dict(failure or {})
        failure.update({"sample": "warmup", "phase": "warmup"})
        result["status"] = "failed"
        result["setup_error"] = "warmup build failed"
        result["warmup_failure"] = failure
        return result

    log(f"[{language.id}] warmup build ok ({elapsed:.1f} ms); validating")
    validation = validate_program(language, full=True, timeout=min(timeout, 120))
    result["validation"] = validation
    if not validation["ok"]:
        result["status"] = "failed"
        result["setup_error"] = "validation failed"
        log(f"[{language.id}] validation failed")
        return result

    def record(phase: str, sample: int) -> None:
        log(f"[{language.id}] sample {sample + 1}/{samples}: {phase}")
        ok, elapsed, failure = timed_build(language, timeout)
        if not ok:
            failure = dict(failure or {})
            failure.update({"sample": sample + 1, "phase": phase})
            phases[phase]["failures"].append(failure)
            log(f"[{language.id}] {phase} build failed")
            return

        quick = validate_program(language, full=False, timeout=min(timeout, 120))
        if not quick["ok"]:
            phases[phase]["failures"].append(
                {
                    "kind": "validation",
                    "sample": sample + 1,
                    "phase": phase,
                    "build_ms": round(elapsed, 1),
                    "errors": quick["errors"],
                }
            )
            log(f"[{language.id}] {phase} validation failed")
            return

        phases[phase]["samples_ms"].append(round(elapsed, 1))
        log(f"[{language.id}] {phase}: {elapsed:.1f} ms")

    try:
        for sample in range(samples):
            language.clean()
            record("cold", sample)

            record("noop", sample)

            assert edit_path is not None and original is not None
            edited = original.replace(language.marker, f"ALT_RNG_REV_{sample + 1}")
            edit_path.write_text(edited)
            try:
                record("edit", sample)
            finally:
                edit_path.write_text(original)
    finally:
        if edit_path is not None and original is not None:
            edit_path.write_text(original)

    for phase in PHASES:
        values = phases[phase]["samples_ms"]
        phases[phase]["median_ms"] = round(statistics.median(values), 1) if values else None
        phases[phase]["min_ms"] = round(min(values), 1) if values else None
        phases[phase]["max_ms"] = round(max(values), 1) if values else None
        phases[phase]["successes"] = len(values)
        phases[phase]["failures_count"] = len(phases[phase]["failures"])

    any_success = any(phases[phase]["samples_ms"] for phase in PHASES)
    any_failure = any(phases[phase]["failures"] for phase in PHASES)
    if not any_success:
        result["status"] = "failed"
    elif any_failure:
        result["status"] = "partial"
    else:
        result["status"] = "ok"

    log(f"[{language.id}] done: {result['status']}")
    return result


def measure_runtime(
    language: Language,
    runtime_config: dict,
    samples: int,
    timeout: int,
) -> dict:
    """Measure wall-clock time of real CLI invocations, external to the process."""
    workloads = []

    for spec in runtime_config["workloads"]:
        workload = {
            "id": spec["id"],
            "args": spec["args"],
            "count": spec.get("count"),
            "length": spec.get("length"),
            "samples_ms": [],
            "failures": [],
            "validation_errors": [],
        }

        log(f"[{language.id}] runtime {spec['id']}: validation")
        try:
            process = run_program(language, spec["args"], timeout)
        except subprocess.TimeoutExpired:
            workload["validation_errors"].append(f"program timed out after {timeout}s")
        else:
            if process.returncode != 0:
                workload["validation_errors"].append(
                    f"exit status {process.returncode}; "
                    f"stderr: {process.stderr.strip()[:500]}"
                )
            else:
                workload["validation_errors"].extend(
                    check_output(
                        process.stdout,
                        spec["format"],
                        spec["length"],
                        spec["count"],
                        spec["classes"],
                        spec.get("no_ambiguous", False),
                    )
                )

        if not workload["validation_errors"]:
            env = language.environment()
            for sample in range(samples):
                log(
                    f"[{language.id}] runtime {spec['id']} "
                    f"{sample + 1}/{samples}"
                )
                started = time.perf_counter()
                try:
                    process = subprocess.run(
                        [*language.run_command, *spec["args"]],
                        cwd=language.directory,
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=timeout,
                    )
                except subprocess.TimeoutExpired:
                    workload["failures"].append(
                        {
                            "kind": "timeout",
                            "sample": sample + 1,
                            "message": f"timed out after {timeout}s",
                        }
                    )
                    log(f"[{language.id}] runtime {spec['id']} timed out")
                    continue

                elapsed_ms = (time.perf_counter() - started) * 1000.0
                if process.returncode != 0:
                    workload["failures"].append(
                        {
                            "kind": "exit",
                            "sample": sample + 1,
                            "returncode": process.returncode,
                            "stderr_tail": process.stderr[-1500:],
                        }
                    )
                    log(f"[{language.id}] runtime {spec['id']} failed")
                    continue

                workload["samples_ms"].append(round(elapsed_ms, 1))
                log(
                    f"[{language.id}] runtime {spec['id']}: "
                    f"{elapsed_ms:.1f} ms"
                )

        values = workload["samples_ms"]
        workload["median_ms"] = (
            round(statistics.median(values), 1) if values else None
        )
        workload["min_ms"] = round(min(values), 1) if values else None
        workload["max_ms"] = round(max(values), 1) if values else None
        workload["successes"] = len(values)
        workload["failures_count"] = len(workload["failures"])
        workloads.append(workload)

    if any(workload["validation_errors"] for workload in workloads):
        status = "failed"
    elif any(workload["failures"] for workload in workloads):
        status = "partial"
    elif all(workload["samples_ms"] for workload in workloads):
        status = "ok"
    else:
        status = "failed"

    log(f"[{language.id}] runtime done: {status}")
    return {"samples": samples, "status": status, "workloads": workloads}


def command_overhead(samples: int = 5) -> float | None:
    """Approximate the floor of a measured sample: spawning a trivial process."""
    true_command = shutil.which("true")
    if true_command is None:
        return None

    values = []
    for _ in range(samples):
        started = time.perf_counter()
        try:
            subprocess.run(
                [true_command],
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        values.append((time.perf_counter() - started) * 1000.0)
    return round(statistics.median(values), 1)


def tool_version(name: str) -> str | None:
    """Best-effort version line for a required toolchain command."""
    for args in ([name, "--version"], [name, "version"]):
        try:
            process = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=15,
                env={**os.environ, "LC_ALL": "C", "NO_COLOR": "1"},
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        if process.returncode == 0:
            text = (process.stdout or process.stderr).strip()
            if text:
                return text.splitlines()[0]

    return None


def format_ms(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}"


def phase_value(result: dict, phase: str, field: str = "median_ms") -> float | None:
    phase_data = result.get("phases", {}).get(phase)
    if not phase_data:
        return None
    return phase_data.get(field)


def runtime_workload(result: dict, workload_id: str) -> dict | None:
    runtime = result.get("runtime") or {}
    for workload in runtime.get("workloads", []):
        if workload.get("id") == workload_id:
            return workload
    return None


def format_rate(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f}"


def render_markdown(report: dict) -> str:
    settings = report["settings"]
    if settings.get("runtime_enabled"):
        sample_sentence = (
            f"Median of up to {settings['samples']} samples per build phase and "
            f"{settings.get('runtime_samples')} per runtime workload. Builds and "
            "runtime runs are timed externally with a monotonic clock."
        )
    else:
        sample_sentence = (
            f"Median of up to {settings['samples']} samples per build phase. "
            "Builds are timed externally with a monotonic clock."
        )

    lines = [
        "# AltBench results",
        "",
        f"Generated {report['generated_at']} on `{report['host']['platform']}`.",
        "",
        sample_sentence,
        "",
        "| Language | Mode | Cold (ms) | Noop (ms) | Edit (ms) | Edit / Cold | Status |",
        "|---|---|---:|---:|---:|---:|---|",
    ]

    for language in report["languages"]:
        cold = phase_value(language, "cold")
        noop = phase_value(language, "noop")
        edit = phase_value(language, "edit")
        ratio = "—"
        if cold and edit is not None:
            ratio = f"{edit / cold:.2f}×"

        status = language["status"]
        if status == "skipped" and language.get("missing_requirements"):
            status = f"skipped ({', '.join(language['missing_requirements'])})"

        lines.append(
            f"| {language['label']} | {language['mode']} | "
            f"{format_ms(cold)} | {format_ms(noop)} | {format_ms(edit)} | "
            f"{ratio} | {status} |"
        )

    lines.extend(
        [
            "",
            f"Command-spawn floor: "
            f"{format_ms(settings.get('command_overhead_ms'))} ms "
            "(median of spawning `/bin/true`). Very small no-op numbers are "
            "dominated by this floor.",
            "",
        ]
    )

    runtime_languages = [
        language for language in report["languages"] if language.get("runtime")
    ]
    if runtime_languages:
        lines.extend(
            [
                "## Runtime",
                "",
                "External wall-clock time of complete CLI invocations, with output "
                "discarded. The `single` workload generates one password; `bulk` "
                "generates 20000 at length 32. `Bulk net` subtracts the median "
                "single run from the median bulk run; it is an estimate, not a "
                "per-run measurement. Throughput uses that net time.",
                "",
                "| Language | Single (ms) | Bulk (ms) | Bulk net (ms) | Bulk pwd/s | Status |",
                "|---|---:|---:|---:|---:|---|",
            ]
        )

        for language in runtime_languages:
            runtime = language["runtime"]
            single = runtime_workload(language, "single")
            bulk = runtime_workload(language, "bulk")
            single_ms = single.get("median_ms") if single else None
            bulk_ms = bulk.get("median_ms") if bulk else None

            net_ms = None
            if single_ms is not None and bulk_ms is not None:
                net_ms = max(bulk_ms - single_ms, 0.0)

            rate = None
            if net_ms and bulk and bulk.get("count"):
                rate = bulk["count"] / (net_ms / 1000.0)

            lines.append(
                f"| {language['label']} | {format_ms(single_ms)} | "
                f"{format_ms(bulk_ms)} | {format_ms(net_ms)} | "
                f"{format_rate(rate)} | {runtime['status']} |"
            )

        lines.append("")

    toolchains = report.get("toolchains", {})
    if toolchains:
        lines.extend(["## Toolchains", ""])
        for name, version in toolchains.items():
            lines.append(f"- `{name}`: {version}")
        lines.append("")

    lines.extend(
        [
            "Modes:",
            "",
            "- `file` — the toolchain recompiles changed files and relinks "
            "(Make/C/C++).",
            "- `program` — the toolchain recompiles a package/program unit; "
            "dependency caches may still be reused (Go).",
            "- `full` — the release build is a whole-program rebuild, so `edit` "
            "is expected to be close to `cold` (Rust release, Zig release).",
            "- `interpreted` — there is no native build; the `build` command is a "
            "syntax/bytecode check and the numbers measure that check only "
            "(Python, JavaScript).",
            "",
            "`cold` removes first-party artifacts only; compiler/toolchain caches "
            "are kept. A failed build is recorded as a failure, never as a time.",
            "",
        ]
    )

    problems = []
    for language in report["languages"]:
        if language.get("setup_error"):
            problems.append(f"- **{language['label']}**: {language['setup_error']}")
            if language.get("warmup_failure"):
                failure = language["warmup_failure"]
                problems.append(
                    f"  - `{failure.get('command', '?')}`: "
                    f"{failure.get('stderr_tail') or failure.get('message') or 'failed'}"
                )
        for phase in PHASES:
            failures = language.get("phases", {}).get(phase, {}).get("failures", [])
            for failure in failures:
                detail = (
                    failure.get("stderr_tail")
                    or failure.get("message")
                    or "; ".join(failure.get("errors", []))
                    or failure.get("kind", "failed")
                )
                problems.append(
                    f"- **{language['label']}** {phase} sample "
                    f"{failure.get('sample')}: {detail}"
                )

        runtime = language.get("runtime") or {}
        for workload in runtime.get("workloads", []):
            for error in workload.get("validation_errors", []):
                problems.append(
                    f"- **{language['label']}** runtime {workload['id']} "
                    f"validation: {error}"
                )
            for failure in workload.get("failures", []):
                detail = (
                    failure.get("stderr_tail")
                    or failure.get("message")
                    or failure.get("kind", "failed")
                )
                problems.append(
                    f"- **{language['label']}** runtime {workload['id']} "
                    f"sample {failure.get('sample')}: {detail}"
                )

    if problems:
        lines.extend(["## Problems", ""])
        lines.extend(problems)
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Measure cold, no-op, and edit builds plus runtime of the AltBench passgen program."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help="language configuration JSON (default: languages.json)",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=None,
        help="build samples per phase (default: value from the config)",
    )
    parser.add_argument(
        "--runtime-samples",
        type=int,
        default=None,
        help="samples per runtime workload (default: value from the config)",
    )
    parser.add_argument(
        "--skip-runtime",
        action="store_true",
        help="only measure builds; skip runtime workloads",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="comma-separated language ids to run",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=900,
        help="per-command timeout in seconds for builds and runtime runs (default: 900)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JSON results path (default: results.json next to this script)",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=DEFAULT_MARKDOWN,
        help="Markdown results path (default: RESULTS.md next to this script)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list configured languages and exit",
    )
    args = parser.parse_args(argv)

    try:
        config = json.loads(args.config.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        log(f"cannot read config: {exc}")
        return 1

    languages = [Language(spec, args.config.parent) for spec in config["languages"]]
    by_id = {language.id: language for language in languages}

    if args.list:
        for language in languages:
            missing = language.missing_requirements()
            availability = "available" if not missing else f"missing: {', '.join(missing)}"
            print(
                f"{language.id:12} {language.label:24} mode={language.mode:12} "
                f"{availability}"
            )
        return 0

    selected = languages
    if args.only:
        wanted = [part.strip() for part in args.only.split(",") if part.strip()]
        unknown = [name for name in wanted if name not in by_id]
        if unknown:
            log(f"unknown language id(s): {', '.join(unknown)}")
            return 1
        selected = [by_id[name] for name in wanted]

    samples = args.samples if args.samples is not None else int(config.get("samples", 3))
    if samples < 1:
        log("--samples must be at least 1")
        return 1

    if not selected:
        log("no languages selected")
        return 1

    runtime_config = config.get("runtime")
    runtime_samples = None
    if runtime_config and not args.skip_runtime:
        runtime_samples = (
            args.runtime_samples
            if args.runtime_samples is not None
            else int(runtime_config.get("samples", 5))
        )
        if runtime_samples < 1:
            log("--runtime-samples must be at least 1")
            return 1

    overhead = command_overhead()
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    toolchain_names = sorted(
        {
            name
            for language in selected
            for name in language.requires
            if shutil.which(name) is not None
        }
    )
    toolchains = {}
    for name in toolchain_names:
        version = tool_version(name)
        if version:
            toolchains[name] = version

    results = []
    for language in selected:
        result = measure_language(language, samples, args.timeout)
        if (
            runtime_config
            and runtime_samples is not None
            and result["status"] in ("ok", "partial")
        ):
            result["runtime"] = measure_runtime(
                language,
                runtime_config,
                runtime_samples,
                args.timeout,
            )
        results.append(result)

    report = {
        "generated_at": started_at,
        "generator": "harness.py",
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
        "settings": {
            "samples": samples,
            "runtime_samples": runtime_samples,
            "runtime_enabled": runtime_config is not None and not args.skip_runtime,
            "timeout_s": args.timeout,
            "command_overhead_ms": overhead,
        },
        "toolchains": toolchains,
        "runtime_config": runtime_config if runtime_samples is not None else None,
        "methodology": {
            "cold": "remove first-party artifacts, then build",
            "noop": "build again with no source change",
            "edit": "replace the ALT_RNG_REV marker in the leaf rng file, then build",
            "clean_scope": "first-party artifacts only; shared toolchain caches are kept",
            "timing": "external monotonic clock around the build commands",
            "failures": "recorded as failures; no time is recorded for a failed build",
            "validation": "property-based checks, because password output is random",
            "runtime": "external wall clock of complete CLI invocations, output discarded",
        },
        "languages": results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    markdown = render_markdown(report)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(markdown + "\n")

    print(markdown)
    log(f"wrote {args.output} and {args.markdown}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        raise SystemExit(130)
