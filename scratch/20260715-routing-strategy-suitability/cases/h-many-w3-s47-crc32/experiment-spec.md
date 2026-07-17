# Experiment Spec: h-many-w3-s47-crc32

## Goal

Map the suitability boundary for `hash-robustness` without changing any other matrix dimension.

## Topology

- profile: `clos-hash`
- candidate_width: `3`
- path_delay: `20ns`
- path_rate_ratio: `1.0`
- transport_channel_mode: `on-demand`
- generator: `generate_topology.py`

## Workload

- profile: `hash-many`
- flow_count: `64`
- flow_size_bytes: `262144`
- operation: `URMA_WRITE`
- transport: `RTP`
- seed_kind: `traffic_key_seed`
- seed: `47`
- interarrival_gap_ns: `0`
- active_ingress_count: `0`

## Routing Intent

- routing_type: `PER_FLOW_SHORTEST_PATHS`
- multipath_selector: `CRC32`
- path_source: `manual-route-table` for micro profiles, `auto-path-finder` for Clos profiles

## Controlled Comparison

- role: `treatment`
- control_id: `h-many-w3-s47-hash64`
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

Per-flow affinity holds; distribution quality varies with selector, candidate width, and the sampled structured key set.

## Reason

Static hashes map the same 17-byte routing key deterministically.

## Falsification Signal

A flow changes uplink, or one selector Pareto-dominates every width and key seed.

## Artifact Contract

The case must contain node, topology, routing, traffic, a full network-attribute snapshot,
console output, runlog traces, and parser summaries. Results are simulator-derived.
