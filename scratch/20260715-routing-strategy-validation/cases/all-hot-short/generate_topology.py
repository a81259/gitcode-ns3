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

for host in range(2):
    graph.add_netisim_host(host, forward_delay='1ns')
for switch in range(2, 7):
    graph.add_netisim_node(switch, forward_delay='1ns')
graph.add_netisim_edge(0, 2, bandwidth='1200Gbps', delay='20ns')
graph.add_netisim_edge(1, 3, bandwidth='1200Gbps', delay='20ns')
graph.add_netisim_edge(2, 4, bandwidth='25Gbps', delay='20ns')
graph.add_netisim_edge(3, 4, bandwidth='25Gbps', delay='20ns')
graph.add_netisim_edge(2, 5, bandwidth='400Gbps', delay='20ns')
graph.add_netisim_edge(3, 5, bandwidth='400Gbps', delay='20ns')
graph.add_netisim_edge(2, 6, bandwidth='400Gbps', delay='20ns')
graph.add_netisim_edge(3, 6, bandwidth='400Gbps', delay='20ns')
graph.build_graph_config()
graph.gen_compressed_route_table(path_finding_algo=all_shortest_paths, multiple_workers=1)
graph.write_config(include_transport=False)
route_path = CASE_DIR / 'routing_table.csv'
route_path.write_text('''nodeId,dstNodeId,dstPortId,outPorts,metrics
0,1,0,0,4
1,0,0,0,4
2,0,0,0,1
2,1,0,1 2 3,3 4 4
3,0,0,1 2 3,3 4 4
3,1,0,0,1
4,0,0,0,2
4,1,0,1,2
5,0,0,0,2
5,1,0,1,2
6,0,0,0,2
6,1,0,1,2
''', encoding='utf-8')
