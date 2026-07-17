#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
BASE_SCRIPT = REPO_ROOT / "scratch/20260715-routing-strategy-validation/analyze_results.py"
spec = importlib.util.spec_from_file_location("routing_analysis", BASE_SCRIPT)
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def main() -> None:
    rows = json.loads((ROOT / "matrix.yaml").read_text(encoding="utf-8"))["cases"]
    ledger = json.loads((ROOT / "run-ledger.json").read_text(encoding="utf-8"))
    status = {item["case_id"]: item for item in ledger["results"]}
    analysis.PACKAGE_ROOT = ROOT
    summaries = [analysis.summarize(row, status) for row in rows]
    out = ROOT / "analysis"
    out.mkdir(exist_ok=True)
    with (out / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    lines = ["# Routing Latency Follow-up Results", "",
             "| case | paths | inversions | mean FCT us | p95 FCT us |",
             "|---|---:|---:|---:|---:|"]
    for item in summaries:
        lines.append(f"| {item['case_id']} | {item['unique_branch_ports']} | "
                     f"{item['psn_adjacent_inversions']} | {item['mean_task_duration_us']} | "
                     f"{item['p95_task_duration_us']} |")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
