#!/usr/bin/env python3
"""Regression tests for Pod1D fault-case generation."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import build_fault_cases
from build_fault_cases import (
    LinkFaultTarget,
    apply_fault_link_down_preserving_ports,
    configure_packet_spray,
    host_l1_target_for_case,
    parse_range,
)


def range_contains(value: str, target: int) -> bool:
    start, end = parse_range(value)
    return start <= target <= end


class StandardPacketSprayConfigurationTest(unittest.TestCase):
    def test_case_generator_always_sets_standard_packet_spray(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            attribute_path = case_dir / "network_attribute.txt"
            attribute_path.write_text(
                "\n".join(
                    [
                        'default ns3::UbRoutingProcess::BwWeightedPacketSpray "true"',
                        'default ns3::UbRoutingProcess::BwWeightedPacketSprayScope "l1-l2"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            configure_packet_spray(case_dir)

            self.assertEqual(
                attribute_path.read_text(encoding="utf-8"),
                "\n".join(
                    [
                        'default ns3::UbRoutingProcess::BwWeightedPacketSpray "false"',
                        'default ns3::UbRoutingProcess::BwWeightedPacketSprayScope "all"',
                    ]
                )
                + "\n",
            )


class AccessL1LinkDownRouteTest(unittest.TestCase):
    def test_test05_uses_pp_bottleneck_access_l1_target(self) -> None:
        self.assertEqual(
            host_l1_target_for_case(Path("/tmp/test05_pp_send_recv")),
            LinkFaultTarget(
                node1=1492,
                port1=1,
                node2=2760,
                port2=52,
                half_bandwidth="112Gbps",
            ),
        )

    def test_access_l1_link_down_keeps_host_port_and_reroutes_failed_uplink(self) -> None:
        target = LinkFaultTarget(
            node1=2,
            port1=1,
            node2=4,
            port2=0,
            half_bandwidth="2000Gbps",
        )
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            (case_dir / "topology.csv").write_text(
                "\n".join(
                    [
                        "nodeId1,portId1,nodeId2,portId2,bandwidth,delay",
                        "0,0,2,0,4000Gbps,0ns",
                        "1,0,3,0,4000Gbps,0ns",
                        "2,1,4,0,4000Gbps,0ns",
                        "2,2,5,0,4000Gbps,0ns",
                        "3,1,4,1,4000Gbps,0ns",
                        "3,2,5,1,4000Gbps,0ns",
                        "4,2,6,0,4000Gbps,0ns",
                        "5,2,6,1,4000Gbps,0ns",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (case_dir / "routing_table.csv").write_text(
                "\n".join(
                    [
                        "nodeId,dstNodeId,dstPortId,outPorts,metrics",
                        "0,1,0,0,4",
                        "2,0,0,0,1",
                        "2,1,0,1 2,3 3",
                        "4,0,0,0,2",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            apply_fault_link_down_preserving_ports(case_dir, target)

            with (case_dir / "routing_table.csv").open("r", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))

        host_source_route = [
            row
            for row in rows
            if row["nodeId"] == "0" and row["dstNodeId"] == "1" and row["dstPortId"] == "0"
        ]
        self.assertEqual(
            host_source_route,
            [
                {
                    "nodeId": "0",
                    "dstNodeId": "1",
                    "dstPortId": "0",
                    "outPorts": "0",
                    "metrics": "4",
                }
            ],
        )

        access_route = [
            row
            for row in rows
            if row["nodeId"] == "2" and row["dstNodeId"] == "1" and row["dstPortId"] == "0"
        ]
        self.assertEqual(
            access_route,
            [
                {
                    "nodeId": "2",
                    "dstNodeId": "1",
                    "dstPortId": "0",
                    "outPorts": "2",
                    "metrics": "3",
                }
            ],
        )

        direct_failed_l1_route = [
            row
            for row in rows
            if row["nodeId"] == "4"
            and range_contains(row["dstNodeId"], 0)
            and row["dstPortId"] == "0"
            and row["outPorts"] == "0"
        ]
        self.assertEqual(direct_failed_l1_route, [])

        backup_route = [
            row
            for row in rows
            if row["nodeId"] == "4" and row["dstNodeId"] == "0" and row["dstPortId"] == "0"
        ]
        self.assertEqual(
            backup_route,
            [
                {
                    "nodeId": "4",
                    "dstNodeId": "0",
                    "dstPortId": "0",
                    "outPorts": "2",
                    "metrics": "3",
                }
            ],
        )

    def test_access_l1_link_down_removes_dead_l2_descent_without_shared_l2(self) -> None:
        target = LinkFaultTarget(
            node1=2,
            port1=1,
            node2=4,
            port2=0,
            half_bandwidth="2000Gbps",
        )
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            (case_dir / "topology.csv").write_text(
                "\n".join(
                    [
                        "nodeId1,portId1,nodeId2,portId2,bandwidth,delay",
                        "0,0,2,0,4000Gbps,0ns",
                        "1,0,3,0,4000Gbps,0ns",
                        "2,1,4,0,4000Gbps,0ns",
                        "2,2,5,0,4000Gbps,0ns",
                        "3,1,4,1,4000Gbps,0ns",
                        "3,2,5,1,4000Gbps,0ns",
                        "4,2,6,0,4000Gbps,0ns",
                        "5,2,7,0,4000Gbps,0ns",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (case_dir / "routing_table.csv").write_text(
                "\n".join(
                    [
                        "nodeId,dstNodeId,dstPortId,outPorts,metrics",
                        "2,0,0,0,1",
                        "2,1,0,1 2,3 3",
                        "4,0,0,0,2",
                        "4,1,0,1,2",
                        "6,0..1,0,0,3",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            apply_fault_link_down_preserving_ports(case_dir, target)

            with (case_dir / "routing_table.csv").open("r", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))

        dead_l2_descent = [
            row
            for row in rows
            if row["nodeId"] == "6"
            and range_contains(row["dstNodeId"], 0)
            and row["dstPortId"] == "0"
            and row["outPorts"] == "0"
        ]
        self.assertEqual(dead_l2_descent, [])

        surviving_l2_descent = [
            row
            for row in rows
            if row["nodeId"] == "6" and row["dstNodeId"] == "1" and row["dstPortId"] == "0"
        ]
        self.assertEqual(
            surviving_l2_descent,
            [
                {
                    "nodeId": "6",
                    "dstNodeId": "1",
                    "dstPortId": "0",
                    "outPorts": "0",
                    "metrics": "3",
                }
            ],
        )

    def test_access_l1_link_down_adds_failed_l1_backup_via_peer_access(self) -> None:
        target = LinkFaultTarget(
            node1=2,
            port1=1,
            node2=4,
            port2=0,
            half_bandwidth="2000Gbps",
        )
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            (case_dir / "topology.csv").write_text(
                "\n".join(
                    [
                        "nodeId1,portId1,nodeId2,portId2,bandwidth,delay",
                        "0,0,2,0,4000Gbps,0ns",
                        "2,1,4,0,4000Gbps,0ns",
                        "2,2,5,0,4000Gbps,0ns",
                        "3,1,4,1,4000Gbps,0ns",
                        "3,2,5,1,4000Gbps,0ns",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (case_dir / "routing_table.csv").write_text(
                "\n".join(
                    [
                        "nodeId,dstNodeId,dstPortId,outPorts,metrics",
                        "2,0,0,0,1",
                        "3,0,0,2,3",
                        "4,0,0,0,2",
                        "5,0,0,0,2",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            apply_fault_link_down_preserving_ports(case_dir, target)

            with (case_dir / "routing_table.csv").open("r", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))

        backup_route = [
            row
            for row in rows
            if row["nodeId"] == "4" and row["dstNodeId"] == "0" and row["dstPortId"] == "0"
        ]
        self.assertEqual(
            backup_route,
            [
                {
                    "nodeId": "4",
                    "dstNodeId": "0",
                    "dstPortId": "0",
                    "outPorts": "1",
                    "metrics": "4",
                }
            ],
        )


class MultiLinkFaultTargetTest(unittest.TestCase):
    def test_case06_targets_first_l1_in_pods_1_through_18(self) -> None:
        expected = tuple(
            LinkFaultTarget(
                node1=2736 + pod_index * 24,
                port1=72,
                node2=3192,
                port2=pod_index * 9,
                half_bandwidth="224Gbps",
            )
            for pod_index in range(18)
        )

        self.assertEqual(
            getattr(build_fault_cases, "PODS_1_TO_18_FIRST_L1_FIRST_L2_TARGETS", None),
            expected,
        )

    def test_case07_targets_pod1_first_l1_with_5_5_4_4_links(self) -> None:
        expected = tuple(
            LinkFaultTarget(
                node1=2736,
                port1=72 + l2_index * 9 + link_index,
                node2=3192 + l2_index,
                port2=link_index,
                half_bandwidth="224Gbps",
            )
            for l2_index, link_count in enumerate((5, 5, 4, 4))
            for link_index in range(link_count)
        )

        self.assertEqual(
            getattr(build_fault_cases, "POD1_FIRST_L1_PLANE1_L2_TARGETS", None),
            expected,
        )

    def test_multiple_link_faults_update_topology_and_routes(self) -> None:
        apply_faults = getattr(
            build_fault_cases,
            "apply_fault_links_down_preserving_ports",
            None,
        )
        self.assertIsNotNone(apply_faults)

        targets = (
            LinkFaultTarget(10, 0, 20, 0, "224Gbps"),
            LinkFaultTarget(10, 1, 21, 0, "224Gbps"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            (case_dir / "topology.csv").write_text(
                "\n".join(
                    [
                        "nodeId1,portId1,nodeId2,portId2,bandwidth,delay",
                        "10,0,20,0,448Gbps,150ns",
                        "10,1,21,0,448Gbps,150ns",
                        "10,2,21,1,448Gbps,150ns",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (case_dir / "routing_table.csv").write_text(
                "\n".join(
                    [
                        "nodeId,dstNodeId,dstPortId,outPorts,metrics",
                        "10,30,0,0 1 2,4 4 4",
                        "20,30,0,0 5,3 3",
                        "21,30,0,0 1 5,3 3 3",
                        "30,10,0,7,2",
                        "30,10,1,8,2",
                        "30,21,1,9,2",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            apply_faults(case_dir, targets)

            with (case_dir / "topology.csv").open("r", encoding="utf-8", newline="") as f:
                topology_rows = list(csv.DictReader(f))
            with (case_dir / "routing_table.csv").open("r", encoding="utf-8", newline="") as f:
                route_rows = list(csv.DictReader(f))

        self.assertEqual(
            topology_rows,
            [
                {
                    "nodeId1": "10",
                    "portId1": "2",
                    "nodeId2": "21",
                    "portId2": "1",
                    "bandwidth": "448Gbps",
                    "delay": "150ns",
                }
            ],
        )
        source_routes = {
            row["nodeId"]: row["outPorts"]
            for row in route_rows
            if row["dstNodeId"] == "30"
        }
        self.assertEqual(source_routes, {"10": "2", "20": "5", "21": "1 5"})
        self.assertFalse(
            any(
                row["dstNodeId"] == "10" and row["dstPortId"] in {"0", "1"}
                for row in route_rows
            )
        )
        self.assertTrue(
            any(
                row["dstNodeId"] == "21" and row["dstPortId"] == "1"
                for row in route_rows
            )
        )


if __name__ == "__main__":
    unittest.main()
