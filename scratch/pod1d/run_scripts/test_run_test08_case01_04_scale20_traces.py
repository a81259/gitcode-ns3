from __future__ import annotations

import csv
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from run_test08_case01_04_scale20_traces import (  # noqa: E402
    ANALYSIS_TRACE_VALUES,
    build_ns3_command,
    enable_analysis_traces,
    scale_traffic,
    stage_case,
    summarize_task_statistics,
    trace_inventory,
)


def write_traffic(path: Path, sizes: list[int]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("taskId", "dataSize(Byte)", "phaseId"),
            lineterminator="\n",
        )
        writer.writeheader()
        for task_id, size in enumerate(sizes):
            writer.writerow(
                {
                    "taskId": task_id,
                    "dataSize(Byte)": size,
                    "phaseId": task_id,
                }
            )


def read_sizes(path: Path) -> list[int]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return [int(row["dataSize(Byte)"]) for row in csv.DictReader(stream)]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ScaleTrafficTests(unittest.TestCase):
    def test_scales_positive_sizes_and_preserves_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "traffic.original.csv"
            destination = root / "traffic.csv"
            write_traffic(source, [100, 19, 1, 0])

            summary = scale_traffic(source, destination, scale=20)

            self.assertEqual(read_sizes(destination), [5, 1, 1, 0])
            self.assertEqual(summary.rows, 4)
            self.assertEqual(summary.original_bytes, 120)
            self.assertEqual(summary.scaled_bytes, 7)
            self.assertAlmostEqual(summary.ratio, 7 / 120)


class TraceConfigurationTests(unittest.TestCase):
    def test_enables_analysis_trace_set_without_changing_other_attributes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "network_attribute.txt"
            path.write_text(
                "default ns3::Example::KeepMe \"17\"\n"
                "global UB_TRACE_ENABLE \"true\"\n"
                "global UB_TASK_TRACE_ENABLE \"true\"\n"
                "global UB_PACKET_TRACE_ENABLE \"false\"\n"
                "global UB_PORT_TRACE_ENABLE \"false\"\n"
                "global UB_QUEUE_TRACE_ENABLE \"false\"\n"
                "global UB_FLOW_CONTROL_TRACE_ENABLE \"false\"\n"
                "global UB_CONGESTION_CONTROL_TRACE_ENABLE \"true\"\n"
                "global UB_RECORD_PKT_TRACE \"false\"\n"
                "global UB_PARSE_TRACE_ENABLE \"true\"\n",
                encoding="utf-8",
            )

            enable_analysis_traces(path)

            text = path.read_text(encoding="utf-8")
            self.assertIn('default ns3::Example::KeepMe "17"', text)
            for name, value in ANALYSIS_TRACE_VALUES.items():
                self.assertEqual(text.count(f'global {name} "{value}"'), 1)


class StageCaseTests(unittest.TestCase):
    def make_source_case(self, root: Path) -> Path:
        source = root / "source"
        source.mkdir()
        (source / "network_attribute.txt").write_text(
            "global UB_TRACE_ENABLE \"true\"\n"
            "global UB_TASK_TRACE_ENABLE \"true\"\n"
            "global UB_PACKET_TRACE_ENABLE \"false\"\n"
            "global UB_PORT_TRACE_ENABLE \"false\"\n"
            "global UB_QUEUE_TRACE_ENABLE \"false\"\n"
            "global UB_FLOW_CONTROL_TRACE_ENABLE \"false\"\n"
            "global UB_CONGESTION_CONTROL_TRACE_ENABLE \"false\"\n"
            "global UB_RECORD_PKT_TRACE \"false\"\n"
            "global UB_PARSE_TRACE_ENABLE \"true\"\n",
            encoding="utf-8",
        )
        for name, content in (
            ("node.csv", "node\n"),
            ("topology.csv", "topology\n"),
            ("routing_table.csv", "routing\n"),
        ):
            (source / name).write_text(content, encoding="utf-8")
        write_traffic(source / "traffic.original.csv", [100, 41])
        return source

    def test_stages_isolated_case_from_original_traffic(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.make_source_case(root)
            destination = root / "destination"
            source_hashes = {
                path.name: digest(path) for path in source.iterdir() if path.is_file()
            }

            staged = stage_case(source, destination, scale=20)

            self.assertEqual(read_sizes(destination / "traffic.csv"), [5, 2])
            self.assertEqual(staged.traffic.rows, 2)
            for name in ("node.csv", "topology.csv", "routing_table.csv"):
                self.assertEqual(digest(source / name), digest(destination / name))
            self.assertEqual(
                source_hashes,
                {path.name: digest(path) for path in source.iterdir() if path.is_file()},
            )

    def test_rejects_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.make_source_case(root)
            destination = root / "destination"
            destination.mkdir()

            with self.assertRaises(FileExistsError):
                stage_case(source, destination, scale=20)


class ArtifactSummaryTests(unittest.TestCase):
    def test_builds_ns3_command_with_repository_relative_case_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            case = repo / "scratch" / "pod1d" / "batch" / "case01"
            case.mkdir(parents=True)

            command = build_ns3_command(repo, case)

            self.assertEqual(
                command,
                [
                    "./ns3",
                    "run",
                    "--no-build",
                    "scratch/ub-quick-example "
                    "--case-path=scratch/pod1d/batch/case01",
                ],
            )

    def test_rejects_case_path_outside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as repo_temp:
            with tempfile.TemporaryDirectory() as case_temp:
                with self.assertRaises(ValueError):
                    build_ns3_command(Path(repo_temp), Path(case_temp))

    def test_summarizes_task_completion_times(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "task_statistics.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=("taskId", "taskCompletesTime(us)"),
                    lineterminator="\n",
                )
                writer.writeheader()
                writer.writerow({"taskId": 0, "taskCompletesTime(us)": "10.0"})
                writer.writerow({"taskId": 1, "taskCompletesTime(us)": "14.0"})

            summary = summarize_task_statistics(path)

            self.assertEqual(summary.tasks, 2)
            self.assertEqual(summary.average_complete_us, 12.0)
            self.assertEqual(summary.max_complete_us, 14.0)

    def test_inventories_required_trace_families(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runlog = Path(temp)
            files = {
                "TaskTrace_node_0.tr": b"task",
                "PacketTrace_node_0.tr": b"packet",
                "PortTrace_node_1_port_2.tr": b"port-data",
                "QueueTrace_node_1_port_2.tr": b"queue",
                "PfcTrace_node_1_port_2.tr": b"pfc",
                "CbfcTrace_node_1_port_2.tr": b"cbfc-data",
                "AllPacketTrace_Tx_node_0.tr": b"path",
            }
            for name, content in files.items():
                (runlog / name).write_bytes(content)

            inventory = trace_inventory(runlog)

            self.assertEqual(inventory["task"].files, 1)
            self.assertEqual(inventory["packet"].files, 1)
            self.assertEqual(inventory["port"].bytes, len(b"port-data"))
            self.assertEqual(inventory["queue"].files, 1)
            self.assertEqual(inventory["flow_control"].files, 2)
            self.assertEqual(inventory["packet_path"].files, 1)


if __name__ == "__main__":
    unittest.main()
