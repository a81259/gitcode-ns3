#!/usr/bin/env python3
"""Render the renumbered test09/test10 scale20 Task FCT CDFs by phase."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
POD_ROOT = SCRIPT_DIR.parent
REPO_ROOT = POD_ROOT.parents[1]
SOURCE_ROOT = (
    REPO_ROOT
    / "scratch/20260717-test08-test09-scale20-packet-spray-rr"
    / "artifacts/test08_09_scale20_all_cases"
    / "task_statistics"
)
DEFAULT_OUTPUT_DIR = POD_ROOT / "cdf"
TESTS = ("test09_dp_all_gather", "test10_dp_reduce_scatter")
TEST_SHORT_NAMES = {
    "test09_dp_all_gather": "test09",
    "test10_dp_reduce_scatter": "test10",
}
ARCHIVED_TEST_DIRS = {
    "test09_dp_all_gather": "test08_dp_all_gather",
    "test10_dp_reduce_scatter": "test09_dp_reduce_scatter",
}
CASES = (
    "case01_标准topo",
    "case02_故障1topo_单链路lane",
    "case03_故障2topo_单链路laport",
    "case04_故障3topo_分布式多链路port",
    "case05_故障4topo_分集中式多链路port",
)
CASE_LABELS = {
    "case01_标准topo": "Standard",
    "case02_故障1topo_单链路lane": "Fault 1: one link 448G→224G",
    "case03_故障2topo_单链路laport": "Fault 2: one link down",
    "case04_故障3topo_分布式多链路port": "Fault 3: 18 distributed links down",
    "case05_故障4topo_分集中式多链路port": "Fault 4: 18 concentrated links down",
}
CASE_COLORS = {
    "case01_标准topo": "#2f4f3e",
    "case02_故障1topo_单链路lane": "#d84a5b",
    "case03_故障2topo_单链路laport": "#7a5aa6",
    "case04_故障3topo_分布式多链路port": "#087f8c",
    "case05_故障4topo_分集中式多链路port": "#d18f00",
}
CASE_LINESTYLES = {
    "case01_标准topo": "-",
    "case02_故障1topo_单链路lane": "--",
    "case03_故障2topo_单链路laport": ":",
    "case04_故障3topo_分布式多链路port": "-.",
    "case05_故障4topo_分集中式多链路port": (0, (5, 2, 1, 2)),
}
PHASE_BUCKETS = (0, 1, 2, 3, 4)
PHASE_COLUMN = "phaseId"
START_COLUMN = "taskStartTime(us)"
COMPLETE_COLUMN = "taskCompletesTime(us)"
EXPECTED_ALL_TASKS = 6840
EXPECTED_BUCKET_TASKS = 1368


@dataclass(frozen=True)
class FigureSpec:
    test: str
    phase_position: int | None
    output_name: str


def phase_bucket(phase_id: int) -> int:
    if phase_id < 0:
        raise ValueError(f"phaseId must be nonnegative, got {phase_id}")
    return phase_id % len(PHASE_BUCKETS)


def build_figure_specs() -> list[FigureSpec]:
    specs: list[FigureSpec] = []
    for test in TESTS:
        short_name = TEST_SHORT_NAMES[test]
        for phase_position in PHASE_BUCKETS:
            specs.append(
                FigureSpec(
                    test=test,
                    phase_position=phase_position,
                    output_name=f"{short_name}_scale20_phase{phase_position}_task_fct_cdf.png",
                )
            )
        specs.append(
            FigureSpec(
                test=test,
                phase_position=None,
                output_name=f"{short_name}_scale20_all_phases_task_fct_cdf.png",
            )
        )
    return specs


def stats_path(test: str, case: str) -> Path:
    return SOURCE_ROOT / ARCHIVED_TEST_DIRS[test] / case / "task_statistics.csv"


def read_fcts(test: str, case: str, phase_position: int | None) -> list[float]:
    path = stats_path(test, case)
    if not path.is_file():
        raise FileNotFoundError(f"missing scale20 task statistics: {path}")
    fcts: list[float] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {PHASE_COLUMN, START_COLUMN, COMPLETE_COLUMN}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} missing columns: {sorted(missing)}")
        for row in reader:
            if not row[START_COLUMN].strip() or not row[COMPLETE_COLUMN].strip():
                continue
            if phase_position is not None and phase_bucket(int(row[PHASE_COLUMN])) != phase_position:
                continue
            fcts.append(float(row[COMPLETE_COLUMN]) - float(row[START_COLUMN]))
    fcts.sort()
    expected = EXPECTED_ALL_TASKS if phase_position is None else EXPECTED_BUCKET_TASKS
    if len(fcts) != expected:
        raise ValueError(f"{path} expected {expected} completed tasks, got {len(fcts)}")
    return fcts


def cdf_y_values(values: list[float]) -> list[float]:
    return [(index + 1) / len(values) for index in range(len(values))]


def figure_title(spec: FigureSpec) -> str:
    if spec.phase_position is None:
        return f"{spec.test} Task FCT empirical CDF — scale20, packet spray round robin"
    return (
        f"{spec.test} Task FCT empirical CDF — scale20, "
        f"phase position {spec.phase_position} (phaseId mod 5)"
    )


def render_figure(spec: FigureSpec, output_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(12.8, 7.2), constrained_layout=True)
    for case in CASES:
        fcts = read_fcts(spec.test, case, spec.phase_position)
        axis.step(
            fcts,
            cdf_y_values(fcts),
            where="post",
            linewidth=2.3,
            color=CASE_COLORS[case],
            linestyle=CASE_LINESTYLES[case],
            label=CASE_LABELS[case],
        )
    axis.set_title(figure_title(spec), fontsize=17, pad=16)
    axis.set_xlabel("Task FCT (us)", fontsize=13)
    axis.set_ylabel("Empirical CDF", fontsize=13)
    axis.set_ylim(0.0, 1.005)
    axis.grid(True, alpha=0.28)
    axis.legend(loc="lower right", fontsize=10)
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def render_all(output_dir: Path, overwrite: bool) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = [output_dir / spec.output_name for spec in build_figure_specs()]
    existing = [path for path in outputs if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing PNGs: {existing}")
    for spec, output in zip(build_figure_specs(), outputs, strict=True):
        render_figure(spec, output)
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = render_all(args.output_dir.resolve(), args.overwrite)
    for output in outputs:
        print(output)
    print(f"total_png={len(outputs)} output_dir={args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
