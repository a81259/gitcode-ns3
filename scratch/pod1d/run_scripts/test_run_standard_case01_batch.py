#!/usr/bin/env python3
"""Tests for the standard case01 batch runner."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import run_standard_case01_batch as runner


class JobDefinitionTest(unittest.TestCase):
    def test_jobs_cover_only_requested_standard_cases_in_order(self) -> None:
        expected_tests = (
            "test01_tp_all_gather",
            "test02_cp_all_to_all",
            "test03_tp_reduce_scatter",
            "test04_tp_reduce_scatter",
            "test05_pp_send_recv",
            "test06_epxetp_all_to_all",
            "test07_etp_all_reduce",
        )

        jobs = runner.build_jobs()

        self.assertEqual(tuple(job.test for job in jobs), expected_tests)
        self.assertTrue(all(job.case == "case01_标准topo" for job in jobs))


class PreparationTest(unittest.TestCase):
    def test_prepare_case_preserves_traffic_bytes_and_migrates_routing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            traffic = case_dir / "traffic.csv"
            traffic_bytes = (
                b"taskId,sourceNode,destNode,dataSize(Byte),opType,priority,"
                b"delay,phaseId,dependOnPhases\n"
                b"0,0,1,123,URMA_WRITE,7,0ns,0,\n"
            )
            traffic.write_bytes(traffic_bytes)
            attributes = case_dir / "network_attribute.txt"
            attributes.write_text(
                "\n".join(
                    [
                        'default ns3::UbApp::UsePacketSpray "true"',
                        'default ns3::UbApp::UseShortestPaths "true"',
                        'default ns3::UbTransportChannel::UsePacketSpray "true"',
                        'default ns3::UbTransportChannel::UseShortestPaths "true"',
                        'default ns3::UbLdstApi::UsePacketSpray "true"',
                        'default ns3::UbLdstApi::UseShortestPaths "true"',
                        'default ns3::UbRoutingProcess::PacketSprayMode "ROUND_ROBIN"',
                        'default ns3::UbJetty::UbInflightMax "10000"',
                        'default ns3::UbTransportChannel::InitialRTO "+25600ns"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            summary = runner.prepare_case(case_dir)

            self.assertEqual(traffic.read_bytes(), traffic_bytes)
            self.assertEqual(summary["traffic_sha256_before"], summary["traffic_sha256_after"])
            text = attributes.read_text(encoding="utf-8")
            self.assertEqual(text.count('RoutingType "PER_PACKET_SHORTEST_PATHS"'), 3)
            self.assertEqual(text.count('MultipathSelector "ROUND_ROBIN"'), 1)
            self.assertNotIn("UsePacketSpray", text)
            self.assertNotIn("UseShortestPaths", text)
            self.assertNotIn("UbInflightMax", text)
            self.assertNotIn("InitialRTO", text)


class LaunchCommandTest(unittest.TestCase):
    def test_command_uses_10ns_dependency_delay_without_mtp(self) -> None:
        job = runner.build_jobs()[0]

        command = runner.build_command(job)

        self.assertIn("--dependency-visibility-delay=10ns", command[-1])
        self.assertNotIn("--mtp-threads", command[-1])


class ResultOrderingTest(unittest.TestCase):
    def test_results_are_written_in_requested_test_order(self) -> None:
        rows = [
            {"test": "test07_etp_all_reduce"},
            {"test": "test02_cp_all_to_all"},
            {"test": "test01_tp_all_gather"},
        ]

        ordered = runner.order_results(rows)

        self.assertEqual(
            [row["test"] for row in ordered],
            [
                "test01_tp_all_gather",
                "test02_cp_all_to_all",
                "test07_etp_all_reduce",
            ],
        )


if __name__ == "__main__":
    unittest.main()
