#!/usr/bin/env python3
"""Generate task_statistics.csv for completed test08 cases from TaskTrace files."""

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import re
import sys


TASK_TRACE_PATTERN = re.compile(
    r"^\[(?P<timestamp>[-+]?\d+(?:\.\d+)?)us\] "
    r"(?P<event>.*?),.*?taskId: (?P<task_id>\d+)"
)
START_MARKERS = ("WQE Starts", "MEM Task Starts")
COMPLETE_MARKERS = ("WQE Completes", "MEM Task Completes")
STAT_COLUMNS = (
    "taskStartTime(us)",
    "taskCompletesTime(us)",
    "firstPacketSends(us)",
    "lastPacketACKs(us)",
    "taskThroughput(Gbps)",
)


@dataclass(frozen=True)
class CaseSummary:
    case_dir: Path
    total_traffic_tasks: int
    completed_tasks: int
    output_path: Path


def collect_task_times(runlog_dir: Path) -> dict[str, tuple[float | None, float | None]]:
    trace_files = sorted(runlog_dir.glob("TaskTrace_node_*.tr"))
    if not trace_files:
        raise FileNotFoundError(f"missing TaskTrace_node_*.tr under {runlog_dir}")

    task_times: dict[str, list[float | None]] = {}
    for trace_path in trace_files:
        with trace_path.open(encoding="utf-8", errors="replace") as trace_file:
            for line in trace_file:
                match = TASK_TRACE_PATTERN.match(line)
                if match is None:
                    continue
                event = match.group("event")
                task_id = match.group("task_id")
                timestamp = float(match.group("timestamp"))
                start_time, complete_time = task_times.setdefault(task_id, [None, None])
                if any(marker in event for marker in START_MARKERS):
                    task_times[task_id][0] = (
                        timestamp if start_time is None else min(start_time, timestamp)
                    )
                elif any(marker in event for marker in COMPLETE_MARKERS):
                    task_times[task_id][1] = (
                        timestamp if complete_time is None else max(complete_time, timestamp)
                    )

    completed = {
        task_id: (times[0], times[1])
        for task_id, times in task_times.items()
        if times[1] is not None
    }
    if not completed:
        raise ValueError(f"no task completion events found under {runlog_dir}")
    return completed


def read_traffic(traffic_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with traffic_path.open(newline="", encoding="utf-8") as traffic_file:
        reader = csv.DictReader(traffic_file)
        if reader.fieldnames is None:
            raise ValueError(f"traffic.csv has no header: {traffic_path}")
        if "taskId" not in reader.fieldnames or "dataSize(Byte)" not in reader.fieldnames:
            raise ValueError(f"traffic.csv lacks taskId or dataSize(Byte): {traffic_path}")
        return list(reader.fieldnames), list(reader)


def generate_case_statistics(case_dir: Path, output_dir_name: str = "output") -> CaseSummary:
    traffic_path = case_dir / "traffic.csv"
    runlog_dir = case_dir / "runlog"
    if not traffic_path.is_file():
        raise FileNotFoundError(f"missing traffic.csv: {traffic_path}")
    if not runlog_dir.is_dir():
        raise FileNotFoundError(f"missing runlog directory: {runlog_dir}")

    fieldnames, rows = read_traffic(traffic_path)
    task_times = collect_task_times(runlog_dir)
    for column in STAT_COLUMNS:
        if column not in fieldnames:
            fieldnames.append(column)

    completed_tasks = 0
    for row in rows:
        task_id = row.get("taskId", "")
        start_time, complete_time = task_times.get(task_id, (None, None))
        if start_time is None or complete_time is None:
            for column in STAT_COLUMNS:
                row[column] = ""
            continue

        duration_us = complete_time - start_time
        data_size = int(row["dataSize(Byte)"])
        throughput_gbps = round((data_size * 8 / 1000) / duration_us, 4) if duration_us > 0 else 0.0
        row["taskStartTime(us)"] = str(start_time)
        row["taskCompletesTime(us)"] = str(complete_time)
        row["firstPacketSends(us)"] = "0.0"
        row["lastPacketACKs(us)"] = "0.0"
        row["taskThroughput(Gbps)"] = str(throughput_gbps)
        completed_tasks += 1

    output_dir = case_dir / output_dir_name
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "task_statistics.csv"
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return CaseSummary(
        case_dir=case_dir,
        total_traffic_tasks=len(rows),
        completed_tasks=completed_tasks,
        output_path=output_path,
    )


def default_test_root() -> Path:
    return Path(__file__).resolve().parents[1] / "test08_dp_reduce_scatter"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate task_statistics.csv for every test08 case from completed TaskTrace files."
    )
    parser.add_argument(
        "case_dir",
        nargs="?",
        type=Path,
        help="one completed case directory, as supplied by the ns-3 trace parser",
    )
    parser.add_argument(
        "is_test",
        nargs="?",
        choices=("true", "false"),
        default="false",
        help="write under test/ when true; default false writes under output/",
    )
    parser.add_argument(
        "--test-root",
        type=Path,
        default=default_test_root(),
        help="test08 directory containing case* subdirectories",
    )
    args = parser.parse_args(argv)

    if args.case_dir is not None:
        try:
            output_dir_name = "test" if args.is_test == "true" else "output"
            summary = generate_case_statistics(args.case_dir, output_dir_name)
            print(
                f"[{args.case_dir.name}] generated {summary.output_path} "
                f"({summary.completed_tasks}/{summary.total_traffic_tasks} tasks completed)"
            )
            return 0
        except (OSError, ValueError, csv.Error) as error:
            print(f"[{args.case_dir.name}] ERROR: {error}", file=sys.stderr)
            return 1

    case_dirs = sorted(path for path in args.test_root.glob("case*") if path.is_dir())
    if not case_dirs:
        parser.error(f"no case* directories found under {args.test_root}")

    failures = 0
    for case_dir in case_dirs:
        try:
            summary = generate_case_statistics(case_dir)
            print(
                f"[{case_dir.name}] generated {summary.output_path} "
                f"({summary.completed_tasks}/{summary.total_traffic_tasks} tasks completed)"
            )
        except (OSError, ValueError, csv.Error) as error:
            failures += 1
            print(f"[{case_dir.name}] ERROR: {error}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
