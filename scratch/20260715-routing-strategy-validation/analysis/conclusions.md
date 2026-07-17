# Routing Strategy Validation Conclusions

## Execution Summary

- Primary matrix: 56/56 successful after fixing the CTP service initialization-order bug.
- Semantic gate: passed before the remaining matrix executed.
- Legal matrix: all 18 canonical RoutingType/MultipathSelector combinations completed.
- Transport smoke: all five representative CTP and five representative LDST cases completed.
- Latency follow-up: 4/4 successful in a separate immutable package.

All task durations below are measured from `task_statistics.csv`. Path distributions, Jain index,
queue occupancy, and PSN arrival inversions are trace-derived. They are simulator results, not
physical-device measurements.

## Prediction Versus Actual

| Strategy block | Status | Strongest evidence | Interpretation |
|---|---|---|---|
| RoutingType bits | matched | shortest cases used only port 1; per-flow all used one path; per-packet all used ports 1/2/3 | Flow/packet scope and shortest/all scope behave as independent RT bits. |
| Static hash, many flows | partially matched | HASH64 Jain 0.928; CRC32 0.500; Toeplitz 1.000 | All remained per-flow affine, but this structured workload exposed strong CRC32 low-bit/modulo correlation. |
| Static hash, four elephants | matched | HASH64 and Toeplitz used 4/8 paths; CRC32 used 1/8 | Few elephant flows expose deterministic collision sensitivity; no hash is congestion-aware. |
| Per-flow vs per-packet, equal paths | matched | mean FCT 171.42 us per-flow, 59.92 us packet hash, 57.70 us RR | Packet spray aggregated three 400 Gbps paths and reduced long-flow FCT by 65-66%. |
| Unequal-delay long flow | partially matched | packet-hash FCT 63.45 us and RR 63.06 us versus 59.92/57.70 us at equal delay | Delay imposed a cost, but aggregate bandwidth still dominated an 8 MiB transfer. |
| Adaptive persistent hotspot | matched | slow-path packets 678 -> 275; slow-path max queue 918,838 -> 301,024 bytes; FCT 227.13 -> 92.47 us | Local VOQ plus egress occupancy successfully steered traffic away from the 100 Gbps path. |
| Adaptive sparse traffic | matched | RR distribution 22/21/21; adaptive 64/0/0; equal FCT | When queues drain between packets, first-candidate tie breaking collapses adaptive routing to one path. |
| Ingress stripe, distributed ingress | matched | stripe Jain 1.000 vs hash 0.571; p95 FCT 342.87 vs 1027.24 us | Stripe is strong when ingress ports already provide uniformly distributed entropy. |
| Ingress stripe, single ingress | matched | stripe Jain 0.125 vs hash 0.444; p95 FCT 1369.60 vs 514.16 us | One ingress maps every flow to the same uplink, increasing p95 FCT by 166%. |
| All paths, congested shortest | matched | FCT 2739.37 -> 908.60 us | High-rate non-shortest paths can recover capacity when the only shortest path is slow. |
| All paths, 2 us detours and 8 MiB flow | mismatched | FCT 171.42 -> 66.35 us despite path stretch | The original disadvantage case remained bandwidth-dominated; this negative result is retained. |
| Short-flow latency follow-up | matched | packet spray p95 0.645 -> 80.455 us; all paths p95 0.645 -> 80.511 us | With 16 KiB sparse tasks and 20 us detours, latency dominates and exposes the expected spray/detour cost. |

## Strategy Boundaries

- `HASH64`, `CRC32`, and `TOEPLITZ` are deterministic mapping choices, not congestion policies.
  The observed ranking applies to this structured address/key set and eight-way modulo only.
- `ROUND_ROBIN` gives nearly exact packet-count balance, but it cannot distinguish a slow path from
  a fast one and produces PSN arrival inversions whenever packets use independent queues.
- `ADAPTIVE` is effective only when its local queue snapshot contains a useful difference. It has no
  global path state, cost weighting, prediction, or tie spreading.
- `INGRESS_PORT_STRIPE` is best treated as topology-derived flow placement. Its quality is bounded by
  the ingress-port distribution, and a single ingress is its canonical failure case.
- `ALL_PATHS` is a capacity option, not a generally faster mode. The current selector sees shortest
  and non-shortest candidates without path-length weighting, so workload size and detour latency
  decide whether extra capacity or path stretch dominates.
- `PER_PACKET` is advantageous for long bandwidth-bound transfers on symmetric paths. For short
  latency-sensitive transfers, one delayed candidate can dominate completion time.

## Implementation Finding

CTP round-robin and adaptive initially aborted before traffic started. `UbCtpTransportService` was
validating its unbound per-flow default during node/switch initialization, before `UbApp` assigned
the configured per-packet policy. The redundant internal validation was removed. Configuration-file
validation remains at `UbUtils::SetComponentsAttribute()`, while explicit CTP policy assignments and
entity policies still validate immediately.

## Evidence Limits

- `throughput.csv` is per-port Rx/Tx evidence and is not used as task completion throughput.
- PSN inversion is a trace-derived ordering signal, not an exact retransmission count.
- The default traces do not expose a complete retransmission counter.
- Queue means are time-weighted over observed queue events; maxima are direct trace maxima.
- Results establish current OpenUSim reference-model behavior, not UB-mandated algorithm superiority.
