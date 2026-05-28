# UB Retransmission Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move RTP retransmission policy, RTO handling, GBN state, selective retransmission state, and MarkPSN state from `UbTransportChannel` into a dedicated `ub-retrans.h/.cc` module.

**Architecture:** `UbTransportChannel` remains the common transport owner for packet parsing/building, queues, WQE segment lifecycle, receive buffering, congestion control, tracing, and transaction completion. `UbRetransController` owns retransmission configuration and RTO state, delegates GBN behavior to `UbGbnRetransStrategy`, and delegates selective behavior plus MarkPSN state to `UbSelectiveRetransStrategy`.

**Tech Stack:** C++17-style ns-3 module code, ns-3 `TypeId` attributes, `Ptr<Packet>`, `EventId`, `Simulator`, existing UnifiedBus transport tests.

---

## File Structure

- Create: `src/unified-bus/model/protocol/ub-retrans.h`
  - Declares `UbRetransController`, `UbRetransStrategy`, `UbGbnRetransStrategy`, `UbSelectiveRetransStrategy`, and result structs.
  - Owns retransmission-facing public APIs used by `UbTransportChannel`.

- Create: `src/unified-bus/model/protocol/ub-retrans.cc`
  - Implements RTO logic, GBN logic, selective retransmission logic, and MarkPSN logic.
  - Uses narrow `UbTransportChannel` methods for shared transport state.

- Modify: `src/unified-bus/model/protocol/ub-transport.h`
  - Adds `std::unique_ptr<UbRetransController> m_retrans`.
  - Removes retransmission-owned fields after each migration phase.
  - Adds forwarding methods used by ns-3 attributes and by `ub-retrans.cc`.

- Modify: `src/unified-bus/model/protocol/ub-transport.cc`
  - Constructs/disposes `m_retrans`.
  - Replaces inline retransmission branches in `GetNextPacket`, `RecvTpAck`, `RecvDataPacket`, and `ReTxTimeout` with controller calls.
  - Keeps packet parsing/building, ACK/CNP queues, WQE completion, tracing, congestion-control ownership, and transaction completion.

- Modify: `src/unified-bus/CMakeLists.txt`
  - Adds `model/protocol/ub-retrans.cc`.
  - Adds `model/protocol/ub-retrans.h` to headers if tests or other translation units include it directly.

- Modify: `src/unified-bus/test/ub-test.cc`
  - Update tests that used transport test-only accessors for retransmission state so they call forwarding accessors, or include `ub-retrans.h` if direct controller assertions are needed.

## Task 1: Add Empty Retrans Module

**Files:**
- Create: `src/unified-bus/model/protocol/ub-retrans.h`
- Create: `src/unified-bus/model/protocol/ub-retrans.cc`
- Modify: `src/unified-bus/CMakeLists.txt`

- [ ] **Step 1: Create the header skeleton**

Create `src/unified-bus/model/protocol/ub-retrans.h`:

```cpp
#ifndef UB_RETRANS_H
#define UB_RETRANS_H

#include "ns3/nstime.h"
#include "ns3/packet.h"
#include "ns3/ptr.h"
#include "ns3/ub-datatype.h"
#include "ns3/ub-header.h"

#include <cstdint>
#include <optional>

namespace ns3 {

class UbTransportChannel;
class UbWqeSegment;

struct UbRetransAckResult
{
    bool ackAdvanced{false};
    uint64_t previousSndUna{0};
    uint64_t newSndUna{0};
    bool triggerTransmit{false};
};

struct UbRetransReceiveDecision
{
    bool dropPacket{false};
    bool shouldAck{false};
    bool shouldNak{false};
    bool selectiveAck{false};
    bool suppressResponse{false};
    uint64_t responsePsn{0};
    TpOpcode responseOpcode{TpOpcode::TP_OPCODE_ACK_WITHOUT_CETPH};
    std::optional<UbSelectiveAckExtTph> selectiveAckHeader;
};

struct UbRetransTimeoutResult
{
    bool triggerTransmit{false};
};

class UbRetransStrategy
{
public:
    virtual ~UbRetransStrategy() = default;
};

class UbRetransController
{
public:
    explicit UbRetransController(UbTransportChannel& transport);

private:
    UbTransportChannel& m_transport;
};

} // namespace ns3

#endif // UB_RETRANS_H
```

- [ ] **Step 2: Create the implementation skeleton**

Create `src/unified-bus/model/protocol/ub-retrans.cc`:

```cpp
#include "ns3/ub-retrans.h"

#include "ns3/ub-transport.h"

namespace ns3 {

UbRetransController::UbRetransController(UbTransportChannel& transport)
    : m_transport(transport)
{
}

} // namespace ns3
```

- [ ] **Step 3: Register files in CMake**

Modify `src/unified-bus/CMakeLists.txt`:

```cmake
model/protocol/ub-retrans.cc
```

Add it near `model/protocol/ub-transport.cc`.

If public headers are listed, add:

```cmake
model/protocol/ub-retrans.h
```

near `model/protocol/ub-transport.h`.

- [ ] **Step 4: Build to verify empty module integration**

Run:

```bash
./ns3 build
```

Expected: build succeeds with no behavior changes.

- [ ] **Step 5: Commit**

```bash
git add src/unified-bus/model/protocol/ub-retrans.h \
        src/unified-bus/model/protocol/ub-retrans.cc \
        src/unified-bus/CMakeLists.txt
git commit -m "refactor(transport): add retransmission module skeleton"
```

## Task 2: Add Controller Ownership And Attribute Forwarding

**Files:**
- Modify: `src/unified-bus/model/protocol/ub-retrans.h`
- Modify: `src/unified-bus/model/protocol/ub-retrans.cc`
- Modify: `src/unified-bus/model/protocol/ub-transport.h`
- Modify: `src/unified-bus/model/protocol/ub-transport.cc`

- [ ] **Step 1: Extend controller configuration API**

In `ub-retrans.h`, extend `UbRetransController`:

```cpp
class UbRetransController
{
public:
    explicit UbRetransController(UbTransportChannel& transport);

    void SetInitialRto(Time rto);
    Time GetInitialRto() const;

    void SetMaxRetransAttempts(uint16_t attempts);
    uint16_t GetMaxRetransAttempts() const;

    void SetRetransExponentFactor(uint16_t factor);
    uint16_t GetRetransExponentFactor() const;

    void SetRetransmissionMode(UbRetransmissionMode mode);
    UbRetransmissionMode GetRetransmissionMode() const;

    void SetSelectiveAckBitmapBits(uint32_t bits);
    uint32_t GetSelectiveAckBitmapBitsConfig() const;

    void SetFastRetransEnable(bool enable);
    bool GetFastRetransEnable() const;

    void SetSelectiveMarkPsnEnable(bool enable);
    bool GetSelectiveMarkPsnEnable() const;

private:
    UbTransportChannel& m_transport;
    Time m_initialRto;
    Time m_rto;
    uint16_t m_maxRetransAttempts{7};
    uint16_t m_retransAttemptsLeft{7};
    uint16_t m_retransExponentFactor{1};
    UbRetransmissionMode m_retransmissionMode{UbRetransmissionMode::GBN};
    uint32_t m_selectiveAckBitmapBits{0};
    bool m_enableFastRetrans{false};
    bool m_enableSelectiveMarkPsn{false};
};
```

- [ ] **Step 2: Implement simple getters and setters**

In `ub-retrans.cc`:

```cpp
void
UbRetransController::SetInitialRto(Time rto)
{
    m_initialRto = rto;
    m_rto = rto;
}

Time
UbRetransController::GetInitialRto() const
{
    return m_initialRto;
}

void
UbRetransController::SetMaxRetransAttempts(uint16_t attempts)
{
    m_maxRetransAttempts = attempts;
    m_retransAttemptsLeft = attempts;
}

uint16_t
UbRetransController::GetMaxRetransAttempts() const
{
    return m_maxRetransAttempts;
}

void
UbRetransController::SetRetransExponentFactor(uint16_t factor)
{
    m_retransExponentFactor = factor;
}

uint16_t
UbRetransController::GetRetransExponentFactor() const
{
    return m_retransExponentFactor;
}

void
UbRetransController::SetRetransmissionMode(UbRetransmissionMode mode)
{
    m_retransmissionMode = mode;
}

UbRetransmissionMode
UbRetransController::GetRetransmissionMode() const
{
    return m_retransmissionMode;
}

void
UbRetransController::SetSelectiveAckBitmapBits(uint32_t bits)
{
    m_selectiveAckBitmapBits = bits;
}

uint32_t
UbRetransController::GetSelectiveAckBitmapBitsConfig() const
{
    return m_selectiveAckBitmapBits;
}

void
UbRetransController::SetFastRetransEnable(bool enable)
{
    m_enableFastRetrans = enable;
}

bool
UbRetransController::GetFastRetransEnable() const
{
    return m_enableFastRetrans;
}

void
UbRetransController::SetSelectiveMarkPsnEnable(bool enable)
{
    m_enableSelectiveMarkPsn = enable;
}

bool
UbRetransController::GetSelectiveMarkPsnEnable() const
{
    return m_enableSelectiveMarkPsn;
}
```

- [ ] **Step 3: Add transport ownership**

In `ub-transport.h`, include `<memory>` and forward-declare the controller if needed:

```cpp
#include <memory>

class UbRetransController;
```

Add a member:

```cpp
std::unique_ptr<UbRetransController> m_retrans;
```

Add forwarding methods:

```cpp
void SetInitialRto(Time rto);
Time GetInitialRto() const;
void SetMaxRetransAttempts(uint16_t attempts);
uint16_t GetMaxRetransAttempts() const;
void SetRetransExponentFactor(uint16_t factor);
uint16_t GetRetransExponentFactor() const;
void SetRetransmissionMode(UbRetransmissionMode mode);
UbRetransmissionMode GetRetransmissionMode() const;
void SetSelectiveAckBitmapBits(uint32_t bits);
uint32_t GetSelectiveAckBitmapBitsConfig() const;
void SetFastRetransEnable(bool enable);
bool GetFastRetransEnable() const;
void SetSelectiveMarkPsnEnable(bool enable);
bool GetSelectiveMarkPsnEnable() const;
```

- [ ] **Step 4: Construct controller**

In the `UbTransportChannel` constructor or initialization path in `ub-transport.cc`, add:

```cpp
m_retrans = std::make_unique<UbRetransController>(*this);
```

If the class currently has no explicit constructor body suitable for this, add initialization where other member initialization occurs.

- [ ] **Step 5: Implement forwarding methods**

In `ub-transport.cc`:

```cpp
void
UbTransportChannel::SetFastRetransEnable(bool enable)
{
    m_retrans->SetFastRetransEnable(enable);
}

bool
UbTransportChannel::GetFastRetransEnable() const
{
    return m_retrans->GetFastRetransEnable();
}
```

Repeat the same forwarding pattern for RTO, attempts, exponent factor, mode, selective ACK bitmap bits, and MarkPSN enable.

- [ ] **Step 6: Update TypeId accessors except EnableRetrans**

In `GetTypeId()`, remove the `EnableRetrans` `.AddAttribute(...)` block.

Change direct member accessors to method accessors:

```cpp
MakeTimeAccessor(&UbTransportChannel::SetInitialRto,
                 &UbTransportChannel::GetInitialRto)
```

```cpp
MakeUintegerAccessor(&UbTransportChannel::SetMaxRetransAttempts,
                     &UbTransportChannel::GetMaxRetransAttempts)
```

```cpp
MakeUintegerAccessor(&UbTransportChannel::SetRetransExponentFactor,
                     &UbTransportChannel::GetRetransExponentFactor)
```

```cpp
MakeEnumAccessor<UbRetransmissionMode>(&UbTransportChannel::SetRetransmissionMode,
                                       &UbTransportChannel::GetRetransmissionMode)
```

```cpp
MakeUintegerAccessor(&UbTransportChannel::SetSelectiveAckBitmapBits,
                     &UbTransportChannel::GetSelectiveAckBitmapBitsConfig)
```

```cpp
MakeBooleanAccessor(&UbTransportChannel::SetFastRetransEnable,
                    &UbTransportChannel::GetFastRetransEnable)
```

```cpp
MakeBooleanAccessor(&UbTransportChannel::SetSelectiveMarkPsnEnable,
                    &UbTransportChannel::GetSelectiveMarkPsnEnable)
```

- [ ] **Step 7: Keep old fields temporarily**

Do not remove old retransmission fields yet. Keep behavior unchanged until the relevant logic migrates.

- [ ] **Step 8: Build and run attribute-related tests**

Run:

```bash
./ns3 build
./test.py -s unified-bus
```

Expected: build succeeds. Existing tests pass, except any test that explicitly expects `EnableRetrans` to exist should be updated because the design removes that attribute.

- [ ] **Step 9: Commit**

```bash
git add src/unified-bus/model/protocol/ub-retrans.h \
        src/unified-bus/model/protocol/ub-retrans.cc \
        src/unified-bus/model/protocol/ub-transport.h \
        src/unified-bus/model/protocol/ub-transport.cc \
        src/unified-bus/test/ub-test.cc
git commit -m "refactor(transport): route retransmission attributes through controller"
```

## Task 3: Move RTO State And Timeout Handling

**Files:**
- Modify: `src/unified-bus/model/protocol/ub-retrans.h`
- Modify: `src/unified-bus/model/protocol/ub-retrans.cc`
- Modify: `src/unified-bus/model/protocol/ub-transport.h`
- Modify: `src/unified-bus/model/protocol/ub-transport.cc`

- [ ] **Step 1: Add timer API to controller**

In `ub-retrans.h`:

```cpp
void StartTimerIfNeeded();
void RestartTimerAfterAckProgress();
void CancelTimer();
UbRetransTimeoutResult OnTimeout();
bool HasTimerRunning() const;
```

Add private members:

```cpp
EventId m_retransEvent{};
```

Include:

```cpp
#include "ns3/event-id.h"
```

- [ ] **Step 2: Implement timer helpers**

In `ub-retrans.cc`:

```cpp
void
UbRetransController::StartTimerIfNeeded()
{
    if (!m_retransEvent.IsExpired()) {
        return;
    }
    m_rto = m_initialRto;
    m_retransEvent = Simulator::Schedule(m_rto, &UbRetransController::OnTimeout, this);
}

void
UbRetransController::RestartTimerAfterAckProgress()
{
    m_rto = m_initialRto;
    m_retransAttemptsLeft = m_maxRetransAttempts;
    m_retransEvent.Cancel();
    m_retransEvent = Simulator::Schedule(m_rto, &UbRetransController::OnTimeout, this);
}

void
UbRetransController::CancelTimer()
{
    m_retransEvent.Cancel();
}

bool
UbRetransController::HasTimerRunning() const
{
    return !m_retransEvent.IsExpired();
}
```

Include:

```cpp
#include "ns3/simulator.h"
```

- [ ] **Step 3: Implement timeout backoff shell**

In `ub-retrans.cc`:

```cpp
UbRetransTimeoutResult
UbRetransController::OnTimeout()
{
    m_retransAttemptsLeft--;
    uint64_t rto = m_rto.GetNanoSeconds();
    rto = rto << m_retransExponentFactor;
    m_rto = NanoSeconds(rto);
    NS_ASSERT_MSG(m_retransAttemptsLeft > 0, "Avaliable retransmission attempts exhausted.");

    UbRetransTimeoutResult result;
    result.triggerTransmit = true;
    m_retransEvent = Simulator::Schedule(m_rto, &UbRetransController::OnTimeout, this);
    return result;
}
```

Include:

```cpp
#include "ns3/log.h"
```

- [ ] **Step 4: Change send-side timer calls**

In `GetNextPacket()`, replace the current `if (m_isRetransEnable) { ... Schedule ... }` block after sending a new data packet with:

```cpp
m_retrans->StartTimerIfNeeded();
```

- [ ] **Step 5: Change ACK progress timer reset**

In `RecvTpAck()`, replace the current ACK-progress RTO reset block with:

```cpp
m_retrans->RestartTimerAfterAckProgress();
```

- [ ] **Step 6: Change flow completion timer cancellation**

Where transport currently cancels `m_retransEvent` after all flow data is acknowledged, replace with:

```cpp
m_retrans->CancelTimer();
```

- [ ] **Step 7: Keep mode-specific timeout behavior temporarily in transport**

For this task, `UbRetransController::OnTimeout()` only owns backoff and timer reschedule. The actual GBN/selective retransmission action may still call existing transport helpers until Tasks 4 and 5.

- [ ] **Step 8: Build and run retransmission tests**

Run:

```bash
./ns3 build
./test.py -s unified-bus
```

Expected: build succeeds and transport tests pass.

- [ ] **Step 9: Commit**

```bash
git add src/unified-bus/model/protocol/ub-retrans.h \
        src/unified-bus/model/protocol/ub-retrans.cc \
        src/unified-bus/model/protocol/ub-transport.h \
        src/unified-bus/model/protocol/ub-transport.cc
git commit -m "refactor(transport): move retransmission timer state"
```

## Task 4: Move GBN Strategy

**Files:**
- Modify: `src/unified-bus/model/protocol/ub-retrans.h`
- Modify: `src/unified-bus/model/protocol/ub-retrans.cc`
- Modify: `src/unified-bus/model/protocol/ub-transport.h`
- Modify: `src/unified-bus/model/protocol/ub-transport.cc`
- Modify: `src/unified-bus/test/ub-test.cc`

- [ ] **Step 1: Add GBN strategy class**

In `ub-retrans.h`:

```cpp
class UbGbnRetransStrategy : public UbRetransStrategy
{
public:
    explicit UbGbnRetransStrategy(UbRetransController& controller);

    void PrepareRetransmissionFromPsn(uint64_t psn);
    bool HandleTpNak(uint64_t nakPsn);
    UbRetransReceiveDecision OnDataPacketReceived(uint64_t psn);
    UbRetransTimeoutResult OnTimeout();
    void ClearNakSuppressionIfGapClosed(uint64_t recvNext);

private:
    UbRetransController& m_controller;
    uint64_t m_lastNakPsn{std::numeric_limits<uint64_t>::max()};
};
```

Include:

```cpp
#include <limits>
```

- [ ] **Step 2: Expose narrow transport methods for GBN**

In `ub-transport.h`, add methods used by GBN strategy:

```cpp
uint64_t GetPsnSndUna() const;
uint64_t GetPsnSndNxt() const;
void SetPsnSndNxt(uint64_t psn);
uint64_t GetPsnRecvNxt() const;
void ResetSegmentSendProgressFromPsn(uint64_t psn);
void TriggerTransportTransmit();
```

Implement in `ub-transport.cc` by wrapping existing state and the body of current `PrepareGbnRetransmissionFromPsn()`.

- [ ] **Step 3: Implement GBN retransmission rollback**

Move the body of `UbTransportChannel::PrepareGbnRetransmissionFromPsn` into:

```cpp
void
UbGbnRetransStrategy::PrepareRetransmissionFromPsn(uint64_t psn)
{
    if (psn < m_controller.GetTransport().GetPsnSndUna() ||
        psn >= m_controller.GetTransport().GetPsnSndNxt()) {
        return;
    }
    m_controller.GetTransport().SetPsnSndNxt(psn);
    m_controller.GetTransport().ResetSegmentSendProgressFromPsn(psn);
}
```

Add this controller accessor:

```cpp
UbTransportChannel& GetTransport();
const UbTransportChannel& GetTransport() const;
```

- [ ] **Step 4: Implement TPNAK sender handling**

In `ub-retrans.cc`:

```cpp
bool
UbGbnRetransStrategy::HandleTpNak(uint64_t nakPsn)
{
    if (!m_controller.GetFastRetransEnable()) {
        return false;
    }
    const auto& transport = m_controller.GetTransport();
    if (nakPsn < transport.GetPsnSndUna() || nakPsn >= transport.GetPsnSndNxt()) {
        return false;
    }
    PrepareRetransmissionFromPsn(nakPsn);
    return true;
}
```

- [ ] **Step 5: Implement receiver-side GBN out-of-order decision**

In `ub-retrans.cc`:

```cpp
UbRetransReceiveDecision
UbGbnRetransStrategy::OnDataPacketReceived(uint64_t psn)
{
    UbRetransReceiveDecision decision;
    const uint64_t expected = m_controller.GetTransport().GetPsnRecvNxt();
    if (!m_controller.GetFastRetransEnable() || psn <= expected) {
        decision.shouldAck = true;
        decision.responsePsn = expected == 0 ? 0 : expected - 1;
        return decision;
    }
    if (m_lastNakPsn == expected) {
        decision.dropPacket = true;
        decision.suppressResponse = true;
        return decision;
    }
    m_lastNakPsn = expected;
    decision.dropPacket = true;
    decision.shouldNak = true;
    decision.responsePsn = expected;
    decision.responseOpcode = TpOpcode::TP_OPCODE_NAK_WITHOUT_CETPH;
    return decision;
}
```

- [ ] **Step 6: Wire GBN into controller response handling**

In `UbRetransController::OnTransportResponse(...)`, route TPNAK to GBN strategy when mode is GBN. Return `triggerTransmit=true` if `HandleTpNak()` returns true.

```cpp
if (opcode == TpOpcode::TP_OPCODE_NAK_WITHOUT_CETPH &&
    m_retransmissionMode == UbRetransmissionMode::GBN) {
    UbRetransAckResult result;
    result.triggerTransmit = m_gbn->HandleTpNak(tph.GetPsn());
    return result;
}
```

- [ ] **Step 7: Wire GBN timeout**

In `UbRetransController::OnTimeout()`, after common backoff:

```cpp
if (m_retransmissionMode == UbRetransmissionMode::GBN) {
    m_gbn->PrepareRetransmissionFromPsn(m_transport.GetPsnSndUna());
    result.triggerTransmit = true;
    return result;
}
```

- [ ] **Step 8: Remove GBN-specific state from transport**

Remove:

```cpp
uint64_t m_lastGbnNakPsn;
void PrepareGbnRetransmissionFromPsn(uint64_t psn);
```

Keep any test accessor as a forwarding method if tests need it.

- [ ] **Step 9: Build and run GBN-focused tests**

Run:

```bash
./ns3 build
./test.py -s unified-bus
```

Run GBN scratch cases if available:

```bash
./ns3 run --no-build "scratch/retrans/GBN_fast"
./ns3 run --no-build "scratch/retrans/GBN_unfast"
```

Expected: GBN tests and scenarios preserve prior behavior.

- [ ] **Step 10: Commit**

```bash
git add src/unified-bus/model/protocol/ub-retrans.h \
        src/unified-bus/model/protocol/ub-retrans.cc \
        src/unified-bus/model/protocol/ub-transport.h \
        src/unified-bus/model/protocol/ub-transport.cc \
        src/unified-bus/test/ub-test.cc
git commit -m "refactor(transport): move GBN retransmission strategy"
```

## Task 5: Move Selective Sent-PSN State And ACK Processing

**Files:**
- Modify: `src/unified-bus/model/protocol/ub-retrans.h`
- Modify: `src/unified-bus/model/protocol/ub-retrans.cc`
- Modify: `src/unified-bus/model/protocol/ub-transport.h`
- Modify: `src/unified-bus/model/protocol/ub-transport.cc`
- Modify: `src/unified-bus/test/ub-test.cc`

- [ ] **Step 1: Add selective state and strategy class**

In `ub-retrans.h`:

```cpp
class UbSelectiveRetransStrategy : public UbRetransStrategy
{
public:
    explicit UbSelectiveRetransStrategy(UbRetransController& controller);

    void RetainSentPsn(uint64_t psn,
                       Ptr<Packet> packet,
                       uint32_t payloadBytes,
                       uint32_t logicalBytes,
                       Ptr<UbWqeSegment> segment);
    void MarkPsnAcked(uint64_t psn);
    void AcknowledgeCumulativePsn(uint64_t ackPsn);
    void AdvanceSendUnaFromAckState();
    std::vector<uint64_t> CollectMissingPsnsFromSelectiveAck(const UbTransportHeader& tpHeader,
                                                             const UbSelectiveAckExtTph& saetph);
    std::vector<uint64_t> GetMissingPsnsFromSelectiveAck(const UbTransportHeader& tpHeader,
                                                         const UbSelectiveAckExtTph& saetph) const;
    bool QueueRetransmission(uint64_t psn);
    void CompactRetransmissionQueue();
    Ptr<Packet> TryGetNextRetransmissionPacket();
    UbRetransTimeoutResult OnTimeout();

private:
    struct SentPsnState
    {
        Ptr<Packet> packet;
        uint32_t payloadBytes{0};
        uint32_t logicalBytes{0};
        Ptr<UbWqeSegment> segment;
        bool acknowledged{false};
        bool selectivelyReportedMissing{false};
        bool retransmitPending{false};
        uint32_t retransmitCount{0};
    };

    UbRetransController& m_controller;
    std::map<uint64_t, SentPsnState> m_sentPsnState;
    std::deque<uint64_t> m_selectiveRetransmitQ;
};
```

Include:

```cpp
#include <deque>
#include <map>
#include <vector>
```

- [ ] **Step 2: Move RetainSentPsn**

Move current `UbTransportChannel::RetainSentPsn` logic into:

```cpp
void
UbSelectiveRetransStrategy::RetainSentPsn(uint64_t psn,
                                          Ptr<Packet> packet,
                                          uint32_t payloadBytes,
                                          uint32_t logicalBytes,
                                          Ptr<UbWqeSegment> segment)
{
    SentPsnState& state = m_sentPsnState[psn];
    state.packet = packet == nullptr ? nullptr : packet->Copy();
    state.payloadBytes = payloadBytes;
    state.logicalBytes = logicalBytes;
    state.segment = segment;
    state.acknowledged = false;
    state.selectivelyReportedMissing = false;
    state.retransmitPending = false;
    state.retransmitCount = 0;
}
```

- [ ] **Step 3: Move ACK-state helpers**

Move `MarkPsnAcked`, `AcknowledgeCumulativePsn`, and `AdvanceSendUnaFromAckState` into the strategy.

When advancing `SndUna`, use:

```cpp
m_controller.GetTransport().SetPsnSndUna(nextUna);
```

Add `SetPsnSndUna(uint64_t psn)` to `UbTransportChannel` if it does not already exist outside test code.

- [ ] **Step 4: Move missing-PSN helpers**

Move `CollectMissingPsnsFromSelectiveAck` and `GetMissingPsnsFromSelectiveAck` into the strategy unchanged except for references to moved state.

- [ ] **Step 5: Move selective queue helpers**

Move `QueueSelectiveRetransmission`, `CompactSelectiveRetransmissionQueue`, `HasPendingSelectiveRetransmission`, `CanSendSelectiveRetransmission`, `GetNextSelectiveRetransmissionSize`, and `GetNextSelectiveRetransmissionLogicalBytes` into `UbSelectiveRetransStrategy`.

Rename internally to shorter names if desired:

```cpp
QueueRetransmission
CompactRetransmissionQueue
HasPendingRetransmission
CanSendRetransmission
GetNextRetransmissionSize
GetNextRetransmissionLogicalBytes
```

- [ ] **Step 6: Implement selective retransmission dequeue**

Move the selective retransmission branch from `GetNextPacket()` into:

```cpp
Ptr<Packet>
UbSelectiveRetransStrategy::TryGetNextRetransmissionPacket()
{
    while (CanSendRetransmission()) {
        const uint64_t psn = m_selectiveRetransmitQ.front();
        auto it = m_sentPsnState.find(psn);
        if (it == m_sentPsnState.end() || it->second.acknowledged || it->second.packet == nullptr) {
            m_selectiveRetransmitQ.pop_front();
            continue;
        }
        const uint32_t logicalBytes = it->second.logicalBytes == 0 ? UB_MTU_BYTE : it->second.logicalBytes;
        if (m_controller.GetTransport().IsCcLimitedForRetransmission(logicalBytes)) {
            m_controller.GetTransport().SetSendWindowLimited(true);
            return nullptr;
        }
        m_selectiveRetransmitQ.pop_front();
        it->second.retransmitPending = false;
        it->second.retransmitCount++;
        m_controller.GetTransport().OnSelectiveRetransmissionPacketSent(psn,
                                                                        logicalBytes,
                                                                        it->second.payloadBytes);
        return it->second.packet->Copy();
    }
    return nullptr;
}
```

Add the narrow transport wrappers used above.

- [ ] **Step 7: Wire new data send retain**

In `UbRetransController::OnNewDataPacketSent(...)`:

```cpp
if (m_retransmissionMode == UbRetransmissionMode::SELECTIVE) {
    m_selective->RetainSentPsn(psn, packet, payloadBytes, logicalBytes, segment);
}
```

In `GetNextPacket()`, replace direct `RetainSentPsn(...)` with controller call.

- [ ] **Step 8: Wire TPSACK sender processing**

Move the selective `hasSaetph` block from `RecvTpAck()` into `UbSelectiveRetransStrategy`.

Return:

```cpp
UbRetransAckResult{.ackAdvanced = ..., .previousSndUna = ..., .newSndUna = ..., .triggerTransmit = ...}
```

Use transport wrappers for congestion-control callbacks:

```cpp
m_controller.GetTransport().OnSenderSelectiveAck(...);
```

- [ ] **Step 9: Wire TPACK sender processing for selective mode**

Move selective ordinary TPACK handling into strategy:

```cpp
AcknowledgeCumulativePsn(tpHeader.GetPsn());
AdvanceSendUnaFromAckState();
```

- [ ] **Step 10: Remove selective sender state from transport**

Remove from `UbTransportChannel`:

```cpp
std::map<uint64_t, SentPsnState> m_sentPsnState;
std::deque<uint64_t> m_selectiveRetransmitQ;
```

Forward existing test-only accessors to the selective strategy through `UbRetransController`.

- [ ] **Step 11: Build and run selective tests**

Run:

```bash
./ns3 build
./test.py -s unified-bus
```

Expected: selective receiver/sender tests pass.

- [ ] **Step 12: Commit**

```bash
git add src/unified-bus/model/protocol/ub-retrans.h \
        src/unified-bus/model/protocol/ub-retrans.cc \
        src/unified-bus/model/protocol/ub-transport.h \
        src/unified-bus/model/protocol/ub-transport.cc \
        src/unified-bus/test/ub-test.cc
git commit -m "refactor(transport): move selective retransmission state"
```

## Task 6: Move Selective Receiver ACK Bitmap Logic

**Files:**
- Modify: `src/unified-bus/model/protocol/ub-retrans.h`
- Modify: `src/unified-bus/model/protocol/ub-retrans.cc`
- Modify: `src/unified-bus/model/protocol/ub-transport.cc`

- [ ] **Step 1: Move bitmap configuration resolution**

Move `ResolveSelectiveAckBitmapBits` and `GetSelectiveAckBitmapBits` into `UbSelectiveRetransStrategy` or `UbRetransController`.

Use transport wrapper:

```cpp
uint32_t GetPsnOooThreshold() const;
```

to preserve automatic bitmap width from `TpOooThreshold`.

- [ ] **Step 2: Move ACK base and header construction**

Move:

```cpp
GetSelectiveAckBase
BuildSelectiveAckHeader
```

into `UbSelectiveRetransStrategy`.

Use transport wrappers:

```cpp
bool HasReceiveGap() const;
uint64_t GetCumulativeAckPsn() const;
bool ReceiveWindowContains(uint64_t psn) const;
uint64_t GetMaxRcvPsn() const;
```

- [ ] **Step 3: Implement selective receiver decision**

In `UbSelectiveRetransStrategy`, add:

```cpp
UbRetransReceiveDecision BuildReceiveDecisionForCurrentState();
```

Implementation:

```cpp
UbRetransReceiveDecision decision;
const bool selectiveAck = m_controller.GetTransport().HasReceiveGap();
if (!selectiveAck) {
    decision.shouldAck = true;
    decision.responsePsn = m_controller.GetTransport().GetCumulativeAckPsn();
    decision.responseOpcode = m_controller.GetTransport().GetResponseOpcodeForRetrans(false);
    return decision;
}

uint32_t bits = 0;
if (!ResolveSelectiveAckBitmapBits(bits)) {
    decision.suppressResponse = true;
    return decision;
}

const uint64_t ackBase = GetSelectiveAckBase();
decision.shouldAck = true;
decision.selectiveAck = true;
decision.responsePsn = ackBase;
decision.responseOpcode = m_controller.GetTransport().GetResponseOpcodeForRetrans(true);
decision.selectiveAckHeader = BuildSelectiveAckHeader(ackBase);
return decision;
```

- [ ] **Step 4: Replace duplicate ACK-building decisions in RecvDataPacket**

In `RecvDataPacket()`, keep packet parsing and ACK packet construction in transport, but replace duplicated selective ACK decision logic with:

```cpp
UbRetransReceiveDecision decision = m_retrans->BuildReceiveDecisionForCurrentState();
if (decision.suppressResponse) {
    return;
}
QueueTransportResponse(decision, pktHeader, NetworkHeader, ipv4Header, udpHeader, TaHeader, flowTag);
```

- [ ] **Step 5: Build and run receiver tests**

Run:

```bash
./ns3 build
./test.py -s unified-bus
```

Expected: receiver ACK/TPSACK tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/unified-bus/model/protocol/ub-retrans.h \
        src/unified-bus/model/protocol/ub-retrans.cc \
        src/unified-bus/model/protocol/ub-transport.cc
git commit -m "refactor(transport): move selective ACK decisions"
```

## Task 7: Move MarkPSN State Machine

**Files:**
- Modify: `src/unified-bus/model/protocol/ub-retrans.h`
- Modify: `src/unified-bus/model/protocol/ub-retrans.cc`
- Modify: `src/unified-bus/model/protocol/ub-transport.h`
- Modify: `src/unified-bus/model/protocol/ub-transport.cc`
- Modify: `src/unified-bus/test/ub-test.cc`

- [ ] **Step 1: Add MarkPSN fields to selective strategy**

In `UbSelectiveRetransStrategy`:

```cpp
bool m_markPsnRetransPhase{false};
bool m_markPsnAwaitingFirstNew{true};
bool m_markPsnValid{false};
uint64_t m_markPsn{0};
bool m_lastFirstRtxPsnValid{false};
uint64_t m_lastFirstRtxPsn{0};
```

- [ ] **Step 2: Move MarkPSN helper methods**

Move:

```cpp
IsSelectiveMarkPsnEnabled
SelectiveAckReportsReceivedAtOrAboveMarkPsn
EnterSelectiveMarkPsnRetransPhase
FinishSelectiveMarkPsnRetransPhaseIfDone
MaybeMarkFirstNewSelectivePacket
```

into `UbSelectiveRetransStrategy`.

Rename `IsSelectiveMarkPsnEnabled` to:

```cpp
bool IsMarkPsnEnabled() const;
```

Use controller state:

```cpp
return m_controller.GetSelectiveMarkPsnEnable() &&
       m_controller.GetRetransmissionMode() == UbRetransmissionMode::SELECTIVE &&
       m_controller.GetFastRetransEnable();
```

- [ ] **Step 3: Update new packet send path**

In `UbSelectiveRetransStrategy::OnNewDataPacketSent(...)`:

```cpp
if (IsMarkPsnEnabled()) {
    MaybeMarkFirstNewSelectivePacket(psn);
}
RetainSentPsn(psn, packet, payloadBytes, logicalBytes, segment);
```

- [ ] **Step 4: Update selective retransmission dequeue**

When sending a selective retransmission for a PSN whose `retransmitCount == 0`, set:

```cpp
m_lastFirstRtxPsn = psn;
m_lastFirstRtxPsnValid = true;
```

Call:

```cpp
FinishMarkPsnRetransPhaseIfDone();
```

after popping stale queue entries and after sending a retransmission.

- [ ] **Step 5: Update TPSACK processing**

When processing TPSACK:

```cpp
const std::vector<uint64_t> allMissingPsns = GetMissingPsnsFromSelectiveAck(tpHeader, saetph);
if (SelectiveAckReportsReceivedAtOrAboveMarkPsn(tpHeader, saetph)) {
    EnterMarkPsnRetransPhase();
}
```

When fast retransmission is enabled:

```cpp
const std::vector<uint64_t>& candidatePsns =
    IsMarkPsnEnabled() ? allMissingPsns : missingPsns;
for (uint64_t psn : candidatePsns) {
    if (IsMarkPsnEnabled() && !m_markPsnRetransPhase) {
        continue;
    }
    queuedFastRetransmission = QueueRetransmission(psn) || queuedFastRetransmission;
}
```

- [ ] **Step 6: Remove MarkPSN fields from transport**

Remove:

```cpp
m_selectiveMarkPsnRetransPhase
m_selectiveMarkPsnAwaitingFirstNew
m_selectiveMarkPsnValid
m_selectiveMarkPsn
m_lastFirstSelectiveRtxPsnValid
m_lastFirstSelectiveRtxPsn
```

Forward tests through controller/strategy if needed.

- [ ] **Step 7: Build and run MarkPSN cases**

Run:

```bash
./ns3 build
./test.py -s unified-bus
```

Run selective fast MarkPSN scratch case:

```bash
./ns3 run --no-build "scratch/retrans/SELE_fast/non_first_tp_packet_loss_markpsn"
```

Expected: MarkPSN case still performs fast re-retransmission without waiting for RTO.

- [ ] **Step 8: Commit**

```bash
git add src/unified-bus/model/protocol/ub-retrans.h \
        src/unified-bus/model/protocol/ub-retrans.cc \
        src/unified-bus/model/protocol/ub-transport.h \
        src/unified-bus/model/protocol/ub-transport.cc \
        src/unified-bus/test/ub-test.cc
git commit -m "refactor(transport): move selective MarkPSN state"
```

## Task 8: Simplify Transport Entry Points

**Files:**
- Modify: `src/unified-bus/model/protocol/ub-transport.cc`
- Modify: `src/unified-bus/model/protocol/ub-transport.h`
- Modify: `src/unified-bus/model/protocol/ub-retrans.h`
- Modify: `src/unified-bus/model/protocol/ub-retrans.cc`

- [ ] **Step 1: Simplify GetNextPacket**

Ensure `GetNextPacket()` follows this shape:

```cpp
if (!m_cnpQ.empty()) {
    return PopCnpPacket();
}
if (!m_ackQ.empty()) {
    return PopAckPacket();
}
if (Ptr<Packet> retransmission = m_retrans->TryGetNextRetransmissionPacket()) {
    if (!IsEmpty()) {
        m_headArrivalTime = Simulator::Now();
    }
    return retransmission;
}
return TryGetNextNewDataPacket();
```

Create `PopCnpPacket`, `PopAckPacket`, and `TryGetNextNewDataPacket` only if the existing function remains hard to read after strategy migration.

- [ ] **Step 2: Simplify RecvTpAck**

Keep only:

- null packet guard
- header parsing
- CNP handling
- malformed TPSACK handling
- trace notification
- call to `m_retrans->OnTransportResponse(...)`
- common ACK progress effects
- WQE segment completion loop

Remove GBN/Selective mode branches that now live in strategies.

- [ ] **Step 3: Simplify RecvDataPacket**

Keep only:

- header parsing
- data trace
- last-packet receive notification
- repeat/out-of-order/common receive-window state updates
- inbound TA tracking
- call to retrans receive-decision helper
- ACK/NAK/TPSACK packet construction from returned decision
- completed TA unit notification

Remove GBN/Selective decision logic from the body.

- [ ] **Step 4: Simplify ReTxTimeout**

Replace body with:

```cpp
void
UbTransportChannel::ReTxTimeout()
{
    const UbRetransTimeoutResult result = m_retrans->OnTimeout();
    if (result.triggerTransmit) {
        TriggerTransportTransmit();
    }
}
```

If the controller directly triggers transmit through `UbTransportChannel`, document that and keep `ReTxTimeout()` as:

```cpp
m_retrans->OnTimeout();
```

- [ ] **Step 5: Remove obsolete transport fields and declarations**

Remove all moved retransmission fields and private methods from `ub-transport.h`.

Keep test-only accessors only if tests still use them, and implement them as forwarding methods to `m_retrans`.

- [ ] **Step 6: Build and run full focused tests**

Run:

```bash
./ns3 build
./test.py -s unified-bus
```

Expected: build succeeds and tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/unified-bus/model/protocol/ub-transport.h \
        src/unified-bus/model/protocol/ub-transport.cc \
        src/unified-bus/model/protocol/ub-retrans.h \
        src/unified-bus/model/protocol/ub-retrans.cc
git commit -m "refactor(transport): simplify retransmission entry points"
```

## Task 9: Validate Scenario Behavior

**Files:**
- Modify: `scratch/retrans/retrans_update_summary.md` only if behavior notes need updating.

- [ ] **Step 1: Run GBN fast scenario family**

Run the existing GBN fast cases the project uses for retransmission validation.

Example command pattern:

```bash
./ns3 run --no-build "scratch/retrans/GBN_fast/first_tp_packet_loss"
```

Expected: first data loss triggers TPNAK-driven GBN fast retransmission; tail data loss still waits for RTO.

- [ ] **Step 2: Run GBN unfast scenario family**

Run:

```bash
./ns3 run --no-build "scratch/retrans/GBN_unfast/first_tp_packet_loss"
```

Expected: no TPNAK fast recovery; actual loss waits for RTO; out-of-order without real loss can complete through cumulative TPACK.

- [ ] **Step 3: Run selective fast scenario family**

Run:

```bash
./ns3 run --no-build "scratch/retrans/SELE_fast/first_tp_packet_loss"
./ns3 run --no-build "scratch/retrans/SELE_fast/non_first_tp_packet_loss_markpsn"
```

Expected: first loss uses TPSACK sparse retransmission; MarkPSN case detects non-first loss quickly when MarkPSN evidence arrives.

- [ ] **Step 4: Run selective unfast scenario family**

Run:

```bash
./ns3 run --no-build "scratch/retrans/SELE_unfast/first_tp_packet_loss"
./ns3 run --no-build "scratch/retrans/SELE_unfast/out_of_order_no_actual_loss"
```

Expected: TPSACK updates sender state but does not immediately retransmit; actual loss waits for RTO.

- [ ] **Step 5: Inspect traces for preserved response types**

Check ACK traces still include:

```text
ACK(PSN=...)
NAK(PSN=...)
SACK(PSN=...,MAX=...,BM=...)
```

Expected: trace formatting and packet classification remain unchanged.

- [ ] **Step 6: Commit docs only if validation notes changed**

If `scratch/retrans/retrans_update_summary.md` changes:

```bash
git add scratch/retrans/retrans_update_summary.md
git commit -m "docs: update retransmission validation notes"
```

If no docs changed, do not create an empty commit.

## Self-Review

Spec coverage:

- Dedicated `ub-retrans.h/.cc`: covered by Tasks 1 and 2.
- RTO migration: covered by Task 3.
- GBN strategy and state migration: covered by Task 4.
- Selective state and queue migration: covered by Task 5.
- Selective receiver ACK bitmap behavior: covered by Task 6.
- MarkPSN state migration: covered by Task 7.
- Transport cleanup: covered by Task 8.
- Scenario validation: covered by Task 9.
- Default behavior is GBN non-fast retransmission with no `EnableRetrans` business switch: covered by Task 2.

Placeholder scan:

- No task contains unresolved placeholder markers.
- Code steps include concrete skeletons or exact migration targets.

Type consistency:

- `UbRetransController`, `UbRetransStrategy`, `UbGbnRetransStrategy`, and `UbSelectiveRetransStrategy` names match the approved design.
- `SetFastRetransEnable` and `GetFastRetransEnable` match the Attribute compatibility section.
- `UbRetransAckResult`, `UbRetransReceiveDecision`, and `UbRetransTimeoutResult` are used consistently across tasks.
