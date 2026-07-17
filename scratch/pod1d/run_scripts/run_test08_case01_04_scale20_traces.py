#!/usr/bin/env python3
"""Run isolated scale-20 test08 case01/case04 copies with analysis traces."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import resource
import signal
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean


SIZE_COLUMN = "dataSize(Byte)"
STRUCTURAL_FILES = ("node.csv", "topology.csv", "routing_table.csv")
CASE_INPUT_FILES = ("network_attribute.txt", *STRUCTURAL_FILES, "traffic.original.csv")
ANALYSIS_TRACE_VALUES = {
    "UB_TRACE_ENABLE": "true",
    "UB_TASK_TRACE_ENABLE": "true",
    "UB_TASK_SEGMENT_TRACE_ENABLE": "false",
    "UB_PACKET_TRACE_ENABLE": "true",
    "UB_PORT_TRACE_ENABLE": "true",
    "UB_QUEUE_TRACE_ENABLE": "true",
    "UB_FLOW_CONTROL_TRACE_ENABLE": "true",
    "UB_CONGESTION_CONTROL_TRACE_ENABLE": "false",
    "UB_RECORD_PKT_TRACE": "true",
    "UB_PARSE_TRACE_ENABLE": "true",
}
GLOBAL_LINE = re.compile(r'^(\s*global\s+)(\S+)(\s+")([^"]*)(".*)$')
SCRIPT_DIR = Path(__file__).resolve().parent
POD_ROOT = SCRIPT_DIR.parent
REPO_ROOT = POD_ROOT.parents[1]
SOURCE_TEST = POD_ROOT / "test08_dp_reduce_scatter"
CASES = ("case01_standard", "case04_l1_l2_lane_down")
REQUIRED_TRACE_FAMILIES = (
    "task",
    "packet",
    "port",
    "queue",
    "flow_control",
    "packet_path",
)


@dataclass(frozen=True)
class TrafficSummary:
    rows: int
    original_bytes: int
    scaled_bytes: int
    ratio: float


@dataclass(frozen=True)
class StagedCase:
    source: Path
    destination: Path
    traffic: TrafficSummary
    structural_hashes: dict[str, str]


@dataclass(frozen=True)
class TaskStatisticsSummary:
    tasks: int
    average_complete_us: float
    max_complete_us: float


@dataclass(frozen=True)
class TraceFamilySummary:
    files: int
    bytes: int


@dataclass
class ActiveRun:
    case: str
    staged: StagedCase
    command: list[str]
    process: subprocess.Popen[str]
    console_path: Path
    console_stream: object
    started_monotonic: float
    returncode: int | None = None
    elapsed_seconds: float | None = None


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scale_traffic(source: Path, destination: Path, scale: int) -> TrafficSummary:
    if scale <= 0:
        raise ValueError("scale must be positive")

    rows: list[dict[str, str]] = []
    original_total = 0
    scaled_total = 0
    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames = list(reader.fieldnames or [])
        if SIZE_COLUMN not in fieldnames:
            raise ValueError(f"{source} missing {SIZE_COLUMN!r}")
        for row in reader:
            original = int(float(row[SIZE_COLUMN]))
            scaled = 0 if original <= 0 else max(1, original // scale)
            row[SIZE_COLUMN] = str(scaled)
            rows.append(row)
            original_total += original
            scaled_total += scaled

    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    ratio = 0.0 if original_total == 0 else scaled_total / original_total
    return TrafficSummary(len(rows), original_total, scaled_total, ratio)


def enable_analysis_traces(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    seen: set[str] = set()
    updated: list[str] = []

    for line in lines:
        match = GLOBAL_LINE.match(line)
        if match and match.group(2) in ANALYSIS_TRACE_VALUES:
            name = match.group(2)
            value = ANALYSIS_TRACE_VALUES[name]
            line_ending = "\n" if line.endswith("\n") else ""
            updated.append(
                f'{match.group(1)}{name}{match.group(3)}{value}{match.group(5).rstrip()}\n'
                if line_ending
                else f'{match.group(1)}{name}{match.group(3)}{value}{match.group(5)}'
            )
            seen.add(name)
        else:
            updated.append(line)

    optional_insert = "UB_TASK_SEGMENT_TRACE_ENABLE"
    required = set(ANALYSIS_TRACE_VALUES) - {optional_insert}
    missing = sorted(required - seen)
    if missing:
        raise ValueError(f"{path} missing trace globals: {', '.join(missing)}")
    if optional_insert not in seen:
        updated.append(
            f'global {optional_insert} "{ANALYSIS_TRACE_VALUES[optional_insert]}"\n'
        )

    path.write_text("".join(updated), encoding="utf-8")


def stage_case(source: Path, destination: Path, scale: int) -> StagedCase:
    if destination.exists():
        raise FileExistsError(destination)
    for name in CASE_INPUT_FILES:
        if not (source / name).is_file():
            raise FileNotFoundError(source / name)

    destination.mkdir(parents=True)
    for name in CASE_INPUT_FILES:
        shutil.copy2(source / name, destination / name)

    traffic = scale_traffic(
        destination / "traffic.original.csv",
        destination / "traffic.csv",
        scale,
    )
    enable_analysis_traces(destination / "network_attribute.txt")

    structural_hashes: dict[str, str] = {}
    for name in STRUCTURAL_FILES:
        source_hash = sha256_file(source / name)
        destination_hash = sha256_file(destination / name)
        if source_hash != destination_hash:
            raise RuntimeError(f"staged {name} does not match source")
        structural_hashes[name] = source_hash

    return StagedCase(source, destination, traffic, structural_hashes)


def summarize_task_statistics(path: Path) -> TaskStatisticsSummary:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        return TaskStatisticsSummary(0, 0.0, 0.0)
    column = "taskCompletesTime(us)"
    if column not in rows[0]:
        raise ValueError(f"{path} missing {column!r}")
    completes = [float(row[column]) for row in rows]
    return TaskStatisticsSummary(len(rows), mean(completes), max(completes))


def trace_inventory(runlog: Path) -> dict[str, TraceFamilySummary]:
    prefixes = {
        "task": ("TaskTrace_",),
        "packet": ("PacketTrace_",),
        "port": ("PortTrace_",),
        "queue": ("QueueTrace_",),
        "flow_control": ("PfcTrace_", "PfcDynamicTrace_", "CbfcTrace_"),
        "packet_path": ("AllPacketTrace_",),
    }
    result: dict[str, TraceFamilySummary] = {}
    files = [path for path in runlog.iterdir() if path.is_file()] if runlog.is_dir() else []
    for family, family_prefixes in prefixes.items():
        matches = [path for path in files if path.name.startswith(family_prefixes)]
        result[family] = TraceFamilySummary(
            files=len(matches),
            bytes=sum(path.stat().st_size for path in matches),
        )
    return result


def build_ns3_command(repo_root: Path, case_path: Path) -> list[str]:
    try:
        relative = case_path.resolve().relative_to(repo_root.resolve())
    except ValueError as error:
        raise ValueError(f"case path must be inside repository: {case_path}") from error
    return [
        "./ns3",
        "run",
        "--no-build",
        f"scratch/ub-quick-example --case-path={relative.as_posix()}",
    ]


def snapshot_case_inputs(case_path: Path) -> dict[str, str]:
    names = list(CASE_INPUT_FILES)
    if (case_path / "traffic.csv").is_file():
        names.append("traffic.csv")
    return {name: sha256_file(case_path / name) for name in names}


def memory_available_bytes() -> int:
    with Path("/proc/meminfo").open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable not found in /proc/meminfo")


def directory_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return total
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except FileNotFoundError:
                continue
    return total


def raise_file_descriptor_limit(target: int = 65535) -> tuple[int, int]:
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    requested = target if hard == resource.RLIM_INFINITY else min(target, hard)
    if soft < requested:
        resource.setrlimit(resource.RLIMIT_NOFILE, (requested, hard))
    return resource.getrlimit(resource.RLIMIT_NOFILE)


def terminate_process_group(run: ActiveRun) -> None:
    if run.process.poll() is not None:
        return
    try:
        os.killpg(run.process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        run.process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(run.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        run.process.wait(timeout=30)


def launch_case(case: str, staged: StagedCase, batch_dir: Path) -> ActiveRun:
    command = build_ns3_command(REPO_ROOT, staged.destination)
    console_path = batch_dir / f"{case}.console.log"
    console_stream = console_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        stdout=console_stream,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    return ActiveRun(
        case=case,
        staged=staged,
        command=command,
        process=process,
        console_path=console_path,
        console_stream=console_stream,
        started_monotonic=time.monotonic(),
    )


def append_monitor_row(
    path: Path,
    runs: dict[str, ActiveRun],
    memory_bytes: int,
    free_disk_bytes: int,
) -> None:
    fieldnames = ["timestamp", "available_memory_gib", "free_disk_gib"]
    for case in CASES:
        fieldnames.extend((f"{case}_state", f"{case}_runlog_bytes"))
    create_header = not path.exists()
    row: dict[str, str] = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "available_memory_gib": f"{memory_bytes / (1024 ** 3):.3f}",
        "free_disk_gib": f"{free_disk_bytes / (1024 ** 3):.3f}",
    }
    for case, run in runs.items():
        returncode = run.process.poll()
        row[f"{case}_state"] = "RUNNING" if returncode is None else f"EXIT_{returncode}"
        row[f"{case}_runlog_bytes"] = str(directory_bytes(run.staged.destination / "runlog"))
    with path.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        if create_header:
            writer.writeheader()
        writer.writerow(row)


def write_trace_inventory(path: Path, runs: dict[str, ActiveRun]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("case", "family", "files", "bytes"),
            lineterminator="\n",
        )
        writer.writeheader()
        for case, run in runs.items():
            for family, summary in trace_inventory(
                run.staged.destination / "runlog"
            ).items():
                writer.writerow(
                    {
                        "case": case,
                        "family": family,
                        "files": summary.files,
                        "bytes": summary.bytes,
                    }
                )


def write_run_summary(
    path: Path,
    runs: dict[str, ActiveRun],
    source_hashes_before: dict[str, dict[str, str]],
) -> bool:
    fieldnames = (
        "case",
        "returncode",
        "elapsed_seconds",
        "traffic_rows",
        "original_bytes",
        "scaled_bytes",
        "tasks",
        "average_complete_us",
        "max_complete_us",
        "source_inputs_unchanged",
        "required_traces_present",
    )
    all_ok = True
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for case, run in runs.items():
            stats_path = run.staged.destination / "output" / "task_statistics.csv"
            stats = (
                summarize_task_statistics(stats_path)
                if stats_path.is_file()
                else TaskStatisticsSummary(0, 0.0, 0.0)
            )
            inventory = trace_inventory(run.staged.destination / "runlog")
            traces_present = all(
                inventory[family].files > 0 and inventory[family].bytes > 0
                for family in REQUIRED_TRACE_FAMILIES
            )
            inputs_unchanged = (
                snapshot_case_inputs(run.staged.source) == source_hashes_before[case]
            )
            case_ok = (
                run.returncode == 0
                and stats.tasks == 6840
                and traces_present
                and inputs_unchanged
            )
            all_ok = all_ok and case_ok
            writer.writerow(
                {
                    "case": case,
                    "returncode": run.returncode,
                    "elapsed_seconds": f"{run.elapsed_seconds or 0.0:.3f}",
                    "traffic_rows": run.staged.traffic.rows,
                    "original_bytes": run.staged.traffic.original_bytes,
                    "scaled_bytes": run.staged.traffic.scaled_bytes,
                    "tasks": stats.tasks,
                    "average_complete_us": f"{stats.average_complete_us:.6f}",
                    "max_complete_us": f"{stats.max_complete_us:.6f}",
                    "source_inputs_unchanged": str(inputs_unchanged).lower(),
                    "required_traces_present": str(traces_present).lower(),
                }
            )
    scaled_totals = {run.staged.traffic.scaled_bytes for run in runs.values()}
    return all_ok and len(scaled_totals) == 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--label",
        default=f"test08_scale20_case01_04_analysis_traces_{datetime.now():%Y%m%d_%H%M%S}",
    )
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--min-free-disk-gib", type=float, default=100.0)
    parser.add_argument("--min-available-memory-gib", type=float, default=4.0)
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    if args.min_free_disk_gib <= 0:
        parser.error("--min-free-disk-gib must be positive")
    if args.min_available_memory_gib <= 0:
        parser.error("--min-available-memory-gib must be positive")
    return args


def main() -> int:
    args = parse_args()
    batch_dir = SCRIPT_DIR / "batch_run_logs" / args.label
    if batch_dir.exists():
        raise FileExistsError(batch_dir)
    cases_dir = batch_dir / "cases"
    cases_dir.mkdir(parents=True)

    source_hashes_before = {
        case: snapshot_case_inputs(SOURCE_TEST / case) for case in CASES
    }
    staged_cases = {
        case: stage_case(SOURCE_TEST / case, cases_dir / case, scale=20)
        for case in CASES
    }
    scaled_totals = {staged.traffic.scaled_bytes for staged in staged_cases.values()}
    if len(scaled_totals) != 1:
        raise RuntimeError("case01 and case04 scaled traffic totals differ")

    nofile_soft, nofile_hard = raise_file_descriptor_limit()
    manifest = {
        "label": args.label,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": str(REPO_ROOT),
        "source_test": str(SOURCE_TEST),
        "scale": 20,
        "trace_values": ANALYSIS_TRACE_VALUES,
        "nofile_soft": nofile_soft,
        "nofile_hard": nofile_hard,
        "source_hashes_before": source_hashes_before,
        "cases": {
            case: {
                "source": str(staged.source),
                "destination": str(staged.destination),
                "traffic": {
                    "rows": staged.traffic.rows,
                    "original_bytes": staged.traffic.original_bytes,
                    "scaled_bytes": staged.traffic.scaled_bytes,
                    "ratio": staged.traffic.ratio,
                },
                "structural_hashes": staged.structural_hashes,
            }
            for case, staged in staged_cases.items()
        },
    }
    (batch_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    runs: dict[str, ActiveRun] = {}
    unsafe_reason = ""
    try:
        for case, staged in staged_cases.items():
            runs[case] = launch_case(case, staged, batch_dir)
            print(
                f"[{datetime.now():%H:%M:%S}] START {case} pid={runs[case].process.pid} "
                f"scaled_bytes={staged.traffic.scaled_bytes}",
                flush=True,
            )

        monitor_path = batch_dir / "monitor.csv"
        while any(run.process.poll() is None for run in runs.values()):
            memory_bytes = memory_available_bytes()
            free_disk_bytes = shutil.disk_usage(batch_dir).free
            append_monitor_row(
                monitor_path,
                runs,
                memory_bytes=memory_bytes,
                free_disk_bytes=free_disk_bytes,
            )
            states = " ".join(
                f"{case}={'RUNNING' if run.process.poll() is None else run.process.returncode}"
                for case, run in runs.items()
            )
            print(
                f"[{datetime.now():%H:%M:%S}] MONITOR mem={memory_bytes / (1024 ** 3):.1f}GiB "
                f"disk={free_disk_bytes / (1024 ** 3):.1f}GiB {states}",
                flush=True,
            )
            if free_disk_bytes < args.min_free_disk_gib * (1024 ** 3):
                unsafe_reason = "free disk below threshold"
                break
            if memory_bytes < args.min_available_memory_gib * (1024 ** 3):
                unsafe_reason = "available memory below threshold"
                break
            time.sleep(args.poll_seconds)

        if unsafe_reason:
            print(f"UNSAFE: {unsafe_reason}; terminating active cases", flush=True)
            for run in runs.values():
                terminate_process_group(run)

        for run in runs.values():
            run.returncode = run.process.wait()
            run.elapsed_seconds = time.monotonic() - run.started_monotonic
            run.console_stream.close()
            print(
                f"[{datetime.now():%H:%M:%S}] EXIT {run.case} rc={run.returncode} "
                f"elapsed={run.elapsed_seconds:.1f}s",
                flush=True,
            )
    except BaseException:
        for run in runs.values():
            terminate_process_group(run)
            run.console_stream.close()
        raise

    write_trace_inventory(batch_dir / "trace_inventory.csv", runs)
    successful = write_run_summary(
        batch_dir / "run_summary.csv", runs, source_hashes_before
    )
    if unsafe_reason:
        (batch_dir / "unsafe_reason.txt").write_text(unsafe_reason + "\n", encoding="utf-8")
    print(f"batch_dir={batch_dir}", flush=True)
    print(f"successful={successful}", flush=True)
    return 0 if successful and not unsafe_reason else 1


if __name__ == "__main__":
    raise SystemExit(main())
