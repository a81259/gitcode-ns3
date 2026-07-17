# Refreshed-traffic standard case01 results

- test01 traffic.csv: pod1-internal only (nodes 0-71); traffic.original.csv remains full
- test02-test04 traffic.csv: refreshed sizes from the requested multipliers
- Routing: PER_PACKET_SHORTEST_PATHS + ROUND_ROBIN
- Dependency visibility delay: 10ns
- Runtime: single-thread simulations; test02-test04 completed in the parallel-4 batch, corrected test01 rerun separately

| Test | Completed | Mean (us) | P95 (us) | Max (us) | RC |
|---|---:|---:|---:|---:|---:|
| test01_tp_all_gather | 72/72 | 79.194680 | 79.209935 | 79.209935 | 0 |
| test02_cp_all_to_all | 216/216 | 301.648622 | 310.965652 | 310.993163 | 0 |
| test03_tp_reduce_scatter | 72/72 | 360.799144 | 360.814899 | 360.814899 | 0 |
| test04_tp_reduce_scatter | 72/72 | 182.667296 | 182.683051 | 182.683051 | 0 |
