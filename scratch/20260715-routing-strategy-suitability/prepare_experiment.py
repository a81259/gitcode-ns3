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


HASHES = ("HASH64", "CRC32", "TOEPLITZ")
SEEDS = (11, 29, 47)


@dataclass(frozen=True)
class Case:
    case_id: str
    block_id: str
    role: str
    control_id: str
    topology_profile: str
    workload_profile: str
    routing_type: str
    selector: str
    changed_variable: str
    prediction: str
    reason: str
    falsification_signal: str
    candidate_width: int = 3
    traffic_seed_kind: str = "none"
    traffic_seed: int = 0
    flow_size_bytes: int = 0
    flow_count: int = 0
    path_delay: str = "20ns"
    path_rate_ratio: float = 1.0
    interarrival_gap_ns: int = 0
    active_ingress_count: int = 0
    transport: str = "RTP"
    op_type: str = "URMA_WRITE"
    observability: str = "balanced"


def add_hash_cases(cases: list[Case]) -> None:
    for width in (3, 5, 8):
        for seed in SEEDS:
            control = f"h-many-w{width}-s{seed}-hash64"
            for selector in HASHES:
                cases.append(Case(
                    case_id=f"h-many-w{width}-s{seed}-{selector.lower()}",
                    block_id="hash-robustness",
                    role="control" if selector == "HASH64" else "treatment",
                    control_id=control,
                    topology_profile="clos-hash",
                    workload_profile="hash-many",
                    routing_type="PER_FLOW_SHORTEST_PATHS",
                    selector=selector,
                    changed_variable="multipath selector",
                    prediction=(
                        "Per-flow affinity holds; distribution quality varies with selector, "
                        "candidate width, and the sampled structured key set."
                    ),
                    reason="Static hashes map the same 17-byte routing key deterministically.",
                    falsification_signal=(
                        "A flow changes uplink, or one selector Pareto-dominates every width and key seed."
                    ),
                    candidate_width=width,
                    traffic_seed_kind="traffic_key_seed",
                    traffic_seed=seed,
                    flow_size_bytes=256 * 1024,
                    flow_count=64,
                    observability="balanced",
                ))
    for seed in SEEDS:
        control = f"h-elephant-w8-s{seed}-hash64"
        for selector in HASHES:
            cases.append(Case(
                case_id=f"h-elephant-w8-s{seed}-{selector.lower()}",
                block_id="hash-robustness",
                role="control" if selector == "HASH64" else "treatment",
                control_id=control,
                topology_profile="clos-hash",
                workload_profile="hash-elephant",
                routing_type="PER_FLOW_SHORTEST_PATHS",
                selector=selector,
                changed_variable="multipath selector",
                prediction="Few elephant flows expose collision sensitivity without a universal hash winner.",
                reason="Four deterministic flow keys cannot reliably occupy all eight candidates.",
                falsification_signal="The same selector wins every seed with no collision-sensitive tail penalty.",
                candidate_width=8,
                traffic_seed_kind="traffic_key_seed",
                traffic_seed=seed,
                flow_size_bytes=16 * 1024 * 1024,
                flow_count=4,
                observability="balanced",
            ))


def add_spray_cases(cases: list[Case]) -> None:
    sizes = ((16 * 1024, "16k"), (256 * 1024, "256k"), (8 * 1024 * 1024, "8m"))
    delays = (("20ns", "20n"), ("2us", "2u"), ("20us", "20u"))
    strategies = (
        ("flow-hash64", "PER_FLOW_SHORTEST_PATHS", "HASH64"),
        ("packet-hash64", "PER_PACKET_SHORTEST_PATHS", "HASH64"),
        ("packet-rr", "PER_PACKET_SHORTEST_PATHS", "ROUND_ROBIN"),
    )
    for size, size_label in sizes:
        for delay, delay_label in delays:
            control = f"s-{size_label}-d{delay_label}-flow-hash64"
            for label, routing_type, selector in strategies:
                packet = routing_type.startswith("PER_PACKET")
                cases.append(Case(
                    case_id=f"s-{size_label}-d{delay_label}-{label}",
                    block_id="spray-crossover",
                    role="control" if not packet else "treatment",
                    control_id=control,
                    topology_profile="micro-spray",
                    workload_profile="single-flow",
                    routing_type=routing_type,
                    selector=selector,
                    changed_variable="packet versus flow selection",
                    prediction=(
                        "Packet selection uses multiple paths; it wins for long symmetric transfers but "
                        "loses tail latency when one candidate has large delay."
                    ),
                    reason="Packet spray aggregates capacity but completion waits for delayed packets.",
                    falsification_signal=(
                        "The delayed path is used and no flow-size-by-delay FCT crossover appears."
                    ),
                    flow_size_bytes=size,
                    flow_count=1,
                    path_delay=delay,
                    observability="detailed",
                ))


def add_adaptive_cases(cases: list[Case]) -> None:
    strategies = (
        ("hash64", "HASH64"),
        ("rr", "ROUND_ROBIN"),
        ("adaptive", "ADAPTIVE"),
    )
    for ratio, ratio_label in ((1.0, "100"), (0.5, "50"), (0.25, "25")):
        for gap_ns, gap_label in ((0, "0"), (10_000, "10u")):
            control = f"a-screen-r{ratio_label}-g{gap_label}-hash64"
            for label, selector in strategies:
                cases.append(Case(
                    case_id=f"a-screen-r{ratio_label}-g{gap_label}-{label}",
                    block_id="adaptive-signal",
                    role="control" if selector == "HASH64" else "treatment",
                    control_id=control,
                    topology_profile="micro-adaptive",
                    workload_profile="adaptive-screen",
                    routing_type="PER_PACKET_SHORTEST_PATHS",
                    selector=selector,
                    changed_variable="selector under local queue signal",
                    prediction=(
                        "Adaptive improves as a persistent slow-path queue appears, but sparse empty-queue "
                        "traffic exposes first-candidate tie bias."
                    ),
                    reason="Adaptive observes local VOQ plus egress occupancy, not global path state.",
                    falsification_signal=(
                        "A persistent queue difference exists but adaptive does not reduce slow-path share or FCT."
                    ),
                    path_rate_ratio=ratio,
                    interarrival_gap_ns=gap_ns,
                    flow_size_bytes=256 * 1024,
                    flow_count=16,
                    observability="detailed",
                ))
    for seed in SEEDS:
        control = f"a-confirm-s{seed}-hash64"
        for label, selector in strategies:
            cases.append(Case(
                case_id=f"a-confirm-s{seed}-{label}",
                block_id="adaptive-signal",
                role="control" if selector == "HASH64" else "treatment",
                control_id=control,
                topology_profile="micro-adaptive",
                workload_profile="adaptive-confirm",
                routing_type="PER_PACKET_SHORTEST_PATHS",
                selector=selector,
                changed_variable="arrival seed at the pre-registered half-rate boundary",
                prediction="Adaptive's half-rate advantage remains visible across arrival-jitter seeds.",
                reason="A persistent local queue signal should be robust to small launch-order changes.",
                falsification_signal="The benefit changes sign across arrival seeds.",
                traffic_seed_kind="arrival_seed",
                traffic_seed=seed,
                path_rate_ratio=0.5,
                interarrival_gap_ns=0,
                flow_size_bytes=256 * 1024,
                flow_count=16,
                observability="detailed",
            ))


def add_ingress_cases(cases: list[Case]) -> None:
    for active in (1, 2, 4, 8):
        for seed in SEEDS:
            control = f"i-n{active}-s{seed}-hash64"
            for label, selector in (("hash64", "HASH64"), ("stripe", "INGRESS_PORT_STRIPE")):
                cases.append(Case(
                    case_id=f"i-n{active}-s{seed}-{label}",
                    block_id="ingress-entropy",
                    role="control" if selector == "HASH64" else "treatment",
                    control_id=control,
                    topology_profile="clos-ingress",
                    workload_profile="ingress-entropy",
                    routing_type="PER_FLOW_SHORTEST_PATHS",
                    selector=selector,
                    changed_variable="ingress-derived versus hash placement",
                    prediction="Stripe improves monotonically with active-ingress count and balance.",
                    reason="Ingress stripe maps inPort modulo candidate count and adds no other entropy.",
                    falsification_signal=(
                        "Stripe wins with one ingress, or remains materially worse with eight balanced ingresses."
                    ),
                    candidate_width=8,
                    traffic_seed_kind="pairing_seed",
                    traffic_seed=seed,
                    flow_size_bytes=256 * 1024,
                    flow_count=64,
                    active_ingress_count=active,
                    observability="balanced",
                ))


def add_path_scope_cases(cases: list[Case]) -> None:
    profiles = (
        ("flow-short", "PER_FLOW_SHORTEST_PATHS"),
        ("flow-all", "PER_FLOW_ALL_PATHS"),
        ("packet-short", "PER_PACKET_SHORTEST_PATHS"),
        ("packet-all", "PER_PACKET_ALL_PATHS"),
    )
    workloads = (("long", "single-long", 8 * 1024 * 1024, 1),
                 ("many", "many-medium", 256 * 1024, 32))
    for regime in ("neutral", "capacity", "latency"):
        for work_label, workload, size, count in workloads:
            flow_control = f"p-{regime}-{work_label}-flow-short"
            packet_control = f"p-{regime}-{work_label}-packet-short"
            for label, routing_type in profiles:
                packet = routing_type.startswith("PER_PACKET")
                all_paths = "ALL_PATHS" in routing_type
                cases.append(Case(
                    case_id=f"p-{regime}-{work_label}-{label}",
                    block_id="path-scope-region",
                    role="treatment" if all_paths else "control",
                    control_id=packet_control if packet else flow_control,
                    topology_profile=f"micro-scope-{regime}",
                    workload_profile=workload,
                    routing_type=routing_type,
                    selector="HASH64",
                    changed_variable="shortest-only versus all-path candidate scope",
                    prediction=(
                        "All paths wins when detours add useful capacity and loses for latency-sensitive "
                        "traffic when detour delay dominates; per-flow all-path needs multiple flows to spread."
                    ),
                    reason="RoutingType changes the candidate set without path-cost weighting in the selector.",
                    falsification_signal="No workload-by-detour interaction appears despite actual detour use.",
                    flow_size_bytes=size,
                    flow_count=count,
                    observability="detailed",
                ))


def add_transport_cases(cases: list[Case]) -> None:
    profiles = (
        ("flow-hash64", "PER_FLOW_SHORTEST_PATHS", "HASH64"),
        ("flow-crc32", "PER_FLOW_SHORTEST_PATHS", "CRC32"),
        ("flow-toeplitz", "PER_FLOW_SHORTEST_PATHS", "TOEPLITZ"),
        ("packet-rr", "PER_PACKET_SHORTEST_PATHS", "ROUND_ROBIN"),
        ("packet-adaptive", "PER_PACKET_SHORTEST_PATHS", "ADAPTIVE"),
        ("flow-stripe", "PER_FLOW_SHORTEST_PATHS", "INGRESS_PORT_STRIPE"),
        ("packet-all-hash64", "PER_PACKET_ALL_PATHS", "HASH64"),
    )
    for transport, op_type in (("CTP", "URMA_WRITE"), ("LDST", "MEM_STORE")):
        for label, routing_type, selector in profiles:
            cases.append(Case(
                case_id=f"t-{transport.lower()}-{label}",
                block_id="transport-transfer",
                role="treatment",
                control_id="historical-rmtp-semantic-baseline",
                topology_profile="micro-transport",
                workload_profile="transport-smoke",
                routing_type=routing_type,
                selector=selector,
                changed_variable="transport path",
                prediction="The legal strategy completes and preserves its path-selection signature.",
                reason="Routing selection is shared, while transport completion semantics differ.",
                falsification_signal="A legal profile aborts or reverses its expected flow/packet path signature.",
                flow_size_bytes=1024 * 1024,
                flow_count=1,
                transport=transport,
                op_type=op_type,
                observability="balanced",
            ))


def build_cases() -> list[Case]:
    cases: list[Case] = []
    add_hash_cases(cases)
    add_spray_cases(cases)
    add_adaptive_cases(cases)
    add_ingress_cases(cases)
    add_path_scope_cases(cases)
    add_transport_cases(cases)
    if len(cases) != 152:
        raise RuntimeError(f"expected 152 cases, got {len(cases)}")
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate case id in matrix")
    return cases


CASES = build_cases()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def micro_config(current: Case) -> tuple[list[str], list[str], list[int]]:
    rates = ["400Gbps"] * current.candidate_width
    delays = ["20ns"] * current.candidate_width
    metrics = [3] * current.candidate_width
    if current.topology_profile == "micro-spray":
        delays[-1] = current.path_delay
    elif current.topology_profile == "micro-adaptive":
        rates[0] = f"{int(400 * current.path_rate_ratio)}Gbps"
    elif current.topology_profile == "micro-scope-neutral":
        metrics = [3, 4, 4]
    elif current.topology_profile == "micro-scope-capacity":
        rates[0] = "100Gbps"
        metrics = [3, 4, 4]
    elif current.topology_profile == "micro-scope-latency":
        delays[1:] = ["20us", "20us"]
        metrics = [3, 4, 4]
    elif current.topology_profile != "micro-transport":
        raise ValueError(current.topology_profile)
    return rates, delays, metrics


def topology_script(current: Case) -> str:
    common = """#!/usr/bin/env python3
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
"""
    if current.topology_profile.startswith("clos-"):
        width = current.candidate_width
        body = f"""
for host in range(32):
    graph.add_netisim_host(host, forward_delay='1ns')
for switch in range(32, {36 + width}):
    graph.add_netisim_node(switch, forward_delay='1ns')
for host in range(32):
    graph.add_netisim_edge(host, 32 + host // 8, bandwidth='400Gbps', delay='20ns')
for leaf in range(32, 36):
    for spine in range(36, {36 + width}):
        graph.add_netisim_edge(leaf, spine, bandwidth='100Gbps', delay='20ns')
graph.build_graph_config()
graph.gen_compressed_route_table(path_finding_algo=all_shortest_paths, multiple_workers=1)
graph.write_config(include_transport=False)
"""
        return common + body

    rates, delays, metrics = micro_config(current)
    edge_lines = []
    for index, (rate, delay) in enumerate(zip(rates, delays)):
        mid = 4 + index
        edge_lines.append(f"graph.add_netisim_edge(2, {mid}, bandwidth='{rate}', delay='{delay}')")
        edge_lines.append(f"graph.add_netisim_edge(3, {mid}, bandwidth='{rate}', delay='{delay}')")
    ports = " ".join(str(index + 1) for index in range(current.candidate_width))
    metric_text = " ".join(str(value) for value in metrics)
    mid_routes = []
    for mid in range(4, 4 + current.candidate_width):
        mid_routes.extend((f"{mid},0,0,0,2", f"{mid},1,0,1,2"))
    body = f"""
for host in range(2):
    graph.add_netisim_host(host, forward_delay='1ns')
for switch in range(2, {4 + current.candidate_width}):
    graph.add_netisim_node(switch, forward_delay='1ns')
graph.add_netisim_edge(0, 2, bandwidth='1200Gbps', delay='20ns')
graph.add_netisim_edge(1, 3, bandwidth='1200Gbps', delay='20ns')
{chr(10).join(edge_lines)}
graph.build_graph_config()
graph.gen_compressed_route_table(path_finding_algo=all_shortest_paths, multiple_workers=1)
graph.write_config(include_transport=False)
(CASE_DIR / 'routing_table.csv').write_text('''nodeId,dstNodeId,dstPortId,outPorts,metrics
0,1,0,0,4
1,0,0,0,4
2,0,0,0,1
2,1,0,{ports},{metric_text}
3,0,0,{ports},{metric_text}
3,1,0,0,1
{chr(10).join(mid_routes)}
''', encoding='utf-8')
"""
    return common + body


def sampled_pairs(seed: int, count: int) -> list[tuple[int, int]]:
    population = [(src, dst) for src in range(16) for dst in range(16, 32)]
    return random.Random(seed).sample(population, count)


def traffic_rows(current: Case) -> list[list[str | int]]:
    rng = random.Random(current.traffic_seed)
    if current.workload_profile in {"hash-many", "hash-elephant"}:
        pairs = sampled_pairs(current.traffic_seed, current.flow_count)
        delays = ["10ns"] * current.flow_count
    elif current.workload_profile == "single-flow":
        pairs = [(0, 1)]
        delays = ["10ns"]
    elif current.workload_profile in {"adaptive-screen", "adaptive-confirm"}:
        pairs = [(0, 1)] * current.flow_count
        if current.workload_profile == "adaptive-confirm":
            delays = [f"{10 + rng.randrange(0, 1001)}ns" for _ in pairs]
        elif current.interarrival_gap_ns:
            delays = [f"{10 + index * current.interarrival_gap_ns}ns" for index in range(len(pairs))]
        else:
            delays = ["10ns"] * len(pairs)
    elif current.workload_profile == "ingress-entropy":
        sources = list(range(current.active_ingress_count))
        destinations = list(range(16, 24))
        pairs = [(sources[index % len(sources)], rng.choice(destinations))
                 for index in range(current.flow_count)]
        rng.shuffle(pairs)
        delays = ["10ns"] * len(pairs)
    elif current.workload_profile == "single-long":
        pairs = [(0, 1)]
        delays = ["10ns"]
    elif current.workload_profile == "many-medium":
        pairs = [(0, 1)] * current.flow_count
        delays = ["10ns"] * len(pairs)
    elif current.workload_profile == "transport-smoke":
        pairs = [(0, 1)]
        delays = ["10ns"]
    else:
        raise ValueError(current.workload_profile)
    return [
        [index, src, dst, current.flow_size_bytes, current.op_type, 7, delays[index], 0, ""]
        for index, (src, dst) in enumerate(pairs)
    ]


def write_traffic(case_dir: Path, current: Case) -> None:
    header = ["taskId", "sourceNode", "destNode", "dataSize(Byte)", "opType",
              "priority", "delay", "phaseId", "dependOnPhases"]
    with (case_dir / "traffic.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(traffic_rows(current))


def spec_text(current: Case) -> str:
    return f"""# Experiment Spec: {current.case_id}

## Goal

Map the suitability boundary for `{current.block_id}` without changing any other matrix dimension.

## Topology

- profile: `{current.topology_profile}`
- candidate_width: `{current.candidate_width}`
- path_delay: `{current.path_delay}`
- path_rate_ratio: `{current.path_rate_ratio}`
- transport_channel_mode: `on-demand`
- generator: `generate_topology.py`

## Workload

- profile: `{current.workload_profile}`
- flow_count: `{current.flow_count}`
- flow_size_bytes: `{current.flow_size_bytes}`
- operation: `{current.op_type}`
- transport: `{current.transport}`
- seed_kind: `{current.traffic_seed_kind}`
- seed: `{current.traffic_seed}`
- interarrival_gap_ns: `{current.interarrival_gap_ns}`
- active_ingress_count: `{current.active_ingress_count}`

## Routing Intent

- routing_type: `{current.routing_type}`
- multipath_selector: `{current.selector}`
- path_source: `manual-route-table` for micro profiles, `auto-path-finder` for Clos profiles

## Controlled Comparison

- role: `{current.role}`
- control_id: `{current.control_id}`
- changed_variable: `{current.changed_variable}`
- fixed_controls: topology profile, workload profile, flow control, transport mode, and observability

## Network Overrides

- flow_control: `CBFC`
- congestion_control: disabled
- retransmission: disabled; a drop or incomplete task is a safety failure

## Observability

- tier: `{current.observability}`
- measured: task statistics and per-port throughput
- trace-derived: branch usage, queue occupancy, and packet order when detailed trace is enabled

## Prediction

{current.prediction}

## Reason

{current.reason}

## Falsification Signal

{current.falsification_signal}

## Artifact Contract

The case must contain node, topology, routing, traffic, a full network-attribute snapshot,
console output, runlog traces, and parser summaries. Results are simulator-derived.
"""


def plan_text() -> str:
    return """# Routing Strategy Suitability Experiment Plan

## Claim

The current routing strategies do not have one global winner. Their best use depends on flow size,
path width, path delay and capacity heterogeneity, congestion persistence, ingress entropy, and
whether non-shortest capacity is worth its path stretch.

## Simulator Boundary

This experiment characterizes the current OpenUSim reference implementation. Routing algorithms
are implementation choices rather than UB-mandated performance policy, and results are not
physical-device measurements.

## Evaluation Rule

Use scenario-specific Pareto fronts instead of a weighted global score. A strategy is recommended
for a scenario cell only when it completes successfully, is non-dominated on that block's primary
metrics, and remains non-dominated in at least two of three key/pairing/arrival seeds where seeds
exist. Report minimax relative regret across cells as robustness evidence, not as a universal rank.

Primary metrics by block:

- hash and ingress: path Jain, maximum path share, p95 task duration, aggregate task goodput
- spray and path scope: p95/p99 task duration, aggregate goodput, PSN inversions per 1000 packets
- adaptive: p95 task duration, slow-path share, maximum/time-weighted queue occupancy
- transport transfer: completion and path-selection signature only; absolute FCT is not compared

## Experiment Blocks

1. `hash-robustness` (36): three hashes over widths 3/5/8 and three traffic-key seeds, plus
   four-elephant collision exposure at width 8.
2. `spray-crossover` (27): flow hash, packet hash, and packet RR over 16 KiB/256 KiB/8 MiB and
   20 ns/2 us/20 us slow-candidate delay.
3. `adaptive-signal` (27): hash, RR, and adaptive over rate ratios 1/1, 1/2, 1/4 and dense/sparse
   arrivals, followed by three pre-registered arrival seeds at the half-rate dense boundary.
4. `ingress-entropy` (24): hash versus ingress stripe over 1/2/4/8 active ingress ports and three
   pairing seeds.
5. `path-scope-region` (24): per-flow/per-packet shortest controls versus all-path treatments over
   neutral detours, capacity-gain detours, and latency-cost detours for one long or 32 medium flows.
6. `transport-transfer` (14): seven representative legal profiles on CTP and LDST. This is a
   transferability check, not a claim that RTP FCT values carry across transports.

## Fixed Controls

- current `next` branch release build and `scratch/ub-quick-example`
- on-demand transport-channel setup
- CBFC flow control, congestion control disabled, retransmission disabled
- identical topology and workload inside each comparison cell
- sequential execution only; no MTP and no concurrent build/test/simulation
- seed names describe generated traffic keys, pairings, or arrivals; they are not simulator RNG seeds

## Predictions And Falsification

- no hash is predicted to dominate all widths and key seeds
- packet selection is predicted to win long symmetric transfers and lose short high-delay-skew cells
- adaptive is predicted to require persistent local queue differences and to lose useful spreading
  when queues empty between packets
- ingress stripe is predicted to improve with ingress entropy and collapse with one ingress
- all-path scope is predicted to win only where detour capacity outweighs detour latency
- transport checks require direction/signature transfer, not equal absolute completion time

Every negative, flat, failed, skipped, or inconclusive row remains in the final analysis.

## Evidence Plan

- measured: `output/task_statistics.csv`, `output/throughput.csv`
- trace-derived: branch-port Tx bytes/packets, Jain/CV, queue max and time-weighted occupancy
- trace-derived where available: exact-record-deduplicated PSN arrival inversions
- log-derived: command, return code, timeout, and explicit failure text
- proxy only: duplicate PSN/NAK/SACK signals; no exact retransmission-rate claim

## Checkpoint Policy

`continue_full_matrix`. Each block starts with one control and one treatment pilot. Missing required
artifacts, route non-use that invalidates the comparison, abort, timeout, or incomplete tasks stop
that block and mark its remaining rows skipped. Prediction mismatch does not stop execution and may
not change the registered sweep. All cases run sequentially.

## Resource Budget

Upper bound: 152 cases, approximately 5-10 minutes simulation wall time and 300-600 MiB with
selective detailed trace and post-run gzip. A 1 GiB package-size safety limit stops further runs.

## Artifact Contract

The package contains this plan, immutable matrix, command manifest, durable run ledgers, per-case
specs, generated case inputs, compressed traces, parser summaries, row classifications, Pareto
tables, final recommendations, and limitations.
"""


def matrix_rows() -> list[dict]:
    rows = []
    for current in CASES:
        row = asdict(current)
        row.update({
            "case_dir": f"cases/{current.case_id}",
            "fixed_controls": "See experiment-plan.md and the control_id row.",
            "metric_checks": ["task_fct", "aggregate_goodput", "path_usage", "queue_evidence"],
            "expected_artifacts": [
                "console.log", "runlog/", "output/task_statistics.csv", "output/throughput.csv"
            ],
            "parallel_group": "sequential-only",
            "checkpoint_ids": [f"pilot-{current.block_id}"],
        })
        rows.append(row)
    return rows


def write_package_metadata() -> None:
    write_text(PACKAGE_ROOT / "experiment-plan.md", plan_text())
    rows = matrix_rows()
    write_text(PACKAGE_ROOT / "matrix.yaml", json.dumps({"cases": rows}, indent=2))
    manifest = {
        "execution_policy": "sequential-only",
        "checkpoint_policy": "continue_full_matrix with per-block safety pilots",
        "runner": "python3.12 ./ns3 run --no-build",
        "cases": [
            {
                "case_id": current.case_id,
                "command": (
                    "python3.12 ./ns3 run --no-build "
                    f"'scratch/ub-quick-example --case-path=scratch/20260715-routing-strategy-suitability/"
                    f"cases/{current.case_id}'"
                ),
            }
            for current in CASES
        ],
    }
    write_text(PACKAGE_ROOT / "command-manifest.yaml", json.dumps(manifest, indent=2))
    lines = [
        "# Run Ledger", "", "- branch: `next`", "- status: planned",
        "- checkpoint_policy: continue_full_matrix with per-block safety pilots",
        "- execution: sequential-only", "", "| case | block | status | return code |",
        "|---|---|---:|---:|",
    ]
    lines.extend(f"| {case.case_id} | {case.block_id} | pending | |" for case in CASES)
    write_text(PACKAGE_ROOT / "run-ledger.md", "\n".join(lines))
    for current in CASES:
        write_text(CASES_ROOT / current.case_id / "experiment-spec.md", spec_text(current))


def prepare_case(current: Case) -> None:
    case_dir = CASES_ROOT / current.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--generate-cases", action="store_true")
    args = parser.parse_args()
    if args.plan_only == args.generate_cases:
        parser.error("choose exactly one of --plan-only or --generate-cases")
    write_package_metadata()
    if args.plan_only:
        print(f"planned {len(CASES)} cases under {PACKAGE_ROOT}")
        return
    catalog, catalog_path = load_or_build_parameter_catalog()
    print(f"runtime catalog: {catalog_path} ({catalog['entry_count']} entries)")
    for index, current in enumerate(CASES, start=1):
        print(f"[{index:03d}/{len(CASES)}] generate {current.case_id}", flush=True)
        prepare_case(current)
    print(f"generated and gated {len(CASES)} cases")


if __name__ == "__main__":
    main()
