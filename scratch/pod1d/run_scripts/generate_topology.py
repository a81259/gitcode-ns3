#!/usr/bin/env python3
"""Generate a Pod1D topology with a per-host access-switch layer.

The generated shape is:

    host -> access switch -> pod-local L1 -> global L2

Each host has a single port and behaves as a traffic endpoint. The access
switch owns the fanout to the 24 pod-local L1 switches.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path


def add_tools_path() -> None:
    for path in Path(__file__).resolve().parents:
        tools_path = path / "scratch" / "ns-3-ub-tools"
        if tools_path.exists():
            sys.path.insert(0, str(tools_path))
            return
    raise RuntimeError("Could not locate scratch/ns-3-ub-tools")


add_tools_path()

import net_sim_builder as netsim
import networkx as nx
from net_sim_builder import check_route_table_connectivity, validate_route_table_no_conflicts
from route_compaction import compact_route_rows


HOST_FORWARD_DELAY = "1ns"
ACCESS_FORWARD_DELAY = "1ns"
L1_FORWARD_DELAY = "225ns"
L2_FORWARD_DELAY = "225ns"
HOST_ACCESS_LINK_DELAY = "0ns"
ACCESS_L1_LINK_DELAY = "10ns"
L1_L2_LINK_DELAY = "150ns"
HOST_ACCESS_LINK_BW = "6000Gbps"
ACCESS_L1_LINK_BW = "224Gbps"
L1_L2_LINK_BW = "448Gbps"
ROUTE_PRIORITIES = [7, 8]


@dataclass(frozen=True)
class TopologyParams:
    pod_num: int = 19
    node_per_pod: int = 9
    npu_per_node: int = 8
    l1_switch_per_pod: int = 24
    l2_plane_num: int = 24
    l2_switch_per_plane: int = 4
    l1_to_each_l2_ports: int = 9
    host_to_access_ports: int = 1
    access_to_each_l1_ports: int = 1


@dataclass(frozen=True)
class IdLayout:
    host_num: int
    access_base_id: int
    l1_base_id: int
    l2_base_id: int
    access_switch_num: int
    l1_switch_num: int
    l2_switch_num: int

    @property
    def total_node_num(self) -> int:
        return self.host_num + self.access_switch_num + self.l1_switch_num + self.l2_switch_num


def all_shortest_paths(graph, source, target):
    try:
        return nx.all_shortest_paths(graph, source, target)
    except nx.NetworkXNoPath:
        return []


def validate_params(params: TopologyParams) -> None:
    for field_name, value in vars(params).items():
        if value <= 0:
            raise ValueError(f"{field_name} must be positive")
    if params.l1_switch_per_pod != params.l2_plane_num:
        raise ValueError("l1_switch_per_pod must match l2_plane_num")


def build_id_layout(params: TopologyParams) -> IdLayout:
    validate_params(params)
    host_num = params.pod_num * params.node_per_pod * params.npu_per_node
    access_switch_num = host_num
    l1_switch_num = params.pod_num * params.l1_switch_per_pod
    l2_switch_num = params.l2_plane_num * params.l2_switch_per_plane
    access_base_id = host_num
    l1_base_id = access_base_id + access_switch_num
    l2_base_id = l1_base_id + l1_switch_num
    return IdLayout(
        host_num=host_num,
        access_base_id=access_base_id,
        l1_base_id=l1_base_id,
        l2_base_id=l2_base_id,
        access_switch_num=access_switch_num,
        l1_switch_num=l1_switch_num,
        l2_switch_num=l2_switch_num,
    )


def npu_id(params: TopologyParams, pod_id: int, node_id: int, npu_id_in_node: int) -> int:
    return (pod_id * params.node_per_pod + node_id) * params.npu_per_node + npu_id_in_node


def access_switch_id(layout: IdLayout, host_id: int) -> int:
    return layout.access_base_id + host_id


def host_id_for_access(layout: IdLayout, access_id: int) -> int:
    return access_id - layout.access_base_id


def l1_switch_id(params: TopologyParams, layout: IdLayout, pod_id: int, plane_id: int) -> int:
    return layout.l1_base_id + pod_id * params.l1_switch_per_pod + plane_id


def l2_switch_id(params: TopologyParams, layout: IdLayout, l2_idx: int) -> int:
    return layout.l2_base_id + l2_idx


def format_range(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}..{end}"


def hosts_per_pod(params: TopologyParams) -> int:
    return params.node_per_pod * params.npu_per_node


def host_range_for_pod(params: TopologyParams, pod_id: int) -> tuple[int, int]:
    start = pod_id * hosts_per_pod(params)
    return start, start + hosts_per_pod(params) - 1


def l1_ids_for_pod(params: TopologyParams, layout: IdLayout, pod_id: int) -> list[int]:
    start = layout.l1_base_id + pod_id * params.l1_switch_per_pod
    return list(range(start, start + params.l1_switch_per_pod))


def pod_id_for_host(params: TopologyParams, host_id: int) -> int:
    return host_id // hosts_per_pod(params)


def pod_id_for_l1(params: TopologyParams, layout: IdLayout, l1_id: int) -> int:
    return (l1_id - layout.l1_base_id) // params.l1_switch_per_pod


def ports_text(port_values: list[int]) -> str:
    return " ".join(str(port) for port in sorted(set(port_values)))


def metrics_text(metric: int, port_values: list[int]) -> str:
    return " ".join(str(metric) for _ in sorted(set(port_values)))


def append_route(
    rows: list[tuple[str, str, int, str, str]],
    node_id: int | str,
    dst_id: int | str,
    dst_port: int,
    out_ports: list[int],
    metric: int,
) -> None:
    if not out_ports:
        return
    normalized_ports = sorted(set(out_ports))
    rows.append((
        str(node_id),
        str(dst_id),
        dst_port,
        ports_text(normalized_ports),
        metrics_text(metric, normalized_ports),
    ))


def append_host_ranges_excluding_self(
    rows: list[tuple[str, str, int, str, str]],
    node_id: int,
    host_id: int,
    start: int,
    end: int,
    dst_port: int,
    out_ports: list[int],
    metric: int,
) -> None:
    if start <= host_id - 1:
        append_route(rows, node_id, format_range(start, host_id - 1), dst_port, out_ports, metric)
    if host_id + 1 <= end:
        append_route(rows, node_id, format_range(host_id + 1, end), dst_port, out_ports, metric)


def l1_l2_neighbors(graph: netsim.NetworkSimulationGraph, layout: IdLayout) -> dict[int, set[int]]:
    neighbors = {}
    for l1_id in range(layout.l1_base_id, layout.l2_base_id):
        neighbors[l1_id] = {
            node_id
            for node_id in graph.neighbors(l1_id)
            if layout.l2_base_id <= node_id < layout.total_node_num
        }
    return neighbors


def l2_l1_neighbors_by_pod(
    graph: netsim.NetworkSimulationGraph,
    params: TopologyParams,
    layout: IdLayout,
) -> dict[int, dict[int, list[int]]]:
    neighbors: dict[int, dict[int, list[int]]] = {}
    for l2_id in range(layout.l2_base_id, layout.total_node_num):
        by_pod: dict[int, list[int]] = {}
        for node_id in graph.neighbors(l2_id):
            if layout.l1_base_id <= node_id < layout.l2_base_id:
                by_pod.setdefault(pod_id_for_l1(params, layout, node_id), []).append(node_id)
        neighbors[l2_id] = {pod_id: sorted(l1_ids) for pod_id, l1_ids in by_pod.items()}
    return neighbors


def access_to_l1_ports(
    graph: netsim.NetworkSimulationGraph,
    access_id: int,
    l1_ids: list[int],
) -> list[int]:
    out_ports: list[int] = []
    for l1_id in l1_ids:
        out_ports.extend(graph.get_link_ports(access_id, l1_id))
    return out_ports


def l1_ports_reaching_pod(
    graph: netsim.NetworkSimulationGraph,
    params: TopologyParams,
    layout: IdLayout,
    src_l1_id: int,
    dst_pod: int,
    l1_to_l2: dict[int, set[int]],
) -> list[int]:
    dst_l2_ids: set[int] = set()
    for dst_l1_id in l1_ids_for_pod(params, layout, dst_pod):
        dst_l2_ids.update(l1_to_l2[dst_l1_id])

    out_ports: list[int] = []
    for l2_id in sorted(l1_to_l2[src_l1_id] & dst_l2_ids):
        out_ports.extend(graph.get_link_ports(src_l1_id, l2_id))
    return out_ports


def access_ports_reaching_pod(
    graph: netsim.NetworkSimulationGraph,
    params: TopologyParams,
    layout: IdLayout,
    access_id: int,
    src_pod: int,
    dst_pod: int,
    l1_to_l2: dict[int, set[int]],
) -> list[int]:
    out_ports: list[int] = []
    for src_l1_id in l1_ids_for_pod(params, layout, src_pod):
        if l1_ports_reaching_pod(graph, params, layout, src_l1_id, dst_pod, l1_to_l2):
            out_ports.extend(graph.get_link_ports(access_id, src_l1_id))
    return out_ports


def write_pod1d_compressed_route_table(
    graph: netsim.NetworkSimulationGraph,
    params: TopologyParams,
    layout: IdLayout,
) -> list[tuple[str, str, int, str, str]]:
    if graph.next_hop_ports == []:
        graph.build_graph_config()

    rows: list[tuple[str, str, int, str, str]] = []
    l1_to_l2 = l1_l2_neighbors(graph, layout)
    l2_to_l1_by_pod = l2_l1_neighbors_by_pod(graph, params, layout)

    # Hosts have exactly one access-facing port. Host destinations always use dstPortId 0.
    for src_host in range(layout.host_num):
        src_pod = pod_id_for_host(params, src_host)
        src_access = access_switch_id(layout, src_host)
        out_ports = graph.get_link_ports(src_host, src_access)
        local_start, local_end = host_range_for_pod(params, src_pod)
        append_host_ranges_excluding_self(
            rows,
            src_host,
            src_host,
            local_start,
            local_end,
            0,
            out_ports,
            4,
        )
        for dst_pod in range(params.pod_num):
            if dst_pod == src_pod:
                continue
            dst_start, dst_end = host_range_for_pod(params, dst_pod)
            append_route(rows, src_host, format_range(dst_start, dst_end), 0, out_ports, 6)

    # Access switches route to their attached host directly and otherwise fan out to L1.
    for access_id in range(layout.access_base_id, layout.l1_base_id):
        host_id = host_id_for_access(layout, access_id)
        src_pod = pod_id_for_host(params, host_id)
        local_start, local_end = host_range_for_pod(params, src_pod)
        local_l1_ids = l1_ids_for_pod(params, layout, src_pod)
        local_l1_ports = access_to_l1_ports(graph, access_id, local_l1_ids)

        append_route(rows, access_id, host_id, 0, graph.get_link_ports(access_id, host_id), 1)
        append_host_ranges_excluding_self(
            rows,
            access_id,
            host_id,
            local_start,
            local_end,
            0,
            local_l1_ports,
            3,
        )
        for dst_pod in range(params.pod_num):
            if dst_pod == src_pod:
                continue
            dst_start, dst_end = host_range_for_pod(params, dst_pod)
            out_ports = access_ports_reaching_pod(
                graph,
                params,
                layout,
                access_id,
                src_pod,
                dst_pod,
                l1_to_l2,
            )
            append_route(rows, access_id, format_range(dst_start, dst_end), 0, out_ports, 5)

    # L1 switches route to local access switches or up to L2 for remote pods.
    for src_l1_id in range(layout.l1_base_id, layout.l2_base_id):
        src_pod = pod_id_for_l1(params, layout, src_l1_id)
        local_host_start, local_host_end = host_range_for_pod(params, src_pod)
        for dst_host in range(local_host_start, local_host_end + 1):
            dst_access = access_switch_id(layout, dst_host)
            append_route(
                rows,
                src_l1_id,
                dst_host,
                0,
                graph.get_link_ports(src_l1_id, dst_access),
                2,
            )

        for dst_pod in range(params.pod_num):
            if dst_pod == src_pod:
                continue
            dst_start, dst_end = host_range_for_pod(params, dst_pod)
            out_ports = l1_ports_reaching_pod(
                graph,
                params,
                layout,
                src_l1_id,
                dst_pod,
                l1_to_l2,
            )
            append_route(rows, src_l1_id, format_range(dst_start, dst_end), 0, out_ports, 4)

    # L2 switches descend to every L1 in the destination pod that they can reach.
    for l2_id in range(layout.l2_base_id, layout.total_node_num):
        for dst_pod, dst_l1_ids in l2_to_l1_by_pod[l2_id].items():
            dst_start, dst_end = host_range_for_pod(params, dst_pod)
            out_ports: list[int] = []
            for dst_l1_id in dst_l1_ids:
                out_ports.extend(graph.get_link_ports(l2_id, dst_l1_id))
            append_route(rows, l2_id, format_range(dst_start, dst_end), 0, out_ports, 3)

    rows = compact_route_rows(rows)
    route_path = Path(graph.output_dir) / "routing_table.csv"
    route_path.parent.mkdir(parents=True, exist_ok=True)
    with route_path.open("w", encoding="utf-8") as f:
        f.write("nodeId,dstNodeId,dstPortId,outPorts,metrics\n")
        for row in rows:
            f.write(",".join(map(str, row)) + "\n")

    print(f"Pod1D compressed route table: {route_path.resolve()}")
    validate_route_table_no_conflicts(os.fspath(route_path))
    if not check_route_table_connectivity(os.fspath(route_path)):
        raise ValueError("Pod1D compressed route table is incomplete")
    graph._route_table_requires_on_demand_tp = True
    return rows


def build_graph(params: TopologyParams = TopologyParams()) -> tuple[netsim.NetworkSimulationGraph, IdLayout]:
    layout = build_id_layout(params)
    graph = netsim.NetworkSimulationGraph()

    for host_id in range(layout.host_num):
        graph.add_netisim_host(host_id, forward_delay=HOST_FORWARD_DELAY)

    for switch_id in range(layout.access_base_id, layout.l1_base_id):
        graph.add_netisim_node(switch_id, forward_delay=ACCESS_FORWARD_DELAY)

    for switch_id in range(layout.l1_base_id, layout.l2_base_id):
        graph.add_netisim_node(switch_id, forward_delay=L1_FORWARD_DELAY)

    for switch_id in range(layout.l2_base_id, layout.total_node_num):
        graph.add_netisim_node(switch_id, forward_delay=L2_FORWARD_DELAY)

    for host_id in range(layout.host_num):
        graph.add_netisim_edge(
            host_id,
            access_switch_id(layout, host_id),
            bandwidth=HOST_ACCESS_LINK_BW,
            delay=HOST_ACCESS_LINK_DELAY,
            edge_count=params.host_to_access_ports,
        )

    for pod_id in range(params.pod_num):
        host_start, host_end = host_range_for_pod(params, pod_id)
        for host_id in range(host_start, host_end + 1):
            access_id = access_switch_id(layout, host_id)
            for plane_id in range(params.l1_switch_per_pod):
                graph.add_netisim_edge(
                    access_id,
                    l1_switch_id(params, layout, pod_id, plane_id),
                    bandwidth=ACCESS_L1_LINK_BW,
                    delay=ACCESS_L1_LINK_DELAY,
                    edge_count=params.access_to_each_l1_ports,
                )

    for l1_idx, l1_id in enumerate(range(layout.l1_base_id, layout.l2_base_id)):
        plane_id = l1_idx % params.l2_plane_num
        for plane_l2_offset in range(params.l2_switch_per_plane):
            l2_idx = plane_id * params.l2_switch_per_plane + plane_l2_offset
            graph.add_netisim_edge(
                l1_id,
                l2_switch_id(params, layout, l2_idx),
                bandwidth=L1_L2_LINK_BW,
                delay=L1_L2_LINK_DELAY,
                edge_count=params.l1_to_each_l2_ports,
            )

    return graph, layout


def clean_outputs(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for file_name in (
        "node.csv",
        "topology.csv",
        "routing_table.csv",
        "transport_channel.csv",
    ):
        path = output_dir / file_name
        if path.exists():
            path.unlink()


def write_case(
    output_dir: Path,
    params: TopologyParams = TopologyParams(),
    route_mode: str = "none",
    route_workers: int = 1,
    include_transport: bool = False,
) -> tuple[netsim.NetworkSimulationGraph, IdLayout]:
    if route_mode not in {"none", "compressed", "exact"}:
        raise ValueError("route_mode must be one of: none, compressed, exact")
    if include_transport and route_mode != "exact":
        raise ValueError("include_transport requires route_mode=exact")

    clean_outputs(output_dir)
    graph, layout = build_graph(params)
    graph.output_dir = os.fspath(output_dir)
    graph.build_graph_config()

    if route_mode == "compressed":
        write_pod1d_compressed_route_table(graph, params, layout)
        graph.write_config(include_transport=False)
    elif route_mode == "exact":
        graph.gen_route_table(
            host_router=True,
            path_finding_algo=all_shortest_paths,
            multiple_workers=route_workers,
        )
        graph.config_transport_channel(ROUTE_PRIORITIES)
        graph.write_config(include_transport=include_transport)
    else:
        graph.write_config(include_transport=False)

    return graph, layout


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("output/pod1d"))
    parser.add_argument("--route-mode", choices=["none", "compressed", "exact"], default="none")
    parser.add_argument("--route-workers", type=int, default=1)
    parser.add_argument("--include-transport", action="store_true")
    parser.add_argument("--pod-num", type=int, default=TopologyParams.pod_num)
    parser.add_argument("--node-per-pod", type=int, default=TopologyParams.node_per_pod)
    parser.add_argument("--npu-per-node", type=int, default=TopologyParams.npu_per_node)
    parser.add_argument("--l1-switch-per-pod", type=int, default=TopologyParams.l1_switch_per_pod)
    parser.add_argument("--l2-plane-num", type=int, default=TopologyParams.l2_plane_num)
    parser.add_argument("--l2-switch-per-plane", type=int, default=TopologyParams.l2_switch_per_plane)
    parser.add_argument("--l1-to-each-l2-ports", type=int, default=TopologyParams.l1_to_each_l2_ports)
    parser.add_argument("--host-to-access-ports", type=int, default=TopologyParams.host_to_access_ports)
    parser.add_argument("--access-to-each-l1-ports", type=int, default=TopologyParams.access_to_each_l1_ports)
    return parser.parse_args()


def params_from_args(args: argparse.Namespace) -> TopologyParams:
    return TopologyParams(
        pod_num=args.pod_num,
        node_per_pod=args.node_per_pod,
        npu_per_node=args.npu_per_node,
        l1_switch_per_pod=args.l1_switch_per_pod,
        l2_plane_num=args.l2_plane_num,
        l2_switch_per_plane=args.l2_switch_per_plane,
        l1_to_each_l2_ports=args.l1_to_each_l2_ports,
        host_to_access_ports=args.host_to_access_ports,
        access_to_each_l1_ports=args.access_to_each_l1_ports,
    )


def main() -> None:
    args = parse_args()
    params = params_from_args(args)
    graph, layout = write_case(
        output_dir=args.output_dir,
        params=params,
        route_mode=args.route_mode,
        route_workers=args.route_workers,
        include_transport=args.include_transport,
    )
    expanded_link_num = sum(data["edge_count"] for _, _, data in graph.edges(data=True))
    print(
        "Pod1D topology: "
        f"hosts={layout.host_num}, "
        f"access={layout.access_switch_num}, "
        f"l1={layout.l1_switch_num}, "
        f"l2={layout.l2_switch_num}, "
        f"total_nodes={layout.total_node_num}, "
        f"links={expanded_link_num}, "
        f"output={args.output_dir.resolve()}"
    )


if __name__ == "__main__":
    main()
