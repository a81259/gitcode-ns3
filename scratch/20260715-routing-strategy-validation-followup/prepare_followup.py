#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
BASE_SCRIPT = REPO_ROOT / "scratch/20260715-routing-strategy-validation/prepare_experiment.py"
spec = importlib.util.spec_from_file_location("routing_prepare", BASE_SCRIPT)
prep = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = prep
spec.loader.exec_module(prep)

CASES = [
    prep.case("spray-latency-flow-hash", "spray-latency", "control",
              "micro-extreme-equal", "latency-small", "PER_FLOW_SHORTEST_PATHS", "HASH64",
              prediction="Short flows remain on one low-delay path."),
    prep.case("spray-latency-packet-hash", "spray-latency", "treatment",
              "micro-extreme-equal", "latency-small", "PER_PACKET_SHORTEST_PATHS", "HASH64",
              prediction="Packet spray uses the 20 us path and increases short-flow tail latency."),
    prep.case("all-latency-short", "all-latency", "control",
              "micro-extreme-mixed", "latency-small", "PER_PACKET_SHORTEST_PATHS", "HASH64",
              prediction="Short flows use only the low-delay shortest path."),
    prep.case("all-latency-all", "all-latency", "treatment",
              "micro-extreme-mixed", "latency-small", "PER_PACKET_ALL_PATHS", "HASH64",
              prediction="All-path routing uses 20 us detours and increases short-flow tail latency."),
]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def main() -> None:
    prep.PACKAGE_ROOT = ROOT
    prep.CASES_ROOT = ROOT / "cases"
    prep.CASES = CASES
    write(ROOT / "experiment-plan.md", """# Routing Latency Follow-up Plan

## Trigger

The original 8 MiB unequal-delay treatments remained bandwidth-dominated. This follow-up is a
separate pre-registered matrix and does not rewrite the original result.

## Claim

For sparse 16 KiB short flows, a 20 us candidate path exposes packet-spray and all-path tail-latency
costs that aggregate bandwidth hides in long-flow tests.

## Controls and Treatments

- `spray-latency`: per-flow HASH64 control versus per-packet HASH64 treatment on three equal-metric paths.
- `all-latency`: per-packet shortest-path control versus per-packet all-path treatment with two non-shortest detours.

## Fixed Controls

RTP, CBFC, 400 Gbps core links, 64 tasks of 16 KiB spaced by 100 us, on-demand TP creation,
detailed observability, sequential execution, and unchanged hash implementation.

## Prediction and Falsification

Treatments should use the delayed path and increase p95 task duration. The claim is falsified if
the delayed path is used but p95 does not increase.

## Checkpoint Policy

Continue the complete four-case matrix unless a case fails to execute.
""")
    rows = []
    for current in CASES:
        row = asdict(current)
        row.update({
            "case_dir": f"cases/{current.case_id}", "fixed_controls": "See experiment-plan.md",
            "metric_checks": ["path_usage", "task_completion", "psn_order"],
            "expected_artifacts": ["console.log", "runlog/", "output/task_statistics.csv"],
            "parallel_group": "sequential-only", "checkpoint_ids": [],
        })
        rows.append(row)
    write(ROOT / "matrix.yaml", json.dumps({"cases": rows}, indent=2))
    write(ROOT / "command-manifest.yaml", json.dumps({
        "execution_policy": "sequential-only",
        "cases": [{"case_id": c.case_id,
                   "command": f"python3.12 ./ns3 run --no-build 'scratch/ub-quick-example --case-path=scratch/20260715-routing-strategy-validation-followup/cases/{c.case_id}'"}
                  for c in CASES],
    }, indent=2))
    write(ROOT / "run-ledger.md", "# Run Ledger\n\nAll cases pending.\n")
    for current in CASES:
        print("prepare", current.case_id, flush=True)
        prep.prepare_case(current)


if __name__ == "__main__":
    main()
