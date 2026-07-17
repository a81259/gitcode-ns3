#!/usr/bin/env python3
"""Run scaled test08/test09 case06/case07 with one queue per test."""

from __future__ import annotations

import argparse
import csv
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
DEFAULT_TESTS = ("test08_dp_reduce_scatter", "test09_dp_all_gather")
DEFAULT_CASES = (
    "case06_pod1_18_l1_first_l2_port_down",
    "case07_pod1_4l1_full_1l1_half_l2_port_down",
)
SIZE_COL = "dataSize(Byte)"
START_COL = "taskStartTime(us)"
COMPLETE_COL = "taskCompletesTime(us)"
THROUGHPUT_COL = "taskThroughput(Gbps)"


@dataclass(frozen=True)
class Job:
    scale: int
    test: str
    case: str

    @property
    def case_path(self) -> Path:
        return POD_ROOT / self.test / self.case

    @property
    def relative_case_path(self) -> str:
        return str(self.case_path.relative_to(REPO_ROOT))

    @property
    def traffic_original_path(self) -> Path:
        return self.case_path / "traffic.original.csv"

    @property
    def traffic_path(self) -> Path:
        return self.case_path / "traffic.csv"

    @property
    def output_path(self) -> Path:
        return self.case_path / "output"

    @property
    def runlog_path(self) -> Path:
        return self.case_path / "runlog"

    @property
    def stats_path(self) -> Path:
        return self.output_path / "task_statistics.csv"

    @property
    def queue_name(self) -> str:
        return self.test

    @property
    def name(self) -> str:
        return f"scale{self.scale}/{self.test}/{self.case}"


@dataclass(frozen=True)
class TrafficSummary:
    scale: int
    test: str
    case: str
    rows: int
    original_bytes: int
    scaled_bytes: int
    ratio: float
    traffic_path: Path


def mem_available_gib() -> float:
    try:
        with Path("/proc/meminfo").open("r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024 / 1024
    except FileNotFoundError:
        return 999.0
    return 0.0


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


def ensure_inputs(tests: tuple[str, ...], cases: tuple[str, ...]) -> None:
    for test in tests:
        for case in cases:
            case_path = POD_ROOT / test / case
            if not case_path.is_dir():
                raise FileNotFoundError(f"missing case directory: {case_path}")
            if not (case_path / "traffic.original.csv").exists():
                raise FileNotFoundError(f"missing traffic.original.csv: {case_path}")
            for name in ("network_attribute.txt", "node.csv", "topology.csv", "routing_table.csv"):
                if not (case_path / name).exists():
                    raise FileNotFoundError(f"missing {name}: {case_path}")


def scale_size(value: str, scale: int) -> int:
    original = int(float(value))
    if original <= 0:
        return original
    return max(1, original // scale)


def rewrite_traffic(job: Job) -> TrafficSummary:
    rows: list[dict[str, str]] = []
    original_total = 0
    scaled_total = 0
    with job.traffic_original_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        if SIZE_COL not in fieldnames:
            raise ValueError(f"{job.traffic_original_path} missing required column {SIZE_COL!r}")
        for row in reader:
            original = int(float(row[SIZE_COL]))
            scaled = scale_size(row[SIZE_COL], job.scale)
            row[SIZE_COL] = str(scaled)
            rows.append(row)
            original_total += original
            scaled_total += scaled

    with job.traffic_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    ratio = 0.0 if original_total == 0 else scaled_total / original_total
    return TrafficSummary(
        scale=job.scale,
        test=job.test,
        case=job.case,
        rows=len(rows),
        original_bytes=original_total,
        scaled_bytes=scaled_total,
        ratio=ratio,
        traffic_path=job.traffic_path.relative_to(REPO_ROOT),
    )


def clean_case(job: Job) -> None:
    shutil.rmtree(job.output_path, ignore_errors=True)
    shutil.rmtree(job.runlog_path, ignore_errors=True)


def launch(job: Job, log_dir: Path) -> tuple[subprocess.Popen[str], float, Path, object]:
    scale_dir = log_dir / f"scale{job.scale}"
    scale_dir.mkdir(parents=True, exist_ok=True)
    log_path = scale_dir / f"{job.test}__{job.case}.log"
    log_file = log_path.open("w", encoding="utf-8")
    cmd = [
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
    return proc, time.monotonic(), log_path, log_file


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


def summarize_stats(stats_path: Path) -> dict[str, str]:
    if not stats_path.exists():
        return {
            "status": "MISSING_STATS",
            "tasks": "",
            "total_bytes": "",
            "max_complete_us": "",
            "avg_complete_us": "",
            "p95_complete_us": "",
            "avg_fct_us": "",
            "avg_throughput_gbps": "",
            "min_throughput_gbps": "",
            "max_throughput_gbps": "",
            "slowest": "",
        }

    rows: list[dict[str, str]] = []
    with stats_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {SIZE_COL, START_COL, COMPLETE_COL, THROUGHPUT_COL}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{stats_path} missing required columns: {sorted(missing)}")
        rows = list(reader)

    if not rows:
        return {
            "status": "EMPTY_STATS",
            "tasks": "0",
            "total_bytes": "0",
            "max_complete_us": "",
            "avg_complete_us": "",
            "p95_complete_us": "",
            "avg_fct_us": "",
            "avg_throughput_gbps": "",
            "min_throughput_gbps": "",
            "max_throughput_gbps": "",
            "slowest": "",
        }

    completes = sorted(float(row[COMPLETE_COL]) for row in rows)
    fcts = [float(row[COMPLETE_COL]) - float(row.get(START_COL) or 0.0) for row in rows]
    throughputs = [float(row[THROUGHPUT_COL]) for row in rows]
    total_bytes = sum(int(float(row[SIZE_COL])) for row in rows)
    slow_rows = sorted(rows, key=lambda row: float(row[COMPLETE_COL]), reverse=True)[:3]
    slowest = " | ".join(
        f"{row['taskId']}:{row['sourceNode']}->{row['destNode']} {float(row[COMPLETE_COL]):.6f}us"
        for row in slow_rows
    )
    return {
        "status": "OK",
        "tasks": str(len(rows)),
        "total_bytes": str(total_bytes),
        "max_complete_us": f"{max(completes):.6f}",
        "avg_complete_us": f"{mean(completes):.6f}",
        "p95_complete_us": f"{percentile(completes, 0.95):.6f}",
        "avg_fct_us": f"{mean(fcts):.6f}",
        "avg_throughput_gbps": f"{mean(throughputs):.6f}",
        "min_throughput_gbps": f"{min(throughputs):.6f}",
        "max_throughput_gbps": f"{max(throughputs):.6f}",
        "slowest": slowest,
    }


def archive_job(job: Job, log_dir: Path, log_path: Path) -> tuple[Path, Path]:
    archive = log_dir / f"scale{job.scale}" / job.test / job.case
    archive.mkdir(parents=True, exist_ok=True)
    traffic_archive = archive / "traffic.csv"
    shutil.copy2(job.traffic_path, traffic_archive)
    if job.output_path.exists():
        output_archive = archive / "output"
        shutil.rmtree(output_archive, ignore_errors=True)
        shutil.copytree(job.output_path, output_archive)
    return archive, log_path


def write_traffic_summary(rows: list[TrafficSummary], log_dir: Path) -> None:
    path = log_dir / "traffic_scale_summary.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=(
                "scale",
                "test",
                "case",
                "rows",
                "original_bytes",
                "scaled_bytes",
                "ratio",
                "traffic_path",
            ),
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "scale": row.scale,
                    "test": row.test,
                    "case": row.case,
                    "rows": row.rows,
                    "original_bytes": row.original_bytes,
                    "scaled_bytes": row.scaled_bytes,
                    "ratio": f"{row.ratio:.12f}",
                    "traffic_path": row.traffic_path.as_posix(),
                }
            )


def write_run_summaries(rows: list[dict[str, str]], log_dir: Path) -> None:
    run_fields = (
        "finish_order",
        "scale",
        "test",
        "case",
        "returncode",
        "elapsed_s",
        "archive",
        "task_statistics",
        "log",
    )
    stats_fields = run_fields + (
        "status",
        "tasks",
        "total_bytes",
        "max_complete_us",
        "avg_complete_us",
        "p95_complete_us",
        "avg_fct_us",
        "avg_throughput_gbps",
        "min_throughput_gbps",
        "max_throughput_gbps",
        "slowest",
    )
    with (log_dir / "run_summary.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=run_fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in run_fields} for row in rows)

    with (log_dir / "case_stats_summary.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=stats_fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in stats_fields} for row in rows)

    tsv_fields = (
        "scale",
        "test",
        "case",
        "tasks",
        "avg_complete_us",
        "max_complete_us",
        "p95_complete_us",
        "avg_fct_us",
        "avg_throughput_gbps",
        "min_throughput_gbps",
        "max_throughput_gbps",
        "slowest",
    )
    with (log_dir / "result_summary.tsv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=tsv_fields, delimiter="\t")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in tsv_fields} for row in rows)


def write_planned_queue(scales: tuple[int, ...], tests: tuple[str, ...], cases: tuple[str, ...], log_dir: Path) -> None:
    path = log_dir / "planned_queue.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=("scale", "queue", "order_in_queue", "test", "case"))
        writer.writeheader()
        for scale in scales:
            for test in tests:
                for order, case in enumerate(cases, start=1):
                    writer.writerow(
                        {
                            "scale": scale,
                            "queue": test,
                            "order_in_queue": order,
                            "test": test,
                            "case": case,
                        }
                    )


def select_launchable_tests(
    tests: tuple[str, ...],
    queues: dict[str, list[Job]],
    active: dict[str, object],
    parallel: int,
) -> list[str]:
    available_slots = max(0, parallel - len(active))
    return [
        test
        for test in tests
        if test not in active and queues[test]
    ][:available_slots]


def run_scale(
    scale: int,
    tests: tuple[str, ...],
    cases: tuple[str, ...],
    parallel: int,
    log_dir: Path,
    poll_seconds: float,
    min_mem_gib: float,
    results: list[dict[str, str]],
    traffic_rows: list[TrafficSummary],
) -> None:
    queues = {
        test: [Job(scale=scale, test=test, case=case) for case in cases]
        for test in tests
    }
    active: dict[str, tuple[Job, subprocess.Popen[str], float, Path, object]] = {}

    print(f"[{datetime.now():%H:%M:%S}] SCALE_START scale={scale}", flush=True)
    while any(queues.values()) or active:
        for test in select_launchable_tests(tests, queues, active, parallel):
            if mem_available_gib() < min_mem_gib:
                print(
                    f"[{datetime.now():%H:%M:%S}] WAIT mem_avail={mem_available_gib():.1f}GiB "
                    f"below {min_mem_gib:.1f}GiB",
                    flush=True,
                )
                break
            job = queues[test].pop(0)
            traffic_summary = rewrite_traffic(job)
            traffic_rows.append(traffic_summary)
            write_traffic_summary(traffic_rows, log_dir)
            clean_case(job)
            proc, start_time, log_path, log_file = launch(job, log_dir)
            active[test] = (job, proc, start_time, log_path, log_file)
            print(
                f"[{datetime.now():%H:%M:%S}] START {job.name} "
                f"rows={traffic_summary.rows} scaled_bytes={traffic_summary.scaled_bytes} "
                f"mem_avail={mem_available_gib():.1f}GiB",
                flush=True,
            )

        if not active:
            time.sleep(poll_seconds)
            continue

        time.sleep(poll_seconds)
        for test in list(active):
            job, proc, start_time, log_path, log_file = active[test]
            rc = proc.poll()
            if rc is None:
                continue
            log_file.close()
            elapsed = time.monotonic() - start_time
            archive, archived_log = archive_job(job, log_dir, log_path)
            stats = summarize_stats(archive / "output" / "task_statistics.csv")
            row = {
                "finish_order": str(len(results) + 1),
                "scale": str(job.scale),
                "test": job.test,
                "case": job.case,
                "returncode": str(rc),
                "elapsed_s": f"{elapsed:.3f}",
                "archive": str(archive.relative_to(REPO_ROOT)),
                "task_statistics": str((archive / "output" / "task_statistics.csv").relative_to(REPO_ROOT)),
                "log": str(archived_log.relative_to(REPO_ROOT)),
            }
            row.update(stats)
            results.append(row)
            write_run_summaries(results, log_dir)
            status = "OK" if rc == 0 and stats["status"] == "OK" else "FAIL"
            print(
                f"[{datetime.now():%H:%M:%S}] DONE {status} {job.name} "
                f"rc={rc} elapsed={elapsed:.1f}s status={stats['status']} "
                f"max_complete_us={stats.get('max_complete_us', '')}",
                flush=True,
            )
            del active[test]

    print(f"[{datetime.now():%H:%M:%S}] SCALE_DONE scale={scale}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scales", type=int, nargs="+", required=True)
    parser.add_argument("--tests", nargs="+", default=list(DEFAULT_TESTS))
    parser.add_argument("--cases", nargs="+", default=list(DEFAULT_CASES))
    parser.add_argument("--parallel", type=int)
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    parser.add_argument("--min-mem-gib", type=float, default=8.0)
    parser.add_argument(
        "--label",
        default=f"test08_09_case06_07_scaled_{datetime.now():%Y%m%d_%H%M%S}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scales = tuple(args.scales)
    tests = tuple(args.tests)
    cases = tuple(args.cases)
    if any(scale <= 0 for scale in scales):
        raise ValueError("--scales must contain positive integers")
    if args.poll_seconds <= 0:
        raise ValueError("--poll-seconds must be positive")
    if args.min_mem_gib < 0:
        raise ValueError("--min-mem-gib must be non-negative")
    if args.parallel is not None and args.parallel <= 0:
        raise ValueError("--parallel must be positive")

    ensure_inputs(tests, cases)
    parallel = args.parallel or len(tests)
    log_dir = SCRIPT_DIR / "batch_run_logs" / args.label
    log_dir.mkdir(parents=True, exist_ok=False)
    write_planned_queue(scales, tests, cases, log_dir)

    print(f"log_dir={log_dir}", flush=True)
    print(f"repo_root={REPO_ROOT}", flush=True)
    print(f"scales={','.join(map(str, scales))}", flush=True)
    print(f"queues={','.join(tests)} cases={','.join(cases)} parallel={parallel}", flush=True)

    results: list[dict[str, str]] = []
    traffic_rows: list[TrafficSummary] = []
    active_processes: list[subprocess.Popen[str]] = []
    try:
        for scale in scales:
            run_scale(
                scale=scale,
                tests=tests,
                cases=cases,
                parallel=parallel,
                log_dir=log_dir,
                poll_seconds=args.poll_seconds,
                min_mem_gib=args.min_mem_gib,
                results=results,
                traffic_rows=traffic_rows,
            )
    except KeyboardInterrupt:
        for proc in active_processes:
            terminate_process_group(proc)
        raise

    failed = [row for row in results if row["returncode"] != "0" or row["status"] != "OK"]
    print(f"traffic_summary={log_dir / 'traffic_scale_summary.csv'}", flush=True)
    print(f"run_summary={log_dir / 'run_summary.csv'}", flush=True)
    print(f"case_stats_summary={log_dir / 'case_stats_summary.csv'}", flush=True)
    print(f"result_summary={log_dir / 'result_summary.tsv'}", flush=True)
    print(f"total={len(results)} failed={len(failed)}", flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
