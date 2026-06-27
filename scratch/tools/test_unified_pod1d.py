import csv
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

import unified_pod1d as casegen


SMALL_PARAMS = casegen.TopologyParams(
    pod_num=2,
    node_per_pod=2,
    npu_per_node=4,
    l1_switch_per_pod=4,
    l2_plane_num=4,
    l2_switch_per_plane=2,
    l1_to_each_l2_ports=2,
    host_to_each_l1_ports=1,
)


ECMP_PARAMS = casegen.TopologyParams(
    pod_num=1,
    node_per_pod=1,
    npu_per_node=4,
    l1_switch_per_pod=2,
    l2_plane_num=2,
    l2_switch_per_plane=1,
    l1_to_each_l2_ports=1,
    host_to_each_l1_ports=1,
)


def _assert_first_path_is_written_before_second_path(graph, src, dst):
    yield [src, 2, dst]
    if not graph.route_table_2port[src][dst]:
        raise AssertionError("route table was not updated before the next path was requested")
    yield [src, 3, dst]


def _build_two_path_ns3_graph():
    graph = casegen.netsim.NetworkSimulationGraph()
    graph.add_netisim_host(0, forward_delay=casegen.FORWARD_DELAY)
    graph.add_netisim_host(1, forward_delay=casegen.FORWARD_DELAY)
    graph.add_netisim_node(2, forward_delay=casegen.FORWARD_DELAY)
    graph.add_netisim_node(3, forward_delay=casegen.FORWARD_DELAY)
    graph.add_netisim_edge(0, 2, bandwidth=casegen.NS3_NODE_LINK_BW, delay=casegen.LINK_DELAY)
    graph.add_netisim_edge(2, 1, bandwidth=casegen.NS3_NODE_LINK_BW, delay=casegen.LINK_DELAY)
    graph.add_netisim_edge(0, 3, bandwidth=casegen.NS3_NODE_LINK_BW, delay=casegen.LINK_DELAY)
    graph.add_netisim_edge(3, 1, bandwidth=casegen.NS3_NODE_LINK_BW, delay=casegen.LINK_DELAY)
    graph.build_graph_config()
    return graph


def _build_two_path_netisim_graph():
    graph = casegen.netisim_graph.NetiSimGraph()
    graph.add_netisim_host(0)
    graph.add_netisim_host(1)
    graph.add_netisim_node(2)
    graph.add_netisim_node(3)
    graph.add_netisim_edge(0, 2, bandwidth=casegen.NETISIM_NODE_LINK_BW, delay=casegen.NETISIM_LINK_DELAY)
    graph.add_netisim_edge(2, 1, bandwidth=casegen.NETISIM_NODE_LINK_BW, delay=casegen.NETISIM_LINK_DELAY)
    graph.add_netisim_edge(0, 3, bandwidth=casegen.NETISIM_NODE_LINK_BW, delay=casegen.NETISIM_LINK_DELAY)
    graph.add_netisim_edge(3, 1, bandwidth=casegen.NETISIM_NODE_LINK_BW, delay=casegen.NETISIM_LINK_DELAY)
    graph.build_graph_config(
        str(casegen.DEFAULT_NETISIM_TEMPLATE),
        node_gen_delay=casegen.NETISIM_LINK_DELAY,
        write_flag=False,
    )
    return graph


def _find_target_covering_node(route_group, node_id):
    for target in route_group.findall("target"):
        target_id = target.attrib["node_id"]
        if ".." in target_id:
            start, end = (int(value) for value in target_id.split(".."))
            if start <= node_id <= end:
                return target
        elif int(target_id) == node_id:
            return target
    return None


class UnifiedPod1dTest(unittest.TestCase):
    def test_unified_generator_reuses_original_platform_builders(self):
        source = Path(casegen.__file__).read_text(encoding="utf-8")

        self.assertIn("import netisim_graph", source)
        self.assertIn("import net_sim_builder as netsim", source)
        self.assertIn("netisim_graph.NetiSimGraph()", source)
        self.assertIn("netsim.NetworkSimulationGraph()", source)
        self.assertIn("graph.write_config()", source)
        self.assertIn("host_router=False", source)
        self.assertNotIn("single_shortest_path", source)
        self.assertNotIn("path_finding_algo=", source)
        self.assertNotIn("from lxml import etree", source)
        self.assertNotIn("xml.etree.ElementTree", source)
        self.assertNotIn("postprocess_netisim_config", source)
        self.assertNotIn("sync_process_partition", source)
        self.assertNotIn("def write_netisim_router_xml", source)
        self.assertNotIn("def write_ns3_node_csv", source)

    def test_default_params_match_original_pod1d_constants(self):
        params = casegen.TopologyParams()
        layout = casegen.build_id_layout(params)

        self.assertEqual(params.pod_num, 19)
        self.assertEqual(params.node_per_pod, 9)
        self.assertEqual(params.npu_per_node, 8)
        self.assertEqual(params.l1_switch_per_pod, 24)
        self.assertEqual(params.l2_plane_num, 24)
        self.assertEqual(params.l2_switch_per_plane, 4)
        self.assertEqual(params.l1_to_each_l2_ports, 9)
        self.assertEqual(params.host_to_each_l1_ports, 1)
        self.assertEqual(layout.host_num, 1368)
        self.assertEqual(layout.access_base_id, 1368)
        self.assertEqual(layout.l1_base_id, 2736)
        self.assertEqual(layout.l2_base_id, 3192)

    def test_builds_same_pod1d_topology_on_both_existing_graph_types(self):
        ns3_graph, ns3_ids = casegen.build_ns3_graph(SMALL_PARAMS)
        netisim_graph, netisim_ids = casegen.build_netisim_graph(SMALL_PARAMS)

        self.assertEqual(type(ns3_graph).__name__, "NetworkSimulationGraph")
        self.assertEqual(type(netisim_graph).__name__, "NetiSimGraph")
        self.assertEqual(ns3_ids.host_ids, list(range(16)))
        self.assertNotIn("sw1825", ns3_ids.switch_groups)
        self.assertNotIn("sw1650", ns3_ids.switch_groups)
        self.assertEqual(ns3_ids.switch_groups["access"], list(range(16, 32)))
        self.assertEqual(ns3_ids.switch_groups["l1"], list(range(32, 40)))
        self.assertEqual(ns3_ids.switch_groups["l2"], list(range(40, 48)))
        self.assertEqual(ns3_ids, netisim_ids)
        self.assertEqual(sorted(ns3_graph.edges()), sorted(netisim_graph.edges()))
        self.assertEqual(sum(data["edge_count"] for _, _, data in ns3_graph.edges(data=True)), 112)

        link_counts = {(u, v): data["edge_count"] for u, v, data in ns3_graph.edges(data=True)}
        self.assertEqual(link_counts[(0, 16)], 1)
        self.assertEqual(link_counts[(16, 32)], 1)
        self.assertEqual(link_counts[(16, 35)], 1)
        self.assertEqual(link_counts[(32, 40)], 1)
        self.assertEqual(link_counts[(32, 43)], 1)
        self.assertEqual(casegen.host_egress_count(SMALL_PARAMS), 1)

    def test_netisim_fault_half_bandwidth_updates_first_access_to_l1_link(self):
        graph, _ = casegen.build_netisim_graph(SMALL_PARAMS, fault="npu0_l1_bw56")
        layout = casegen.build_id_layout(SMALL_PARAMS)

        first_access = casegen.access_switch_id(layout, 0)
        first_l1 = casegen.l1_switch_id(SMALL_PARAMS, layout, 0, 0)
        second_l1 = casegen.l1_switch_id(SMALL_PARAMS, layout, 0, 1)

        self.assertEqual(graph.edges[first_access, first_l1]["bandwidth"], "56")
        self.assertEqual(graph.edges[first_access, first_l1]["delay"], casegen.NETISIM_LINK_DELAY)
        self.assertEqual(graph.edges[first_access, second_l1]["bandwidth"], casegen.NETISIM_L1_LINK_BW)

    def test_netisim_fault_removed_omits_first_access_to_l1_link(self):
        graph, _ = casegen.build_netisim_graph(SMALL_PARAMS, fault="npu0_l1_removed")
        layout = casegen.build_id_layout(SMALL_PARAMS)

        first_access = casegen.access_switch_id(layout, 0)
        first_l1 = casegen.l1_switch_id(SMALL_PARAMS, layout, 0, 0)
        second_l1 = casegen.l1_switch_id(SMALL_PARAMS, layout, 0, 1)

        self.assertFalse(graph.has_edge(first_access, first_l1))
        self.assertTrue(graph.has_edge(first_access, second_l1))

    def test_generates_ns3_and_netisim_cases_through_existing_builders(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = casegen.generate_cases(
                target="both",
                output_root=Path(tmp),
                route_workers=1,
                params=SMALL_PARAMS,
            )

            ns3_dir = result["ns3"]
            netisim_dir = result["netisim"]

            self.assertTrue((ns3_dir / "node.csv").exists())
            self.assertTrue((ns3_dir / "topology.csv").exists())
            self.assertTrue((ns3_dir / "routing_table.csv").exists())
            self.assertTrue((ns3_dir / "traffic.csv").exists())
            self.assertTrue((ns3_dir / "transport_channel.csv").exists())
            self.assertFalse((ns3_dir / "network_attribute.txt").exists())

            with (ns3_dir / "node.csv").open(newline="", encoding="utf-8") as f:
                node_rows = list(csv.DictReader(f))
            self.assertEqual(node_rows[0]["nodeId"], "0..15")
            self.assertEqual(node_rows[0]["nodeType"], "DEVICE")
            self.assertEqual(node_rows[0]["portNum"], "1")

            with (ns3_dir / "topology.csv").open(newline="", encoding="utf-8") as f:
                topology_rows = list(csv.DictReader(f))
            self.assertEqual(len(topology_rows), 112)
            self.assertIn(
                {
                    "nodeId1": "32",
                    "portId1": "8",
                    "nodeId2": "40",
                    "portId2": "0",
                    "bandwidth": "224Gbps",
                    "delay": "20ns",
                },
                topology_rows,
            )
            self.assertIn(
                {
                    "nodeId1": "0",
                    "portId1": "0",
                    "nodeId2": "16",
                    "portId2": "0",
                    "bandwidth": "400Gbps",
                    "delay": "0ns",
                },
                topology_rows,
            )

            xml_path = netisim_dir / "dcn2.0_config.xml"
            self.assertTrue(xml_path.exists())
            self.assertTrue((netisim_dir / "rdma_operate.txt").exists())
            root = ET.parse(xml_path).getroot()
            node_groups = root.findall("./dcn_network/node/grp")
            self.assertEqual(
                [group.attrib["type"] for group in node_groups],
                ["ft2_host", "ft2_node", "ft2_node", "ft2_node"],
            )
            self.assertEqual(
                [group.attrib["node_id"] for group in node_groups],
                ["0..15", "16..31", "32..39", "40..47"],
            )
            self.assertEqual(node_groups[0].attrib["comp_delay"], "0")
            self.assertEqual(node_groups[1].attrib["comp_delay"], "225")
            self.assertEqual(node_groups[2].attrib["comp_delay"], "225")
            self.assertEqual(node_groups[3].attrib["comp_delay"], "225")
            partition_chips = root.findall(
                "./dcn_network/mpi_multi_processing/process_partition/"
                "overlap_partition/chip"
            )
            self.assertEqual(
                [chip.attrib["dev_id"] for chip in partition_chips],
                [group.attrib["node_id"] for group in node_groups],
            )
            node_template_ids = [
                group.attrib["config_template"]
                for group in node_groups
                if group.attrib["type"] == "ft2_node"
            ]
            xml_template_ids = [
                template.attrib["id"]
                for template in root.findall("./dcn_network/xml_template/template")
            ]
            self.assertEqual(xml_template_ids, node_template_ids)
            ft_node_config = root.find("./dcn_common_node_config/ft_node/node_config")
            self.assertIsNotNone(ft_node_config)
            self.assertEqual(ft_node_config.attrib["host_num"], "16")
            self.assertEqual(ft_node_config.attrib["leaf_num"], "16")
            self.assertEqual(ft_node_config.attrib["spine_num"], "8")
            self.assertEqual(ft_node_config.attrib["core_num"], "8")
            self.assertEqual(ft_node_config.attrib["top_num"], "0")
            self.assertEqual(ft_node_config.attrib["direct_topo"], "false")
            credit_fc = root.find("./dcn_common_node_config/ft_host/credit_fc")
            self.assertIsNotNone(credit_fc)
            self.assertEqual(credit_fc.attrib["direct_topo"], "false")

            links = root.findall("./dcn_network/topology/grp")
            self.assertEqual(node_groups[0].attrib["port_num"], "2")
            self.assertEqual(len(links), 113)
            self.assertEqual(sum(1 for link in links if link.attrib["dst_node"] == "-1"), 1)
            self.assertEqual(links[0].attrib["src_node"], "0..15")
            self.assertEqual(links[0].attrib["src_port"], "0")
            self.assertEqual(links[0].attrib["dst_node"], "-1")
            self.assertEqual(links[0].attrib["dst_port"], "0..15")
            self.assertEqual(links[0].attrib["bandwidth"], "4000")
            self.assertEqual(links[0].attrib["delay"], "10")
            self.assertEqual(links[1].attrib["src_node"], "0")
            self.assertEqual(links[1].attrib["src_port"], "1")
            self.assertEqual(links[1].attrib["dst_node"], "16")
            self.assertEqual(links[1].attrib["dst_port"], "0")
            self.assertEqual(links[1].attrib["delay"], "0")

            router = ET.parse(netisim_dir / "router.xml").getroot()
            self.assertEqual(router.tag, "router")
            self.assertGreater(len(router.findall("grp")), 0)
            self.assertIsNone(router.find("./grp[@node_id='0']"))
            self.assertIsNotNone(router.find("./grp[@node_id='16']"))

    def test_default_shortest_paths_generate_ecmp_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = casegen.generate_cases(
                target="netisim",
                output_root=Path(tmp),
                route_workers=1,
                params=ECMP_PARAMS,
            )

            router = ET.parse(result["netisim"] / "router.xml").getroot()
            group = router.find("./grp[@node_id='4']")
            self.assertIsNotNone(group)
            target = _find_target_covering_node(group, 1)

            self.assertIsNotNone(target)
            self.assertEqual(target.attrib["port_id"].split(), ["1", "2"])
            self.assertNotIn("metric", target.attrib)

    def test_pod1d_routes_use_l1_when_hosts_are_in_the_same_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = casegen.generate_cases(
                target="netisim",
                output_root=Path(tmp),
                route_workers=1,
                params=SMALL_PARAMS,
            )

            router = ET.parse(result["netisim"] / "router.xml").getroot()
            group = router.find("./grp[@node_id='16']")
            self.assertIsNotNone(group)
            target = _find_target_covering_node(group, 2)

            self.assertIsNotNone(target)
            self.assertEqual(target.attrib["port_id"].split(), ["1", "2", "3", "4"])
            self.assertNotIn("metric", target.attrib)

    def test_pod1d_routes_use_l1_when_hosts_are_in_different_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = casegen.generate_cases(
                target="netisim",
                output_root=Path(tmp),
                route_workers=1,
                params=SMALL_PARAMS,
            )

            router = ET.parse(result["netisim"] / "router.xml").getroot()
            group = router.find("./grp[@node_id='16']")
            self.assertIsNotNone(group)
            target = _find_target_covering_node(group, 4)

            self.assertIsNotNone(target)
            self.assertEqual(target.attrib["port_id"].split(), ["1", "2", "3", "4"])
            self.assertNotIn("metric", target.attrib)

    def test_netisim_router_xml_compresses_consecutive_targets_with_same_ports(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = casegen.netisim_graph.NetiSimGraph()
            for host_id in range(4):
                graph.add_netisim_host(host_id)
            graph.add_netisim_node(4)
            graph.output_dir = str(Path(tmp)) + "/"
            total_node_num = graph.get_total_num()
            graph.route_table_2port = [[set() for _ in range(total_node_num)] for _ in range(total_node_num)]
            graph.route_table_2node = [[set() for _ in range(total_node_num)] for _ in range(total_node_num)]
            graph.route_table_2port[4][0].add((0, 1))
            for dst_id in range(1, 4):
                graph.route_table_2port[4][dst_id].update((port_id, 2) for port_id in range(1, 9))

            graph.write_route_table_to_xml(host_router=True)

            router = ET.parse(Path(tmp) / "router.xml").getroot()
            node = router.find("./grp[@node_id='4']")
            self.assertIsNotNone(node)
            targets = [(target.attrib["node_id"], target.attrib["port_id"]) for target in node.findall("target")]
            self.assertIn(("0", "0"), targets)
            self.assertIn(("1..3", "1 2 3 4 5 6 7 8"), targets)
            self.assertFalse(any("metric" in target.attrib for target in node.findall("target")))
            self.assertIsNone(node.find("./target[@node_id='1']"))

    def test_netisim_default_shortest_routing_does_not_enumerate_all_paths(self):
        graph = _build_two_path_netisim_graph()

        def exploding_all_paths(graph, src, dst):
            raise AssertionError("default shortest routing should use next-hop distances")

        exploding_all_paths.__name__ = "all_shortest_paths"
        graph.gen_route_table(
            write_file=False,
            host_router=True,
            path_finding_algo=exploding_all_paths,
            multiple_workers=1,
        )

        self.assertGreaterEqual(len(graph.route_table_2port[0][1]), 2)

    def test_default_shortest_routing_does_not_use_host_transit(self):
        graph = casegen.netisim_graph.NetiSimGraph()
        graph.add_netisim_host(0)
        graph.add_netisim_host(1)
        graph.add_netisim_node(2)
        graph.add_netisim_node(3)
        graph.add_netisim_edge(0, 3, bandwidth=casegen.NETISIM_NODE_LINK_BW, delay=casegen.NETISIM_LINK_DELAY)
        graph.add_netisim_edge(1, 2, bandwidth=casegen.NETISIM_NODE_LINK_BW, delay=casegen.NETISIM_LINK_DELAY)
        graph.add_netisim_edge(1, 3, bandwidth=casegen.NETISIM_NODE_LINK_BW, delay=casegen.NETISIM_LINK_DELAY)
        graph.build_graph_config(
            str(casegen.DEFAULT_NETISIM_TEMPLATE),
            node_gen_delay=casegen.NETISIM_LINK_DELAY,
            write_flag=False,
        )

        graph.gen_route_table(
            write_file=False,
            host_router=True,
            multiple_workers=1,
        )

        self.assertEqual(graph.route_table_2port[2][0], set())

    def test_l1_reaches_faulted_host_through_l2_without_host_transit(self):
        graph, _ = casegen.build_netisim_graph(SMALL_PARAMS)
        layout = casegen.build_id_layout(SMALL_PARAMS)
        graph.remove_edge(
            casegen.access_switch_id(layout, 0),
            casegen.l1_switch_id(SMALL_PARAMS, layout, 0, 0),
        )
        graph.build_graph_config(
            str(casegen.DEFAULT_NETISIM_TEMPLATE),
            node_gen_delay=casegen.NETISIM_LINK_DELAY,
            direct_topo=False,
            write_flag=False,
        )

        graph.gen_route_table(
            write_file=False,
            host_router=True,
            multiple_workers=1,
        )

        self.assertEqual(
            sorted(port_id for port_id, _ in graph.route_table_2port[32][0]),
            [7, 8, 9, 10],
        )

    def test_single_worker_route_generation_streams_paths_into_route_tables(self):
        ns3_graph = _build_two_path_ns3_graph()
        ns3_graph.gen_route_table(
            write_file=False,
            host_router=True,
            path_finding_algo=_assert_first_path_is_written_before_second_path,
            multiple_workers=1,
        )
        self.assertGreaterEqual(len(ns3_graph.route_table_2port[0][1]), 2)

        netisim_graph = _build_two_path_netisim_graph()
        netisim_graph.gen_route_table(
            write_file=False,
            host_router=True,
            path_finding_algo=_assert_first_path_is_written_before_second_path,
            multiple_workers=1,
        )
        self.assertGreaterEqual(len(netisim_graph.route_table_2port[0][1]), 2)

    def test_regeneration_removes_stale_files_from_previous_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            ns3_dir = output_root / "ns3"
            netisim_dir = output_root / "netisim"
            ns3_dir.mkdir()
            netisim_dir.mkdir()
            (ns3_dir / "network_attribute.txt").write_text("old\n", encoding="utf-8")
            (ns3_dir / "transport_channel.csv").write_text("old\n", encoding="utf-8")
            (netisim_dir / "rdma_operate.txt").write_text("old\n", encoding="utf-8")

            casegen.generate_cases(
                target="both",
                output_root=output_root,
                route_workers=1,
                params=SMALL_PARAMS,
            )

            self.assertFalse((ns3_dir / "network_attribute.txt").exists())
            self.assertNotEqual((ns3_dir / "transport_channel.csv").read_text(encoding="utf-8"), "old\n")
            self.assertNotEqual((netisim_dir / "rdma_operate.txt").read_text(encoding="utf-8"), "old\n")


if __name__ == "__main__":
    unittest.main()
