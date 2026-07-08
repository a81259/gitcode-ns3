#!/usr/bin/env python3
"""Regression tests for Pod1D topology generation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from generate_topology import TopologyParams, write_case


class Pod1DCompressedRouteTest(unittest.TestCase):
    def test_access_layer_gives_hosts_one_port_and_zero_delay_links(self) -> None:
        params = TopologyParams(
            pod_num=1,
            node_per_pod=1,
            npu_per_node=4,
            l1_switch_per_pod=4,
            l2_plane_num=4,
            l2_switch_per_plane=1,
            l1_to_each_l2_ports=2,
            host_to_access_ports=1,
            access_to_each_l1_ports=1,
        )

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            write_case(output_dir, params=params, route_mode="none")
            node_rows = (output_dir / "node.csv").read_text(encoding="utf-8").splitlines()
            topology_rows = (output_dir / "topology.csv").read_text(encoding="utf-8").splitlines()

        self.assertEqual(
            node_rows,
            [
                "nodeId,nodeType,portNum,forwardDelay",
                "0..3,DEVICE,1,1ns",
                "4..7,SWITCH,5,1ns",
                "8..11,SWITCH,6,225ns",
                "12..15,SWITCH,2,225ns",
            ],
        )
        self.assertIn("0,0,4,0,6000Gbps,0ns", topology_rows)
        self.assertIn("4,1,8,0,224Gbps,10ns", topology_rows)
        self.assertIn("8,4,12,0,448Gbps,150ns", topology_rows)
        self.assertIn("8,5,12,1,448Gbps,150ns", topology_rows)
        self.assertNotIn("8,5,13,0,448Gbps,150ns", topology_rows)

    def test_local_host_routes_through_single_access_port(self) -> None:
        params = TopologyParams(
            pod_num=1,
            node_per_pod=1,
            npu_per_node=4,
            l1_switch_per_pod=4,
            l2_plane_num=4,
            l2_switch_per_plane=1,
            l1_to_each_l2_ports=1,
            host_to_access_ports=1,
            access_to_each_l1_ports=1,
        )

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            write_case(output_dir, params=params, route_mode="compressed")
            rows = (output_dir / "routing_table.csv").read_text(encoding="utf-8").splitlines()

        local_rows = [row for row in rows if row.startswith("0,1..3,")]
        self.assertEqual(
            local_rows,
            [
                "0,1..3,0,0,4",
            ],
        )

        access_rows = [row for row in rows if row.startswith("4,")]
        self.assertIn("4,0,0,0,1", access_rows)
        self.assertIn("4,1..3,0,1 2 3 4,3 3 3 3", access_rows)

    def test_interpod_routes_aggregate_l1_and_l2_choices_for_host_port_zero(self) -> None:
        params = TopologyParams(
            pod_num=2,
            node_per_pod=1,
            npu_per_node=2,
            l1_switch_per_pod=2,
            l2_plane_num=2,
            l2_switch_per_plane=1,
            l1_to_each_l2_ports=1,
            host_to_access_ports=1,
            access_to_each_l1_ports=1,
        )

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            write_case(output_dir, params=params, route_mode="compressed")
            rows = (output_dir / "routing_table.csv").read_text(encoding="utf-8").splitlines()

        self.assertIn("0,2..3,0,0,6", rows)
        self.assertIn("4,2..3,0,1 2,5 5", rows)

    def test_identical_interpod_host_ranges_are_compacted(self) -> None:
        params = TopologyParams(
            pod_num=4,
            node_per_pod=1,
            npu_per_node=2,
            l1_switch_per_pod=2,
            l2_plane_num=2,
            l2_switch_per_plane=1,
            l1_to_each_l2_ports=1,
            host_to_access_ports=1,
            access_to_each_l1_ports=1,
        )

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            write_case(output_dir, params=params, route_mode="compressed")
            rows = (output_dir / "routing_table.csv").read_text(encoding="utf-8").splitlines()

        host_zero_rows = [row for row in rows if row.startswith("0,")]
        self.assertIn("0,1,0,0,4", host_zero_rows)
        self.assertIn("0,2..7,0,0,6", host_zero_rows)
        self.assertNotIn("0,2..3,0,0,6", host_zero_rows)
        self.assertNotIn("0,4..5,0,0,6", host_zero_rows)
        self.assertNotIn("0,6..7,0,0,6", host_zero_rows)


if __name__ == "__main__":
    unittest.main()
