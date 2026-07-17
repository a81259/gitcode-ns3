#!/usr/bin/env python3
"""Tests for the test09/test10 scale80 experiment runner."""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import run_test09_10_scale80_all_cases as runner


class TrafficScalingTest(unittest.TestCase):
    def test_scale_traffic_divides_each_positive_task_size_by_80(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "traffic.original.csv"
            destination = root / "traffic.csv"
            source.write_text(
                "\n".join(
                    [
                        "taskId,sourceNode,destNode,dataSize(Byte),opType,priority,delay,phaseId,dependOnPhases",
                        "0,0,1,160,URMA_WRITE,7,0ns,0,",
                        "1,1,0,79,URMA_WRITE,7,0ns,0,",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            summary = runner.scale_traffic(source, destination, scale=80)

            with destination.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["dataSize(Byte)"] for row in rows], ["2", "1"])
            self.assertEqual(summary.rows, 2)
            self.assertEqual(summary.original_bytes, 239)
            self.assertEqual(summary.scaled_bytes, 3)


class RoutingAttributeRewriteTest(unittest.TestCase):
    def test_rewrite_replaces_legacy_packet_spray_fields_with_canonical_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "network_attribute.txt"
            path.write_text(
                "\n".join(
                    [
                        'default ns3::UbApp::EnableMultiPath "true"',
                        'default ns3::UbApp::UsePacketSpray "true"',
                        'default ns3::UbApp::UseShortestPaths "true"',
                        'default ns3::UbTransportChannel::UsePacketSpray "true"',
                        'default ns3::UbTransportChannel::UseShortestPaths "true"',
                        'default ns3::UbLdstApi::UsePacketSpray "true"',
                        'default ns3::UbLdstApi::UseShortestPaths "true"',
                        'default ns3::UbRoutingProcess::PacketSprayMode "ROUND_ROBIN"',
                        'default ns3::UbRoutingProcess::BwWeightedPacketSpray "false"',
                        'default ns3::UbRoutingProcess::BwWeightedPacketSprayScope "all"',
                        'default ns3::UbJetty::UbInflightMax "10000"',
                        'default ns3::UbTransportChannel::InitialRTO "+25600ns"',
                        'global UB_TASK_TRACE_ENABLE "true"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            runner.rewrite_routing_attributes(path)

            text = path.read_text(encoding="utf-8")
            self.assertNotIn("UsePacketSpray", text)
            self.assertNotIn("UseShortestPaths", text)
            self.assertNotIn("PacketSprayMode", text)
            self.assertNotIn("BwWeightedPacketSpray", text)
            for owner in ("UbApp", "UbTransportChannel", "UbLdstApi"):
                self.assertIn(
                    f'default ns3::{owner}::RoutingType "PER_PACKET_SHORTEST_PATHS"',
                    text,
                )
            self.assertIn(
                'default ns3::UbRoutingProcess::MultipathSelector "ROUND_ROBIN"',
                text,
            )
            self.assertNotIn("ns3::UbJetty::UbInflightMax", text)
            self.assertIn(
                'default ns3::UbJetty::UbJettyInflightMax "10000"',
                text,
            )
            self.assertNotIn("ns3::UbTransportChannel::InitialRTO", text)
            self.assertIn(
                'default ns3::UbTransportChannel::BaseRTO "+25600ns"',
                text,
            )
            self.assertIn('global UB_TASK_TRACE_ENABLE "true"', text)


class JobOrderingTest(unittest.TestCase):
    def test_each_test_queue_orders_standard_then_four_faults(self) -> None:
        queues = runner.build_queues(("test09_dp_all_gather", "test10_dp_reduce_scatter"))

        expected = list(runner.CASES)
        self.assertEqual([job.case for job in queues["test09_dp_all_gather"]], expected)
        self.assertEqual([job.case for job in queues["test10_dp_reduce_scatter"]], expected)


class LaunchCommandTest(unittest.TestCase):
    def test_command_sets_dependency_visibility_delay_without_mtp(self) -> None:
        job = runner.Job("test09_dp_all_gather", runner.CASES[0])

        command = runner.build_command(job)

        self.assertIn("--dependency-visibility-delay=10ns", command[-1])
        self.assertNotIn("--mtp-threads", command[-1])


class FctSummaryTest(unittest.TestCase):
    def test_summary_reports_completed_count_and_fct_distribution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "task_statistics.csv"
            path.write_text(
                "\n".join(
                    [
                        "taskId,taskStartTime(us),taskCompletesTime(us)",
                        "0,1,3",
                        "1,2,6",
                        "2,,",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            summary, fcts = runner.summarize_fct(path)

            self.assertEqual(summary.completed_tasks, 2)
            self.assertEqual(fcts, [2.0, 4.0])
            self.assertEqual(summary.mean_us, 3.0)
            self.assertEqual(summary.p95_us, 3.9)
            self.assertEqual(summary.max_us, 4.0)


if __name__ == "__main__":
    unittest.main()
