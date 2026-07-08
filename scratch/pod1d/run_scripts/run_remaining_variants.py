#!/usr/bin/env python3
"""Run test02..test09 for standard/fault variants and collect logs."""

from __future__ import annotations

import argparse
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parents[1]
VARIANTS = (
    "case01_standard",
    "case02_host_l1_lane_down",
    "case03_host_l1_port_down",
    "case04_l1_l2_lane_down",
    "case05_l1_l2_port_down",
)


@dataclass
class Job:
    case_dir: Path
    variant: str

    @property
    def case_path(self) -> Path:
        return self.case_dir / self.variant

    @property
    def name(self) -> str:
        return f"{self.case_dir.name}/{self.variant}"

    @property
    def relative_case_path(self) -> str:
        return str(self.case_path.relative_to(REPO_ROOT))

    @property
    def stats_path(self) -> Path:
        return self.case_path / "output" / "task_statistics.csv"


def list_jobs() -> list[Job]:
    jobs: list[Job] = []
    for case_dir in sorted(BASE_DIR.glob("test[0-9][0-9]_*")):
        if case_dir.name.startswith("test01_"):
            continue
        for variant in VARIANTS:
            jobs.append(Job(case_dir, variant))
    return jobs


def launch(job: Job, log_dir: Path) -> tuple[subprocess.Popen, float, Path]:
    log_path = log_dir / f"{job.case_dir.name}__{job.variant}.log"
    log_file = log_path.open("w", encoding="utf-8")
    cmd = [
        "./ns3",
        "run",
        "--no-build",
        f"scratch/ub-quick-example --case-path={job.relative_case_path} --stop-ms=50 --mtp-threads=1",
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    proc._codex_log_file = log_file  # type: ignore[attr-defined]
    return proc, time.monotonic(), log_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parallel", type=int, default=4)
    args = parser.parse_args()

    jobs = list_jobs()
    if not jobs:
        print("no jobs found", flush=True)
        return 1

    log_dir = BASE_DIR / "batch_run_logs" / datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir.mkdir(parents=True, exist_ok=True)
    print(f"log_dir={log_dir}", flush=True)
    print(f"total_jobs={len(jobs)} parallel={args.parallel}", flush=True)

    pending = jobs[:]
    active: list[tuple[Job, subprocess.Popen, float, Path]] = []
    results: list[tuple[Job, int, float, Path]] = []

    while pending or active:
        while pending and len(active) < args.parallel:
            job = pending.pop(0)
            proc, start_time, log_path = launch(job, log_dir)
            active.append((job, proc, start_time, log_path))
            print(f"[{datetime.now():%H:%M:%S}] START {job.name}", flush=True)

        time.sleep(5)
        still_active: list[tuple[Job, subprocess.Popen, float, Path]] = []
        for job, proc, start_time, log_path in active:
            rc = proc.poll()
            if rc is None:
                still_active.append((job, proc, start_time, log_path))
                continue

            proc._codex_log_file.close()  # type: ignore[attr-defined]
            elapsed = time.monotonic() - start_time
            results.append((job, rc, elapsed, log_path))
            status = "OK" if rc == 0 and job.stats_path.exists() else "FAIL"
            print(
                f"[{datetime.now():%H:%M:%S}] DONE {status} {job.name} "
                f"rc={rc} elapsed={elapsed:.1f}s stats={job.stats_path.exists()}",
                flush=True,
            )
        active = still_active

    missing = [job for job in jobs if not job.stats_path.exists()]
    failed = [item for item in results if item[1] != 0]

    summary_path = log_dir / "summary.txt"
    with summary_path.open("w", encoding="utf-8") as f:
        for job, rc, elapsed, log_path in results:
            f.write(
                f"{job.name}\trc={rc}\telapsed={elapsed:.1f}s\t"
                f"stats={job.stats_path.exists()}\tlog={log_path}\n"
            )
        if missing:
            f.write("\nmissing stats:\n")
            for job in missing:
                f.write(f"{job.name}\n")
        if failed:
            f.write("\nfailed jobs:\n")
            for job, rc, _, log_path in failed:
                f.write(f"{job.name}\trc={rc}\tlog={log_path}\n")

    print(f"summary={summary_path}", flush=True)
    print(f"missing_stats={len(missing)} failed_jobs={len(failed)}", flush=True)
    return 0 if not missing and not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
