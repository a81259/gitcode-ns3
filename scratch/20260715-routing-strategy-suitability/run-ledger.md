# Run Ledger

- branch: `next`
- commit: `d369f91df7d3ee78993ff812e1be3efbb2c02af9`
- dirty_at_start: `true`
- checkpoint_policy: continue_full_matrix with per-block safety pilots
- execution: sequential-only
- package_size_bytes: `170478806`

## Checkpoints

- hash-robustness: passed
- spray-crossover: passed
- adaptive-signal: passed
- ingress-entropy: passed
- path-scope-region: passed
- transport-transfer: passed

| case | block | status | return code | duration (s) | artifact gate |
|---|---|---:|---:|---:|---|
| h-many-w3-s11-hash64 | hash-robustness | success | 0 | 1.083 | completed_tasks=64/64 |
| h-many-w3-s11-crc32 | hash-robustness | success | 0 | 1.187 | completed_tasks=64/64 |
| h-many-w3-s11-toeplitz | hash-robustness | success | 0 | 1.234 | completed_tasks=64/64 |
| h-many-w3-s29-hash64 | hash-robustness | success | 0 | 1.148 | completed_tasks=64/64 |
| h-many-w3-s29-crc32 | hash-robustness | success | 0 | 1.165 | completed_tasks=64/64 |
| h-many-w3-s29-toeplitz | hash-robustness | success | 0 | 1.166 | completed_tasks=64/64 |
| h-many-w3-s47-hash64 | hash-robustness | success | 0 | 1.137 | completed_tasks=64/64 |
| h-many-w3-s47-crc32 | hash-robustness | success | 0 | 1.173 | completed_tasks=64/64 |
| h-many-w3-s47-toeplitz | hash-robustness | success | 0 | 1.185 | completed_tasks=64/64 |
| h-many-w5-s11-hash64 | hash-robustness | success | 0 | 1.237 | completed_tasks=64/64 |
| h-many-w5-s11-crc32 | hash-robustness | success | 0 | 1.195 | completed_tasks=64/64 |
| h-many-w5-s11-toeplitz | hash-robustness | success | 0 | 1.22 | completed_tasks=64/64 |
| h-many-w5-s29-hash64 | hash-robustness | success | 0 | 1.175 | completed_tasks=64/64 |
| h-many-w5-s29-crc32 | hash-robustness | success | 0 | 1.207 | completed_tasks=64/64 |
| h-many-w5-s29-toeplitz | hash-robustness | success | 0 | 1.237 | completed_tasks=64/64 |
| h-many-w5-s47-hash64 | hash-robustness | success | 0 | 1.192 | completed_tasks=64/64 |
| h-many-w5-s47-crc32 | hash-robustness | success | 0 | 1.192 | completed_tasks=64/64 |
| h-many-w5-s47-toeplitz | hash-robustness | success | 0 | 1.17 | completed_tasks=64/64 |
| h-many-w8-s11-hash64 | hash-robustness | success | 0 | 1.193 | completed_tasks=64/64 |
| h-many-w8-s11-crc32 | hash-robustness | success | 0 | 1.259 | completed_tasks=64/64 |
| h-many-w8-s11-toeplitz | hash-robustness | success | 0 | 1.239 | completed_tasks=64/64 |
| h-many-w8-s29-hash64 | hash-robustness | success | 0 | 1.256 | completed_tasks=64/64 |
| h-many-w8-s29-crc32 | hash-robustness | success | 0 | 1.198 | completed_tasks=64/64 |
| h-many-w8-s29-toeplitz | hash-robustness | success | 0 | 1.281 | completed_tasks=64/64 |
| h-many-w8-s47-hash64 | hash-robustness | success | 0 | 1.256 | completed_tasks=64/64 |
| h-many-w8-s47-crc32 | hash-robustness | success | 0 | 1.216 | completed_tasks=64/64 |
| h-many-w8-s47-toeplitz | hash-robustness | success | 0 | 1.22 | completed_tasks=64/64 |
| h-elephant-w8-s11-hash64 | hash-robustness | success | 0 | 3.471 | completed_tasks=4/4 |
| h-elephant-w8-s11-crc32 | hash-robustness | success | 0 | 3.351 | completed_tasks=4/4 |
| h-elephant-w8-s11-toeplitz | hash-robustness | success | 0 | 3.485 | completed_tasks=4/4 |
| h-elephant-w8-s29-hash64 | hash-robustness | success | 0 | 3.357 | completed_tasks=4/4 |
| h-elephant-w8-s29-crc32 | hash-robustness | success | 0 | 3.354 | completed_tasks=4/4 |
| h-elephant-w8-s29-toeplitz | hash-robustness | success | 0 | 3.509 | completed_tasks=4/4 |
| h-elephant-w8-s47-hash64 | hash-robustness | success | 0 | 3.386 | completed_tasks=4/4 |
| h-elephant-w8-s47-crc32 | hash-robustness | success | 0 | 3.39 | completed_tasks=4/4 |
| h-elephant-w8-s47-toeplitz | hash-robustness | success | 0 | 3.385 | completed_tasks=4/4 |
| s-16k-d20n-flow-hash64 | spray-crossover | success | 0 | 0.17 | completed_tasks=1/1 |
| s-16k-d20n-packet-hash64 | spray-crossover | success | 0 | 0.178 | completed_tasks=1/1 |
| s-16k-d20n-packet-rr | spray-crossover | success | 0 | 0.201 | completed_tasks=1/1 |
| s-16k-d2u-flow-hash64 | spray-crossover | success | 0 | 0.192 | completed_tasks=1/1 |
| s-16k-d2u-packet-hash64 | spray-crossover | success | 0 | 0.2 | completed_tasks=1/1 |
| s-16k-d2u-packet-rr | spray-crossover | success | 0 | 0.194 | completed_tasks=1/1 |
| s-16k-d20u-flow-hash64 | spray-crossover | success | 0 | 0.188 | completed_tasks=1/1 |
| s-16k-d20u-packet-hash64 | spray-crossover | success | 0 | 0.192 | completed_tasks=1/1 |
| s-16k-d20u-packet-rr | spray-crossover | success | 0 | 0.194 | completed_tasks=1/1 |
| s-256k-d20n-flow-hash64 | spray-crossover | success | 0 | 0.187 | completed_tasks=1/1 |
| s-256k-d20n-packet-hash64 | spray-crossover | success | 0 | 0.214 | completed_tasks=1/1 |
| s-256k-d20n-packet-rr | spray-crossover | success | 0 | 0.202 | completed_tasks=1/1 |
| s-256k-d2u-flow-hash64 | spray-crossover | success | 0 | 0.194 | completed_tasks=1/1 |
| s-256k-d2u-packet-hash64 | spray-crossover | success | 0 | 0.197 | completed_tasks=1/1 |
| s-256k-d2u-packet-rr | spray-crossover | success | 0 | 0.206 | completed_tasks=1/1 |
| s-256k-d20u-flow-hash64 | spray-crossover | success | 0 | 0.195 | completed_tasks=1/1 |
| s-256k-d20u-packet-hash64 | spray-crossover | success | 0 | 0.193 | completed_tasks=1/1 |
| s-256k-d20u-packet-rr | spray-crossover | success | 0 | 0.203 | completed_tasks=1/1 |
| s-8m-d20n-flow-hash64 | spray-crossover | success | 0 | 0.638 | completed_tasks=1/1 |
| s-8m-d20n-packet-hash64 | spray-crossover | success | 0 | 0.536 | completed_tasks=1/1 |
| s-8m-d20n-packet-rr | spray-crossover | success | 0 | 0.547 | completed_tasks=1/1 |
| s-8m-d2u-flow-hash64 | spray-crossover | success | 0 | 0.64 | completed_tasks=1/1 |
| s-8m-d2u-packet-hash64 | spray-crossover | success | 0 | 0.488 | completed_tasks=1/1 |
| s-8m-d2u-packet-rr | spray-crossover | success | 0 | 0.513 | completed_tasks=1/1 |
| s-8m-d20u-flow-hash64 | spray-crossover | success | 0 | 0.687 | completed_tasks=1/1 |
| s-8m-d20u-packet-hash64 | spray-crossover | success | 0 | 0.498 | completed_tasks=1/1 |
| s-8m-d20u-packet-rr | spray-crossover | success | 0 | 0.511 | completed_tasks=1/1 |
| a-screen-r100-g0-hash64 | adaptive-signal | success | 0 | 0.345 | completed_tasks=16/16 |
| a-screen-r100-g0-rr | adaptive-signal | success | 0 | 0.363 | completed_tasks=16/16 |
| a-screen-r100-g0-adaptive | adaptive-signal | success | 0 | 0.395 | completed_tasks=16/16 |
| a-screen-r100-g10u-hash64 | adaptive-signal | success | 0 | 0.389 | completed_tasks=16/16 |
| a-screen-r100-g10u-rr | adaptive-signal | success | 0 | 0.405 | completed_tasks=16/16 |
| a-screen-r100-g10u-adaptive | adaptive-signal | success | 0 | 0.378 | completed_tasks=16/16 |
| a-screen-r50-g0-hash64 | adaptive-signal | success | 0 | 0.337 | completed_tasks=16/16 |
| a-screen-r50-g0-rr | adaptive-signal | success | 0 | 0.341 | completed_tasks=16/16 |
| a-screen-r50-g0-adaptive | adaptive-signal | success | 0 | 0.339 | completed_tasks=16/16 |
| a-screen-r50-g10u-hash64 | adaptive-signal | success | 0 | 0.365 | completed_tasks=16/16 |
| a-screen-r50-g10u-rr | adaptive-signal | success | 0 | 0.387 | completed_tasks=16/16 |
| a-screen-r50-g10u-adaptive | adaptive-signal | success | 0 | 0.348 | completed_tasks=16/16 |
| a-screen-r25-g0-hash64 | adaptive-signal | success | 0 | 0.358 | completed_tasks=16/16 |
| a-screen-r25-g0-rr | adaptive-signal | success | 0 | 0.353 | completed_tasks=16/16 |
| a-screen-r25-g0-adaptive | adaptive-signal | success | 0 | 0.323 | completed_tasks=16/16 |
| a-screen-r25-g10u-hash64 | adaptive-signal | success | 0 | 0.363 | completed_tasks=16/16 |
| a-screen-r25-g10u-rr | adaptive-signal | success | 0 | 0.361 | completed_tasks=16/16 |
| a-screen-r25-g10u-adaptive | adaptive-signal | success | 0 | 0.334 | completed_tasks=16/16 |
| a-confirm-s11-hash64 | adaptive-signal | success | 0 | 0.345 | completed_tasks=16/16 |
| a-confirm-s11-rr | adaptive-signal | success | 0 | 0.342 | completed_tasks=16/16 |
| a-confirm-s11-adaptive | adaptive-signal | success | 0 | 0.349 | completed_tasks=16/16 |
| a-confirm-s29-hash64 | adaptive-signal | success | 0 | 0.353 | completed_tasks=16/16 |
| a-confirm-s29-rr | adaptive-signal | success | 0 | 0.355 | completed_tasks=16/16 |
| a-confirm-s29-adaptive | adaptive-signal | success | 0 | 0.341 | completed_tasks=16/16 |
| a-confirm-s47-hash64 | adaptive-signal | success | 0 | 0.413 | completed_tasks=16/16 |
| a-confirm-s47-rr | adaptive-signal | success | 0 | 0.368 | completed_tasks=16/16 |
| a-confirm-s47-adaptive | adaptive-signal | success | 0 | 0.33 | completed_tasks=16/16 |
| i-n1-s11-hash64 | ingress-entropy | success | 0 | 1.032 | completed_tasks=64/64 |
| i-n1-s11-stripe | ingress-entropy | success | 0 | 1.056 | completed_tasks=64/64 |
| i-n1-s29-hash64 | ingress-entropy | success | 0 | 1.092 | completed_tasks=64/64 |
| i-n1-s29-stripe | ingress-entropy | success | 0 | 1.021 | completed_tasks=64/64 |
| i-n1-s47-hash64 | ingress-entropy | success | 0 | 1.023 | completed_tasks=64/64 |
| i-n1-s47-stripe | ingress-entropy | success | 0 | 1.034 | completed_tasks=64/64 |
| i-n2-s11-hash64 | ingress-entropy | success | 0 | 1.057 | completed_tasks=64/64 |
| i-n2-s11-stripe | ingress-entropy | success | 0 | 1.126 | completed_tasks=64/64 |
| i-n2-s29-hash64 | ingress-entropy | success | 0 | 1.168 | completed_tasks=64/64 |
| i-n2-s29-stripe | ingress-entropy | success | 0 | 1.075 | completed_tasks=64/64 |
| i-n2-s47-hash64 | ingress-entropy | success | 0 | 1.07 | completed_tasks=64/64 |
| i-n2-s47-stripe | ingress-entropy | success | 0 | 1.038 | completed_tasks=64/64 |
| i-n4-s11-hash64 | ingress-entropy | success | 0 | 1.061 | completed_tasks=64/64 |
| i-n4-s11-stripe | ingress-entropy | success | 0 | 1.071 | completed_tasks=64/64 |
| i-n4-s29-hash64 | ingress-entropy | success | 0 | 1.106 | completed_tasks=64/64 |
| i-n4-s29-stripe | ingress-entropy | success | 0 | 1.129 | completed_tasks=64/64 |
| i-n4-s47-hash64 | ingress-entropy | success | 0 | 1.115 | completed_tasks=64/64 |
| i-n4-s47-stripe | ingress-entropy | success | 0 | 1.07 | completed_tasks=64/64 |
| i-n8-s11-hash64 | ingress-entropy | success | 0 | 1.107 | completed_tasks=64/64 |
| i-n8-s11-stripe | ingress-entropy | success | 0 | 1.067 | completed_tasks=64/64 |
| i-n8-s29-hash64 | ingress-entropy | success | 0 | 1.094 | completed_tasks=64/64 |
| i-n8-s29-stripe | ingress-entropy | success | 0 | 1.085 | completed_tasks=64/64 |
| i-n8-s47-hash64 | ingress-entropy | success | 0 | 1.076 | completed_tasks=64/64 |
| i-n8-s47-stripe | ingress-entropy | success | 0 | 1.088 | completed_tasks=64/64 |
| p-neutral-long-flow-short | path-scope-region | success | 0 | 0.65 | completed_tasks=1/1 |
| p-neutral-long-flow-all | path-scope-region | success | 0 | 0.639 | completed_tasks=1/1 |
| p-neutral-long-packet-short | path-scope-region | success | 0 | 0.63 | completed_tasks=1/1 |
| p-neutral-long-packet-all | path-scope-region | success | 0 | 0.531 | completed_tasks=1/1 |
| p-neutral-many-flow-short | path-scope-region | success | 0 | 0.63 | completed_tasks=32/32 |
| p-neutral-many-flow-all | path-scope-region | success | 0 | 0.692 | completed_tasks=32/32 |
| p-neutral-many-packet-short | path-scope-region | success | 0 | 0.657 | completed_tasks=32/32 |
| p-neutral-many-packet-all | path-scope-region | success | 0 | 0.508 | completed_tasks=32/32 |
| p-capacity-long-flow-short | path-scope-region | success | 0 | 0.653 | completed_tasks=1/1 |
| p-capacity-long-flow-all | path-scope-region | success | 0 | 0.62 | completed_tasks=1/1 |
| p-capacity-long-packet-short | path-scope-region | success | 0 | 0.68 | completed_tasks=1/1 |
| p-capacity-long-packet-all | path-scope-region | success | 0 | 0.492 | completed_tasks=1/1 |
| p-capacity-many-flow-short | path-scope-region | success | 0 | 0.631 | completed_tasks=32/32 |
| p-capacity-many-flow-all | path-scope-region | success | 0 | 0.627 | completed_tasks=32/32 |
| p-capacity-many-packet-short | path-scope-region | success | 0 | 0.645 | completed_tasks=32/32 |
| p-capacity-many-packet-all | path-scope-region | success | 0 | 0.503 | completed_tasks=32/32 |
| p-latency-long-flow-short | path-scope-region | success | 0 | 0.619 | completed_tasks=1/1 |
| p-latency-long-flow-all | path-scope-region | success | 0 | 0.658 | completed_tasks=1/1 |
| p-latency-long-packet-short | path-scope-region | success | 0 | 0.651 | completed_tasks=1/1 |
| p-latency-long-packet-all | path-scope-region | success | 0 | 0.516 | completed_tasks=1/1 |
| p-latency-many-flow-short | path-scope-region | success | 0 | 0.653 | completed_tasks=32/32 |
| p-latency-many-flow-all | path-scope-region | success | 0 | 0.635 | completed_tasks=32/32 |
| p-latency-many-packet-short | path-scope-region | success | 0 | 0.63 | completed_tasks=32/32 |
| p-latency-many-packet-all | path-scope-region | success | 0 | 0.503 | completed_tasks=32/32 |
| t-ctp-flow-hash64 | transport-transfer | success | 0 | 0.223 | completed_tasks=1/1 |
| t-ctp-flow-crc32 | transport-transfer | success | 0 | 0.218 | completed_tasks=1/1 |
| t-ctp-flow-toeplitz | transport-transfer | success | 0 | 0.223 | completed_tasks=1/1 |
| t-ctp-packet-rr | transport-transfer | success | 0 | 0.232 | completed_tasks=1/1 |
| t-ctp-packet-adaptive | transport-transfer | success | 0 | 0.228 | completed_tasks=1/1 |
| t-ctp-flow-stripe | transport-transfer | success | 0 | 0.217 | completed_tasks=1/1 |
| t-ctp-packet-all-hash64 | transport-transfer | success | 0 | 0.218 | completed_tasks=1/1 |
| t-ldst-flow-hash64 | transport-transfer | success | 0 | 0.491 | completed_tasks=1/1 |
| t-ldst-flow-crc32 | transport-transfer | success | 0 | 0.479 | completed_tasks=1/1 |
| t-ldst-flow-toeplitz | transport-transfer | success | 0 | 0.503 | completed_tasks=1/1 |
| t-ldst-packet-rr | transport-transfer | success | 0 | 0.537 | completed_tasks=1/1 |
| t-ldst-packet-adaptive | transport-transfer | success | 0 | 0.495 | completed_tasks=1/1 |
| t-ldst-flow-stripe | transport-transfer | success | 0 | 0.484 | completed_tasks=1/1 |
| t-ldst-packet-all-hash64 | transport-transfer | success | 0 | 0.499 | completed_tasks=1/1 |
