# Experiment Spec: t-ctp-flow-hash64

## Goal

Map the suitability boundary for `transport-transfer` without changing any other matrix dimension.

## Topology

- profile: `micro-transport`
- candidate_width: `3`
- path_delay: `20ns`
- path_rate_ratio: `1.0`
- transport_channel_mode: `on-demand`
- generator: `generate_topology.py`

## Workload

- profile: `transport-smoke`
- flow_count: `1`
- flow_size_bytes: `1048576`
- operation: `URMA_WRITE`
- transport: `CTP`
- seed_kind: `none`
- seed: `0`
- interarrival_gap_ns: `0`
- active_ingress_count: `0`

## Routing Intent

- routing_type: `PER_FLOW_SHORTEST_PATHS`
- multipath_selector: `HASH64`
- path_source: `manual-route-table` for micro profiles, `auto-path-finder` for Clos profiles

## Controlled Comparison

- role: `treatment`
- control_id: `historical-rmtp-semantic-baseline`
- changed_variable: `transport path`
- fixed_controls: topology profile, workload profile, flow control, transport mode, and observability

## Network Overrides

- flow_control: `CBFC`
- congestion_control: disabled
- retransmission: disabled; a drop or incomplete task is a safety failure

## Observability

- tier: `balanced`
- measured: task statistics and per-port throughput
- trace-derived: branch usage, queue occupancy, and packet order when detailed trace is enabled

## Prediction

The legal strategy completes and preserves its path-selection signature.

## Reason

Routing selection is shared, while transport completion semantics differ.

## Falsification Signal

A legal profile aborts or reverses its expected flow/packet path signature.

## Artifact Contract

The case must contain node, topology, routing, traffic, a full network-attribute snapshot,
console output, runlog traces, and parser summaries. Results are simulator-derived.
