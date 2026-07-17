# Scale40 And Standard Case01 Batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run test08/test09 scale40 across five topology cases, then run the existing case01 traffic for test01–06, test10, and test11, with reproducible summaries and isolated artifacts.

**Architecture:** Reuse the verified test08/test09 runner for stage 1 by passing `--scale 40` and a new package root. Add one focused stage-2 runner that imports the existing traffic/config/FCT helpers, preserves each existing `traffic.csv`, migrates canonical routing attributes, executes eight standard cases with two concurrent single-thread processes, and archives task statistics.

**Tech Stack:** Python 3.12, Miniconda Python 3, ns-3.44 `ub-quick-example`, CSV, unittest, matplotlib.

---

### Task 1: Create The Durable Experiment Package

**Files:**
- Create: `scratch/20260716-scale40-test08-09-then-standard-case01/experiment-plan.md`
- Create: `scratch/20260716-scale40-test08-09-then-standard-case01/matrix.yaml`
- Create: `scratch/20260716-scale40-test08-09-then-standard-case01/command-manifest.yaml`
- Create: `scratch/20260716-scale40-test08-09-then-standard-case01/run-ledger.md`
- Create: `scratch/20260716-scale40-test08-09-then-standard-case01/cases/*/experiment-spec.md`

- [ ] **Step 1: Record the two sequential stages**

The package must state that stage 1 contains ten scale40 test08/test09 cases and stage 2 contains eight unscaled existing-traffic standard cases.

- [ ] **Step 2: Record fixed controls**

Record `PER_PACKET_SHORTEST_PATHS + ROUND_ROBIN`, `10ns` dependency visibility delay, no MTP, one simulator thread per process, and process-level parallelism two.

- [ ] **Step 3: Verify package completeness**

Run:

```bash
test -f scratch/20260716-scale40-test08-09-then-standard-case01/experiment-plan.md
test -f scratch/20260716-scale40-test08-09-then-standard-case01/matrix.yaml
test -f scratch/20260716-scale40-test08-09-then-standard-case01/command-manifest.yaml
test -f scratch/20260716-scale40-test08-09-then-standard-case01/run-ledger.md
find scratch/20260716-scale40-test08-09-then-standard-case01/cases -name experiment-spec.md | wc -l
```

Expected: all file checks succeed and the final count is `18`.

### Task 2: Add The Stage-2 Standard Case Runner With TDD

**Files:**
- Create: `scratch/pod1d/run_scripts/test_run_standard_case01_batch.py`
- Create: `scratch/pod1d/run_scripts/run_standard_case01_batch.py`

- [ ] **Step 1: Write failing tests**

Tests must require the exact eight test directories, `case01_标准topo`, preservation of `traffic.csv` bytes during preparation, canonical routing migration, and a command containing `--dependency-visibility-delay=10ns` without `--mtp-threads`.

- [ ] **Step 2: Verify RED**

Run:

```bash
python3.12 -m unittest scratch/pod1d/run_scripts/test_run_standard_case01_batch.py
```

Expected: failure because `run_standard_case01_batch` does not exist.

- [ ] **Step 3: Implement the minimal runner**

The runner must:

```python
TESTS = (
    "test01_tp_all_gather",
    "test02_cp_all_to_all",
    "test03_tp_reduce_scatter",
    "test04_tp_reduce_scatter",
    "test05_ep_all_to_all",
    "test06_pp_send_recv",
    "test10_epxetp_all_to_all",
    "test11_etp_all_reduce",
)
CASE = "case01_标准topo"
```

It must not call `scale_traffic`. It must hash `traffic.csv` before and after preparation and fail if the bytes change. It must run at most two processes, archive per-case console logs and `task_statistics.csv`, and write `fct_summary.csv` plus `results.md`.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
python3.12 -m unittest scratch/pod1d/run_scripts/test_run_standard_case01_batch.py
/home/a81257/miniconda3/bin/python -m unittest scratch/pod1d/run_scripts/test_run_standard_case01_batch.py
python3.12 -m py_compile scratch/pod1d/run_scripts/run_standard_case01_batch.py
```

Expected: all tests pass and compilation exits zero.

### Task 3: Execute Stage 1

**Files:**
- Output: `scratch/20260716-scale40-test08-09-then-standard-case01/artifacts/stage1_test08_09_scale40/`

- [ ] **Step 1: Run the ten-case scale40 matrix**

Run:

```bash
/home/a81257/miniconda3/bin/python \
  scratch/pod1d/run_scripts/run_test08_09_scale80_all_cases.py \
  --scale 40 --parallel 2 \
  --package-root scratch/20260716-scale40-test08-09-then-standard-case01 \
  --label stage1_test08_09_scale40
```

Expected: ten cases, zero failures, `6840/6840` completed in each row, and two single-panel five-curve CDFs.

- [ ] **Step 2: Verify stage-1 artifacts**

Check `fct_summary.csv`, ten archived `task_statistics.csv` files, two PNG files, two SVG files, and absence of fatal markers in console logs.

### Task 4: Execute Stage 2 After Stage 1

**Files:**
- Output: `scratch/20260716-scale40-test08-09-then-standard-case01/artifacts/stage2_standard_case01/`

- [ ] **Step 1: Confirm stage-1 success gate**

Do not start stage 2 unless stage 1 has ten return codes equal to zero and all expected tasks completed.

- [ ] **Step 2: Run the eight existing-traffic standard cases**

Run:

```bash
/home/a81257/miniconda3/bin/python \
  scratch/pod1d/run_scripts/run_standard_case01_batch.py \
  --parallel 2 \
  --package-root scratch/20260716-scale40-test08-09-then-standard-case01 \
  --label stage2_standard_case01
```

Expected: eight rows in `fct_summary.csv`, no traffic hash changes, and zero failed cases.

- [ ] **Step 3: Final verification**

Verify return codes, task counts, archived statistics, canonical routing attributes, `10ns` runtime switch, no MTP, and no fatal markers. Update `run-ledger.md` with measured statuses and paths.
