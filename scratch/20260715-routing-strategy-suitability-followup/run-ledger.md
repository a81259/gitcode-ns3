# Run Ledger

- branch: `next`
- commit: `d369f91df7d3ee78993ff812e1be3efbb2c02af9`
- dirty_at_start: `true`
- checkpoint_policy: continue_full_matrix with per-block safety pilots
- execution: sequential-only
- package_size_bytes: `15725593`

## Checkpoints

- adaptive-single-packet-sparse: passed
- per-flow-all-distinct-keys: passed

| case | block | status | return code | duration (s) | artifact gate |
|---|---|---:|---:|---:|---|
| as-r100-g1u-hash64 | adaptive-single-packet-sparse | success | 0 | 0.192 | completed_tasks=64/64 |
| as-r100-g1u-rr | adaptive-single-packet-sparse | success | 0 | 0.199 | completed_tasks=64/64 |
| as-r100-g1u-adaptive | adaptive-single-packet-sparse | success | 0 | 0.204 | completed_tasks=64/64 |
| as-r100-g10u-hash64 | adaptive-single-packet-sparse | success | 0 | 0.21 | completed_tasks=64/64 |
| as-r100-g10u-rr | adaptive-single-packet-sparse | success | 0 | 0.218 | completed_tasks=64/64 |
| as-r100-g10u-adaptive | adaptive-single-packet-sparse | success | 0 | 0.209 | completed_tasks=64/64 |
| as-r100-g100u-hash64 | adaptive-single-packet-sparse | success | 0 | 0.22 | completed_tasks=64/64 |
| as-r100-g100u-rr | adaptive-single-packet-sparse | success | 0 | 0.217 | completed_tasks=64/64 |
| as-r100-g100u-adaptive | adaptive-single-packet-sparse | success | 0 | 0.208 | completed_tasks=64/64 |
| as-r50-g1u-hash64 | adaptive-single-packet-sparse | success | 0 | 0.212 | completed_tasks=64/64 |
| as-r50-g1u-rr | adaptive-single-packet-sparse | success | 0 | 0.218 | completed_tasks=64/64 |
| as-r50-g1u-adaptive | adaptive-single-packet-sparse | success | 0 | 0.204 | completed_tasks=64/64 |
| as-r50-g10u-hash64 | adaptive-single-packet-sparse | success | 0 | 0.21 | completed_tasks=64/64 |
| as-r50-g10u-rr | adaptive-single-packet-sparse | success | 0 | 0.207 | completed_tasks=64/64 |
| as-r50-g10u-adaptive | adaptive-single-packet-sparse | success | 0 | 0.199 | completed_tasks=64/64 |
| as-r50-g100u-hash64 | adaptive-single-packet-sparse | success | 0 | 0.206 | completed_tasks=64/64 |
| as-r50-g100u-rr | adaptive-single-packet-sparse | success | 0 | 0.211 | completed_tasks=64/64 |
| as-r50-g100u-adaptive | adaptive-single-packet-sparse | success | 0 | 0.199 | completed_tasks=64/64 |
| as-r25-g1u-hash64 | adaptive-single-packet-sparse | success | 0 | 0.198 | completed_tasks=64/64 |
| as-r25-g1u-rr | adaptive-single-packet-sparse | success | 0 | 0.211 | completed_tasks=64/64 |
| as-r25-g1u-adaptive | adaptive-single-packet-sparse | success | 0 | 0.198 | completed_tasks=64/64 |
| as-r25-g10u-hash64 | adaptive-single-packet-sparse | success | 0 | 0.2 | completed_tasks=64/64 |
| as-r25-g10u-rr | adaptive-single-packet-sparse | success | 0 | 0.206 | completed_tasks=64/64 |
| as-r25-g10u-adaptive | adaptive-single-packet-sparse | success | 0 | 0.203 | completed_tasks=64/64 |
| as-r25-g100u-hash64 | adaptive-single-packet-sparse | success | 0 | 0.202 | completed_tasks=64/64 |
| as-r25-g100u-rr | adaptive-single-packet-sparse | success | 0 | 0.211 | completed_tasks=64/64 |
| as-r25-g100u-adaptive | adaptive-single-packet-sparse | success | 0 | 0.199 | completed_tasks=64/64 |
| pf-neutral-s11-short | per-flow-all-distinct-keys | success | 0 | 0.579 | completed_tasks=32/32 |
| pf-neutral-s11-all | per-flow-all-distinct-keys | success | 0 | 0.61 | completed_tasks=32/32 |
| pf-neutral-s29-short | per-flow-all-distinct-keys | success | 0 | 0.585 | completed_tasks=32/32 |
| pf-neutral-s29-all | per-flow-all-distinct-keys | success | 0 | 0.585 | completed_tasks=32/32 |
| pf-neutral-s47-short | per-flow-all-distinct-keys | success | 0 | 0.583 | completed_tasks=32/32 |
| pf-neutral-s47-all | per-flow-all-distinct-keys | success | 0 | 0.587 | completed_tasks=32/32 |
| pf-capacity-s11-short | per-flow-all-distinct-keys | success | 0 | 0.59 | completed_tasks=32/32 |
| pf-capacity-s11-all | per-flow-all-distinct-keys | success | 0 | 0.624 | completed_tasks=32/32 |
| pf-capacity-s29-short | per-flow-all-distinct-keys | success | 0 | 0.585 | completed_tasks=32/32 |
| pf-capacity-s29-all | per-flow-all-distinct-keys | success | 0 | 0.603 | completed_tasks=32/32 |
| pf-capacity-s47-short | per-flow-all-distinct-keys | success | 0 | 0.596 | completed_tasks=32/32 |
| pf-capacity-s47-all | per-flow-all-distinct-keys | success | 0 | 0.582 | completed_tasks=32/32 |
| pf-latency-s11-short | per-flow-all-distinct-keys | success | 0 | 0.584 | completed_tasks=32/32 |
| pf-latency-s11-all | per-flow-all-distinct-keys | success | 0 | 0.597 | completed_tasks=32/32 |
| pf-latency-s29-short | per-flow-all-distinct-keys | success | 0 | 0.579 | completed_tasks=32/32 |
| pf-latency-s29-all | per-flow-all-distinct-keys | success | 0 | 0.583 | completed_tasks=32/32 |
| pf-latency-s47-short | per-flow-all-distinct-keys | success | 0 | 0.578 | completed_tasks=32/32 |
| pf-latency-s47-all | per-flow-all-distinct-keys | success | 0 | 0.595 | completed_tasks=32/32 |
