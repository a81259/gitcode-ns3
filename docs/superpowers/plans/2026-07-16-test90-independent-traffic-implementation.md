# test90 Independent-Traffic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run a self-contained, serial test90 experiment that compares the five test09 topology variants using only scale80 traffic rows without phase dependencies.

**Architecture:** A dedicated Python runner copies the five formal test09 case inputs into test90, saves the unfiltered scale80 traffic as provenance, filters `traffic.csv` to rows with blank `dependOnPhases`, and launches `ub-quick-example` one case at a time. The runner archives per-case evidence, calculates FCT statistics, and renders one five-curve full-distribution CDF under test90.

**Tech Stack:** Python 3.12 standard library, Miniconda Matplotlib runtime, ns-3 `scratch/ub-quick-example`, CSV input/output.

---

## File Structure

- Create `scratch/pod1d/run_scripts/run_test90_independent_scale80.py`: owns source-to-test90 preparation, serial execution, FCT extraction, artifact archiving, CDF rendering, and result markdown.
- Create `scratch/pod1d/run_scripts/test_run_test90_independent_scale80.py`: standard-library unit tests for filtering, source snapshot creation, and serial job order.
- Create at runtime `scratch/pod1d/test90_dp_reduce_scatter_independent_scale80/case0*/`: isolated case inputs copied from test09.
- Create at runtime `scratch/pod1d/test90_dp_reduce_scatter_independent_scale80/artifacts/<label>/`: logs, task-statistics copies, input evidence, FCT CSV, markdown, and plots.
- Create at runtime `scratch/pod1d/test90_dp_reduce_scatter_independent_scale80/experiment-plan.md`: fixed experiment controls and interpretation boundary.

### Task 1: Add a test-first independent-traffic filter

**Files:**
- Create: `scratch/pod1d/run_scripts/test_run_test90_independent_scale80.py`
- Create: `scratch/pod1d/run_scripts/run_test90_independent_scale80.py`

- [ ] **Step 1: Write the failing filter test**

```python
def test_filter_independent_traffic_keeps_only_blank_dependencies(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.csv"
        destination = Path(tmp) / "filtered.csv"
        source.write_text(
            "taskId,sourceNode,destNode,dataSize(Byte),opType,priority,delay,phaseId,dependOnPhases\\n"
            "0,0,1,80,URMA_WRITE,7,10ns,0,\\n"
            "1,1,0,160,URMA_WRITE,7,10ns,1,  \\n"
            "2,2,3,240,URMA_WRITE,7,10ns,2,0\\n",
            encoding="utf-8",
        )

        summary = runner.filter_independent_traffic(source, destination)

        with destination.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([row["taskId"] for row in rows], ["0", "1"])
        self.assertEqual(summary.total_tasks, 3)
        self.assertEqual(summary.kept_tasks, 2)
        self.assertEqual(summary.removed_tasks, 1)
        self.assertEqual(summary.kept_bytes, 240)
```

- [ ] **Step 2: Run the test and confirm the missing-function failure**

Run:

```bash
python3.12 -m unittest scratch/pod1d/run_scripts/test_run_test90_independent_scale80.py
```

Expected: failure naming missing `filter_independent_traffic`.

- [ ] **Step 3: Implement the minimal CSV filter**

```python
@dataclass(frozen=True)
class FilterSummary:
    total_tasks: int
    kept_tasks: int
    removed_tasks: int
    total_bytes: int
    kept_bytes: int


def filter_independent_traffic(source: Path, destination: Path) -> FilterSummary:
    with source.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if "dependOnPhases" not in fieldnames:
            raise ValueError(f"{source} lacks dependOnPhases")
        rows = list(reader)
    kept = [row for row in rows if not row["dependOnPhases"].strip()]
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\\n")
        writer.writeheader()
        writer.writerows(kept)
    return FilterSummary(
        total_tasks=len(rows),
        kept_tasks=len(kept),
        removed_tasks=len(rows) - len(kept),
        total_bytes=sum(int(float(row["dataSize(Byte)"])) for row in rows),
        kept_bytes=sum(int(float(row["dataSize(Byte)"])) for row in kept),
    )
```

- [ ] **Step 4: Run the unit test and confirm it passes**

Run:

```bash
python3.12 -m unittest scratch/pod1d/run_scripts/test_run_test90_independent_scale80.py
```

Expected: all test methods pass.

### Task 2: Prepare isolated test90 cases and prove their inputs

**Files:**
- Modify: `scratch/pod1d/run_scripts/run_test90_independent_scale80.py`
- Modify: `scratch/pod1d/run_scripts/test_run_test90_independent_scale80.py`
- Create at runtime: `scratch/pod1d/test90_dp_reduce_scatter_independent_scale80/`

- [ ] **Step 1: Write the failing case-preparation test**

```python
def test_formal_case_names_are_processed_in_standard_then_fault_order(self) -> None:
    self.assertEqual(
        runner.CASES,
        (
            "case01_标准topo",
            "case02_故障1topo_单链路lane",
            "case03_故障2topo_单链路laport",
            "case04_故障3topo_分布式多链路port",
            "case05_故障4topo_分集中式多链路port",
        ),
    )
```

- [ ] **Step 2: Run the test and confirm the missing-constant failure**

Run:

```bash
python3.12 -m unittest scratch/pod1d/run_scripts/test_run_test90_independent_scale80.py
```

Expected: failure naming missing `CASES`.

- [ ] **Step 3: Implement preparation and input evidence**

```python
SOURCE_TEST = "test09_dp_reduce_scatter"
TARGET_TEST = "test90_dp_reduce_scatter_independent_scale80"
CASES = (
    "case01_标准topo",
    "case02_故障1topo_单链路lane",
    "case03_故障2topo_单链路laport",
    "case04_故障3topo_分布式多链路port",
    "case05_故障4topo_分集中式多链路port",
)
CASE_INPUTS = ("network_attribute.txt", "node.csv", "topology.csv", "routing_table.csv")


def prepare_case(case: str) -> FilterSummary:
    source = POD_ROOT / SOURCE_TEST / case
    target = POD_ROOT / TARGET_TEST / case
    target.mkdir(parents=True, exist_ok=True)
    for name in CASE_INPUTS:
        shutil.copy2(source / name, target / name)
    shutil.copy2(source / "traffic.csv", target / "traffic.scale80.source.csv")
    return filter_independent_traffic(target / "traffic.scale80.source.csv", target / "traffic.csv")
```

The implementation must reject a source workload that does not yield exactly
`1368` retained rows or contains a nonblank dependency after writing. It must
write a `traffic_filter_summary.csv` containing total/kept/removed task counts,
total/kept bytes, source SHA-256, and filtered SHA-256 for each of the five cases.

- [ ] **Step 4: Run all unit tests**

Run:

```bash
python3.12 -m unittest scratch/pod1d/run_scripts/test_run_test90_independent_scale80.py
```

Expected: all tests pass; test09 is not written.

### Task 3: Implement serial runner and FCT report

**Files:**
- Modify: `scratch/pod1d/run_scripts/run_test90_independent_scale80.py`
- Modify: `scratch/pod1d/run_scripts/test_run_test90_independent_scale80.py`
- Create at runtime: `scratch/pod1d/test90_dp_reduce_scatter_independent_scale80/artifacts/<label>/`

- [ ] **Step 1: Write the failing single-thread command test**

```python
def test_command_has_visibility_delay_and_no_mtp_threads(self) -> None:
    command = runner.build_command(runner.CASES[0])
    self.assertIn("--dependency-visibility-delay=10ns", command[-1])
    self.assertNotIn("--mtp-threads", command[-1])
```

- [ ] **Step 2: Run the test and confirm the missing-function failure**

Run:

```bash
python3.12 -m unittest scratch/pod1d/run_scripts/test_run_test90_independent_scale80.py
```

Expected: failure naming missing `build_command`.

- [ ] **Step 3: Implement serial execution and result extraction**

```python
def build_command(case: str) -> list[str]:
    case_path = (POD_ROOT / TARGET_TEST / case).relative_to(REPO_ROOT).as_posix()
    return [
        "python3.12", "./ns3", "run", "--no-build",
        f"scratch/ub-quick-example --case-path={case_path} "
        "--dependency-visibility-delay=10ns",
    ]


def run_serial(cases: tuple[str, ...], artifact_dir: Path) -> list[dict[str, str]]:
    results = []
    for case in cases:
        clean_case_output(case)
        log_path = artifact_dir / "console_logs" / f"{case}.log"
        completed = subprocess.run(
            build_command(case), cwd=REPO_ROOT, text=True,
            stdout=log_path.open("w", encoding="utf-8"),
            stderr=subprocess.STDOUT, check=False,
        )
        results.append(summarize_case(case, completed.returncode, artifact_dir, log_path))
    return results
```

`summary_case` must archive `output/task_statistics.csv`, compute mean/P95/max
from `taskCompletesTime(us) - taskStartTime(us)`, and record the 1368-task
completion ratio and return code.  The runner must stop and exit nonzero if a
case returns nonzero or completes fewer than 1368 tasks; it must not start a
later case after such a failure.

- [ ] **Step 4: Implement one-panel five-curve chart and human-readable result note**

```python
fig, axis = plt.subplots(figsize=(12.8, 7.2), constrained_layout=True)
for case in CASES:
    fcts = read_fcts(artifact_dir / "task_statistics" / case / "task_statistics.csv")
    axis.step(fcts, [(index + 1) / len(fcts) for index in range(len(fcts))],
              where="post", label=CASE_LABELS[case])
axis.set_title("test90 Task FCT empirical CDF — independent scale80 traffic")
axis.set_xlabel("Task FCT (us)")
axis.set_ylabel("Empirical CDF")
axis.set_ylim(0.0, 1.005)
axis.legend(loc="lower right")
```

Write PNG/SVG, `fct_summary.csv`, and `results.md` under the selected artifact
label.  Write `experiment-plan.md` at the test90 root with the source, filter,
fixed controls, task count, and simulation-only interpretation boundary.

- [ ] **Step 5: Run all runner tests and compile the runner**

Run:

```bash
python3.12 -m unittest scratch/pod1d/run_scripts/test_run_test90_independent_scale80.py
python3.12 -m py_compile scratch/pod1d/run_scripts/run_test90_independent_scale80.py
```

Expected: all tests pass and compilation exits 0.

### Task 4: Execute test90 and verify deliverables

**Files:**
- Create at runtime: `scratch/pod1d/test90_dp_reduce_scatter_independent_scale80/artifacts/test90_independent_scale80_serial/`

- [ ] **Step 1: Prepare test90 without simulation**

Run:

```bash
/home/a81257/miniconda3/bin/python scratch/pod1d/run_scripts/run_test90_independent_scale80.py \
  --prepare-only --label test90_prepare_verification
```

Expected: five cases each show `total_tasks=6840`, `kept_tasks=1368`, and zero
nonblank `dependOnPhases` values in their generated `traffic.csv`.

- [ ] **Step 2: Execute the five cases serially**

Run:

```bash
/home/a81257/miniconda3/bin/python scratch/pod1d/run_scripts/run_test90_independent_scale80.py \
  --label test90_independent_scale80_serial
```

Expected: start and finish messages appear in case order; only one child
simulation is active at any time.

- [ ] **Step 3: Verify the full artifact contract**

Run:

```bash
/home/a81257/miniconda3/bin/python -c 'import csv, pathlib
root = pathlib.Path("scratch/pod1d/test90_dp_reduce_scatter_independent_scale80/artifacts/test90_independent_scale80_serial")
rows = list(csv.DictReader((root / "fct_summary.csv").open()))
assert len(rows) == 5
assert all(row["returncode"] == "0" for row in rows)
assert all(row["completed_tasks"] == row["expected_tasks"] == "1368" for row in rows)
for row in rows:
    assert (root / row["task_statistics"]).is_file()
assert (root / "test90_task_fct_cdf.png").stat().st_size > 10000
assert (root / "test90_task_fct_cdf.svg").stat().st_size > 10000
print("verified 5 serial cases, 1368/1368 tasks, and two nonempty CDF files")'
```

Expected: verification text prints and exits 0.

- [ ] **Step 4: Inspect the CDF and report results**

Inspect the PNG with the image viewer. Report completed-task count, FCT mean,
P95, max, standard-relative deltas, exact artifact links, and the direct rerun
command. State explicitly that the plot has one full-distribution panel and
five curves.

## Commit Policy

Do not create a Git commit unless the user explicitly asks for one.
