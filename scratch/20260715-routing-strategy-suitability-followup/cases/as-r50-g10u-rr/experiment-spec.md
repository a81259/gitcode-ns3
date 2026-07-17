# Follow-up Experiment Spec: as-r50-g10u-rr

## Goal

Close the comparison-validity gap identified by the 152-case suitability matrix.

## Topology And Workload

- topology_profile: `micro-sparse`
- transport_channel_mode: `on-demand`
- path_rate_ratio: `0.5`
- interarrival_gap_ns: `10000`
- pairing_seed: `0`
- workload: `64 one-packet tasks` for sparse adaptive, `32 distinct endpoint pairs` for per-flow scope

## Routing Intent

- routing_type: `PER_PACKET_SHORTEST_PATHS`
- multipath_selector: `ROUND_ROBIN`

## Controlled Comparison

- role: `treatment`
- control_id: `as-r50-g10u-hash64`
- changed_variable: `selector under one-packet sparse arrivals`

## Prediction

As the interarrival gap drains every queue, adaptive loses congestion signal and concentrates on the first tied candidate.

## Falsification Signal

Queues are empty before each task but adaptive remains evenly spread.

## Evidence

Task statistics are measured. Path use, queue state, and packet order are trace-derived. Runs are
sequential with CBFC, congestion control disabled, retransmission disabled, and on-demand TP setup.
