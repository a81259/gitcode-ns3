#!/usr/bin/env python3
"""Tests for the serial test90 independent-traffic experiment runner."""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import run_test90_independent_scale80 as runner


class IndependentTrafficFilterTest(unittest.TestCase):
    def test_filter_keeps_only_blank_dependency_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.csv"
            destination = Path(tmp) / "filtered.csv"
            source.write_text(
                "taskId,sourceNode,destNode,dataSize(Byte),opType,priority,delay,phaseId,dependOnPhases\n"
                "0,0,1,80,URMA_WRITE,7,10ns,0,\n"
                "1,1,0,160,URMA_WRITE,7,10ns,1,  \n"
                "2,2,3,240,URMA_WRITE,7,10ns,2,0\n",
                encoding="utf-8",
            )

            summary = runner.filter_independent_traffic(source, destination)

            with destination.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["taskId"] for row in rows], ["0", "1"])
            self.assertEqual(summary.total_tasks, 3)
            self.assertEqual(summary.kept_tasks, 2)
            self.assertEqual(summary.removed_tasks, 1)
            self.assertEqual(summary.kept_bytes, 240)


class CaseOrderTest(unittest.TestCase):
    def test_formal_cases_are_standard_then_four_faults(self) -> None:
        self.assertEqual(
            runner.CASES,
            (
                "case01_标准topo",
                "case02_故障1topo_单链路lane",
                "case03_故障2topo_单链路laport",
                "case04_故障3topo_分布式多链路port",
                "case05_故障4topo_分集中式多链路port",
            ),
        )


class LaunchCommandTest(unittest.TestCase):
    def test_command_uses_10ns_visibility_delay_without_mtp(self) -> None:
        command = runner.build_command(runner.CASES[0])

        self.assertIn("--dependency-visibility-delay=10ns", command[-1])
        self.assertNotIn("--mtp-threads", command[-1])
        self.assertIn("test90_dp_reduce_scatter_independent_scale80", command[-1])


class Scale80SourceTest(unittest.TestCase):
    def test_traffic_source_comes_from_immutable_scale80_snapshot(self) -> None:
        source = runner.scale80_traffic_source(runner.CASES[0])

        self.assertIn("test08_09_scale80_all_cases_v2", source.as_posix())
        self.assertEqual(source.name, "traffic.csv")
        self.assertIn("test09_dp_reduce_scatter", source.as_posix())


if __name__ == "__main__":
    unittest.main()
