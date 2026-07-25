#!/usr/bin/env python3
"""Summarize average and maximum task completion times for test08 cases."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import math
from pathlib import Path
from statistics import fmean
import sys


COMPLETION_COLUMN = "taskCompletesTime(us)"
CASES = (
    "case01_标准topo",
    "case02_故障1topo_单链路lane",
    "case03_故障2topo_单链路laport",
    "case04_故障3topo_分布式多链路port",
    "case05_故障4topo_分集中式多链路port",
)
OUTPUT_COLUMNS = (
    "case",
    "total_tasks",
    "completed_tasks",
    "average_completion_time_us",
    "max_completion_time_us",
    "statistics_file",
)


@dataclass(frozen=True)
class CaseSummary:
    case: str
    total_tasks: int
    completed_tasks: int
    average_completion_time_us: float
    max_completion_time_us: float
    statistics_file: Path


def default_test_root() -> Path:
    return Path(__file__).resolve().parents[1] / "test08_dp_reduce_scatter"


def default_output_path() -> Path:
    return Path(__file__).resolve().parents[1] / "result" / "test08_completion_time_summary.csv"


def read_case_summary(case_dir: Path) -> CaseSummary:
    statistics_file = case_dir / "output" / "task_statistics.csv"
    if not statistics_file.is_file():
        raise FileNotFoundError(f"missing statistics file: {statistics_file}")

    with statistics_file.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {statistics_file}")
        if COMPLETION_COLUMN not in reader.fieldnames:
            raise ValueError(
                f"{statistics_file} is missing required column {COMPLETION_COLUMN!r}"
            )

        total_tasks = 0
        completion_times: list[float] = []
        for line_number, row in enumerate(reader, start=2):
            total_tasks += 1
            raw_value = (row.get(COMPLETION_COLUMN) or "").strip()
            if not raw_value:
                continue
            try:
                value = float(raw_value)
            except ValueError as error:
                raise ValueError(
                    f"{statistics_file}:{line_number} has invalid "
                    f"{COMPLETION_COLUMN}: {raw_value!r}"
                ) from error
            if not math.isfinite(value) or value < 0:
                raise ValueError(
                    f"{statistics_file}:{line_number} has invalid "
                    f"{COMPLETION_COLUMN}: {raw_value!r}"
                )
            completion_times.append(value)

    if total_tasks == 0:
        raise ValueError(f"statistics file has no task rows: {statistics_file}")
    if not completion_times:
        raise ValueError(f"statistics file has no completed tasks: {statistics_file}")

    return CaseSummary(
        case=case_dir.name,
        total_tasks=total_tasks,
        completed_tasks=len(completion_times),
        average_completion_time_us=fmean(completion_times),
        max_completion_time_us=max(completion_times),
        statistics_file=statistics_file,
    )


def collect_summaries(test_root: Path) -> list[CaseSummary]:
    summaries: list[CaseSummary] = []
    errors: list[str] = []
    for case in CASES:
        case_dir = test_root / case
        try:
            summaries.append(read_case_summary(case_dir))
        except (OSError, ValueError, csv.Error) as error:
            errors.append(f"[{case}] {error}")

    if errors:
        raise RuntimeError("\n".join(errors))
    return summaries


def write_summary(output_path: Path, summaries: list[CaseSummary]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for summary in summaries:
            writer.writerow(
                {
                    "case": summary.case,
                    "total_tasks": summary.total_tasks,
                    "completed_tasks": summary.completed_tasks,
                    "average_completion_time_us": (
                        f"{summary.average_completion_time_us:.6f}"
                    ),
                    "max_completion_time_us": f"{summary.max_completion_time_us:.6f}",
                    "statistics_file": summary.statistics_file,
                }
            )


def print_summary(summaries: list[CaseSummary]) -> None:
    print(
        f"{'case':<42} {'completed/total':>17} "
        f"{'average(us)':>15} {'max(us)':>15}"
    )
    for summary in summaries:
        print(
            f"{summary.case:<42} "
            f"{summary.completed_tasks:>8}/{summary.total_tasks:<8} "
            f"{summary.average_completion_time_us:>15.6f} "
            f"{summary.max_completion_time_us:>15.6f}"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Calculate average and maximum taskCompletesTime(us) for the five "
            "test08 topology cases."
        )
    )
    parser.add_argument(
        "--test-root",
        type=Path,
        default=default_test_root(),
        help="test08_dp_reduce_scatter directory containing the five case directories",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_output_path(),
        help="summary CSV path",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summaries = collect_summaries(args.test_root)
        write_summary(args.output, summaries)
    except (OSError, RuntimeError, ValueError, csv.Error) as error:
        print(f"ERROR:\n{error}", file=sys.stderr)
        return 1

    print_summary(summaries)
    print(f"\nsummary written to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
