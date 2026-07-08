#!/usr/bin/env python3
"""Run test01..test06 variants in groups of five and summarize outputs."""

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
    def traffic_path(self) -> Path:
        return self.case_path / "traffic.csv"

    @property
    def network_attribute_path(self) -> Path:
        return self.case_path / "network_attribute.txt"


def selected_tests() -> list[Path]:
    return sorted(path for path in BASE_DIR.glob("test0[1-6]_*") if path.is_dir())


def read_bw_weighted_packet_spray(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if "ns3::UbRoutingProcess::BwWeightedPacketSpray" in line:
            return line.rsplit(maxsplit=1)[-1].strip('"')
    return ""


def read_use_packet_spray(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if "ns3::UbTransportChannel::UsePacketSpray" in line:
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


def stats_summary(path: Path) -> dict[str, str]:
    if not path.exists():
        return {
            "tasks": "0",
            "max_complete_us": "",
            "avg_complete_us": "",
            "min_throughput_Gbps": "",
            "avg_throughput_Gbps": "",
        }
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    complete_times = [float(row["taskCompletesTime(us)"]) for row in rows]
    throughputs = [float(row["taskThroughput(Gbps)"]) for row in rows]
    return {
        "tasks": str(len(rows)),
        "max_complete_us": f"{max(complete_times):.6f}" if complete_times else "",
        "avg_complete_us": f"{sum(complete_times) / len(complete_times):.6f}" if complete_times else "",
        "min_throughput_Gbps": f"{min(throughputs):.4f}" if throughputs else "",
        "avg_throughput_Gbps": f"{sum(throughputs) / len(throughputs):.4f}" if throughputs else "",
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


def run_group(test_dir: Path, log_dir: Path) -> list[dict[str, str]]:
    jobs = [Job(test_dir, variant) for variant in VARIANTS]
    active: list[tuple[Job, subprocess.Popen[str], float, float, Path]] = []
    for job in jobs:
        proc, start_time, old_mtime, log_path = launch(job, log_dir)
        active.append((job, proc, start_time, old_mtime, log_path))
        print(f"[{datetime.now():%H:%M:%S}] START {job.name}", flush=True)

    results: list[dict[str, str]] = []
    while active:
        time.sleep(5)
        still_active: list[tuple[Job, subprocess.Popen[str], float, float, Path]] = []
        for job, proc, start_time, old_mtime, log_path in active:
            rc = proc.poll()
            if rc is None:
                still_active.append((job, proc, start_time, old_mtime, log_path))
                continue

            proc._codex_log_file.close()  # type: ignore[attr-defined]
            elapsed = time.monotonic() - start_time
            stats_mtime = job.stats_path.stat().st_mtime if job.stats_path.exists() else 0.0
            stats_fresh = stats_mtime > old_mtime
            status = "OK" if rc == 0 and stats_fresh else "FAIL"
            print(
                f"[{datetime.now():%H:%M:%S}] DONE {status} {job.name} "
                f"rc={rc} elapsed={elapsed:.1f}s stats_fresh={stats_fresh}",
                flush=True,
            )
            row = {
                "test": job.test_dir.name,
                "variant": job.variant,
                "bw_weighted_packet_spray": read_bw_weighted_packet_spray(job.network_attribute_path),
                "use_packet_spray": read_use_packet_spray(job.network_attribute_path),
                "rc": str(rc),
                "elapsed_s": f"{elapsed:.1f}",
                "stats_fresh": str(stats_fresh),
                "log": str(log_path.relative_to(REPO_ROOT)),
                "stats": str(job.stats_path.relative_to(REPO_ROOT)),
            }
            row.update(traffic_summary(job.traffic_path))
            if stats_fresh:
                row.update(stats_summary(job.stats_path))
            else:
                row.update(
                    {
                        "tasks": "0",
                        "max_complete_us": "",
                        "avg_complete_us": "",
                        "min_throughput_Gbps": "",
                        "avg_throughput_Gbps": "",
                    }
                )
            results.append(row)
        active = still_active
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default=f"test01_06_parallel5_{datetime.now():%Y%m%d_%H%M%S}")
    args = parser.parse_args()

    tests = selected_tests()
    if len(tests) != 6:
        print(f"expected 6 tests, found {len(tests)}", flush=True)
        return 1

    log_dir = BASE_DIR / "batch_run_logs" / args.label
    log_dir.mkdir(parents=True, exist_ok=True)
    print(f"log_dir={log_dir}", flush=True)
    print(f"tests={len(tests)} variants_per_test={len(VARIANTS)}", flush=True)

    results: list[dict[str, str]] = []
    for test_dir in tests:
        print(f"[{datetime.now():%H:%M:%S}] GROUP {test_dir.name}", flush=True)
        results.extend(run_group(test_dir, log_dir))

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
        "tasks",
        "max_complete_us",
        "avg_complete_us",
        "min_throughput_Gbps",
        "avg_throughput_Gbps",
        "log",
        "stats",
    )
    summary_csv = log_dir / "summary.csv"
    with summary_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    failed = [row for row in results if row["rc"] != "0" or row["stats_fresh"] != "True"]
    print(f"summary={summary_csv}", flush=True)
    print(f"total={len(results)} failed={len(failed)}", flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
