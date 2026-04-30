# ns-3-UB Release Notes

**Language**: [English](RELEASE_NOTES_UB_en.md) | [中文](RELEASE_NOTES_UB.md)

## Release 1.2.1

**Release Date**: April 2026

### Features and Behavior Changes

- Completed the unified hook architecture for congestion control and flow control. Congestion-control algorithms plug into sender, switch, and receiver events through hooks such as `OnSender*`, `OnSwitch*`, `OnReceiver*`, and `OnTpAttached`; flow-control algorithms plug into ingress, egress, control-frame, and data-credit events through hooks such as `OnIngress*`, `OnEgress*`, `OnControlFrameReceived`, and `OnDataPacketReceived`. Users can add custom algorithms while reusing the existing topology, queue, trace, and case configuration paths, keeping most algorithm logic inside the corresponding algorithm classes and required enum/config entries instead of making invasive changes to switch, transport, or case-template code. The current implementation supports DCQCN and C-AQM congestion control, plus CBFC and PFC flow control.
- Added RTP-side DCQCN support, plus `PFC_DYNAMIC_PAPER` as the paper-style dynamic PFC threshold reproduction mode for the DCQCN paper **"Congestion Control for Large-Scale RDMA Deployments"** (SIGCOMM 2015).
- `ub-quick-example` now stops early when `EnableRetrans=false` and a packet is dropped, with guidance to check routing, buffer, and flow-control settings instead of continuing a run that has no recovery path.

### Compatibility and Migration

- This release keeps copied `scratch` case migration in the release notes, with runtime diagnostics for common legacy configuration keys.
- `network_attribute.txt` is now scanned for known legacy keys before `ConfigStore` loads it, so copied cases get a migration hint. Known migrations include `ns3::UbQueueManager::ResumeOffset` -> `ns3::UbQueueManager::DynamicPfcResumeGapBytes`, `ns3::UbSwitch::EnableCBFC/EnablePFC` -> `ns3::UbSwitch::FlowControl`, and `ns3::UbApiThread::*` -> `ns3::UbLdstThread::*`.
- If an older case depends on the previous `CbfcRetCellGrainControlPacket=1` behavior, set that value explicitly in `network_attribute.txt`; the current repo default is `32`.
- Fine-grained trace files are controlled by new switches: `UB_QUEUE_TRACE_ENABLE`, `UB_FLOW_CONTROL_TRACE_ENABLE`, and `UB_CONGESTION_CONTROL_TRACE_ENABLE`. Older cases that omit them still run, but they do not automatically produce the corresponding `QueueTrace_*`, `PfcTrace_*`, `CbfcTrace_*`, `Dcqcn*`, or `Caqm*` files.

---

## Release 1.2.0

**Release Date**: March 2026

### New Features

- **OpenUSim Agent Skill System**: Introduced four-stage repository-bundled AI Agent Skills, enabling AI coding assistants (Codex / Claude Code / Cursor, etc.) to drive UB simulation experiments end-to-end. The four stages are: environment readiness check (welcome), experiment planning and parameter convergence (plan-experiment), case generation and simulation execution (run-experiment), and result interpretation with root-cause analysis (analyze-results). Includes an AGENTS.md routing policy, a shared knowledge base (topology options, workload patterns, trace observability, etc. — 7 reference documents), and automated simulation configuration scripts

- **Full URMA Read Data Path**: Implemented the complete URMA Read request/response data path. Read requests are sent with zero payload carrying logical byte counts; the remote side automatically generates a Read Response with the actual data. The transport layer supports multi-packet Read response reassembly and completion detection, while the transaction layer distinguishes Request/Response directions and correctly handles the different completion semantics of Read vs. Write

- **Flow Control and Buffer Management Overhaul**:
  - **Shared Buffer Dynamic Admission Control**: Redesigned ingress buffer management with a Reserve → Shared → Headroom three-tier admission model. Each ingress queue has a dedicated reserve quota; excess traffic competes for allocation from a global shared pool via dynamic thresholds (Alpha); under PFC, per-port headroom absorbs in-flight packets. Supports XOFF/XON watermark queries and anti-oscillation resume offset
  - **CBFC / PFC Flow Control Modes**: Flow control expanded to five modes — NONE, CBFC (exclusive credit), CBFC_SHARED (shared credit pool), PFC_FIXED (fixed-threshold backpressure), and PFC_DYNAMIC (buffer-occupancy-based dynamic-threshold backpressure). CBFC and PFC operate as peer flow control strategies sharing the same ingress admission model, selectable per scenario

- **MPI Multi-Process Data Path**: Added a remote link abstraction to support cross-process UB packet transmission via MPI, enabling distributed multi-process simulation. Combined with the unified quick-example entry point, supports MPI config-driven multi-host topology simulation

### Improvements

- **Simulation Stall Warning**: The case-runner monitors task completion progress in real time and emits a potential deadlock warning when no task completes for an extended period, helping quickly identify flow-control deadlocks or routing loops
- **Fine-Grained Tracing**: Module-level trace switches allow per-layer trace output to be enabled or disabled on demand, reducing I/O overhead in large-scale simulations
- **Observability Tier Presets**: Multiple observability presets enable one-click switching of log verbosity between quick validation and deep analysis scenarios
- **TrafficGen Thread Safety**: The traffic generator supports safe invocation under UNISON multi-threaded concurrent scheduling
- **TrafficGen URMA Read Support**: Traffic description files now support specifying the URMA_READ operation type
- **Unified Simulation Entry**: ub-quick-example restructured as a config-driven unified entry point supporting both MPI multi-process and MTP multi-threaded execution modes

### Bug Fixes

- Fixed fairness issue in TA-layer WQE Segment scheduling that caused some segments to starve
- Fixed multi-packet URMA Read request slicing reassembly logic to ensure data integrity
- Fixed incorrect port information in routing traces and VOQ index bounds checking
- Fixed unified-bus library link failures under certain build configurations
- Fixed race conditions during initialization, improving startup stability
- MPI-related tests are now conditionally compiled by build flags; non-MPI builds no longer fail

### Build & CI

- Simplified CI pipeline to Ubuntu single-platform
- Added uv.lock dependency lock file, pinned Python 3.11
- Updated ns-3-ub-tools submodule

### Tests

- Added regression tests for URMA Read, shared buffer admission, and MPI CBFC hybrid mode
- Added TrafficGen and quick-example entry boundary tests
- Added Agent Skill documentation and helper script tests
- ~2800 net new lines of test code

---

## Release 1.1.0

**Release Date**: January 2026

### New Features

- **UNISON Multi-threaded Parallel Simulation**: Integrated UNISON framework for multi-threaded parallel simulation
- **DWRR Scheduling Algorithm**: Added Deficit Weighted Round Robin (DWRR) based inter-VL scheduling support on both network and data link layers
- **Adaptive Routing**: Implemented port-load-aware adaptive routing with configurable routing attributes
- **Deadlock Detection**: Added potential deadlock detection in UB switch and transport layer with enhanced packet arrival time tracking
- **CBFC Credit-Shared Mode**: Introduced CBFC credit-shared mode for more flexible flow control configuration

### Optimizations & Bug Fixes

- Optimized DWRR user configuration method
- Refactored buffer management architecture with unified VOQ management (dual-view with egress statistics)
- Enhanced routing table lookup process
- Improved queue management with byte-limit based egress queue management
- Fixed LDST CBFC compatibility issues
- Optimized flow control configuration interface
- Fixed TP removal and credit resumption at switch allocator
- Support for automatic TP generation without configuration files
- Support for useless TP removal optimization

---

## Release 1.0.0

Initial release of ns-3-UB simulator implementing the UnifiedBus Base Specification with comprehensive protocol stack support across function, transaction, transport, network, and data link layers.

**Key Features:**
- Complete UB protocol stack implementation
- Support for Load/Store and URMA programming interfaces
- Congestion control and flow control mechanisms
- Multi-path routing and load balancing
- QoS support with SP scheduling
- Credit-based flow control with CBFC support
