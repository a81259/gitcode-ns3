# test90 Independent-Traffic Experiment Design

## Objective

Create a self-contained test90 experiment from test09 DP Reduce Scatter.  For each
of the five formal topology cases, retain only traffic rows whose
`dependOnPhases` field is empty, then compare task FCT across standard and four
fault variants.

## Scope and Inputs

- Source: `scratch/pod1d/test09_dp_reduce_scatter`.
- Destination: `scratch/pod1d/test90_dp_reduce_scatter_independent_scale80`.
- Cases, in execution order:
  1. `case01_标准topo`
  2. `case02_故障1topo_单链路lane`
  3. `case03_故障2topo_单链路laport`
  4. `case04_故障3topo_分布式多链路port`
  5. `case05_故障4topo_分集中式多链路port`
- Base traffic: the existing scale80 `traffic.csv` in each source case.
- Expected filtered workload: 1368 of 6840 tasks, 7,261,283,448 bytes per case.
- `test09` remains unchanged.

## Fixed Controls

- Routing: `PER_PACKET_SHORTEST_PATHS + ROUND_ROBIN` (packet spray).
- Simulation: one process, one thread; serial case order (parallelism 1).
- No task has phase dependencies after filtering; use the established
  `--dependency-visibility-delay=10ns` run switch for command consistency.
- Preserve each case's node, topology, routing table, and network attributes.

## Artifacts

All generated content lives under the test90 directory:

- prepared case inputs and filtered traffic evidence;
- console logs and archived `task_statistics.csv` for every case;
- `fct_summary.csv` with completed task count, FCT mean, P95, and max;
- one full-distribution Task FCT empirical CDF with five curves in PNG and SVG;
- a result note and an exact rerun command.

## Implementation and Validation

1. Add a small testable runner dedicated to test90.
2. Test first that blank or whitespace-only dependency fields are retained and
   non-empty fields are excluded, while headers and the remaining row order are
   preserved.
3. Copy only the required test09 case inputs into test90 and write filtered
   `traffic.csv` plus a scale80 source snapshot.
4. Run all five cases serially in the listed order.
5. Verify five zero return codes, `1368/1368` completed tasks per case, no
   dependency fields in prepared traffic, canonical routing attributes, and
   non-empty PNG/SVG plot outputs.

## Interpretation Boundary

Results are simulation-derived for this independent-task subset and should not
be compared as an equal-load replacement for the prior 6840-task dependent
workload.  The summary reports task FCT only.
