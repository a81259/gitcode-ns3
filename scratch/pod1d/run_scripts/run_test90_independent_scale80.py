#!/usr/bin/env python3
"""Prepare and run the serial test90 independent scale80 workload experiment."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean


SCRIPT_DIR = Path(__file__).resolve().parent
POD_ROOT = SCRIPT_DIR.parent
REPO_ROOT = POD_ROOT.parents[1]
SOURCE_TEST = "test10_dp_reduce_scatter"
TARGET_TEST = "test90_dp_reduce_scatter_independent_scale80"
SCALE80_SNAPSHOT_ROOT = (
    REPO_ROOT
    / "scratch/20260716-test08-test09-scale80-packet-spray-rr"
    / "artifacts/test08_09_scale80_all_cases_v2/input_snapshots/test09_dp_reduce_scatter"
)
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
CASE_INPUTS = ("network_attribute.txt", "node.csv", "topology.csv", "routing_table.csv")
SIZE_COLUMN = "dataSize(Byte)"
DEPENDENCY_COLUMN = "dependOnPhases"
START_COLUMN = "taskStartTime(us)"
COMPLETE_COLUMN = "taskCompletesTime(us)"
EXPECTED_SOURCE_TASKS = 6840
EXPECTED_FILTERED_TASKS = 1368
EXPECTED_FILTERED_BYTES = 7261283448


@dataclass(frozen=True)
class FilterSummary:
    total_tasks: int
    kept_tasks: int
    removed_tasks: int
    total_bytes: int
    kept_bytes: int


@dataclass(frozen=True)
class FctSummary:
    completed_tasks: int
    mean_us: float
    p95_us: float
    max_us: float


def filter_independent_traffic(source: Path, destination: Path) -> FilterSummary:
    with source.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if DEPENDENCY_COLUMN not in fieldnames:
            raise ValueError(f"{source} lacks {DEPENDENCY_COLUMN}")
        if SIZE_COLUMN not in fieldnames:
            raise ValueError(f"{source} lacks {SIZE_COLUMN}")
        rows = list(reader)

    kept_rows = [row for row in rows if not row[DEPENDENCY_COLUMN].strip()]
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(kept_rows)

    return FilterSummary(
        total_tasks=len(rows),
        kept_tasks=len(kept_rows),
        removed_tasks=len(rows) - len(kept_rows),
        total_bytes=sum(int(float(row[SIZE_COLUMN])) for row in rows),
        kept_bytes=sum(int(float(row[SIZE_COLUMN])) for row in kept_rows),
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def target_root() -> Path:
    return POD_ROOT / TARGET_TEST


def source_case_dir(case: str) -> Path:
    return POD_ROOT / SOURCE_TEST / case


def scale80_traffic_source(case: str) -> Path:
    source = SCALE80_SNAPSHOT_ROOT / case / "traffic.csv"
    if not source.is_file():
        raise FileNotFoundError(f"missing immutable scale80 traffic snapshot: {source}")
    return source


def target_case_dir(case: str) -> Path:
    return target_root() / case


def ensure_canonical_routing(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    expected = (
        'default ns3::UbApp::RoutingType "PER_PACKET_SHORTEST_PATHS"',
        'default ns3::UbTransportChannel::RoutingType "PER_PACKET_SHORTEST_PATHS"',
        'default ns3::UbLdstApi::RoutingType "PER_PACKET_SHORTEST_PATHS"',
        'default ns3::UbRoutingProcess::MultipathSelector "ROUND_ROBIN"',
    )
    missing = [line for line in expected if line not in text]
    if missing:
        raise ValueError(f"{path} lacks canonical routing settings: {missing}")


def prepare_case(case: str) -> dict[str, str]:
    source = source_case_dir(case)
    target = target_case_dir(case)
    if not source.is_dir():
        raise FileNotFoundError(f"missing source case: {source}")
    target.mkdir(parents=True, exist_ok=True)
    for name in CASE_INPUTS:
        shutil.copy2(source / name, target / name)
    ensure_canonical_routing(target / "network_attribute.txt")
    saved_source = target / "traffic.scale80.source.csv"
    shutil.copy2(scale80_traffic_source(case), saved_source)
    summary = filter_independent_traffic(saved_source, target / "traffic.csv")
    if summary.total_tasks != EXPECTED_SOURCE_TASKS:
        raise ValueError(f"{case} expected {EXPECTED_SOURCE_TASKS} source tasks, got {summary.total_tasks}")
    if summary.kept_tasks != EXPECTED_FILTERED_TASKS:
        raise ValueError(f"{case} expected {EXPECTED_FILTERED_TASKS} independent tasks, got {summary.kept_tasks}")
    if summary.kept_bytes != EXPECTED_FILTERED_BYTES:
        raise ValueError(f"{case} expected {EXPECTED_FILTERED_BYTES} independent bytes, got {summary.kept_bytes}")
    with (target / "traffic.csv").open(encoding="utf-8-sig", newline="") as handle:
        if any(row[DEPENDENCY_COLUMN].strip() for row in csv.DictReader(handle)):
            raise ValueError(f"{case} still contains dependent traffic")
    return {
        "case": case,
        "source_tasks": str(summary.total_tasks),
        "kept_tasks": str(summary.kept_tasks),
        "removed_tasks": str(summary.removed_tasks),
        "source_bytes": str(summary.total_bytes),
        "kept_bytes": str(summary.kept_bytes),
        "source_traffic_sha256": sha256_file(saved_source),
        "filtered_traffic_sha256": sha256_file(target / "traffic.csv"),
        "network_attribute_sha256": sha256_file(target / "network_attribute.txt"),
        "topology_sha256": sha256_file(target / "topology.csv"),
        "routing_table_sha256": sha256_file(target / "routing_table.csv"),
    }


def write_experiment_plan(root: Path) -> None:
    (root / "experiment-plan.md").write_text(
        "# test90 independent scale80 traffic\n\n"
        "- Base: test10 DP Reduce Scatter five formal cases.\n"
        "- Filter: retain only rows with blank `dependOnPhases`.\n"
        "- Workload: 1368 independent tasks and 7,261,283,448 bytes per case.\n"
        "- Routing: `PER_PACKET_SHORTEST_PATHS + ROUND_ROBIN`.\n"
        "- Runtime: one single-thread simulator process at a time, in standard-to-fault4 order.\n"
        "- Metric: task FCT = `taskCompletesTime(us) - taskStartTime(us)`.\n"
        "- Boundary: results are simulation-derived for this independent-task subset.\n",
        encoding="utf-8",
    )


def prepare_cases(artifact_dir: Path) -> list[dict[str, str]]:
    root = target_root()
    root.mkdir(parents=True, exist_ok=True)
    write_experiment_plan(root)
    rows = [prepare_case(case) for case in CASES]
    write_csv(artifact_dir / "traffic_filter_summary.csv", rows)
    for case in CASES:
        snapshot = artifact_dir / "input_snapshots" / case
        snapshot.mkdir(parents=True, exist_ok=True)
        for name in (*CASE_INPUTS, "traffic.scale80.source.csv", "traffic.csv"):
            shutil.copy2(target_case_dir(case) / name, snapshot / name)
    return rows


def build_command(case: str) -> list[str]:
    case_path = target_case_dir(case).relative_to(REPO_ROOT).as_posix()
    return [
        "python3.12",
        "./ns3",
        "run",
        "--no-build",
        (
            f"scratch/ub-quick-example --case-path={case_path} "
            "--dependency-visibility-delay=10ns"
        ),
    ]


def percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return math.nan
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (position - lower)


def summarize_fct(path: Path) -> tuple[FctSummary, list[float]]:
    if not path.is_file():
        return FctSummary(0, math.nan, math.nan, math.nan), []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        missing = {START_COLUMN, COMPLETE_COLUMN} - fields
        if missing:
            raise ValueError(f"{path} missing FCT columns: {sorted(missing)}")
        fcts = sorted(
            float(row[COMPLETE_COLUMN]) - float(row[START_COLUMN])
            for row in reader
            if row[START_COLUMN].strip() and row[COMPLETE_COLUMN].strip()
        )
    if not fcts:
        return FctSummary(0, math.nan, math.nan, math.nan), []
    return FctSummary(len(fcts), mean(fcts), percentile(fcts, 0.95), max(fcts)), fcts


def format_float(value: float) -> str:
    return "" if math.isnan(value) else f"{value:.6f}"


def clean_case_outputs(case: str) -> None:
    for name in ("runlog", "output"):
        shutil.rmtree(target_case_dir(case) / name, ignore_errors=True)


def summarize_case(case: str, returncode: int, elapsed_s: float, artifact_dir: Path, log_path: Path) -> dict[str, str]:
    archived_dir = artifact_dir / "task_statistics" / case
    archived_dir.mkdir(parents=True, exist_ok=True)
    archived = archived_dir / "task_statistics.csv"
    stats = target_case_dir(case) / "output/task_statistics.csv"
    if stats.is_file():
        shutil.copy2(stats, archived)
    summary, _ = summarize_fct(archived)
    return {
        "case": case,
        "label": CASE_LABELS[case],
        "returncode": str(returncode),
        "elapsed_s": f"{elapsed_s:.3f}",
        "expected_tasks": str(EXPECTED_FILTERED_TASKS),
        "completed_tasks": str(summary.completed_tasks),
        "completion_ratio": f"{summary.completed_tasks / EXPECTED_FILTERED_TASKS:.12f}",
        "fct_mean_us": format_float(summary.mean_us),
        "fct_p95_us": format_float(summary.p95_us),
        "fct_max_us": format_float(summary.max_us),
        "console_log": log_path.relative_to(artifact_dir).as_posix(),
        "task_statistics": archived.relative_to(artifact_dir).as_posix() if archived.is_file() else "",
    }


def run_serial(artifact_dir: Path) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for position, case in enumerate(CASES, start=1):
        clean_case_outputs(case)
        log_path = artifact_dir / "console_logs" / f"{case}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[{datetime.now():%H:%M:%S}] START {position}/5 {case} parallel=1/1", flush=True)
        started = time.monotonic()
        with log_path.open("w", encoding="utf-8") as log_stream:
            completed = subprocess.run(
                build_command(case),
                cwd=REPO_ROOT,
                stdout=log_stream,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        row = summarize_case(case, completed.returncode, time.monotonic() - started, artifact_dir, log_path)
        results.append(row)
        write_csv(artifact_dir / "fct_summary.csv", results)
        success = row["returncode"] == "0" and row["completed_tasks"] == row["expected_tasks"]
        print(
            f"[{datetime.now():%H:%M:%S}] DONE {'OK' if success else 'FAIL'} {case} "
            f"rc={row['returncode']} completed={row['completed_tasks']}/{row['expected_tasks']}",
            flush=True,
        )
        if not success:
            break
    return results


def read_fcts(path: Path) -> list[float]:
    return summarize_fct(path)[1]


def plot_cdf(results: list[dict[str, str]], artifact_dir: Path) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if len(results) != len(CASES):
        return []
    figure, axis = plt.subplots(figsize=(12.8, 7.2), constrained_layout=True)
    for case in CASES:
        row = next(result for result in results if result["case"] == case)
        fcts = read_fcts(artifact_dir / row["task_statistics"])
        axis.step(
            fcts,
            [(index + 1) / len(fcts) for index in range(len(fcts))],
            where="post",
            linewidth=2.3,
            color=CASE_COLORS[case],
            linestyle=CASE_LINESTYLES[case],
            label=CASE_LABELS[case],
        )
    axis.set_title("test90 Task FCT empirical CDF — independent scale80 traffic", fontsize=17, pad=16)
    axis.set_xlabel("Task FCT (us)", fontsize=13)
    axis.set_ylabel("Empirical CDF", fontsize=13)
    axis.set_ylim(0.0, 1.005)
    axis.grid(True, alpha=0.28)
    axis.legend(loc="lower right", fontsize=10)
    paths = [artifact_dir / "test90_task_fct_cdf.png", artifact_dir / "test90_task_fct_cdf.svg"]
    figure.savefig(paths[0], dpi=180)
    figure.savefig(paths[1])
    plt.close(figure)
    return paths


def write_results_markdown(results: list[dict[str, str]], artifact_dir: Path) -> None:
    lines = [
        "# test90 independent scale80 traffic FCT results",
        "",
        "- Source: test10 DP Reduce Scatter scale80 traffic.",
        "- Filter: `dependOnPhases` is blank for every retained task.",
        "- Routing: `PER_PACKET_SHORTEST_PATHS + ROUND_ROBIN`.",
        "- Runtime: serial, single-thread simulator process.",
        "",
        "| Case | Completed | Mean (us) | P95 (us) | Max (us) | RC |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in results:
        lines.append(
            f"| {row['label']} | {row['completed_tasks']}/{row['expected_tasks']} | "
            f"{row['fct_mean_us']} | {row['fct_p95_us']} | {row['fct_max_us']} | {row['returncode']} |"
        )
    lines.extend(
        [
            "",
            "## Direct rerun",
            "",
            "```bash",
            "/home/a81257/miniconda3/bin/python scratch/pod1d/run_scripts/run_test90_independent_scale80.py \\",
            "  --label test90_independent_scale80_rerun",
            "```",
        ]
    )
    (artifact_dir / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--label", default=f"run_{datetime.now():%Y%m%d_%H%M%S}")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifact_dir = target_root() / "artifacts" / args.label
    artifact_dir.mkdir(parents=True, exist_ok=False)
    print(f"repo_root={REPO_ROOT}", flush=True)
    print(f"target_root={target_root()}", flush=True)
    print(f"artifact_dir={artifact_dir}", flush=True)
    print("parallel=1 mtp_threads=disabled", flush=True)
    preparation_rows = prepare_cases(artifact_dir)
    print(
        f"prepared={len(preparation_rows)} cases independent_tasks={EXPECTED_FILTERED_TASKS}",
        flush=True,
    )
    if args.prepare_only:
        print("PREPARE_ONLY complete", flush=True)
        return 0
    results = run_serial(artifact_dir)
    write_results_markdown(results, artifact_dir)
    plots = plot_cdf(results, artifact_dir) if len(results) == len(CASES) else []
    failed = [
        row
        for row in results
        if row["returncode"] != "0" or row["completed_tasks"] != row["expected_tasks"]
    ]
    print(f"summary={artifact_dir / 'fct_summary.csv'}", flush=True)
    print(f"results={artifact_dir / 'results.md'}", flush=True)
    for plot in plots:
        print(f"plot={plot}", flush=True)
    print(f"total={len(results)} failed={len(failed)}", flush=True)
    return 0 if len(results) == len(CASES) and not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
