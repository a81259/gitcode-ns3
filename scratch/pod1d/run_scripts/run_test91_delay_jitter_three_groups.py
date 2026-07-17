#!/usr/bin/env python3
"""Run three deterministic delay-jitter replicas for test91 standard topology and fault3."""

from __future__ import annotations

import argparse
import csv
import random
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from statistics import fmean, pstdev


SCRIPT_DIR = Path(__file__).resolve().parent
POD_ROOT = SCRIPT_DIR.parent
REPO_ROOT = POD_ROOT.parents[1]
SOURCE_ROOT = POD_ROOT / "test91_dp_reduce_scatter"
TARGET_ROOT = POD_ROOT / "test91_delay_jitter_three_groups"
GROUP_SEEDS = (101, 202, 303)
CASES = (
    ("标准拓扑", "case01_standard"),
    ("故障3（L1–L2 分布式 Port Down，每个 POD 1 根）", "case06_pod1_18_l1_first_l2_port_down"),
)
EXCLUDED_ENTRIES = {"output", "runlog"}
DELAY_RE = re.compile(r"^(?P<value>\d+)(?P<unit>ps|ns|us|ms|s)$")
UNIT_TO_PS = {"ps": 1, "ns": 1_000, "us": 1_000_000, "ms": 1_000_000_000, "s": 1_000_000_000_000}


def delay_to_ps(delay: str) -> int:
    match = DELAY_RE.fullmatch(delay.strip())
    if match is None:
        raise ValueError(f"only non-negative integer ps/ns/us/ms/s delays are supported, got {delay!r}")
    return int(match["value"]) * UNIT_TO_PS[match["unit"]]


def copy_case_inputs(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    for entry in source.iterdir():
        if entry.name in EXCLUDED_ENTRIES:
            continue
        destination = target / entry.name
        if entry.is_dir():
            shutil.copytree(entry, destination)
        else:
            shutil.copy2(entry, destination)


def load_source_traffic() -> tuple[list[str], list[dict[str, str]]]:
    source = SOURCE_ROOT / "case01_standard" / "traffic.csv"
    with source.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    required = {"taskId", "delay"}
    if required - set(fields):
        raise ValueError(f"{source} missing columns {sorted(required - set(fields))}")
    return fields, rows


def jittered_rows(rows: list[dict[str, str]], seed: int) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    generator = random.Random(seed)
    jittered: list[dict[str, str]] = []
    audit_rows: list[dict[str, str]] = []
    for row in rows:
        base_ps = delay_to_ps(row["delay"])
        jitter_ps = generator.randint(0, 499)
        copy = dict(row)
        copy["delay"] = f"{base_ps + jitter_ps}ps"
        jittered.append(copy)
        audit_rows.append(
            {
                "taskId": row["taskId"],
                "base_delay": row["delay"],
                "jitter_ps": str(jitter_ps),
                "jittered_delay": copy["delay"],
            }
        )
    return jittered, audit_rows


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def prepare(log_dir: Path) -> list[tuple[int, str, str, Path]]:
    if TARGET_ROOT.exists():
        raise FileExistsError(f"refusing to overwrite existing experiment root: {TARGET_ROOT}")
    fields, source_rows = load_source_traffic()
    jobs: list[tuple[int, str, str, Path]] = []
    for seed in GROUP_SEEDS:
        group_dir = TARGET_ROOT / f"group_seed{seed}"
        jittered, audit = jittered_rows(source_rows, seed)
        write_csv(log_dir / f"delay_jitter_seed{seed}.csv", ["taskId", "base_delay", "jitter_ps", "jittered_delay"], audit)
        for title, case in CASES:
            source = SOURCE_ROOT / case
            if not source.is_dir():
                raise FileNotFoundError(f"missing source case: {source}")
            target = group_dir / case
            copy_case_inputs(source, target)
            write_csv(target / "traffic.csv", fields, jittered)
            jobs.append((seed, title, case, target))
    return jobs


def summarize_stats(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {"status": "MISSING_STATS", "tasks": "", "max_complete_us": "", "avg_complete_us": ""}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {"status": "EMPTY_STATS", "tasks": "0", "max_complete_us": "", "avg_complete_us": ""}
    completes = [float(row["taskCompletesTime(us)"]) for row in rows]
    return {
        "status": "OK",
        "tasks": str(len(rows)),
        "max_complete_us": f"{max(completes):.6f}",
        "avg_complete_us": f"{fmean(completes):.6f}",
    }


def launch(seed: int, case: str, target: Path, log_dir: Path) -> tuple[subprocess.Popen[str], object, float, Path]:
    log_path = log_dir / f"seed{seed}__{case}.log"
    handle = log_path.open("w", encoding="utf-8")
    relative = target.relative_to(REPO_ROOT).as_posix()
    process = subprocess.Popen(
        [
            "python3.12",
            "./ns3",
            "run",
            "--no-build",
            f"scratch/ub-quick-example --case-path={relative} --rng-run={seed}",
        ],
        cwd=REPO_ROOT,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return process, handle, time.monotonic(), log_path


def write_summaries(rows: list[dict[str, str]], log_dir: Path) -> None:
    fields = (
        "seed", "rng_seed", "case", "title", "returncode", "elapsed_s", "status", "tasks",
        "max_complete_us", "avg_complete_us", "max_delta_vs_standard_us", "max_delta_vs_standard_percent",
        "avg_delta_vs_standard_us", "avg_delta_vs_standard_percent", "case_path", "log",
    )
    by_seed_case = {(row["seed"], row["case"]): row for row in rows}
    for row in rows:
        baseline = by_seed_case.get((row["seed"], "case01_standard"))
        if baseline is None or row["status"] != "OK" or baseline["status"] != "OK":
            continue
        for metric, prefix in (("max_complete_us", "max"), ("avg_complete_us", "avg")):
            value = float(row[metric])
            base = float(baseline[metric])
            row[f"{prefix}_delta_vs_standard_us"] = f"{value - base:.6f}"
            row[f"{prefix}_delta_vs_standard_percent"] = "" if base == 0 else f"{(value - base) / base * 100:.6f}"
    write_csv(log_dir / "run_summary.csv", list(fields), rows)

    aggregate_rows: list[dict[str, str]] = []
    for case in (case for _title, case in CASES):
        subset = [row for row in rows if row["case"] == case and row["status"] == "OK"]
        if len(subset) != len(GROUP_SEEDS):
            continue
        for metric in ("max_complete_us", "avg_complete_us"):
            values = [float(row[metric]) for row in subset]
            aggregate_rows.append(
                {
                    "case": case,
                    "metric": metric,
                    "replicas": str(len(values)),
                    "mean_us": f"{fmean(values):.6f}",
                    "stddev_us": f"{pstdev(values):.6f}",
                    "min_us": f"{min(values):.6f}",
                    "max_us": f"{max(values):.6f}",
                }
            )
    write_csv(log_dir / "replica_summary.csv", ["case", "metric", "replicas", "mean_us", "stddev_us", "min_us", "max_us"], aggregate_rows)


def run_jobs(jobs: list[tuple[int, str, str, Path]], parallel: int, log_dir: Path) -> int:
    pending = jobs[:]
    active: list[tuple[int, str, str, Path, subprocess.Popen[str], object, float, Path]] = []
    rows: list[dict[str, str]] = []
    while pending or active:
        while pending and len(active) < parallel:
            seed, title, case, target = pending.pop(0)
            process, handle, started, log_path = launch(seed, case, target, log_dir)
            active.append((seed, title, case, target, process, handle, started, log_path))
            print(f"[{datetime.now():%H:%M:%S}] START seed={seed} {title}", flush=True)
        time.sleep(5)
        remaining = []
        for seed, title, case, target, process, handle, started, log_path in active:
            result = process.poll()
            if result is None:
                remaining.append((seed, title, case, target, process, handle, started, log_path))
                continue
            handle.close()
            stats = summarize_stats(target / "output" / "task_statistics.csv")
            row = {
                "seed": str(seed),
                "rng_seed": str(seed),
                "case": case,
                "title": title,
                "returncode": str(result),
                "elapsed_s": f"{time.monotonic() - started:.3f}",
                "case_path": target.relative_to(REPO_ROOT).as_posix(),
                "log": log_path.relative_to(REPO_ROOT).as_posix(),
            }
            row.update(stats)
            rows.append(row)
            print(f"[{datetime.now():%H:%M:%S}] DONE seed={seed} {case} rc={result}", flush=True)
        active = remaining
        write_summaries(rows, log_dir)
    failed = [row for row in rows if row["returncode"] != "0" or row["status"] != "OK"]
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parallel", type=int, default=2)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument(
        "--label",
        default=f"test91_delay_jitter_three_groups_{datetime.now():%Y%m%d_%H%M%S}",
        help="new batch_run_logs directory",
    )
    args = parser.parse_args()
    if args.parallel < 1:
        raise ValueError("--parallel must be at least 1")
    log_dir = SCRIPT_DIR / "batch_run_logs" / args.label
    log_dir.mkdir(parents=True, exist_ok=False)
    jobs = prepare(log_dir)
    print("groups=3 seeds=101,202,303 jitter=0..499ps rng_run=group_seed", flush=True)
    print(f"target_root={TARGET_ROOT}", flush=True)
    print(f"log_dir={log_dir}", flush=True)
    if args.prepare_only:
        return 0
    return run_jobs(jobs, args.parallel, log_dir)


if __name__ == "__main__":
    raise SystemExit(main())
