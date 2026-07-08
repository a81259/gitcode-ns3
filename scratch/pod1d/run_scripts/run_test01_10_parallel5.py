#!/usr/bin/env python3
"""Run pod1d test01 and test10 variants with bounded concurrency."""

from __future__ import annotations

import argparse
import csv
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parents[1]
HOSTS_PER_POD = 72
TEST_DIRS = (
    "test01_tp_all_gather",
    "test10_pairwise_10mb",
)
VARIANTS = (
    "case01_standard",
    "case02_host_l1_lane_down",
    "case03_host_l1_port_down",
    "case04_l1_l2_lane_down",
    "case05_l1_l2_port_down",
)


@dataclass(frozen=True)
class Job:
    test_dir: Path
    variant: str

    @property
    def case_path(self) -> Path:
        return self.test_dir / self.variant

    @property
    def name(self) -> str:
        return f"{self.test_dir.name}/{self.variant}"

    @property
    def relative_case_path(self) -> str:
        return str(self.case_path.relative_to(REPO_ROOT))

    @property
    def stats_path(self) -> Path:
        return self.case_path / "output" / "task_statistics.csv"

    @property
    def throughput_path(self) -> Path:
        return self.case_path / "output" / "throughput.csv"

    @property
    def traffic_path(self) -> Path:
        return self.case_path / "traffic.csv"

    @property
    def network_attribute_path(self) -> Path:
        return self.case_path / "network_attribute.txt"


def build_jobs() -> list[Job]:
    jobs: list[Job] = []
    for test_name in TEST_DIRS:
        test_dir = BASE_DIR / test_name
        if not test_dir.is_dir():
            raise FileNotFoundError(f"missing test directory: {test_dir}")
        for variant in VARIANTS:
            case_path = test_dir / variant
            if not case_path.is_dir():
                raise FileNotFoundError(f"missing case directory: {case_path}")
            jobs.append(Job(test_dir, variant))
    return jobs


def read_attribute(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if key in line:
            return line.rsplit(maxsplit=1)[-1].strip('"')
    return ""


def traffic_summary(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    src_nodes = [int(row["sourceNode"]) for row in rows]
    dst_nodes = [int(row["destNode"]) for row in rows]
    pods = {node // HOSTS_PER_POD for node in src_nodes + dst_nodes}
    cross_pod = sum(
        1
        for src, dst in zip(src_nodes, dst_nodes)
        if src // HOSTS_PER_POD != dst // HOSTS_PER_POD
    )
    return {
        "traffic_rows": str(len(rows)),
        "src_range": f"{min(src_nodes)}..{max(src_nodes)}" if src_nodes else "",
        "dst_range": f"{min(dst_nodes)}..{max(dst_nodes)}" if dst_nodes else "",
        "traffic_pods": " ".join(str(pod) for pod in sorted(pods)),
        "cross_pod_flows": str(cross_pod),
        "single_pod_traffic": str(cross_pod == 0),
    }


def percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * pct
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction


def stats_summary(path: Path) -> dict[str, str]:
    if not path.exists():
        return empty_stats_summary()
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    complete_times = sorted(float(row["taskCompletesTime(us)"]) for row in rows)
    throughputs = [float(row["taskThroughput(Gbps)"]) for row in rows]
    slow_rows = sorted(
        rows,
        key=lambda row: float(row["taskCompletesTime(us)"]),
        reverse=True,
    )[:3]
    slowest = " | ".join(
        f"{row['taskId']}:{row['sourceNode']}->{row['destNode']} {float(row['taskCompletesTime(us)']):.6f}us"
        for row in slow_rows
    )
    return {
        "tasks": str(len(rows)),
        "max_complete_us": f"{max(complete_times):.6f}" if complete_times else "",
        "avg_complete_us": f"{sum(complete_times) / len(complete_times):.6f}" if complete_times else "",
        "p95_complete_us": f"{percentile(complete_times, 0.95):.6f}" if complete_times else "",
        "min_throughput_Gbps": f"{min(throughputs):.4f}" if throughputs else "",
        "avg_throughput_Gbps": f"{sum(throughputs) / len(throughputs):.4f}" if throughputs else "",
        "max_throughput_Gbps": f"{max(throughputs):.4f}" if throughputs else "",
        "slowest": slowest,
    }


def empty_stats_summary() -> dict[str, str]:
    return {
        "tasks": "0",
        "max_complete_us": "",
        "avg_complete_us": "",
        "p95_complete_us": "",
        "min_throughput_Gbps": "",
        "avg_throughput_Gbps": "",
        "max_throughput_Gbps": "",
        "slowest": "",
    }


def launch(job: Job, log_dir: Path) -> tuple[subprocess.Popen[str], float, float, Path]:
    log_path = log_dir / f"{job.test_dir.name}__{job.variant}.log"
    old_mtime = job.stats_path.stat().st_mtime if job.stats_path.exists() else 0.0
    log_file = log_path.open("w", encoding="utf-8")
    cmd = [
        "python3.12",
        "./ns3",
        "run",
        "--no-build",
        f"scratch/ub-quick-example --case-path={job.relative_case_path}",
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    proc._codex_log_file = log_file  # type: ignore[attr-defined]
    return proc, time.monotonic(), old_mtime, log_path


def collect_result(
    job: Job,
    rc: int,
    elapsed: float,
    old_mtime: float,
    log_path: Path,
) -> dict[str, str]:
    stats_mtime = job.stats_path.stat().st_mtime if job.stats_path.exists() else 0.0
    stats_fresh = stats_mtime > old_mtime
    row = {
        "test": job.test_dir.name,
        "variant": job.variant,
        "bw_weighted_packet_spray": read_attribute(
            job.network_attribute_path,
            "ns3::UbRoutingProcess::BwWeightedPacketSpray",
        ),
        "use_packet_spray": read_attribute(
            job.network_attribute_path,
            "ns3::UbTransportChannel::UsePacketSpray",
        ),
        "traffic_rows": "",
        "src_range": "",
        "dst_range": "",
        "traffic_pods": "",
        "cross_pod_flows": "",
        "single_pod_traffic": "",
        "rc": str(rc),
        "elapsed_s": f"{elapsed:.1f}",
        "stats_fresh": str(stats_fresh),
        "throughput_exists": str(job.throughput_path.exists()),
        "log": str(log_path.relative_to(REPO_ROOT)),
        "stats": str(job.stats_path.relative_to(REPO_ROOT)),
    }
    row.update(traffic_summary(job.traffic_path))
    row.update(stats_summary(job.stats_path) if stats_fresh else empty_stats_summary())
    return row


def write_summaries(results: list[dict[str, str]], log_dir: Path) -> None:
    fieldnames = (
        "test",
        "variant",
        "bw_weighted_packet_spray",
        "use_packet_spray",
        "traffic_rows",
        "src_range",
        "dst_range",
        "traffic_pods",
        "cross_pod_flows",
        "single_pod_traffic",
        "rc",
        "elapsed_s",
        "stats_fresh",
        "throughput_exists",
        "tasks",
        "max_complete_us",
        "avg_complete_us",
        "p95_complete_us",
        "min_throughput_Gbps",
        "avg_throughput_Gbps",
        "max_throughput_Gbps",
        "slowest",
        "log",
        "stats",
    )
    summary_csv = log_dir / "summary.csv"
    with summary_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    result_tsv = log_dir / "result_summary.tsv"
    tsv_fields = (
        "test",
        "variant",
        "tasks",
        "avg_complete_us",
        "max_complete_us",
        "p95_complete_us",
        "avg_throughput_Gbps",
        "min_throughput_Gbps",
        "max_throughput_Gbps",
        "slowest",
    )
    with result_tsv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=tsv_fields, delimiter="\t")
        writer.writeheader()
        for row in results:
            writer.writerow({field: row[field] for field in tsv_fields})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parallel", type=int, default=5)
    parser.add_argument("--label", default=f"test01_test10_parallel5_{datetime.now():%Y%m%d_%H%M%S}")
    args = parser.parse_args()

    if args.parallel < 1:
        raise ValueError("--parallel must be >= 1")

    jobs = build_jobs()
    log_dir = BASE_DIR / "batch_run_logs" / args.label
    log_dir.mkdir(parents=True, exist_ok=True)
    print(f"log_dir={log_dir}", flush=True)
    print(f"total_jobs={len(jobs)} parallel={args.parallel}", flush=True)

    pending = jobs[:]
    active: list[tuple[Job, subprocess.Popen[str], float, float, Path]] = []
    results: list[dict[str, str]] = []

    while pending or active:
        while pending and len(active) < args.parallel:
            job = pending.pop(0)
            proc, start_time, old_mtime, log_path = launch(job, log_dir)
            active.append((job, proc, start_time, old_mtime, log_path))
            print(f"[{datetime.now():%H:%M:%S}] START {job.name}", flush=True)

        time.sleep(5)
        still_active: list[tuple[Job, subprocess.Popen[str], float, float, Path]] = []
        for job, proc, start_time, old_mtime, log_path in active:
            rc = proc.poll()
            if rc is None:
                still_active.append((job, proc, start_time, old_mtime, log_path))
                continue

            proc._codex_log_file.close()  # type: ignore[attr-defined]
            elapsed = time.monotonic() - start_time
            row = collect_result(job, rc, elapsed, old_mtime, log_path)
            results.append(row)
            status = "OK" if row["rc"] == "0" and row["stats_fresh"] == "True" else "FAIL"
            print(
                f"[{datetime.now():%H:%M:%S}] DONE {status} {job.name} "
                f"rc={rc} elapsed={elapsed:.1f}s stats_fresh={row['stats_fresh']}",
                flush=True,
            )
        active = still_active

    write_summaries(results, log_dir)
    failed = [row for row in results if row["rc"] != "0" or row["stats_fresh"] != "True"]
    print(f"summary={log_dir / 'summary.csv'}", flush=True)
    print(f"result_summary={log_dir / 'result_summary.tsv'}", flush=True)
    print(f"total={len(results)} failed={len(failed)}", flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
