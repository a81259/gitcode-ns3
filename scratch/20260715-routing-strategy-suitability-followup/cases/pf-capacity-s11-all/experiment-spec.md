# Follow-up Experiment Spec: pf-capacity-s11-all

## Goal

Close the comparison-validity gap identified by the 152-case suitability matrix.

## Topology And Workload

- topology_profile: `clos-distinct-capacity`
- transport_channel_mode: `on-demand`
- path_rate_ratio: `1.0`
- interarrival_gap_ns: `0`
- pairing_seed: `11`
- workload: `64 one-packet tasks` for sparse adaptive, `32 distinct endpoint pairs` for per-flow scope

## Routing Intent

- routing_type: `PER_FLOW_ALL_PATHS`
- multipath_selector: `HASH64`

## Controlled Comparison

- role: `treatment`
- control_id: `pf-capacity-s11-short`
- changed_variable: `shortest-only versus all-path scope across distinct flow keys`

## Prediction

Distinct per-flow keys spread across the full candidate set; capacity detours help and high-delay detours hurt relative to shortest-only routing.

## Falsification Signal

All-path traffic uses no detour across three pairing seeds, or no regime-dependent performance sign change appears despite detour use.

## Evidence

Task statistics are measured. Path use, queue state, and packet order are trace-derived. Runs are
sequential with CBFC, congestion control disabled, retransmission disabled, and on-demand TP setup.
