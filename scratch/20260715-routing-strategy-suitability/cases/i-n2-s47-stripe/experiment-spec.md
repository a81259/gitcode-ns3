# Experiment Spec: i-n2-s47-stripe

## Goal

Map the suitability boundary for `ingress-entropy` without changing any other matrix dimension.

## Topology

- profile: `clos-ingress`
- candidate_width: `8`
- path_delay: `20ns`
- path_rate_ratio: `1.0`
- transport_channel_mode: `on-demand`
- generator: `generate_topology.py`

## Workload

- profile: `ingress-entropy`
- flow_count: `64`
- flow_size_bytes: `262144`
- operation: `URMA_WRITE`
- transport: `RTP`
- seed_kind: `pairing_seed`
- seed: `47`
- interarrival_gap_ns: `0`
- active_ingress_count: `2`

## Routing Intent

- routing_type: `PER_FLOW_SHORTEST_PATHS`
- multipath_selector: `INGRESS_PORT_STRIPE`
- path_source: `manual-route-table` for micro profiles, `auto-path-finder` for Clos profiles

## Controlled Comparison

- role: `treatment`
- control_id: `i-n2-s47-hash64`
- changed_variable: `ingress-derived versus hash placement`
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

Stripe improves monotonically with active-ingress count and balance.

## Reason

Ingress stripe maps inPort modulo candidate count and adds no other entropy.

## Falsification Signal

Stripe wins with one ingress, or remains materially worse with eight balanced ingresses.

## Artifact Contract

The case must contain node, topology, routing, traffic, a full network-attribute snapshot,
console output, runlog traces, and parser summaries. Results are simulator-derived.
