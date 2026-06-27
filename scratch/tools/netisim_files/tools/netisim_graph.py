import networkx as nx
from lxml import etree
import argparse
from copy import deepcopy
from collections import deque
import heapq
import time
import os
import numpy as np
from tqdm import tqdm, trange
try:
    import utils.netisim_utils as netisim_utils
except ModuleNotFoundError:
    netisim_utils = None
import math

from itertools import combinations
from concurrent.futures import ProcessPoolExecutor, as_completed
import time

STATIC_COMP_COST = 8 * 1024 * 1024
STATIC_SYNC_COST = 8 * 1024 * 1024


def _format_int_ranges(values):
    values = sorted(values)
    if not values:
        return ""

    ranges = []
    start = values[0]
    prev = values[0]
    for value in values[1:]:
        if value == prev + 1:
            prev = value
            continue
        ranges.append(str(start) if start == prev else f"{start}..{prev}")
        start = value
        prev = value
    ranges.append(str(start) if start == prev else f"{start}..{prev}")
    return " ".join(ranges)


def _sync_overlap_partition_chips(root_config, node_ele):
    overlap_partitions = root_config.xpath(
        '/dcn/dcn_network/mpi_multi_processing/process_partition/overlap_partition'
    )
    if not overlap_partitions:
        return

    overlap_partition = overlap_partitions[0]
    for chip_ele in overlap_partition.xpath('./chip'):
        overlap_partition.remove(chip_ele)
    for node_group in node_ele.xpath('./grp'):
        etree.SubElement(overlap_partition, "chip", dev_id=node_group.get("node_id"))


def _sync_xml_templates(root_config, node_ele):
    xml_templates = root_config.xpath('/dcn/dcn_network/xml_template')
    if not xml_templates:
        return

    template_ids = sorted(
        {
            int(node_group.get("config_template"))
            for node_group in node_ele.xpath('./grp')
            if node_group.get("type") == NETISIM_MOD + "node"
        }
    )
    if not template_ids:
        return

    xml_template = xml_templates[0]
    old_templates = xml_template.xpath('./template')
    template_seed = deepcopy(old_templates[0]) if old_templates else etree.Element("template")
    if not template_seed.xpath('./index'):
        etree.SubElement(template_seed, "index", config_file="")
        etree.SubElement(template_seed, "index", config_file="")

    for template_ele in old_templates:
        xml_template.remove(template_ele)
    for template_id in template_ids:
        template_ele = deepcopy(template_seed)
        template_ele.set("id", str(template_id))
        xml_template.append(template_ele)


def _sync_ft_node_counts(root_config, graph):
    node_configs = root_config.xpath('/dcn/dcn_common_node_config/ft_node/node_config')
    if not node_configs:
        return

    distances = {host_id: 0 for host_id in graph.host_ids}
    queue = deque(graph.host_ids)
    while queue:
        node_id = queue.popleft()
        for neighbor in graph.neighbors(node_id):
            if neighbor in distances:
                continue
            distances[neighbor] = distances[node_id] + 1
            queue.append(neighbor)
    layer_counts = {
        "host_num": len(graph.host_ids),
        "leaf_num": 0,
        "spine_num": 0,
        "core_num": 0,
        "top_num": 0,
    }
    for node_id in graph.node_ids:
        distance = distances.get(node_id)
        if distance == 1:
            layer_counts["leaf_num"] += 1
        elif distance == 2:
            layer_counts["spine_num"] += 1
        elif distance == 3:
            layer_counts["core_num"] += 1
        elif distance is not None and distance >= 4:
            layer_counts["top_num"] += 1

    node_config = node_configs[0]
    for key, value in layer_counts.items():
        node_config.set(key, str(value))


def _sync_direct_topo(root_config, direct_topo):
    direct_topo_value = "true" if direct_topo else "false"
    for ele in root_config.xpath('//*[@direct_topo]'):
        ele.set("direct_topo", direct_topo_value)

        
def _process_path_chunk(graph, path_finding_algo, node_pairs):
    paths = []
    for src, dst in tqdm(node_pairs, desc="算法{}寻找所有可用路径".format(path_finding_algo.__name__)):
        paths += path_finding_algo(graph, src, dst)
    return paths

class NetiSimGraph(nx.Graph):
    node_type = [
        'host',
        'node'
    ]

    def __init__(self):
        super().__init__()

        self.output_dir = "./output/" + time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime()) + "/"
        self.host_ids = []  # 拓扑中的host节点id
        self.node_ids = []  # 拓扑中的node(即交换机)节点id
        self.next_hop_ports = []  # 下一跳端口表: next_hop_ports[this_node][next_hpo] = (port1, port2, ...), 同时可用get_next_hop(src, port)获取下一跳节点
        self.route_table_2port = None  # 路由表: route_table_2port[node_id][dst_id] = {port1, port2, ...} 与2node对应
        self.route_table_2node = None  # 路由表: route_table_2node[node_id][dst_id] = {node1, node2, ...} 与2port对应
        self.topo_ele_xml = None  # 生成的拓扑xml文件
        self.node_ele_xml = None  # 生成的节点xml文件
        self.route_ele_xml = None  # 生成的路由表xml文件

        # 给定xml文件生成graph,根据仿真激励修剪graph相关的变量
        self.comm = {}  # 用户指定的通信域
        self.avtive_comm_id = set()  # 根据用户指定的仿真激励, 激活的通信域id
        self.avtive_ids = set()  # 根据激活的通信域id, 基于路由表生成的激活节点id. 用于修剪拓扑

        self.path_finding_algo = nx.all_shortest_paths

    # 增加host节点, 通常表示netisim中的交换机
    def add_netisim_host(self, node_id, **attr):
        self.host_ids.append(node_id)
        return super().add_node(node_id, type='host', comp_cost=STATIC_COMP_COST, **attr)

    # 增加node节点, 通常表示netisim中的交换机
    def add_netisim_node(self, node_id, comp_delay=1300, **attr):
        self.node_ids.append(node_id)
        return super().add_node(node_id, type='node', comp_delay=comp_delay, comp_cost=STATIC_COMP_COST, **attr)

    # graph.add_edge(host_id, int(host_id/6) * 2 + HOST_NUM, weight='1', bandwidth='200', delay='20')
    def add_netisim_edge(self, u, v, bandwidth='200', delay='20', edge_count=1, **attr):
        """
        在网络模拟图中，在节点u和v之间添加一条具有指定属性的边。

        :param u: 边的一个端点。
        :param v: 边的另一个端点。
        :param bandwidth: 边的带宽，单位Gbps，默认值为'200'。
        :param delay: 边的延时，单位为ns，默认值为'20'。
        :param edge_count: 节点u和v之间的边的数量（有多少个wu'li'lian'luwulilianlu），默认值为1。
        :param attr: 需要为边设置的其他属性。
        :return: 超类add_edge方法的返回值
        """
        return super().add_edge(u, v, bandwidth=bandwidth, delay=delay, edge_count=edge_count,
                                sync_cost=STATIC_SYNC_COST, **attr)

    def check_graph_index_valid(self):
        for i in range(len(self.nodes)):
            assert self.has_node(i), "编号{}:必须从0开始顺序编号!".format(i)
            assert self.nodes[i][
                       "type"] in self.node_type, "编号{}节点类型{},必须是host(代表NPU卡)或node(代表交换机)!".format(i,
                                                                                                                     self.nodes[
                                                                                                                         i][
                                                                                                                         "type"])

        assert max(self.host_ids) == min(self.node_ids) - 1, "编号由小到大,host在前,node在后,且顺序编号!"
        assert len(self.host_ids) + len(self.node_ids) == len(self.nodes), "host和node节点数目之和应等于总节点数目!"
        return True

    def get_host_num(self):
        return len(self.host_ids)

    def get_node_num(self):
        return len(self.node_ids)

    def get_total_num(self):
        return len(self.host_ids) + len(self.node_ids)

    def node_is_switch(self, node_id):
        return self.nodes[node_id]['type'] == 'node'

    def node_is_host(self, node_id):
        return self.nodes[node_id]['type'] == 'host'

    def build_graph_config(self, template_xml, write_flag=True, output_name=None,
                           node_gen_bandwidth='400', node_gen_delay='20',
                           direct_topo=True, generator_link=True):
        # graph到xml文件的转换
        assert self.check_graph_index_valid()
        try:
            root_config = etree.parse(template_xml).getroot()
        except:
            print("Woops.")
            exit()
        else:
            pass

        old_node_ele = root_config.xpath('/dcn/dcn_network/node')[0]
        new_node_ele = etree.Element("node")

        host_num = self.get_host_num()
        total_node_num = self.get_total_num()

        # host_ele = etree.SubElement(new_node_ele, "grp", type=HOST_TYPE, node_id="0..{}".format(host_num - 1), port_num="2", config_template="0")

        port_num_id_dict = {}
        for node_id in self.nodes:
            # if not self.node_is_switch(node_id):
            #     continue
            t_node = self.nodes[node_id]
            # t_port_num = self.degree[node_id]
            t_port_num = 0
            for edge in self.edges(node_id):
                t_port_num += int(self.get_edge_data(edge[0], edge[1])["edge_count"])
            t_group_key = (t_node["type"], t_port_num)
            if t_group_key not in port_num_id_dict:
                port_num_id_dict[t_group_key] = [node_id]
            else:
                port_num_id_dict[t_group_key].append(node_id)

        t_template_host = 0
        t_template_node = 0
        for (_, port_num), node_id in port_num_id_dict.items():
            if 'comp_delay' in self.nodes[node_id[0]]:
                comp_delay = self.nodes[node_id[0]]['comp_delay']
            else:
                comp_delay = 1300
            # print(comp_delay)
            if self.node_is_host(node_id[0]):
                host_port_num = port_num + 1 if generator_link else port_num
                node_ele = etree.SubElement(new_node_ele, "grp", type=NETISIM_MOD + self.nodes[node_id[0]]['type'],
                                            node_id=_format_int_ranges(node_id), port_num=str(host_port_num),
                                            config_template=str(t_template_host), comp_delay=str(comp_delay))
                t_template_host += 1
            else:
                node_ele = etree.SubElement(new_node_ele, "grp", type=NETISIM_MOD + self.nodes[node_id[0]]['type'],
                                            node_id=_format_int_ranges(node_id), port_num=str(port_num),
                                            config_template=str(t_template_node), comp_delay=str(comp_delay))
                t_template_node += 1
        old_node_ele.getparent().replace(old_node_ele, new_node_ele)
        _sync_overlap_partition_chips(root_config, new_node_ele)
        _sync_xml_templates(root_config, new_node_ele)

        old_topo_ele = root_config.xpath('/dcn/dcn_network/topology')[0]
        new_topo_ele = etree.Element("topology")
        if generator_link:
            etree.SubElement(new_topo_ele, "grp", link_type="bi_direct", src_node="0..{}".format(host_num - 1),
                             src_port="0", dst_node="-1", dst_port="0..{}".format(host_num - 1),
                             bandwidth=node_gen_bandwidth, delay=node_gen_delay)
        port_conn_count = [0] * total_node_num
        for node_id in self.nodes:
            if generator_link and self.node_is_host(node_id):
                port_conn_count[node_id] += 1

        for u, v in tqdm(self.edges, desc="生成拓扑连线"):
            edge_count = self.edges[u, v]["edge_count"]
            for e in range(int(edge_count)):
                u_port_cnt = str(port_conn_count[u])
                v_port_cnt = str(port_conn_count[v])
                bw = self.edges[u, v]["bandwidth"]
                dl = self.edges[u, v]["delay"]
                topo_ele = etree.SubElement(new_topo_ele, "grp", link_type="bi_direct", src_node=str(u),
                                            src_port=u_port_cnt, dst_node=str(v), dst_port=v_port_cnt,
                                            bandwidth=str(bw), delay=str(dl))
                port_conn_count[u] += 1
                port_conn_count[v] += 1
        old_topo_ele.getparent().replace(old_topo_ele, new_topo_ele)

        # <dcn_common_node_config>修改
        config_ele = etree.Element("common_node")
        old_config_ele = root_config.xpath('/dcn/dcn_common_node_config/common_node')[0]
        template_ele = root_config.xpath('/dcn/dcn_common_node_config/common_node/template')[0]

        t_template_id = 0
        for (_, port_num), node_id in port_num_id_dict.items():
            if not self.node_is_switch(node_id[0]):
                continue
            template_ele.set("index", str(t_template_id))
            t_port_att_eles = template_ele.xpath('.//*[@port]')
            for ele in t_port_att_eles:
                # print(ele.get("port"))
                ele.set("port", "0.." + str(port_num - 1))
            config_ele.append(deepcopy(template_ele))
            t_template_id += 1
        old_config_ele.getparent().replace(old_config_ele, config_ele)

        config_ele = etree.Element("common_host")
        old_config_ele = root_config.xpath('/dcn/dcn_common_node_config/common_host')[0]
        template_ele = root_config.xpath('/dcn/dcn_common_node_config/common_host/template')[0]

        t_template_id = 0
        for (_, port_num), node_id in port_num_id_dict.items():
            if not self.node_is_host(node_id[0]):
                continue
            template_ele.set("index", str(t_template_id))
            t_port_att_eles = template_ele.xpath('.//*[@port]')
            for ele in t_port_att_eles:
                # print(ele.get("port"))
                if ele.get("port") == "0..0":
                    continue
                non_zero_port_max = port_num if generator_link else port_num - 1
                if non_zero_port_max < 1:
                    ele.getparent().remove(ele)
                else:
                    ele.set("port", "1.." + str(non_zero_port_max))
            config_ele.append(deepcopy(template_ele))
            t_template_id += 1
        old_config_ele.getparent().replace(old_config_ele, config_ele)

        # 按照现有配置, 更改一些xml中的字段
        # ft_ele = root_config.xpath('/dcn/dcn_common_node_config/ft_node/node_config')[0]
        # ft_ele.set("host_num", str(list(self.host_ids)))
        # ft_ele.set("leaf_num", str(list(self.node_ids)))
        _sync_ft_node_counts(root_config, self)
        _sync_direct_topo(root_config, direct_topo)

        etree.indent(root_config, space="    ")
        # print(etree.tostring(root_config, pretty_print=True).decode(), end="")
        if output_name is None:
            output_name = "dcn2.0_config.xml"
        if write_flag:
            try:
                os.makedirs(self.output_dir, exist_ok=True)
            except OSError as e:
                print(f"Error creating directory {self.output_dir}: {e}")
                return
            with open(self.output_dir + output_name, "w") as output_xml:
                output_xml.write(etree.tostring(root_config, pretty_print=True).decode())
            print("配置文件已写入：", self.output_dir + output_name)

        self.topo_ele_xml = new_topo_ele
        self.node_ele_xml = new_node_ele

        # 构建下一跳端口表next_hop_ports[this_node][next_hpo] = (port1, port2, ...)
        print("构建下一跳端口表...")
        next_hop_ports = []
        for i in range(total_node_num):
            next_hop_ports.append([])
            for j in range(total_node_num):
                next_hop_ports[i].append([])
        for link_ele in self.topo_ele_xml:
            if link_ele.get("dst_node") == "-1":
                continue
            # 为简化代码,脚本仅支持一对一的topo配置,不支持使用空格或".."分割的配置
            sn = int(link_ele.get("src_node"))
            sp = int(link_ele.get("src_port"))
            dn = int(link_ele.get("dst_node"))
            dp = int(link_ele.get("dst_port"))
            if sp in next_hop_ports[sn][dn]:
                print(f"{sn}->{dn}: 端口{sp}已经存在")
            next_hop_ports[sn][dn].append(sp)
            if dp in next_hop_ports[dn][sn]:
                print(f"{dn}->{sn}: 端口{dp}已经存在")
            next_hop_ports[dn][sn].append(dp)
            # print(next_hop_port)
        self.next_hop_ports = next_hop_ports

        return new_node_ele, new_topo_ele

    def set_route_table(self, curr_node, dst, next_hop_node, metric):
        """如果你想直接写入路由表项, 请使用本方法. 
        如果你想使用寻路算法寻找每一对host节点间的可用路径, 并基于可用路径生成路由表, 请使用gen_route_table方法. 
        
        Parameters
        ----------
        self : 定义好的NetiSimGraph图
        curr_node : 表项会被写入到的当前节点id
        dst : 目的节点id
        next_hop_node : 从当前节点到目的节点的下一跳节点id
        metric : 当前路径到目的节点的跳数, 或者其它用于量化该路径长度/开销的值
        """
        self.route_table_2node[curr_node][dst].add((next_hop_node, metric))
        next_hop_ports = self.get_link_ports(curr_node, next_hop_node)

        for next_hop_port in list(next_hop_ports):
            record_flag = False
            for recorded_port_metric in list(self.route_table_2port[curr_node][dst]):
                if recorded_port_metric[0] == next_hop_port:
                    if recorded_port_metric[1] > metric:
                        # 如果已有的下一跳记录跳数比当前记录大，则删除已有的
                        self.route_table_2port[curr_node][dst].remove(recorded_port_metric)
                    else:
                        # 如果已有的下一跳记录跳数比当前记录小，则保留已有的，不加入新的
                        record_flag = True
            if not record_flag:
                self.route_table_2port[curr_node][dst].add((next_hop_port, metric))

    def _add_path_to_route_table(self, path):
        if not path:
            return
        src = path[0]
        dst = path[-1]
        for i in range(0, len(path)):
            node_id = path[i]
            if self.node_is_host(node_id):
                pass

            if i >= 1:
                metric = i
                self.set_route_table(node_id, src, path[i - 1], metric)
            if i < len(path) - 1:
                metric = len(path) - i - 1
                self.set_route_table(node_id, dst, path[i + 1], metric)

    def _route_weight(self, u, v):
        return self.edges[u, v].get("route_weight", 1)

    def _reverse_forwarding_neighbors(self, node_id, dst):
        if self.node_is_host(node_id):
            if node_id != dst:
                return []
            return [neighbor for neighbor in self.neighbors(node_id) if self.node_is_switch(neighbor)]
        return list(self.neighbors(node_id))

    def _shortest_forwarding_distances_to_host(self, dst):
        distances = {dst: 0}
        hop_lengths = {dst: 0}
        heap = [(0, 0, dst)]

        while heap:
            distance, hop_length, node_id = heapq.heappop(heap)
            if distance != distances[node_id] or hop_length != hop_lengths[node_id]:
                continue

            for prev_hop in self._reverse_forwarding_neighbors(node_id, dst):
                next_distance = distance + self._route_weight(prev_hop, node_id)
                next_hop_length = hop_length + 1
                if (
                    prev_hop not in distances
                    or next_distance < distances[prev_hop]
                    or (
                        next_distance == distances[prev_hop]
                        and next_hop_length < hop_lengths[prev_hop]
                    )
                ):
                    distances[prev_hop] = next_distance
                    hop_lengths[prev_hop] = next_hop_length
                    heapq.heappush(heap, (next_distance, next_hop_length, prev_hop))

        return distances, hop_lengths

    def _gen_default_shortest_route_table(self):
        start_time = time.time()
        for dst in tqdm(self.host_ids, desc="默认最短路生成下一跳路由"):
            path_lengths, hop_lengths = self._shortest_forwarding_distances_to_host(dst)
            for node_id in self.nodes:
                if node_id == dst or node_id not in path_lengths:
                    continue
                for next_hop in self.neighbors(node_id):
                    if self.node_is_host(next_hop) and next_hop != dst:
                        continue
                    if next_hop not in path_lengths:
                        continue
                    if path_lengths[next_hop] + self._route_weight(node_id, next_hop) == path_lengths[node_id]:
                        metric = hop_lengths[next_hop] + 1
                        self.set_route_table(node_id, dst, next_hop, metric)
        end_time = time.time()
        print(f"默认最短路生成路由耗时 {end_time - start_time:.2f}s")

    def _use_default_shortest_routing(self, path_finding_algo):
        return getattr(path_finding_algo, "__name__", "") == "all_shortest_paths"

    def all_shortest_paths(self, src, dst):
        return nx.all_shortest_paths(self, src, dst, weight=None, method="dijkstra")
    
    def set_path_finding_algo(self, func):
        """设置需要的路径发现算法.
            Parameters
            ----------
            func : 算法定义

            Notes
            -----
            func只允许三个变量输入,分别是图`graph`, 源节点`src`以及目的节点`dst`.
            `src`以及`dst`皆为`host`节点.
            输出算法发现的从`src`到`dst`所有路径, 路径以有序的节点编号表示, 以`src`为开头, `dst`为结尾.
        """
        self.path_finding_algo = func

    def get_path_finding_algo(self):
        return self.path_finding_algo.__name__

    def init_routing_tables(self):
        # 初始化路由表
        if self.topo_ele_xml is None or self.node_ele_xml is None:
            self.build_graph_config()
        total_node_num = self.get_total_num()
        self.route_table_2port = []
        self.route_table_2node = []
        for i in range(total_node_num):
            self.route_table_2port.append([])
            self.route_table_2node.append([])
            for j in range(total_node_num):
                self.route_table_2port[i].append(set())
                self.route_table_2node[i].append(set())

    def gen_route_table(self, path_finding_algo=nx.all_shortest_paths, write_file=True, host_router=False, multiple_workers=1):
        """
        如果你想使用寻路算法寻找每一对host节点间的可用路径, 并基于可用路径生成路由表, 请使用本方法. 
        
        如果你想直接写入路由表项, 请使用`set_route_table`方法. 
        Parameters
        ----------
            :param path_finding_algo: 你可以自定义寻路方法. 该方法定义为`path_finding_algo(NetiSimGraph, src, dst)`.
            只允许三个变量输入, 分别是图`NetiSimGraph`, 源节点`src`以及目的节点`dst`. `src`以及`dst`皆为`host`节点.
            输出算法发现的从`src`到`dst`所有路径, 路径以有序的节点编号列表表示, 以`src`为开头, `dst`为结尾.
            :param write_file: 是否写入文件
            :param host_router: 是否包含host路由文件（对应direct_topo选项）

        """
        if self.get_total_num() > 1 * 1024:
            print(f"正在使用寻路算法生成全网路由，当前拓扑节点数较多，速度可能较慢。如果等不了建议基于拓扑特性自行生成路由表：）")
        self.init_routing_tables()

        if self._use_default_shortest_routing(path_finding_algo):
            self._gen_default_shortest_route_table()
            if write_file:
                self.write_route_table_to_xml(algo=path_finding_algo, host_router=host_router)
            return
        
        # 对每一对host间的路径进行路由表项的建立
        # paths = []
        # for m in trange(len(self.host_ids), desc="算法{}寻找所有可用路径".format(path_finding_algo.__name__)):
        #     src = self.host_ids[m]
        #     ts1 = time.time()
        #     for n in range(m, len(self.host_ids)):
        #         dst = self.host_ids[n]
        #         try:
        #             paths += path_finding_algo(self, src, dst)
        #         except nx.exception.NetworkXNoPath:
        #             # print("networkx.exception.NetworkXNoPath: {} {}".format(src, dst))
        #             pass
        
        # mp
        # 生成所有节点对
        nodes = self.host_ids
        node_pairs = list(combinations(nodes, 2))  # 生成所有无向节点对
        if multiple_workers and multiple_workers > 1:
            print(f"使用多进程加速，worker数量{multiple_workers}:")

            start_time = time.time()
            with ProcessPoolExecutor(max_workers=multiple_workers) as executor:
                futures = []
                chunk_size = len(node_pairs) // multiple_workers + 1
                for i in range(0, len(node_pairs), chunk_size):
                    chunk = node_pairs[i:i+chunk_size]
                    future = executor.submit(
                        _process_path_chunk,
                        nx.Graph(self),
                        path_finding_algo,
                        chunk
                    )
                    futures.append(future)

                paths = []
                for future in as_completed(futures):
                    try:
                        chunk_results = future.result()
                        paths += chunk_results
                    except Exception as e:
                        print(f"Error in path finding: {e}")

            end_time = time.time()
            print(f"寻路耗时 {end_time - start_time:.2f}s")

            for path in tqdm(paths, desc="填写路由表项"):
                self._add_path_to_route_table(path)
        else:
            start_time = time.time()
            for src, dst in tqdm(node_pairs, desc="算法{}寻找并填写路径".format(path_finding_algo.__name__)):
                try:
                    for path in path_finding_algo(self, src, dst):
                        self._add_path_to_route_table(path)
                except nx.exception.NetworkXNoPath:
                    pass
            end_time = time.time()
            print(f"寻路和填写路由耗时 {end_time - start_time:.2f}s")

        if write_file:
            self.write_route_table_to_xml(algo=path_finding_algo, host_router=host_router)

    def write_route_table_to_xml(self, algo=None, host_router=False):
        # 路由表写入xml文件中
        route_ele = etree.Element("router")
        route_table = self.route_table_2port

        def format_range(dst_ids):
            if len(dst_ids) == 1:
                return str(dst_ids[0])
            return f"{dst_ids[0]}..{dst_ids[-1]}"

        def add_target(route_grp_ele, dst_ids, ports):
            etree.SubElement(
                route_grp_ele,
                "target",
                node_id=format_range(dst_ids),
                port_id=ports,
            )

        for node_id in tqdm(self.nodes, desc="写入路由表"):
            # print(self.nodes[node_id]["type"])
            if self.node_is_host(node_id) and host_router is False:
                continue
            route_grp_ele = etree.SubElement(route_ele, "grp", node_id=str(node_id),
                                             node_type=self.nodes[node_id]["type"])
            route_grp_ele.set("node_id", str(node_id))
            current_dst_ids = []
            current_signature = None
            for dst_id in range(len(route_table[node_id])):
                next_ports_metric_sets = sorted(route_table[node_id][dst_id])
                if len(next_ports_metric_sets) == 0:
                    if current_dst_ids:
                        add_target(route_grp_ele, current_dst_ids, current_signature)
                        current_dst_ids = []
                        current_signature = None
                    continue
                ports = " ".join(str(port_id) for port_id in sorted({p_m[0] for p_m in next_ports_metric_sets}))
                signature = ports
                if current_dst_ids and signature == current_signature and dst_id == current_dst_ids[-1] + 1:
                    current_dst_ids.append(dst_id)
                else:
                    if current_dst_ids:
                        add_target(route_grp_ele, current_dst_ids, current_signature)
                    current_dst_ids = [dst_id]
                    current_signature = signature
            if current_dst_ids:
                add_target(route_grp_ele, current_dst_ids, current_signature)

        self.route_ele_xml = route_ele

        if not os.path.exists(self.output_dir):
            os.mkdir(self.output_dir)
        etree.indent(route_ele, space="    ")
        # print(etree.tostring(route_ele, pretty_print=True).decode(), end="")
        with open(self.output_dir + "router.xml", "w") as output_xml:
            if algo:
                output_xml.write(
                    "<!-- create with [{}] algorithm at module [{}] -->\n".format(algo.__name__, algo.__module__))
            output_xml.write(etree.tostring(route_ele, pretty_print=True).decode())
        print("路由文件已写入：", self.output_dir + "router.xml")

    def get_link_ports(self, this_node, next_hop) -> list[int]:
        """
        this_node, next_hop,输出this_node绑定的对应所有ports
        :param this_node: 当前节点
        :param next_hop: 下一跳节点
        :return: 所有的端口列表
        """
        return self.next_hop_ports[this_node][next_hop]

    def get_next_hop(self, src, target_port):  # 给定src, port,输出下一跳节点
        find_flag = False
        next_hop = -1
        for ports in self.next_hop_ports[src]:
            if target_port in ports:
                if not find_flag:
                    next_hop = self.next_hop_ports[src].index(ports)
                    find_flag = True
                else:
                    print(
                        f"节点{src}的端口{target_port}有多个目的地址：{next_hop}/{self.next_hop_ports[src].index(ports)}")

        return next_hop

    def find_all_paths_with_router(self, src, dst):
        if self.route_table_2port is None or self.route_table_2node is None:
            print("先生成NetiSimGraph图以及路由信息再调用此方法！")
            return None
        result_paths = []

        current_idx = 0
        current_path = [src]
        current_node = current_path[current_idx]

        possible_next_hops = []
        next_hops = self.route_table_2node[current_node][dst]
        possible_next_hops.append(list(next_hops))
        next_hop = possible_next_hops[current_idx].pop()[0]
        current_path.append(next_hop)
        current_idx += 1
        current_node = current_path[current_idx]
        while current_idx != 0:
            if current_node == dst:
                result_paths.append(current_path.copy())
                current_idx -= 1
                current_path = current_path[:-1]
                current_node = current_path[current_idx]
                continue
            if current_idx >= len(possible_next_hops):
                # 第一次进入当前跳数的节点，下一跳节点还未更新
                next_hops = self.route_table_2node[current_node][dst]
                possible_next_hops.append(list(next_hops))
            if len(possible_next_hops[current_idx]) == 0:
                # 当前跳数的下一跳可能节点已经全部遍历完毕，则返回上一层
                possible_next_hops = possible_next_hops[:-1]
                current_path = current_path[:-1]
                current_idx -= 1
                current_node = current_path[current_idx]
                continue
            next_hop = possible_next_hops[current_idx].pop()[0]
            current_path.append(next_hop)
            current_idx += 1
            current_node = current_path[current_idx]

        return result_paths

    def find_all_paths_host2host(self, src, dst, method="shortest"):
        if self.node_is_switch(src) or self.node_is_switch(dst):
            print("src和dst必须是host节点!任意节点间最短路径使用networkx内置函数nx.shortest_path()计算!")
            return None
        if method == "shortest":
            return nx.all_shortest_paths(self, src, dst)
        if method == "router":
            return self.find_all_paths_with_router(src, dst)

    def cost_model(self, traffic_xml):
        # 构建仿真激励
        root = etree.parse(traffic_xml).getroot()
        comm_ele = root.xpath('/dcn/packet_generator_config/app/mpi/comm/item')
        # 获得所有通信域
        for c in comm_ele:
            comm = list(netisim_utils.get_range_int(c.get('rank')))
            idx = int(c.get('index'))
            self.comm[idx] = comm

        op_ele = root.xpath('/dcn/packet_generator_config/app/mpi/op/*')
        # 获得实际使用的通信域编号
        op_info = []
        for op in op_ele:
            op_type = op.tag
            op_comm_id = int(op.get('comm_id'))
            op_comm = self.comm[op_comm_id]
            op_size_count = int(op.get('send_recv_count'))
            op_size_type = int(op.get('send_recv_type'))
            op_info.append(
                {"op_type": op_type, "op_comm_id": op_comm_id, "op_comm": op_comm, "op_size_type": op_size_type,
                 "op_size_count": op_size_count})
        print(op_info)

        for op in op_info:
            self.gen_comm_traffic(op["op_comm"], op["op_size_count"], op["op_type"])

    def gen_pair_traffic(self, src, dst, traffic_size):
        paths = self.find_all_paths_with_router(src, dst)
        size_per_path = traffic_size / len(paths)
        for path in paths:
            previous_node = -1
            for node in path:
                self.nodes[node]['comp_cost'] += size_per_path
                if not previous_node == -1:
                    self.get_edge_data(node, previous_node)['sync_cost'] += size_per_path
                previous_node = node

    def gen_comm_traffic(self, comm_ranks, comm_size, comm_type):
        if comm_type == "mpi_allreduce":
            if not is_2power(len(comm_ranks)):
                print("ERROR! only HD allreduce :(")
            else:
                total_step = int(math.log2(len(comm_ranks)))
                for s in range(total_step):
                    distance = 2 ** s
                    for i in range(0, len(comm_ranks), distance * 2):
                        for j in range(distance):
                            # print(i, j)
                            u = i + j
                            v = i + j + distance
                            self.gen_pair_traffic(u, v, 2 * comm_size / (distance * 2))  # 两倍的意思是双向都一次算进去了
        else:
            print("not for now :(")


def gen_netisim_graph_with_xml(config_xml) -> NetiSimGraph:
    root = etree.parse(config_xml).getroot()
    graph = NetiSimGraph()
    # 从xml文件中读取节点信息
    for node in root.xpath('/dcn/dcn_network/node/grp'):
        if "host" in node.get('type'):
            for host_id in netisim_utils.get_range_int(node.get('node_id')):
                graph.add_netisim_host(host_id)
        elif "node" in node.get('type'):
            for node_id in netisim_utils.get_range_int(node.get('node_id')):
                graph.add_netisim_node(node_id)

    # 从xml文件中读取链路信息
    total_node_num = graph.get_total_num()
    graph.next_hop_port = []
    for i in range(total_node_num):
        graph.next_hop_port.append([])
        for j in range(total_node_num):
            graph.next_hop_port[i].append(-1)

    for link in root.xpath('/dcn/dcn_network/topology/grp'):
        if link.get('dst_node') == '-1':
            continue
        # 为简化代码,脚本仅支持一对一的topo配置,不支持使用空格或".."分割的配置
        src_node = int(link.get('src_node'))
        dst_node = int(link.get('dst_node'))
        bandwidth = int(link.get('bandwidth'))
        delay = int(link.get('delay'))
        graph.add_netisim_edge(src_node, dst_node, bandwidth, delay)
        graph.next_hop_port[src_node][dst_node] = int(link.get('src_port'))
        graph.next_hop_port[dst_node][src_node] = int(link.get('dst_port'))

    graph.node_ele_xml = root.xpath('/dcn/dcn_network/node')[0]
    graph.topo_ele_xml = root.xpath('/dcn/dcn_network/topology')[0]
    # show node_ele_xml and topo_ele_xml
    # print(etree.tostring(self.node_ele_xml, pretty_print=True).decode(), end="")
    # print(etree.tostring(self.topo_ele_xml, pretty_print=True).decode(), end="")

    return graph

def get_2power_floor(k):
    # 输出小于等于k
    i = 1
    while i < k:
        i = i << 1
    return i >> 1


def is_2power(k):
    return not (k & k - 1)


def trim_graph(graph: NetiSimGraph, traffic_xml):
    # 构建仿真激励
    root = etree.parse(traffic_xml).getroot()
    comm_ele = root.xpath('/dcn/packet_generator_config/app/mpi/comm/item')
    # 获得所有通信域
    for c in comm_ele:
        comm = list(netisim_utils.get_range_int(c.get('rank')))
        idx = int(c.get('index'))
        graph.comm[idx] = comm

    op_ele = root.xpath('/dcn/packet_generator_config/app/mpi/op/*')
    # 获得实际使用的通信域编号
    for op in op_ele:
        op_comm_id = int(op.get('comm_id'))
        graph.avtive_comm_id.add(op_comm_id)

    for c_id in graph.avtive_comm_id:
        for i in range(len(graph.comm[c_id])):
            for j in range(i + 1, len(graph.comm[c_id])):
                for path in graph.find_all_paths_host2host(graph.comm[c_id][i], graph.comm[c_id][j], method="router"):
                    graph.avtive_ids.update(path)
                    # print(graph.avtive_ids, path)

    inactive_ids = set(graph.nodes) - graph.avtive_ids
    for i in inactive_ids:
        graph.remove_node(i)

    # print("旧配置文件节点列表" + str(list(graph.nodes)))
    # print("旧配置文件连线列表" + str(list(graph.edges)))

    trimed_graph = NetiSimGraph()
    mapping = {}  # 旧节点编号到新节点编号的映射 mapping[old_id] = new_id
    new_id = 0
    for node_id in graph.nodes:

        if graph.node_is_host(node_id):
            trimed_graph.add_netisim_host(new_id)
        else:
            trimed_graph.add_netisim_node(new_id)
        mapping[node_id] = new_id
        new_id += 1

    for edge in graph.edges:
        u, v = edge
        trimed_graph.add_netisim_edge(mapping[u], mapping[v], bandwidth=graph.edges[u, v]['bandwidth'],
                                      delay=graph.edges[u, v]['delay'])

    output_name = "dcn2.0_config_opt.xml"
    trimed_graph.build_graph_config(template_xml=traffic_xml, output_name=output_name)

    # 基于mapping生成对应仿真激励
    app_ele = root.xpath('/dcn/packet_generator_config/app/mpi')[0]
    app_ele.set("world_size", str(len(trimed_graph.host_ids)))
    world_rank_mapping_ele = root.xpath('/dcn/packet_generator_config/app/mpi/world_rank_mapping')[0]
    world_rank_mapping_ele.set("rank", "0..{}".format(len(trimed_graph.host_ids) - 1))
    world_rank_mapping_ele = root.xpath('/dcn/packet_generator_config/app/mpi/world_rank_mapping/item')[0]
    world_rank_mapping_ele.set("rank", "0..{}".format(len(trimed_graph.host_ids) - 1))
    world_rank_mapping_ele.set("host_id", "0..{}".format(len(trimed_graph.host_ids) - 1))
    comm_ele = root.xpath('/dcn/packet_generator_config/app/mpi/comm/item')
    for c in comm_ele:
        comm = list(netisim_utils.get_range_int(c.get('rank')))
        idx = int(c.get('index'))
        if idx not in graph.avtive_comm_id:
            continue
        new_comm = []
        for i in comm:
            if i in mapping:
                new_comm.append(mapping[i])
        c.set("rank", " ".join([str(i) for i in new_comm]))
    # 替换xml文件中对应字段
    etree.indent(root, space="    ")
    # print(etree.tostring(root_config, pretty_print=True).decode(), end="")
    with open(trimed_graph.output_dir + output_name, "w") as output_xml:
        output_xml.write(etree.tostring(root, pretty_print=True).decode())
    print("仿真激励已写入：", trimed_graph.output_dir + output_name)

    # 路由表映射
    # 按照route_table_2node以及mapping进行映射
    trimed_graph.init_routing_tables()
    # trimed_graph.route_table_2node = []
    # trimed_graph.route_table_2port = []
    # for i in range(trimed_graph.get_total_num()):
    #     trimed_graph.route_table_2node.append([])
    #     trimed_graph.route_table_2port.append([])
    #     for j in range(trimed_graph.get_total_num()):
    #         trimed_graph.route_table_2node[i].append(set())
    #         trimed_graph.route_table_2port[i].append(set())

    for i in range(len(graph.route_table_2node)):
        if i not in mapping:
            continue
        for j in range(len(graph.route_table_2node[i])):
            if j not in mapping:
                continue
            for tuple_next_hop_metric in graph.route_table_2node[i][j]:
                next_hop = tuple_next_hop_metric[0]
                metric = tuple_next_hop_metric[1]
                trimed_graph.set_route_table(mapping[i], mapping[j], mapping[next_hop], metric)
                # trimed_graph.route_table_2node[mapping[i]][mapping[j]].add(mapping[next_hop])
                # # print("new: {}->{} next_hop:{}".format(mapping[i], mapping[j], mapping[next_hop]))
                # trimed_graph.route_table_2port[mapping[i]][mapping[j]].add(trimed_graph.get_link_port(mapping[i], mapping[next_hop]))

    # 打印旧id到新id的映射关系,并写入到文件mapping.txt
    print("旧id到新id的映射关系写入: {}".format(trimed_graph.output_dir + "mapping.csv"))
    with open(trimed_graph.output_dir + "mapping.csv", "w") as f:
        f.write("old_id,new_id\n")
        for old_id, new_id in mapping.items():
            f.write("{},{}\n".format(old_id, new_id))
    # print("新配置文件拓扑列表" + str(list(trimed_graph.nodes)))
    # print("新配置文件连线列表" + str(list(trimed_graph.edges)))
    # for i in range(len(trimed_graph.route_table_2port)):
    #     print(trimed_graph.route_table_2port[i])

    trimed_graph.write_route_table_to_xml()

    return trimed_graph


NETISIM_MOD = "ft2_"
HOST_TYPE = NETISIM_MOD + "host"
NODE_TYPE = NETISIM_MOD + "node"

COMP_DELAY = 1300
TO_DIR = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime()) + "/"


def user_topo_1DFMClosX10():
    graph = NetiSimGraph()
    host_num = 64
    leaf_sw_num = 80  # 8组*10个union
    spine_sw_num = 10  # 10个5808, 连接每组同号卡
    total_node_num = host_num + leaf_sw_num + spine_sw_num

    hostid_matrix = np.array([[x * 8 + y for y in range(8)] for x in range(8)])

    # step1: 生成节点,要求host在前,node在后,且顺序编号,不符合要求会报错
    for host_id in range(host_num):
        graph.add_netisim_host(host_id, comp_delay=COMP_DELAY)

    for leaf_sw_id in range(leaf_sw_num):
        graph.add_netisim_node(leaf_sw_id + host_num, comp_delay=COMP_DELAY)

    for spine_sw_id in range(spine_sw_num):
        graph.add_netisim_node(spine_sw_id + host_num + leaf_sw_num, comp_delay=COMP_DELAY)

    # step2: 生成拓扑连线,按照自定义拓扑,将指定id的节点(host或node皆可)进行连线并指定带宽和时延(发包器会自动连接)
    # X轴fullmesh
    for x in range(8):
        for y in range(8):
            host_id = x * 8 + y
            for neighbor in range(x * 8, x * 8 + 8):
                if not host_id == neighbor:
                    graph.add_netisim_edge(host_id, neighbor, bandwidth='400', delay='20')

    # Y轴8轨union
    for swunion_rail_id in range(8):
        union_neighbors = np.nditer(hostid_matrix[swunion_rail_id, :])
        print("=========")
        for host_id in union_neighbors:
            print(host_id)
            for union in range(10):
                union_id = host_num + swunion_rail_id * 10 + union
                print(host_id, union_id)
                graph.add_netisim_edge(int(host_id), union_id, bandwidth='400', delay='20')

    for sw5808_i in range(10):
        print("=========")
        for swunion_rail_id in range(8):
            sw5808_id = host_num + leaf_sw_num + sw5808_i
            union_id = host_num + swunion_rail_id * 10 + sw5808_i
            print(sw5808_id, union_id)
            for _ in range(8):
                graph.add_netisim_edge(sw5808_id, union_id, bandwidth='400', delay='20', edge_count=8)

    # 生成配置文件,build_graph_config会生成一系列中间数据,最终生成dcn2.0_config.xml文件
    graph.build_graph_config(output_name="dcn2.0_config.xml")
    # 生成路由表,gen_route_table会依赖build_graph_config产生的中间数据,最终生成router.xml文件
    graph.gen_route_table()


def user_topo_1DFMClosX8():
    graph = NetiSimGraph()
    host_num = 64
    leaf_sw_num = 4 + 4 * 4  # 4个5808 4*4个union
    spine_sw_num = 0
    total_node_num = host_num + leaf_sw_num + spine_sw_num

    hostid_matrix = np.array([[x * 8 + y for y in range(8)] for x in range(8)])

    # step1: 生成节点,要求host在前,node在后,且顺序编号,不符合要求会报错
    for host_id in range(host_num):
        graph.add_netisim_host(host_id, comp_delay=COMP_DELAY)

    for leaf_sw_id in range(leaf_sw_num):
        graph.add_netisim_node(leaf_sw_id + host_num, comp_delay=COMP_DELAY)

    for spine_sw_id in range(spine_sw_num):
        graph.add_netisim_node(spine_sw_id + host_num + leaf_sw_num, comp_delay=COMP_DELAY)

    # step2: 生成拓扑连线,按照自定义拓扑,将指定id的节点(host或node皆可)进行连线并指定带宽和时延(发包器会自动连接)
    for x in range(8):
        for y in range(8):
            host_id = x * 8 + y
            for neighbor in range(x * 8, x * 8 + 8):
                if not host_id == neighbor:
                    graph.add_netisim_edge(host_id, neighbor, bandwidth='400', delay='20')

    for sw5808_id in range(host_num, host_num + 4):
        for host_id in range(host_num):
            graph.add_netisim_edge(host_id, sw5808_id, bandwidth='400', delay='20')

    for swunion_rail_id in range(host_num + 4, host_num + 4 + 4 * 4, 4):
        swunion_id = 0
        for y in range(0, 8, 2):
            union_neighbors = np.nditer(hostid_matrix[:, y:y + 2])
            # print(hostid_matrix[:,y:y+2])
            # print(swunion_rail_id + swunion_id)
            for host_id in union_neighbors:
                graph.add_netisim_edge(int(host_id), swunion_rail_id + swunion_id, bandwidth='400', delay='20')
                # print(int(host_id), swunion_rail_id + swunion_id)
                # print("================")
            swunion_id += 1
    # 生成配置文件,build_graph_config会生成一系列中间数据,最终生成dcn2.0_config.xml文件
    graph.build_graph_config(output_name="dcn2.0_config.xml")
    # 生成路由表,gen_route_table会依赖build_graph_config产生的中间数据,最终生成router.xml文件
    graph.gen_route_table()


# 用例1:用户自定义拓扑,并生成xml文件以及通过最短路径算法生成路由文件
def user_topo():
    graph = NetiSimGraph()
    host_num = 8
    leaf_sw_num = 4
    spine_sw_num = 4
    total_node_num = host_num + leaf_sw_num + spine_sw_num

    # step1: 生成节点,要求host在前,node在后,且顺序编号,不符合要求会报错
    for host_id in range(host_num):
        graph.add_netisim_host(host_id)

    for leaf_sw_id in range(leaf_sw_num):
        graph.add_netisim_node(leaf_sw_id + host_num, comp_delay=COMP_DELAY)

    for spine_sw_id in range(spine_sw_num):
        graph.add_netisim_node(spine_sw_id + host_num + leaf_sw_num, comp_delay=COMP_DELAY)

    # step2: 生成拓扑连线,按照自定义拓扑,将指定id的节点(host或node皆可)进行连线并指定带宽和时延(发包器会自动连接)
    for host_id in range(host_num):
        graph.add_netisim_edge(host_id, host_num + int(host_id / 2), bandwidth='200', delay='20')

    for lsw_id in range(host_num, host_num + leaf_sw_num):
        for ssw_id in range(host_num + leaf_sw_num, host_num + leaf_sw_num + spine_sw_num):
            graph.add_netisim_edge(lsw_id, ssw_id, bandwidth='200', delay='20')

    # 生成配置文件,build_graph_config会生成一系列中间数据,最终生成dcn2.0_config.xml文件
    graph.build_graph_config(output_name="dcn2.0_config.xml", write_flag=False)
    # 生成路由表,gen_route_table会依赖build_graph_config产生的中间数据,最终生成router.xml文件
    graph.gen_route_table(write_file=False)
    return graph


def user_topo_pfc():
    graph = NetiSimGraph()
    # host_num = 5
    host_num = 256
    # leaf_sw_num = 2
    leaf_sw_num = 14
    # spine_sw_num = 2
    spine_sw_num = 24
    total_node_num = host_num + leaf_sw_num + spine_sw_num

    # step1: 生成节点,要求host在前,node在后,且顺序编号,不符合要求会报错
    for host_id in range(host_num):
        graph.add_netisim_host(host_id)

    for leaf_sw_id in range(leaf_sw_num):
        graph.add_netisim_node(leaf_sw_id + host_num, comp_delay=COMP_DELAY)

    for spine_sw_id in range(spine_sw_num):
        graph.add_netisim_node(spine_sw_id + host_num + leaf_sw_num, comp_delay=COMP_DELAY)

    # step2: 生成拓扑连线,按照自定义拓扑,将指定id的节点(host或node皆可)进行连线并指定带宽和时延(发包器会自动连接)
    # for host_id in [0, 1]:
    #     graph.add_netisim_edge(host_id, 5, weight='1', bandwidth='200', delay='20')

    # npu to leaf
    for step_cnt in range(0, 5):
        for leaf_node in range(256 + step_cnt * 2, 256 + (step_cnt + 1) * 2):
            for host_id in range(step_cnt * 48, (step_cnt + 1) * 48):
                graph.add_netisim_edge(host_id, leaf_node, weight="2", bandwidth="200", delay="20", num=1)

    for host_id in range(240, 248):
        for leaf_node in range(266, 268):
            graph.add_netisim_edge(host_id, leaf_node, weight="2", bandwidth="200", delay="20", num=1)

    for host_id in range(248, 256):
        for leaf_node in range(268, 270):
            graph.add_netisim_edge(host_id, leaf_node, weight="2", bandwidth="200", delay="20", num=1)

    # leaf to spine
    for leaf_node in range(256, 270):
        for spine_node in range(270, 294):
            graph.add_netisim_edge(leaf_node, spine_node, weight="1", bandwidth="200", delay="20", num=1)

    # spine to spine
    # for step_cnt in range(0, 16):
    #     for ssw_id_1 in range(step_cnt*4+1088, (step_cnt+1)*4+1088):
    #         for tt in range(1, 16):
    #             if ssw_id_1+(4*tt) <= 1151:
    #                 ssw_id_2 = ssw_id_1+(4*tt)
    #                 graph.add_netisim_edge(ssw_id_1, ssw_id_2, weight="1", bandwidth="200", delay="20", num=1)

    # for lsw_id in range(host_num, host_num + leaf_sw_num):
    #     for ssw_id in range(host_num + leaf_sw_num, host_num + leaf_sw_num + spine_sw_num):
    #         graph.add_netisim_edge(lsw_id, ssw_id, weight='1', bandwidth='200', delay='20')
    # print(graph.key_value_in_everyedge)
    # 生成配置文件,build_graph_config会生成一系列中间数据,最终生成dcn2.0_config.xml文件
    graph.build_graph_config(output_name="dcn2.0_config.xml")

    # 生成路由表,gen_route_table会依赖build_graph_config产生的中间数据,最终生成router.xml文件
    graph.gen_route_table()


# 用例2:基于用户指定的仿真激励,对拓扑进行修剪,并生成xml文件以及通过最短路径算法生成路由文件
def pre_sim():
    # 给定已经写好的dcn2.0_config.xml和router.xml,生成对应NetiSimGraph对象
    comfig_xml_path = traffic_xml_path = './output/2024-06-03_16-26-10/dcn2.0_config.xml'
    router_xml_path = './output/2024-06-03_16-26-10/router.xml'
    graph = gen_netisim_graph_with_xml(comfig_xml_path, router_xml_path)
    # 修剪拓扑,生成dcn2.0_config_opt.xml和router.xml
    trim_graph(graph, traffic_xml_path)


if __name__ == '__main__':
    user_topo_pfc()
    exit()
    comfig_xml_path = traffic_xml_path = './output/busypod128host_testcut/dcn2.0_config.xml'
    router_xml_path = './output/busypod128host_testcut/router.xml'
    graph = gen_netisim_graph_with_xml(comfig_xml_path, router_xml_path)
    print(graph.find_all_paths_with_router(0, 8))
    graph.cost_model(traffic_xml_path)
