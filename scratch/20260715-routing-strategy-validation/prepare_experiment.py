#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
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
    observability_preset,
    write_network_attributes,
)


@dataclass(frozen=True)
class Case:
    case_id: str
    block_id: str
    role: str
    topology: str
    workload: str
    routing_type: str
    selector: str
    observability: str
    transport: str = "RTP"
    op_type: str = "URMA_WRITE"
    changed_variable: str = "routing strategy"
    prediction: str = "See experiment-plan.md"
    falsification_signal: str = "Observed routing behavior contradicts the pre-registered block claim."


HASHES = ("HASH64", "CRC32", "TOEPLITZ")


def case(case_id: str, block: str, role: str, topology: str, workload: str,
         routing_type: str, selector: str, **kwargs) -> Case:
    return Case(case_id, block, role, topology, workload, routing_type, selector,
                kwargs.pop("observability", "detailed"), **kwargs)


CASES: list[Case] = [
    case("sem-flow-short", "semantic", "control", "micro-mixed", "semantic",
         "PER_FLOW_SHORTEST_PATHS", "HASH64", prediction="One stable shortest path only."),
    case("sem-packet-short", "semantic", "treatment", "micro-mixed", "semantic",
         "PER_PACKET_SHORTEST_PATHS", "HASH64", prediction="Only the unique shortest path is used."),
    case("sem-flow-all", "semantic", "treatment", "micro-mixed", "semantic",
         "PER_FLOW_ALL_PATHS", "HASH64", prediction="One stable path from the full candidate set."),
    case("sem-packet-all", "semantic", "treatment", "micro-mixed", "semantic",
         "PER_PACKET_ALL_PATHS", "HASH64", prediction="Shortest and non-shortest paths are both used."),
]

for selector in HASHES:
    CASES.append(case(f"hash-many-{selector.lower()}", "hash-many", "treatment",
                      "clos-32-4-8", "hash-many", "PER_FLOW_SHORTEST_PATHS", selector,
                      prediction="Many flows remain path-affine and distribute across spine paths."))
    CASES.append(case(f"hash-elephant-{selector.lower()}", "hash-elephant", "treatment",
                      "clos-32-4-8", "hash-elephant", "PER_FLOW_SHORTEST_PATHS", selector,
                      prediction="Few elephant flows expose collision and load-skew sensitivity."))

for scenario, topology in (("equal", "micro-equal"), ("delay", "micro-delay")):
    CASES.extend([
        case(f"spray-{scenario}-flow-hash", f"spray-{scenario}", "control", topology,
             "long-flow", "PER_FLOW_SHORTEST_PATHS", "HASH64",
             prediction="The flow remains on one path."),
        case(f"spray-{scenario}-packet-hash", f"spray-{scenario}", "treatment", topology,
             "long-flow", "PER_PACKET_SHORTEST_PATHS", "HASH64",
             prediction="Packets use multiple paths; unequal delay may increase reordering."),
        case(f"spray-{scenario}-round-robin", f"spray-{scenario}", "treatment", topology,
             "long-flow", "PER_PACKET_SHORTEST_PATHS", "ROUND_ROBIN",
             prediction="Packet counts differ by at most one on equal paths; unequal delay exposes reordering."),
    ])

CASES.extend([
    case("adaptive-hot-hash", "adaptive-hot", "control", "micro-slow", "adaptive-hot",
         "PER_PACKET_SHORTEST_PATHS", "HASH64",
         prediction="Static hashing continues to use the slow queued path."),
    case("adaptive-hot-adaptive", "adaptive-hot", "treatment", "micro-slow", "adaptive-hot",
         "PER_PACKET_SHORTEST_PATHS", "ADAPTIVE",
         prediction="Adaptive reduces traffic share and queueing on the slow path."),
    case("adaptive-sparse-rr", "adaptive-sparse", "control", "micro-equal", "adaptive-sparse",
         "PER_PACKET_SHORTEST_PATHS", "ROUND_ROBIN",
         prediction="Sparse packets remain evenly striped."),
    case("adaptive-sparse-adaptive", "adaptive-sparse", "treatment", "micro-equal", "adaptive-sparse",
         "PER_PACKET_SHORTEST_PATHS", "ADAPTIVE",
         prediction="Empty-queue ties reveal first-candidate bias."),
    case("stripe-multi-hash", "stripe-multi", "control", "clos-32-4-8", "ingress-multi",
         "PER_FLOW_SHORTEST_PATHS", "HASH64", prediction="Hash provides a static flow baseline."),
    case("stripe-multi-stripe", "stripe-multi", "treatment", "clos-32-4-8", "ingress-multi",
         "PER_FLOW_SHORTEST_PATHS", "INGRESS_PORT_STRIPE",
         prediction="Eight ingress ports map one-to-one onto eight spine uplinks."),
    case("stripe-single-hash", "stripe-single", "control", "clos-32-4-8", "ingress-single",
         "PER_FLOW_SHORTEST_PATHS", "HASH64", prediction="Different flow keys may use multiple uplinks."),
    case("stripe-single-stripe", "stripe-single", "treatment", "clos-32-4-8", "ingress-single",
         "PER_FLOW_SHORTEST_PATHS", "INGRESS_PORT_STRIPE",
         prediction="One ingress port concentrates all flows on one uplink."),
    case("all-hot-short", "all-hot", "control", "micro-all-hot", "long-flow",
         "PER_PACKET_SHORTEST_PATHS", "HASH64", prediction="Traffic is capped by the slow shortest path."),
    case("all-hot-all", "all-hot", "treatment", "micro-all-hot", "long-flow",
         "PER_PACKET_ALL_PATHS", "HASH64", prediction="Non-shortest high-rate detours improve completion."),
    case("all-delay-short", "all-delay", "control", "micro-all-delay", "long-flow",
         "PER_PACKET_SHORTEST_PATHS", "HASH64", prediction="Traffic avoids delayed detours."),
    case("all-delay-all", "all-delay", "treatment", "micro-all-delay", "long-flow",
         "PER_PACKET_ALL_PATHS", "HASH64", prediction="Delayed detours increase path stretch and reordering."),
])

for selector in HASHES:
    for routing_type in (
        "PER_FLOW_ALL_PATHS", "PER_PACKET_ALL_PATHS",
        "PER_FLOW_SHORTEST_PATHS", "PER_PACKET_SHORTEST_PATHS",
    ):
        CASES.append(case(
            f"cover-{selector.lower()}-{routing_type.lower().replace('_', '-')}",
            "coverage", "coverage", "micro-mixed", "coverage", routing_type, selector,
            observability="balanced", prediction="Legal combination loads and completes successfully.",
        ))
for selector, routing_types in (
    ("ROUND_ROBIN", ("PER_PACKET_ALL_PATHS", "PER_PACKET_SHORTEST_PATHS")),
    ("ADAPTIVE", ("PER_PACKET_ALL_PATHS", "PER_PACKET_SHORTEST_PATHS")),
    ("INGRESS_PORT_STRIPE", ("PER_FLOW_ALL_PATHS", "PER_FLOW_SHORTEST_PATHS")),
):
    for routing_type in routing_types:
        CASES.append(case(
            f"cover-{selector.lower().replace('_', '-')}-{routing_type.lower().replace('_', '-')}",
            "coverage", "coverage", "micro-mixed", "coverage", routing_type, selector,
            observability="balanced", prediction="Legal combination loads and completes successfully.",
        ))

SMOKE_STRATEGIES = (
    ("flow-hash", "PER_FLOW_SHORTEST_PATHS", "HASH64"),
    ("packet-hash", "PER_PACKET_SHORTEST_PATHS", "HASH64"),
    ("round-robin", "PER_PACKET_SHORTEST_PATHS", "ROUND_ROBIN"),
    ("adaptive", "PER_PACKET_SHORTEST_PATHS", "ADAPTIVE"),
    ("ingress-stripe", "PER_FLOW_SHORTEST_PATHS", "INGRESS_PORT_STRIPE"),
)
for transport, op_type in (("CTP", "URMA_WRITE"), ("LDST", "MEM_STORE")):
    for name, routing_type, selector in SMOKE_STRATEGIES:
        CASES.append(case(
            f"smoke-{transport.lower()}-{name}", f"smoke-{transport.lower()}", "smoke",
            "micro-equal", "smoke", routing_type, selector, observability="balanced",
            transport=transport, op_type=op_type,
            prediction=f"{transport} completes with the representative legal strategy.",
        ))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def topology_script(topology: str) -> str:
    config = {
        "micro-equal": (("400Gbps", "20ns"),) * 3,
        "micro-mixed": (("400Gbps", "20ns"),) * 3,
        "micro-delay": (("400Gbps", "20ns"), ("400Gbps", "20ns"), ("400Gbps", "2us")),
        "micro-slow": (("100Gbps", "20ns"), ("400Gbps", "20ns"), ("400Gbps", "20ns")),
        "micro-all-hot": (("25Gbps", "20ns"), ("400Gbps", "20ns"), ("400Gbps", "20ns")),
        "micro-all-delay": (("400Gbps", "20ns"), ("400Gbps", "2us"), ("400Gbps", "2us")),
        "micro-extreme-equal": (("400Gbps", "20ns"), ("400Gbps", "20ns"), ("400Gbps", "20us")),
        "micro-extreme-mixed": (("400Gbps", "20ns"), ("400Gbps", "20us"), ("400Gbps", "20us")),
    }
    if topology == "clos-32-4-8":
        body = """
for host in range(32):
    graph.add_netisim_host(host, forward_delay='1ns')
for switch in range(32, 44):
    graph.add_netisim_node(switch, forward_delay='1ns')
for host in range(32):
    graph.add_netisim_edge(host, 32 + host // 8, bandwidth='400Gbps', delay='20ns')
for leaf in range(32, 36):
    for spine in range(36, 44):
        graph.add_netisim_edge(leaf, spine, bandwidth='100Gbps', delay='20ns')
graph.build_graph_config()
graph.gen_compressed_route_table(path_finding_algo=all_shortest_paths, multiple_workers=1)
graph.write_config(include_transport=False)
"""
    else:
        links = config[topology]
        link_lines = []
        for index, (bandwidth, delay) in enumerate(links):
            mid = 4 + index
            link_lines.append(
                f"graph.add_netisim_edge(2, {mid}, bandwidth='{bandwidth}', delay='{delay}')"
            )
            link_lines.append(
                f"graph.add_netisim_edge(3, {mid}, bandwidth='{bandwidth}', delay='{delay}')"
            )
        metric = "3 4 4" if topology in {
            "micro-mixed", "micro-all-hot", "micro-all-delay", "micro-extreme-mixed"
        } else "3 3 3"
        body = f"""
for host in range(2):
    graph.add_netisim_host(host, forward_delay='1ns')
for switch in range(2, 7):
    graph.add_netisim_node(switch, forward_delay='1ns')
graph.add_netisim_edge(0, 2, bandwidth='1200Gbps', delay='20ns')
graph.add_netisim_edge(1, 3, bandwidth='1200Gbps', delay='20ns')
{chr(10).join(link_lines)}
graph.build_graph_config()
graph.gen_compressed_route_table(path_finding_algo=all_shortest_paths, multiple_workers=1)
graph.write_config(include_transport=False)
route_path = CASE_DIR / 'routing_table.csv'
route_path.write_text('''nodeId,dstNodeId,dstPortId,outPorts,metrics
0,1,0,0,4
1,0,0,0,4
2,0,0,0,1
2,1,0,1 2 3,{metric}
3,0,0,1 2 3,{metric}
3,1,0,0,1
4,0,0,0,2
4,1,0,1,2
5,0,0,0,2
5,1,0,1,2
6,0,0,0,2
6,1,0,1,2
''', encoding='utf-8')
"""
    return f"""#!/usr/bin/env python3
import sys
from pathlib import Path
import networkx as nx

CASE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = CASE_DIR.parents[2] / 'ns-3-ub-tools'
sys.path.insert(0, str(TOOLS_DIR))
import net_sim_builder as netsim

def all_shortest_paths(graph, source, target):
    try:
        return nx.all_shortest_paths(graph, source, target)
    except nx.NetworkXNoPath:
        return []

graph = netsim.NetworkSimulationGraph()
graph.output_dir = str(CASE_DIR) + '/'
{body}
"""


def workload_rows(name: str, op_type: str) -> list[list[str | int]]:
    if name == "hash-many":
        pairs = [(src, dst) for src in range(8) for dst in range(16, 24)]
        size = 262_144
    elif name == "hash-elephant":
        pairs = [(i, 16 + i) for i in range(4)]
        size = 16 * 1024 * 1024
    elif name == "ingress-multi":
        pairs = [(i, 16 + i) for i in range(8)]
        size = 4 * 1024 * 1024
    elif name == "ingress-single":
        pairs = [(0, dst) for dst in range(16, 24)]
        size = 2 * 1024 * 1024
    elif name == "adaptive-sparse":
        return [[i, 0, 1, 1024, op_type, 7, f"{i * 10}us", 0, ""] for i in range(64)]
    elif name == "latency-small":
        return [[i, 0, 1, 16 * 1024, op_type, 7, f"{i * 100}us", 0, ""] for i in range(64)]
    elif name == "semantic":
        pairs, size = [(0, 1)], 4 * 1024 * 1024
    elif name in {"long-flow", "adaptive-hot"}:
        pairs, size = [(0, 1)], 8 * 1024 * 1024
    elif name in {"coverage", "smoke"}:
        pairs, size = [(0, 1)], 1024 * 1024
    else:
        raise ValueError(name)
    return [[i, src, dst, size, op_type, 7, "10ns", 0, ""]
            for i, (src, dst) in enumerate(pairs)]


def write_traffic(case_dir: Path, current: Case) -> None:
    header = ["taskId", "sourceNode", "destNode", "dataSize(Byte)", "opType",
              "priority", "delay", "phaseId", "dependOnPhases"]
    with (case_dir / "traffic.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(workload_rows(current.workload, current.op_type))


def spec_text(current: Case) -> str:
    return f"""# Experiment Spec: {current.case_id}

## Goal

Validate the pre-registered routing claim for block `{current.block_id}`.

## Topology

- family: `{current.topology}`
- transport_channel_mode: `on-demand`
- generated by: `generate_topology.py`

## Workload

- profile: `{current.workload}`
- operation: `{current.op_type}`
- transport: `{current.transport}`

## Routing Intent

- routing_type: `{current.routing_type}`
- multipath_selector: `{current.selector}`
- path_source: `manual-route-table` for micro topologies, otherwise `auto-path-finder`

## Network Overrides

- flow_control: `CBFC` (runtime catalog default, explicitly pinned)
- congestion_control: disabled
- retransmission: disabled; any drop is a safety failure

## Observability

- tier: `{current.observability}`

## Prediction

{current.prediction}

## Falsification Signal

{current.falsification_signal}

## Artifact Contract

The case must contain node, topology, routing, traffic, full network attributes, console log,
runlog traces, and parser summaries. Path and queue metrics are trace-derived.
"""


def plan_text() -> str:
    return """# Routing Strategy Validation Plan

## Claim

Every legal routing strategy must satisfy its routing semantics, and its expected advantage must
appear only in the topology and workload conditions that provide the mechanism it relies on.

## Simulator Boundary

This is an OpenUSim model validation. Results establish behavior of the current reference
implementation, not physical-device performance or UB specification-mandated algorithm quality.

## Blocks

1. `semantic`: four UB RT bit combinations on one shortest plus two non-shortest candidates.
2. `hash-many` / `hash-elephant`: static hash distribution with many flows and collision exposure.
3. `spray-equal` / `spray-delay`: per-flow, per-packet hash, and RR under equal/unequal delay.
4. `adaptive-hot` / `adaptive-sparse`: local queue avoidance and empty-queue tie bias.
5. `stripe-multi` / `stripe-single`: distributed ingress advantage and single-ingress collapse.
6. `all-hot` / `all-delay`: detour capacity advantage and path-stretch cost.
7. `coverage`: all 18 legal RoutingType/MultipathSelector combinations.
8. `smoke-ctp` / `smoke-ldst`: five representative strategies per transport path.

## Fixed Controls

- release build and `scratch/ub-quick-example` runner
- on-demand transport-channel creation
- CBFC flow control; congestion control disabled
- identical topology and workload within each control/treatment block
- RTP for directional and coverage blocks; CTP/LDST only for representative smoke
- detailed observability for directional blocks, balanced for coverage and smoke

## Evidence Plan

- measured: task statistics and per-port throughput
- trace-derived: path histogram, flow affinity, Jain index, CV, PSN arrival inversions
- trace-derived queue evidence: maximum and time-weighted occupancy where available
- log-derived: return code and explicit failure text

Exact duplicate AllPacketTrace records are removed by complete record identity. Same-PSN records
with different timestamps or paths remain visible as retransmission or duplicate-delivery proxies.

## Checkpoint Policy

`pause_for_user` is replaced by the user's approved end-to-end policy: semantic hard failures stop
the matrix immediately. Performance prediction mismatches are retained and execution continues.
All simulations run sequentially; no concurrent build or test is allowed.

## Artifact Contract

The package contains the plan, immutable matrix, command manifest, run ledger, per-case specs,
generated case inputs, console logs, traces, parser summaries, and final analysis tables.
"""


def write_package_metadata() -> None:
    write_text(PACKAGE_ROOT / "experiment-plan.md", plan_text())
    matrix = []
    for current in CASES:
        row = asdict(current)
        row.update({
            "case_dir": f"cases/{current.case_id}",
            "fixed_controls": "See experiment-plan.md",
            "metric_checks": ["path_usage", "flow_affinity", "task_completion", "queue_evidence"],
            "expected_artifacts": ["console.log", "runlog/", "output/task_statistics.csv"],
            "parallel_group": "sequential-only",
            "checkpoint_ids": ["semantic-gate"] if current.block_id == "semantic" else [],
        })
        matrix.append(row)
    write_text(PACKAGE_ROOT / "matrix.yaml", json.dumps({"cases": matrix}, indent=2))
    commands = {
        "execution_policy": "sequential-only",
        "runner": "python3.12 ./ns3 run --no-build",
        "cases": [
            {"case_id": current.case_id,
             "command": f"python3.12 ./ns3 run --no-build 'scratch/ub-quick-example --case-path=scratch/20260715-routing-strategy-validation/cases/{current.case_id}'"}
            for current in CASES
        ],
    }
    write_text(PACKAGE_ROOT / "command-manifest.yaml", json.dumps(commands, indent=2))
    ledger_lines = [
        "# Run Ledger", "", "- branch: `codex/routing-modes`",
        "- checkpoint_policy: semantic hard failure stops; performance mismatch continues",
        "- execution: sequential-only", "", "| case | block | status | return code |",
        "|---|---|---:|---:|",
    ]
    ledger_lines.extend(f"| {c.case_id} | {c.block_id} | pending | |" for c in CASES)
    write_text(PACKAGE_ROOT / "run-ledger.md", "\n".join(ledger_lines))


def prepare_case(current: Case) -> None:
    case_dir = CASES_ROOT / current.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    write_text(case_dir / "experiment-spec.md", spec_text(current))
    script = case_dir / "generate_topology.py"
    write_text(script, topology_script(current.topology))
    subprocess.run([sys.executable, str(script)], cwd=REPO_ROOT, check=True)
    write_traffic(case_dir, current)
    explicit = {
        "ns3::UbApp::RoutingType": current.routing_type,
        "ns3::UbTransportChannel::RoutingType": current.routing_type,
        "ns3::UbLdstApi::RoutingType": current.routing_type,
        "ns3::UbRoutingProcess::MultipathSelector": current.selector,
        "ns3::UbSwitch::FlowControl": "CBFC",
        "UB_CC_ENABLED": "false",
    }
    if current.transport in {"RTP", "CTP"}:
        explicit["ns3::UbApp::TransportMode"] = current.transport
    write_network_attributes(
        case_dir,
        explicit_overrides=explicit,
        observability_overrides=observability_preset(current.observability),
    )
    result = check_case_files(case_dir, transport_channel_mode="on-demand")
    if result["status"] != "ok":
        raise RuntimeError(f"case gate failed for {current.case_id}: {result}")


def main() -> None:
    if len(CASES) != 56:
        raise RuntimeError(f"expected 56 cases, got {len(CASES)}")
    write_package_metadata()
    for index, current in enumerate(CASES, start=1):
        print(f"[{index:02d}/{len(CASES)}] prepare {current.case_id}", flush=True)
        prepare_case(current)
    print(f"prepared {len(CASES)} cases under {PACKAGE_ROOT}")


if __name__ == "__main__":
    main()
