#!/usr/bin/env python3
"""Build standard and fault variants for the Pod1D traffic cases."""

from __future__ import annotations

import csv
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from route_compaction import compact_route_dict_rows, is_route_fieldset


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
SHARED_CASE_FILES = ("generate_topology.py", "route_compaction.py")

@dataclass(frozen=True)
class LinkFaultTarget:
    node1: int
    port1: int
    node2: int
    port2: int
    half_bandwidth: str


ACCESS_L1_TARGET = LinkFaultTarget(
    node1=1368,
    port1=1,
    node2=2736,
    port2=0,
    half_bandwidth="112Gbps",
)
HOST_L1_TARGET = ACCESS_L1_TARGET
HOST_L1_TARGET_OVERRIDES = {
    "test06_pp_send_recv": LinkFaultTarget(
        node1=1492,
        port1=1,
        node2=2760,
        port2=52,
        half_bandwidth="112Gbps",
    ),
}
L1_L2_TARGET = LinkFaultTarget(
    node1=2736,
    port1=72,
    node2=3192,
    port2=0,
    half_bandwidth="224Gbps",
)

GENERATED_OUTPUT_DIRS = {"output", "runlog", "test"}
TRANSIENT_FILES = {"transport_channel.csv"}


PortMetric = tuple[int, int]
RouteSegment = tuple[int, int, int, int, int, list[PortMetric]]
TopologyLinks = dict[int, dict[int, list[int]]]


def is_traffic_case(path: Path) -> bool:
    return path.is_dir() and path.name.startswith("test")


def case_dirs() -> list[Path]:
    return sorted(path for path in BASE_DIR.iterdir() if is_traffic_case(path))


def host_l1_target_for_case(case_dir: Path) -> LinkFaultTarget:
    return HOST_L1_TARGET_OVERRIDES.get(case_dir.name, HOST_L1_TARGET)


def is_host_l1_target(target: LinkFaultTarget) -> bool:
    return target.node1 < HOST_L1_TARGET.node2 <= target.node2


def is_access_l1_target(links: TopologyLinks, target: LinkFaultTarget) -> bool:
    lower_neighbors = [neighbor for neighbor in links.get(target.node1, {}) if neighbor < target.node1]
    return len(lower_neighbors) == 1 and target.node2 > target.node1


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


def range_contains(range_value: str, target: int) -> bool:
    start, end = parse_range(range_value)
    return start <= target <= end


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
    replacement_ports: list[int] | None = None,
) -> list[RouteSegment]:
    rewritten: list[RouteSegment] = []
    for node_start, node_end, dst_start, dst_end, dst_port, port_metrics in segments:
        if bad_node < node_start or bad_node > node_end:
            rewritten.append((node_start, node_end, dst_start, dst_end, dst_port, port_metrics))
            continue

        if node_start <= bad_node - 1:
            rewritten.append((node_start, bad_node - 1, dst_start, dst_end, dst_port, port_metrics))

        used_ports = {port for port, _ in port_metrics if port != bad_port}
        filtered: list[PortMetric] = []
        for port, metric in port_metrics:
            if port != bad_port:
                filtered.append((port, metric))
                continue
            replacement_port = next(
                (
                    candidate
                    for candidate in replacement_ports or []
                    if candidate not in used_ports
                ),
                None,
            )
            if replacement_port is not None:
                filtered.append((replacement_port, metric))
                used_ports.add(replacement_port)
        if filtered:
            rewritten.append((bad_node, bad_node, dst_start, dst_end, dst_port, filtered))

        if bad_node + 1 <= node_end:
            rewritten.append((bad_node + 1, node_end, dst_start, dst_end, dst_port, port_metrics))

    return rewritten


def isolate_destination_node_from_range_segments(
    segments: list[RouteSegment],
    dst_node: int,
) -> list[RouteSegment]:
    rewritten: list[RouteSegment] = []
    for node_start, node_end, dst_start, dst_end, dst_port, port_metrics in segments:
        if dst_node < dst_start or dst_node > dst_end:
            rewritten.append((node_start, node_end, dst_start, dst_end, dst_port, port_metrics))
            continue

        for left, right in remove_values_from_interval(dst_start, dst_end, [dst_node]):
            rewritten.append((node_start, node_end, left, right, dst_port, port_metrics))

        for node_id in range(node_start, node_end + 1):
            rewritten.append((node_id, node_id, dst_node, dst_node, dst_port, port_metrics))

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


def rewrite_link_down_route_table(
    route_path: Path,
    target: LinkFaultTarget,
    source_port_replacements: dict[tuple[int, int], list[int]] | None = None,
    isolated_destination_nodes: set[int] | None = None,
) -> None:
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
            replacement_ports = (source_port_replacements or {}).get((bad_node, bad_port))
            segments = remove_source_port_from_segments(
                segments,
                bad_node,
                bad_port,
                replacement_ports,
            )
            next_segments: list[RouteSegment] = []
            for segment in segments:
                next_segments.extend(
                    remove_destination_port_from_segments(*segment, bad_node, bad_port)
                )
            segments = next_segments

        for isolated_dst_node in isolated_destination_nodes or set():
            segments = isolate_destination_node_from_range_segments(
                segments,
                isolated_dst_node,
            )

        for segment in segments:
            append_route_row(rewritten_rows, *segment)

    write_csv(route_path, fieldnames, rewritten_rows)


def apply_fault_link_down_preserving_ports(dst_dir: Path, target: LinkFaultTarget) -> None:
    remove_link_preserving_ports(dst_dir / "topology.csv", target)
    links = read_topology_links(dst_dir / "topology.csv")
    access_l1_down = is_access_l1_target(links, target)
    source_port_replacements: dict[tuple[int, int], list[int]] = {}
    blocked_l2_descent_ports: dict[int, list[int]] = {}
    blocked_host_id: int | None = None
    if access_l1_down:
        blocked_host_id = attached_host_for_access(links, target.node1)
        source_port_replacements[(target.node1, target.port1)] = live_uplink_ports_for_access(
            links,
            target.node1,
        )
        blocked_l2_descent_ports = l2_ports_to_l1(links, target.node2)
    rewrite_link_down_route_table(
        dst_dir / "routing_table.csv",
        target,
        source_port_replacements,
    )
    if access_l1_down and blocked_host_id is not None:
        remove_source_ports_for_destination(
            dst_dir / "routing_table.csv",
            blocked_host_id,
            blocked_l2_descent_ports,
        )
    if access_l1_down:
        append_access_l1_down_backup_routes(dst_dir, target)


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


def access_ports_to_l1s(links: TopologyLinks, access_id: int) -> list[tuple[int, int]]:
    return sorted(
        (ports[0], neighbor)
        for neighbor, ports in links.get(access_id, {}).items()
        if neighbor > access_id
        if ports
    )


def attached_host_for_access(links: TopologyLinks, access_id: int) -> int:
    host_neighbors = sorted(
        neighbor
        for neighbor, ports in links.get(access_id, {}).items()
        if neighbor < access_id
        if ports
    )
    if len(host_neighbors) != 1:
        raise ValueError(f"expected one attached host for access {access_id}, found {host_neighbors}")
    return host_neighbors[0]


def live_ports_for_node(links: TopologyLinks, node_id: int) -> list[int]:
    ports = set()
    for neighbor_ports in links.get(node_id, {}).values():
        ports.update(neighbor_ports)
    return sorted(ports)


def live_uplink_ports_for_access(links: TopologyLinks, access_id: int) -> list[int]:
    ports = set()
    for neighbor, neighbor_ports in links.get(access_id, {}).items():
        if neighbor > access_id:
            ports.update(neighbor_ports)
    return sorted(ports)


def l2_neighbors(links: TopologyLinks, l1_id: int) -> dict[int, list[int]]:
    return {
        neighbor: sorted(ports)
        for neighbor, ports in links.get(l1_id, {}).items()
        if neighbor > l1_id
    }


def l2_ports_to_l1(links: TopologyLinks, l1_id: int) -> dict[int, list[int]]:
    return {
        l2_id: sorted(links.get(l2_id, {}).get(l1_id, []))
        for l2_id in l2_neighbors(links, l1_id)
    }


def peer_access_backup_ports_to_host(
    links: TopologyLinks,
    access_id: int,
    failed_l1_id: int,
) -> list[int]:
    target_access_l1s = {
        l1_id
        for _, l1_id in access_ports_to_l1s(links, access_id)
        if l1_id != failed_l1_id
    }
    if not target_access_l1s:
        return []

    backup_ports = set()
    for peer_access_id, failed_l1_ports in links.get(failed_l1_id, {}).items():
        if peer_access_id == access_id or peer_access_id > failed_l1_id:
            continue
        peer_access_l1s = set(links.get(peer_access_id, {})) & target_access_l1s
        if peer_access_l1s:
            backup_ports.update(failed_l1_ports)
    return sorted(backup_ports)


def append_single_destination_with_filtered_source_ports(
    rows: list[dict[str, str]],
    node_start: int,
    node_end: int,
    dst_node: int,
    dst_port: int,
    port_metrics: list[PortMetric],
    source_ports_to_remove: dict[int, list[int]],
) -> None:
    cursor = node_start
    for source_node in sorted(source_ports_to_remove):
        if source_node < node_start or source_node > node_end:
            continue
        if cursor <= source_node - 1:
            append_route_row(rows, cursor, source_node - 1, dst_node, dst_node, dst_port, port_metrics)
        removed_ports = set(source_ports_to_remove[source_node])
        filtered = [
            (port, metric)
            for port, metric in port_metrics
            if port not in removed_ports
        ]
        append_route_row(rows, source_node, source_node, dst_node, dst_node, dst_port, filtered)
        cursor = source_node + 1
    if cursor <= node_end:
        append_route_row(rows, cursor, node_end, dst_node, dst_node, dst_port, port_metrics)


def remove_source_ports_for_destination(
    route_path: Path,
    dst_node: int,
    source_ports_to_remove: dict[int, list[int]],
    dst_port: int = 0,
) -> None:
    if not source_ports_to_remove:
        return

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
        row_dst_port = int(row["dstPortId"])
        port_metrics = parse_port_metrics(row)

        if row_dst_port != dst_port or not (dst_start <= dst_node <= dst_end):
            append_route_row(
                rewritten_rows,
                node_start,
                node_end,
                dst_start,
                dst_end,
                row_dst_port,
                port_metrics,
            )
            continue

        for left, right in remove_values_from_interval(dst_start, dst_end, [dst_node]):
            append_route_row(
                rewritten_rows,
                node_start,
                node_end,
                left,
                right,
                row_dst_port,
                port_metrics,
            )
        append_single_destination_with_filtered_source_ports(
            rewritten_rows,
            node_start,
            node_end,
            dst_node,
            row_dst_port,
            port_metrics,
            source_ports_to_remove,
        )

    write_csv(route_path, fieldnames, rewritten_rows)


def append_access_l1_down_backup_routes(dst_dir: Path, target: LinkFaultTarget) -> None:
    """Keep the failed L1 able to reach the access-attached host through other L1s."""
    topology_path = dst_dir / "topology.csv"
    route_path = dst_dir / "routing_table.csv"
    links = read_topology_links(topology_path)

    access_id = target.node1
    host_id = attached_host_for_access(links, access_id)
    failed_l1_id = target.node2
    failed_l1_l2_ports = l2_neighbors(links, failed_l1_id)

    with route_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        if fieldnames is None:
            raise ValueError(f"{route_path} has no CSV header")
        rows = list(reader)

    backup_out_ports = []
    for _, dst_l1_id in access_ports_to_l1s(links, access_id):
        if dst_l1_id == failed_l1_id:
            continue
        shared_l2_ids = sorted(
            set(failed_l1_l2_ports) & set(l2_neighbors(links, dst_l1_id))
        )
        for l2_id in shared_l2_ids:
            backup_out_ports.extend(failed_l1_l2_ports[l2_id])

    backup_metric = 3
    if not backup_out_ports:
        backup_out_ports = peer_access_backup_ports_to_host(links, access_id, failed_l1_id)
        backup_metric = 4

    port_metrics = [(port, backup_metric) for port in sorted(set(backup_out_ports))]
    backup_rows: list[dict[str, str]] = []
    append_route_row(
        backup_rows,
        failed_l1_id,
        failed_l1_id,
        host_id,
        host_id,
        0,
        port_metrics,
    )
    if not backup_rows:
        return
    rows.extend(backup_rows)
    write_csv(route_path, fieldnames, rows)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    if is_route_fieldset(fieldnames):
        rows = compact_route_dict_rows(rows)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def set_default_attribute(lines: list[str], attribute: str, value: str) -> bool:
    prefix = f"default ns3::UbRoutingProcess::{attribute} "
    replacement = f'{prefix}"{value}"'
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            return True
    return False


def configure_packet_spray(case_dir: Path, enabled: bool, scope: str = "all") -> None:
    attribute_path = case_dir / "network_attribute.txt"
    if not attribute_path.exists():
        raise FileNotFoundError(f"missing network attributes: {attribute_path}")

    lines = attribute_path.read_text(encoding="utf-8").splitlines()
    has_weighted = set_default_attribute(
        lines,
        "BwWeightedPacketSpray",
        "true" if enabled else "false",
    )
    has_scope = set_default_attribute(lines, "BwWeightedPacketSprayScope", scope)

    if not has_weighted:
        lines.append(
            f'default ns3::UbRoutingProcess::BwWeightedPacketSpray '
            f'"{"true" if enabled else "false"}"'
        )
    if not has_scope:
        insert_after = next(
            (
                index + 1
                for index, line in enumerate(lines)
                if line.startswith("default ns3::UbRoutingProcess::BwWeightedPacketSpray ")
            ),
            len(lines),
        )
        lines.insert(
            insert_after,
            f'default ns3::UbRoutingProcess::BwWeightedPacketSprayScope "{scope}"',
        )

    attribute_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_case_variants(case_dir: Path) -> None:
    standard_dir = move_root_case_files_to_standard(case_dir)
    sync_shared_case_files(standard_dir)
    configure_packet_spray(standard_dir, enabled=False)
    host_l1_target = host_l1_target_for_case(case_dir)

    for legacy_name in LEGACY_CASE_VARIANTS:
        legacy_dir = case_dir / legacy_name
        if legacy_dir.exists():
            shutil.rmtree(legacy_dir)

    host_l1_bw_dir = case_dir / FAULT_HOST_L1_BW_HALF_CASE
    copy_clean_case(standard_dir, host_l1_bw_dir)
    sync_shared_case_files(host_l1_bw_dir)
    rewrite_link_bandwidth(host_l1_bw_dir / "topology.csv", host_l1_target)
    configure_packet_spray(host_l1_bw_dir, enabled=True, scope="access-l1")

    host_l1_link_down_dir = case_dir / FAULT_HOST_L1_LINK_DOWN_CASE
    copy_clean_case(standard_dir, host_l1_link_down_dir)
    sync_shared_case_files(host_l1_link_down_dir)
    apply_fault_link_down_preserving_ports(host_l1_link_down_dir, host_l1_target)
    configure_packet_spray(host_l1_link_down_dir, enabled=False)

    l1_l2_bw_dir = case_dir / FAULT_L1_L2_BW_HALF_CASE
    copy_clean_case(standard_dir, l1_l2_bw_dir)
    sync_shared_case_files(l1_l2_bw_dir)
    rewrite_link_bandwidth(l1_l2_bw_dir / "topology.csv", L1_L2_TARGET)
    configure_packet_spray(l1_l2_bw_dir, enabled=True, scope="l1-l2")

    l1_l2_link_down_dir = case_dir / FAULT_L1_L2_LINK_DOWN_CASE
    copy_clean_case(standard_dir, l1_l2_link_down_dir)
    sync_shared_case_files(l1_l2_link_down_dir)
    apply_fault_link_down_preserving_ports(l1_l2_link_down_dir, L1_L2_TARGET)
    configure_packet_spray(l1_l2_link_down_dir, enabled=False)


def main() -> None:
    for case_dir in case_dirs():
        build_case_variants(case_dir)
        print(f"built variants for {case_dir.name}")


if __name__ == "__main__":
    main()
