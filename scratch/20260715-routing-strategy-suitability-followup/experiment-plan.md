# Routing Strategy Suitability Follow-up Plan

## Claim

Two validity gaps in the main 152-case matrix need bounded follow-up before final recommendations:
256 KiB sparse tasks do not guarantee empty queues between packets, and repeated tasks on one
endpoint pair do not provide independent per-flow hash keys.

## Blocks

1. `adaptive-single-packet-sparse` (27): 64 one-packet tasks, rate ratios 1/1, 1/2, 1/4,
   interarrival gaps 1/10/100 us, and HASH64/RR/ADAPTIVE.
2. `per-flow-all-distinct-keys` (18): 32 independently paired flows, three pairing seeds,
   neutral/capacity/latency detour regimes, and per-flow shortest/all-path routing.

## Controls And Evidence

Each row changes one routing choice inside a fixed topology/workload cell. Adaptive is compared to
HASH64 and RR. Per-flow all-path is compared to per-flow shortest. Required evidence is task FCT,
aggregate goodput, branch-port bytes, queue occupancy, and detailed packet paths for sparse cases.

## Checkpoint Policy

`continue_full_matrix`; one pilot pair per block, block safety stop on abort, incomplete task,
missing artifact, or route non-use. Prediction mismatch continues and remains visible.

## Artifact Contract

The package contains 45 immutable rows, commands, ledgers, generated case inputs, compressed traces,
analysis tables, and a final statement of whether each evidence gap was closed.
