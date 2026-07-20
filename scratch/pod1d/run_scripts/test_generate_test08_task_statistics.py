import csv
import importlib.util
import pathlib
import tempfile
import unittest


SCRIPT_PATH = pathlib.Path(__file__).with_name("generate_test08_task_statistics.py")


def load_generator_module():
    if not SCRIPT_PATH.is_file():
        raise AssertionError(f"missing generator script: {SCRIPT_PATH}")
    spec = importlib.util.spec_from_file_location("generate_test08_task_statistics", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_traffic(case_dir: pathlib.Path) -> None:
    with (case_dir / "traffic.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["taskId", "sourceNode", "destNode", "dataSize(Byte)", "opType"],
        )
        writer.writeheader()
        writer.writerows(
            [
                {
                    "taskId": "0",
                    "sourceNode": "0",
                    "destNode": "1",
                    "dataSize(Byte)": "125000",
                    "opType": "URMA_WRITE",
                },
                {
                    "taskId": "1",
                    "sourceNode": "1",
                    "destNode": "0",
                    "dataSize(Byte)": "250000",
                    "opType": "URMA_WRITE",
                },
            ]
        )


class GenerateTest08TaskStatisticsTest(unittest.TestCase):
    def test_generates_task_statistics_from_task_traces(self):
        generator = load_generator_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            case_dir = pathlib.Path(temp_dir) / "case01"
            runlog = case_dir / "runlog"
            runlog.mkdir(parents=True)
            write_traffic(case_dir)
            (runlog / "TaskTrace_node_0.tr").write_text(
                "[2.000000us] WQE Completes, jettyNum: 0 taskId: 0\n"
                "[1.000000us] WQE Starts, jettyNum: 0 taskId: 0\n"
                "[4.000000us] MEM Task Completes, jettyNum: 0 taskId: 1\n"
                "[1.500000us] MEM Task Starts, jettyNum: 0 taskId: 1\n",
                encoding="utf-8",
            )

            summary = generator.generate_case_statistics(case_dir)

            self.assertEqual(summary.total_traffic_tasks, 2)
            self.assertEqual(summary.completed_tasks, 2)
            with (case_dir / "output" / "task_statistics.csv").open(
                newline="", encoding="utf-8"
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["taskStartTime(us)"], "1.0")
            self.assertEqual(rows[0]["taskCompletesTime(us)"], "2.0")
            self.assertEqual(rows[0]["taskThroughput(Gbps)"], "1000.0")
            self.assertEqual(rows[0]["firstPacketSends(us)"], "0.0")
            self.assertEqual(rows[1]["taskThroughput(Gbps)"], "800.0")

    def test_rejects_case_without_task_trace(self):
        generator = load_generator_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            case_dir = pathlib.Path(temp_dir) / "case01"
            case_dir.mkdir()
            (case_dir / "runlog").mkdir()
            write_traffic(case_dir)

            with self.assertRaisesRegex(FileNotFoundError, "TaskTrace_node_\\*.tr"):
                generator.generate_case_statistics(case_dir)


if __name__ == "__main__":
    unittest.main()
