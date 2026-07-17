# test90 independent scale80 traffic

- Base: test09 DP Reduce Scatter five formal cases.
- Filter: retain only rows with blank `dependOnPhases`.
- Workload: 1368 independent tasks and 7,261,283,448 bytes per case.
- Routing: `PER_PACKET_SHORTEST_PATHS + ROUND_ROBIN`.
- Runtime: one single-thread simulator process at a time, in standard-to-fault4 order.
- Metric: task FCT = `taskCompletesTime(us) - taskStartTime(us)`.
- Boundary: results are simulation-derived for this independent-task subset.
