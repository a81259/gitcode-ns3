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
    sw1650_per_node=2,
    sw1825_per_node=4,
    l1_switch_per_pod=4,
    l2_plane_num=4,
    l2_switch_per_plane=2,
    l1_to_each_l2_ports=2,
)


class UnifiedPod1dTest(unittest.TestCase):
    def test_unified_generator_reuses_original_platform_builders(self):
        source = Path(casegen.__file__).read_text(encoding="utf-8")

        self.assertIn("import netisim_graph", source)
        self.assertIn("import net_sim_builder as netsim", source)
        self.assertIn("netisim_graph.NetiSimGraph()", source)
        self.assertIn("netsim.NetworkSimulationGraph()", source)
        self.assertNotIn("xml.etree.ElementTree", source)
        self.assertNotIn("def assign_ports", source)
        self.assertNotIn("def write_netisim_router_xml", source)
        self.assertNotIn("def write_ns3_node_csv", source)

    def test_default_params_match_original_pod1d_constants(self):
        params = casegen.TopologyParams()
        layout = casegen.build_id_layout(params)

        self.assertEqual(params.pod_num, 19)
        self.assertEqual(params.node_per_pod, 9)
        self.assertEqual(params.npu_per_node, 8)
        self.assertEqual(params.sw1650_per_node, 2)
        self.assertEqual(params.sw1825_per_node, 4)
        self.assertEqual(params.l1_switch_per_pod, 24)
        self.assertEqual(params.l2_plane_num, 24)
        self.assertEqual(params.l2_switch_per_plane, 4)
        self.assertEqual(params.l1_to_each_l2_ports, 9)
        self.assertEqual(layout.host_num, 1368)
        self.assertEqual(layout.sw1825_base_id, 1368)
        self.assertEqual(layout.sw1650_base_id, 2052)
        self.assertEqual(layout.l1_base_id, 2394)
        self.assertEqual(layout.l2_base_id, 2850)

    def test_builds_same_pod1d_topology_on_both_existing_graph_types(self):
        ns3_graph, ns3_ids = casegen.build_ns3_graph(SMALL_PARAMS)
        netisim_graph, netisim_ids = casegen.build_netisim_graph(SMALL_PARAMS)

        self.assertEqual(type(ns3_graph).__name__, "NetworkSimulationGraph")
        self.assertEqual(type(netisim_graph).__name__, "NetiSimGraph")
        self.assertEqual(ns3_ids.host_ids, list(range(16)))
        self.assertEqual(ns3_ids.switch_groups["sw1825"], list(range(16, 32)))
        self.assertEqual(ns3_ids.switch_groups["sw1650"], list(range(32, 40)))
        self.assertEqual(ns3_ids.switch_groups["l1"], list(range(40, 48)))
        self.assertEqual(ns3_ids.switch_groups["l2"], list(range(48, 56)))
        self.assertEqual(ns3_ids, netisim_ids)
        self.assertEqual(sorted(ns3_graph.edges()), sorted(netisim_graph.edges()))
        self.assertEqual(sum(data["edge_count"] for _, _, data in ns3_graph.edges(data=True)), 128)

        link_counts = {(u, v): data["edge_count"] for u, v, data in ns3_graph.edges(data=True)}
        self.assertEqual(link_counts[(0, 32)], 1)
        self.assertEqual(link_counts[(0, 16)], 1)
        self.assertEqual(link_counts[(0, 40)], 1)
        self.assertEqual(link_counts[(0, 43)], 1)
        self.assertEqual(link_counts[(40, 48)], 2)
        self.assertEqual(link_counts[(44, 48)], 2)

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
            self.assertFalse((ns3_dir / "transport_channel.csv").exists())
            self.assertFalse((ns3_dir / "network_attribute.txt").exists())

            with (ns3_dir / "node.csv").open(newline="", encoding="utf-8") as f:
                node_rows = list(csv.DictReader(f))
            self.assertEqual(node_rows[0]["nodeId"], "0..15")
            self.assertEqual(node_rows[0]["nodeType"], "DEVICE")
            self.assertEqual(node_rows[0]["portNum"], "6")

            with (ns3_dir / "topology.csv").open(newline="", encoding="utf-8") as f:
                topology_rows = list(csv.DictReader(f))
            self.assertEqual(len(topology_rows), 128)
            self.assertIn(
                {
                    "nodeId1": "40",
                    "portId1": "8",
                    "nodeId2": "48",
                    "portId2": "0",
                    "bandwidth": "224Gbps",
                    "delay": "20ns",
                },
                topology_rows,
            )

            xml_path = netisim_dir / "dcn2.0_config.xml"
            self.assertTrue(xml_path.exists())
            self.assertFalse((netisim_dir / "rdma_operate.txt").exists())
            root = ET.parse(xml_path).getroot()
            node_groups = root.findall("./dcn_network/node/grp")
            self.assertEqual(
                [group.attrib["node_id"] for group in node_groups],
                ["0..15", "16..31", "32..39", "40..47", "48..55"],
            )

            links = root.findall("./dcn_network/topology/grp")
            self.assertEqual(len(links), 129)
            self.assertEqual(links[0].attrib["dst_node"], "-1")
            self.assertEqual(links[1].attrib["src_node"], "0")
            self.assertEqual(links[1].attrib["src_port"], "1")

            partition_chips = root.findall(
                "./dcn_network/mpi_multi_processing/process_partition/overlap_partition/chip"
            )
            self.assertEqual(
                [chip.attrib["dev_id"] for chip in partition_chips],
                ["0..15", "16..31", "32..39", "40..47", "48..55"],
            )
            template_ids = [
                template.attrib["id"]
                for template in root.findall("./dcn_network/xml_template/template")
            ]
            self.assertEqual(template_ids, ["0", "1", "2", "3"])

            router = ET.parse(netisim_dir / "router.xml").getroot()
            self.assertEqual(router.tag, "router")
            self.assertGreater(len(router.findall("grp")), 0)

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
            self.assertFalse((ns3_dir / "transport_channel.csv").exists())
            self.assertFalse((netisim_dir / "rdma_operate.txt").exists())


if __name__ == "__main__":
    unittest.main()
