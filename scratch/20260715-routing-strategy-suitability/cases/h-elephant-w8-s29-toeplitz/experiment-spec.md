# Experiment Spec: h-elephant-w8-s29-toeplitz

## Goal

Map the suitability boundary for `hash-robustness` without changing any other matrix dimension.

## Topology

- profile: `clos-hash`
- candidate_width: `8`
- path_delay: `20ns`
- path_rate_ratio: `1.0`
- transport_channel_mode: `on-demand`
- generator: `generate_topology.py`

## Workload

- profile: `hash-elephant`
- flow_count: `4`
- flow_size_bytes: `16777216`
- operation: `URMA_WRITE`
- transport: `RTP`
- seed_kind: `traffic_key_seed`
- seed: `29`
- interarrival_gap_ns: `0`
- active_ingress_count: `0`

## Routing Intent

- routing_type: `PER_FLOW_SHORTEST_PATHS`
- multipath_selector: `TOEPLITZ`
- path_source: `manual-route-table` for micro profiles, `auto-path-finder` for Clos profiles

## Controlled Comparison

- role: `treatment`
- control_id: `h-elephant-w8-s29-hash64`
- changed_variable: `multipath selector`
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

Few elephant flows expose collision sensitivity without a universal hash winner.

## Reason

Four deterministic flow keys cannot reliably occupy all eight candidates.

## Falsification Signal

The same selector wins every seed with no collision-sensitive tail penalty.

## Artifact Contract

The case must contain node, topology, routing, traffic, a full network-attribute snapshot,
console output, runlog traces, and parser summaries. Results are simulator-derived.
