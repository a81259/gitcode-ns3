#!/usr/bin/env python3
"""Summarize pod1d case task statistics.

The script scans the 10 x 5 pod1d case layout:

    test*/case*/output/task_statistics.csv

For every discovered case it reports whether task_statistics.csv exists.
For cases with an existing statistics file it also reports:
  - max_sim_complete_us: max taskCompletesTime(us), the simulation makespan point
  - avg_flow_fct_us: average taskCompletesTime(us) - taskStartTime(us)
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from statistics import mean


COMPLETE_COL = "taskCompletesTime(us)"
START_COL = "taskStartTime(us)"


@dataclass(frozen=True)
class CaseStats:
    test: str
    case: str
    status: str
    task_count: int | None
    max_sim_complete_us: float | None
    avg_flow_fct_us: float | None
    stats_path: Path


def natural_key(path: Path) -> tuple[int, str, int, str]:
    test = path.parent.name if path.name.startswith("case") else path.name
    case = path.name if path.name.startswith("case") else ""
    test_num = int(test[4:6]) if test.startswith("test") and test[4:6].isdigit() else 999
    case_num = int(case[4:6]) if case.startswith("case") and case[4:6].isdigit() else 999
    return test_num, test, case_num, case


def parse_float(value: str | None, *, default: float | None = None) -> float:
    if value is None or value == "":
        if default is not None:
            return default
        raise ValueError("empty numeric value")
    return float(value)


def collect_one(case_dir: Path, root: Path) -> CaseStats:
    stats_path = case_dir / "output" / "task_statistics.csv"
    if not stats_path.exists():
        return CaseStats(
            test=case_dir.parent.name,
            case=case_dir.name,
            status="MISSING",
            task_count=None,
            max_sim_complete_us=None,
            avg_flow_fct_us=None,
            stats_path=stats_path.relative_to(root),
        )

    completes: list[float] = []
    fcts: list[float] = []
    with stats_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if COMPLETE_COL not in (reader.fieldnames or []):
            raise ValueError(f"{stats_path} missing required column {COMPLETE_COL!r}")

        for row in reader:
            complete_us = parse_float(row.get(COMPLETE_COL))
            start_us = parse_float(row.get(START_COL), default=0.0)
            completes.append(complete_us)
            fcts.append(complete_us - start_us)

    if not completes:
        raise ValueError(f"{stats_path} has no task rows")

    return CaseStats(
        test=case_dir.parent.name,
        case=case_dir.name,
        status="OK",
        task_count=len(completes),
        max_sim_complete_us=max(completes),
        avg_flow_fct_us=mean(fcts),
        stats_path=stats_path.relative_to(root),
    )


def discover_case_dirs(root: Path) -> list[Path]:
    case_dirs: list[Path] = []
    for test_dir in root.glob("test*"):
        if not test_dir.is_dir():
            continue
        for case_dir in test_dir.glob("case*"):
            if case_dir.is_dir():
                case_dirs.append(case_dir)
    return sorted(case_dirs, key=natural_key)


def collect(root: Path) -> tuple[list[CaseStats], int]:
    case_dirs = discover_case_dirs(root)
    rows: list[CaseStats] = []
    for case_dir in case_dirs:
        rows.append(collect_one(case_dir, root))
    return rows, len(case_dirs)


def format_table(rows: list[CaseStats], total_cases: int) -> str:
    headers = ["test", "case", "status", "tasks", "max_sim_complete_us", "avg_flow_fct_us"]
    body = [
        [
            row.test,
            row.case,
            row.status,
            "" if row.task_count is None else str(row.task_count),
            "" if row.max_sim_complete_us is None else f"{row.max_sim_complete_us:.6f}",
            "" if row.avg_flow_fct_us is None else f"{row.avg_flow_fct_us:.6f}",
        ]
        for row in rows
    ]
    widths = [len(h) for h in headers]
    for line in body:
        widths = [max(width, len(cell)) for width, cell in zip(widths, line)]

    def fmt(line: list[str]) -> str:
        return "  ".join(cell.ljust(width) for cell, width in zip(line, widths))

    found_cases = sum(1 for row in rows if row.status == "OK")
    missing_cases = sum(1 for row in rows if row.status == "MISSING")
    out = [
        f"found_stats_cases={found_cases} missing_stats_cases={missing_cases} total_case_dirs={total_cases}",
        fmt(headers),
        fmt(["-" * width for width in widths]),
    ]
    out.extend(fmt(line) for line in body)
    return "\n".join(out)


def write_csv(rows: list[CaseStats], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "test",
            "case",
            "status",
            "tasks",
            "max_sim_complete_us",
            "avg_flow_fct_us",
            "stats_path",
        ])
        for row in rows:
            writer.writerow([
                row.test,
                row.case,
                row.status,
                "" if row.task_count is None else row.task_count,
                "" if row.max_sim_complete_us is None else f"{row.max_sim_complete_us:.6f}",
                "" if row.avg_flow_fct_us is None else f"{row.avg_flow_fct_us:.6f}",
                row.stats_path.as_posix(),
            ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="pod1d root directory; defaults to this script's directory",
    )
    parser.add_argument("--csv", type=Path, help="optional CSV output path")
    args = parser.parse_args()

    root = args.root.resolve()
    rows, total_cases = collect(root)
    print(format_table(rows, total_cases))
    if args.csv:
        write_csv(rows, args.csv)
        print(f"csv={args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
