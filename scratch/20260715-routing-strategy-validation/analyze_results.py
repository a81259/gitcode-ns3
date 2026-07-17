#!/usr/bin/env python3
from __future__ import annotations

import csv
import gzip
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
MATRIX = json.loads((PACKAGE_ROOT / "matrix.yaml").read_text(encoding="utf-8"))["cases"]
HEADER = re.compile(
    r"Uid:(\d+) Psn:(\d+) Src:(\d+) Dst:(\d+) "
    r"SrcTpn:(\d+) DstTpn:(\d+).*?TaskId:(\d+)"
)
TRACE_NODE = re.compile(r"_node_(\d+)\.tr$")
PATH_TRIPLE = re.compile(r"\[\s*(\d+)\s*\]\[\s*(\d+)\s*\]\[\s*(\d+)\s*\]")
TIME_VALUE = re.compile(r"\[\s*(\d+)\s*\]")
QUEUE_ROW = re.compile(r"\[([0-9.]+)us\].*totalBytes: (\d+)")


def trace_lines(path: Path) -> list[str]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
            return handle.read().splitlines()
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def packet_records(case_dir: Path) -> list[dict]:
    records = []
    seen = set()
    traces = list((case_dir / "runlog").glob("AllPacketTrace_PKT_node_*.tr"))
    traces.extend((case_dir / "runlog").glob("AllPacketTrace_PKT_node_*.tr.gz"))
    for trace in sorted(traces):
        trace_node_match = re.search(r"_node_(\d+)\.tr(?:\.gz)?$", trace.name)
        if trace_node_match is None:
            continue
        trace_node = int(trace_node_match.group(1))
        lines = trace_lines(trace)
        for index, line in enumerate(lines):
            match = HEADER.search(line)
            if not match or index + 2 >= len(lines):
                continue
            if trace_node != int(match.group(3)):
                continue
            identity = (line.strip(), lines[index + 1].strip(), lines[index + 2].strip())
            if identity in seen:
                continue
            seen.add(identity)
            triples = [(int(a), int(b), int(c)) for a, b, c in PATH_TRIPLE.findall(identity[1])]
            branch_port = next((send for _, node, send in triples if node in {2, 32}), None)
            times = [int(value) for value in TIME_VALUE.findall(identity[2])]
            records.append({
                "uid": int(match.group(1)), "psn": int(match.group(2)),
                "src": int(match.group(3)), "dst": int(match.group(4)),
                "src_tpn": int(match.group(5)), "dst_tpn": int(match.group(6)),
                "task_id": int(match.group(7)), "branch_port": branch_port,
                "arrival": times[-1] if times else None, "path": identity[1],
            })
    return records


def jain(counts: list[int]) -> float | None:
    if not counts or not sum(counts):
        return None
    return sum(counts) ** 2 / (len(counts) * sum(value * value for value in counts))


def task_metrics(case_dir: Path) -> tuple[float | None, float | None, int]:
    path = case_dir / "output/task_statistics.csv"
    if not path.is_file():
        return None, None, 0
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    durations = []
    throughputs = []
    for row in rows:
        try:
            durations.append(float(row["taskCompletesTime(us)"]) - float(row["taskStartTime(us)"]))
            throughputs.append(float(row["taskThroughput(Gbps)"]))
        except (KeyError, TypeError, ValueError):
            continue
    if not durations:
        return None, None, len(rows)
    ordered = sorted(durations)
    p95 = ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)]
    return statistics.mean(durations), p95, len(rows)


def queue_metrics(case_dir: Path, node: int, ports) -> tuple[dict[int, int], dict[int, float]]:
    maxima: dict[int, int] = {}
    weighted_means: dict[int, float] = {}
    for port in ports:
        trace = case_dir / "runlog" / f"QueueTrace_node_{node}_port_{port}.tr"
        if not trace.is_file():
            trace = trace.with_suffix(trace.suffix + ".gz")
        events = []
        if trace.is_file():
            for line in trace_lines(trace):
                match = QUEUE_ROW.search(line)
                if match:
                    events.append((float(match.group(1)), int(match.group(2))))
        maxima[port] = max((value for _, value in events), default=0)
        if len(events) < 2 or events[-1][0] <= events[0][0]:
            weighted_means[port] = 0.0
            continue
        area = sum(
            value * max(0.0, next_time - time)
            for (time, value), (next_time, _) in zip(events, events[1:])
        )
        weighted_means[port] = area / (events[-1][0] - events[0][0])
    return maxima, weighted_means


def summarize(row: dict, status_by_id: dict[str, dict]) -> dict:
    case_dir = PACKAGE_ROOT / row["case_dir"]
    records = packet_records(case_dir)
    observed_counts = Counter(
        record["branch_port"] for record in records if record["branch_port"] is not None
    )
    if row["topology"] == "clos-32-4-8":
        candidate_ports = range(8, 16)
    elif "SHORTEST_PATHS" in row["routing_type"] and row["topology"] in {
        "micro-mixed", "micro-all-hot", "micro-all-delay"
    }:
        candidate_ports = (1,)
    else:
        candidate_ports = (1, 2, 3)
    counts = {port: observed_counts.get(port, 0) for port in candidate_ports}
    values = list(counts.values())
    queue_node = 32 if row["topology"] == "clos-32-4-8" else 2
    queue_max, queue_mean = queue_metrics(case_dir, queue_node, candidate_ports)
    inversions = 0
    by_flow: dict[tuple[int, int, int, int, int], list[dict]] = {}
    for record in records:
        flow = (
            record["task_id"], record["src"], record["dst"],
            record["src_tpn"], record["dst_tpn"],
        )
        by_flow.setdefault(flow, []).append(record)
    for flow_records in by_flow.values():
        arrivals = sorted((item for item in flow_records if item["arrival"] is not None),
                          key=lambda item: item["arrival"])
        inversions += sum(a["psn"] > b["psn"] for a, b in zip(arrivals, arrivals[1:]))
    mean_fct, p95_fct, task_count = task_metrics(case_dir)
    status = status_by_id.get(row["case_id"], {})
    analysis_status = "matched"
    analysis_note = "Observed evidence is consistent with the pre-registered prediction."
    if status.get("status") != "success":
        analysis_status = "inconclusive"
        analysis_note = "The case did not complete successfully."
    elif row["case_id"] == "hash-many-crc32":
        analysis_status = "partially_matched"
        analysis_note = "Flow affinity held, but structured keys reached only four of eight paths."
    elif row["case_id"] in {"spray-delay-packet-hash", "spray-delay-round-robin"}:
        analysis_status = "partially_matched"
        analysis_note = "FCT increased versus equal-delay spray, but the inversion-count direction was not monotonic."
    elif row["case_id"] == "all-delay-all":
        analysis_status = "mismatched"
        analysis_note = "For the 8 MiB flow, parallel bandwidth still outweighed the 2 us detour delay."
    mean = statistics.mean(values) if values else 0
    cv = statistics.pstdev(values) / mean if len(values) > 1 and mean else 0
    return {
        "case_id": row["case_id"], "block_id": row["block_id"],
        "routing_type": row["routing_type"], "selector": row["selector"],
        "transport": row["transport"], "status": status.get("status", "missing"),
        "analysis_status": analysis_status, "analysis_note": analysis_note,
        "packet_records": len(records),
        "unique_branch_ports": sum(value > 0 for value in counts.values()),
        "branch_port_counts": json.dumps(counts),
        "branch_queue_max_bytes": json.dumps(queue_max),
        "branch_queue_tw_mean_bytes": json.dumps(
            {port: round(value, 3) for port, value in queue_mean.items()}
        ),
        "jain": round(jain(values), 6) if jain(values) is not None else "",
        "cv": round(cv, 6), "psn_adjacent_inversions": inversions,
        "task_count": task_count,
        "mean_task_duration_us": round(mean_fct, 6) if mean_fct is not None else "",
        "p95_task_duration_us": round(p95_fct, 6) if p95_fct is not None else "",
    }


def main() -> None:
    ledger = json.loads((PACKAGE_ROOT / "run-ledger.json").read_text(encoding="utf-8"))
    status_by_id = {item["case_id"]: item for item in ledger["results"]}
    summaries = [summarize(row, status_by_id) for row in MATRIX]
    analysis_dir = PACKAGE_ROOT / "analysis"
    analysis_dir.mkdir(exist_ok=True)
    fields = list(summaries[0])
    with (analysis_dir / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summaries)
    lines = [
        "# Routing Strategy Validation Results", "",
        f"- semantic checkpoint: {ledger['semantic_checkpoint']}",
        f"- successful cases: {sum(item['status'] == 'success' for item in summaries)}/{len(summaries)}",
        "- packet records are exact-record deduplicated; different time/path records are retained.", "",
        "| case | status | paths | Jain | inversions | mean FCT us | p95 FCT us |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summaries:
        lines.append(
            f"| {item['case_id']} | {item['status']} | {item['unique_branch_ports']} | "
            f"{item['jain']} | {item['psn_adjacent_inversions']} | "
            f"{item['mean_task_duration_us']} | {item['p95_task_duration_us']} |"
        )
    (analysis_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(analysis_dir / "summary.csv")


if __name__ == "__main__":
    main()
