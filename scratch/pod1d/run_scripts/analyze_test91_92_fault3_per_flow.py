#!/usr/bin/env python3
"""Write per-flow standard-versus-fault3 comparisons for test91 and test92."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
POD_ROOT = SCRIPT_DIR.parent
DEFAULT_OUTPUT_DIR = (
    SCRIPT_DIR / "batch_run_logs" / "test91_92_independent_scale160_run_20260716"
)
TESTS = (
    ("test91_dp_reduce_scatter", "test91（Reduce-Scatter）"),
    ("test92_dp_all_gather", "test92（All-Gather）"),
)
STANDARD_CASE = "case01_standard"
FAULT3_CASE = "case06_pod1_18_l1_first_l2_port_down"
STANDARD_TITLE = "标准拓扑"
FAULT3_TITLE = "故障3（L1–L2 分布式 Port Down，每个 POD 1 根）"
COMPLETE_COL = "taskCompletesTime(us)"


def load(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["taskId"]: row for row in csv.DictReader(handle)}


def direction(delta: float) -> str:
    if delta < 0:
        return "faster"
    if delta > 0:
        return "slower"
    return "unchanged"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    flow_rows: list[dict[str, str]] = []
    phase_rows: list[dict[str, str]] = []
    test_rows: list[dict[str, str]] = []
    for test_dir, test_title in TESTS:
        standard_path = POD_ROOT / test_dir / STANDARD_CASE / "output" / "task_statistics.csv"
        fault_path = POD_ROOT / test_dir / FAULT3_CASE / "output" / "task_statistics.csv"
        standard = load(standard_path)
        fault = load(fault_path)
        if standard.keys() != fault.keys():
            raise ValueError(f"task IDs differ: {standard_path} vs {fault_path}")

        phase_deltas: dict[str, list[float]] = defaultdict(list)
        deltas: list[float] = []
        counts: dict[str, int] = defaultdict(int)
        for task_id in sorted(standard, key=int):
            base = standard[task_id]
            case = fault[task_id]
            base_time = float(base[COMPLETE_COL])
            fault_time = float(case[COMPLETE_COL])
            delta = fault_time - base_time
            result = direction(delta)
            deltas.append(delta)
            counts[result] += 1
            phase_deltas[base["phaseId"]].append(delta)
            flow_rows.append(
                {
                    "test": test_title,
                    "baseline_title": STANDARD_TITLE,
                    "fault_title": FAULT3_TITLE,
                    "taskId": task_id,
                    "phaseId": base["phaseId"],
                    "sourceNode": base["sourceNode"],
                    "destNode": base["destNode"],
                    "dataSize(Byte)": base["dataSize(Byte)"],
                    "standard_complete_us": f"{base_time:.6f}",
                    "fault3_complete_us": f"{fault_time:.6f}",
                    "delta_us": f"{delta:.6f}",
                    "delta_percent": f"{(delta / base_time * 100) if base_time else 0.0:.6f}",
                    "comparison": result,
                }
            )

        for phase_id in sorted(phase_deltas, key=int):
            values = phase_deltas[phase_id]
            phase_rows.append(
                {
                    "test": test_title,
                    "phaseId": phase_id,
                    "flows": str(len(values)),
                    "faster": str(sum(value < 0 for value in values)),
                    "slower": str(sum(value > 0 for value in values)),
                    "unchanged": str(sum(value == 0 for value in values)),
                    "delta_sum_us": f"{sum(values):.6f}",
                    "delta_mean_us": f"{sum(values) / len(values):.6f}",
                    "delta_min_us": f"{min(values):.6f}",
                    "delta_max_us": f"{max(values):.6f}",
                }
            )
        test_rows.append(
            {
                "test": test_title,
                "flows": str(len(deltas)),
                "faster": str(counts["faster"]),
                "slower": str(counts["slower"]),
                "unchanged": str(counts["unchanged"]),
                "delta_sum_us": f"{sum(deltas):.6f}",
                "delta_mean_us": f"{sum(deltas) / len(deltas):.9f}",
            }
        )

    outputs = (
        ("fault3_per_flow_comparison.csv", flow_rows),
        ("fault3_per_phase_summary.csv", phase_rows),
        ("fault3_per_test_summary.csv", test_rows),
    )
    for name, rows in outputs:
        with (output_dir / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(output_dir / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
