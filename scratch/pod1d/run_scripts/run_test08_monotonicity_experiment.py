#!/usr/bin/env python3
"""Run isolated, low-log test08 case01/case04 monotonicity experiments."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean


SCRIPT_DIR = Path(__file__).resolve().parent
POD_ROOT = SCRIPT_DIR.parent
REPO_ROOT = POD_ROOT.parents[1]
SOURCE_TEST = POD_ROOT / "test08_dp_reduce_scatter"
CASES = ("case01_standard", "case04_l1_l2_lane_down")
INPUT_FILES = (
    "network_attribute.txt",
    "node.csv",
    "topology.csv",
    "routing_table.csv",
    "traffic.original.csv",
)
SIZE_COLUMN = "dataSize(Byte)"
START_COLUMN = "taskStartTime(us)"
COMPLETE_COLUMN = "taskCompletesTime(us)"
THROUGHPUT_COLUMN = "taskThroughput(Gbps)"
DEFAULT_LINE = re.compile(r'^(\s*default\s+)(\S+)(\s+")([^"]*)(".*)$')
GLOBAL_LINE = re.compile(r'^(\s*global\s+)(\S+)(\s+")([^"]*)(".*)$')

DEFAULT_VALUES = {
    "ns3::UbRoutingProcess::BwWeightedPacketSpray": "true",
    "ns3::UbRoutingProcess::BwWeightedPacketSprayScope": "l1-l2",
    "ns3::UbTransportChannel::TransactionAckPriority": "6",
}
GLOBAL_VALUES = {
    "UB_TRACE_ENABLE": "true",
    "UB_TASK_TRACE_ENABLE": "true",
    "UB_TASK_SEGMENT_TRACE_ENABLE": "false",
    "UB_PACKET_TRACE_ENABLE": "false",
    "UB_PORT_TRACE_ENABLE": "false",
    "UB_QUEUE_TRACE_ENABLE": "false",
    "UB_FLOW_CONTROL_TRACE_ENABLE": "false",
    "UB_CONGESTION_CONTROL_TRACE_ENABLE": "false",
    "UB_RECORD_PKT_TRACE": "false",
    "UB_PARSE_TRACE_ENABLE": "true",
}


@dataclass
class ActiveRun:
    case: str
    case_dir: Path
    process: subprocess.Popen[str]
    console_path: Path
    console_stream: object
    started: float


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rewrite_attributes(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    seen_defaults: set[str] = set()
    seen_globals: set[str] = set()
    rewritten: list[str] = []

    for line in lines:
        default_match = DEFAULT_LINE.match(line)
        global_match = GLOBAL_LINE.match(line)
        if default_match and default_match.group(2) in DEFAULT_VALUES:
            name = default_match.group(2)
            rewritten.append(
                f'{default_match.group(1)}{name}{default_match.group(3)}'
                f'{DEFAULT_VALUES[name]}{default_match.group(5)}'
            )
            seen_defaults.add(name)
        elif global_match and global_match.group(2) in GLOBAL_VALUES:
            name = global_match.group(2)
            rewritten.append(
                f'{global_match.group(1)}{name}{global_match.group(3)}'
                f'{GLOBAL_VALUES[name]}{global_match.group(5)}'
            )
            seen_globals.add(name)
        else:
            rewritten.append(line)

    for name, value in DEFAULT_VALUES.items():
        if name not in seen_defaults:
            rewritten.append(f'default {name} "{value}"')
    for name, value in GLOBAL_VALUES.items():
        if name not in seen_globals:
            rewritten.append(f'global {name} "{value}"')

    path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def scale_traffic(source: Path, destination: Path, scale: int) -> tuple[int, int, int]:
    rows: list[dict[str, str]] = []
    original_bytes = 0
    scaled_bytes = 0
    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames = list(reader.fieldnames or [])
        if SIZE_COLUMN not in fieldnames:
            raise ValueError(f"{source} missing {SIZE_COLUMN}")
        for row in reader:
            original = int(float(row[SIZE_COLUMN]))
            scaled = original if original <= 0 else max(1, original // scale)
            row[SIZE_COLUMN] = str(scaled)
            rows.append(row)
            original_bytes += original
            scaled_bytes += scaled

    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows), original_bytes, scaled_bytes


def stage_case(source: Path, destination: Path, scale: int) -> dict[str, object]:
    destination.mkdir(parents=True)
    hashes: dict[str, str] = {}
    for name in INPUT_FILES:
        source_path = source / name
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        shutil.copy2(source_path, destination / name)
        hashes[name] = sha256_file(source_path)

    rows, original_bytes, scaled_bytes = scale_traffic(
        destination / "traffic.original.csv",
        destination / "traffic.csv",
        scale,
    )
    rewrite_attributes(destination / "network_attribute.txt")
    return {
        "rows": rows,
        "original_bytes": original_bytes,
        "scaled_bytes": scaled_bytes,
        "source_hashes": hashes,
    }


def launch(case: str, case_dir: Path, batch_dir: Path) -> ActiveRun:
    relative_case = case_dir.relative_to(REPO_ROOT).as_posix()
    console_path = batch_dir / f"{case}.console.log"
    console_stream = console_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            "./ns3",
            "run",
            "--no-build",
            f"scratch/ub-quick-example --case-path={relative_case}",
        ],
        cwd=REPO_ROOT,
        stdout=console_stream,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    return ActiveRun(case, case_dir, process, console_path, console_stream, time.monotonic())


def terminate(run: ActiveRun) -> None:
    if run.process.poll() is not None:
        return
    try:
        os.killpg(run.process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        run.process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        os.killpg(run.process.pid, signal.SIGKILL)
        run.process.wait(timeout=30)


def summarize(case: str, case_dir: Path, returncode: int, elapsed: float) -> dict[str, object]:
    stats_path = case_dir / "output" / "task_statistics.csv"
    if not stats_path.is_file():
        return {
            "case": case,
            "returncode": returncode,
            "elapsed_seconds": elapsed,
            "tasks": 0,
        }
    with stats_path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    completes = [float(row[COMPLETE_COLUMN]) for row in rows]
    fcts = [
        float(row[COMPLETE_COLUMN]) - float(row[START_COLUMN])
        for row in rows
    ]
    throughputs = [float(row[THROUGHPUT_COLUMN]) for row in rows]
    return {
        "case": case,
        "returncode": returncode,
        "elapsed_seconds": elapsed,
        "tasks": len(rows),
        "average_complete_us": mean(completes),
        "max_complete_us": max(completes),
        "average_fct_us": mean(fcts),
        "max_fct_us": max(fcts),
        "average_throughput_gbps": mean(throughputs),
        "stats_sha256": sha256_file(stats_path),
        "runlog_bytes": sum(
            path.stat().st_size
            for path in (case_dir / "runlog").rglob("*")
            if path.is_file()
        ),
    }


def run_scale(scale: int, batch_dir: Path, poll_seconds: float) -> list[dict[str, object]]:
    scale_dir = batch_dir / f"scale{scale}"
    staged: dict[str, dict[str, object]] = {}
    runs: dict[str, ActiveRun] = {}
    try:
        for case in CASES:
            case_dir = scale_dir / case
            staged[case] = stage_case(SOURCE_TEST / case, case_dir, scale)
            runs[case] = launch(case, case_dir, batch_dir)
            print(f"START scale={scale} case={case} pid={runs[case].process.pid}", flush=True)

        while any(run.process.poll() is None for run in runs.values()):
            states = ", ".join(
                f"{case}={'RUNNING' if run.process.poll() is None else run.process.returncode}"
                for case, run in runs.items()
            )
            free_gib = shutil.disk_usage(batch_dir).free / (1024 ** 3)
            print(f"MONITOR scale={scale} disk={free_gib:.1f}GiB {states}", flush=True)
            if free_gib < 5.0:
                raise RuntimeError("free disk fell below 5 GiB")
            time.sleep(poll_seconds)
    except BaseException:
        for run in runs.values():
            terminate(run)
        raise
    finally:
        for run in runs.values():
            run.console_stream.close()

    results = [
        summarize(
            case,
            run.case_dir,
            run.process.wait(),
            time.monotonic() - run.started,
        )
        for case, run in runs.items()
    ]
    scaled_totals = {int(staged[case]["scaled_bytes"]) for case in CASES}
    if len(scaled_totals) != 1:
        raise RuntimeError("staged case traffic totals differ")
    return results


def write_summary(path: Path, scale: int, results: list[dict[str, object]]) -> None:
    by_case = {str(row["case"]): row for row in results}
    standard = by_case[CASES[0]]
    fault = by_case[CASES[1]]
    document = {
        "scale": scale,
        "configuration": {
            "data_priority": 7,
            "transaction_ack_priority": 6,
            "weighted_packet_spray": True,
            "weighted_packet_spray_scope": "l1-l2",
        },
        "results": results,
        "case04_minus_case01": {
            "average_complete_us": float(fault["average_complete_us"])
            - float(standard["average_complete_us"]),
            "max_complete_us": float(fault["max_complete_us"])
            - float(standard["max_complete_us"]),
        },
        "standard_strictly_better": {
            "average_complete": float(standard["average_complete_us"])
            < float(fault["average_complete_us"]),
            "max_complete": float(standard["max_complete_us"])
            < float(fault["max_complete_us"]),
        },
    }
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scales", type=int, nargs="+", default=[80])
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument(
        "--label",
        default=f"test08_monotonicity_{datetime.now():%Y%m%d_%H%M%S}",
    )
    args = parser.parse_args()
    if any(scale <= 0 for scale in args.scales):
        parser.error("scales must be positive")
    if args.poll_seconds <= 0:
        parser.error("poll-seconds must be positive")
    return args


def main() -> int:
    args = parse_args()
    batch_dir = SCRIPT_DIR / "batch_run_logs" / args.label
    batch_dir.mkdir(parents=True)
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip(),
        "binary_sha256": sha256_file(REPO_ROOT / "build/scratch/ns3.44-ub-quick-example"),
        "defaults": DEFAULT_VALUES,
        "globals": GLOBAL_VALUES,
    }
    (batch_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    success = True
    for scale in args.scales:
        results = run_scale(scale, batch_dir, args.poll_seconds)
        write_summary(batch_dir / f"scale{scale}_summary.json", scale, results)
        for row in results:
            print(json.dumps(row, sort_keys=True), flush=True)
            success = success and row["returncode"] == 0 and row["tasks"] == 6840
    print(f"batch_dir={batch_dir}", flush=True)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
