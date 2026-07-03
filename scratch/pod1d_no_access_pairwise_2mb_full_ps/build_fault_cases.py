#!/usr/bin/env python3
"""Build standard and fault variants for the Pod1D traffic cases."""

from __future__ import annotations

import csv
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


BASE_DIR = Path(__file__).resolve().parent

STANDARD_CASE = "case01_standard"
FAULT_HOST_L1_BW_HALF_CASE = "case02_host_l1_lane_down"
FAULT_HOST_L1_LINK_DOWN_CASE = "case03_host_l1_port_down"
FAULT_L1_L2_BW_HALF_CASE = "case04_l1_l2_lane_down"
FAULT_L1_L2_LINK_DOWN_CASE = "case05_l1_l2_port_down"
CASE_VARIANTS = (
    STANDARD_CASE,
    FAULT_HOST_L1_BW_HALF_CASE,
    FAULT_HOST_L1_LINK_DOWN_CASE,
    FAULT_L1_L2_BW_HALF_CASE,
    FAULT_L1_L2_LINK_DOWN_CASE,
)
LEGACY_CASE_VARIANTS = (
    "standard",
    "fault_bw56",
    "fault_link_down",
    "fault_host_l1_bw112",
    "fault_host_l1_link_down",
    "fault_l1_l2_bw224",
    "fault_l1_l2_link_down",
)
ALL_VARIANT_DIR_NAMES = set(CASE_VARIANTS) | set(LEGACY_CASE_VARIANTS)
SHARED_CASE_FILES = ("generate_topology.py",)

@dataclass(frozen=True)
class LinkFaultTarget:
    node1: int
    port1: int
    node2: int
    port2: int
    half_bandwidth: str


HOST_L1_TARGET = LinkFaultTarget(
    node1=0,
    port1=0,
    node2=1368,
    port2=0,
    half_bandwidth="112Gbps",
)
L1_L2_TARGET = LinkFaultTarget(
    node1=1368,
    port1=72,
    node2=1824,
    port2=0,
    half_bandwidth="224Gbps",
)

GENERATED_OUTPUT_DIRS = {"output", "runlog"}
TRANSIENT_FILES = {"transport_channel.csv"}


PortMetric = tuple[int, int]
RouteSegment = tuple[int, int, int, int, int, list[PortMetric]]
TopologyLinks = dict[int, dict[int, list[int]]]


def is_traffic_case(path: Path) -> bool:
    return path.is_dir() and path.name.startswith("test")


def case_dirs() -> list[Path]:
    return sorted(path for path in BASE_DIR.iterdir() if is_traffic_case(path))


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def move_root_case_files_to_standard(case_dir: Path) -> Path:
    standard_dir = case_dir / STANDARD_CASE
    standard_dir.mkdir(exist_ok=True)

    for child in sorted(case_dir.iterdir()):
        if child.name in ALL_VARIANT_DIR_NAMES:
            continue
        if child.name.startswith("."):
            continue
        shutil.move(str(child), standard_dir / child.name)

    return standard_dir


def copy_clean_case(src_dir: Path, dst_dir: Path) -> None:
    reset_dir(dst_dir)
    for child in sorted(src_dir.iterdir()):
        if child.name in GENERATED_OUTPUT_DIRS or child.name in TRANSIENT_FILES:
            continue
        dst = dst_dir / child.name
        if child.is_dir():
            shutil.copytree(child, dst)
        else:
            shutil.copy2(child, dst)


def sync_shared_case_files(dst_dir: Path) -> None:
    for file_name in SHARED_CASE_FILES:
        src = BASE_DIR / file_name
        if not src.exists():
            raise FileNotFoundError(f"missing shared case file: {src}")
        shutil.copy2(src, dst_dir / file_name)


def parse_range(value: str) -> tuple[int, int]:
    if ".." in value:
        left, right = value.split("..", 1)
        return int(left), int(right)
    node_id = int(value)
    return node_id, node_id


def format_range(start: int, end: int) -> str:
    if start == end:
        return str(start)
    return f"{start}..{end}"


def parse_int_list(value: str) -> list[int]:
    return [int(item) for item in value.split()]


def parse_port_metrics(row: dict[str, str]) -> list[PortMetric]:
    ports = parse_int_list(row["outPorts"])
    metrics = parse_int_list(row["metrics"])
    if len(metrics) == 1 and len(ports) > 1:
        metrics = metrics * len(ports)
    if len(ports) != len(metrics):
        raise ValueError(f"outPorts and metrics length mismatch: {row}")
    return list(zip(ports, metrics))


def remove_values_from_interval(start: int, end: int, values: Iterable[int]) -> list[tuple[int, int]]:
    intervals = [(start, end)]
    for value in sorted(set(values)):
        next_intervals = []
        for left, right in intervals:
            if value < left or value > right:
                next_intervals.append((left, right))
                continue
            if left <= value - 1:
                next_intervals.append((left, value - 1))
            if value + 1 <= right:
                next_intervals.append((value + 1, right))
        intervals = next_intervals
    return intervals


def append_route_row(
    rows: list[dict[str, str]],
    node_start: int,
    node_end: int,
    dst_start: int,
    dst_end: int,
    dst_port: int,
    port_metrics: list[PortMetric],
) -> None:
    if not port_metrics:
        return
    rows.append(
        {
            "nodeId": format_range(node_start, node_end),
            "dstNodeId": format_range(dst_start, dst_end),
            "dstPortId": str(dst_port),
            "outPorts": " ".join(str(port) for port, _ in port_metrics),
            "metrics": " ".join(str(metric) for _, metric in port_metrics),
        }
    )


def remove_destination_port_from_segments(
    node_start: int,
    node_end: int,
    dst_start: int,
    dst_end: int,
    dst_port: int,
    port_metrics: list[PortMetric],
    bad_dst_node: int,
    bad_dst_port: int,
) -> list[RouteSegment]:
    if dst_port != bad_dst_port:
        return [(node_start, node_end, dst_start, dst_end, dst_port, port_metrics)]

    dst_intervals = remove_values_from_interval(dst_start, dst_end, [bad_dst_node])
    return [
        (node_start, node_end, left, right, dst_port, port_metrics)
        for left, right in dst_intervals
    ]


def remove_source_port_from_segments(
    segments: list[RouteSegment],
    bad_node: int,
    bad_port: int,
) -> list[RouteSegment]:
    rewritten: list[RouteSegment] = []
    for node_start, node_end, dst_start, dst_end, dst_port, port_metrics in segments:
        if bad_node < node_start or bad_node > node_end:
            rewritten.append((node_start, node_end, dst_start, dst_end, dst_port, port_metrics))
            continue

        if node_start <= bad_node - 1:
            rewritten.append((node_start, bad_node - 1, dst_start, dst_end, dst_port, port_metrics))

        filtered = [(port, metric) for port, metric in port_metrics if port != bad_port]
        if filtered:
            rewritten.append((bad_node, bad_node, dst_start, dst_end, dst_port, filtered))

        if bad_node + 1 <= node_end:
            rewritten.append((bad_node + 1, node_end, dst_start, dst_end, dst_port, port_metrics))

    return rewritten


def rewrite_link_bandwidth(topology_path: Path, target: LinkFaultTarget) -> None:
    with topology_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        if fieldnames is None:
            raise ValueError(f"{topology_path} has no CSV header")
        rows = list(reader)

    changed = 0
    for row in rows:
        if is_target_link(row, target):
            row["bandwidth"] = target.half_bandwidth
            changed += 1

    if changed != 1:
        raise ValueError(f"expected exactly one target link in {topology_path}, found {changed}")

    write_csv(topology_path, fieldnames, rows)


def is_target_link(row: dict[str, str], target: LinkFaultTarget) -> bool:
    forward = (
        row["nodeId1"] == str(target.node1)
        and row["portId1"] == str(target.port1)
        and row["nodeId2"] == str(target.node2)
        and row["portId2"] == str(target.port2)
    )
    reverse = (
        row["nodeId1"] == str(target.node2)
        and row["portId1"] == str(target.port2)
        and row["nodeId2"] == str(target.node1)
        and row["portId2"] == str(target.port1)
    )
    return forward or reverse


def remove_link_preserving_ports(topology_path: Path, target: LinkFaultTarget) -> None:
    with topology_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        if fieldnames is None:
            raise ValueError(f"{topology_path} has no CSV header")
        rows = list(reader)

    kept_rows = []
    removed = 0
    for row in rows:
        if is_target_link(row, target):
            removed += 1
            continue
        kept_rows.append(row)

    if removed != 1:
        raise ValueError(f"expected exactly one target link in {topology_path}, found {removed}")

    write_csv(topology_path, fieldnames, kept_rows)


def rewrite_link_down_route_table(route_path: Path, target: LinkFaultTarget) -> None:
    with route_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        if fieldnames is None:
            raise ValueError(f"{route_path} has no CSV header")
        source_rows = list(reader)

    rewritten_rows: list[dict[str, str]] = []
    for row in source_rows:
        node_start, node_end = parse_range(row["nodeId"])
        dst_start, dst_end = parse_range(row["dstNodeId"])
        dst_port = int(row["dstPortId"])
        port_metrics = parse_port_metrics(row)

        segments = [(node_start, node_end, dst_start, dst_end, dst_port, port_metrics)]
        for bad_node, bad_port in (
            (target.node1, target.port1),
            (target.node2, target.port2),
        ):
            segments = remove_source_port_from_segments(segments, bad_node, bad_port)
            next_segments: list[RouteSegment] = []
            for segment in segments:
                next_segments.extend(
                    remove_destination_port_from_segments(*segment, bad_node, bad_port)
                )
            segments = next_segments

        for segment in segments:
            append_route_row(rewritten_rows, *segment)

    write_csv(route_path, fieldnames, rewritten_rows)


def apply_fault_link_down_preserving_ports(dst_dir: Path, target: LinkFaultTarget) -> None:
    remove_link_preserving_ports(dst_dir / "topology.csv", target)
    rewrite_link_down_route_table(dst_dir / "routing_table.csv", target)
    if target == HOST_L1_TARGET:
        append_host_l1_down_backup_routes(dst_dir, target)


def read_topology_links(topology_path: Path) -> TopologyLinks:
    links: TopologyLinks = {}
    with topology_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            node1 = int(row["nodeId1"])
            port1 = int(row["portId1"])
            node2 = int(row["nodeId2"])
            port2 = int(row["portId2"])
            links.setdefault(node1, {}).setdefault(node2, []).append(port1)
            links.setdefault(node2, {}).setdefault(node1, []).append(port2)
    return links


def host_ports_to_l1s(links: TopologyLinks, host_id: int) -> list[tuple[int, int]]:
    return sorted(
        (ports[0], neighbor)
        for neighbor, ports in links.get(host_id, {}).items()
        if ports
    )


def l2_neighbors(links: TopologyLinks, l1_id: int, host_node_max: int) -> dict[int, list[int]]:
    return {
        neighbor: sorted(ports)
        for neighbor, ports in links.get(l1_id, {}).items()
        if neighbor > host_node_max
    }


def append_host_l1_down_backup_routes(dst_dir: Path, target: LinkFaultTarget) -> None:
    """Keep the failed L1 able to reach the host through L2 and other L1s."""
    topology_path = dst_dir / "topology.csv"
    route_path = dst_dir / "routing_table.csv"
    links = read_topology_links(topology_path)

    host_id = target.node1
    failed_l1_id = target.node2
    host_node_max = failed_l1_id - 1
    failed_l1_l2_ports = l2_neighbors(links, failed_l1_id, host_node_max)

    with route_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        if fieldnames is None:
            raise ValueError(f"{route_path} has no CSV header")
        rows = list(reader)

    backup_row: list[dict[str, str]] = []
    for dst_port, dst_l1_id in host_ports_to_l1s(links, host_id):
        if dst_l1_id == failed_l1_id:
            continue
        backup_out_ports = []
        shared_l2_ids = sorted(
            set(failed_l1_l2_ports) & set(l2_neighbors(links, dst_l1_id, host_node_max))
        )
        for l2_id in shared_l2_ids:
            backup_out_ports.extend(failed_l1_l2_ports[l2_id])
        port_metrics = [(port, 3) for port in sorted(set(backup_out_ports))]
        append_route_row(
            backup_row,
            failed_l1_id,
            failed_l1_id,
            host_id,
            host_id,
            dst_port,
            port_metrics,
        )
    if not backup_row:
        raise ValueError(f"no backup route found for {failed_l1_id} -> host {host_id}")
    rows.extend(backup_row)
    write_csv(route_path, fieldnames, rows)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_case_variants(case_dir: Path) -> None:
    standard_dir = move_root_case_files_to_standard(case_dir)
    sync_shared_case_files(standard_dir)

    for legacy_name in LEGACY_CASE_VARIANTS:
        legacy_dir = case_dir / legacy_name
        if legacy_dir.exists():
            shutil.rmtree(legacy_dir)

    host_l1_bw_dir = case_dir / FAULT_HOST_L1_BW_HALF_CASE
    copy_clean_case(standard_dir, host_l1_bw_dir)
    sync_shared_case_files(host_l1_bw_dir)
    rewrite_link_bandwidth(host_l1_bw_dir / "topology.csv", HOST_L1_TARGET)

    host_l1_link_down_dir = case_dir / FAULT_HOST_L1_LINK_DOWN_CASE
    copy_clean_case(standard_dir, host_l1_link_down_dir)
    sync_shared_case_files(host_l1_link_down_dir)
    apply_fault_link_down_preserving_ports(host_l1_link_down_dir, HOST_L1_TARGET)

    l1_l2_bw_dir = case_dir / FAULT_L1_L2_BW_HALF_CASE
    copy_clean_case(standard_dir, l1_l2_bw_dir)
    sync_shared_case_files(l1_l2_bw_dir)
    rewrite_link_bandwidth(l1_l2_bw_dir / "topology.csv", L1_L2_TARGET)

    l1_l2_link_down_dir = case_dir / FAULT_L1_L2_LINK_DOWN_CASE
    copy_clean_case(standard_dir, l1_l2_link_down_dir)
    sync_shared_case_files(l1_l2_link_down_dir)
    apply_fault_link_down_preserving_ports(l1_l2_link_down_dir, L1_L2_TARGET)


def main() -> None:
    for case_dir in case_dirs():
        build_case_variants(case_dir)
        print(f"built variants for {case_dir.name}")


if __name__ == "__main__":
    main()
