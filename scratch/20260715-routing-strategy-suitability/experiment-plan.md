# Routing Strategy Suitability Experiment Plan

## Claim

The current routing strategies do not have one global winner. Their best use depends on flow size,
path width, path delay and capacity heterogeneity, congestion persistence, ingress entropy, and
whether non-shortest capacity is worth its path stretch.

## Simulator Boundary

This experiment characterizes the current OpenUSim reference implementation. Routing algorithms
are implementation choices rather than UB-mandated performance policy, and results are not
physical-device measurements.

## Evaluation Rule

Use scenario-specific Pareto fronts instead of a weighted global score. A strategy is recommended
for a scenario cell only when it completes successfully, is non-dominated on that block's primary
metrics, and remains non-dominated in at least two of three key/pairing/arrival seeds where seeds
exist. Report minimax relative regret across cells as robustness evidence, not as a universal rank.

Primary metrics by block:

- hash and ingress: path Jain, maximum path share, p95 task duration, aggregate task goodput
- spray and path scope: p95/p99 task duration, aggregate goodput, PSN inversions per 1000 packets
- adaptive: p95 task duration, slow-path share, maximum/time-weighted queue occupancy
- transport transfer: completion and path-selection signature only; absolute FCT is not compared

## Experiment Blocks

1. `hash-robustness` (36): three hashes over widths 3/5/8 and three traffic-key seeds, plus
   four-elephant collision exposure at width 8.
2. `spray-crossover` (27): flow hash, packet hash, and packet RR over 16 KiB/256 KiB/8 MiB and
   20 ns/2 us/20 us slow-candidate delay.
3. `adaptive-signal` (27): hash, RR, and adaptive over rate ratios 1/1, 1/2, 1/4 and dense/sparse
   arrivals, followed by three pre-registered arrival seeds at the half-rate dense boundary.
4. `ingress-entropy` (24): hash versus ingress stripe over 1/2/4/8 active ingress ports and three
   pairing seeds.
5. `path-scope-region` (24): per-flow/per-packet shortest controls versus all-path treatments over
   neutral detours, capacity-gain detours, and latency-cost detours for one long or 32 medium flows.
6. `transport-transfer` (14): seven representative legal profiles on CTP and LDST. This is a
   transferability check, not a claim that RTP FCT values carry across transports.

## Fixed Controls

- current `next` branch release build and `scratch/ub-quick-example`
- on-demand transport-channel setup
- CBFC flow control, congestion control disabled, retransmission disabled
- identical topology and workload inside each comparison cell
- sequential execution only; no MTP and no concurrent build/test/simulation
- seed names describe generated traffic keys, pairings, or arrivals; they are not simulator RNG seeds

## Predictions And Falsification

- no hash is predicted to dominate all widths and key seeds
- packet selection is predicted to win long symmetric transfers and lose short high-delay-skew cells
- adaptive is predicted to require persistent local queue differences and to lose useful spreading
  when queues empty between packets
- ingress stripe is predicted to improve with ingress entropy and collapse with one ingress
- all-path scope is predicted to win only where detour capacity outweighs detour latency
- transport checks require direction/signature transfer, not equal absolute completion time

Every negative, flat, failed, skipped, or inconclusive row remains in the final analysis.

## Evidence Plan

- measured: `output/task_statistics.csv`, `output/throughput.csv`
- trace-derived: branch-port Tx bytes/packets, Jain/CV, queue max and time-weighted occupancy
- trace-derived where available: exact-record-deduplicated PSN arrival inversions
- log-derived: command, return code, timeout, and explicit failure text
- proxy only: duplicate PSN/NAK/SACK signals; no exact retransmission-rate claim

## Checkpoint Policy

`continue_full_matrix`. Each block starts with one control and one treatment pilot. Missing required
artifacts, route non-use that invalidates the comparison, abort, timeout, or incomplete tasks stop
that block and mark its remaining rows skipped. Prediction mismatch does not stop execution and may
not change the registered sweep. All cases run sequentially.

## Resource Budget

Upper bound: 152 cases, approximately 5-10 minutes simulation wall time and 300-600 MiB with
selective detailed trace and post-run gzip. A 1 GiB package-size safety limit stops further runs.

## Artifact Contract

The package contains this plan, immutable matrix, command manifest, durable run ledgers, per-case
specs, generated case inputs, compressed traces, parser summaries, row classifications, Pareto
tables, final recommendations, and limitations.
