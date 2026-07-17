#!/usr/bin/env python3
from __future__ import annotations

import csv
import gzip
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parents[1]
MATRIX = json.loads((PACKAGE_ROOT / "matrix.yaml").read_text(encoding="utf-8"))["cases"]
BLOCK_ORDER = ("adaptive-single-packet-sparse", "per-flow-all-distinct-keys")
MAX_PACKAGE_BYTES = 1024**3


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def package_size_bytes() -> int:
    return sum(path.stat().st_size for path in PACKAGE_ROOT.rglob("*") if path.is_file())


def portable_command(row: dict) -> str:
    return (
        "python3.12 ./ns3 run --no-build "
        f"'scratch/ub-quick-example --case-path=scratch/20260715-routing-strategy-"
        f"suitability-followup/cases/{row['case_id']}'"
    )


def clean_case_outputs(case_dir: Path) -> None:
    for name in ("runlog", "output", "test"):
        path = case_dir / name
        if path.exists():
            shutil.rmtree(path)
    (case_dir / "console.log").unlink(missing_ok=True)


def gzip_traces(case_dir: Path) -> None:
    runlog = case_dir / "runlog"
    if not runlog.is_dir():
        return
    for source in sorted(runlog.glob("*.tr")):
        target = source.with_suffix(source.suffix + ".gz")
        with source.open("rb") as input_handle, gzip.open(
            target, "wb", compresslevel=6
        ) as output_handle:
            shutil.copyfileobj(input_handle, output_handle)
        source.unlink()


def completed_task_count(case_dir: Path) -> tuple[int, int]:
    traffic_path = case_dir / "traffic.csv"
    stats_path = case_dir / "output/task_statistics.csv"
    if not traffic_path.is_file() or not stats_path.is_file():
        return 0, 0
    with traffic_path.open(newline="", encoding="utf-8-sig") as handle:
        expected = sum(1 for _ in csv.DictReader(handle))
    with stats_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    completed = sum(bool(row.get("taskCompletesTime(us)")) for row in rows)
    return completed, expected


def artifact_gate(row: dict, case_dir: Path) -> tuple[bool, str]:
    completed, expected = completed_task_count(case_dir)
    if expected == 0 or completed != expected:
        return False, f"completed_tasks={completed}/{expected}"
    required = (case_dir / "output/task_statistics.csv", case_dir / "output/throughput.csv")
    if any(not path.is_file() for path in required):
        return False, "parser summary missing"
    runlog = case_dir / "runlog"
    branch_node = 2 if row["block_id"].startswith("adaptive") else 16
    if not any(runlog.glob(f"PortTrace_node_{branch_node}_port_*.tr*")):
        return False, "branch port trace missing"
    if row["observability"] == "detailed" and not any(
        runlog.glob("AllPacketTrace_PKT_node_*.tr*")
    ):
        return False, "detailed packet path trace missing"
    return True, f"completed_tasks={completed}/{expected}"


def artifact_inventory(case_dir: Path) -> list[str]:
    names = ("console.log", "runlog", "output/task_statistics.csv", "output/throughput.csv")
    return [name for name in names if (case_dir / name).exists()]


def run_case(row: dict) -> dict:
    case_dir = PACKAGE_ROOT / row["case_dir"]
    clean_case_outputs(case_dir)
    relative = case_dir.relative_to(REPO_ROOT)
    command = [
        sys.executable,
        str(REPO_ROOT / "ns3"),
        "run",
        "--no-build",
        f"scratch/ub-quick-example --case-path={relative}",
    ]
    started_wall = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("OPENUSIM_CASE_TIMEOUT", "180")),
            check=False,
        )
        return_code = completed.returncode
        output = completed.stdout + completed.stderr
        status = "success" if return_code == 0 else "failed"
        failure_category = "" if return_code == 0 else "simulation_or_configuration_failure"
    except subprocess.TimeoutExpired as error:
        return_code = 124
        stdout = error.stdout.decode() if isinstance(error.stdout, bytes) else (error.stdout or "")
        stderr = error.stderr.decode() if isinstance(error.stderr, bytes) else (error.stderr or "")
        output = stdout + stderr + "\nTIMEOUT\n"
        status = "failed"
        failure_category = "timeout"
    (case_dir / "console.log").write_text(output, encoding="utf-8")
    if status == "success":
        gate_ok, gate_detail = artifact_gate(row, case_dir)
        if not gate_ok:
            status = "failed"
            failure_category = "artifact_gate_failure"
    else:
        gate_detail = "run did not return success"
    gzip_traces(case_dir)
    return {
        "case_id": row["case_id"],
        "block_id": row["block_id"],
        "status": status,
        "return_code": return_code,
        "duration_s": round(time.monotonic() - started, 3),
        "started_at": started_wall,
        "command": portable_command(row),
        "artifacts": artifact_inventory(case_dir),
        "artifact_gate": gate_detail,
        "failure_category": failure_category,
        "retryable": failure_category in {"timeout", "artifact_gate_failure"},
    }


def skipped_result(row: dict, reason: str) -> dict:
    return {
        "case_id": row["case_id"],
        "block_id": row["block_id"],
        "status": "skipped",
        "return_code": "",
        "duration_s": 0,
        "started_at": "",
        "command": portable_command(row),
        "artifacts": [],
        "artifact_gate": "not run",
        "failure_category": reason,
        "retryable": True,
    }


def pilot_rows(rows: list[dict]) -> list[dict]:
    control = next(row for row in rows if row["role"] == "control")
    treatment = next(row for row in rows if row["role"] == "treatment")
    return [control, treatment]


def write_ledgers(results: list[dict], checkpoints: dict[str, str], run_meta: dict) -> None:
    by_id = {result["case_id"]: result for result in results}
    lines = [
        "# Run Ledger",
        "",
        f"- branch: `{run_meta['branch']}`",
        f"- commit: `{run_meta['commit']}`",
        f"- dirty_at_start: `{str(run_meta['dirty_at_start']).lower()}`",
        "- checkpoint_policy: continue_full_matrix with per-block safety pilots",
        "- execution: sequential-only",
        f"- package_size_bytes: `{package_size_bytes()}`",
        "",
        "## Checkpoints",
        "",
    ]
    lines.extend(f"- {block}: {checkpoints.get(block, 'pending')}" for block in BLOCK_ORDER)
    lines.extend(
        (
            "",
            "| case | block | status | return code | duration (s) | artifact gate |",
            "|---|---|---:|---:|---:|---|",
        )
    )
    for row in MATRIX:
        result = by_id.get(row["case_id"], {})
        lines.append(
            f"| {row['case_id']} | {row['block_id']} | {result.get('status', 'pending')} | "
            f"{result.get('return_code', '')} | {result.get('duration_s', '')} | "
            f"{result.get('artifact_gate', '')} |"
        )
    (PACKAGE_ROOT / "run-ledger.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (PACKAGE_ROOT / "run-ledger.json").write_text(
        json.dumps(
            {"run_meta": run_meta, "checkpoints": checkpoints, "results": results}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    run_meta = {
        "branch": git_output("branch", "--show-current"),
        "commit": git_output("rev-parse", "HEAD"),
        "dirty_at_start": bool(git_output("status", "--short")),
        "runtime": sys.executable,
        "runner": "scratch/ub-quick-example",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "package_size_limit_bytes": MAX_PACKAGE_BYTES,
    }
    results: list[dict] = []
    checkpoints = {block: "pending" for block in BLOCK_ORDER}
    write_ledgers(results, checkpoints, run_meta)
    for block in BLOCK_ORDER:
        rows = [row for row in MATRIX if row["block_id"] == block]
        pilots = pilot_rows(rows)
        pilot_ids = {row["case_id"] for row in pilots}
        checkpoints[block] = "pilot-running"
        write_ledgers(results, checkpoints, run_meta)
        block_failed = False
        for index, row in enumerate(pilots, start=1):
            print(f"[{block} pilot {index}/{len(pilots)}] {row['case_id']}", flush=True)
            result = run_case(row)
            results.append(result)
            write_ledgers(results, checkpoints, run_meta)
            if result["status"] != "success":
                block_failed = True
                checkpoints[block] = f"failed: {row['case_id']} {result['failure_category']}"
                break
        remaining = [row for row in rows if row["case_id"] not in pilot_ids]
        if block_failed:
            results.extend(skipped_result(row, "block_safety_stop") for row in remaining)
            write_ledgers(results, checkpoints, run_meta)
            continue
        checkpoints[block] = "pilot-passed; matrix-running"
        write_ledgers(results, checkpoints, run_meta)
        for index, row in enumerate(remaining, start=1):
            if package_size_bytes() > MAX_PACKAGE_BYTES:
                checkpoints[block] = "failed: package-size safety limit exceeded"
                results.extend(skipped_result(item, "package_size_limit") for item in remaining[index - 1 :])
                break
            print(f"[{block} {index}/{len(remaining)}] {row['case_id']}", flush=True)
            result = run_case(row)
            results.append(result)
            write_ledgers(results, checkpoints, run_meta)
            if result["status"] != "success":
                checkpoints[block] = f"failed: {row['case_id']} {result['failure_category']}"
                results.extend(skipped_result(item, "block_safety_stop") for item in remaining[index:])
                break
        else:
            checkpoints[block] = "passed"
        write_ledgers(results, checkpoints, run_meta)
    run_meta["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    write_ledgers(results, checkpoints, run_meta)
    counts = {
        status: sum(result["status"] == status for result in results)
        for status in ("success", "failed", "skipped")
    }
    print(json.dumps(counts), flush=True)
    raise SystemExit(1 if counts["failed"] else 0)


if __name__ == "__main__":
    main()
