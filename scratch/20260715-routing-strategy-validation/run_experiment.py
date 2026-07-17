#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parents[1]
MATRIX = json.loads((PACKAGE_ROOT / "matrix.yaml").read_text(encoding="utf-8"))["cases"]
PATH_TRIPLE = re.compile(r"\[\s*(\d+)\s*\]\[\s*(\d+)\s*\]\[\s*(\d+)\s*\]")


def unique_packet_records(case_dir: Path) -> list[tuple[str, str, str]]:
    records: list[tuple[str, str, str]] = []
    seen = set()
    for trace in sorted((case_dir / "runlog").glob("AllPacketTrace_PKT_node_0.tr")):
        lines = trace.read_text(encoding="utf-8", errors="replace").splitlines()
        for index, line in enumerate(lines):
            if not line.startswith("Uid:") or index + 2 >= len(lines):
                continue
            record = (line.strip(), lines[index + 1].strip(), lines[index + 2].strip())
            if record not in seen:
                seen.add(record)
                records.append(record)
    return records


def branch_ports(case_dir: Path) -> list[int]:
    ports = []
    for _, path, _ in unique_packet_records(case_dir):
        for recv_port, node, send_port in PATH_TRIPLE.findall(path):
            if int(node) == 2:
                ports.append(int(send_port))
                break
    return ports


def semantic_gate(results: list[dict]) -> tuple[bool, str]:
    by_id = {item["case_id"]: item for item in results}
    required = {"sem-flow-short", "sem-packet-short", "sem-flow-all", "sem-packet-all"}
    if not required.issubset(by_id):
        return False, "semantic cases did not all execute"
    if any(by_id[name]["status"] != "success" for name in required):
        return False, "one or more semantic cases failed to run"
    ports = {name: branch_ports(PACKAGE_ROOT / "cases" / name) for name in required}
    if any(not values for values in ports.values()):
        return False, f"missing semantic path evidence: {ports}"
    if set(ports["sem-flow-short"]) != {1} or set(ports["sem-packet-short"]) != {1}:
        return False, f"shortest-only cases escaped shortest port: {ports}"
    if len(set(ports["sem-flow-all"])) != 1:
        return False, f"per-flow all-path case changed path: {ports['sem-flow-all']}"
    if not ({2, 3} & set(ports["sem-packet-all"])):
        return False, f"per-packet all-path case did not use non-shortest paths: {ports['sem-packet-all']}"
    return True, json.dumps({name: sorted(set(values)) for name, values in ports.items()})


def write_ledger(results: list[dict], checkpoint: str) -> None:
    result_by_id = {item["case_id"]: item for item in results}
    lines = [
        "# Run Ledger", "", "- branch: `codex/routing-modes`",
        "- checkpoint_policy: semantic hard failure stops; performance mismatch continues",
        "- execution: sequential-only", f"- semantic_checkpoint: {checkpoint}", "",
        "| case | block | status | return code | duration (s) | artifacts |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in MATRIX:
        result = result_by_id.get(row["case_id"], {})
        lines.append(
            f"| {row['case_id']} | {row['block_id']} | {result.get('status', 'pending')} | "
            f"{result.get('return_code', '')} | {result.get('duration_s', '')} | "
            f"{', '.join(result.get('artifacts', []))} |"
        )
    (PACKAGE_ROOT / "run-ledger.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (PACKAGE_ROOT / "run-ledger.json").write_text(
        json.dumps({"semantic_checkpoint": checkpoint, "results": results}, indent=2) + "\n",
        encoding="utf-8",
    )


def run_case(row: dict) -> dict:
    case_dir = PACKAGE_ROOT / row["case_dir"]
    relative = case_dir.relative_to(REPO_ROOT)
    for directory in (case_dir / "runlog", case_dir / "output"):
        if directory.exists():
            for path in directory.rglob("*"):
                if path.is_file():
                    path.unlink()
    command = [
        sys.executable, str(REPO_ROOT / "ns3"), "run", "--no-build",
        f"scratch/ub-quick-example --case-path={relative}",
    ]
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command, cwd=REPO_ROOT, capture_output=True, text=True,
            timeout=int(os.environ.get("OPENUSIM_CASE_TIMEOUT", "180")), check=False,
        )
        return_code = completed.returncode
        output = completed.stdout + completed.stderr
        status = "success" if return_code == 0 else "failed"
    except subprocess.TimeoutExpired as error:
        return_code = 124
        output = (error.stdout or "") + (error.stderr or "") + "\nTIMEOUT\n"
        status = "failed"
    (case_dir / "console.log").write_text(output, encoding="utf-8")
    artifacts = []
    for name in ("console.log", "runlog", "output/task_statistics.csv", "output/throughput.csv"):
        if (case_dir / name).exists():
            artifacts.append(name)
    return {
        "case_id": row["case_id"], "block_id": row["block_id"], "status": status,
        "return_code": return_code, "duration_s": round(time.monotonic() - started, 3),
        "command": " ".join(command), "artifacts": artifacts,
    }


def main() -> None:
    results: list[dict] = []
    checkpoint = "pending"
    semantic_rows = [row for row in MATRIX if row["block_id"] == "semantic"]
    remaining_rows = [row for row in MATRIX if row["block_id"] != "semantic"]
    for index, row in enumerate(semantic_rows, start=1):
        print(f"[semantic {index}/{len(semantic_rows)}] {row['case_id']}", flush=True)
        results.append(run_case(row))
        write_ledger(results, checkpoint)
    passed, detail = semantic_gate(results)
    checkpoint = f"{'passed' if passed else 'failed'}: {detail}"
    write_ledger(results, checkpoint)
    print(f"semantic checkpoint {checkpoint}", flush=True)
    if not passed:
        raise SystemExit(2)
    for index, row in enumerate(remaining_rows, start=1):
        print(f"[matrix {index}/{len(remaining_rows)}] {row['case_id']}", flush=True)
        results.append(run_case(row))
        write_ledger(results, checkpoint)
    failures = [item for item in results if item["status"] != "success"]
    print(f"completed={len(results)} failures={len(failures)}", flush=True)
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
