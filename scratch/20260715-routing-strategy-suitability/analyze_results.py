#!/usr/bin/env python3
from __future__ import annotations

import csv
import gzip
import json
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
MATRIX = json.loads((PACKAGE_ROOT / "matrix.yaml").read_text(encoding="utf-8"))["cases"]
LEDGER = json.loads((PACKAGE_ROOT / "run-ledger.json").read_text(encoding="utf-8"))
RUN_BY_ID = {item["case_id"]: item for item in LEDGER["results"]}
PORT_ROW = re.compile(r"Port Tx, port ID: (\d+) PacketSize: (\d+)")
QUEUE_ROW = re.compile(r"\[([0-9.]+)us\].*totalBytes: (\d+)")
HEADER = re.compile(
    r"Uid:(\d+) Psn:(\d+) Src:(\d+) Dst:(\d+) "
    r"SrcTpn:(\d+) DstTpn:(\d+).*?TaskId:(\d+)"
)
PATH_TRIPLE = re.compile(r"\[\s*(\d+)\s*\]\[\s*(\d+)\s*\]\[\s*(\d+)\s*\]")
TIME_VALUE = re.compile(r"\[\s*(\d+)\s*\]")


def text_lines(path: Path) -> list[str]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
            return handle.read().splitlines()
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1)]


def jain(values: list[int]) -> float | None:
    if not values or not sum(values):
        return None
    return sum(values) ** 2 / (len(values) * sum(value * value for value in values))


def task_metrics(case_dir: Path) -> dict:
    path = case_dir / "output/task_statistics.csv"
    if not path.is_file():
        return {"task_count": 0, "completed_task_count": 0}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    durations = []
    starts = []
    completions = []
    total_bytes = 0
    for row in rows:
        try:
            start = float(row["taskStartTime(us)"])
            complete = float(row["taskCompletesTime(us)"])
            size = int(row["dataSize(Byte)"])
        except (KeyError, TypeError, ValueError):
            continue
        starts.append(start)
        completions.append(complete)
        durations.append(complete - start)
        total_bytes += size
    span = max(completions) - min(starts) if durations else 0.0
    aggregate_goodput = total_bytes * 8 / span / 1000 if span > 0 else None
    return {
        "task_count": len(rows),
        "completed_task_count": len(durations),
        "mean_task_duration_us": statistics.mean(durations) if durations else None,
        "p50_task_duration_us": percentile(durations, 0.50),
        "p95_task_duration_us": percentile(durations, 0.95),
        "p99_task_duration_us": percentile(durations, 0.99),
        "aggregate_task_goodput_gbps": aggregate_goodput,
    }


def branch_locations(row: dict) -> tuple[list[int], list[int]]:
    width = row["candidate_width"]
    if row["topology_profile"] == "clos-hash":
        return [32, 33], list(range(8, 8 + width))
    if row["topology_profile"] == "clos-ingress":
        return [32], list(range(8, 8 + width))
    return [2], list(range(1, 1 + width))


def branch_metrics(case_dir: Path, row: dict) -> dict:
    nodes, ports = branch_locations(row)
    packet_counts = {port: 0 for port in ports}
    byte_counts = {port: 0 for port in ports}
    for node in nodes:
        for port in ports:
            paths = list((case_dir / "runlog").glob(f"PortTrace_node_{node}_port_{port}.tr*"))
            for path in paths:
                for line in text_lines(path):
                    match = PORT_ROW.search(line)
                    if not match:
                        continue
                    packet_size = int(match.group(2))
                    if packet_size <= 256:
                        continue
                    packet_counts[port] += 1
                    byte_counts[port] += packet_size
    values = list(byte_counts.values())
    total = sum(values)
    mean = statistics.mean(values) if values else 0
    cv = statistics.pstdev(values) / mean if len(values) > 1 and mean else 0
    return {
        "branch_packet_counts": json.dumps(packet_counts, sort_keys=True),
        "branch_byte_counts": json.dumps(byte_counts, sort_keys=True),
        "branch_total_bytes": total,
        "unique_branch_ports": sum(value > 0 for value in values),
        "path_jain": jain(values),
        "path_cv": cv,
        "max_path_share": max(values) / total if total else None,
        "last_path_share": values[-1] / total if total else None,
        "detour_share": sum(values[1:]) / total if total else None,
        "slow_path_share": values[0] / total if total else None,
    }


def queue_metrics(case_dir: Path, row: dict) -> dict:
    nodes, ports = branch_locations(row)
    maxima = []
    weighted_means = []
    slow_max = 0
    slow_mean = 0.0
    for node in nodes:
        for port in ports:
            events = []
            seen = set()
            for path in (case_dir / "runlog").glob(f"QueueTrace_node_{node}_port_{port}.tr*"):
                for line in text_lines(path):
                    match = QUEUE_ROW.search(line)
                    if not match:
                        continue
                    event = (float(match.group(1)), int(match.group(2)), line)
                    if event in seen:
                        continue
                    seen.add(event)
                    events.append((event[0], event[1]))
            events.sort()
            maximum = max((value for _, value in events), default=0)
            if len(events) >= 2 and events[-1][0] > events[0][0]:
                area = sum(
                    value * max(0.0, next_time - current_time)
                    for (current_time, value), (next_time, _) in zip(events, events[1:])
                )
                weighted = area / (events[-1][0] - events[0][0])
            else:
                weighted = 0.0
            maxima.append(maximum)
            weighted_means.append(weighted)
            if port == ports[0]:
                slow_max = max(slow_max, maximum)
                slow_mean = max(slow_mean, weighted)
    return {
        "queue_max_bytes": max(maxima, default=0),
        "queue_tw_mean_max_bytes": max(weighted_means, default=0.0),
        "slow_path_queue_max_bytes": slow_max,
        "slow_path_queue_tw_mean_bytes": slow_mean,
    }


def packet_order_metrics(case_dir: Path, row: dict) -> dict:
    if row["observability"] != "detailed" or row["transport"] != "RTP":
        return {
            "packet_records": None,
            "psn_adjacent_inversions": None,
            "psn_inversions_per_1000": None,
            "per_flow_affinity_violations": None,
        }
    records = []
    seen = set()
    for path in sorted((case_dir / "runlog").glob("AllPacketTrace_PKT_node_*.tr*")):
        trace_node_match = re.search(r"_node_(\d+)\.tr(?:\.gz)?$", path.name)
        if trace_node_match is None:
            continue
        trace_node = int(trace_node_match.group(1))
        lines = text_lines(path)
        for index, line in enumerate(lines):
            match = HEADER.search(line)
            if not match or index + 2 >= len(lines) or trace_node != int(match.group(3)):
                continue
            identity = (line.strip(), lines[index + 1].strip(), lines[index + 2].strip())
            if identity in seen:
                continue
            seen.add(identity)
            triples = [(int(a), int(b), int(c)) for a, b, c in PATH_TRIPLE.findall(identity[1])]
            branch_nodes, _ = branch_locations(row)
            branch_port = next((send for _, node, send in triples if node in branch_nodes), None)
            times = [int(value) for value in TIME_VALUE.findall(identity[2])]
            records.append({
                "psn": int(match.group(2)),
                "src": int(match.group(3)),
                "dst": int(match.group(4)),
                "src_tpn": int(match.group(5)),
                "dst_tpn": int(match.group(6)),
                "task_id": int(match.group(7)),
                "branch_port": branch_port,
                "arrival": times[-1] if times else None,
            })
    by_flow = defaultdict(list)
    for record in records:
        key = (
            record["task_id"], record["src"], record["dst"],
            record["src_tpn"], record["dst_tpn"],
        )
        by_flow[key].append(record)
    inversions = 0
    affinity_violations = 0
    for flow_records in by_flow.values():
        ports = {record["branch_port"] for record in flow_records if record["branch_port"] is not None}
        affinity_violations += len(ports) > 1
        arrivals = sorted(
            (record for record in flow_records if record["arrival"] is not None),
            key=lambda record: record["arrival"],
        )
        inversions += sum(a["psn"] > b["psn"] for a, b in zip(arrivals, arrivals[1:]))
    return {
        "packet_records": len(records),
        "psn_adjacent_inversions": inversions,
        "psn_inversions_per_1000": inversions * 1000 / len(records) if records else None,
        "per_flow_affinity_violations": affinity_violations,
    }


def summarize(row: dict) -> dict:
    case_dir = PACKAGE_ROOT / row["case_dir"]
    result = {key: row[key] for key in (
        "case_id", "block_id", "role", "control_id", "topology_profile",
        "workload_profile", "routing_type", "selector", "candidate_width",
        "traffic_seed_kind", "traffic_seed", "flow_size_bytes", "flow_count",
        "path_delay", "path_rate_ratio", "interarrival_gap_ns", "active_ingress_count",
        "transport", "observability",
    )}
    run = RUN_BY_ID.get(row["case_id"], {})
    result["run_status"] = run.get("status", "missing")
    result.update(task_metrics(case_dir))
    result.update(branch_metrics(case_dir, row))
    result.update(queue_metrics(case_dir, row))
    result.update(packet_order_metrics(case_dir, row))
    return result


def relative_delta(value: float | None, control: float | None) -> float | None:
    if value is None or control in (None, 0):
        return None
    return (value - control) / control * 100


def classify(item: dict, control: dict | None) -> tuple[str, str]:
    if item["run_status"] != "success" or item["completed_task_count"] != item["task_count"]:
        return "inconclusive", "Run or task completion evidence is incomplete."
    if not item["branch_total_bytes"]:
        return "inconclusive", "No branch-port data bytes were observed."
    block = item["block_id"]
    if block == "hash-robustness":
        return "matched", "Static per-flow mapping completed; cross-cell ranking is evaluated at block level."
    if block == "spray-crossover":
        expected_paths = 1 if item["routing_type"].startswith("PER_FLOW") else 2
        if item["unique_branch_ports"] >= expected_paths:
            return "matched", "Observed path scope matches the registered flow/packet behavior."
        return "mismatched", "Packet selection did not use multiple candidates."
    if block == "adaptive-signal":
        if item["selector"] == "HASH64":
            return "matched", "Static-hash control completed with branch evidence."
        if item["selector"] == "ROUND_ROBIN":
            status = "matched" if item["unique_branch_ports"] > 1 else "mismatched"
            return status, "Round-robin path spreading was checked directly."
        if item["interarrival_gap_ns"] > 0:
            status = "matched" if item["max_path_share"] is not None and item["max_path_share"] > 0.8 else "partially_matched"
            return status, "Sparse adaptive traffic is evaluated for empty-queue tie concentration."
        if control is None:
            return "inconclusive", "Adaptive control row is missing."
        share_better = item["slow_path_share"] < control["slow_path_share"]
        fct_better = item["p95_task_duration_us"] < control["p95_task_duration_us"]
        if item["path_rate_ratio"] < 1 and share_better and fct_better:
            return "matched", "Adaptive reduced slow-path share and p95 duration versus hash."
        if share_better or fct_better:
            return "partially_matched", "Only one adaptive advantage metric improved."
        return "mismatched", "Adaptive did not improve either slow-path share or p95 duration."
    if block == "ingress-entropy":
        if item["selector"] == "HASH64":
            return "matched", "Hash control completed with path evidence."
        if item["unique_branch_ports"] <= max(1, item["active_ingress_count"]):
            return "matched", "Stripe path cardinality is bounded by active ingress cardinality."
        return "mismatched", "Stripe used more paths than ingress-derived mapping permits."
    if block == "path-scope-region":
        all_paths = "ALL_PATHS" in item["routing_type"]
        if not all_paths:
            status = "matched" if item["detour_share"] == 0 else "mismatched"
            return status, "Shortest-only route scope was checked from branch-port bytes."
        if item["flow_count"] > 1 or item["routing_type"].startswith("PER_PACKET"):
            status = "matched" if item["detour_share"] > 0 else "mismatched"
            return status, "All-path treatment was checked for actual detour use."
        return "matched", "A single per-flow hash may choose any one candidate from the all-path set."
    if block == "transport-transfer":
        return "matched", "The legal transport/profile combination completed with branch evidence."
    return "inconclusive", "No classification rule is registered for this block."


def comparison_cell(item: dict) -> str:
    block = item["block_id"]
    if block == "hash-robustness":
        return f"{item['workload_profile']}|w{item['candidate_width']}|s{item['traffic_seed']}"
    if block == "spray-crossover":
        return f"{item['flow_size_bytes']}|{item['path_delay']}"
    if block == "adaptive-signal":
        if item["workload_profile"] == "adaptive-confirm":
            return f"confirm|s{item['traffic_seed']}"
        return f"screen|r{item['path_rate_ratio']}|g{item['interarrival_gap_ns']}"
    if block == "ingress-entropy":
        return f"n{item['active_ingress_count']}|s{item['traffic_seed']}"
    if block == "path-scope-region":
        return f"{item['topology_profile']}|{item['workload_profile']}"
    return f"{item['transport']}"


OBJECTIVES = {
    "hash-robustness": (("path_jain", "max"), ("aggregate_task_goodput_gbps", "max"),
                        ("p95_task_duration_us", "min"), ("queue_max_bytes", "min")),
    "spray-crossover": (("aggregate_task_goodput_gbps", "max"),
                        ("p95_task_duration_us", "min"), ("p99_task_duration_us", "min"),
                        ("psn_inversions_per_1000", "min")),
    "adaptive-signal": (("aggregate_task_goodput_gbps", "max"),
                        ("p95_task_duration_us", "min"), ("queue_max_bytes", "min"),
                        ("slow_path_share", "min")),
    "ingress-entropy": (("path_jain", "max"), ("aggregate_task_goodput_gbps", "max"),
                        ("p95_task_duration_us", "min"), ("queue_max_bytes", "min")),
    "path-scope-region": (("aggregate_task_goodput_gbps", "max"),
                          ("p95_task_duration_us", "min"), ("p99_task_duration_us", "min"),
                          ("psn_inversions_per_1000", "min")),
}


def dominates(left: dict, right: dict, objectives: tuple[tuple[str, str], ...]) -> bool:
    comparable = []
    strictly_better = False
    for field, direction in objectives:
        a, b = left.get(field), right.get(field)
        if a is None or b is None:
            continue
        comparable.append(field)
        if direction == "max":
            if a < b:
                return False
            strictly_better |= a > b
        else:
            if a > b:
                return False
            strictly_better |= a < b
    return bool(comparable) and strictly_better


def mark_pareto(items: list[dict]) -> None:
    by_cell = defaultdict(list)
    for item in items:
        item["comparison_cell"] = comparison_cell(item)
        item["pareto"] = None if item["block_id"] == "transport-transfer" else False
        by_cell[(item["block_id"], item["comparison_cell"])].append(item)
    for (block, _), cell_items in by_cell.items():
        if block not in OBJECTIVES:
            continue
        objectives = OBJECTIVES[block]
        valid = [item for item in cell_items if item["analysis_status"] != "inconclusive"]
        for item in valid:
            item["pareto"] = not any(
                other is not item and dominates(other, item, objectives) for other in valid
            )


def round_value(value):
    return round(value, 6) if isinstance(value, float) else value


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    if not rows:
        return
    fields = fields or list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({key: round_value(value) for key, value in row.items()} for row in rows)


def main() -> None:
    summaries = [summarize(row) for row in MATRIX]
    by_id = {item["case_id"]: item for item in summaries}
    for item in summaries:
        control = by_id.get(item["control_id"])
        status, note = classify(item, control)
        item["analysis_status"] = status
        item["analysis_note"] = note
        item["p95_delta_vs_control_pct"] = relative_delta(
            item.get("p95_task_duration_us"), control.get("p95_task_duration_us") if control else None
        )
        item["goodput_delta_vs_control_pct"] = relative_delta(
            item.get("aggregate_task_goodput_gbps"),
            control.get("aggregate_task_goodput_gbps") if control else None,
        )
        item["jain_delta_vs_control"] = (
            item["path_jain"] - control["path_jain"]
            if control and item["path_jain"] is not None and control["path_jain"] is not None
            else None
        )
    mark_pareto(summaries)
    analysis_dir = PACKAGE_ROOT / "analysis"
    analysis_dir.mkdir(exist_ok=True)
    write_csv(analysis_dir / "summary.csv", summaries)
    pareto_rows = [item for item in summaries if item["pareto"] is True]
    write_csv(analysis_dir / "pareto.csv", pareto_rows)
    comparisons = [item for item in summaries if item["control_id"] in by_id]
    write_csv(analysis_dir / "comparisons.csv", comparisons)
    status_counts = defaultdict(int)
    for item in summaries:
        status_counts[item["analysis_status"]] += 1
    block_rows = []
    for block in sorted({item["block_id"] for item in summaries}):
        group = [item for item in summaries if item["block_id"] == block]
        block_rows.append({
            "block_id": block,
            "cases": len(group),
            "success": sum(item["run_status"] == "success" for item in group),
            "matched": sum(item["analysis_status"] == "matched" for item in group),
            "partially_matched": sum(item["analysis_status"] == "partially_matched" for item in group),
            "mismatched": sum(item["analysis_status"] == "mismatched" for item in group),
            "inconclusive": sum(item["analysis_status"] == "inconclusive" for item in group),
            "pareto_rows": sum(item["pareto"] is True for item in group),
        })
    write_csv(analysis_dir / "block-summary.csv", block_rows)
    report = [
        "# Routing Strategy Suitability Analysis", "",
        f"- completed runs: {sum(item['run_status'] == 'success' for item in summaries)}/{len(summaries)}",
        "- evidence: measured task statistics plus trace-derived path, queue, and ordering metrics",
        "- throughput.csv is treated as per-port evidence; aggregate task goodput is derived from task completion span",
        "- PSN inversions are ordering evidence, not an exact retransmission count", "",
        "## Block Summary", "",
        "| block | cases | matched | partial | mismatch | inconclusive | Pareto rows |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in block_rows:
        report.append(
            f"| {row['block_id']} | {row['cases']} | {row['matched']} | "
            f"{row['partially_matched']} | {row['mismatched']} | {row['inconclusive']} | "
            f"{row['pareto_rows']} |"
        )
    report.extend(("", "## Row Classification", "",
                   "| case | status | Pareto | p95 us | goodput Gbps | Jain | inversions/1000 |",
                   "|---|---:|---:|---:|---:|---:|---:|"))
    for item in summaries:
        report.append(
            f"| {item['case_id']} | {item['analysis_status']} | {item['pareto']} | "
            f"{round_value(item.get('p95_task_duration_us'))} | "
            f"{round_value(item.get('aggregate_task_goodput_gbps'))} | "
            f"{round_value(item.get('path_jain'))} | "
            f"{round_value(item.get('psn_inversions_per_1000'))} |"
        )
    (analysis_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    (analysis_dir / "status-counts.json").write_text(
        json.dumps(dict(status_counts), indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"rows": len(summaries), "status": dict(status_counts)}))


if __name__ == "__main__":
    main()
