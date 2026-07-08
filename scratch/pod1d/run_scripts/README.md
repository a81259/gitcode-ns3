# Pod1D No-Access Pairwise 2MB Single-Thread Baseline

This case is a reproducible single-thread baseline for the Pod1D topology with
the per-host access layer removed.

## Topology

- Hosts: 1368
- L1 switches: 456
- L2 switches: 96
- Total nodes: 1920
- Topology links: 49248
- Each host connects directly to 24 pod-local L1 switches.
- `transport_channel.csv` is intentionally header-only; transport channels are
  created on demand by `UbApp`.

## Workload

- Pattern: pairwise bidirectional traffic over all hosts.
- Pairs: `0<->1`, `2<->3`, ..., `1366<->1367`.
- Tasks: 1368.
- Size per task: 2,000,000 bytes.
- Opcode: `URMA_WRITE`.
- Priority: 7.

## Key Attributes

- `ns3::UbApp::EnableMultiPath = true`
- `ns3::UbTransportChannel::UsePacketSpray = true`
- `UB_TASK_TRACE_ENABLE = true`
- `UB_PACKET_TRACE_ENABLE = false`
- `UB_PORT_TRACE_ENABLE = false`

Packet and port traces are disabled so the full-host case can run with lower
trace overhead. The committed baseline result is task-level only.

## Regenerate Topology

The topology generator used for this case is committed as:

```text
scratch/pod1d_no_access_pairwise_2mb_full_ps/generate_topology.py
```

To regenerate `node.csv`, `topology.csv`, and `routing_table.csv`:

```bash
PYTHONPATH=scratch/ns-3-ub-tools python3 scratch/pod1d_no_access_pairwise_2mb_full_ps/generate_topology.py --output-dir scratch/pod1d_no_access_pairwise_2mb_full_ps --route-mode compressed
```

## Run

Configure/build a single-thread UB quick-example first:

```bash
python3.12 ./ns3 configure --enable-modules=unified-bus --disable-examples --disable-tests --disable-mpi --disable-mtp --disable-werror -d release -G Ninja
BUILD_JOBS=${BUILD_JOBS:-$(python3.12 -c 'import os; print(os.cpu_count() or 1)')}
python3.12 ./ns3 build -j "$BUILD_JOBS" ub-quick-example
```

Run the case:

```bash
python3.12 ./ns3 run --no-build 'scratch/ub-quick-example --case-path=scratch/pod1d_no_access_pairwise_2mb_full_ps --stop-ms=50 --mtp-threads=1'
```

If the tree is configured with MTP enabled, still pass `--mtp-threads=1` for
this baseline. Do not use `--mtp-threads=4` when comparing task completion
times against the committed single-thread result.

## Baseline Result

The committed reference output is:

```text
scratch/pod1d_no_access_pairwise_2mb_full_ps/output/task_statistics_single.csv
```

Observed single-thread result:

- Processed tasks: 1368/1368
- `taskCompletesTime(us)`: 10.072232 for every task
- `taskThroughput(Gbps)`: 1590.1045 for every task
- Run wall-clock from `run_single.log`: 240.535985 s
- Total wall-clock from `run_single.log`: 254.308225 s

This baseline is intended as the reference behavior for the 2MB full-coverage
single-thread case.
