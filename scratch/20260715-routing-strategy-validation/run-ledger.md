# Run Ledger

- branch: `codex/routing-modes`
- checkpoint_policy: semantic hard failure stops; performance mismatch continues
- execution: sequential-only
- semantic_checkpoint: passed: {"sem-packet-all": [1, 2, 3], "sem-flow-short": [1], "sem-flow-all": [2], "sem-packet-short": [1]}

| case | block | status | return code | duration (s) | artifacts |
|---|---|---:|---:|---:|---|
| sem-flow-short | semantic | success | 0 | 0.392 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| sem-packet-short | semantic | success | 0 | 0.359 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| sem-flow-all | semantic | success | 0 | 0.378 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| sem-packet-all | semantic | success | 0 | 0.45 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| hash-many-hash64 | hash-many | success | 0 | 1.228 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| hash-elephant-hash64 | hash-elephant | success | 0 | 3.886 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| hash-many-crc32 | hash-many | success | 0 | 1.003 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| hash-elephant-crc32 | hash-elephant | success | 0 | 3.588 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| hash-many-toeplitz | hash-many | success | 0 | 1.359 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| hash-elephant-toeplitz | hash-elephant | success | 0 | 5.401 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| spray-equal-flow-hash | spray-equal | success | 0 | 0.96 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| spray-equal-packet-hash | spray-equal | success | 0 | 0.759 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| spray-equal-round-robin | spray-equal | success | 0 | 0.771 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| spray-delay-flow-hash | spray-delay | success | 0 | 1.06 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| spray-delay-packet-hash | spray-delay | success | 0 | 0.732 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| spray-delay-round-robin | spray-delay | success | 0 | 0.738 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| adaptive-hot-hash | adaptive-hot | success | 0 | 0.802 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| adaptive-hot-adaptive | adaptive-hot | success | 0 | 0.701 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| adaptive-sparse-rr | adaptive-sparse | success | 0 | 0.356 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| adaptive-sparse-adaptive | adaptive-sparse | success | 0 | 0.352 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| stripe-multi-hash | stripe-multi | success | 0 | 3.118 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| stripe-multi-stripe | stripe-multi | success | 0 | 2.973 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| stripe-single-hash | stripe-single | success | 0 | 1.69 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| stripe-single-stripe | stripe-single | success | 0 | 1.693 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| all-hot-short | all-hot | success | 0 | 0.945 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| all-hot-all | all-hot | success | 0 | 0.761 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| all-delay-short | all-delay | success | 0 | 0.941 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| all-delay-all | all-delay | success | 0 | 0.733 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| cover-hash64-per-flow-all-paths | coverage | success | 0 | 0.339 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| cover-hash64-per-packet-all-paths | coverage | success | 0 | 0.348 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| cover-hash64-per-flow-shortest-paths | coverage | success | 0 | 0.381 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| cover-hash64-per-packet-shortest-paths | coverage | success | 0 | 0.38 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| cover-crc32-per-flow-all-paths | coverage | success | 0 | 0.351 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| cover-crc32-per-packet-all-paths | coverage | success | 0 | 0.348 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| cover-crc32-per-flow-shortest-paths | coverage | success | 0 | 0.368 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| cover-crc32-per-packet-shortest-paths | coverage | success | 0 | 0.391 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| cover-toeplitz-per-flow-all-paths | coverage | success | 0 | 0.399 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| cover-toeplitz-per-packet-all-paths | coverage | success | 0 | 0.363 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| cover-toeplitz-per-flow-shortest-paths | coverage | success | 0 | 0.371 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| cover-toeplitz-per-packet-shortest-paths | coverage | success | 0 | 0.37 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| cover-round-robin-per-packet-all-paths | coverage | success | 0 | 0.365 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| cover-round-robin-per-packet-shortest-paths | coverage | success | 0 | 0.36 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| cover-adaptive-per-packet-all-paths | coverage | success | 0 | 0.346 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| cover-adaptive-per-packet-shortest-paths | coverage | success | 0 | 0.331 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| cover-ingress-port-stripe-per-flow-all-paths | coverage | success | 0 | 0.345 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| cover-ingress-port-stripe-per-flow-shortest-paths | coverage | success | 0 | 0.389 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| smoke-ctp-flow-hash | smoke-ctp | success | 0 | 0.396 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| smoke-ctp-packet-hash | smoke-ctp | success | 0 | 0.378 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| smoke-ctp-round-robin | smoke-ctp | success | 0 | 0.158 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| smoke-ctp-adaptive | smoke-ctp | success | 0 | 0.152 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| smoke-ctp-ingress-stripe | smoke-ctp | success | 0 | 0.377 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| smoke-ldst-flow-hash | smoke-ldst | success | 0 | 0.789 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| smoke-ldst-packet-hash | smoke-ldst | success | 0 | 0.815 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| smoke-ldst-round-robin | smoke-ldst | success | 0 | 0.799 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| smoke-ldst-adaptive | smoke-ldst | success | 0 | 0.757 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| smoke-ldst-ingress-stripe | smoke-ldst | success | 0 | 0.773 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
