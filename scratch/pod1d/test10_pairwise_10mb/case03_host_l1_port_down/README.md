# Pod1D Test10 Pairwise 10MB (case01_standard)

This case mirrors `scratch/pod1d/test01_tp_all_gather/case01_standard` and replaces only the traffic pattern.

## Workload

- Pattern: bidirectional pairwise traffic between hosts `0..71` and `72..143`.
- Pairs: `0<->72`, `1<->73`, ..., `71<->143`.
- Tasks: 144.
- Size per task: 10 MiB (`10485760` bytes).
- Opcode: `URMA_WRITE`.
- Priority: 7.

## Run

```bash
./ns3 run --no-build 'scratch/ub-quick-example --case-path=scratch/pod1d/test10_pairwise_10mb/case01_standard'
```
