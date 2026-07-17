#!/usr/bin/env python3
"""Aggregate Port Tx traces into time buckets and compare standard topology with fault3."""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


L2_START = 2736
L2_END = 3192
PLANE_START = 3192
@dataclass(frozen=True)
class CaseTrace:
    key: str
    title: str
    case_dir: Path
    ports: frozenset[tuple[int, int]]
    counts: Counter[tuple[int, tuple[int, int]]]
    bytes: Counter[tuple[int, tuple[int, int]]]
    max_bucket: int
    tx_packets: int
    tx_bytes: int


def l2_plane_ports(topology: Path) -> frozenset[tuple[int, int]]:
    ports: set[tuple[int, int]] = set()
    with topology.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            node1 = int(row["nodeId1"])
            node2 = int(row["nodeId2"])
            if L2_START <= node1 < L2_END and node2 >= PLANE_START:
                ports.add((node1, int(row["portId1"])))
            if L2_START <= node2 < L2_END and node1 >= PLANE_START:
                ports.add((node2, int(row["portId2"])))
    if not ports:
        raise ValueError(f"no L2-to-plane ports found in {topology}")
    return frozenset(ports)


def parse_case(key: str, title: str, case_dir: Path, bin_us: Decimal) -> CaseTrace:
    ports = l2_plane_ports(case_dir / "topology.csv")
    counts: Counter[tuple[int, tuple[int, int]]] = Counter()
    byte_counts: Counter[tuple[int, tuple[int, int]]] = Counter()
    max_bucket = 0
    tx_packets = 0
    tx_bytes = 0
    trace_dir = case_dir / "runlog"
    if not trace_dir.is_dir():
        raise FileNotFoundError(f"missing runlog directory: {trace_dir}")
    trace_path = trace_dir / "PortTxBucketTrace.csv"
    if not trace_path.is_file():
        raise FileNotFoundError(f"missing aggregated port trace: {trace_path}")
    expected_width_ns = int(bin_us * Decimal(1000))
    if Decimal(expected_width_ns) != bin_us * Decimal(1000):
        raise ValueError(f"time bucket must have an integer number of ns: {bin_us} us")
    with trace_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            bucket = int(row["bucket_index"])
            start_ns = int(row["bucket_start_ns"])
            end_ns = int(row["bucket_end_ns"])
            if start_ns != bucket * expected_width_ns or end_ns - start_ns != expected_width_ns:
                raise ValueError(f"unexpected bucket bounds in {trace_path}: {row}")
            port = (int(row["node_id"]), int(row["port_id"]))
            if port not in ports:
                raise ValueError(f"trace contains a port absent from topology: {port}")
            packets = int(row["tx_packets"])
            bytes_sent = int(row["tx_bytes"])
            counts[(bucket, port)] += packets
            byte_counts[(bucket, port)] += bytes_sent
            max_bucket = max(max_bucket, bucket)
            tx_packets += packets
            tx_bytes += bytes_sent
    if tx_packets == 0:
        raise ValueError(f"aggregated port trace is empty: {trace_path}")
    return CaseTrace(key, title, case_dir, ports, counts, byte_counts, max_bucket, tx_packets, tx_bytes)


def distribution_metrics(values: list[int]) -> dict[str, float | int | str]:
    total = sum(values)
    active = sum(value > 0 for value in values)
    if not values:
        raise ValueError("empty port universe")
    avg = total / len(values)
    variance = sum((value - avg) ** 2 for value in values) / len(values)
    stddev = math.sqrt(variance)
    squares = sum(value * value for value in values)
    return {
        "eligible_ports": len(values),
        "active_ports": active,
        "total_packets": total,
        "avg_packets_per_port": avg,
        "stddev_packets_per_port": stddev,
        "cv": "" if avg == 0 else stddev / avg,
        "jain": "" if squares == 0 else total * total / (len(values) * squares),
        "max_packets_on_one_port": max(values),
    }


def weighted_l2_metrics(values_by_port: dict[tuple[int, int], int]) -> dict[str, float | int | str]:
    by_l2: dict[int, list[int]] = defaultdict(list)
    for (node, _port), value in values_by_port.items():
        by_l2[node].append(value)
    groups = [distribution_metrics(values) for values in by_l2.values() if sum(values) > 0]
    total = sum(int(group["total_packets"]) for group in groups)
    if total == 0:
        return {"active_l2_switches": 0, "weighted_l2_jain": "", "weighted_l2_cv": ""}
    return {
        "active_l2_switches": len(groups),
        "weighted_l2_jain": sum(float(group["jain"]) * int(group["total_packets"]) for group in groups) / total,
        "weighted_l2_cv": sum(float(group["cv"]) * int(group["total_packets"]) for group in groups) / total,
    }


def add_metrics(row: dict[str, object], values_by_port: dict[tuple[int, int], int]) -> None:
    row.update(distribution_metrics(list(values_by_port.values())))
    row.update(weighted_l2_metrics(values_by_port))


def fmt_time(bucket: int, bin_us: Decimal) -> str:
    return f"{Decimal(bucket) * bin_us:.6f}"


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def analyze(standard_dir: Path, fault3_dir: Path, out_dir: Path, bin_us: Decimal) -> None:
    standard = parse_case("standard", "标准拓扑", standard_dir, bin_us)
    fault3 = parse_case("fault3", "故障3（L1–L2 分布式 Port Down，每个 POD 1 根）", fault3_dir, bin_us)
    common_ports = tuple(sorted(standard.ports & fault3.ports))
    removed_ports = tuple(sorted(standard.ports - fault3.ports))
    if not common_ports:
        raise ValueError("standard and fault3 have no common L2-to-plane ports")

    max_bucket = max(standard.max_bucket, fault3.max_bucket)
    bucket_rows: list[dict[str, object]] = []
    port_rows: list[dict[str, object]] = []
    overall_rows: list[dict[str, object]] = []
    cases = (standard, fault3)
    for case in cases:
        overall_values = {port: sum(case.counts[(bucket, port)] for bucket in range(max_bucket + 1)) for port in common_ports}
        overall = {
            "case": case.key,
            "title": case.title,
            "time_scope": "all_buckets",
            "bucket_width_us": f"{bin_us:.6f}",
            "total_l2_plane_ports_in_topology": len(case.ports),
            "common_surviving_ports": len(common_ports),
            "excluded_failed_ports": len(removed_ports) if case.key == "standard" else 0,
            "all_l2_plane_tx_packets": case.tx_packets,
            "all_l2_plane_tx_bytes": case.tx_bytes,
        }
        add_metrics(overall, overall_values)
        overall_rows.append(overall)

        for bucket in range(max_bucket + 1):
            values = {port: case.counts[(bucket, port)] for port in common_ports}
            row = {
                "case": case.key,
                "title": case.title,
                "bucket_index": bucket,
                "bucket_start_us": fmt_time(bucket, bin_us),
                "bucket_end_us": fmt_time(bucket + 1, bin_us),
                "bucket_width_us": f"{bin_us:.6f}",
            }
            add_metrics(row, values)
            bucket_rows.append(row)
            for port, packets in values.items():
                port_rows.append(
                    {
                        "case": case.key,
                        "title": case.title,
                        "bucket_index": bucket,
                        "bucket_start_us": fmt_time(bucket, bin_us),
                        "bucket_end_us": fmt_time(bucket + 1, bin_us),
                        "node_id": port[0],
                        "port_id": port[1],
                        "tx_packets": packets,
                        "tx_bytes": case.bytes[(bucket, port)],
                    }
                )

    comparison_fields = [
        "metric",
        "standard",
        "fault3",
        "fault3_minus_standard",
        "fault3_vs_standard_percent",
        "interpretation",
    ]
    comparison_rows: list[dict[str, object]] = []
    standard_overall, fault3_overall = overall_rows
    for metric, interpretation in (
        ("jain", "higher means packet counts are more even across the same surviving ports"),
        ("cv", "lower means packet counts are more even across the same surviving ports"),
        ("weighted_l2_jain", "higher means more even port use within active L2 switches"),
        ("weighted_l2_cv", "lower means more even port use within active L2 switches"),
    ):
        base = standard_overall[metric]
        fault = fault3_overall[metric]
        if base == "" or fault == "":
            continue
        base_float = float(base)
        fault_float = float(fault)
        comparison_rows.append(
            {
                "metric": metric,
                "standard": f"{base_float:.9f}",
                "fault3": f"{fault_float:.9f}",
                "fault3_minus_standard": f"{fault_float - base_float:.9f}",
                "fault3_vs_standard_percent": "" if base_float == 0 else f"{(fault_float - base_float) / base_float * 100:.6f}",
                "interpretation": interpretation,
            }
        )

    bucket_comparison_rows: list[dict[str, object]] = []
    standard_buckets = {int(row["bucket_index"]): row for row in bucket_rows if row["case"] == "standard"}
    fault3_buckets = {int(row["bucket_index"]): row for row in bucket_rows if row["case"] == "fault3"}
    for bucket in sorted(standard_buckets):
        standard_bucket = standard_buckets[bucket]
        fault3_bucket = fault3_buckets[bucket]
        standard_jain = float(standard_bucket["jain"]) if standard_bucket["jain"] != "" else 0.0
        fault3_jain = float(fault3_bucket["jain"]) if fault3_bucket["jain"] != "" else 0.0
        standard_cv = float(standard_bucket["cv"]) if standard_bucket["cv"] != "" else 0.0
        fault3_cv = float(fault3_bucket["cv"]) if fault3_bucket["cv"] != "" else 0.0
        standard_l2_jain = (
            float(standard_bucket["weighted_l2_jain"])
            if standard_bucket["weighted_l2_jain"] != ""
            else 0.0
        )
        fault3_l2_jain = (
            float(fault3_bucket["weighted_l2_jain"])
            if fault3_bucket["weighted_l2_jain"] != ""
            else 0.0
        )
        standard_l2_cv = float(standard_bucket["weighted_l2_cv"]) if standard_bucket["weighted_l2_cv"] != "" else 0.0
        fault3_l2_cv = float(fault3_bucket["weighted_l2_cv"]) if fault3_bucket["weighted_l2_cv"] != "" else 0.0
        if abs(fault3_jain - standard_jain) < 1e-12:
            global_winner = "相同"
        elif fault3_jain > standard_jain:
            global_winner = "故障3更均衡"
        else:
            global_winner = "标准拓扑更均衡"
        if abs(fault3_l2_jain - standard_l2_jain) < 1e-12:
            l2_winner = "相同"
        elif fault3_l2_jain > standard_l2_jain:
            l2_winner = "故障3更均衡"
        else:
            l2_winner = "标准拓扑更均衡"
        bucket_comparison_rows.append(
            {
                "bucket_index": bucket,
                "bucket_start_us": standard_bucket["bucket_start_us"],
                "bucket_end_us": standard_bucket["bucket_end_us"],
                "standard_packets": standard_bucket["total_packets"],
                "fault3_packets": fault3_bucket["total_packets"],
                "standard_jain": f"{standard_jain:.9f}",
                "fault3_jain": f"{fault3_jain:.9f}",
                "jain_delta_fault3_minus_standard": f"{fault3_jain - standard_jain:.9f}",
                "standard_cv": f"{standard_cv:.9f}",
                "fault3_cv": f"{fault3_cv:.9f}",
                "cv_delta_fault3_minus_standard": f"{fault3_cv - standard_cv:.9f}",
                "global_fairer": global_winner,
                "standard_weighted_l2_jain": f"{standard_l2_jain:.9f}",
                "fault3_weighted_l2_jain": f"{fault3_l2_jain:.9f}",
                "weighted_l2_jain_delta_fault3_minus_standard": f"{fault3_l2_jain - standard_l2_jain:.9f}",
                "standard_weighted_l2_cv": f"{standard_l2_cv:.9f}",
                "fault3_weighted_l2_cv": f"{fault3_l2_cv:.9f}",
                "weighted_l2_cv_delta_fault3_minus_standard": f"{fault3_l2_cv - standard_l2_cv:.9f}",
                "within_l2_fairer": l2_winner,
            }
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        out_dir / "l2_plane_port_tx_by_250ns.csv",
        ["case", "title", "bucket_index", "bucket_start_us", "bucket_end_us", "node_id", "port_id", "tx_packets", "tx_bytes"],
        port_rows,
    )
    write_csv(
        out_dir / "l2_plane_port_fairness_by_250ns.csv",
        [
            "case", "title", "bucket_index", "bucket_start_us", "bucket_end_us", "bucket_width_us", "eligible_ports",
            "active_ports", "total_packets", "avg_packets_per_port", "stddev_packets_per_port", "cv", "jain",
            "max_packets_on_one_port", "active_l2_switches", "weighted_l2_jain", "weighted_l2_cv",
        ],
        bucket_rows,
    )
    write_csv(
        out_dir / "l2_plane_port_fairness_overall.csv",
        [
            "case", "title", "time_scope", "bucket_width_us", "total_l2_plane_ports_in_topology", "common_surviving_ports",
            "excluded_failed_ports", "all_l2_plane_tx_packets", "all_l2_plane_tx_bytes", "eligible_ports", "active_ports",
            "total_packets", "avg_packets_per_port", "stddev_packets_per_port", "cv", "jain", "max_packets_on_one_port",
            "active_l2_switches", "weighted_l2_jain", "weighted_l2_cv",
        ],
        overall_rows,
    )
    write_csv(out_dir / "l2_plane_port_fairness_comparison.csv", comparison_fields, comparison_rows)
    write_csv(
        out_dir / "l2_plane_port_fairness_bucket_comparison.csv",
        [
            "bucket_index", "bucket_start_us", "bucket_end_us", "standard_packets", "fault3_packets",
            "standard_jain", "fault3_jain", "jain_delta_fault3_minus_standard", "standard_cv", "fault3_cv",
            "cv_delta_fault3_minus_standard", "global_fairer", "standard_weighted_l2_jain",
            "fault3_weighted_l2_jain", "weighted_l2_jain_delta_fault3_minus_standard",
            "standard_weighted_l2_cv", "fault3_weighted_l2_cv", "weighted_l2_cv_delta_fault3_minus_standard",
            "within_l2_fairer",
        ],
        bucket_comparison_rows,
    )
    write_csv(
        out_dir / "l2_plane_failed_ports.csv",
        ["node_id", "port_id"],
        [{"node_id": node, "port_id": port} for node, port in removed_ports],
    )

    print(f"common_surviving_ports={len(common_ports)}")
    print(f"failed_ports_excluded_from_fairness={len(removed_ports)}")
    print(f"time_buckets={max_bucket + 1}")
    print(f"overall={out_dir / 'l2_plane_port_fairness_overall.csv'}")
    print(f"comparison={out_dir / 'l2_plane_port_fairness_comparison.csv'}")
    print(f"bucket_comparison={out_dir / 'l2_plane_port_fairness_bucket_comparison.csv'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--standard-dir", type=Path, required=True)
    parser.add_argument("--fault3-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--bin-us", type=Decimal, default=Decimal("0.25"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.bin_us <= 0:
        raise ValueError("--bin-us must be positive")
    analyze(args.standard_dir, args.fault3_dir, args.out_dir, args.bin_us)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
