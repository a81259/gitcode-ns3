#!/usr/bin/env python3
"""Summarize task FCT and operator completion time for test08 cases."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import math
from pathlib import Path
from statistics import fmean
import sys


START_COLUMN = "taskStartTime(us)"
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
    "average_fct_us",
    "max_fct_us",
    "operator_completion_time_us",
    "statistics_file",
)


@dataclass(frozen=True)
class CaseSummary:
    case: str
    total_tasks: int
    completed_tasks: int
    average_fct_us: float
    max_fct_us: float
    operator_completion_time_us: float
    statistics_file: Path


def default_test_root() -> Path:
    return Path(__file__).resolve().parents[1] / "test08_dp_reduce_scatter"


def default_output_path() -> Path:
    return Path(__file__).resolve().parents[1] / "result" / "test08_fct_summary.csv"


def parse_time(
    raw_value: str | None,
    *,
    column: str,
    statistics_file: Path,
    line_number: int,
) -> float | None:
    value_text = (raw_value or "").strip()
    if not value_text:
        return None
    try:
        value = float(value_text)
    except ValueError as error:
        raise ValueError(
            f"{statistics_file}:{line_number} has invalid {column}: {value_text!r}"
        ) from error
    if not math.isfinite(value) or value < 0:
        raise ValueError(
            f"{statistics_file}:{line_number} has invalid {column}: {value_text!r}"
        )
    return value


def read_case_summary(case_dir: Path) -> CaseSummary:
    statistics_file = case_dir / "output" / "task_statistics.csv"
    if not statistics_file.is_file():
        raise FileNotFoundError(f"missing statistics file: {statistics_file}")

    with statistics_file.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {statistics_file}")
        missing_columns = [
            column
            for column in (START_COLUMN, COMPLETION_COLUMN)
            if column not in reader.fieldnames
        ]
        if missing_columns:
            raise ValueError(
                f"{statistics_file} is missing required columns: "
                f"{', '.join(missing_columns)}"
            )

        total_tasks = 0
        task_times: list[tuple[float, float]] = []
        for line_number, row in enumerate(reader, start=2):
            total_tasks += 1
            start_time = parse_time(
                row.get(START_COLUMN),
                column=START_COLUMN,
                statistics_file=statistics_file,
                line_number=line_number,
            )
            completion_time = parse_time(
                row.get(COMPLETION_COLUMN),
                column=COMPLETION_COLUMN,
                statistics_file=statistics_file,
                line_number=line_number,
            )
            if start_time is None and completion_time is None:
                continue
            if start_time is None or completion_time is None:
                raise ValueError(
                    f"{statistics_file}:{line_number} has only one of "
                    f"{START_COLUMN} and {COMPLETION_COLUMN}"
                )
            if completion_time < start_time:
                raise ValueError(
                    f"{statistics_file}:{line_number} completes before it starts: "
                    f"{completion_time} < {start_time}"
                )
            task_times.append((start_time, completion_time))

    if total_tasks == 0:
        raise ValueError(f"statistics file has no task rows: {statistics_file}")
    if not task_times:
        raise ValueError(f"statistics file has no completed tasks: {statistics_file}")

    fcts = [completion_time - start_time for start_time, completion_time in task_times]
    return CaseSummary(
        case=case_dir.name,
        total_tasks=total_tasks,
        completed_tasks=len(task_times),
        average_fct_us=fmean(fcts),
        max_fct_us=max(fcts),
        operator_completion_time_us=(
            max(completion_time for _, completion_time in task_times)
            - min(start_time for start_time, _ in task_times)
        ),
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
                    "average_fct_us": f"{summary.average_fct_us:.6f}",
                    "max_fct_us": f"{summary.max_fct_us:.6f}",
                    "operator_completion_time_us": (
                        f"{summary.operator_completion_time_us:.6f}"
                    ),
                    "statistics_file": summary.statistics_file,
                }
            )


def print_summary(summaries: list[CaseSummary]) -> None:
    print(
        f"{'case':<42} {'completed/total':>17} "
        f"{'avg FCT(us)':>15} {'max FCT(us)':>15} {'operator(us)':>15}"
    )
    for summary in summaries:
        print(
            f"{summary.case:<42} "
            f"{summary.completed_tasks:>8}/{summary.total_tasks:<8} "
            f"{summary.average_fct_us:>15.6f} "
            f"{summary.max_fct_us:>15.6f} "
            f"{summary.operator_completion_time_us:>15.6f}"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Calculate average task FCT, maximum task FCT, and operator completion "
            "time for the five test08 topology cases. Task FCT is completion minus "
            "start; operator completion time is latest completion minus earliest start."
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
