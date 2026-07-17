# Run Ledger

- branch: `codex/routing-modes`
- checkpoint_policy: semantic hard failure stops; performance mismatch continues
- execution: sequential-only
- semantic_checkpoint: not-applicable

| case | block | status | return code | duration (s) | artifacts |
|---|---|---:|---:|---:|---|
| spray-latency-flow-hash | spray-latency | success | 0 | 0.349 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| spray-latency-packet-hash | spray-latency | success | 0 | 0.397 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| all-latency-short | all-latency | success | 0 | 0.387 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
| all-latency-all | all-latency | success | 0 | 0.357 | console.log, runlog, output/task_statistics.csv, output/throughput.csv |
