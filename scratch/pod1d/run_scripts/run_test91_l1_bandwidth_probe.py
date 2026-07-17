#!/usr/bin/env python3
"""Measure instantaneous lower-side and upper-side L1 Tx bandwidth for test91.

The source workload is test91 delay-jitter replica seed 202.  Each of the five
topologies is copied into an isolated probe directory, run with 500 ns
port-Tx byte buckets, then summarized without modifying the source cases.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import shutil
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
POD_ROOT = SCRIPT_DIR.parent
REPO_ROOT = POD_ROOT.parents[1]
DEFAULT_SOURCE_ROOT = (
    POD_ROOT
    / "test91_92_delay_jitter_three_groups"
    / "group_seed202"
    / "test91_dp_reduce_scatter"
)
DEFAULT_PROBE_ROOT = POD_ROOT / "test91_l1_bandwidth_probe_seed202"

HOST_START, HOST_END = 0, 1367
LOWER_START, LOWER_END = 1368, 2735
L1_START, L1_END = 2736, 3191
L2_START, L2_END = 3192, 3287
BUCKET_NS = 500
RNG_RUN = 202

CASES = (
    ("标准拓扑", "case01_standard", "standard"),
    ("故障1（L1–L2 单链路 Lane Down）", "case04_l1_l2_lane_down", "fault1_lane_down"),
    ("故障2（L1–L2 单链路 Port Down）", "case05_l1_l2_port_down", "fault2_port_down"),
    ("故障3（L1–L2 分布式 Port Down，每个 POD 1 根）", "case06_pod1_18_l1_first_l2_port_down", "fault3_distributed"),
    ("故障4（L1–L2 集中式 Port Down）", "case07_pod1_4l1_full_1l1_half_l2_port_down", "fault4_concentrated"),
)

TRACE_GLOBALS = {
    "UB_TRACE_ENABLE": "true",
    "UB_TASK_TRACE_ENABLE": "true",
    "UB_PACKET_TRACE_ENABLE": "false",
    "UB_PORT_TRACE_ENABLE": "true",
    "UB_QUEUE_TRACE_ENABLE": "false",
    "UB_FLOW_CONTROL_TRACE_ENABLE": "false",
    "UB_CONGESTION_CONTROL_TRACE_ENABLE": "false",
    "UB_RECORD_PKT_TRACE": "false",
    "UB_PARSE_TRACE_ENABLE": "true",
    "UB_PORT_BUCKET_TRACE_ENABLE": "true",
    "UB_PORT_TRACE_NODE_ID_MIN": str(LOWER_START),
    "UB_PORT_TRACE_NODE_ID_MAX": str(L1_END),
    "UB_PORT_TRACE_PORT_ID_MIN": "0",
    "UB_PORT_TRACE_PORT_ID_MAX": "170",
    "UB_PORT_TRACE_BUCKET_NS": str(BUCKET_NS),
}


@dataclass(frozen=True)
class PortInfo:
    category: str
    capacity_gbps: float


def set_global(text: str, name: str, value: str) -> str:
    pattern = rf'(?m)^global {re.escape(name)} ".*"$'
    replacement = f'global {name} "{value}"'
    text, replacements = re.subn(pattern, replacement, text)
    if replacements == 0:
        if not text.endswith("\n"):
            text += "\n"
        text += replacement + "\n"
    elif replacements != 1:
        raise ValueError(f"expected one or zero {name} global settings, found {replacements}")
    return text


def configure_trace_globals(attribute_path: Path) -> None:
    text = attribute_path.read_text(encoding="utf-8")
    for name, value in TRACE_GLOBALS.items():
        text = set_global(text, name, value)
    attribute_path.write_text(text, encoding="utf-8")


def is_access_l1_link(node1: int, node2: int) -> bool:
    return (in_range(node1, LOWER_START, LOWER_END) and in_range(node2, L1_START, L1_END)) or (
        in_range(node2, LOWER_START, LOWER_END) and in_range(node1, L1_START, L1_END)
    )


def is_host_access_link(node1: int, node2: int) -> bool:
    return (in_range(node1, HOST_START, HOST_END) and in_range(node2, LOWER_START, LOWER_END)) or (
        in_range(node2, HOST_START, HOST_END) and in_range(node1, LOWER_START, LOWER_END)
    )


def rewrite_link_bandwidths(
    topology_path: Path, access_l1_bandwidth_gbps: float | None, host_access_bandwidth_gbps: float | None
) -> None:
    if access_l1_bandwidth_gbps is None and host_access_bandwidth_gbps is None:
        return
    with topology_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    required = {"nodeId1", "nodeId2", "bandwidth"}
    if required - set(fields):
        raise ValueError(f"{topology_path} missing required fields: {required - set(fields)}")
    access_l1_changed = 0
    host_access_changed = 0
    for row in rows:
        node1, node2 = int(row["nodeId1"]), int(row["nodeId2"])
        if access_l1_bandwidth_gbps is not None and is_access_l1_link(node1, node2):
            row["bandwidth"] = f"{access_l1_bandwidth_gbps:g}Gbps"
            access_l1_changed += 1
        if host_access_bandwidth_gbps is not None and is_host_access_link(node1, node2):
            row["bandwidth"] = f"{host_access_bandwidth_gbps:g}Gbps"
            host_access_changed += 1
    if access_l1_bandwidth_gbps is not None and access_l1_changed != 32832:
        raise ValueError(f"expected 32832 Access-L1 links in {topology_path}, changed {access_l1_changed}")
    if host_access_bandwidth_gbps is not None and host_access_changed != 1368:
        raise ValueError(f"expected 1368 Host-Access links in {topology_path}, changed {host_access_changed}")
    write_csv(topology_path, fields, rows)


def copy_case(
    source: Path,
    target: Path,
    access_l1_bandwidth_gbps: float | None,
    host_access_bandwidth_gbps: float | None,
) -> None:
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {target}")
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("output", "runlog"))
    rewrite_link_bandwidths(target / "topology.csv", access_l1_bandwidth_gbps, host_access_bandwidth_gbps)
    configure_trace_globals(target / "network_attribute.txt")


def prepare_cases(
    source_root: Path,
    probe_root: Path,
    access_l1_bandwidth_gbps: float | None,
    host_access_bandwidth_gbps: float | None,
) -> list[tuple[str, str, Path]]:
    if probe_root.exists():
        raise FileExistsError(f"refusing to overwrite existing probe root {probe_root}")
    prepared: list[tuple[str, str, Path]] = []
    for title, source_name, key in CASES:
        source = source_root / source_name
        if not source.is_dir():
            raise FileNotFoundError(f"missing source case: {source}")
        target = probe_root / key
        copy_case(source, target, access_l1_bandwidth_gbps, host_access_bandwidth_gbps)
        prepared.append((title, key, target))
    return prepared


def prepared_cases(probe_root: Path) -> list[tuple[str, str, Path]]:
    prepared: list[tuple[str, str, Path]] = []
    for title, _, key in CASES:
        case_dir = probe_root / key
        if not (case_dir / "traffic.csv").is_file():
            raise FileNotFoundError(f"missing prepared case: {case_dir}")
        prepared.append((title, key, case_dir))
    return prepared


def launch(case_dir: Path, log_path: Path) -> tuple[subprocess.Popen[str], object, float]:
    handle = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            "python3.12",
            "./ns3",
            "run",
            "--no-build",
            f"scratch/ub-quick-example --case-path={case_dir.relative_to(REPO_ROOT).as_posix()} --rng-run={RNG_RUN}",
        ],
        cwd=REPO_ROOT,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return process, handle, time.monotonic()


def run_cases(cases: list[tuple[str, str, Path]], log_dir: Path, parallel: int) -> None:
    pending = list(cases)
    active: list[tuple[str, str, Path, subprocess.Popen[str], object, float, Path]] = []
    failures: list[str] = []
    while pending or active:
        while pending and len(active) < parallel:
            title, key, case_dir = pending.pop(0)
            log_path = log_dir / f"{key}.log"
            process, handle, started = launch(case_dir, log_path)
            active.append((title, key, case_dir, process, handle, started, log_path))
            print(f"[{datetime.now():%H:%M:%S}] START {title}", flush=True)

        time.sleep(5)
        remaining = []
        for title, key, case_dir, process, handle, started, log_path in active:
            return_code = process.poll()
            if return_code is None:
                remaining.append((title, key, case_dir, process, handle, started, log_path))
                continue
            handle.close()
            trace = case_dir / "runlog" / "PortTxBucketTrace.csv"
            valid = return_code == 0 and trace.is_file() and trace.stat().st_size > 100
            print(
                f"[{datetime.now():%H:%M:%S}] DONE {title} rc={return_code} "
                f"elapsed={time.monotonic() - started:.1f}s trace_bytes={trace.stat().st_size if trace.exists() else 0}",
                flush=True,
            )
            if not valid:
                failures.append(f"{title}: rc={return_code}, trace={trace}, log={log_path}")
        active = remaining
    if failures:
        raise RuntimeError("probe failures: " + "; ".join(failures))


def parse_gbps(raw: str) -> float:
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)Gbps", raw.strip())
    if match is None:
        raise ValueError(f"unsupported bandwidth value: {raw!r}")
    return float(match.group(1))


def in_range(node_id: int, lower: int, upper: int) -> bool:
    return lower <= node_id <= upper


def category_ports(topology_path: Path) -> dict[tuple[int, int], PortInfo]:
    ports: dict[tuple[int, int], PortInfo] = {}
    with topology_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            node1, port1 = int(row["nodeId1"]), int(row["portId1"])
            node2, port2 = int(row["nodeId2"]), int(row["portId2"])
            capacity = parse_gbps(row["bandwidth"])
            endpoint1, endpoint2 = (node1, port1), (node2, port2)
            node1_lower = in_range(node1, LOWER_START, LOWER_END)
            node2_lower = in_range(node2, LOWER_START, LOWER_END)
            node1_l1 = in_range(node1, L1_START, L1_END)
            node2_l1 = in_range(node2, L1_START, L1_END)
            node1_l2 = in_range(node1, L2_START, L2_END)
            node2_l2 = in_range(node2, L2_START, L2_END)
            if node1_lower and node2_l1:
                ports[endpoint1] = PortInfo("LOWER_TO_L1", capacity)
                ports[endpoint2] = PortInfo("L1_TO_LOWER", capacity)
            elif node2_lower and node1_l1:
                ports[endpoint2] = PortInfo("LOWER_TO_L1", capacity)
                ports[endpoint1] = PortInfo("L1_TO_LOWER", capacity)
            elif node1_l1 and node2_l2:
                ports[endpoint1] = PortInfo("L1_TO_L2", capacity)
            elif node2_l1 and node1_l2:
                ports[endpoint2] = PortInfo("L1_TO_L2", capacity)
    if not ports:
        raise ValueError(f"no selected hierarchy ports found in {topology_path}")
    return ports


def percentile(values: Iterable[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[math.ceil(fraction * len(ordered)) - 1]


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def analyze_case(title: str, key: str, case_dir: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    ports = category_ports(case_dir / "topology.csv")
    category_port_list: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for port, info in ports.items():
        category_port_list[info.category].append(port)
    bucket_bytes: dict[tuple[int, tuple[int, int]], int] = defaultdict(int)
    trace_path = case_dir / "runlog" / "PortTxBucketTrace.csv"
    max_bucket = -1
    with trace_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            bucket = int(row["bucket_index"])
            start, end = int(row["bucket_start_ns"]), int(row["bucket_end_ns"])
            if start != bucket * BUCKET_NS or end - start != BUCKET_NS:
                raise ValueError(f"unexpected bucket bounds in {trace_path}: {row}")
            port = (int(row["node_id"]), int(row["port_id"]))
            if port in ports:
                bucket_bytes[(bucket, port)] += int(row["tx_bytes"])
                max_bucket = max(max_bucket, bucket)
    if max_bucket < 0:
        raise ValueError(f"no selected port Tx entries in {trace_path}")

    bucket_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    for category in ("LOWER_TO_L1", "L1_TO_LOWER", "L1_TO_L2"):
        selected_ports = sorted(category_port_list[category])
        total_capacity = sum(ports[port].capacity_gbps for port in selected_ports)
        rows_for_category: list[dict[str, object]] = []
        for bucket in range(max_bucket + 1):
            byte_values = [bucket_bytes[(bucket, port)] for port in selected_ports]
            link_gbps = [value * 8.0 / BUCKET_NS for value in byte_values]
            active = [value for value in link_gbps if value > 0]
            aggregate_gbps = sum(link_gbps)
            row = {
                "case": key,
                "title": title,
                "category": category,
                "bucket_index": bucket,
                "bucket_start_us": f"{bucket * BUCKET_NS / 1000:.3f}",
                "bucket_end_us": f"{(bucket + 1) * BUCKET_NS / 1000:.3f}",
                "bucket_width_ns": BUCKET_NS,
                "links": len(selected_ports),
                "capacity_gbps": f"{total_capacity:.3f}",
                "tx_bytes": sum(byte_values),
                "aggregate_gbps": f"{aggregate_gbps:.6f}",
                "aggregate_utilization_percent": f"{aggregate_gbps / total_capacity * 100:.9f}",
                "active_links": len(active),
                "active_link_percent": f"{len(active) / len(selected_ports) * 100:.9f}",
                "mean_active_link_gbps": f"{sum(active) / len(active) if active else 0:.6f}",
                "p95_active_link_gbps": f"{percentile(active, 0.95):.6f}",
                "max_link_gbps": f"{max(link_gbps):.6f}",
                "max_link_utilization_percent": f"{max(link_gbps[port] / ports[selected_ports[port]].capacity_gbps for port in range(len(selected_ports))) * 100:.9f}",
            }
            rows_for_category.append(row)
            bucket_rows.append(row)

        aggregate_values = [float(row["aggregate_gbps"]) for row in rows_for_category]
        utilization_values = [float(row["aggregate_utilization_percent"]) for row in rows_for_category]
        active_values = [int(row["active_links"]) for row in rows_for_category]
        summary_rows.append(
            {
                "case": key,
                "title": title,
                "category": category,
                "bucket_width_ns": BUCKET_NS,
                "buckets": len(rows_for_category),
                "links": len(selected_ports),
                "capacity_gbps": f"{total_capacity:.3f}",
                "total_tx_bytes": sum(int(row["tx_bytes"]) for row in rows_for_category),
                "mean_aggregate_gbps": f"{sum(aggregate_values) / len(aggregate_values):.6f}",
                "peak_aggregate_gbps": f"{max(aggregate_values):.6f}",
                "mean_utilization_percent": f"{sum(utilization_values) / len(utilization_values):.9f}",
                "peak_utilization_percent": f"{max(utilization_values):.9f}",
                "mean_active_links": f"{sum(active_values) / len(active_values):.6f}",
                "peak_active_links": max(active_values),
                "peak_active_link_percent": f"{max(active_values) / len(selected_ports) * 100:.9f}",
                "peak_one_link_gbps": f"{max(float(row['max_link_gbps']) for row in rows_for_category):.6f}",
                "peak_one_link_utilization_percent": f"{max(float(row['max_link_utilization_percent']) for row in rows_for_category):.9f}",
            }
        )
    return bucket_rows, summary_rows


def analyze_all(cases: list[tuple[str, str, Path]], log_dir: Path) -> None:
    bucket_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    for title, key, case_dir in cases:
        by_bucket, summary = analyze_case(title, key, case_dir)
        bucket_rows.extend(by_bucket)
        summary_rows.extend(summary)
    write_csv(
        log_dir / "l1_hierarchy_instantaneous_bandwidth_500ns.csv",
        [
            "case", "title", "category", "bucket_index", "bucket_start_us", "bucket_end_us", "bucket_width_ns",
            "links", "capacity_gbps", "tx_bytes", "aggregate_gbps", "aggregate_utilization_percent",
            "active_links", "active_link_percent", "mean_active_link_gbps", "p95_active_link_gbps",
            "max_link_gbps", "max_link_utilization_percent",
        ],
        bucket_rows,
    )
    write_csv(
        log_dir / "l1_hierarchy_bandwidth_summary.csv",
        [
            "case", "title", "category", "bucket_width_ns", "buckets", "links", "capacity_gbps", "total_tx_bytes",
            "mean_aggregate_gbps", "peak_aggregate_gbps", "mean_utilization_percent", "peak_utilization_percent",
            "mean_active_links", "peak_active_links", "peak_active_link_percent", "peak_one_link_gbps",
            "peak_one_link_utilization_percent",
        ],
        summary_rows,
    )
    performance_rows: list[dict[str, object]] = []
    baseline: dict[str, object] | None = None
    for title, key, case_dir in cases:
        stats_path = case_dir / "output" / "task_statistics.csv"
        if not stats_path.is_file():
            raise FileNotFoundError(f"missing task statistics: {stats_path}")
        with stats_path.open(encoding="utf-8-sig", newline="") as handle:
            statistics = list(csv.DictReader(handle))
        completes = [float(row["taskCompletesTime(us)"]) for row in statistics]
        if not completes:
            raise ValueError(f"empty task statistics: {stats_path}")
        row = {
            "case": key,
            "title": title,
            "tasks": len(completes),
            "avg_complete_us": f"{sum(completes) / len(completes):.6f}",
            "max_complete_us": f"{max(completes):.6f}",
            "avg_delta_vs_standard_percent": "",
            "max_delta_vs_standard_percent": "",
        }
        if key == "standard":
            baseline = row
        performance_rows.append(row)
    if baseline is None:
        raise ValueError("standard case is required for performance comparison")
    baseline_avg = float(baseline["avg_complete_us"])
    baseline_max = float(baseline["max_complete_us"])
    for row in performance_rows:
        row["avg_delta_vs_standard_percent"] = f"{(float(row['avg_complete_us']) / baseline_avg - 1) * 100:.6f}"
        row["max_delta_vs_standard_percent"] = f"{(float(row['max_complete_us']) / baseline_max - 1) * 100:.6f}"
    write_csv(
        log_dir / "task_completion_summary.csv",
        [
            "case", "title", "tasks", "avg_complete_us", "max_complete_us",
            "avg_delta_vs_standard_percent", "max_delta_vs_standard_percent",
        ],
        performance_rows,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parallel", type=int, default=5)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--probe-root", type=Path, default=DEFAULT_PROBE_ROOT)
    parser.add_argument(
        "--access-l1-bandwidth-gbps",
        type=float,
        default=None,
        help="replace every Access-L1 link bandwidth in isolated copied cases",
    )
    parser.add_argument(
        "--host-access-bandwidth-gbps",
        type=float,
        default=None,
        help="replace every Host-Access link bandwidth in isolated copied cases",
    )
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--run-prepared", action="store_true")
    parser.add_argument("--analyze-only", action="store_true", help="analyze already generated trace and task files")
    parser.add_argument(
        "--label",
        default=f"test91_l1_bandwidth_probe_{datetime.now():%Y%m%d_%H%M%S}",
        help="new output directory under batch_run_logs",
    )
    args = parser.parse_args()
    args.source_root = args.source_root.resolve()
    args.probe_root = args.probe_root.resolve()
    if args.parallel < 1:
        raise ValueError("--parallel must be at least 1")
    if args.access_l1_bandwidth_gbps is not None and args.access_l1_bandwidth_gbps <= 0:
        raise ValueError("--access-l1-bandwidth-gbps must be positive")
    if args.host_access_bandwidth_gbps is not None and args.host_access_bandwidth_gbps <= 0:
        raise ValueError("--host-access-bandwidth-gbps must be positive")
    if args.prepare_only and args.run_prepared:
        raise ValueError("--prepare-only and --run-prepared cannot be combined")
    if args.prepare_only and args.analyze_only:
        raise ValueError("--prepare-only and --analyze-only cannot be combined")
    if args.analyze_only and not args.run_prepared:
        raise ValueError("--analyze-only requires --run-prepared")
    log_dir = SCRIPT_DIR / "batch_run_logs" / args.label
    log_dir.mkdir(parents=True, exist_ok=False)
    cases = (
        prepared_cases(args.probe_root)
        if args.run_prepared
        else prepare_cases(
            args.source_root,
            args.probe_root,
            args.access_l1_bandwidth_gbps,
            args.host_access_bandwidth_gbps,
        )
    )
    print(f"source_root={args.source_root}", flush=True)
    print(f"probe_root={args.probe_root}", flush=True)
    print(
        f"bucket_ns={BUCKET_NS} rng_run={RNG_RUN} access_l1_bandwidth_gbps="
        f"{args.access_l1_bandwidth_gbps} host_access_bandwidth_gbps="
        f"{args.host_access_bandwidth_gbps} cases={len(cases)}",
        flush=True,
    )
    if args.prepare_only:
        return 0
    if not args.analyze_only:
        run_cases(cases, log_dir, args.parallel)
    analyze_all(cases, log_dir)
    print(f"results={log_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
