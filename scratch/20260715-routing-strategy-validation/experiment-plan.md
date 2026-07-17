# Routing Strategy Validation Plan

## Claim

Every legal routing strategy must satisfy its routing semantics, and its expected advantage must
appear only in the topology and workload conditions that provide the mechanism it relies on.

## Simulator Boundary

This is an OpenUSim model validation. Results establish behavior of the current reference
implementation, not physical-device performance or UB specification-mandated algorithm quality.

## Blocks

1. `semantic`: four UB RT bit combinations on one shortest plus two non-shortest candidates.
2. `hash-many` / `hash-elephant`: static hash distribution with many flows and collision exposure.
3. `spray-equal` / `spray-delay`: per-flow, per-packet hash, and RR under equal/unequal delay.
4. `adaptive-hot` / `adaptive-sparse`: local queue avoidance and empty-queue tie bias.
5. `stripe-multi` / `stripe-single`: distributed ingress advantage and single-ingress collapse.
6. `all-hot` / `all-delay`: detour capacity advantage and path-stretch cost.
7. `coverage`: all 18 legal RoutingType/MultipathSelector combinations.
8. `smoke-ctp` / `smoke-ldst`: five representative strategies per transport path.

## Fixed Controls

- release build and `scratch/ub-quick-example` runner
- on-demand transport-channel creation
- CBFC flow control; congestion control disabled
- identical topology and workload within each control/treatment block
- RTP for directional and coverage blocks; CTP/LDST only for representative smoke
- detailed observability for directional blocks, balanced for coverage and smoke

## Evidence Plan

- measured: task statistics and per-port throughput
- trace-derived: path histogram, flow affinity, Jain index, CV, PSN arrival inversions
- trace-derived queue evidence: maximum and time-weighted occupancy where available
- log-derived: return code and explicit failure text

Exact duplicate AllPacketTrace records are removed by complete record identity. Same-PSN records
with different timestamps or paths remain visible as retransmission or duplicate-delivery proxies.

## Checkpoint Policy

`pause_for_user` is replaced by the user's approved end-to-end policy: semantic hard failures stop
the matrix immediately. Performance prediction mismatches are retained and execution continues.
All simulations run sequentially; no concurrent build or test is allowed.

## Artifact Contract

The package contains the plan, immutable matrix, command manifest, run ledger, per-case specs,
generated case inputs, console logs, traces, parser summaries, and final analysis tables.
