#!/usr/bin/env python3
"""Run pod1d variants in the requested order with conservative concurrency."""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parents[1]
TEST_GLOB = "test[0-9][0-9]_*"
PHASE1_VARIANTS = (
    "case01_standard",
    "case04_l1_l2_lane_down",
    "case05_l1_l2_port_down",
)
PHASE2_VARIANTS = (
    "case02_host_l1_lane_down",
    "case03_host_l1_port_down",
)
NO_TASK_PATTERN = re.compile(r"No task completed for ([0-9.]+)\s*(us|ms|s)")


@dataclass(frozen=True)
class Job:
    test_dir: Path
    variant: str
    phase: int

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


def mem_available_gib() -> float:
    with Path("/proc/meminfo").open("r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024 / 1024
    return 0.0


def build_jobs() -> tuple[list[Job], list[Job]]:
    tests = sorted(p for p in BASE_DIR.glob(TEST_GLOB) if p.is_dir())
    phase1 = [Job(test, variant, 1) for variant in PHASE1_VARIANTS for test in tests]
    phase2 = [Job(test, variant, 2) for variant in PHASE2_VARIANTS for test in tests]
    return phase1, phase2


def clean_case(job: Job) -> None:
    shutil.rmtree(job.case_path / "runlog", ignore_errors=True)
    shutil.rmtree(job.case_path / "output", ignore_errors=True)


def launch(job: Job, log_dir: Path) -> tuple[subprocess.Popen[str], float, Path]:
    clean_case(job)
    log_path = log_dir / f"{job.test_dir.name}__{job.variant}.log"
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
        start_new_session=True,
    )
    proc._codex_log_file = log_file  # type: ignore[attr-defined]
    return proc, time.monotonic(), log_path


def duration_to_ms(value: str, unit: str) -> float:
    duration = float(value)
    if unit == "us":
        return duration / 1000.0
    if unit == "s":
        return duration * 1000.0
    return duration


def max_no_task_ms(log_path: Path) -> float:
    if not log_path.exists():
        return 0.0
    text = log_path.read_text(errors="ignore")
    max_duration = 0.0
    for match in NO_TASK_PATTERN.finditer(text):
        max_duration = max(max_duration, duration_to_ms(match.group(1), match.group(2)))
    return max_duration


def terminate_process_group(proc: subprocess.Popen[str]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=10)


def run_phase(
    jobs: list[Job],
    parallel: int,
    min_mem_gib: float,
    log_dir: Path,
    max_no_task_ms_limit: float,
) -> list[dict[str, str]]:
    pending = jobs[:]
    active: list[tuple[Job, subprocess.Popen[str], float, Path]] = []
    results: list[dict[str, str]] = []

    while pending or active:
        while pending and len(active) < parallel and mem_available_gib() >= min_mem_gib:
            job = pending.pop(0)
            proc, start_time, log_path = launch(job, log_dir)
            active.append((job, proc, start_time, log_path))
            print(f"[{datetime.now():%H:%M:%S}] START p{job.phase} {job.name} mem_avail={mem_available_gib():.1f}GiB", flush=True)

        if pending and len(active) < parallel and mem_available_gib() < min_mem_gib:
            print(f"[{datetime.now():%H:%M:%S}] WAIT mem_avail={mem_available_gib():.1f}GiB below {min_mem_gib:.1f}GiB", flush=True)

        time.sleep(5)
        still_active: list[tuple[Job, subprocess.Popen[str], float, Path]] = []
        for job, proc, start_time, log_path in active:
            no_task_ms = max_no_task_ms(log_path)
            if no_task_ms > max_no_task_ms_limit:
                terminate_process_group(proc)
                proc._codex_log_file.close()  # type: ignore[attr-defined]
                elapsed = time.monotonic() - start_time
                print(
                    f"[{datetime.now():%H:%M:%S}] STOP TIMEOUT_NO_TASK p{job.phase} {job.name} "
                    f"no_task_ms={no_task_ms:.3f} elapsed={elapsed:.1f}s "
                    f"mem_avail={mem_available_gib():.1f}GiB",
                    flush=True,
                )
                results.append(
                    {
                        "phase": str(job.phase),
                        "test": job.test_dir.name,
                        "variant": job.variant,
                        "rc": "TIMEOUT_NO_TASK",
                        "elapsed_s": f"{elapsed:.1f}",
                        "stats_exists": str(job.stats_path.exists()),
                        "log": str(log_path),
                        "stats": str(job.stats_path),
                    }
                )
                continue

            rc = proc.poll()
            if rc is None:
                still_active.append((job, proc, start_time, log_path))
                continue

            proc._codex_log_file.close()  # type: ignore[attr-defined]
            elapsed = time.monotonic() - start_time
            stats_exists = job.stats_path.exists()
            status = "OK" if rc == 0 and stats_exists else "FAIL"
            print(
                f"[{datetime.now():%H:%M:%S}] DONE {status} p{job.phase} {job.name} "
                f"rc={rc} elapsed={elapsed:.1f}s stats={stats_exists} mem_avail={mem_available_gib():.1f}GiB",
                flush=True,
            )
            results.append(
                {
                    "phase": str(job.phase),
                    "test": job.test_dir.name,
                    "variant": job.variant,
                    "rc": str(rc),
                    "elapsed_s": f"{elapsed:.1f}",
                    "stats_exists": str(stats_exists),
                    "log": str(log_path),
                    "stats": str(job.stats_path),
                }
            )
        active = still_active

    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parallel", type=int, default=2)
    parser.add_argument("--min-mem-gib", type=float, default=16.0)
    parser.add_argument("--max-no-task-ms", type=float, default=50.0)
    args = parser.parse_args()

    phase1, phase2 = build_jobs()
    log_dir = BASE_DIR / "batch_run_logs" / f"ordered_{datetime.now():%Y%m%d_%H%M%S}"
    log_dir.mkdir(parents=True, exist_ok=True)

    print(f"log_dir={log_dir}", flush=True)
    print(f"phase1_jobs={len(phase1)} phase2_jobs={len(phase2)} parallel={args.parallel}", flush=True)
    results = run_phase(phase1, args.parallel, args.min_mem_gib, log_dir, args.max_no_task_ms)
    results.extend(run_phase(phase2, args.parallel, args.min_mem_gib, log_dir, args.max_no_task_ms))

    summary_csv = log_dir / "summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=("phase", "test", "variant", "rc", "elapsed_s", "stats_exists", "log", "stats"),
        )
        writer.writeheader()
        writer.writerows(results)

    failed = [r for r in results if r["rc"] != "0" or r["stats_exists"] != "True"]
    print(f"summary={summary_csv}", flush=True)
    print(f"total={len(results)} failed={len(failed)}", flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
