#!/usr/bin/env python3
"""Regression tests for Pod1D no-access topology generation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from generate_topology import TopologyParams, write_case


class Pod1DCompressedRouteTest(unittest.TestCase):
    def test_local_host_routes_preserve_destination_port_mapping(self) -> None:
        params = TopologyParams(
            pod_num=1,
            node_per_pod=1,
            npu_per_node=4,
            l1_switch_per_pod=4,
            l2_plane_num=4,
            l2_switch_per_plane=1,
            l1_to_each_l2_ports=1,
            host_to_each_l1_ports=1,
        )

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            write_case(output_dir, params=params, route_mode="compressed")
            rows = (output_dir / "routing_table.csv").read_text(encoding="utf-8").splitlines()

        local_rows = [row for row in rows if row.startswith("0,1..3,")]
        self.assertEqual(
            local_rows,
            [
                "0,1..3,0,0,2",
                "0,1..3,1,1,2",
                "0,1..3,2,2,2",
                "0,1..3,3,3,2",
            ],
        )


if __name__ == "__main__":
    unittest.main()
