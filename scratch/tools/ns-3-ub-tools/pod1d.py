import os
import csv

import net_sim_builder as netsim
import networkx as nx


POD_NUM = 19
NODE_PER_POD = 9
NPU_PER_NODE = 8
SW1650_PER_NODE = 2
SW1825_PER_NODE = 4
L1_SWITCH_PER_POD = 24
L2_PLANE_NUM = 24
L2_SWITCH_PER_PLANE = 4

NPU_1650_BANDWIDTH = "400Gbps"
NPU_1825_BANDWIDTH = "400Gbps"
NPU_L1_BANDWIDTH = "112Gbps"
L1_L2_BANDWIDTH = "224Gbps"
LINK_DELAY = "20ns"
FORWARD_DELAY = "1ns"
L1_TO_EACH_L2_PORTS = 9
ROUTE_WORKERS = 4
TRAFFIC_BYTES_PER_TASK = 8 * 1024 * 1024
TRAFFIC_PRIORITY = 7
TRAFFIC_DELAY = "10ns"


HOST_NUM = POD_NUM * NODE_PER_POD * NPU_PER_NODE
SW1650_NUM = POD_NUM * NODE_PER_POD * SW1650_PER_NODE
SW1825_NUM = POD_NUM * NODE_PER_POD * SW1825_PER_NODE
L1_SWITCH_NUM = POD_NUM * L1_SWITCH_PER_POD
L2_SWITCH_NUM = L2_PLANE_NUM * L2_SWITCH_PER_PLANE
SW1825_BASE_ID = HOST_NUM
SW1650_BASE_ID = SW1825_BASE_ID + SW1825_NUM
L1_BASE_ID = SW1650_BASE_ID + SW1650_NUM
L2_BASE_ID = L1_BASE_ID + L1_SWITCH_NUM
TOTAL_NODE_NUM = HOST_NUM + SW1650_NUM + SW1825_NUM + L1_SWITCH_NUM + L2_SWITCH_NUM

NPU_PORT_NUM = L1_SWITCH_PER_POD + 2
SW1650_PORT_NUM = NPU_PER_NODE // SW1650_PER_NODE
SW1825_PORT_NUM = NPU_PER_NODE // SW1825_PER_NODE
L1_SWITCH_PORT_NUM = NODE_PER_POD * NPU_PER_NODE + L2_SWITCH_PER_PLANE * L1_TO_EACH_L2_PORTS
L2_SWITCH_PORT_NUM = POD_NUM * L1_TO_EACH_L2_PORTS


def npu_id(pod_id, node_id, npu_id_in_node):
    return (pod_id * NODE_PER_POD + node_id) * NPU_PER_NODE + npu_id_in_node


def node_offset(pod_id, node_id):
    return pod_id * NODE_PER_POD + node_id


def sw1650_id(pod_id, node_id, sw1650_id_in_node):
    return SW1650_BASE_ID + node_offset(pod_id, node_id) * SW1650_PER_NODE + sw1650_id_in_node


def sw1825_id(pod_id, node_id, sw1825_id_in_node):
    return SW1825_BASE_ID + node_offset(pod_id, node_id) * SW1825_PER_NODE + sw1825_id_in_node


def l1_switch_id(pod_id, plane_id):
    return L1_BASE_ID + pod_id * L1_SWITCH_PER_POD + plane_id


def l2_switch_id(plane_id, switch_id_in_plane):
    return L2_BASE_ID + plane_id * L2_SWITCH_PER_PLANE + switch_id_in_plane


def build_graph():
    graph = netsim.NetworkSimulationGraph()

    for host_id in range(HOST_NUM):
        graph.add_netisim_host(host_id, forward_delay=FORWARD_DELAY)

    for switch_id in range(SW1650_NUM + SW1825_NUM + L1_SWITCH_NUM + L2_SWITCH_NUM):
        graph.add_netisim_node(HOST_NUM + switch_id, forward_delay=FORWARD_DELAY)

    # 节点内：每个 1650 连接 4 个 NPU，每个 1825 连接 2 个 NPU。
    for pod_id in range(POD_NUM):
        for node_id in range(NODE_PER_POD):
            for npu_id_in_node in range(NPU_PER_NODE):
                host_id = npu_id(pod_id, node_id, npu_id_in_node)
                graph.add_netisim_edge(
                    host_id,
                    sw1650_id(pod_id, node_id, npu_id_in_node // SW1650_PORT_NUM),
                    bandwidth=NPU_1650_BANDWIDTH,
                    delay=LINK_DELAY,
                    edge_count=1,
                )
                graph.add_netisim_edge(
                    host_id,
                    sw1825_id(pod_id, node_id, npu_id_in_node // SW1825_PORT_NUM),
                    bandwidth=NPU_1825_BANDWIDTH,
                    delay=LINK_DELAY,
                    edge_count=1,
                )

    # Pod 内：每个 NPU 连接本 Pod 的 24 个 L1 5809s，单链路 112G。
    for pod_id in range(POD_NUM):
        for node_id in range(NODE_PER_POD):
            for npu_id_in_node in range(NPU_PER_NODE):
                host_id = npu_id(pod_id, node_id, npu_id_in_node)
                for plane_id in range(L1_SWITCH_PER_POD):
                    graph.add_netisim_edge(
                        host_id,
                        l1_switch_id(pod_id, plane_id),
                        bandwidth=NPU_L1_BANDWIDTH,
                        delay=LINK_DELAY,
                        edge_count=1,
                    )

    # 跨 Pod：每个 Pod 的第 i 个 L1 switch 连接 L2 第 i 个平面内的 4 个 switch，
    # 到每个 L2 switch 使用 9 条 224G 端口。
    for pod_id in range(POD_NUM):
        for plane_id in range(L2_PLANE_NUM):
            l1_id = l1_switch_id(pod_id, plane_id)
            for switch_id_in_plane in range(L2_SWITCH_PER_PLANE):
                graph.add_netisim_edge(
                    l1_id,
                    l2_switch_id(plane_id, switch_id_in_plane),
                    bandwidth=L1_L2_BANDWIDTH,
                    delay=LINK_DELAY,
                    edge_count=L1_TO_EACH_L2_PORTS,
                )

    return graph


def single_shortest_path(graph, source, target):
    try:
        return [nx.shortest_path(graph, source, target)]
    except nx.NetworkXNoPath:
        return []


def remove_stale_transport(output_dir):
    transport_path = os.path.join(output_dir, "transport_channel.csv")
    if os.path.exists(transport_path):
        os.remove(transport_path)


def write_traffic_csv(output_dir, bytes_per_task=TRAFFIC_BYTES_PER_TASK):
    traffic_path = os.path.join(output_dir, "traffic.csv")
    half_host_num = HOST_NUM // 2

    with open(traffic_path, "w", newline="", encoding="utf-8") as f:
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
        for task_id, src in enumerate(range(half_host_num)):
            dst = src + half_host_num
            writer.writerow([
                task_id,
                src,
                dst,
                bytes_per_task,
                "URMA_WRITE",
                TRAFFIC_PRIORITY,
                TRAFFIC_DELAY,
                0,
                "",
            ])

    print(f"流量配置: {os.path.abspath(traffic_path)}")


def write_config(graph, output_dir=None):
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), "output", "pod1d")

    graph.output_dir = output_dir
    graph.build_graph_config()
    os.makedirs(graph.output_dir, exist_ok=True)
    remove_stale_transport(graph.output_dir)
    graph.gen_route_table(path_finding_algo=single_shortest_path, multiple_workers=ROUTE_WORKERS)
    graph._write_node_csv(os.path.join(graph.output_dir, "node.csv"))
    graph._write_topology_csv(os.path.join(graph.output_dir, "topology.csv"))
    write_traffic_csv(graph.output_dir)
    remove_stale_transport(graph.output_dir)
    print(f"输出目录: {os.path.abspath(graph.output_dir)}")


if __name__ == "__main__":
    write_config(build_graph())
