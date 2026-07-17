# Routing Suitability Follow-up Results

## Execution

- cases: 45 success, 0 failed, 0 skipped
- classifications: {"matched": 45}
- evidence boundary: OpenUSim reference-implementation simulation, not hardware measurement

## Adaptive With Fully Drained Queues

- adaptive max-path share range: 1.000 to 1.000
- round-robin max-path share range: 0.344 to 0.344
- adaptive empty-before-arrival fraction: 1.000
- conclusion: after every branch queue drains, adaptive repeatedly selects the first tied candidate; it needs a live load difference to express its advantage.
- aggregate goodput is intentionally idle-gap dominated in this block and is not used for selector ranking.

## Per-flow All-path With Distinct Keys

| regime | seed | detour share | p95 FCT delta vs shortest | goodput delta vs shortest |
|---|---:|---:|---:|---:|
| neutral | 11 | 62.5% | -59.3% | 145.4% |
| neutral | 29 | 71.9% | -59.3% | 145.4% |
| neutral | 47 | 81.2% | -56.2% | 128.0% |
| capacity | 11 | 62.5% | -62.5% | 166.1% |
| capacity | 29 | 71.9% | -71.8% | 254.1% |
| capacity | 47 | 81.2% | -81.2% | 429.8% |
| latency | 11 | 62.5% | 27.6% | -21.6% |
| latency | 29 | 71.9% | 27.6% | -21.6% |
| latency | 47 | 81.2% | 34.1% | -25.4% |

- all-path used all three candidates for every pairing seed.
- neutral and capacity-gain regimes improved p95 FCT; 20 us detours worsened it.
- conclusion: per-flow all-path can aggregate capacity across independent flow keys, but candidate-set scope must exclude paths whose latency cost dominates their capacity value.

## Validity

Both named validity gaps from the 152-case matrix are closed. The follow-up does not claim hardware performance, exact packet reordering cost, or a universal hash winner.
