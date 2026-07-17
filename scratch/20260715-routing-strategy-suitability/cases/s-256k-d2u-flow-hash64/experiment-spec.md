# Experiment Spec: s-256k-d2u-flow-hash64

## Goal

Map the suitability boundary for `spray-crossover` without changing any other matrix dimension.

## Topology

- profile: `micro-spray`
- candidate_width: `3`
- path_delay: `2us`
- path_rate_ratio: `1.0`
- transport_channel_mode: `on-demand`
- generator: `generate_topology.py`

## Workload

- profile: `single-flow`
- flow_count: `1`
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
- control_id: `s-256k-d2u-flow-hash64`
- changed_variable: `packet versus flow selection`
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

Packet selection uses multiple paths; it wins for long symmetric transfers but loses tail latency when one candidate has large delay.

## Reason

Packet spray aggregates capacity but completion waits for delayed packets.

## Falsification Signal

The delayed path is used and no flow-size-by-delay FCT crossover appears.

## Artifact Contract

The case must contain node, topology, routing, traffic, a full network-attribute snapshot,
console output, runlog traces, and parser summaries. Results are simulator-derived.
