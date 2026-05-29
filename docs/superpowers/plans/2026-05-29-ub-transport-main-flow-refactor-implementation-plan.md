# UB Transport Main Flow Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `RecvTpAck()` and `TryGetNextNewDataPacket()` so they keep only the main protocol/send flow while branch handling and state updates move into named private helpers.

**Architecture:** Keep all behavior inside `UbTransportChannel`; do not introduce a new file or alter retransmission policy. Add small context structs in `ub-transport.h`, then extract helpers in `ub-transport.cc` in behavior-preserving steps with build/test checkpoints after each functional slice.

**Tech Stack:** C++17-style ns-3 code, `Ptr<Packet>`, ns-3 headers/tags, existing `UbRetransController`, existing ns-3 test runner and scratch scenarios.

---

## File Structure

- Modify: `src/unified-bus/model/protocol/ub-transport.h`
  - Add `TransportResponseContext` for decoded TP ACK/CNP/NAK/SACK packets.
  - Add `NewDataSendContext` for one new data packet send attempt.
  - Add private helper declarations for the extracted receive and send flow steps.

- Modify: `src/unified-bus/model/protocol/ub-transport.cc`
  - Implement parser/handler helpers near the existing `RecvTpAck()` region.
  - Implement new-data send helpers near `TryGetNextNewDataPacket()`.
  - Keep wire format, trace events, retrans controller calls, congestion control calls, and timer behavior unchanged.

- No planned test file changes.
  - This is a refactor. Verification uses existing focused tests and representative retransmission scenarios.

## Task 1: Add Context Types And ACK Response Parser

**Files:**
- Modify: `src/unified-bus/model/protocol/ub-transport.h`
- Modify: `src/unified-bus/model/protocol/ub-transport.cc`

- [ ] **Step 1: Add `TransportResponseContext` and parser declaration**

In `src/unified-bus/model/protocol/ub-transport.h`, inside the private section after `AckResponseContext`, add:

```cpp
struct TransportResponseContext
{
    Ptr<Packet> packet;
    UbTransportHeader transportHeader;
    UbAckTransactionHeader ackTransactionHeader;
    UbCongestionExtTph congestionHeader;
    UbSelectiveAckExtTph selectiveAckHeader;
    UbCnpExtTph cnpHeader;
    TpOpcode opcode{TpOpcode::TP_OPCODE_ACK_WITHOUT_CETPH};
    bool hasCetph{false};
    bool hasSaetph{false};
    bool isTpnak{false};
    bool isCnp{false};
};
```

Then add this private helper declaration near the existing receive helpers:

```cpp
bool ParseTransportResponsePacket(Ptr<Packet> packet, TransportResponseContext& ctx);
```

- [ ] **Step 2: Implement `ParseTransportResponsePacket()`**

In `src/unified-bus/model/protocol/ub-transport.cc`, place this helper immediately before `RecvTpAck()`:

```cpp
bool
UbTransportChannel::ParseTransportResponsePacket(Ptr<Packet> packet,
                                                 TransportResponseContext& ctx)
{
    if (packet == nullptr) {
        NS_LOG_ERROR("Null ack packet received");
        return false;
    }

    ctx.packet = packet;
    packet->RemoveHeader(ctx.transportHeader);
    ctx.opcode = static_cast<TpOpcode>(ctx.transportHeader.GetTPOpcode());
    ctx.isCnp = ctx.opcode == TpOpcode::TP_OPCODE_CNP;
    ctx.hasCetph = ctx.opcode == TpOpcode::TP_OPCODE_ACK_WITH_CETPH ||
                   ctx.opcode == TpOpcode::TP_OPCODE_SACK_WITH_CETPH;
    ctx.hasSaetph = ctx.opcode == TpOpcode::TP_OPCODE_SACK_WITHOUT_CETPH ||
                    ctx.opcode == TpOpcode::TP_OPCODE_SACK_WITH_CETPH;
    ctx.isTpnak = ctx.opcode == TpOpcode::TP_OPCODE_NAK_WITHOUT_CETPH;

    if (ctx.isCnp) {
        packet->RemoveHeader(ctx.cnpHeader);
        return true;
    }

    if (ctx.hasCetph) {
        packet->RemoveHeader(ctx.congestionHeader);
    }
    if (ctx.hasSaetph) {
        try
        {
            packet->RemoveHeader(ctx.selectiveAckHeader);
        }
        catch (const std::invalid_argument& e)
        {
            NS_LOG_WARN("Dropping malformed TPSACK: " << e.what());
            return false;
        }
    }
    packet->RemoveHeader(ctx.ackTransactionHeader);
    return true;
}
```

- [ ] **Step 3: Replace inline parsing in `RecvTpAck()` with context fields**

Change the beginning of `RecvTpAck()` from local header removal to:

```cpp
TransportResponseContext ctx;
if (!ParseTransportResponsePacket(p, ctx)) {
    return;
}
```

Then replace local variables inside `RecvTpAck()`:

```cpp
TpHeader -> ctx.transportHeader
opcode -> ctx.opcode
hasCetph -> ctx.hasCetph
hasSaetph -> ctx.hasSaetph
isTpnak -> ctx.isTpnak
CETPH -> ctx.congestionHeader
SAETPH -> ctx.selectiveAckHeader
```

The CNP branch still stays inline in this task, but it must use `ctx.cnpHeader` and `ctx.transportHeader`.

- [ ] **Step 4: Verify parser-only refactor**

Run:

```bash
./ns3 build
./test.py -s unified-bus-transport-ooo-regression
git diff --check
```

Expected:

```text
Build finished successfully
PASS: TestSuite unified-bus-transport-ooo-regression
```

- [ ] **Step 5: Commit**

```bash
git add src/unified-bus/model/protocol/ub-transport.h src/unified-bus/model/protocol/ub-transport.cc
git commit -m "refactor(transport): parse transport response context"
```

## Task 2: Extract CNP And TPNAK Early Return Handlers

**Files:**
- Modify: `src/unified-bus/model/protocol/ub-transport.h`
- Modify: `src/unified-bus/model/protocol/ub-transport.cc`

- [ ] **Step 1: Add helper declarations**

In `src/unified-bus/model/protocol/ub-transport.h`, add:

```cpp
bool HandleReceivedCnp(const TransportResponseContext& ctx);
bool HandleReceivedTpNak(const TransportResponseContext& ctx);
```

- [ ] **Step 2: Implement `HandleReceivedCnp()`**

In `src/unified-bus/model/protocol/ub-transport.cc`, place this after `ParseTransportResponsePacket()`:

```cpp
bool
UbTransportChannel::HandleReceivedCnp(const TransportResponseContext& ctx)
{
    if (!ctx.isCnp) {
        return false;
    }

    // CNP is a congestion-control path; it does not advance ACK state.
    UbCongestionExtTph notification;
    notification.SetAckSequence(0);
    notification.SetRawBytes4to7(
        (static_cast<uint32_t>(ctx.cnpHeader.GetEcn() & 0x3U) << 30) |
        (static_cast<uint32_t>(ctx.cnpHeader.GetLocation() ? 1U : 0U) << 29));
    m_congestionCtrl->OnSenderCongestionNotification(TpOpcode::TP_OPCODE_CNP,
                                                     ctx.transportHeader.GetPsn(),
                                                     notification);
    NS_LOG_DEBUG("Recv TP CNP");
    return true;
}
```

- [ ] **Step 3: Implement `HandleReceivedTpNak()`**

In `src/unified-bus/model/protocol/ub-transport.cc`, place this after `HandleReceivedCnp()`:

```cpp
bool
UbTransportChannel::HandleReceivedTpNak(const TransportResponseContext& ctx)
{
    if (!ctx.isTpnak) {
        return false;
    }

    // TPNAK is negative feedback for retransmission; it does not enter ACK progress finalization.
    const uint64_t nakPsn = ctx.transportHeader.GetPsn();
    NS_LOG_DEBUG("[Transport channel] Recv tpnak."
              << " PacketUid: " << ctx.packet->GetUid()
              << " Tpn: " << m_tpn
              << " Psn: " << nakPsn
              << " PacketType: Nak"
              << " Src: " << m_src
              << " Dst: " << m_dest
              << " PacketSize: " << ctx.packet->GetSize());
    if (m_pktTraceEnabled) {
        UbFlowTag flowTag;
        ctx.packet->PeekPacketTag(flowTag);
        UbPacketTraceTag traceTag;
        ctx.packet->PeekPacketTag(traceTag);
        TpRecvNotify(ctx.packet->GetUid(), nakPsn, m_dest, m_src, m_dstTpn, m_tpn,
                     PacketType::NAK, ctx.packet->GetSize(), flowTag.GetFlowId(),
                     FormatSimpleAckInfo("TPNAK", nakPsn), traceTag);
    }

    const UbRetransAckResult ackResult =
        m_retrans->OnTransportResponse(ctx.transportHeader, ctx.opcode, nullptr, nullptr);
    if (ackResult.triggerTransmit) {
        TriggerTransportTransmit();
    }
    return true;
}
```

- [ ] **Step 4: Simplify early branches in `RecvTpAck()`**

Change the start of `RecvTpAck()` to:

```cpp
TransportResponseContext ctx;
if (!ParseTransportResponsePacket(p, ctx)) {
    return;
}

if (HandleReceivedCnp(ctx)) {
    return;
}

if (HandleReceivedTpNak(ctx)) {
    return;
}
```

Remove the now-duplicated inline CNP and TPNAK blocks from `RecvTpAck()`.

- [ ] **Step 5: Verify early handler extraction**

Run:

```bash
./ns3 build
./test.py -s unified-bus-transport-ooo-regression
./test.py -s unified-bus-examples
git diff --check
```

Expected:

```text
Build finished successfully
PASS: TestSuite unified-bus-transport-ooo-regression
PASS: TestSuite unified-bus-examples
```

- [ ] **Step 6: Commit**

```bash
git add src/unified-bus/model/protocol/ub-transport.h src/unified-bus/model/protocol/ub-transport.cc
git commit -m "refactor(transport): extract control response handlers"
```

## Task 3: Extract ACK And SACK Response Handling

**Files:**
- Modify: `src/unified-bus/model/protocol/ub-transport.h`
- Modify: `src/unified-bus/model/protocol/ub-transport.cc`

- [ ] **Step 1: Add helper declaration**

In `src/unified-bus/model/protocol/ub-transport.h`, add:

```cpp
bool HandleReceivedAckOrSack(const TransportResponseContext& ctx,
                             uint64_t previousSndUna,
                             UbRetransAckResult& ackResult);
```

- [ ] **Step 2: Implement `HandleReceivedAckOrSack()`**

In `src/unified-bus/model/protocol/ub-transport.cc`, place this after `HandleReceivedTpNak()`:

```cpp
bool
UbTransportChannel::HandleReceivedAckOrSack(const TransportResponseContext& ctx,
                                            uint64_t,
                                            UbRetransAckResult& ackResult)
{
    if (ctx.hasCetph && !ctx.hasSaetph) {
        m_congestionCtrl->OnSenderCongestionNotification(TpOpcode::TP_OPCODE_ACK_WITH_CETPH,
                                                         ctx.transportHeader.GetPsn(),
                                                         ctx.congestionHeader);
    }
    if (ctx.hasSaetph && m_pktTraceEnabled) {
        UbFlowTag flowTag;
        ctx.packet->PeekPacketTag(flowTag);
        UbPacketTraceTag traceTag;
        ctx.packet->PeekPacketTag(traceTag);
        TpRecvNotify(ctx.packet->GetUid(), ctx.transportHeader.GetPsn(),
                     m_dest, m_src, m_dstTpn, m_tpn,
                     PacketType::SACK, ctx.packet->GetSize(), flowTag.GetFlowId(),
                     FormatSelectiveAckInfo(ctx.transportHeader, ctx.selectiveAckHeader),
                     traceTag);
    }

    ackResult = m_retrans->OnTransportResponse(
        ctx.transportHeader,
        ctx.opcode,
        ctx.hasSaetph ? &ctx.selectiveAckHeader : nullptr,
        ctx.hasCetph ? &ctx.congestionHeader : nullptr);
    if (ackResult.ignoreResponse) {
        return false;
    }
    if (ackResult.triggerTransmit) {
        TriggerTransportTransmit();
    }
    return true;
}
```

- [ ] **Step 3: Replace ACK/SACK inline block in `RecvTpAck()`**

In `RecvTpAck()`, after CNP/TPNAK early returns, use:

```cpp
const uint64_t previousSndUna = m_psnSndUna;
UbRetransAckResult ackResult;
if (!HandleReceivedAckOrSack(ctx, previousSndUna, ackResult)) {
    return;
}
```

Remove the duplicated inline CETPH notification, SACK trace, `m_retrans->OnTransportResponse()`, `ignoreResponse`, and `triggerTransmit` code.

- [ ] **Step 4: Verify ACK/SACK handler extraction**

Run:

```bash
./ns3 build
./test.py -s unified-bus-transport-ooo-regression
git diff --check
```

Expected:

```text
Build finished successfully
PASS: TestSuite unified-bus-transport-ooo-regression
```

- [ ] **Step 5: Commit**

```bash
git add src/unified-bus/model/protocol/ub-transport.h src/unified-bus/model/protocol/ub-transport.cc
git commit -m "refactor(transport): extract ack and sack response handling"
```

## Task 4: Extract ACK Progress Finalization

**Files:**
- Modify: `src/unified-bus/model/protocol/ub-transport.h`
- Modify: `src/unified-bus/model/protocol/ub-transport.cc`

- [ ] **Step 1: Add finalization helper declarations**

In `src/unified-bus/model/protocol/ub-transport.h`, add:

```cpp
void FinalizeTransportAckProgress(const TransportResponseContext& ctx,
                                  uint64_t previousSndUna);
void CompleteAckedWqeSegments(const TransportResponseContext& ctx);
void UpdateSenderAfterTransportAck(const TransportResponseContext& ctx,
                                   uint64_t previousSndUna);
```

- [ ] **Step 2: Implement `CompleteAckedWqeSegments()`**

In `src/unified-bus/model/protocol/ub-transport.cc`, place this after `HandleReceivedAckOrSack()`:

```cpp
void
UbTransportChannel::CompleteAckedWqeSegments(const TransportResponseContext& ctx)
{
    for (size_t i = 0; i < m_wqeSegmentVector.size();) {
        Ptr<UbWqeSegment> segment = m_wqeSegmentVector[i];
        if (m_psnSndUna < segment->GetPsnStart() + segment->GetPsnSize()) {
            ++i;
            continue;
        }

        if (ctx.transportHeader.GetLastPacket()) {
            LastPacketACKsNotify(m_nodeId, segment->GetTaskId(), m_tpn, m_dstTpn,
                                 ctx.transportHeader.GetTpMsn(),
                                 ctx.transportHeader.GetPsn(),
                                 m_sport);
        }
        if (ShouldCompleteOnTpAck(segment)) {
            auto ubTa = GetTransaction();
            if (!ubTa->ProcessWqeSegmentComplete(segment)) {
                ++i;
                continue;
            }
            WqeSegmentCompletesNotify(m_nodeId, segment->GetTaskId(), segment->GetTaSsn());
        }

        m_wqeSegmentVector.erase(m_wqeSegmentVector.begin() + i);
        // Shallow pipeline counts only active segments that can still send new data.
        if (GetActiveSendSegmentCount() < 2) {
            ApplyNextWqeSegment();
        }
    }
}
```

- [ ] **Step 3: Implement `UpdateSenderAfterTransportAck()`**

In `src/unified-bus/model/protocol/ub-transport.cc`, place this after `CompleteAckedWqeSegments()`:

```cpp
void
UbTransportChannel::UpdateSenderAfterTransportAck(const TransportResponseContext&,
                                                  uint64_t)
{
    if (m_tpFullFlag && IsWqeSegmentLimited() == false) {
        m_tpFullFlag = false;
        ApplyNextWqeSegment();
    }
    if (m_wqeSegmentVector.size() == 0) {
        m_retrans->CancelTimer();
    }

    const bool transportIdle = !HasPendingTransmitWork();
    if (transportIdle) {
        m_congestionCtrl->OnSenderTransportIdle();
    }
    if (!transportIdle && !m_congestionCtrl->IsCcLimited(UB_MTU_BYTE)) {
        Ptr<UbPort> port = DynamicCast<UbPort>(NodeList::GetNode(m_nodeId)->GetDevice(m_sport));
        port->TriggerTransmit();
    }
    NS_LOG_DEBUG("Recv TP(data packet) acknowledgment");
}
```

- [ ] **Step 4: Implement `FinalizeTransportAckProgress()`**

In `src/unified-bus/model/protocol/ub-transport.cc`, place this after `UpdateSenderAfterTransportAck()`:

```cpp
void
UbTransportChannel::FinalizeTransportAckProgress(const TransportResponseContext& ctx,
                                                 uint64_t previousSndUna)
{
    if (m_psnSndUna > previousSndUna) {
        if (m_sendWindowLimited && IsInflightLimited() == false) {
            if (!m_congestionCtrl->IsCcLimited(UB_MTU_BYTE)) {
                m_sendWindowLimited = false;
                Ptr<UbPort> port =
                    DynamicCast<UbPort>(NodeList::GetNode(m_nodeId)->GetDevice(m_sport));
                port->TriggerTransmit();
            }
        }
        NS_LOG_DEBUG("[Transport channel] Recv ack."
                  << " PacketUid: " << ctx.packet->GetUid()
                  << " Tpn: " << m_tpn
                  << " Psn: " << m_psnSndUna - 1
                  << " PacketType: Ack"
                  << " Src: " << m_src
                  << " Dst: " << m_dest
                  << " PacketSize: " << ctx.packet->GetSize());
        if (m_pktTraceEnabled && !ctx.hasSaetph) {
            UbFlowTag flowTag;
            ctx.packet->PeekPacketTag(flowTag);
            UbPacketTraceTag traceTag;
            ctx.packet->PeekPacketTag(traceTag);
            TpRecvNotify(ctx.packet->GetUid(), m_psnSndUna - 1,
                         m_dest, m_src, m_dstTpn, m_tpn,
                         PacketType::ACK, ctx.packet->GetSize(), flowTag.GetFlowId(),
                         FormatSimpleAckInfo("TPACK", ctx.transportHeader.GetPsn()),
                         traceTag);
        }

        // Only real ACK progress resets the RTO state and reschedules timeout.
        m_retrans->RestartTimerAfterAckProgress();
    }

    CompleteAckedWqeSegments(ctx);
    TraceTpDebugState(m_nodeId,
                      m_tpn,
                      "RECV_ACK",
                      m_psnSndNxt,
                      m_psnSndUna,
                      m_maxInflightPacketSize,
                      m_congestionCtrl->IsCcLimited(UB_MTU_BYTE),
                      m_sendWindowLimited,
                      GetActiveSendSegmentCount(),
                      static_cast<uint32_t>(m_wqeSegmentVector.size()),
                      static_cast<uint32_t>(m_ackQ.size()),
                      static_cast<uint32_t>(m_cnpQ.size()));
    UpdateSenderAfterTransportAck(ctx, previousSndUna);
}
```

- [ ] **Step 5: Reduce `RecvTpAck()` to the target flow**

After this task, `RecvTpAck()` should be:

```cpp
void
UbTransportChannel::RecvTpAck(Ptr<Packet> p)
{
    TransportResponseContext ctx;
    if (!ParseTransportResponsePacket(p, ctx)) {
        return;
    }

    if (HandleReceivedCnp(ctx)) {
        return;
    }

    if (HandleReceivedTpNak(ctx)) {
        return;
    }

    const uint64_t previousSndUna = m_psnSndUna;
    UbRetransAckResult ackResult;
    if (!HandleReceivedAckOrSack(ctx, previousSndUna, ackResult)) {
        return;
    }

    FinalizeTransportAckProgress(ctx, previousSndUna);
}
```

- [ ] **Step 6: Verify RecvTpAck refactor**

Run:

```bash
./ns3 build
./test.py -s unified-bus-transport-ooo-regression
./test.py -s unified-bus-examples
./ns3 run --no-build "scratch/ub-quick-example --case-path=scratch/retrans/GBN_fast/first_tp_packet_loss"
git diff --check
```

Expected:

```text
Build finished successfully
PASS: TestSuite unified-bus-transport-ooo-regression
PASS: TestSuite unified-bus-examples
```

The scratch scenario should complete without abort/assert/fatal errors.

- [ ] **Step 7: Commit**

```bash
git add src/unified-bus/model/protocol/ub-transport.h src/unified-bus/model/protocol/ub-transport.cc
git commit -m "refactor(transport): extract ack progress finalization"
```

## Task 5: Add New Data Send Context And Pre-Send Helpers

**Files:**
- Modify: `src/unified-bus/model/protocol/ub-transport.h`
- Modify: `src/unified-bus/model/protocol/ub-transport.cc`

- [ ] **Step 1: Add `NewDataSendContext` and helper declarations**

In `src/unified-bus/model/protocol/ub-transport.h`, inside the private section after `TransportResponseContext`, add:

```cpp
struct NewDataSendContext
{
    Ptr<UbWqeSegment> segment;
    uint32_t progressBytes{0};
    uint32_t payloadBytes{0};
    uint32_t wireLengthBytes{0};
    uint32_t totalProgressBytes{0};
};
```

Then add these private helper declarations near `TryGetNextNewDataPacket()`:

```cpp
bool CanTrySendNewDataPacket();
bool BuildNextDataSendContext(NewDataSendContext& ctx);
```

- [ ] **Step 2: Implement `CanTrySendNewDataPacket()`**

In `src/unified-bus/model/protocol/ub-transport.cc`, place this immediately before `TryGetNextNewDataPacket()`:

```cpp
bool
UbTransportChannel::CanTrySendNewDataPacket()
{
    if (m_wqeSegmentVector.empty()) {
        NS_LOG_DEBUG("No WQE segments available to send");
        TraceTpDebugState(m_nodeId,
                          m_tpn,
                          "GET_NEXT_EMPTY_SEGMENTS",
                          m_psnSndNxt,
                          m_psnSndUna,
                          m_maxInflightPacketSize,
                          false,
                          m_sendWindowLimited,
                          GetActiveSendSegmentCount(),
                          static_cast<uint32_t>(m_wqeSegmentVector.size()),
                          static_cast<uint32_t>(m_ackQ.size()),
                          static_cast<uint32_t>(m_cnpQ.size()));
        return false;
    }

    if (IsInflightLimited()) {
        m_sendWindowLimited = true;
        NS_LOG_DEBUG("Full Send Window");
        TraceTpDebugState(m_nodeId,
                          m_tpn,
                          "GET_NEXT_INFLIGHT_LIMITED",
                          m_psnSndNxt,
                          m_psnSndUna,
                          m_maxInflightPacketSize,
                          false,
                          m_sendWindowLimited,
                          GetActiveSendSegmentCount(),
                          static_cast<uint32_t>(m_wqeSegmentVector.size()),
                          static_cast<uint32_t>(m_ackQ.size()),
                          static_cast<uint32_t>(m_cnpQ.size()));
        return false;
    }

    return true;
}
```

- [ ] **Step 3: Implement `BuildNextDataSendContext()`**

In `src/unified-bus/model/protocol/ub-transport.cc`, place this after `CanTrySendNewDataPacket()`:

```cpp
bool
UbTransportChannel::BuildNextDataSendContext(NewDataSendContext& ctx)
{
    // This helper selects only a new data packet. Retransmission packets are handled earlier.
    for (size_t i = 0; i < m_wqeSegmentVector.size(); ++i) {
        Ptr<UbWqeSegment> currentSegment = m_wqeSegmentVector[i];
        if (currentSegment == nullptr || currentSegment->IsSentCompleted()) {
            continue;
        }

        ctx.segment = currentSegment;
        ctx.progressBytes = GetProgressBytesThisPacket(currentSegment);
        ctx.payloadBytes = GetPayloadBytesThisPacket(currentSegment, ctx.progressBytes);
        ctx.wireLengthBytes = GetWireLengthBytes(currentSegment, ctx.payloadBytes);
        ctx.totalProgressBytes = GetTotalProgressBytes(currentSegment);

        if (m_congestionCtrl->IsCcLimited(ctx.progressBytes)) {
            m_sendWindowLimited = true;
            TraceTpDebugState(m_nodeId,
                              m_tpn,
                              "GET_NEXT_CC_LIMITED",
                              m_psnSndNxt,
                              m_psnSndUna,
                              m_maxInflightPacketSize,
                              true,
                              m_sendWindowLimited,
                              GetActiveSendSegmentCount(),
                              static_cast<uint32_t>(m_wqeSegmentVector.size()),
                              static_cast<uint32_t>(m_ackQ.size()),
                              static_cast<uint32_t>(m_cnpQ.size()));
            return false;
        }

        return true;
    }

    return false;
}
```

- [ ] **Step 4: Simplify the front half of `TryGetNextNewDataPacket()`**

Temporarily change `TryGetNextNewDataPacket()` to use the new helpers, while keeping packet generation and post-send state inline:

```cpp
Ptr<Packet>
UbTransportChannel::TryGetNextNewDataPacket()
{
    if (!CanTrySendNewDataPacket()) {
        return nullptr;
    }

    NewDataSendContext ctx;
    if (!BuildNextDataSendContext(ctx)) {
        return nullptr;
    }

    Ptr<Packet> p = GenDataPacket(ctx.segment,
                                  ctx.payloadBytes,
                                  ctx.wireLengthBytes,
                                  ctx.progressBytes);
    m_retrans->OnNewDataPacketSent(m_psnSndNxt,
                                   p,
                                   ctx.payloadBytes,
                                   ctx.progressBytes);

    m_congestionCtrl->OnSenderDataPacketSent(m_psnSndNxt, ctx.progressBytes);

    if (ctx.segment->GetBytesLeft() == ctx.totalProgressBytes) {
        FirstPacketSendsNotify(m_nodeId, ctx.segment->GetTaskId(), m_tpn, m_dstTpn,
                               ctx.segment->GetTpMsn(), m_psnSndNxt, m_sport);
    }
    if (ctx.segment->GetBytesLeft() == ctx.progressBytes) {
        LastPacketSendsNotify(m_nodeId, ctx.segment->GetTaskId(), m_tpn, m_dstTpn,
                              ctx.segment->GetTpMsn(), m_psnSndNxt, m_sport);
    }
    NS_LOG_DEBUG("[Transport channel] Send packet."
              << " PacketUid: " << p->GetUid()
              << " Tpn: " << m_tpn
              << " DstTpn: " << m_dstTpn
              << " Psn: " << m_psnSndNxt
              << " PacketType: Packet"
              << " Src: " << m_src
              << " Dst: " << m_dest
              << " PacketSize: " << p->GetSize()
              << " TaskId: " << ctx.segment->GetTaskId());
    ctx.segment->UpdateSentBytes(ctx.progressBytes);
    m_psnSndNxt++;
    TraceTpDebugState(m_nodeId,
                      m_tpn,
                      "SEND_PACKET",
                      m_psnSndNxt,
                      m_psnSndUna,
                      m_maxInflightPacketSize,
                      false,
                      m_sendWindowLimited,
                      GetActiveSendSegmentCount(),
                      static_cast<uint32_t>(m_wqeSegmentVector.size()),
                      static_cast<uint32_t>(m_ackQ.size()),
                      static_cast<uint32_t>(m_cnpQ.size()));
    m_retrans->StartTimerIfNeeded();
    if (ctx.segment->IsSentCompleted() && GetActiveSendSegmentCount() < 2) {
        ApplyNextWqeSegment();
    }
    if (HasPendingTransmitWork()) {
        m_headArrivalTime = Simulator::Now();
    }
    return p;
}
```

- [ ] **Step 5: Verify pre-send helper extraction**

Run:

```bash
./ns3 build
./test.py -s unified-bus-transport-ooo-regression
git diff --check
```

Expected:

```text
Build finished successfully
PASS: TestSuite unified-bus-transport-ooo-regression
```

- [ ] **Step 6: Commit**

```bash
git add src/unified-bus/model/protocol/ub-transport.h src/unified-bus/model/protocol/ub-transport.cc
git commit -m "refactor(transport): prepare new data send context"
```

## Task 6: Extract New Data Send Notifications And State Advancement

**Files:**
- Modify: `src/unified-bus/model/protocol/ub-transport.h`
- Modify: `src/unified-bus/model/protocol/ub-transport.cc`

- [ ] **Step 1: Add post-send helper declarations**

In `src/unified-bus/model/protocol/ub-transport.h`, add:

```cpp
Ptr<Packet> SendNewDataPacket(const NewDataSendContext& ctx);
void NotifyNewDataPacketSent(const NewDataSendContext& ctx, Ptr<Packet> packet);
void AdvanceNewDataSendState(const NewDataSendContext& ctx, Ptr<Packet> packet);
```

- [ ] **Step 2: Implement `NotifyNewDataPacketSent()`**

In `src/unified-bus/model/protocol/ub-transport.cc`, place this after `BuildNextDataSendContext()`:

```cpp
void
UbTransportChannel::NotifyNewDataPacketSent(const NewDataSendContext& ctx,
                                            Ptr<Packet> packet)
{
    m_retrans->OnNewDataPacketSent(m_psnSndNxt,
                                   packet,
                                   ctx.payloadBytes,
                                   ctx.progressBytes);

    m_congestionCtrl->OnSenderDataPacketSent(m_psnSndNxt, ctx.progressBytes);

    if (ctx.segment->GetBytesLeft() == ctx.totalProgressBytes) {
        FirstPacketSendsNotify(m_nodeId, ctx.segment->GetTaskId(), m_tpn, m_dstTpn,
                               ctx.segment->GetTpMsn(), m_psnSndNxt, m_sport);
    }
    if (ctx.segment->GetBytesLeft() == ctx.progressBytes) {
        LastPacketSendsNotify(m_nodeId, ctx.segment->GetTaskId(), m_tpn, m_dstTpn,
                              ctx.segment->GetTpMsn(), m_psnSndNxt, m_sport);
    }

    NS_LOG_DEBUG("[Transport channel] Send packet."
              << " PacketUid: " << packet->GetUid()
              << " Tpn: " << m_tpn
              << " DstTpn: " << m_dstTpn
              << " Psn: " << m_psnSndNxt
              << " PacketType: Packet"
              << " Src: " << m_src
              << " Dst: " << m_dest
              << " PacketSize: " << packet->GetSize()
              << " TaskId: " << ctx.segment->GetTaskId());
}
```

- [ ] **Step 3: Implement `AdvanceNewDataSendState()`**

In `src/unified-bus/model/protocol/ub-transport.cc`, place this after `NotifyNewDataPacketSent()`:

```cpp
void
UbTransportChannel::AdvanceNewDataSendState(const NewDataSendContext& ctx,
                                            Ptr<Packet>)
{
    ctx.segment->UpdateSentBytes(ctx.progressBytes);
    m_psnSndNxt++;
    TraceTpDebugState(m_nodeId,
                      m_tpn,
                      "SEND_PACKET",
                      m_psnSndNxt,
                      m_psnSndUna,
                      m_maxInflightPacketSize,
                      false,
                      m_sendWindowLimited,
                      GetActiveSendSegmentCount(),
                      static_cast<uint32_t>(m_wqeSegmentVector.size()),
                      static_cast<uint32_t>(m_ackQ.size()),
                      static_cast<uint32_t>(m_cnpQ.size()));
    m_retrans->StartTimerIfNeeded();

    // Shallow pipeline keeps at most two active segments capable of sending new data.
    if (ctx.segment->IsSentCompleted() && GetActiveSendSegmentCount() < 2) {
        ApplyNextWqeSegment();
    }
    if (HasPendingTransmitWork()) {
        m_headArrivalTime = Simulator::Now();
    }
}
```

- [ ] **Step 4: Implement `SendNewDataPacket()`**

In `src/unified-bus/model/protocol/ub-transport.cc`, place this after `AdvanceNewDataSendState()`:

```cpp
Ptr<Packet>
UbTransportChannel::SendNewDataPacket(const NewDataSendContext& ctx)
{
    Ptr<Packet> packet = GenDataPacket(ctx.segment,
                                       ctx.payloadBytes,
                                       ctx.wireLengthBytes,
                                       ctx.progressBytes);
    NotifyNewDataPacketSent(ctx, packet);
    AdvanceNewDataSendState(ctx, packet);
    return packet;
}
```

- [ ] **Step 5: Reduce `TryGetNextNewDataPacket()` to the target flow**

After this task, `TryGetNextNewDataPacket()` should be:

```cpp
Ptr<Packet>
UbTransportChannel::TryGetNextNewDataPacket()
{
    if (!CanTrySendNewDataPacket()) {
        return nullptr;
    }

    NewDataSendContext ctx;
    if (!BuildNextDataSendContext(ctx)) {
        return nullptr;
    }

    return SendNewDataPacket(ctx);
}
```

- [ ] **Step 6: Verify new data send flow refactor**

Run:

```bash
./ns3 build
./test.py -s unified-bus-transport-ooo-regression
./test.py -s unified-bus-examples
git diff --check
```

Expected:

```text
Build finished successfully
PASS: TestSuite unified-bus-transport-ooo-regression
PASS: TestSuite unified-bus-examples
```

- [ ] **Step 7: Commit**

```bash
git add src/unified-bus/model/protocol/ub-transport.h src/unified-bus/model/protocol/ub-transport.cc
git commit -m "refactor(transport): simplify new data send flow"
```

## Task 7: Final Regression And Scenario Verification

**Files:**
- Modify only if verification exposes a compile/test issue:
  - `src/unified-bus/model/protocol/ub-transport.h`
  - `src/unified-bus/model/protocol/ub-transport.cc`

- [ ] **Step 1: Run complete verification**

Run:

```bash
./ns3 build
./test.py -s unified-bus-transport-ooo-regression
./test.py -s unified-bus-examples
./ns3 run --no-build "scratch/ub-quick-example --case-path=scratch/retrans/GBN_fast/first_tp_packet_loss"
./ns3 run --no-build "scratch/ub-quick-example --case-path=scratch/retrans/SELE_fast/first_tp_packet_loss"
./ns3 run --no-build "scratch/ub-quick-example --case-path=scratch/retrans/SELE_fast/non_first_tp_packet_loss_markpsn"
git diff --check
```

Expected:

```text
Build finished successfully
PASS: TestSuite unified-bus-transport-ooo-regression
PASS: TestSuite unified-bus-examples
```

All three scratch scenarios should complete without abort/assert/fatal errors.

- [ ] **Step 2: Inspect the final diff for accidental behavior changes**

Run:

```bash
git diff -- src/unified-bus/model/protocol/ub-transport.h src/unified-bus/model/protocol/ub-transport.cc
```

Check:

- CNP still calls `OnSenderCongestionNotification(TP_OPCODE_CNP, psn, notification)` and returns.
- TPNAK still calls `m_retrans->OnTransportResponse(..., nullptr, nullptr)` and returns.
- ACK/SACK still passes SAETPH/CETPH pointers exactly according to `hasSaetph` and `hasCetph`.
- `RestartTimerAfterAckProgress()` is called only when `m_psnSndUna > previousSndUna`.
- `TryGetNextNewDataPacket()` still updates retrans state before `UpdateSentBytes()` and `m_psnSndNxt++`.
- `TraceTpDebugState("SEND_PACKET")` still observes the incremented `m_psnSndNxt`, matching current behavior.

- [ ] **Step 3: Commit verification-only fixes if needed**

If Step 1 or Step 2 required code fixes, run the complete verification again and commit:

```bash
git add src/unified-bus/model/protocol/ub-transport.h src/unified-bus/model/protocol/ub-transport.cc
git commit -m "fix(transport): preserve main flow refactor behavior"
```

If no fixes were needed, do not create an empty commit.

## Self-Review

- Spec coverage:
  - `RecvTpAck()` protocol parsing, CNP early return, TPNAK early return, ACK/SACK common path, ACK-progress finalization, WQE completion, idle/trigger transmit are covered by Tasks 1-4.
  - `TryGetNextNewDataPacket()` pre-send checks, context construction, packet generation, notifications, PSN/segment/timer advancement are covered by Tasks 5-6.
  - Final build/test/scenario verification is covered by Task 7.

- Placeholder scan:
  - No unresolved placeholder markers or unspecified test-writing instructions are present.

- Type consistency:
  - `TransportResponseContext`, `NewDataSendContext`, and all helper names are declared in `ub-transport.h` before use in `ub-transport.cc`.
  - Helper signatures match the target flow in the design document and include concrete argument types.
