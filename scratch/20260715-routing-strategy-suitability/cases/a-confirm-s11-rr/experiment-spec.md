# Experiment Spec: a-confirm-s11-rr

## Goal

Map the suitability boundary for `adaptive-signal` without changing any other matrix dimension.

## Topology

- profile: `micro-adaptive`
- candidate_width: `3`
- path_delay: `20ns`
- path_rate_ratio: `0.5`
- transport_channel_mode: `on-demand`
- generator: `generate_topology.py`

## Workload

- profile: `adaptive-confirm`
- flow_count: `16`
- flow_size_bytes: `262144`
- operation: `URMA_WRITE`
- transport: `RTP`
- seed_kind: `arrival_seed`
- seed: `11`
- interarrival_gap_ns: `0`
- active_ingress_count: `0`

## Routing Intent

- routing_type: `PER_PACKET_SHORTEST_PATHS`
- multipath_selector: `ROUND_ROBIN`
- path_source: `manual-route-table` for micro profiles, `auto-path-finder` for Clos profiles

## Controlled Comparison

- role: `treatment`
- control_id: `a-confirm-s11-hash64`
- changed_variable: `arrival seed at the pre-registered half-rate boundary`
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

Adaptive's half-rate advantage remains visible across arrival-jitter seeds.

## Reason

A persistent local queue signal should be robust to small launch-order changes.

## Falsification Signal

The benefit changes sign across arrival seeds.

## Artifact Contract

The case must contain node, topology, routing, traffic, a full network-attribute snapshot,
console output, runlog traces, and parser summaries. Results are simulator-derived.
