#!/usr/bin/env python3
"""Generate pod1d cases for ns-3 and NetiSim with the original platform builders."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
NETISIM_TOOLS_DIR = TOOLS_DIR / "netisim_files" / "tools"
NS3_TOOLS_DIR = TOOLS_DIR / "ns-3-ub-tools"
for import_dir in (NETISIM_TOOLS_DIR, NS3_TOOLS_DIR):
    import_dir_str = str(import_dir)
    if import_dir_str not in sys.path:
        sys.path.insert(0, import_dir_str)

import netisim_graph
import net_sim_builder as netsim


FORWARD_DELAY = "1ns"
ACCESS_FORWARD_DELAY = "0ns"
LINK_DELAY = "20ns"
NS3_NODE_LINK_BW = "400Gbps"
NS3_HOST_ACCESS_LINK_BW = "400Gbps"
NS3_L1_LINK_BW = "112Gbps"
NS3_L2_LINK_BW = "224Gbps"
NETISIM_NODE_LINK_BW = "400"
NETISIM_HOST_ACCESS_LINK_BW = "2688"
NETISIM_L1_LINK_BW = "112"
NETISIM_L2_LINK_BW = "224"
NETISIM_LINK_DELAY = "10"
NETISIM_HOST_ACCESS_LINK_DELAY = "0"
NETISIM_NODE_GEN_BW = "2688"
NETISIM_HOST_COMP_DELAY = 0
NETISIM_ACCESS_COMP_DELAY = 225
NETISIM_SWITCH_COMP_DELAY = 225
TRAFFIC_BYTES_PER_TASK = 8 * 1024 * 1024
TRAFFIC_PRIORITY = 7
TRAFFIC_DELAY = "10ns"
ROUTE_PRIORITIES = [7, 8]
DEFAULT_OUTPUT_ROOT = TOOLS_DIR / "generated_cases" / "case01"
DEFAULT_NETISIM_TEMPLATE = TOOLS_DIR / "netisim_files" / "case01" / "dcn2.0_config.xml"
NETISIM_FAULT_NONE = "none"
NETISIM_FAULT_HALF_BANDWIDTH = "npu0_l1_bw56"
NETISIM_FAULT_REMOVED = "npu0_l1_removed"
NETISIM_FAULT_CHOICES = (
    NETISIM_FAULT_NONE,
    NETISIM_FAULT_HALF_BANDWIDTH,
    NETISIM_FAULT_REMOVED,
)


@dataclass(frozen=True)
class TopologyParams:
    pod_num: int = 19
    node_per_pod: int = 9
    npu_per_node: int = 8
    l1_switch_per_pod: int = 24
    l2_plane_num: int = 24
    l2_switch_per_plane: int = 4
    l1_to_each_l2_ports: int = 9
    host_to_each_l1_ports: int = 1


@dataclass(frozen=True)
class IdLayout:
    host_num: int
    access_base_id: int
    l1_base_id: int
    l2_base_id: int
    access_switch_num: int
    l1_switch_num: int
    l2_switch_num: int


@dataclass(frozen=True)
class TopologyIds:
    host_ids: list[int]
    switch_groups: dict[str, list[int]]


def build_id_layout(params: TopologyParams) -> IdLayout:
    if params.l1_switch_per_pod != params.l2_plane_num:
        raise ValueError("l1_switch_per_pod must match l2_plane_num")

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


def host_egress_count(params: TopologyParams) -> int:
    return 1


def npu_id(params: TopologyParams, pod_id: int, node_id: int, npu_id_in_node: int) -> int:
    return (pod_id * params.node_per_pod + node_id) * params.npu_per_node + npu_id_in_node


def node_offset(params: TopologyParams, pod_id: int, node_id: int) -> int:
    return pod_id * params.node_per_pod + node_id


def l1_switch_id(params: TopologyParams, layout: IdLayout, pod_id: int, plane_id: int) -> int:
    return layout.l1_base_id + pod_id * params.l1_switch_per_pod + plane_id


def access_switch_id(layout: IdLayout, host_id: int) -> int:
    return layout.access_base_id + host_id


def l2_switch_id(params: TopologyParams, layout: IdLayout, plane_id: int, switch_id_in_plane: int) -> int:
    return layout.l2_base_id + plane_id * params.l2_switch_per_plane + switch_id_in_plane


def build_ns3_graph(params: TopologyParams = TopologyParams(), fault: str | None = None):
    graph = netsim.NetworkSimulationGraph()
    ids = populate_topology(graph, "ns3", params, fault=fault)
    return graph, ids


def build_netisim_graph(params: TopologyParams = TopologyParams(), fault: str | None = None):
    graph = netisim_graph.NetiSimGraph()
    ids = populate_topology(graph, "netisim", params, fault=fault)
    return graph, ids


def populate_topology(graph, platform: str, params: TopologyParams, fault: str | None = None) -> TopologyIds:
    fault = normalize_fault(fault)
    layout = build_id_layout(params)
    host_ids = list(range(layout.host_num))
    switch_groups = {
        "access": list(range(layout.access_base_id, layout.access_base_id + layout.access_switch_num)),
        "l1": list(range(layout.l1_base_id, layout.l1_base_id + layout.l1_switch_num)),
        "l2": list(range(layout.l2_base_id, layout.l2_base_id + layout.l2_switch_num)),
    }

    for host_id in host_ids:
        add_host(graph, platform, host_id)

    for switch_id in switch_groups["access"]:
        add_access_switch(graph, platform, switch_id)

    for group_name in ("l1", "l2"):
        for switch_id in switch_groups[group_name]:
            add_switch(graph, platform, switch_id)

    for host_id in host_ids:
        add_edge(
            graph,
            platform,
            host_id,
            access_switch_id(layout, host_id),
            ns3_bandwidth=NS3_HOST_ACCESS_LINK_BW,
            netisim_bandwidth=NETISIM_HOST_ACCESS_LINK_BW,
            ns3_delay=ACCESS_FORWARD_DELAY,
            netisim_delay=NETISIM_HOST_ACCESS_LINK_DELAY,
            route_weight=0,
        )

    for pod_id in range(params.pod_num):
        for node_id in range(params.node_per_pod):
            for npu_id_in_node in range(params.npu_per_node):
                host_id = npu_id(params, pod_id, node_id, npu_id_in_node)
                access_id = access_switch_id(layout, host_id)
                for plane_id in range(params.l1_switch_per_pod):
                    if fault == NETISIM_FAULT_REMOVED and host_id == 0 and plane_id == 0:
                        continue
                    netisim_bandwidth = NETISIM_L1_LINK_BW
                    ns3_bandwidth = NS3_L1_LINK_BW
                    if fault == NETISIM_FAULT_HALF_BANDWIDTH and host_id == 0 and plane_id == 0:
                        netisim_bandwidth = "56"
                        ns3_bandwidth = "56Gbps"
                    add_edge(
                        graph,
                        platform,
                        access_id,
                        l1_switch_id(params, layout, pod_id, plane_id),
                        ns3_bandwidth=ns3_bandwidth,
                        netisim_bandwidth=netisim_bandwidth,
                        edge_count=params.host_to_each_l1_ports,
                        route_weight=10,
                    )

    l1_uplink_ports = params.l2_switch_per_plane * params.l1_to_each_l2_ports
    for l1_idx, l1_id in enumerate(switch_groups["l1"]):
        for uplink_idx in range(l1_uplink_ports):
            l2_idx = (l1_idx * l1_uplink_ports + uplink_idx) % layout.l2_switch_num
            add_edge(
                graph,
                platform,
                l1_id,
                layout.l2_base_id + l2_idx,
                ns3_bandwidth=NS3_L2_LINK_BW,
                netisim_bandwidth=NETISIM_L2_LINK_BW,
                edge_count=1,
                route_weight=1,
            )

    return TopologyIds(host_ids=host_ids, switch_groups=switch_groups)


def normalize_fault(fault: str | None) -> str:
    if fault is None:
        return NETISIM_FAULT_NONE
    if fault not in NETISIM_FAULT_CHOICES:
        raise ValueError(f"fault must be one of: {', '.join(NETISIM_FAULT_CHOICES)}")
    return fault


def add_host(graph, platform: str, host_id: int) -> None:
    if platform == "ns3":
        graph.add_netisim_host(host_id, forward_delay=FORWARD_DELAY)
    elif platform == "netisim":
        graph.add_netisim_host(host_id, comp_delay=NETISIM_HOST_COMP_DELAY)
    else:
        raise ValueError(f"unsupported platform: {platform}")


def add_switch(graph, platform: str, switch_id: int) -> None:
    if platform == "ns3":
        graph.add_netisim_node(switch_id, forward_delay=FORWARD_DELAY)
    elif platform == "netisim":
        graph.add_netisim_node(switch_id, comp_delay=NETISIM_SWITCH_COMP_DELAY)
    else:
        raise ValueError(f"unsupported platform: {platform}")


def add_access_switch(graph, platform: str, switch_id: int) -> None:
    if platform == "ns3":
        graph.add_netisim_node(switch_id, forward_delay=ACCESS_FORWARD_DELAY)
    elif platform == "netisim":
        graph.add_netisim_node(switch_id, comp_delay=NETISIM_ACCESS_COMP_DELAY)
    else:
        raise ValueError(f"unsupported platform: {platform}")


def add_edge(
    graph,
    platform: str,
    src: int,
    dst: int,
    ns3_bandwidth: str,
    netisim_bandwidth: str,
    ns3_delay: str = LINK_DELAY,
    netisim_delay: str = NETISIM_LINK_DELAY,
    edge_count: int = 1,
    route_weight: int = 1,
) -> None:
    if platform == "ns3":
        graph.add_netisim_edge(
            src,
            dst,
            bandwidth=ns3_bandwidth,
            delay=ns3_delay,
            edge_count=edge_count,
            route_weight=route_weight,
        )
    elif platform == "netisim":
        graph.add_netisim_edge(
            src,
            dst,
            bandwidth=netisim_bandwidth,
            delay=netisim_delay,
            edge_count=edge_count,
            route_weight=route_weight,
        )
    else:
        raise ValueError(f"unsupported platform: {platform}")


def write_ns3_case(output_dir: Path, params: TopologyParams, route_workers: int) -> None:
    clean_outputs(output_dir, [
        "node.csv",
        "topology.csv",
        "routing_table.csv",
        "transport_channel.csv",
        "traffic.csv",
        "network_attribute.txt",
    ])

    graph, ids = build_ns3_graph(params)
    graph.output_dir = os.fspath(output_dir)
    graph.build_graph_config()
    graph.gen_route_table(
        host_router=True,
        multiple_workers=route_workers,
    )
    graph.config_transport_channel(priority_list=ROUTE_PRIORITIES)
    graph.write_config()
    write_traffic_csv(output_dir, ids)
    clean_outputs(output_dir, ["network_attribute.txt"])


def write_netisim_case(
    output_dir: Path,
    params: TopologyParams,
    template_path: Path,
    route_workers: int,
    fault: str | None = None,
) -> None:
    clean_outputs(output_dir, ["dcn2.0_config.xml", "router.xml", "rdma_operate.txt"])

    graph, ids = build_netisim_graph(params, fault=fault)
    graph.output_dir = output_dir_with_sep(output_dir)
    graph.build_graph_config(
        os.fspath(template_path),
        node_gen_bandwidth=NETISIM_NODE_GEN_BW,
        node_gen_delay=NETISIM_LINK_DELAY,
        direct_topo=False,
        output_name="dcn2.0_config.xml",
    )
    graph.gen_route_table(
        host_router=False,
        multiple_workers=route_workers,
    )
    write_rdma_operate_txt(output_dir, ids)


def write_traffic_csv(output_dir: Path, ids: TopologyIds, bytes_per_task: int = TRAFFIC_BYTES_PER_TASK) -> None:
    traffic_path = output_dir / "traffic.csv"
    half_host_num = len(ids.host_ids) // 2

    with traffic_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "taskId",
            "sourceNodeId",
            "destNodeId",
            "dataSize(Byte)",
            "opType",
            "priority",
            "delay",
            "phaseId",
            "dependOnPhases",
        ])
        for task_id, source in enumerate(range(half_host_num)):
            writer.writerow([
                task_id,
                source,
                source + half_host_num,
                bytes_per_task,
                "URMA_WRITE",
                TRAFFIC_PRIORITY,
                TRAFFIC_DELAY,
                0,
                "",
            ])


def write_rdma_operate_txt(output_dir: Path, ids: TopologyIds, bytes_per_task: int = TRAFFIC_BYTES_PER_TASK) -> None:
    rdma_path = output_dir / "rdma_operate.txt"
    half_host_num = len(ids.host_ids) // 2

    with rdma_path.open("w", encoding="utf-8") as f:
        f.write("stat rdma operate:\n")
        f.write("phase\n")
        for source in range(half_host_num):
            f.write(
                "Type:rdma_send, "
                f"src_node:{source}, src_port:0, "
                f"dst_node:{source + half_host_num}, dst_port:0, "
                f"priority:{TRAFFIC_PRIORITY}, msg_len:{bytes_per_task}\n"
            )


def clean_outputs(output_dir: Path, file_names: list[str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for file_name in file_names:
        path = output_dir / file_name
        if path.exists():
            path.unlink()


def output_dir_with_sep(output_dir: Path) -> str:
    path = os.fspath(output_dir)
    return path if path.endswith(os.sep) else path + os.sep


def case_dirs(output_root: Path) -> dict[str, Path]:
    return {
        "ns3": output_root / "ns3",
        "netisim": output_root / "netisim",
    }


def generate_cases(
    target: str = "both",
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    template_path: Path | str = DEFAULT_NETISIM_TEMPLATE,
    route_workers: int = 1,
    params: TopologyParams = TopologyParams(),
    fault: str | None = None,
) -> dict[str, Path]:
    if target not in {"ns3", "netisim", "both"}:
        raise ValueError("target must be one of: ns3, netisim, both")
    fault = normalize_fault(fault)

    dirs = case_dirs(Path(output_root))
    generated: dict[str, Path] = {}

    if target in {"ns3", "both"}:
        write_ns3_case(dirs["ns3"], params, route_workers)
        generated["ns3"] = dirs["ns3"]

    if target in {"netisim", "both"}:
        write_netisim_case(dirs["netisim"], params, Path(template_path), route_workers, fault=fault)
        generated["netisim"] = dirs["netisim"]

    return generated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["ns3", "netisim", "both"], default="both")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--netisim-template", type=Path, default=DEFAULT_NETISIM_TEMPLATE)
    parser.add_argument("--route-workers", type=int, default=1)
    parser.add_argument("--fault", choices=NETISIM_FAULT_CHOICES, default=NETISIM_FAULT_NONE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generated = generate_cases(
        target=args.target,
        output_root=args.output_root,
        template_path=args.netisim_template,
        route_workers=args.route_workers,
        fault=args.fault,
    )
    for case_type, path in generated.items():
        print(f"{case_type}: {path.resolve()}")


if __name__ == "__main__":
    main()
