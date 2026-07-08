#!/usr/bin/env python3
"""Regenerate test07-test09 traffic.csv from preserved original traffic.

Edit SCALE_FACTOR below, then run this script from anywhere:

    python3 scratch/pod1d/scale_test07_09_traffic.py

The script preserves traffic.original.csv / traffic.ori.csv and overwrites only
traffic.csv. Use --dry-run to preview without writing files.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path


# Change this value manually when you want another scale.
# Example: 10 means traffic.csv dataSize(Byte) = original / 10.
SCALE_FACTOR = 10

TARGET_TESTS = (
    "test07_dp_reduce_scatter",
    "test08_dp_all_gather",
    "test09_dp_reduce_scatter",
)
SOURCE_NAMES = ("traffic.original.csv", "traffic.ori.csv", "traffic.ori")
OUTPUT_NAME = "traffic.csv"
SIZE_COL = "dataSize(Byte)"


@dataclass(frozen=True)
class RewriteSummary:
    test: str
    case: str
    status: str
    rows: int
    original_bytes: int
    scaled_bytes: int
    source: Path | None
    output: Path


def find_source(case_dir: Path) -> Path | None:
    for name in SOURCE_NAMES:
        candidate = case_dir / name
        if candidate.exists():
            return candidate
    return None


def scale_size(value: str, scale_factor: int) -> int:
    original = int(float(value))
    if original <= 0:
        return original
    scaled = original // scale_factor
    return max(1, scaled)


def rewrite_case(case_dir: Path, root: Path, dry_run: bool) -> RewriteSummary:
    source = find_source(case_dir)
    output = case_dir / OUTPUT_NAME
    if source is None:
        return RewriteSummary(
            test=case_dir.parent.name,
            case=case_dir.name,
            status="MISSING_ORIGINAL",
            rows=0,
            original_bytes=0,
            scaled_bytes=0,
            source=None,
            output=output.relative_to(root),
        )

    rows: list[dict[str, str]] = []
    original_total = 0
    scaled_total = 0
    with source.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if SIZE_COL not in (reader.fieldnames or []):
            raise ValueError(f"{source} missing required column {SIZE_COL!r}")

        fieldnames = list(reader.fieldnames)
        for row in reader:
            original = int(float(row[SIZE_COL]))
            scaled = scale_size(row[SIZE_COL], SCALE_FACTOR)
            row[SIZE_COL] = str(scaled)
            rows.append(row)
            original_total += original
            scaled_total += scaled

    if not dry_run:
        with output.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    return RewriteSummary(
        test=case_dir.parent.name,
        case=case_dir.name,
        status="DRY_RUN" if dry_run else "UPDATED",
        rows=len(rows),
        original_bytes=original_total,
        scaled_bytes=scaled_total,
        source=source.relative_to(root),
        output=output.relative_to(root),
    )


def discover_case_dirs(root: Path) -> list[Path]:
    case_dirs: list[Path] = []
    for test in TARGET_TESTS:
        test_dir = root / test
        if not test_dir.is_dir():
            continue
        case_dirs.extend(path for path in test_dir.glob("case*") if path.is_dir())
    return sorted(case_dirs, key=lambda p: (p.parent.name, p.name))


def print_summary(rows: list[RewriteSummary], dry_run: bool) -> None:
    print(f"scale_factor={SCALE_FACTOR} dry_run={dry_run} cases={len(rows)}")
    print("test,case,status,rows,original_bytes,scaled_bytes,ratio,source,output")
    for row in rows:
        ratio = "" if row.original_bytes == 0 else f"{row.scaled_bytes / row.original_bytes:.6f}"
        source = "" if row.source is None else row.source.as_posix()
        print(
            f"{row.test},{row.case},{row.status},{row.rows},"
            f"{row.original_bytes},{row.scaled_bytes},{ratio},"
            f"{source},{row.output.as_posix()}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="pod1d root directory; defaults to this script's directory",
    )
    parser.add_argument("--dry-run", action="store_true", help="preview without overwriting traffic.csv")
    args = parser.parse_args()

    if SCALE_FACTOR <= 0:
        raise ValueError("SCALE_FACTOR must be positive")

    root = args.root.resolve()
    summaries = [rewrite_case(case_dir, root, args.dry_run) for case_dir in discover_case_dirs(root)]
    print_summary(summaries, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
