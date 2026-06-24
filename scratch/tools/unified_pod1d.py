#!/usr/bin/env python3
"""Generate matching ns-3 and NetiSim cases by reusing both original builders."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import networkx as nx
from lxml import etree


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
LINK_DELAY = "20ns"
TRAFFIC_BYTES_PER_TASK = 8 * 1024 * 1024
TRAFFIC_PRIORITY = 7
TRAFFIC_DELAY = "10ns"
DEFAULT_OUTPUT_ROOT = TOOLS_DIR / "generated_cases" / "pod1d"
DEFAULT_NETISIM_TEMPLATE = TOOLS_DIR / "netisim_files" / "case01" / "dcn2.0_config.xml"


@dataclass(frozen=True)
class TopologyParams:
    pod_num: int = 19
    node_per_pod: int = 9
    npu_per_node: int = 8
    sw1650_per_node: int = 2
    sw1825_per_node: int = 4
    l1_switch_per_pod: int = 24
    l2_plane_num: int = 24
    l2_switch_per_plane: int = 4
    l1_to_each_l2_ports: int = 9


@dataclass(frozen=True)
class TopologyIds:
    host_ids: list[int]
    switch_groups: dict[str, list[int]]

    @property
    def switch_ids(self) -> list[int]:
        ids: list[int] = []
        for group_ids in self.switch_groups.values():
            ids.extend(group_ids)
        return ids


@dataclass(frozen=True)
class IdLayout:
    host_num: int
    sw1825_base_id: int
    sw1650_base_id: int
    l1_base_id: int
    l2_base_id: int
    sw1825_num: int
    sw1650_num: int
    l1_switch_num: int
    l2_switch_num: int
    sw1650_port_num: int
    sw1825_port_num: int


def build_ns3_graph(params: TopologyParams = TopologyParams()):
    graph = netsim.NetworkSimulationGraph()
    ids = populate_topology(graph, "ns3", params)
    return graph, ids


def build_netisim_graph(params: TopologyParams = TopologyParams()):
    graph = netisim_graph.NetiSimGraph()
    ids = populate_topology(graph, "netisim", params)
    return graph, ids


def populate_topology(graph, target: str, params: TopologyParams) -> TopologyIds:
    layout = build_id_layout(params)

    host_ids = list(range(layout.host_num))
    switch_groups = {
        "sw1825": list(range(layout.sw1825_base_id, layout.sw1825_base_id + layout.sw1825_num)),
        "sw1650": list(range(layout.sw1650_base_id, layout.sw1650_base_id + layout.sw1650_num)),
        "l1": list(range(layout.l1_base_id, layout.l1_base_id + layout.l1_switch_num)),
        "l2": list(range(layout.l2_base_id, layout.l2_base_id + layout.l2_switch_num)),
    }

    for host_id in host_ids:
        add_host(graph, target, host_id)

    for switch_id in switch_groups["sw1825"] + switch_groups["sw1650"] + switch_groups["l1"] + switch_groups["l2"]:
        add_switch(graph, target, switch_id)

    for pod_id in range(params.pod_num):
        for node_id in range(params.node_per_pod):
            for npu_id_in_node in range(params.npu_per_node):
                host_id = npu_id(params, pod_id, node_id, npu_id_in_node)
                add_edge(
                    graph,
                    target,
                    host_id,
                    sw1650_id(params, layout, pod_id, node_id, npu_id_in_node // layout.sw1650_port_num),
                    ns3_bandwidth="400Gbps",
                    netisim_bandwidth="400",
                )
                add_edge(
                    graph,
                    target,
                    host_id,
                    sw1825_id(params, layout, pod_id, node_id, npu_id_in_node // layout.sw1825_port_num),
                    ns3_bandwidth="400Gbps",
                    netisim_bandwidth="400",
                )

    for pod_id in range(params.pod_num):
        for node_id in range(params.node_per_pod):
            for npu_id_in_node in range(params.npu_per_node):
                host_id = npu_id(params, pod_id, node_id, npu_id_in_node)
                for plane_id in range(params.l1_switch_per_pod):
                    add_edge(
                        graph,
                        target,
                        host_id,
                        l1_switch_id(params, layout, pod_id, plane_id),
                        ns3_bandwidth="112Gbps",
                        netisim_bandwidth="112",
                    )

    for pod_id in range(params.pod_num):
        for plane_id in range(params.l2_plane_num):
            l1_id = l1_switch_id(params, layout, pod_id, plane_id)
            for switch_id_in_plane in range(params.l2_switch_per_plane):
                add_edge(
                    graph,
                    target,
                    l1_id,
                    l2_switch_id(params, layout, plane_id, switch_id_in_plane),
                    ns3_bandwidth="224Gbps",
                    netisim_bandwidth="224",
                    edge_count=params.l1_to_each_l2_ports,
                )

    return TopologyIds(host_ids, switch_groups)


def build_id_layout(params: TopologyParams) -> IdLayout:
    if params.npu_per_node % params.sw1650_per_node != 0:
        raise ValueError("npu_per_node must be divisible by sw1650_per_node")
    if params.npu_per_node % params.sw1825_per_node != 0:
        raise ValueError("npu_per_node must be divisible by sw1825_per_node")
    if params.l1_switch_per_pod != params.l2_plane_num:
        raise ValueError("l1_switch_per_pod must match l2_plane_num")

    host_num = params.pod_num * params.node_per_pod * params.npu_per_node
    sw1825_num = params.pod_num * params.node_per_pod * params.sw1825_per_node
    sw1650_num = params.pod_num * params.node_per_pod * params.sw1650_per_node
    l1_switch_num = params.pod_num * params.l1_switch_per_pod
    l2_switch_num = params.l2_plane_num * params.l2_switch_per_plane
    sw1825_base_id = host_num
    sw1650_base_id = sw1825_base_id + sw1825_num
    l1_base_id = sw1650_base_id + sw1650_num
    l2_base_id = l1_base_id + l1_switch_num

    return IdLayout(
        host_num=host_num,
        sw1825_base_id=sw1825_base_id,
        sw1650_base_id=sw1650_base_id,
        l1_base_id=l1_base_id,
        l2_base_id=l2_base_id,
        sw1825_num=sw1825_num,
        sw1650_num=sw1650_num,
        l1_switch_num=l1_switch_num,
        l2_switch_num=l2_switch_num,
        sw1650_port_num=params.npu_per_node // params.sw1650_per_node,
        sw1825_port_num=params.npu_per_node // params.sw1825_per_node,
    )


def npu_id(params: TopologyParams, pod_id: int, node_id: int, npu_id_in_node: int) -> int:
    return (pod_id * params.node_per_pod + node_id) * params.npu_per_node + npu_id_in_node


def node_offset(params: TopologyParams, pod_id: int, node_id: int) -> int:
    return pod_id * params.node_per_pod + node_id


def sw1650_id(
    params: TopologyParams,
    layout: IdLayout,
    pod_id: int,
    node_id: int,
    sw1650_id_in_node: int,
) -> int:
    return layout.sw1650_base_id + node_offset(params, pod_id, node_id) * params.sw1650_per_node + sw1650_id_in_node


def sw1825_id(
    params: TopologyParams,
    layout: IdLayout,
    pod_id: int,
    node_id: int,
    sw1825_id_in_node: int,
) -> int:
    return layout.sw1825_base_id + node_offset(params, pod_id, node_id) * params.sw1825_per_node + sw1825_id_in_node


def l1_switch_id(params: TopologyParams, layout: IdLayout, pod_id: int, plane_id: int) -> int:
    return layout.l1_base_id + pod_id * params.l1_switch_per_pod + plane_id


def l2_switch_id(
    params: TopologyParams,
    layout: IdLayout,
    plane_id: int,
    switch_id_in_plane: int,
) -> int:
    return layout.l2_base_id + plane_id * params.l2_switch_per_plane + switch_id_in_plane


def add_host(graph, target: str, host_id: int) -> None:
    if target == "ns3":
        graph.add_netisim_host(host_id, forward_delay=FORWARD_DELAY)
    elif target == "netisim":
        graph.add_netisim_host(host_id)
    else:
        raise ValueError(f"unsupported target: {target}")


def add_switch(graph, target: str, switch_id: int) -> None:
    if target == "ns3":
        graph.add_netisim_node(switch_id, forward_delay=FORWARD_DELAY)
    elif target == "netisim":
        graph.add_netisim_node(switch_id, comp_delay=1300)
    else:
        raise ValueError(f"unsupported target: {target}")


def add_edge(
    graph,
    target: str,
    src: int,
    dst: int,
    ns3_bandwidth: str,
    netisim_bandwidth: str,
    edge_count: int = 1,
) -> None:
    if target == "ns3":
        graph.add_netisim_edge(src, dst, bandwidth=ns3_bandwidth, delay=LINK_DELAY, edge_count=edge_count)
    elif target == "netisim":
        graph.add_netisim_edge(src, dst, bandwidth=netisim_bandwidth, delay="20", edge_count=edge_count)
    else:
        raise ValueError(f"unsupported target: {target}")


def single_shortest_path(graph, source: int, target: int):
    try:
        return [nx.shortest_path(graph, source, target)]
    except nx.NetworkXNoPath:
        return []


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


def case_dirs(output_root: Path) -> dict[str, Path]:
    return {
        "ns3": output_root / "ns3",
        "netisim": output_root / "netisim",
    }


def write_ns3_case(output_dir: Path, params: TopologyParams, route_workers: int) -> None:
    clean_known_outputs(
        output_dir,
        [
            "node.csv",
            "topology.csv",
            "routing_table.csv",
            "traffic.csv",
            "transport_channel.csv",
            "network_attribute.txt",
        ],
    )
    graph, ids = build_ns3_graph(params)
    graph.output_dir = os.fspath(output_dir)
    graph.build_graph_config()
    graph.gen_route_table(path_finding_algo=single_shortest_path, multiple_workers=route_workers)
    graph._write_node_csv(os.path.join(graph.output_dir, "node.csv"))
    graph._write_topology_csv(os.path.join(graph.output_dir, "topology.csv"))
    write_traffic_csv(output_dir, ids)
    clean_known_outputs(output_dir, ["transport_channel.csv", "network_attribute.txt"])


def write_netisim_case(
    output_dir: Path,
    params: TopologyParams,
    template_path: Path,
    route_workers: int,
) -> None:
    clean_known_outputs(output_dir, ["dcn2.0_config.xml", "router.xml", "rdma_operate.txt"])
    graph, ids = build_netisim_graph(params)
    graph.output_dir = output_dir_with_sep(output_dir)
    graph.build_graph_config(os.fspath(template_path), node_gen_bandwidth="400", output_name="dcn2.0_config.xml")
    postprocess_netisim_config(output_dir / "dcn2.0_config.xml", ids)
    graph.gen_route_table(path_finding_algo=single_shortest_path, host_router=False, multiple_workers=route_workers)


def output_dir_with_sep(output_dir: Path) -> str:
    path = os.fspath(output_dir)
    return path if path.endswith(os.sep) else path + os.sep


def clean_known_outputs(output_dir: Path, file_names: list[str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for file_name in file_names:
        path = output_dir / file_name
        if path.exists():
            path.unlink()


def postprocess_netisim_config(path: Path, ids: TopologyIds) -> None:
    root = etree.parse(os.fspath(path)).getroot()
    compact_node_groups(root)
    sync_process_partition(root, ids)
    sync_xml_template(root)
    sync_ft_node_config(root, ids)
    etree.indent(root, space="    ")
    path.write_text(etree.tostring(root, pretty_print=True).decode(), encoding="utf-8")


def compact_node_groups(root) -> None:
    for group in root.xpath("/dcn/dcn_network/node/grp[@node_id]"):
        group.set("node_id", compact_ranges(parse_id_expression(group.get("node_id"))))


def sync_process_partition(root, ids: TopologyIds) -> None:
    mpi_nodes = root.xpath("/dcn/dcn_network/mpi_multi_processing")
    if not mpi_nodes:
        return

    process_partition = etree.Element("process_partition")
    overlap_partition = etree.SubElement(process_partition, "overlap_partition", partition_num="1")
    for group_ids in node_layer_groups(ids):
        etree.SubElement(overlap_partition, "chip", dev_id=compact_ranges(group_ids))

    old_partition = mpi_nodes[0].xpath("./process_partition")
    if old_partition:
        old_partition[0].getparent().replace(old_partition[0], process_partition)
    else:
        mpi_nodes[0].append(process_partition)


def sync_xml_template(root) -> None:
    network_nodes = root.xpath("/dcn/dcn_network")
    if not network_nodes:
        return
    network = network_nodes[0]
    old_xml_template = network.xpath("./xml_template")
    base_template = old_xml_template[0].xpath("./template")[0] if old_xml_template and old_xml_template[0].xpath("./template") else None
    template_count = len(root.xpath("/dcn/dcn_network/node/grp[contains(@type, 'node')]"))

    xml_template = etree.Element("xml_template")
    for template_id in range(template_count):
        template = deepcopy(base_template) if base_template is not None else etree.Element("template")
        template.set("id", str(template_id))
        if len(template) == 0:
            etree.SubElement(template, "index", config_file="")
            etree.SubElement(template, "index", config_file="")
        for index in template.xpath("./index"):
            if "config_file" not in index.attrib:
                index.set("config_file", "")
        xml_template.append(template)

    if old_xml_template:
        old_xml_template[0].getparent().replace(old_xml_template[0], xml_template)
    else:
        network.append(xml_template)


def sync_ft_node_config(root, ids: TopologyIds) -> None:
    node_configs = root.xpath("/dcn/dcn_common_node_config/ft_node/node_config")
    if not node_configs:
        return
    node_config = node_configs[0]
    node_config.set("tier", "4")
    node_config.set("host_num", str(len(ids.host_ids)))
    node_config.set("leaf_num", str(len(ids.switch_groups["sw1650"]) + len(ids.switch_groups["sw1825"])))
    node_config.set("spine_num", str(len(ids.switch_groups["l1"])))
    node_config.set("core_num", str(len(ids.switch_groups["l2"])))
    node_config.set("top_num", "0")


def node_layer_groups(ids: TopologyIds) -> list[list[int]]:
    return [
        ids.host_ids,
        ids.switch_groups["sw1825"],
        ids.switch_groups["sw1650"],
        ids.switch_groups["l1"],
        ids.switch_groups["l2"],
    ]


def parse_id_expression(expression: str) -> list[int]:
    ids: list[int] = []
    for token in expression.split():
        if ".." in token:
            start, end = token.split("..", 1)
            ids.extend(range(int(start), int(end) + 1))
        else:
            ids.append(int(token))
    return ids


def compact_ranges(ids: list[int]) -> str:
    ranges: list[str] = []
    start = previous = ids[0]
    for value in ids[1:] + [None]:
        if value is None or value != previous + 1:
            ranges.append(str(start) if start == previous else f"{start}..{previous}")
            if value is not None:
                start = value
        if value is not None:
            previous = value
    return " ".join(ranges)


def generate_cases(
    target: str = "both",
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    template_path: Path | str = DEFAULT_NETISIM_TEMPLATE,
    route_workers: int = 1,
    params: TopologyParams = TopologyParams(),
) -> dict[str, Path]:
    if target not in {"ns3", "netisim", "both"}:
        raise ValueError("target must be one of: ns3, netisim, both")

    root = Path(output_root)
    template = Path(template_path)
    dirs = case_dirs(root)
    generated: dict[str, Path] = {}

    if target in {"ns3", "both"}:
        write_ns3_case(dirs["ns3"], params, route_workers)
        generated["ns3"] = dirs["ns3"]

    if target in {"netisim", "both"}:
        write_netisim_case(dirs["netisim"], params, template, route_workers)
        generated["netisim"] = dirs["netisim"]

    return generated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["ns3", "netisim", "both"], default="both")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--netisim-template", type=Path, default=DEFAULT_NETISIM_TEMPLATE)
    parser.add_argument("--route-workers", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generated = generate_cases(
        target=args.target,
        output_root=args.output_root,
        template_path=args.netisim_template,
        route_workers=args.route_workers,
    )
    for case_type, path in generated.items():
        print(f"{case_type}: {path.resolve()}")


if __name__ == "__main__":
    main()
