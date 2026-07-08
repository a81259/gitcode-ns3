#!/usr/bin/env python3
"""Regression tests for Pod1D fault-case generation."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from build_fault_cases import (
    LinkFaultTarget,
    apply_fault_link_down_preserving_ports,
    host_l1_target_for_case,
    parse_range,
)


def range_contains(value: str, target: int) -> bool:
    start, end = parse_range(value)
    return start <= target <= end


class AccessL1LinkDownRouteTest(unittest.TestCase):
    def test_test06_uses_pp_bottleneck_access_l1_target(self) -> None:
        self.assertEqual(
            host_l1_target_for_case(Path("/tmp/test06_pp_send_recv")),
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


if __name__ == "__main__":
    unittest.main()
