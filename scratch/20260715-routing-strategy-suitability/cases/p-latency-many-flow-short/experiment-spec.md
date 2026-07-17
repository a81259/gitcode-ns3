# Experiment Spec: p-latency-many-flow-short

## Goal

Map the suitability boundary for `path-scope-region` without changing any other matrix dimension.

## Topology

- profile: `micro-scope-latency`
- candidate_width: `3`
- path_delay: `20ns`
- path_rate_ratio: `1.0`
- transport_channel_mode: `on-demand`
- generator: `generate_topology.py`

## Workload

- profile: `many-medium`
- flow_count: `32`
- flow_size_bytes: `262144`
- operation: `URMA_WRITE`
- transport: `RTP`
- seed_kind: `none`
- seed: `0`
- interarrival_gap_ns: `0`
- active_ingress_count: `0`

## Routing Intent

- routing_type: `PER_FLOW_SHORTEST_PATHS`
- multipath_selector: `HASH64`
- path_source: `manual-route-table` for micro profiles, `auto-path-finder` for Clos profiles

## Controlled Comparison

- role: `control`
- control_id: `p-latency-many-flow-short`
- changed_variable: `shortest-only versus all-path candidate scope`
- fixed_controls: topology profile, workload profile, flow control, transport mode, and observability

## Network Overrides

- flow_control: `CBFC`
- congestion_control: disabled
- retransmission: disabled; a drop or incomplete task is a safety failure

## Observability

- tier: `detailed`
- measured: task statistics and per-port throughput
- trace-derived: branch usage, queue occupancy, and packet order when detailed trace is enabled

## Prediction

All paths wins when detours add useful capacity and loses for latency-sensitive traffic when detour delay dominates; per-flow all-path needs multiple flows to spread.

## Reason

RoutingType changes the candidate set without path-cost weighting in the selector.

## Falsification Signal

No workload-by-detour interaction appears despite actual detour use.

## Artifact Contract

The case must contain node, topology, routing, traffic, a full network-attribute snapshot,
console output, runlog traces, and parser summaries. Results are simulator-derived.
