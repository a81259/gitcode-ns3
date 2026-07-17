#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
BASE_SCRIPT = REPO_ROOT / "scratch/20260715-routing-strategy-validation/run_experiment.py"
spec = importlib.util.spec_from_file_location("routing_run", BASE_SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def main() -> None:
    rows = json.loads((ROOT / "matrix.yaml").read_text(encoding="utf-8"))["cases"]
    runner.PACKAGE_ROOT = ROOT
    runner.MATRIX = rows
    results = []
    for index, row in enumerate(rows, start=1):
        print(f"[{index}/{len(rows)}] {row['case_id']}", flush=True)
        results.append(runner.run_case(row))
        runner.write_ledger(results, "not-applicable")
    if any(item["status"] != "success" for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
