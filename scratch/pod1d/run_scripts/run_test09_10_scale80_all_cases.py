#!/usr/bin/env python3
"""Prepare, run, summarize, and plot test09/test10 scale80 case variants."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import os
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
DEFAULT_PACKAGE_ROOT = REPO_ROOT / "scratch/20260717-test09-test10-scale80-packet-spray-rr"
TESTS = ("test09_dp_all_gather", "test10_dp_reduce_scatter")
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
SIZE_COLUMN = "dataSize(Byte)"
START_COLUMN = "taskStartTime(us)"
COMPLETE_COLUMN = "taskCompletesTime(us)"
REQUIRED_INPUTS = (
    "network_attribute.txt",
    "node.csv",
    "topology.csv",
    "routing_table.csv",
    "traffic.original.csv",
)
SNAPSHOT_INPUTS = REQUIRED_INPUTS + ("traffic.csv",)
ROUTING_OWNER_TYPES = ("ns3::UbApp", "ns3::UbTransportChannel", "ns3::UbLdstApi")
REMOVED_ROUTING_KEYS = {
    *(f"{owner}::UsePacketSpray" for owner in ROUTING_OWNER_TYPES),
    *(f"{owner}::UseShortestPaths" for owner in ROUTING_OWNER_TYPES),
    *(f"{owner}::RoutingType" for owner in ROUTING_OWNER_TYPES),
    "ns3::UbRoutingProcess::PacketSprayMode",
    "ns3::UbRoutingProcess::RoutingAlgorithm",
    "ns3::UbRoutingProcess::MultipathSelector",
    "ns3::UbRoutingProcess::BwWeightedPacketSpray",
    "ns3::UbRoutingProcess::BwWeightedPacketSprayScope",
}
RENAMED_ATTRIBUTE_KEYS = {
    "ns3::UbJetty::UbInflightMax": "ns3::UbJetty::UbJettyInflightMax",
    "ns3::UbTransportChannel::InitialRTO": "ns3::UbTransportChannel::BaseRTO",
}


@dataclass(frozen=True)
class Job:
    test: str
    case: str

    @property
    def case_dir(self) -> Path:
        return POD_ROOT / self.test / self.case

    @property
    def relative_case_dir(self) -> str:
        return self.case_dir.relative_to(REPO_ROOT).as_posix()

    @property
    def name(self) -> str:
        return f"{self.test}/{self.case}"

    @property
    def stats_path(self) -> Path:
        return self.case_dir / "output/task_statistics.csv"


@dataclass(frozen=True)
class TrafficScaleSummary:
    rows: int
    original_bytes: int
    scaled_bytes: int


@dataclass(frozen=True)
class FctSummary:
    completed_tasks: int
    mean_us: float
    p95_us: float
    max_us: float


@dataclass
class ActiveRun:
    job: Job
    process: subprocess.Popen[str]
    start_time: float
    log_path: Path
    log_stream: object


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return math.nan
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def scale_traffic(source: Path, destination: Path, scale: int) -> TrafficScaleSummary:
    rows: list[dict[str, str]] = []
    original_bytes = 0
    scaled_bytes = 0
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if SIZE_COLUMN not in fieldnames:
            raise ValueError(f"{source} missing required column {SIZE_COLUMN!r}")
        for row in reader:
            original = int(float(row[SIZE_COLUMN]))
            scaled = original if original <= 0 else max(1, original // scale)
            row[SIZE_COLUMN] = str(scaled)
            rows.append(row)
            original_bytes += original
            scaled_bytes += scaled

    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return TrafficScaleSummary(len(rows), original_bytes, scaled_bytes)


def parse_default_key(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("default "):
        return None
    parts = stripped.split(maxsplit=2)
    return parts[1] if len(parts) >= 2 else None


def rewrite_routing_attributes(path: Path) -> None:
    retained: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        key = parse_default_key(line)
        if key in REMOVED_ROUTING_KEYS:
            continue
        if key in RENAMED_ATTRIBUTE_KEYS:
            line = line.replace(key, RENAMED_ATTRIBUTE_KEYS[key], 1)
        retained.append(line)
    canonical = [
        'default ns3::UbApp::RoutingType "PER_PACKET_SHORTEST_PATHS"',
        'default ns3::UbTransportChannel::RoutingType "PER_PACKET_SHORTEST_PATHS"',
        'default ns3::UbLdstApi::RoutingType "PER_PACKET_SHORTEST_PATHS"',
        'default ns3::UbRoutingProcess::MultipathSelector "ROUND_ROBIN"',
    ]
    path.write_text("\n".join(canonical + retained) + "\n", encoding="utf-8")


def build_queues(tests: tuple[str, ...] = TESTS) -> dict[str, list[Job]]:
    return {test: [Job(test, case) for case in CASES] for test in tests}


def ensure_inputs(jobs: list[Job]) -> None:
    for job in jobs:
        if not job.case_dir.is_dir():
            raise FileNotFoundError(f"missing case directory: {job.case_dir}")
        for name in REQUIRED_INPUTS:
            if not (job.case_dir / name).is_file():
                raise FileNotFoundError(f"missing {name}: {job.case_dir}")


def prepare_jobs(jobs: list[Job], scale: int) -> list[dict[str, str]]:
    summaries: list[dict[str, str]] = []
    for job in jobs:
        traffic = scale_traffic(
            job.case_dir / "traffic.original.csv",
            job.case_dir / "traffic.csv",
            scale,
        )
        rewrite_routing_attributes(job.case_dir / "network_attribute.txt")
        summaries.append(
            {
                "test": job.test,
                "case": job.case,
                "scale": str(scale),
                "tasks": str(traffic.rows),
                "original_bytes": str(traffic.original_bytes),
                "scaled_bytes": str(traffic.scaled_bytes),
                "scale_ratio": f"{traffic.scaled_bytes / traffic.original_bytes:.12f}",
                "traffic_sha256": sha256_file(job.case_dir / "traffic.csv"),
                "network_attribute_sha256": sha256_file(
                    job.case_dir / "network_attribute.txt"
                ),
            }
        )
    return summaries


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def topology_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    forward = (row["nodeId1"], row["portId1"], row["nodeId2"], row["portId2"])
    reverse = (row["nodeId2"], row["portId2"], row["nodeId1"], row["portId1"])
    return min(forward, reverse)


def input_difference_rows(tests: tuple[str, ...] = TESTS) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for test in tests:
        standard_dir = POD_ROOT / test / CASES[0]
        standard_topology = {
            topology_key(row): row for row in read_csv_rows(standard_dir / "topology.csv")
        }
        standard_routes_hash = sha256_file(standard_dir / "routing_table.csv")
        standard_node_hash = sha256_file(standard_dir / "node.csv")
        standard_traffic_hash = sha256_file(standard_dir / "traffic.csv")
        standard_attribute_hash = sha256_file(standard_dir / "network_attribute.txt")
        for case in CASES:
            case_dir = POD_ROOT / test / case
            topology_rows = read_csv_rows(case_dir / "topology.csv")
            topology = {topology_key(row): row for row in topology_rows}
            removed = sorted(set(standard_topology) - set(topology))
            added = sorted(set(topology) - set(standard_topology))
            changed_bandwidth = sorted(
                key
                for key in set(standard_topology) & set(topology)
                if standard_topology[key]["bandwidth"] != topology[key]["bandwidth"]
            )
            rows.append(
                {
                    "test": test,
                    "case": case,
                    "role": "control" if case == CASES[0] else "treatment",
                    "topology_links": str(len(topology_rows)),
                    "removed_links_vs_standard": str(len(removed)),
                    "added_links_vs_standard": str(len(added)),
                    "bandwidth_changed_links_vs_standard": str(len(changed_bandwidth)),
                    "bandwidth_changes": " | ".join(
                        f"{key}:{standard_topology[key]['bandwidth']}->{topology[key]['bandwidth']}"
                        for key in changed_bandwidth
                    ),
                    "routing_table_same_as_standard": str(
                        sha256_file(case_dir / "routing_table.csv") == standard_routes_hash
                    ),
                    "node_same_as_standard": str(
                        sha256_file(case_dir / "node.csv") == standard_node_hash
                    ),
                    "traffic_same_as_standard": str(
                        sha256_file(case_dir / "traffic.csv") == standard_traffic_hash
                    ),
                    "network_attribute_same_as_standard": str(
                        sha256_file(case_dir / "network_attribute.txt")
                        == standard_attribute_hash
                    ),
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"refusing to write empty CSV: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def snapshot_inputs(jobs: list[Job], artifact_dir: Path) -> None:
    for job in jobs:
        destination = artifact_dir / "input_snapshots" / job.test / job.case
        destination.mkdir(parents=True, exist_ok=True)
        for name in SNAPSHOT_INPUTS:
            source = job.case_dir / name
            if source.is_file():
                shutil.copy2(source, destination / name)


def mem_available_gib() -> float:
    try:
        with Path("/proc/meminfo").open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024 / 1024
    except FileNotFoundError:
        return 999.0
    return 0.0


def clean_outputs(job: Job) -> None:
    shutil.rmtree(job.case_dir / "runlog", ignore_errors=True)
    shutil.rmtree(job.case_dir / "output", ignore_errors=True)


def build_command(job: Job) -> list[str]:
    return [
        "python3.12",
        "./ns3",
        "run",
        "--no-build",
        (
            f"scratch/ub-quick-example --case-path={job.relative_case_dir} "
            "--dependency-visibility-delay=10ns"
        ),
    ]


def launch(job: Job, artifact_dir: Path) -> ActiveRun:
    clean_outputs(job)
    log_path = artifact_dir / "console_logs" / f"{job.test}__{job.case}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_stream = log_path.open("w", encoding="utf-8")
    command = build_command(job)
    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        stdout=log_stream,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    return ActiveRun(job, process, time.monotonic(), log_path, log_stream)


def terminate_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=15)


def summarize_fct(path: Path) -> tuple[FctSummary, list[float]]:
    if not path.is_file():
        return FctSummary(0, math.nan, math.nan, math.nan), []
    fcts: list[float] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        missing = {START_COLUMN, COMPLETE_COLUMN} - fields
        if missing:
            raise ValueError(f"{path} missing columns: {sorted(missing)}")
        for row in reader:
            start = row.get(START_COLUMN, "").strip()
            complete = row.get(COMPLETE_COLUMN, "").strip()
            if not start or not complete:
                continue
            fcts.append(float(complete) - float(start))
    fcts.sort()
    if not fcts:
        return FctSummary(0, math.nan, math.nan, math.nan), []
    return (
        FctSummary(
            completed_tasks=len(fcts),
            mean_us=mean(fcts),
            p95_us=percentile(fcts, 0.95),
            max_us=max(fcts),
        ),
        fcts,
    )


def archive_stats(job: Job, artifact_dir: Path) -> Path:
    destination = artifact_dir / "task_statistics" / job.test / job.case
    destination.mkdir(parents=True, exist_ok=True)
    archived = destination / "task_statistics.csv"
    if job.stats_path.is_file():
        shutil.copy2(job.stats_path, archived)
    return archived


def result_row(
    job: Job,
    returncode: int,
    elapsed_s: float,
    artifact_dir: Path,
    log_path: Path,
) -> dict[str, str]:
    archived_stats = archive_stats(job, artifact_dir)
    summary, _ = summarize_fct(archived_stats)
    expected_tasks = sum(1 for _ in read_csv_rows(job.case_dir / "traffic.csv"))
    return {
        "test": job.test,
        "case": job.case,
        "label": CASE_LABELS[job.case],
        "returncode": str(returncode),
        "elapsed_s": f"{elapsed_s:.3f}",
        "expected_tasks": str(expected_tasks),
        "completed_tasks": str(summary.completed_tasks),
        "completion_ratio": (
            f"{summary.completed_tasks / expected_tasks:.12f}" if expected_tasks else ""
        ),
        "fct_mean_us": format_float(summary.mean_us),
        "fct_p95_us": format_float(summary.p95_us),
        "fct_max_us": format_float(summary.max_us),
        "console_log": log_path.relative_to(REPO_ROOT).as_posix(),
        "task_statistics": (
            archived_stats.relative_to(REPO_ROOT).as_posix()
            if archived_stats.is_file()
            else ""
        ),
        "case_output": (job.case_dir / "output").relative_to(REPO_ROOT).as_posix(),
        "case_runlog": (job.case_dir / "runlog").relative_to(REPO_ROOT).as_posix(),
    }


def format_float(value: float) -> str:
    return "" if math.isnan(value) else f"{value:.6f}"


def write_run_ledger(results: list[dict[str, str]], artifact_dir: Path) -> None:
    ordered = sorted(
        results,
        key=lambda row: (TESTS.index(row["test"]), CASES.index(row["case"])),
    )
    write_csv(artifact_dir / "fct_summary.csv", ordered)


def run_queues(
    queues: dict[str, list[Job]],
    parallel: int,
    artifact_dir: Path,
    poll_seconds: float,
    min_mem_gib: float,
) -> list[dict[str, str]]:
    if parallel != 2:
        raise ValueError("this experiment requires --parallel=2")
    active: dict[str, ActiveRun] = {}
    results: list[dict[str, str]] = []
    try:
        while any(queues.values()) or active:
            for test in TESTS:
                if len(active) >= parallel:
                    break
                if test in active or not queues[test]:
                    continue
                if mem_available_gib() < min_mem_gib:
                    print(
                        f"[{datetime.now():%H:%M:%S}] WAIT "
                        f"mem_available={mem_available_gib():.1f}GiB "
                        f"below {min_mem_gib:.1f}GiB",
                        flush=True,
                    )
                    break
                job = queues[test].pop(0)
                active[test] = launch(job, artifact_dir)
                print(
                    f"[{datetime.now():%H:%M:%S}] START {job.name} "
                    f"parallel={len(active)}/{parallel} "
                    f"mem_available={mem_available_gib():.1f}GiB",
                    flush=True,
                )

            if not active:
                time.sleep(poll_seconds)
                continue

            time.sleep(poll_seconds)
            for test in list(active):
                run = active[test]
                returncode = run.process.poll()
                if returncode is None:
                    continue
                run.log_stream.close()
                elapsed = time.monotonic() - run.start_time
                row = result_row(
                    run.job,
                    returncode,
                    elapsed,
                    artifact_dir,
                    run.log_path,
                )
                results.append(row)
                write_run_ledger(results, artifact_dir)
                status = (
                    "OK"
                    if returncode == 0
                    and row["completed_tasks"] == row["expected_tasks"]
                    else "FAIL"
                )
                print(
                    f"[{datetime.now():%H:%M:%S}] DONE {status} {run.job.name} "
                    f"rc={returncode} elapsed={elapsed:.1f}s "
                    f"completed={row['completed_tasks']}/{row['expected_tasks']}",
                    flush=True,
                )
                del active[test]
    except BaseException:
        for run in active.values():
            terminate_process_group(run.process)
            run.log_stream.close()
        raise
    return results


def empirical_cdf(values: list[float]) -> tuple[list[float], list[float]]:
    if not values:
        return [], []
    return values, [(index + 1) / len(values) for index in range(len(values))]


def plot_cdfs(results: list[dict[str, str]], artifact_dir: Path, scale: int) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    result_map = {(row["test"], row["case"]): row for row in results}
    paths: list[Path] = []
    for test in TESTS:
        fig, axis = plt.subplots(figsize=(12.8, 7.2), constrained_layout=True)
        plotted = 0
        for case in CASES:
            row = result_map.get((test, case))
            if not row or not row["task_statistics"]:
                continue
            stats_path = REPO_ROOT / row["task_statistics"]
            _, fcts = summarize_fct(stats_path)
            x_values, y_values = empirical_cdf(fcts)
            if not x_values:
                continue
            axis.step(
                x_values,
                y_values,
                where="post",
                linewidth=2.3,
                color=CASE_COLORS[case],
                linestyle=CASE_LINESTYLES[case],
                label=CASE_LABELS[case],
            )
            plotted += 1
        axis.set_title(
            f"{test} Task FCT empirical CDF — scale{scale}, packet spray round robin",
            fontsize=17,
            pad=16,
        )
        axis.set_xlabel("Task FCT (us)", fontsize=13)
        axis.set_ylabel("Empirical CDF", fontsize=13)
        axis.set_ylim(0.0, 1.005)
        axis.grid(True, alpha=0.28)
        axis.legend(loc="lower right", fontsize=10)
        if plotted != len(CASES):
            axis.text(
                0.02,
                0.98,
                f"Only {plotted}/{len(CASES)} cases produced FCT data",
                transform=axis.transAxes,
                ha="left",
                va="top",
                color="#b22222",
            )
        base = artifact_dir / f"{test}_task_fct_cdf_scale{scale}"
        for suffix in (".png", ".svg"):
            path = base.with_suffix(suffix)
            fig.savefig(path, dpi=180 if suffix == ".png" else None)
            paths.append(path)
        plt.close(fig)
    return paths


def write_result_markdown(
    results: list[dict[str, str]],
    input_rows: list[dict[str, str]],
    artifact_dir: Path,
    scale: int,
) -> None:
    ordered = sorted(
        results,
        key=lambda row: (TESTS.index(row["test"]), CASES.index(row["case"])),
    )
    lines = [
        f"# test09/test10 scale{scale} Task FCT Results",
        "",
        "## Fixed Controls",
        "",
        "- Packet spray: `PER_PACKET_SHORTEST_PATHS`",
        "- Multipath selector: `ROUND_ROBIN`",
        "- Phase dependency visibility delay: `10ns`",
        "- Runtime: single-thread simulation, two concurrent case processes",
        "- Per-test order: standard, fault1, fault2, fault3, fault4",
        "- Metric: task FCT = `taskCompletesTime(us) - taskStartTime(us)`",
        "",
        "## Summary",
        "",
        "| Test | Case | Completed | Mean (us) | P95 (us) | Max (us) | RC |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in ordered:
        lines.append(
            f"| {row['test']} | {row['label']} | "
            f"{row['completed_tasks']}/{row['expected_tasks']} | "
            f"{row['fct_mean_us']} | {row['fct_p95_us']} | "
            f"{row['fct_max_us']} | {row['returncode']} |"
        )
    lines.extend(
        [
            "",
            "## Input Difference Evidence",
            "",
            f"- Detailed case-derived differences: `{(artifact_dir / 'input_diff_summary.csv').relative_to(REPO_ROOT)}`",
            f"- Prepared traffic evidence: `{(artifact_dir / 'traffic_scale_summary.csv').relative_to(REPO_ROOT)}`",
            "",
        ]
    )
    (artifact_dir / "results.md").write_text("\n".join(lines), encoding="utf-8")


def write_preparation_artifacts(
    jobs: list[Job],
    preparation_rows: list[dict[str, str]],
    input_rows: list[dict[str, str]],
    artifact_dir: Path,
) -> None:
    write_csv(artifact_dir / "traffic_scale_summary.csv", preparation_rows)
    write_csv(artifact_dir / "input_diff_summary.csv", input_rows)
    snapshot_inputs(jobs, artifact_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", type=int, default=80)
    parser.add_argument("--parallel", type=int, default=2)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--min-mem-gib", type=float, default=8.0)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument(
        "--package-root",
        type=Path,
        default=DEFAULT_PACKAGE_ROOT,
    )
    parser.add_argument(
        "--label",
        default=f"run_{datetime.now():%Y%m%d_%H%M%S}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.scale <= 0:
        raise ValueError("--scale must be positive")
    if args.parallel != 2:
        raise ValueError("--parallel must be exactly 2")
    if args.poll_seconds <= 0:
        raise ValueError("--poll-seconds must be positive")
    if args.min_mem_gib < 0:
        raise ValueError("--min-mem-gib must be non-negative")

    jobs = [Job(test, case) for test in TESTS for case in CASES]
    ensure_inputs(jobs)
    artifact_dir = args.package_root.resolve() / "artifacts" / args.label
    artifact_dir.mkdir(parents=True, exist_ok=False)
    print(f"repo_root={REPO_ROOT}", flush=True)
    print(f"artifact_dir={artifact_dir}", flush=True)
    print(f"scale={args.scale} tests={','.join(TESTS)} cases={len(CASES)}", flush=True)
    print(f"parallel={args.parallel} mtp_threads=disabled", flush=True)

    preparation_rows = prepare_jobs(jobs, args.scale)
    input_rows = input_difference_rows()
    write_preparation_artifacts(jobs, preparation_rows, input_rows, artifact_dir)
    scaled_totals = {row["scaled_bytes"] for row in preparation_rows}
    traffic_hashes_by_test = {
        test: {
            row["traffic_sha256"]
            for row in preparation_rows
            if row["test"] == test
        }
        for test in TESTS
    }
    if len(scaled_totals) != 1 or any(len(hashes) != 1 for hashes in traffic_hashes_by_test.values()):
        raise RuntimeError("prepared traffic is not identical across the five cases of each test")
    if args.prepare_only:
        print("PREPARE_ONLY complete", flush=True)
        return 0

    results = run_queues(
        build_queues(),
        parallel=args.parallel,
        artifact_dir=artifact_dir,
        poll_seconds=args.poll_seconds,
        min_mem_gib=args.min_mem_gib,
    )
    plot_paths = plot_cdfs(results, artifact_dir, args.scale)
    write_result_markdown(results, input_rows, artifact_dir, args.scale)
    failed = [
        row
        for row in results
        if row["returncode"] != "0"
        or row["completed_tasks"] != row["expected_tasks"]
    ]
    print(f"summary={artifact_dir / 'fct_summary.csv'}", flush=True)
    print(f"results={artifact_dir / 'results.md'}", flush=True)
    for path in plot_paths:
        print(f"plot={path}", flush=True)
    print(f"total={len(results)} failed={len(failed)}", flush=True)
    return 0 if len(results) == len(jobs) and not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
