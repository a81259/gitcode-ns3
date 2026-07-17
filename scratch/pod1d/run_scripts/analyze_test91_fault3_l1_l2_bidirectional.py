#!/usr/bin/env python3
"""Compare L1<->L2 port Tx balance for standard topology and fault3."""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


L1_START, L1_END = 2736, 3192
L2_START, L2_END = 3192, 3288


@dataclass(frozen=True)
class CaseData:
    key: str
    title: str
    links: frozenset[tuple[tuple[int, int], tuple[int, int]]]
    counts: Counter[tuple[int, tuple[int, int]]]
    bytes_sent: Counter[tuple[int, tuple[int, int]]]
    max_bucket: int


def l1_l2_links(topology_path: Path) -> frozenset[tuple[tuple[int, int], tuple[int, int]]]:
    links: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    with topology_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            node1, port1 = int(row["nodeId1"]), int(row["portId1"])
            node2, port2 = int(row["nodeId2"]), int(row["portId2"])
            if L1_START <= node1 < L1_END and L2_START <= node2 < L2_END:
                links.add(((node1, port1), (node2, port2)))
            elif L1_START <= node2 < L1_END and L2_START <= node1 < L2_END:
                links.add(((node2, port2), (node1, port1)))
    if not links:
        raise ValueError(f"no L1-L2 links found in {topology_path}")
    return frozenset(links)


def parse_case(key: str, title: str, case_dir: Path, bucket_us: Decimal) -> CaseData:
    links = l1_l2_links(case_dir / "topology.csv")
    selected_ports = {endpoint for link in links for endpoint in link}
    trace_path = case_dir / "runlog" / "PortTxBucketTrace.csv"
    if not trace_path.is_file():
        raise FileNotFoundError(f"missing aggregated port trace: {trace_path}")
    expected_width_ns = int(bucket_us * Decimal(1000))
    if Decimal(expected_width_ns) != bucket_us * Decimal(1000):
        raise ValueError(f"bucket width must be an integer number of ns: {bucket_us} us")
    counts: Counter[tuple[int, tuple[int, int]]] = Counter()
    bytes_sent: Counter[tuple[int, tuple[int, int]]] = Counter()
    max_bucket = 0
    with trace_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            bucket = int(row["bucket_index"])
            start_ns, end_ns = int(row["bucket_start_ns"]), int(row["bucket_end_ns"])
            if start_ns != bucket * expected_width_ns or end_ns - start_ns != expected_width_ns:
                raise ValueError(f"unexpected bucket bounds in {trace_path}: {row}")
            port = (int(row["node_id"]), int(row["port_id"]))
            if port not in selected_ports:
                continue
            counts[(bucket, port)] += int(row["tx_packets"])
            bytes_sent[(bucket, port)] += int(row["tx_bytes"])
            max_bucket = max(max_bucket, bucket)
    return CaseData(key, title, links, counts, bytes_sent, max_bucket)


def metrics(values_by_port: dict[tuple[int, int], int]) -> dict[str, float | int | str]:
    values = list(values_by_port.values())
    total = sum(values)
    active = sum(value > 0 for value in values)
    mean = total / len(values)
    stddev = math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
    squared = sum(value * value for value in values)
    by_node: dict[int, list[int]] = defaultdict(list)
    for (node, _port), value in values_by_port.items():
        by_node[node].append(value)
    node_metrics = [metrics_without_nodes(group) for group in by_node.values() if sum(group) > 0]
    node_weight = sum(item["total_packets"] for item in node_metrics)
    return {
        "eligible_ports": len(values),
        "active_ports": active,
        "total_packets": total,
        "avg_packets_per_port": mean,
        "stddev_packets_per_port": stddev,
        "cv": "" if mean == 0 else stddev / mean,
        "jain": "" if squared == 0 else total * total / (len(values) * squared),
        "max_packets_on_one_port": max(values),
        "active_switches": len(node_metrics),
        "weighted_switch_jain": "" if node_weight == 0 else sum(item["jain"] * item["total_packets"] for item in node_metrics) / node_weight,
        "weighted_switch_cv": "" if node_weight == 0 else sum(item["cv"] * item["total_packets"] for item in node_metrics) / node_weight,
    }


def metrics_without_nodes(values: list[int]) -> dict[str, float | int]:
    total = sum(values)
    mean = total / len(values)
    stddev = math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
    squared = sum(value * value for value in values)
    return {
        "total_packets": total,
        "jain": total * total / (len(values) * squared),
        "cv": stddev / mean,
    }


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def fmt_time(bucket: int, bucket_us: Decimal) -> str:
    return f"{Decimal(bucket) * bucket_us:.6f}"


def direction_ports(
    links: frozenset[tuple[tuple[int, int], tuple[int, int]]], direction: str
) -> tuple[tuple[int, int], ...]:
    endpoint = 0 if direction == "L1_TO_L2" else 1
    return tuple(sorted(link[endpoint] for link in links))


def analysis_rows(
    standard: CaseData, fault3: CaseData, bucket_us: Decimal
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    common_links = standard.links & fault3.links
    if not common_links:
        raise ValueError("no common L1-L2 links")
    max_bucket = max(standard.max_bucket, fault3.max_bucket)
    overall_rows: list[dict[str, object]] = []
    bucket_rows: list[dict[str, object]] = []
    port_rows: list[dict[str, object]] = []
    comparison_rows: list[dict[str, object]] = []
    cases = (standard, fault3)

    for direction, label in (("L1_TO_L2", "L1 上行 → L2"), ("L2_TO_L1", "L2 回向 → L1")):
        ports = direction_ports(common_links, direction)
        per_case_overall: dict[str, dict[str, object]] = {}
        per_case_buckets: dict[str, dict[int, dict[str, object]]] = {}
        for case in cases:
            overall_values = {
                port: sum(case.counts[(bucket, port)] for bucket in range(max_bucket + 1)) for port in ports
            }
            overall = {
                "direction": direction,
                "direction_title": label,
                "case": case.key,
                "title": case.title,
                "bucket_width_us": f"{bucket_us:.6f}",
                "common_surviving_links": len(common_links),
                "eligible_ports": len(ports),
            }
            overall.update(metrics(overall_values))
            overall_rows.append(overall)
            per_case_overall[case.key] = overall
            per_case_buckets[case.key] = {}
            for bucket in range(max_bucket + 1):
                values = {port: case.counts[(bucket, port)] for port in ports}
                row = {
                    "direction": direction,
                    "direction_title": label,
                    "case": case.key,
                    "title": case.title,
                    "bucket_index": bucket,
                    "bucket_start_us": fmt_time(bucket, bucket_us),
                    "bucket_end_us": fmt_time(bucket + 1, bucket_us),
                    "bucket_width_us": f"{bucket_us:.6f}",
                }
                row.update(metrics(values))
                bucket_rows.append(row)
                per_case_buckets[case.key][bucket] = row
                for port, packets in values.items():
                    port_rows.append(
                        {
                            "direction": direction,
                            "direction_title": label,
                            "case": case.key,
                            "title": case.title,
                            "bucket_index": bucket,
                            "bucket_start_us": fmt_time(bucket, bucket_us),
                            "bucket_end_us": fmt_time(bucket + 1, bucket_us),
                            "node_id": port[0],
                            "port_id": port[1],
                            "tx_packets": packets,
                            "tx_bytes": case.bytes_sent[(bucket, port)],
                        }
                    )

        for bucket in range(max_bucket + 1):
            base, fault = per_case_buckets["standard"][bucket], per_case_buckets["fault3"][bucket]
            base_jain, fault_jain = float(base["jain"] or 0), float(fault["jain"] or 0)
            base_cv, fault_cv = float(base["cv"] or 0), float(fault["cv"] or 0)
            base_switch_jain, fault_switch_jain = float(base["weighted_switch_jain"] or 0), float(fault["weighted_switch_jain"] or 0)
            base_switch_cv, fault_switch_cv = float(base["weighted_switch_cv"] or 0), float(fault["weighted_switch_cv"] or 0)
            comparison_rows.append(
                {
                    "direction": direction,
                    "direction_title": label,
                    "bucket_index": bucket,
                    "bucket_start_us": base["bucket_start_us"],
                    "bucket_end_us": base["bucket_end_us"],
                    "standard_packets": base["total_packets"],
                    "fault3_packets": fault["total_packets"],
                    "standard_jain": f"{base_jain:.9f}",
                    "fault3_jain": f"{fault_jain:.9f}",
                    "jain_delta_fault3_minus_standard": f"{fault_jain - base_jain:.9f}",
                    "standard_cv": f"{base_cv:.9f}",
                    "fault3_cv": f"{fault_cv:.9f}",
                    "cv_delta_fault3_minus_standard": f"{fault_cv - base_cv:.9f}",
                    "standard_weighted_switch_jain": f"{base_switch_jain:.9f}",
                    "fault3_weighted_switch_jain": f"{fault_switch_jain:.9f}",
                    "weighted_switch_jain_delta_fault3_minus_standard": f"{fault_switch_jain - base_switch_jain:.9f}",
                    "standard_weighted_switch_cv": f"{base_switch_cv:.9f}",
                    "fault3_weighted_switch_cv": f"{fault_switch_cv:.9f}",
                    "weighted_switch_cv_delta_fault3_minus_standard": f"{fault_switch_cv - base_switch_cv:.9f}",
                }
            )
    return overall_rows, bucket_rows, port_rows, comparison_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--standard-dir", type=Path, required=True)
    parser.add_argument("--fault3-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--bin-us", type=Decimal, default=Decimal("0.25"))
    args = parser.parse_args()
    if args.bin_us <= 0:
        raise ValueError("--bin-us must be positive")
    standard = parse_case("standard", "标准拓扑", args.standard_dir, args.bin_us)
    fault3 = parse_case("fault3", "故障3（L1–L2 分布式 Port Down，每个 POD 1 根）", args.fault3_dir, args.bin_us)
    overall_rows, bucket_rows, port_rows, comparison_rows = analysis_rows(standard, fault3, args.bin_us)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.out_dir / "l1_l2_bidirectional"
    write_csv(
        prefix.with_name(prefix.name + "_port_tx_by_250ns.csv"),
        ["direction", "direction_title", "case", "title", "bucket_index", "bucket_start_us", "bucket_end_us", "node_id", "port_id", "tx_packets", "tx_bytes"],
        port_rows,
    )
    metric_fields = [
        "direction", "direction_title", "case", "title", "bucket_index", "bucket_start_us", "bucket_end_us", "bucket_width_us",
        "eligible_ports", "active_ports", "total_packets", "avg_packets_per_port", "stddev_packets_per_port", "cv", "jain",
        "max_packets_on_one_port", "active_switches", "weighted_switch_jain", "weighted_switch_cv",
    ]
    write_csv(prefix.with_name(prefix.name + "_fairness_by_250ns.csv"), metric_fields, bucket_rows)
    write_csv(
        prefix.with_name(prefix.name + "_fairness_overall.csv"),
        ["direction", "direction_title", "case", "title", "bucket_width_us", "common_surviving_links", "eligible_ports"] + metric_fields[9:],
        overall_rows,
    )
    write_csv(
        prefix.with_name(prefix.name + "_bucket_comparison.csv"),
        [
            "direction", "direction_title", "bucket_index", "bucket_start_us", "bucket_end_us", "standard_packets", "fault3_packets",
            "standard_jain", "fault3_jain", "jain_delta_fault3_minus_standard", "standard_cv", "fault3_cv",
            "cv_delta_fault3_minus_standard", "standard_weighted_switch_jain", "fault3_weighted_switch_jain",
            "weighted_switch_jain_delta_fault3_minus_standard", "standard_weighted_switch_cv", "fault3_weighted_switch_cv",
            "weighted_switch_cv_delta_fault3_minus_standard",
        ],
        comparison_rows,
    )
    write_csv(
        prefix.with_name(prefix.name + "_failed_links.csv"),
        ["l1_node_id", "l1_port_id", "l2_node_id", "l2_port_id"],
        [
            {"l1_node_id": l1[0], "l1_port_id": l1[1], "l2_node_id": l2[0], "l2_port_id": l2[1]}
            for l1, l2 in sorted(standard.links - fault3.links)
        ],
    )
    print(f"common_surviving_links={len(standard.links & fault3.links)}")
    print(f"failed_links={len(standard.links - fault3.links)}")
    print(f"time_buckets={max(standard.max_bucket, fault3.max_bucket) + 1}")
    print(f"overall={prefix.with_name(prefix.name + '_fairness_overall.csv')}")
    print(f"bucket_comparison={prefix.with_name(prefix.name + '_bucket_comparison.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
