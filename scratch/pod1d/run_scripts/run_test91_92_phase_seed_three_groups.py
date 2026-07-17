#!/usr/bin/env python3
"""Run Test91/Test92 with three reproducible packet-spray phase seeds."""

from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from statistics import fmean, pstdev


SCRIPT_DIR = Path(__file__).resolve().parent
POD_ROOT = SCRIPT_DIR.parent
REPO_ROOT = POD_ROOT.parents[1]
TARGET_ROOT = POD_ROOT / "test91_92_phase_seed_three_groups"
PHASE_SEEDS = (101, 202, 303)
FIXED_RNG_RUN = 10
TESTS = (
    ("test91_dp_reduce_scatter", "Reduce Scatter"),
    ("test92_dp_all_gather", "All Gather"),
)
CASES = (
    ("case01_standard", "标准拓扑"),
    ("case04_l1_l2_lane_down", "故障1（L1–L2 单链路 Lane Down）"),
    ("case05_l1_l2_port_down", "故障2（L1–L2 单链路 Port Down）"),
    ("case06_pod1_18_l1_first_l2_port_down", "故障3（L1–L2 分布式 Port Down，每个 POD 1 根）"),
    ("case07_pod1_4l1_full_1l1_half_l2_port_down", "故障4（L1–L2 集中式 Port Down）"),
)
EXCLUDED_ENTRIES = {"output", "runlog"}
PHASE_SEED_PREFIX = "default ns3::UbRoutingProcess::PacketSprayPhaseSeed "
PACKET_SPRAY_MODE_PREFIX = "default ns3::UbRoutingProcess::PacketSprayMode "


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


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


def configure_phase_seed(path: Path, seed: int) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    configured = f'{PHASE_SEED_PREFIX}"{seed}"'
    output: list[str] = []
    inserted = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(PHASE_SEED_PREFIX):
            if not inserted:
                output.append(configured)
                inserted = True
            continue
        output.append(line)
        if stripped.startswith(PACKET_SPRAY_MODE_PREFIX) and not inserted:
            output.append(configured)
            inserted = True
    if not inserted:
        raise ValueError(f"{path} does not configure UbRoutingProcess::PacketSprayMode")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def prepare() -> list[tuple[str, str, int, str, str, Path]]:
    if TARGET_ROOT.exists():
        raise FileExistsError(f"refusing to overwrite existing experiment root: {TARGET_ROOT}")
    jobs: list[tuple[str, str, int, str, str, Path]] = []
    for test_name, test_title in TESTS:
        for seed in PHASE_SEEDS:
            for case_name, case_title in CASES:
                source = POD_ROOT / test_name / case_name
                if not source.is_dir():
                    raise FileNotFoundError(f"missing source case: {source}")
                target = TARGET_ROOT / f"phase_seed{seed}" / test_name / case_name
                copy_case_inputs(source, target)
                configure_phase_seed(target / "network_attribute.txt", seed)
                jobs.append((test_name, test_title, seed, case_name, case_title, target))
    return jobs


def prepared_jobs() -> list[tuple[str, str, int, str, str, Path]]:
    if not TARGET_ROOT.is_dir():
        raise FileNotFoundError(f"missing prepared experiment root: {TARGET_ROOT}")
    jobs: list[tuple[str, str, int, str, str, Path]] = []
    for test_name, test_title in TESTS:
        for seed in PHASE_SEEDS:
            for case_name, case_title in CASES:
                target = TARGET_ROOT / f"phase_seed{seed}" / test_name / case_name
                network = target / "network_attribute.txt"
                if not network.is_file():
                    raise FileNotFoundError(f"missing prepared network attributes: {network}")
                expected = f'{PHASE_SEED_PREFIX}"{seed}"'
                if expected not in network.read_text(encoding="utf-8").splitlines():
                    raise ValueError(f"wrong PacketSprayPhaseSeed in {network}")
                jobs.append((test_name, test_title, seed, case_name, case_title, target))
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


def launch(target: Path, log_path: Path) -> tuple[subprocess.Popen[str], object, float]:
    handle = log_path.open("w", encoding="utf-8")
    relative = target.relative_to(REPO_ROOT).as_posix()
    process = subprocess.Popen(
        [
            "python3.12",
            "./ns3",
            "run",
            "--no-build",
            f"scratch/ub-quick-example --case-path={relative} --rng-run={FIXED_RNG_RUN}",
        ],
        cwd=REPO_ROOT,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return process, handle, time.monotonic()


def write_summaries(rows: list[dict[str, str]], log_dir: Path) -> None:
    fields = (
        "test", "test_title", "phase_seed", "rng_run", "case", "title", "returncode", "elapsed_s",
        "status", "tasks", "max_complete_us", "avg_complete_us", "max_delta_vs_standard_us",
        "max_delta_vs_standard_percent", "avg_delta_vs_standard_us",
        "avg_delta_vs_standard_percent", "case_path", "log",
    )
    baseline_map = {
        (row["test"], row["phase_seed"]): row
        for row in rows
        if row["case"] == "case01_standard"
    }
    for row in rows:
        baseline = baseline_map.get((row["test"], row["phase_seed"]))
        if baseline is None or row["status"] != "OK" or baseline["status"] != "OK":
            continue
        for metric, prefix in (("max_complete_us", "max"), ("avg_complete_us", "avg")):
            value = float(row[metric])
            base = float(baseline[metric])
            row[f"{prefix}_delta_vs_standard_us"] = f"{value - base:.6f}"
            row[f"{prefix}_delta_vs_standard_percent"] = (
                "" if base == 0 else f"{(value - base) / base * 100:.6f}"
            )
    write_csv(log_dir / "run_summary.csv", list(fields), rows)

    aggregate_rows: list[dict[str, str]] = []
    for test_name, test_title in TESTS:
        for case_name, case_title in CASES:
            subset = [
                row
                for row in rows
                if row["test"] == test_name and row["case"] == case_name and row["status"] == "OK"
            ]
            if len(subset) != len(PHASE_SEEDS):
                continue
            for metric in ("max_complete_us", "avg_complete_us"):
                values = [float(row[metric]) for row in subset]
                aggregate_rows.append(
                    {
                        "test": test_name,
                        "test_title": test_title,
                        "case": case_name,
                        "title": case_title,
                        "metric": metric,
                        "replicas": str(len(values)),
                        "mean_us": f"{fmean(values):.6f}",
                        "stddev_us": f"{pstdev(values):.6f}",
                        "min_us": f"{min(values):.6f}",
                        "max_us": f"{max(values):.6f}",
                    }
                )
    write_csv(
        log_dir / "replica_summary.csv",
        ["test", "test_title", "case", "title", "metric", "replicas", "mean_us", "stddev_us", "min_us", "max_us"],
        aggregate_rows,
    )


def run_jobs(
    jobs: list[tuple[str, str, int, str, str, Path]],
    parallel: int,
    log_dir: Path,
) -> int:
    pending = jobs[:]
    active: list[
        tuple[str, str, int, str, str, Path, subprocess.Popen[str], object, float, Path]
    ] = []
    rows: list[dict[str, str]] = []
    while pending or active:
        while pending and len(active) < parallel:
            test_name, test_title, seed, case_name, case_title, target = pending.pop(0)
            log_path = log_dir / f"{test_name}__phase_seed{seed}__{case_name}.log"
            process, handle, started = launch(target, log_path)
            active.append(
                (test_name, test_title, seed, case_name, case_title, target, process, handle, started, log_path)
            )
            print(f"[{datetime.now():%H:%M:%S}] START {test_name} phase_seed={seed} {case_name}", flush=True)
        time.sleep(5)
        remaining = []
        for test_name, test_title, seed, case_name, case_title, target, process, handle, started, log_path in active:
            result = process.poll()
            if result is None:
                remaining.append(
                    (test_name, test_title, seed, case_name, case_title, target, process, handle, started, log_path)
                )
                continue
            handle.close()
            row = {
                "test": test_name,
                "test_title": test_title,
                "phase_seed": str(seed),
                "rng_run": str(FIXED_RNG_RUN),
                "case": case_name,
                "title": case_title,
                "returncode": str(result),
                "elapsed_s": f"{time.monotonic() - started:.3f}",
                "case_path": target.relative_to(REPO_ROOT).as_posix(),
                "log": log_path.relative_to(REPO_ROOT).as_posix(),
            }
            row.update(summarize_stats(target / "output" / "task_statistics.csv"))
            rows.append(row)
            print(
                f"[{datetime.now():%H:%M:%S}] DONE {test_name} phase_seed={seed} "
                f"{case_name} rc={result}",
                flush=True,
            )
        active = remaining
        write_summaries(rows, log_dir)
    return 1 if any(row["returncode"] != "0" or row["status"] != "OK" for row in rows) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parallel", type=int, default=5)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--run-prepared", action="store_true")
    parser.add_argument(
        "--label",
        default=f"test91_92_phase_seed_three_groups_{datetime.now():%Y%m%d_%H%M%S}",
    )
    args = parser.parse_args()
    if args.parallel < 1:
        raise ValueError("--parallel must be at least 1")
    if args.prepare_only and args.run_prepared:
        raise ValueError("--prepare-only and --run-prepared are mutually exclusive")
    log_dir = SCRIPT_DIR / "batch_run_logs" / args.label
    log_dir.mkdir(parents=True, exist_ok=False)
    jobs = prepared_jobs() if args.run_prepared else prepare()
    print(
        f"jobs={len(jobs)} phase_seeds={PHASE_SEEDS} rng_run={FIXED_RNG_RUN} "
        "traffic=identical_across_phase_seeds",
        flush=True,
    )
    print(f"target_root={TARGET_ROOT}", flush=True)
    print(f"log_dir={log_dir}", flush=True)
    if args.prepare_only:
        return 0
    return run_jobs(jobs, args.parallel, log_dir)


if __name__ == "__main__":
    raise SystemExit(main())
