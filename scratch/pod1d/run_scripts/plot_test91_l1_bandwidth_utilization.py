#!/usr/bin/env python3
"""Plot lower-switch->L1 and L1->L2 aggregate utilization in one chart."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


DEFAULT_INPUT = Path(
    "scratch/pod1d/run_scripts/batch_run_logs/"
    "test91_l1_bandwidth_probe_run_20260716/"
    "l1_hierarchy_instantaneous_bandwidth_500ns.csv"
)
DEFAULT_OUTPUT = Path(
    "scratch/pod1d/run_scripts/batch_run_logs/"
    "test91_l1_bandwidth_probe_run_20260716/"
    "test91_standard_lower_l1_vs_l1_l2_utilization_500ns.svg"
)


def load_series(path: Path, case: str) -> dict[str, tuple[list[float], list[float]]]:
    wanted = {"LOWER_TO_L1", "L1_TO_L2"}
    result: dict[str, tuple[list[float], list[float]]] = {
        category: ([], []) for category in wanted
    }
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            category = row["category"]
            if row["case"] != case or category not in wanted:
                continue
            times, utilizations = result[category]
            times.append((float(row["bucket_start_us"]) + float(row["bucket_end_us"])) / 2)
            utilizations.append(float(row["aggregate_utilization_percent"]))
    if any(not values[0] for values in result.values()):
        raise ValueError(f"missing required series for case={case!r} in {path}")
    return result


def write_svg(path: Path, series: dict[str, tuple[list[float], list[float]]], title: str) -> None:
    width, height = 1440, 780
    left, right, top, bottom = 115, 45, 75, 95
    chart_width, chart_height = width - left - right, height - top - bottom
    lower_time, lower_utilization = series["LOWER_TO_L1"]
    upper_time, upper_utilization = series["L1_TO_L2"]
    x_min, x_max = 0.0, max(lower_time + upper_time)
    y_min, y_max = 0.0, 110.0

    def x(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * chart_width

    def y(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * chart_height

    def points(times: list[float], values: list[float]) -> str:
        return " ".join(f"{x(time):.2f},{y(value):.2f}" for time, value in zip(times, values))

    fragments = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#202124}.tick{font-size:15px}.label{font-size:18px}.title{font-size:23px;font-weight:600}.note{font-size:13px;fill:#5f6368}</style>',
        f'<text class="title" x="720" y="38" text-anchor="middle">{title}</text>',
    ]
    for tick in range(0, 111, 20):
        py = y(tick)
        fragments.extend(
            [
                f'<line x1="{left}" y1="{py:.2f}" x2="{width - right}" y2="{py:.2f}" stroke="#d9dfe7" stroke-width="1"/>',
                f'<text class="tick" x="{left - 13}" y="{py + 5:.2f}" text-anchor="end">{tick}</text>',
            ]
        )
    for tick in range(0, int(x_max) + 1, 2):
        px = x(float(tick))
        fragments.extend(
            [
                f'<line x1="{px:.2f}" y1="{top}" x2="{px:.2f}" y2="{height - bottom}" stroke="#edf0f4" stroke-width="1"/>',
                f'<text class="tick" x="{px:.2f}" y="{height - bottom + 28}" text-anchor="middle">{tick}</text>',
            ]
        )
    fragments.extend(
        [
            f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="#202124" stroke-width="1.5"/>',
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="#202124" stroke-width="1.5"/>',
            f'<polyline points="{points(lower_time, lower_utilization)}" fill="none" stroke="#1772B4" stroke-width="3"/>',
            f'<polyline points="{points(upper_time, upper_utilization)}" fill="none" stroke="#E36A2C" stroke-width="3"/>',
        ]
    )
    for times, values, color, shape in (
        (lower_time, lower_utilization, "#1772B4", "circle"),
        (upper_time, upper_utilization, "#E36A2C", "rect"),
    ):
        for time, value in zip(times, values):
            px, py = x(time), y(value)
            if shape == "circle":
                fragments.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="3.1" fill="{color}"/>')
            else:
                fragments.append(f'<rect x="{px - 3:.2f}" y="{py - 3:.2f}" width="6" height="6" fill="{color}"/>')
    legend_x, legend_y = width - 405, top + 20
    fragments.extend(
        [
            f'<rect x="{legend_x}" y="{legend_y}" width="335" height="72" rx="5" fill="#ffffff" stroke="#c7cdd4"/>',
            f'<line x1="{legend_x + 16}" y1="{legend_y + 25}" x2="{legend_x + 55}" y2="{legend_y + 25}" stroke="#1772B4" stroke-width="3"/>',
            f'<text class="tick" x="{legend_x + 67}" y="{legend_y + 30}">Lower-stage switch → L1</text>',
            f'<line x1="{legend_x + 16}" y1="{legend_y + 53}" x2="{legend_x + 55}" y2="{legend_y + 53}" stroke="#E36A2C" stroke-width="3"/>',
            f'<text class="tick" x="{legend_x + 67}" y="{legend_y + 58}">L1 → L2</text>',
            f'<text class="label" x="{left + chart_width / 2:.2f}" y="{height - 32}" text-anchor="middle">Time (us)</text>',
            f'<text class="label" x="30" y="{top + chart_height / 2:.2f}" text-anchor="middle" transform="rotate(-90 30 {top + chart_height / 2:.2f})">Aggregate link utilization (%)</text>',
            f'<text class="note" x="{left}" y="{height - 8}">500 ns Tx-start buckets; values slightly above 100% are bucket-edge quantization.</text>',
            '</svg>',
        ]
    )
    path.write_text("\n".join(fragments), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--case", default="standard")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--title",
        default="Test91 / Standard topology / seed 202 / 224 Gbps Access–L1",
    )
    args = parser.parse_args()

    series = load_series(args.input, args.case)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_svg(args.output, series, args.title)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
