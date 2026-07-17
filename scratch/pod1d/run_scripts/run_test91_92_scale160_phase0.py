#!/usr/bin/env python3
"""Create test91/test92 from test08/test09 and run independent scale160 traffic."""

from __future__ import annotations

import argparse
import csv
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
SCALE = 160
SIZE_COL = "dataSize(Byte)"
PHASE_COL = "phaseId"
DEPENDENCY_COL = "dependOnPhases"
START_COL = "taskStartTime(us)"
COMPLETE_COL = "taskCompletesTime(us)"
THROUGHPUT_COL = "taskThroughput(Gbps)"
TESTS = (
    ("test08_dp_reduce_scatter", "test91_dp_reduce_scatter"),
    ("test09_dp_all_gather", "test92_dp_all_gather"),
)
CASES = (
    "case01_standard",
    "case04_l1_l2_lane_down",
    "case05_l1_l2_port_down",
    "case06_pod1_18_l1_first_l2_port_down",
    "case07_pod1_4l1_full_1l1_half_l2_port_down",
)
EXCLUDED_SOURCE_ENTRIES = {"output", "runlog"}


@dataclass(frozen=True)
class Job:
    source_test: str
    target_test: str
    case: str

    @property
    def source_dir(self) -> Path:
        return POD_ROOT / self.source_test / self.case

    @property
    def target_dir(self) -> Path:
        return POD_ROOT / self.target_test / self.case

    @property
    def relative_target_dir(self) -> str:
        return self.target_dir.relative_to(REPO_ROOT).as_posix()

    @property
    def original_traffic(self) -> Path:
        return self.target_dir / "traffic.original.csv"

    @property
    def traffic(self) -> Path:
        return self.target_dir / "traffic.csv"

    @property
    def stats(self) -> Path:
        return self.target_dir / "output" / "task_statistics.csv"

    @property
    def name(self) -> str:
        return f"{self.target_test}/{self.case}"


@dataclass(frozen=True)
class TrafficInfo:
    job: Job
    source_rows: int
    selected_rows: int
    source_bytes: int
    scaled_bytes: int
    phase_ids: str


def percentile(sorted_values: list[float], percentage: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * percentage
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] * (high - position) + sorted_values[high] * (position - low)


def build_jobs() -> list[Job]:
    return [Job(source, target, case) for source, target in TESTS for case in CASES]


def ensure_source_inputs(jobs: list[Job]) -> None:
    for job in jobs:
        if not job.source_dir.is_dir():
            raise FileNotFoundError(f"missing source case: {job.source_dir}")
        for name in (
            "traffic.original.csv",
            "network_attribute.txt",
            "node.csv",
            "topology.csv",
            "routing_table.csv",
        ):
            if not (job.source_dir / name).is_file():
                raise FileNotFoundError(f"missing {name}: {job.source_dir}")


def ensure_targets_absent(jobs: list[Job]) -> None:
    target_roots = sorted({job.target_dir.parent for job in jobs})
    existing = [path for path in target_roots if path.exists()]
    if existing:
        names = ", ".join(str(path.relative_to(REPO_ROOT)) for path in existing)
        raise FileExistsError(f"refusing to overwrite existing target test directory/directories: {names}")


def copy_case_inputs(job: Job) -> None:
    job.target_dir.mkdir(parents=True, exist_ok=False)
    for entry in job.source_dir.iterdir():
        if entry.name in EXCLUDED_SOURCE_ENTRIES:
            continue
        destination = job.target_dir / entry.name
        if entry.is_dir():
            shutil.copytree(entry, destination)
        else:
            shutil.copy2(entry, destination)


def is_independent(row: dict[str, str]) -> bool:
    return not row.get(DEPENDENCY_COL, "").strip()


def scaled_independent_rows(path: Path) -> tuple[list[str], list[dict[str, str]], int, int, int, str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        required = {SIZE_COL, PHASE_COL, DEPENDENCY_COL}
        missing = required - set(fieldnames)
        if missing:
            raise ValueError(f"{path} missing columns: {sorted(missing)}")
        source_rows = list(reader)

    selected_rows = [row for row in source_rows if is_independent(row)]
    if not selected_rows:
        raise ValueError(f"{path} has no independent traffic")

    source_bytes = 0
    scaled_bytes = 0
    for row in selected_rows:
        original = int(float(row[SIZE_COL]))
        if original <= 0:
            scaled = original
        else:
            scaled = max(1, original // SCALE)
        row[SIZE_COL] = str(scaled)
        source_bytes += original
        scaled_bytes += scaled
    phase_ids = "|".join(sorted({row[PHASE_COL].strip() for row in selected_rows}, key=int))
    return fieldnames, selected_rows, len(source_rows), source_bytes, scaled_bytes, phase_ids


def rewrite_independent_traffic(job: Job) -> TrafficInfo:
    fieldnames, selected_rows, source_rows, source_bytes, scaled_bytes, phase_ids = scaled_independent_rows(
        job.original_traffic
    )

    with job.traffic.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(selected_rows)

    return TrafficInfo(job, source_rows, len(selected_rows), source_bytes, scaled_bytes, phase_ids)


def validate_written_traffic(info: TrafficInfo) -> None:
    with info.job.traffic.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != info.selected_rows:
        raise ValueError(f"unexpected row count in {info.job.traffic}: {len(rows)}")
    if any(not is_independent(row) for row in rows):
        raise ValueError(f"dependent traffic written to {info.job.traffic}")
    actual_bytes = sum(int(float(row[SIZE_COL])) for row in rows)
    if actual_bytes != info.scaled_bytes:
        raise ValueError(f"scaled-byte mismatch in {info.job.traffic}: {actual_bytes} != {info.scaled_bytes}")


def validate_existing_target(job: Job) -> TrafficInfo:
    if not job.target_dir.is_dir():
        raise FileNotFoundError(f"missing prepared target case: {job.target_dir}")
    if not job.traffic.is_file():
        raise FileNotFoundError(f"missing prepared traffic: {job.traffic}")
    expected_fields, expected_rows, source_rows, source_bytes, scaled_bytes, phase_ids = scaled_independent_rows(
        job.source_dir / "traffic.original.csv"
    )
    with job.traffic.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        actual_fields = list(reader.fieldnames or [])
        actual_rows = list(reader)
    if actual_fields != expected_fields or actual_rows != expected_rows:
        raise ValueError(f"prepared traffic differs from expected independent scale{SCALE} data: {job.traffic}")
    info = TrafficInfo(job, source_rows, len(expected_rows), source_bytes, scaled_bytes, phase_ids)
    validate_written_traffic(info)
    return info


def clear_case_outputs(job: Job) -> None:
    shutil.rmtree(job.target_dir / "output", ignore_errors=True)
    shutil.rmtree(job.target_dir / "runlog", ignore_errors=True)


def write_traffic_summary(infos: list[TrafficInfo], log_dir: Path) -> None:
    fields = (
        "source_test",
        "target_test",
        "case",
        "scale",
        "source_rows",
        "selected_rows",
        "independent_phase_ids",
        "source_independent_bytes",
        "scaled_independent_bytes",
        "ratio",
        "traffic",
    )
    with (log_dir / "traffic_scale_summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for info in infos:
            writer.writerow(
                {
                    "source_test": info.job.source_test,
                    "target_test": info.job.target_test,
                    "case": info.job.case,
                    "scale": SCALE,
                    "source_rows": info.source_rows,
                    "selected_rows": info.selected_rows,
                    "independent_phase_ids": info.phase_ids,
                    "source_independent_bytes": info.source_bytes,
                    "scaled_independent_bytes": info.scaled_bytes,
                    "ratio": f"{info.scaled_bytes / info.source_bytes:.12f}",
                    "traffic": info.job.traffic.relative_to(REPO_ROOT).as_posix(),
                }
            )


def summarize_stats(path: Path) -> dict[str, str]:
    empty = {
        "metric_status": "MISSING_STATS",
        "tasks": "",
        "max_complete_us": "",
        "avg_complete_us": "",
        "p95_complete_us": "",
        "avg_fct_us": "",
        "avg_throughput_gbps": "",
        "min_throughput_gbps": "",
    }
    if not path.is_file():
        return empty

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {SIZE_COL, START_COL, COMPLETE_COL, THROUGHPUT_COL}
        missing = required - set(reader.fieldnames or [])
        if missing:
            return {**empty, "metric_status": f"MISSING_COLUMNS:{'|'.join(sorted(missing))}"}
        rows = list(reader)
    if not rows:
        return {**empty, "metric_status": "EMPTY_STATS", "tasks": "0"}

    completes = sorted(float(row[COMPLETE_COL]) for row in rows)
    fcts = [float(row[COMPLETE_COL]) - float(row[START_COL]) for row in rows]
    throughputs = [float(row[THROUGHPUT_COL]) for row in rows]
    return {
        "metric_status": "OK",
        "tasks": str(len(rows)),
        "max_complete_us": f"{max(completes):.6f}",
        "avg_complete_us": f"{mean(completes):.6f}",
        "p95_complete_us": f"{percentile(completes, 0.95):.6f}",
        "avg_fct_us": f"{mean(fcts):.6f}",
        "avg_throughput_gbps": f"{mean(throughputs):.6f}",
        "min_throughput_gbps": f"{min(throughputs):.6f}",
    }


def launch(job: Job, log_dir: Path) -> tuple[subprocess.Popen[str], float, Path, object]:
    log_path = log_dir / f"{job.target_test}__{job.case}.log"
    log_handle = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            "python3.12",
            "./ns3",
            "run",
            "--no-build",
            f"scratch/ub-quick-example --case-path={job.relative_target_dir}",
        ],
        cwd=REPO_ROOT,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return process, time.monotonic(), log_path, log_handle


def write_run_summaries(rows: list[dict[str, str]], log_dir: Path) -> None:
    fields = (
        "finish_order",
        "target_test",
        "case",
        "returncode",
        "elapsed_s",
        "metric_status",
        "tasks",
        "max_complete_us",
        "delta_vs_case01_us",
        "delta_vs_case01_percent",
        "avg_complete_us",
        "p95_complete_us",
        "avg_fct_us",
        "avg_throughput_gbps",
        "min_throughput_gbps",
        "task_statistics",
        "log",
    )
    for row in rows:
        baseline = next(
            (
                item
                for item in rows
                if item["target_test"] == row["target_test"]
                and item["case"] == "case01_standard"
                and item["returncode"] == "0"
                and item["metric_status"] == "OK"
            ),
            None,
        )
        if baseline is None or row["metric_status"] != "OK":
            row["delta_vs_case01_us"] = ""
            row["delta_vs_case01_percent"] = ""
            continue
        value = float(row["max_complete_us"])
        baseline_value = float(baseline["max_complete_us"])
        row["delta_vs_case01_us"] = f"{value - baseline_value:.6f}"
        row["delta_vs_case01_percent"] = (
            "" if baseline_value == 0 else f"{(value - baseline_value) / baseline_value * 100:.6f}"
        )

    for filename, delimiter in (("run_summary.csv", ","), ("result_summary.tsv", "\t")):
        with (log_dir / filename).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter=delimiter)
            writer.writeheader()
            writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def run_jobs(jobs: list[Job], parallel: int, log_dir: Path) -> list[dict[str, str]]:
    pending = jobs[:]
    active: list[tuple[Job, subprocess.Popen[str], float, Path, object]] = []
    results: list[dict[str, str]] = []
    while pending or active:
        while pending and len(active) < parallel:
            job = pending.pop(0)
            process, started, log_path, log_handle = launch(job, log_dir)
            active.append((job, process, started, log_path, log_handle))
            print(f"[{datetime.now():%H:%M:%S}] START {job.name}", flush=True)

        time.sleep(5)
        still_active: list[tuple[Job, subprocess.Popen[str], float, Path, object]] = []
        for job, process, started, log_path, log_handle in active:
            returncode = process.poll()
            if returncode is None:
                still_active.append((job, process, started, log_path, log_handle))
                continue
            log_handle.close()
            elapsed = time.monotonic() - started
            stats = summarize_stats(job.stats)
            row = {
                "finish_order": str(len(results) + 1),
                "target_test": job.target_test,
                "case": job.case,
                "returncode": str(returncode),
                "elapsed_s": f"{elapsed:.3f}",
                "task_statistics": job.stats.relative_to(REPO_ROOT).as_posix(),
                "log": log_path.relative_to(REPO_ROOT).as_posix(),
            }
            row.update(stats)
            results.append(row)
            status = "OK" if returncode == 0 and stats["metric_status"] == "OK" else "FAIL"
            print(
                f"[{datetime.now():%H:%M:%S}] DONE {status} {job.name} rc={returncode} "
                f"elapsed={elapsed:.1f}s max_complete_us={stats['max_complete_us']}",
                flush=True,
            )
        active = still_active
        write_run_summaries(results, log_dir)
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parallel", type=int, default=5, help="maximum concurrent simulations")
    parser.add_argument("--prepare-only", action="store_true", help="create and validate test91/test92 without running")
    parser.add_argument(
        "--run-existing",
        action="store_true",
        help="run already-prepared targets only after exact traffic validation; never overwrite them",
    )
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="rewrite existing target traffic with the current selector and clear only their output/runlog",
    )
    parser.add_argument(
        "--label",
        default=f"test91_92_independent_scale160_{datetime.now():%Y%m%d_%H%M%S}",
        help="new directory under scratch/pod1d/run_scripts/batch_run_logs",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.parallel < 1:
        raise ValueError("--parallel must be at least 1")
    if sum((args.prepare_only, args.run_existing, args.refresh_existing)) > 1:
        raise ValueError("--prepare-only, --run-existing, and --refresh-existing are mutually exclusive")

    jobs = build_jobs()
    ensure_source_inputs(jobs)
    log_dir = SCRIPT_DIR / "batch_run_logs" / args.label
    log_dir.mkdir(parents=True, exist_ok=False)

    if args.refresh_existing:
        infos = []
        for job in jobs:
            if not job.target_dir.is_dir():
                raise FileNotFoundError(f"missing prepared target case: {job.target_dir}")
            info = rewrite_independent_traffic(job)
            validate_written_traffic(info)
            clear_case_outputs(job)
            infos.append(info)
    elif args.run_existing:
        infos = [validate_existing_target(job) for job in jobs]
    else:
        ensure_targets_absent(jobs)
        infos = []
        for job in jobs:
            copy_case_inputs(job)
            info = rewrite_independent_traffic(job)
            validate_written_traffic(info)
            infos.append(info)
    write_traffic_summary(infos, log_dir)

    print(f"log_dir={log_dir}", flush=True)
    print(f"created_tests=test91_dp_reduce_scatter,test92_dp_all_gather", flush=True)
    print(f"traffic=all_independent_only scale={SCALE} jobs={len(jobs)}", flush=True)
    if args.prepare_only:
        return 0

    results = run_jobs(jobs, args.parallel, log_dir)
    failed = [row for row in results if row["returncode"] != "0" or row["metric_status"] != "OK"]
    print(f"traffic_summary={log_dir / 'traffic_scale_summary.csv'}", flush=True)
    print(f"run_summary={log_dir / 'run_summary.csv'}", flush=True)
    print(f"total={len(results)} failed={len(failed)}", flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
