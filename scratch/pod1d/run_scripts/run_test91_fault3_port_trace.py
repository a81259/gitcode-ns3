#!/usr/bin/env python3
"""Run isolated standard/fault3 test91 simulations with port Tx tracing enabled."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
POD_ROOT = SCRIPT_DIR.parent
REPO_ROOT = POD_ROOT.parents[1]
SOURCE_ROOT = POD_ROOT / "test91_dp_reduce_scatter"
OBSERVATION_ROOT = POD_ROOT / "test91_porttrace_fault3_bidirectional"
ANALYZER = SCRIPT_DIR / "analyze_test91_fault3_l1_l2_bidirectional.py"

CASES = (
    ("标准拓扑", "case01_standard", "standard"),
    ("故障3（L1–L2 分布式 Port Down，每个 POD 1 根）", "case06_pod1_18_l1_first_l2_port_down", "fault3"),
)

TRACE_GLOBALS = {
    "UB_TRACE_ENABLE": "true",
    "UB_TASK_TRACE_ENABLE": "false",
    "UB_PACKET_TRACE_ENABLE": "false",
    "UB_PORT_TRACE_ENABLE": "true",
    "UB_QUEUE_TRACE_ENABLE": "false",
    "UB_FLOW_CONTROL_TRACE_ENABLE": "false",
    "UB_CONGESTION_CONTROL_TRACE_ENABLE": "false",
    "UB_RECORD_PKT_TRACE": "false",
    "UB_PARSE_TRACE_ENABLE": "false",
    "UB_PORT_BUCKET_TRACE_ENABLE": "true",
}
TRACE_FILTER_GLOBALS = {
    "UB_PORT_TRACE_NODE_ID_MIN": "2736",
    "UB_PORT_TRACE_NODE_ID_MAX": "3287",
    "UB_PORT_TRACE_PORT_ID_MIN": "0",
    "UB_PORT_TRACE_PORT_ID_MAX": "170",
    "UB_PORT_TRACE_BUCKET_NS": "250",
}
EXCLUDED_ENTRIES = {"output", "runlog"}


def rewrite_trace_globals(attribute_path: Path) -> None:
    text = attribute_path.read_text(encoding="utf-8")
    for name, value in TRACE_GLOBALS.items():
        pattern = rf'(?m)^global {re.escape(name)} "(?:true|false)"$'
        text, replaced = re.subn(pattern, f'global {name} "{value}"', text)
        if replaced == 0:
            text += f'\nglobal {name} "{value}"\n'
        elif replaced != 1:
            raise ValueError(f"expected at most one {name} setting in {attribute_path}, got {replaced}")
    for name, value in TRACE_FILTER_GLOBALS.items():
        pattern = rf'(?m)^global {re.escape(name)} "\\d+"$'
        text, replaced = re.subn(pattern, f'global {name} "{value}"', text)
        if replaced == 0:
            text += f'\nglobal {name} "{value}"\n'
        elif replaced != 1:
            raise ValueError(f"expected at most one {name} setting in {attribute_path}, got {replaced}")
    attribute_path.write_text(text, encoding="utf-8")


def prepare_cases() -> list[tuple[str, str, Path]]:
    if OBSERVATION_ROOT.exists():
        raise FileExistsError(
            f"refusing to overwrite existing observation directory: {OBSERVATION_ROOT}; "
            "use its existing traces or move it aside explicitly"
        )

    prepared: list[tuple[str, str, Path]] = []
    for title, source_case, target_name in CASES:
        source = SOURCE_ROOT / source_case
        target = OBSERVATION_ROOT / target_name
        if not source.is_dir():
            raise FileNotFoundError(f"missing source case: {source}")
        target.mkdir(parents=True, exist_ok=False)
        for entry in source.iterdir():
            if entry.name in EXCLUDED_ENTRIES:
                continue
            destination = target / entry.name
            if entry.is_dir():
                shutil.copytree(entry, destination)
            else:
                shutil.copy2(entry, destination)
        rewrite_trace_globals(target / "network_attribute.txt")
        prepared.append((title, target_name, target))
    return prepared


def launch(case_path: Path, log_path: Path) -> tuple[subprocess.Popen[str], object, float]:
    handle = log_path.open("w", encoding="utf-8")
    relative_case = case_path.relative_to(REPO_ROOT).as_posix()
    process = subprocess.Popen(
        ["python3.12", "./ns3", "run", "--no-build", f"scratch/ub-quick-example --case-path={relative_case}"],
        cwd=REPO_ROOT,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return process, handle, time.monotonic()


def run_cases(prepared: list[tuple[str, str, Path]], log_dir: Path, parallel: int) -> None:
    pending = prepared[:]
    active: list[tuple[str, str, Path, subprocess.Popen[str], object, float, Path]] = []
    failed: list[str] = []
    while pending or active:
        while pending and len(active) < parallel:
            title, target_name, case_path = pending.pop(0)
            log_path = log_dir / f"{target_name}.log"
            process, handle, started = launch(case_path, log_path)
            active.append((title, target_name, case_path, process, handle, started, log_path))
            print(f"[{datetime.now():%H:%M:%S}] START {title}", flush=True)

        time.sleep(5)
        remaining: list[tuple[str, str, Path, subprocess.Popen[str], object, float, Path]] = []
        for title, target_name, case_path, process, handle, started, log_path in active:
            result = process.poll()
            if result is None:
                remaining.append((title, target_name, case_path, process, handle, started, log_path))
                continue
            handle.close()
            elapsed = time.monotonic() - started
            trace_dir = case_path / "runlog"
            trace_size = sum(path.stat().st_size for path in trace_dir.glob("PortTrace_*.tr")) if trace_dir.is_dir() else 0
            print(
                f"[{datetime.now():%H:%M:%S}] DONE {'OK' if result == 0 else 'FAIL'} {title} "
                f"rc={result} elapsed={elapsed:.1f}s port_trace_bytes={trace_size}",
                flush=True,
            )
            if result != 0:
                failed.append(f"{title} (rc={result}; log={log_path})")
        active = remaining
    if failed:
        raise RuntimeError("port-trace simulation failure(s): " + "; ".join(failed))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parallel", type=int, default=2, help="maximum concurrent simulations (default: 2)")
    parser.add_argument("--bin-us", type=float, default=0.25, help="time bucket width in microseconds (default: 0.25)")
    parser.add_argument("--prepare-only", action="store_true", help="create the isolated cases without running them")
    parser.add_argument(
        "--label",
        default=f"test91_fault3_porttrace_{datetime.now():%Y%m%d_%H%M%S}",
        help="new directory under batch_run_logs",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.parallel < 1:
        raise ValueError("--parallel must be at least 1")
    if args.bin_us <= 0:
        raise ValueError("--bin-us must be positive")
    if not ANALYZER.is_file():
        raise FileNotFoundError(f"missing analyzer: {ANALYZER}")

    log_dir = SCRIPT_DIR / "batch_run_logs" / args.label
    log_dir.mkdir(parents=True, exist_ok=False)
    prepared = prepare_cases()
    if args.prepare_only:
        print(f"observation_root={OBSERVATION_ROOT}")
        print(f"results={log_dir}")
        return 0
    run_cases(prepared, log_dir, args.parallel)

    analysis = subprocess.run(
        [
            "python3.12",
            str(ANALYZER),
            "--standard-dir",
            str(OBSERVATION_ROOT / "standard"),
            "--fault3-dir",
            str(OBSERVATION_ROOT / "fault3"),
            "--out-dir",
            str(log_dir),
            "--bin-us",
            str(args.bin_us),
        ],
        cwd=REPO_ROOT,
        check=False,
    )
    if analysis.returncode != 0:
        return analysis.returncode
    print(f"observation_root={OBSERVATION_ROOT}")
    print(f"results={log_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
