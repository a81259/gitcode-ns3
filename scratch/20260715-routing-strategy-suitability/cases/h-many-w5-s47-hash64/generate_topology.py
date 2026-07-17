#!/usr/bin/env python3
import sys
from pathlib import Path
import networkx as nx

CASE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = CASE_DIR.parents[2] / 'ns-3-ub-tools'
sys.path.insert(0, str(TOOLS_DIR))
import net_sim_builder as netsim

def all_shortest_paths(graph, source, target):
    try:
        return nx.all_shortest_paths(graph, source, target)
    except nx.NetworkXNoPath:
        return []

graph = netsim.NetworkSimulationGraph()
graph.output_dir = str(CASE_DIR) + '/'

for host in range(32):
    graph.add_netisim_host(host, forward_delay='1ns')
for switch in range(32, 41):
    graph.add_netisim_node(switch, forward_delay='1ns')
for host in range(32):
    graph.add_netisim_edge(host, 32 + host // 8, bandwidth='400Gbps', delay='20ns')
for leaf in range(32, 36):
    for spine in range(36, 41):
        graph.add_netisim_edge(leaf, spine, bandwidth='100Gbps', delay='20ns')
graph.build_graph_config()
graph.gen_compressed_route_table(path_finding_algo=all_shortest_paths, multiple_workers=1)
graph.write_config(include_transport=False)
