# Routing Strategy Suitability Conclusions

## Evidence Set

- main matrix: 152/152 successful, 148 matched, 4 partially matched
- bounded follow-up: 45/45 successful, 45 matched
- combined: 197 successful, 193 matched, 4 partially matched, no mismatch,
  inconclusive, failed, or skipped rows
- execution: sequential release-build runs on `next`, CBFC enabled, congestion control and
  retransmission disabled, on-demand transport channels
- evidence: measured task completion statistics plus trace-derived branch use, queue occupancy,
  and PSN adjacent inversions

The four partially matched rows remain visible. Three came from the original 256 KiB sparse
Adaptive cases, where a task was still a burst and did not prove that queues drained between
packets. The follow-up replaced that assumption with 64 one-packet tasks and directly checked queue
state before each arrival.

## Selection Table

| Scenario | Preferred starting point | Why | Avoid or validate |
|---|---|---|---|
| General conservative baseline | `PER_FLOW_SHORTEST_PATHS + HASH64` | Preserves flow affinity, excludes detours, and uses the implementation default selector | It is a baseline, not the best hash for every key set |
| Symmetric equal-cost paths, long transfers | `PER_PACKET_SHORTEST_PATHS + ROUND_ROBIN` | Near-even path use and the strongest long-flow FCT in the spray sweep | Validate packet ordering and transport tolerance |
| Short transfers or large path-delay skew | `PER_FLOW_SHORTEST_PATHS + HASH64` | Avoids paying slow-path latency and packet-order cost | Packet spray crossed from benefit to loss as skew grew |
| Persistent congestion with unequal path rates | `PER_PACKET_SHORTEST_PATHS + ADAPTIVE` | Dense half/quarter-rate cells reduced p95 FCT versus static hash and RR | Needs a live queue/load signal; sparse drained queues collapse to first-candidate bias |
| Uniform, high-cardinality ingress traffic | `PER_FLOW_SHORTEST_PATHS + INGRESS_PORT_STRIPE` | Eight active ingress ports produced perfect path Jain and lower p95 FCT | One or few ingress ports collapse onto too few paths |
| Useful non-shortest capacity, many independent flows | `PER_FLOW_ALL_PATHS + validated hash` | Distinct flow keys used all three paths and improved p95 FCT by 56-81% | Exclude detours whose latency cost dominates capacity gain |
| Useful non-shortest capacity, one dominant flow | `PER_PACKET_ALL_PATHS + ROUND_ROBIN` or `ADAPTIVE` | Per-packet selection can aggregate candidates for one flow | Reordering and path heterogeneity become first-order risks |
| Structured or deployment-specific flow keys | Sweep `HASH64`, `CRC32`, and `TOEPLITZ` | Winner changed with width, seed, and elephant key set | Do not declare a universal hash winner from one traffic sample |

## Stable Findings

### Hash selectors

There is no universal winner. CRC32 won most 64-flow cells, but HASH64 or Toeplitz won selected
5-way and 8-way cells, and the four-elephant winner changed with the generated key seed. Hash choice
must therefore be validated against candidate width and representative deployment keys. HASH64 is
the clean default baseline because it is the implementation default, not because the matrix proves
global superiority.

### Packet spray

On equal-delay paths, packet HASH64 and RR reduced 8 MiB FCT from about 171 us to 58-60 us. With a
20 us slow-path delay, the same 8 MiB packet strategies rose to about 181-183 us and lost to the
171 us per-flow control. For 16 KiB and 256 KiB transfers, even 2 us skew was already enough to make
packet spray slower than the per-flow control. RR generally spread load more evenly than packet
hash, but both can reorder packets; the PSN inversion metric is ordering evidence, not a precise
retransmission count.

### Adaptive

With dense traffic and one path at half rate, Adaptive p95 FCT was about 38.5 us versus 53.5 us for
HASH64 and 59.0 us for RR; three arrival seeds reproduced the direction. At quarter rate, Adaptive
was about 54.7 us versus 106.5 us and 114.1 us. In the one-packet follow-up, every branch queue was
empty before every later arrival and Adaptive selected the first tied candidate for 100% of data
packets across all nine rate/gap cells. Adaptive is therefore a congestion-responsive choice, not
a general-purpose balancing replacement.

### Ingress stripe

The strategy is only as diverse as the ingress signal. With one active ingress, stripe p95 FCT was
about 1355 us versus about 470 us for hash. With eight active ingress ports, stripe reached Jain
1.0 and about 172 us p95 versus hash Jain around 0.87 and about 273 us p95. It is appropriate when
ingress identity is both diverse and well correlated with the desired egress distribution.

### Candidate path scope

`ALL_PATHS` is valuable only when the extra candidates are useful. In the distinct-key follow-up,
per-flow all-path used all three branches for every pairing seed. It improved p95 FCT by 56-59% in
the neutral regime and 63-81% when the shortest branch was rate-limited, but worsened p95 by 28-34%
when two detours added 20 us. Candidate-set construction must therefore remain a separate routing
decision from the selector used inside that set.

### Transport transfer

All 14 CTP/LDST representative profiles completed. Per-flow profiles kept a single-path signature;
RR, Adaptive, and per-packet all-path profiles used three paths. This supports semantic transfer of
the routing profiles, but it does not claim equal absolute FCT across RTP, CTP, and LDST.

## Boundaries

- These are OpenUSim reference-implementation simulation results, not UB-mandated policy or
  physical-device measurements.
- Retransmission was disabled, so the matrix does not quantify recovery cost under packet reorder.
- PSN adjacent inversions are a trace-derived ordering signal, not an exact out-of-order depth or
  retransmission rate.
- The tested dimensions are broad but finite; new topology families and deployment key
  distributions still require a bounded validation sweep.

## Reproduction

Main package:

```text
scratch/20260715-routing-strategy-suitability/
```

Follow-up package:

```text
scratch/20260715-routing-strategy-suitability-followup/
```
