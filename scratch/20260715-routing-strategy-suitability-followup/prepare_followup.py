#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parents[1]
CASES_ROOT = PACKAGE_ROOT / "cases"
SKILL_SCRIPTS = REPO_ROOT / ".codex/skills/openusim-run-experiment/scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

from openusim_run_experiment.case_checker import check_case_files
from openusim_run_experiment.network_attribute_writer import (
    load_or_build_parameter_catalog,
    observability_preset,
    write_network_attributes,
)


SEEDS = (11, 29, 47)


@dataclass(frozen=True)
class Case:
    case_id: str
    block_id: str
    role: str
    control_id: str
    topology_profile: str
    routing_type: str
    selector: str
    changed_variable: str
    prediction: str
    falsification_signal: str
    path_rate_ratio: float = 1.0
    interarrival_gap_ns: int = 0
    pairing_seed: int = 0
    observability: str = "balanced"


def build_cases() -> list[Case]:
    cases = []
    for ratio, ratio_label in ((1.0, "100"), (0.5, "50"), (0.25, "25")):
        for gap_ns, gap_label in ((1_000, "1u"), (10_000, "10u"), (100_000, "100u")):
            control = f"as-r{ratio_label}-g{gap_label}-hash64"
            for label, selector in (("hash64", "HASH64"), ("rr", "ROUND_ROBIN"),
                                    ("adaptive", "ADAPTIVE")):
                cases.append(Case(
                    case_id=f"as-r{ratio_label}-g{gap_label}-{label}",
                    block_id="adaptive-single-packet-sparse",
                    role="control" if selector == "HASH64" else "treatment",
                    control_id=control,
                    topology_profile="micro-sparse",
                    routing_type="PER_PACKET_SHORTEST_PATHS",
                    selector=selector,
                    changed_variable="selector under one-packet sparse arrivals",
                    prediction=(
                        "As the interarrival gap drains every queue, adaptive loses congestion signal "
                        "and concentrates on the first tied candidate."
                    ),
                    falsification_signal=(
                        "Queues are empty before each task but adaptive remains evenly spread."
                    ),
                    path_rate_ratio=ratio,
                    interarrival_gap_ns=gap_ns,
                    observability="detailed",
                ))
    for regime in ("neutral", "capacity", "latency"):
        for seed in SEEDS:
            control = f"pf-{regime}-s{seed}-short"
            for label, routing_type in (("short", "PER_FLOW_SHORTEST_PATHS"),
                                        ("all", "PER_FLOW_ALL_PATHS")):
                cases.append(Case(
                    case_id=f"pf-{regime}-s{seed}-{label}",
                    block_id="per-flow-all-distinct-keys",
                    role="control" if label == "short" else "treatment",
                    control_id=control,
                    topology_profile=f"clos-distinct-{regime}",
                    routing_type=routing_type,
                    selector="HASH64",
                    changed_variable="shortest-only versus all-path scope across distinct flow keys",
                    prediction=(
                        "Distinct per-flow keys spread across the full candidate set; capacity detours help "
                        "and high-delay detours hurt relative to shortest-only routing."
                    ),
                    falsification_signal=(
                        "All-path traffic uses no detour across three pairing seeds, or no regime-dependent "
                        "performance sign change appears despite detour use."
                    ),
                    pairing_seed=seed,
                    observability="balanced",
                ))
    if len(cases) != 45:
        raise RuntimeError(f"expected 45 follow-up cases, got {len(cases)}")
    return cases


CASES = build_cases()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def micro_script(current: Case) -> str:
    slow_rate = int(400 * current.path_rate_ratio)
    return f"""#!/usr/bin/env python3
import sys
from pathlib import Path
import networkx as nx

CASE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = CASE_DIR.parents[2] / 'ns-3-ub-tools'
sys.path.insert(0, str(TOOLS_DIR))
import net_sim_builder as netsim

def paths(graph, source, target):
    try:
        return nx.all_shortest_paths(graph, source, target)
    except nx.NetworkXNoPath:
        return []

graph = netsim.NetworkSimulationGraph()
graph.output_dir = str(CASE_DIR) + '/'
for host in range(2):
    graph.add_netisim_host(host, forward_delay='1ns')
for switch in range(2, 7):
    graph.add_netisim_node(switch, forward_delay='1ns')
graph.add_netisim_edge(0, 2, bandwidth='1200Gbps', delay='20ns')
graph.add_netisim_edge(1, 3, bandwidth='1200Gbps', delay='20ns')
graph.add_netisim_edge(2, 4, bandwidth='{slow_rate}Gbps', delay='20ns')
graph.add_netisim_edge(3, 4, bandwidth='{slow_rate}Gbps', delay='20ns')
for mid in (5, 6):
    graph.add_netisim_edge(2, mid, bandwidth='400Gbps', delay='20ns')
    graph.add_netisim_edge(3, mid, bandwidth='400Gbps', delay='20ns')
graph.build_graph_config()
graph.gen_compressed_route_table(path_finding_algo=paths, multiple_workers=1)
graph.write_config(include_transport=False)
(CASE_DIR / 'routing_table.csv').write_text('''nodeId,dstNodeId,dstPortId,outPorts,metrics
0,1,0,0,4
1,0,0,0,4
2,0,0,0,1
2,1,0,1 2 3,3 3 3
3,0,0,1 2 3,3 3 3
3,1,0,0,1
4,0,0,0,2
4,1,0,1,2
5,0,0,0,2
5,1,0,1,2
6,0,0,0,2
6,1,0,1,2
''', encoding='utf-8')
"""


def clos_script(current: Case) -> str:
    regime = current.topology_profile.removeprefix("clos-distinct-")
    rates = ["400Gbps", "400Gbps", "400Gbps"]
    delays = ["20ns", "20ns", "20ns"]
    if regime == "capacity":
        rates[0] = "100Gbps"
    elif regime == "latency":
        delays[1:] = ["20us", "20us"]
    elif regime != "neutral":
        raise ValueError(regime)
    edge_lines = []
    for index, (rate, delay) in enumerate(zip(rates, delays)):
        spine = 18 + index
        edge_lines.append(f"graph.add_netisim_edge(16, {spine}, bandwidth='{rate}', delay='{delay}')")
        edge_lines.append(f"graph.add_netisim_edge(17, {spine}, bandwidth='{rate}', delay='{delay}')")
    local_left = "\n".join(f"16,{dst},0,{dst},1" for dst in range(8))
    local_right = "\n".join(f"17,{dst},0,{dst - 8},1" for dst in range(8, 16))
    spine_routes = "\n".join(
        f"{spine},0..7,0,0,2\n{spine},8..15,0,1,2" for spine in range(18, 21)
    )
    return f"""#!/usr/bin/env python3
import sys
from pathlib import Path
import networkx as nx

CASE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = CASE_DIR.parents[2] / 'ns-3-ub-tools'
sys.path.insert(0, str(TOOLS_DIR))
import net_sim_builder as netsim

def paths(graph, source, target):
    try:
        return nx.all_shortest_paths(graph, source, target)
    except nx.NetworkXNoPath:
        return []

graph = netsim.NetworkSimulationGraph()
graph.output_dir = str(CASE_DIR) + '/'
for host in range(16):
    graph.add_netisim_host(host, forward_delay='1ns')
for switch in range(16, 21):
    graph.add_netisim_node(switch, forward_delay='1ns')
for host in range(8):
    graph.add_netisim_edge(host, 16, bandwidth='400Gbps', delay='20ns')
for host in range(8, 16):
    graph.add_netisim_edge(host, 17, bandwidth='400Gbps', delay='20ns')
{chr(10).join(edge_lines)}
graph.build_graph_config()
graph.gen_compressed_route_table(path_finding_algo=paths, multiple_workers=1)
graph.write_config(include_transport=False)
(CASE_DIR / 'routing_table.csv').write_text('''nodeId,dstNodeId,dstPortId,outPorts,metrics
0..15,0..15,0,0,4
{local_left}
16,8..15,0,8 9 10,3 4 4
17,0..7,0,8 9 10,3 4 4
{local_right}
{spine_routes}
''', encoding='utf-8')
"""


def topology_script(current: Case) -> str:
    return micro_script(current) if current.block_id == "adaptive-single-packet-sparse" else clos_script(current)


def traffic_rows(current: Case) -> list[list[str | int]]:
    if current.block_id == "adaptive-single-packet-sparse":
        return [
            [index, 0, 1, 1024, "URMA_WRITE", 7,
             f"{10 + index * current.interarrival_gap_ns}ns", 0, ""]
            for index in range(64)
        ]
    pairs = [(src, dst) for src in range(8) for dst in range(8, 16)]
    selected = random.Random(current.pairing_seed).sample(pairs, 32)
    return [
        [index, src, dst, 256 * 1024, "URMA_WRITE", 7, "10ns", 0, ""]
        for index, (src, dst) in enumerate(selected)
    ]


def write_traffic(case_dir: Path, current: Case) -> None:
    header = ["taskId", "sourceNode", "destNode", "dataSize(Byte)", "opType",
              "priority", "delay", "phaseId", "dependOnPhases"]
    with (case_dir / "traffic.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(traffic_rows(current))


def spec_text(current: Case) -> str:
    return f"""# Follow-up Experiment Spec: {current.case_id}

## Goal

Close the comparison-validity gap identified by the 152-case suitability matrix.

## Topology And Workload

- topology_profile: `{current.topology_profile}`
- transport_channel_mode: `on-demand`
- path_rate_ratio: `{current.path_rate_ratio}`
- interarrival_gap_ns: `{current.interarrival_gap_ns}`
- pairing_seed: `{current.pairing_seed}`
- workload: `64 one-packet tasks` for sparse adaptive, `32 distinct endpoint pairs` for per-flow scope

## Routing Intent

- routing_type: `{current.routing_type}`
- multipath_selector: `{current.selector}`

## Controlled Comparison

- role: `{current.role}`
- control_id: `{current.control_id}`
- changed_variable: `{current.changed_variable}`

## Prediction

{current.prediction}

## Falsification Signal

{current.falsification_signal}

## Evidence

Task statistics are measured. Path use, queue state, and packet order are trace-derived. Runs are
sequential with CBFC, congestion control disabled, retransmission disabled, and on-demand TP setup.
"""


def plan_text() -> str:
    return """# Routing Strategy Suitability Follow-up Plan

## Claim

Two validity gaps in the main 152-case matrix need bounded follow-up before final recommendations:
256 KiB sparse tasks do not guarantee empty queues between packets, and repeated tasks on one
endpoint pair do not provide independent per-flow hash keys.

## Blocks

1. `adaptive-single-packet-sparse` (27): 64 one-packet tasks, rate ratios 1/1, 1/2, 1/4,
   interarrival gaps 1/10/100 us, and HASH64/RR/ADAPTIVE.
2. `per-flow-all-distinct-keys` (18): 32 independently paired flows, three pairing seeds,
   neutral/capacity/latency detour regimes, and per-flow shortest/all-path routing.

## Controls And Evidence

Each row changes one routing choice inside a fixed topology/workload cell. Adaptive is compared to
HASH64 and RR. Per-flow all-path is compared to per-flow shortest. Required evidence is task FCT,
aggregate goodput, branch-port bytes, queue occupancy, and detailed packet paths for sparse cases.

## Checkpoint Policy

`continue_full_matrix`; one pilot pair per block, block safety stop on abort, incomplete task,
missing artifact, or route non-use. Prediction mismatch continues and remains visible.

## Artifact Contract

The package contains 45 immutable rows, commands, ledgers, generated case inputs, compressed traces,
analysis tables, and a final statement of whether each evidence gap was closed.
"""


def write_metadata() -> None:
    write_text(PACKAGE_ROOT / "experiment-plan.md", plan_text())
    rows = []
    for current in CASES:
        row = asdict(current)
        row.update({
            "case_dir": f"cases/{current.case_id}",
            "fixed_controls": "See experiment-plan.md and control_id row.",
            "reason": "This row directly closes a named comparison-validity gap.",
            "metric_checks": ["task_fct", "aggregate_goodput", "path_usage", "queue_evidence"],
            "expected_artifacts": ["console.log", "runlog/", "output/task_statistics.csv"],
            "parallel_group": "sequential-only",
            "checkpoint_ids": [f"pilot-{current.block_id}"],
        })
        rows.append(row)
    write_text(PACKAGE_ROOT / "matrix.yaml", json.dumps({"cases": rows}, indent=2))
    manifest = {
        "execution_policy": "sequential-only",
        "cases": [{
            "case_id": current.case_id,
            "command": (
                "python3.12 ./ns3 run --no-build "
                f"'scratch/ub-quick-example --case-path=scratch/20260715-routing-strategy-"
                f"suitability-followup/cases/{current.case_id}'"
            ),
        } for current in CASES],
    }
    write_text(PACKAGE_ROOT / "command-manifest.yaml", json.dumps(manifest, indent=2))
    ledger = ["# Run Ledger", "", "- branch: `next`", "- status: planned",
              "- execution: sequential-only", "", "| case | block | status |", "|---|---|---:|"]
    ledger.extend(f"| {case.case_id} | {case.block_id} | pending |" for case in CASES)
    write_text(PACKAGE_ROOT / "run-ledger.md", "\n".join(ledger))
    for current in CASES:
        write_text(CASES_ROOT / current.case_id / "experiment-spec.md", spec_text(current))


def prepare_case(current: Case) -> None:
    case_dir = CASES_ROOT / current.case_id
    script = case_dir / "generate_topology.py"
    write_text(script, topology_script(current))
    subprocess.run([sys.executable, str(script)], cwd=REPO_ROOT, check=True)
    write_traffic(case_dir, current)
    explicit = {
        "ns3::UbApp::RoutingType": current.routing_type,
        "ns3::UbTransportChannel::RoutingType": current.routing_type,
        "ns3::UbLdstApi::RoutingType": current.routing_type,
        "ns3::UbRoutingProcess::MultipathSelector": current.selector,
        "ns3::UbSwitch::FlowControl": "CBFC",
        "ns3::UbTransportChannel::EnableRetrans": "false",
        "UB_CC_ENABLED": "false",
    }
    write_network_attributes(
        case_dir,
        explicit_overrides=explicit,
        observability_overrides=observability_preset(current.observability),
    )
    result = check_case_files(case_dir, transport_channel_mode="on-demand")
    if result["status"] != "ok":
        raise RuntimeError(f"case gate failed for {current.case_id}: {result}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--generate-cases", action="store_true")
    args = parser.parse_args()
    if args.plan_only == args.generate_cases:
        parser.error("choose exactly one mode")
    write_metadata()
    if args.plan_only:
        print(f"planned {len(CASES)} follow-up cases")
        return
    catalog, path = load_or_build_parameter_catalog()
    print(f"runtime catalog: {path} ({catalog['entry_count']} entries)")
    for index, current in enumerate(CASES, start=1):
        print(f"[{index:02d}/{len(CASES)}] generate {current.case_id}", flush=True)
        prepare_case(current)
    print(f"generated and gated {len(CASES)} follow-up cases")


if __name__ == "__main__":
    main()
