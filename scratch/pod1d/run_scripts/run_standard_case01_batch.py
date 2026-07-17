#!/usr/bin/env python3
"""Run selected standard case01 workloads without changing traffic.csv."""

from __future__ import annotations

import argparse
import csv
import math
import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import run_test09_10_scale80_all_cases as common


SCRIPT_DIR = Path(__file__).resolve().parent
POD_ROOT = SCRIPT_DIR.parent
REPO_ROOT = POD_ROOT.parents[1]
DEFAULT_PACKAGE_ROOT = (
    REPO_ROOT / "scratch/20260716-scale40-test09-10-then-standard-case01"
)
TESTS = (
    "test01_tp_all_gather",
    "test02_cp_all_to_all",
    "test03_tp_reduce_scatter",
    "test04_tp_reduce_scatter",
    "test05_pp_send_recv",
    "test06_epxetp_all_to_all",
    "test07_etp_all_reduce",
)
CASE = "case01_标准topo"
REQUIRED_INPUTS = (
    "network_attribute.txt",
    "node.csv",
    "topology.csv",
    "routing_table.csv",
    "traffic.csv",
)


@dataclass(frozen=True)
class Job:
    test: str
    case: str = CASE

    @property
    def case_dir(self) -> Path:
        return POD_ROOT / self.test / self.case

    @property
    def relative_case_dir(self) -> str:
        return self.case_dir.relative_to(REPO_ROOT).as_posix()

    @property
    def name(self) -> str:
        return f"{self.test}/{self.case}"


@dataclass
class ActiveRun:
    job: Job
    process: subprocess.Popen[str]
    start_time: float
    log_path: Path
    log_stream: object


def build_jobs() -> list[Job]:
    return [Job(test) for test in TESTS]


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


def ensure_inputs(jobs: list[Job]) -> None:
    for job in jobs:
        if not job.case_dir.is_dir():
            raise FileNotFoundError(f"missing case directory: {job.case_dir}")
        for name in REQUIRED_INPUTS:
            if not (job.case_dir / name).is_file():
                raise FileNotFoundError(f"missing {name}: {job.case_dir}")


def prepare_case(case_dir: Path) -> dict[str, str]:
    traffic = case_dir / "traffic.csv"
    before = common.sha256_file(traffic)
    common.rewrite_routing_attributes(case_dir / "network_attribute.txt")
    after = common.sha256_file(traffic)
    if before != after:
        raise RuntimeError(f"traffic.csv changed during preparation: {case_dir}")
    return {
        "traffic_sha256_before": before,
        "traffic_sha256_after": after,
        "network_attribute_sha256": common.sha256_file(
            case_dir / "network_attribute.txt"
        ),
    }


def prepare_jobs(jobs: list[Job], artifact_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for job in jobs:
        summary = prepare_case(job.case_dir)
        task_count = len(common.read_csv_rows(job.case_dir / "traffic.csv"))
        rows.append(
            {
                "test": job.test,
                "case": job.case,
                "tasks": str(task_count),
                **summary,
                "traffic_preserved": str(
                    summary["traffic_sha256_before"]
                    == summary["traffic_sha256_after"]
                ),
            }
        )
        destination = artifact_dir / "input_snapshots" / job.test / job.case
        destination.mkdir(parents=True, exist_ok=True)
        for name in REQUIRED_INPUTS:
            shutil.copy2(job.case_dir / name, destination / name)
    common.write_csv(artifact_dir / "traffic_preservation_summary.csv", rows)
    return rows


def clean_outputs(job: Job) -> None:
    shutil.rmtree(job.case_dir / "runlog", ignore_errors=True)
    shutil.rmtree(job.case_dir / "output", ignore_errors=True)


def launch(job: Job, artifact_dir: Path) -> ActiveRun:
    clean_outputs(job)
    log_path = artifact_dir / "console_logs" / f"{job.test}__{job.case}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_stream = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        build_command(job),
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


def archive_statistics(job: Job, artifact_dir: Path) -> Path:
    source = job.case_dir / "output/task_statistics.csv"
    destination = artifact_dir / "task_statistics" / job.test / job.case
    destination.mkdir(parents=True, exist_ok=True)
    archived = destination / "task_statistics.csv"
    if source.is_file():
        shutil.copy2(source, archived)
    return archived


def result_row(
    run: ActiveRun,
    returncode: int,
    elapsed_s: float,
    artifact_dir: Path,
) -> dict[str, str]:
    archived = archive_statistics(run.job, artifact_dir)
    summary, _ = common.summarize_fct(archived)
    expected = len(common.read_csv_rows(run.job.case_dir / "traffic.csv"))
    return {
        "test": run.job.test,
        "case": run.job.case,
        "returncode": str(returncode),
        "elapsed_s": f"{elapsed_s:.3f}",
        "expected_tasks": str(expected),
        "completed_tasks": str(summary.completed_tasks),
        "completion_ratio": (
            f"{summary.completed_tasks / expected:.12f}" if expected else ""
        ),
        "fct_mean_us": common.format_float(summary.mean_us),
        "fct_p95_us": common.format_float(summary.p95_us),
        "fct_max_us": common.format_float(summary.max_us),
        "console_log": run.log_path.relative_to(REPO_ROOT).as_posix(),
        "task_statistics": (
            archived.relative_to(REPO_ROOT).as_posix() if archived.is_file() else ""
        ),
    }


def order_results(results: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(results, key=lambda row: TESTS.index(row["test"]))


def run_jobs(
    jobs: list[Job],
    parallel: int,
    artifact_dir: Path,
    poll_seconds: float,
    min_mem_gib: float,
) -> list[dict[str, str]]:
    pending = list(jobs)
    active: list[ActiveRun] = []
    results: list[dict[str, str]] = []
    try:
        while pending or active:
            while (
                pending
                and len(active) < parallel
                and common.mem_available_gib() >= min_mem_gib
            ):
                run = launch(pending.pop(0), artifact_dir)
                active.append(run)
                print(
                    f"[{datetime.now():%H:%M:%S}] START {run.job.name} "
                    f"parallel={len(active)}/{parallel} "
                    f"mem_available={common.mem_available_gib():.1f}GiB",
                    flush=True,
                )
            if not active:
                print(
                    f"[{datetime.now():%H:%M:%S}] WAIT "
                    f"mem_available={common.mem_available_gib():.1f}GiB "
                    f"below {min_mem_gib:.1f}GiB",
                    flush=True,
                )
                time.sleep(poll_seconds)
                continue
            time.sleep(poll_seconds)
            for run in list(active):
                returncode = run.process.poll()
                if returncode is None:
                    continue
                run.log_stream.close()
                elapsed = time.monotonic() - run.start_time
                row = result_row(run, returncode, elapsed, artifact_dir)
                results.append(row)
                common.write_csv(artifact_dir / "fct_summary.csv", results)
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
                active.remove(run)
    except BaseException:
        for run in active:
            terminate_process_group(run.process)
            run.log_stream.close()
        raise
    return results


def write_results(results: list[dict[str, str]], artifact_dir: Path) -> None:
    lines = [
        "# Standard case01 batch results",
        "",
        "- Traffic: existing `traffic.csv`, preserved byte-for-byte",
        "- Routing: `PER_PACKET_SHORTEST_PATHS + ROUND_ROBIN`",
        "- Dependency visibility delay: `10ns`",
        "- Runtime: single-thread simulation, two concurrent processes",
        "",
        "| Test | Completed | Mean (us) | P95 (us) | Max (us) | RC |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in order_results(results):
        lines.append(
            f"| {row['test']} | {row['completed_tasks']}/{row['expected_tasks']} | "
            f"{row['fct_mean_us']} | {row['fct_p95_us']} | "
            f"{row['fct_max_us']} | {row['returncode']} |"
        )
    (artifact_dir / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parallel", type=int, default=2)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--min-mem-gib", type=float, default=8.0)
    parser.add_argument("--package-root", type=Path, default=DEFAULT_PACKAGE_ROOT)
    parser.add_argument(
        "--label",
        default=f"standard_case01_{datetime.now():%Y%m%d_%H%M%S}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.parallel != 2:
        raise ValueError("--parallel must be exactly 2")
    if args.poll_seconds <= 0:
        raise ValueError("--poll-seconds must be positive")
    if args.min_mem_gib < 0:
        raise ValueError("--min-mem-gib must be non-negative")

    jobs = build_jobs()
    ensure_inputs(jobs)
    artifact_dir = args.package_root.resolve() / "artifacts" / args.label
    artifact_dir.mkdir(parents=True, exist_ok=False)
    print(f"repo_root={REPO_ROOT}", flush=True)
    print(f"artifact_dir={artifact_dir}", flush=True)
    print(f"tests={len(jobs)} case={CASE}", flush=True)
    print("traffic=existing-preserved parallel=2 mtp_threads=disabled", flush=True)

    preparation = prepare_jobs(jobs, artifact_dir)
    if not all(row["traffic_preserved"] == "True" for row in preparation):
        raise RuntimeError("one or more traffic.csv files changed during preparation")

    results = run_jobs(
        jobs,
        parallel=args.parallel,
        artifact_dir=artifact_dir,
        poll_seconds=args.poll_seconds,
        min_mem_gib=args.min_mem_gib,
    )
    ordered = order_results(results)
    common.write_csv(artifact_dir / "fct_summary.csv", ordered)
    write_results(results, artifact_dir)
    failed = [
        row
        for row in results
        if row["returncode"] != "0"
        or row["completed_tasks"] != row["expected_tasks"]
    ]
    print(f"summary={artifact_dir / 'fct_summary.csv'}", flush=True)
    print(f"results={artifact_dir / 'results.md'}", flush=True)
    print(f"total={len(results)} failed={len(failed)}", flush=True)
    return 0 if len(results) == len(jobs) and not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
