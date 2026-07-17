# Routing Strategy Selection

<reference-hint>
<use-when>Use this reference when choosing or comparing per-flow/per-packet routing, packet spray, hash, round-robin, adaptive, ingress stripe, or path scope.</use-when>
<focus>Routing-type and selector compatibility, workload/topology fit, and the evidence required for path balance, completion, queues, and ordering claims.</focus>
<keywords>RoutingType, MultipathSelector, per-flow, per-packet, packet spray, hash, CRC32, Toeplitz, round robin, adaptive, ingress port stripe, all paths, shortest paths</keywords>
</reference-hint>

## Contents

- Core judgment
- Profile selection
- Selector guidance
- Candidate scope
- Evidence contract
- Reference evidence
- Implementation sources

## Core Judgment

There is no global best routing profile. Choose a profile from four facts:

1. whether selection must preserve one path per flow or may change per packet
2. whether the candidate set should contain only minimum-metric paths or all configured paths
3. whether the selector has a useful signal: representative canonical routing keys, the existing
   per-packet Lb/sport change, live queue load, or diverse ingress identity
4. whether the transport can tolerate the resulting packet ordering behavior

`RoutingType` combines the first two facts. `MultipathSelector` chooses within that candidate set.
They are related but not a free Cartesian product: hash selectors support per-flow and per-packet;
`ROUND_ROBIN` and `ADAPTIVE` require per-packet; `INGRESS_PORT_STRIPE` requires per-flow.

## Profile Selection

| Condition | Recommended starting profile | Main risk |
|---|---|---|
| Conservative default | `PER_FLOW_SHORTEST_PATHS + HASH64` | Hash collisions for the actual key population |
| Long transfer over symmetric equal-cost paths | `PER_PACKET_SHORTEST_PATHS + ROUND_ROBIN` | Packet reorder and transport buffering |
| Short transfer or meaningful path-delay skew | `PER_FLOW_SHORTEST_PATHS + validated hash` | Reduced capacity aggregation |
| Persistent unequal queue pressure or path rate | `PER_PACKET_SHORTEST_PATHS + ADAPTIVE` | No useful signal after queues drain |
| Diverse, balanced ingress identity | `PER_FLOW_SHORTEST_PATHS + INGRESS_PORT_STRIPE` | Collapse when ingress cardinality is small |
| Useful detour capacity across many independent flows | `PER_FLOW_ALL_PATHS + validated hash` | Slow or congested detours admitted into the set |
| Useful detour capacity for one dominant flow | `PER_PACKET_ALL_PATHS + ROUND_ROBIN` or `ADAPTIVE` | Reorder plus path heterogeneity |

Treat the table as an experiment starting point, not a deployment guarantee.

## Selector Guidance

### HASH64, CRC32, and TOEPLITZ

All three are deterministic full-key selectors. The current implementation hashes the complete
17-byte routing key once; do not add a second entropy or packet-ordinal field in the model. The
winner can change with candidate count and key distribution, especially for a small number of
elephant flows. Use representative keys and at least several reproducible key seeds before choosing
among them. Keep HASH64 as the conservative default only when no workload-specific evidence exists.

### ROUND_ROBIN

Use for deliberate packet spray over symmetric paths. It gives predictable candidate cycling and
usually tighter path balance than packet hash. It does not inspect latency, capacity, or queue
state, so it can send the same fraction onto a slow path and expose packet reorder.

### ADAPTIVE

Use when per-packet branch load is persistent enough to distinguish candidates. In the reference
implementation, empty or tied queues select the first minimum-load candidate; fully drained sparse
traffic can therefore concentrate rather than spread. Validate both queue evidence and path share,
not FCT alone.

### INGRESS_PORT_STRIPE

Use when ingress port identity has sufficient entropy and correlates with the desired output
distribution. Its path cardinality cannot exceed active ingress cardinality. Local injection falls
back to HASH64, so a host-originated workload does not gain stripe entropy merely by selecting this
mode.

## Candidate Scope

`SHORTEST_PATHS` is the safer default when candidate latency is heterogeneous or when route metrics
already express the intended policy. `ALL_PATHS` can aggregate non-shortest capacity, but only if
the extra capacity is worth its latency and congestion cost. Per-flow all-path needs multiple
independent flow keys to spread; per-packet all-path can spread one flow but adds ordering risk.

Do not infer candidate quality from graph reachability alone. Validate actual branch use and compare
completion metrics against a shortest-only control.

## Evidence Contract

For a routing recommendation, collect:

- measured `task_statistics.csv` for task FCT and task-level throughput
- trace-derived branch-port bytes for path use, Jain index, and maximum path share
- queue trace evidence for Adaptive and congestion claims
- direct packet-order evidence for packet-spray reorder claims
- failed, flat, negative, and partially matched cases, not only winners

`throughput.csv` is per-port Rx/Tx evidence, not an end-to-end task metric. PSN adjacent inversions
are an ordering proxy, not a precise retransmission count. Follow `throughput-evidence.md`,
`queue-backpressure-vs-topology.md`, and `controlled-experiment-method.md` for those boundaries.

## Reference Evidence

The reusable recommendations above were validated on the current OpenUSim reference implementation
with 197 successful controlled cases across hash width/key seeds, flow sizes, path delay/rate
heterogeneity, arrival density, ingress cardinality, candidate scope, and RTP/CTP/LDST profiles.
The durable experiment conclusions are in:

```text
scratch/20260715-routing-strategy-suitability/analysis/conclusions.md
```

This evidence characterizes the simulator implementation. It is not UB specification policy and is
not a physical-device measurement.

## Implementation Sources

- `src/unified-bus/model/ub-datatype.h`: wire-aligned `RoutingType` values and compatibility helpers
- `src/unified-bus/model/protocol/ub-routing-process.cc`: candidate selection and selector dispatch
- `src/unified-bus/test/ub-test.cc`: wire encoding, selector behavior, compatibility, and routing-key tests
