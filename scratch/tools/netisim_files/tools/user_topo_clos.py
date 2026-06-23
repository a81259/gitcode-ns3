import os
import utils.netisim_graph as netisim_graph
import networkx as nx

def all_simple_paths(G, source, target):
    try:
        paths = nx.all_simple_paths(G, source, target, cutoff=6)
    except nx.exception.NetworkXNoPath:
        paths = []
    return paths

if __name__ == '__main__':
    graph = netisim_graph.NetiSimGraph()

    host_num = 512
    leaf_sw_num = 8
    spine_sw_num = 8
    core_sw_num = 4
    pod_num = 4
    total_node_num = host_num + leaf_sw_num + spine_sw_num
    host_ids = []
    leaf_ids = []
    spine_ids = []
    core_ids = []

    # step1: 生成节点,要求host在前,node在后,且顺序编号,不符合要求会报错
    for host_id in range(host_num):
        graph.add_netisim_host(host_id)
        host_ids.append(host_id)

    for leaf_sw_id in range(leaf_sw_num):
        graph.add_netisim_node(leaf_sw_id + host_num, comp_delay=1300)
        leaf_ids.append(leaf_sw_id + host_num)

    for spine_sw_id in range(spine_sw_num):
        graph.add_netisim_node(spine_sw_id + host_num + leaf_sw_num, comp_delay=1300)
        spine_ids.append(spine_sw_id + host_num + leaf_sw_num)

    for core_sw_id in range(core_sw_num):
        graph.add_netisim_node(core_sw_id + spine_sw_num + host_num + leaf_sw_num, comp_delay=1300)
        core_ids.append(core_sw_id + spine_sw_num + host_num + leaf_sw_num)

    # step2: 生成拓扑连线,按照自定义拓扑,将指定id的节点(host或node皆可)进行连线并指定带宽和时延(发包器会自动连接)
    host_per_leaf = host_num // leaf_sw_num
    for host_id in range(host_num):
        host_id = host_id
        leaf_id = leaf_ids[host_id // host_per_leaf]
        graph.add_netisim_edge(host_id, leaf_id, bandwidth='400', delay='20', edge_count=1)

    leaf_num_per_pod = leaf_sw_num // pod_num
    spine_num_per_pod = spine_sw_num // pod_num
    for leaf_idx,leaf_id in enumerate(leaf_ids):
        for spine_idx,spine_id in enumerate(spine_ids):
            if leaf_idx//leaf_num_per_pod == spine_idx//spine_num_per_pod:
                graph.add_netisim_edge(leaf_id, spine_id, bandwidth='400', delay='20', edge_count=1)

    for spine_id in spine_ids:
        for core_id in core_ids:
            graph.add_netisim_edge(spine_id, core_id, bandwidth='400', delay='20', edge_count=1)

    # step3: 生成配置文件,build_graph_config会生成一系列中间数据,最终生成dcn2.0_config.xml文件
    config_template = "./utils/config_template/dcn2.0_config_template.xml"
    print(f"目前使用的配置模板为[{config_template}]\n请务必使用与你的MNS仿真平台版本适配的模板！否则运行时可能报错！")
    graph.build_graph_config(config_template, node_gen_bandwidth='400', output_name="dcn2.0_config.xml")



    graph.gen_route_table(path_finding_algo=all_simple_paths, host_router=False, multiple_workers=8)
