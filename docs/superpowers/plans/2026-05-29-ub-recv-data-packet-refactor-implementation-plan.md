# UB RecvDataPacket Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `UbTransportChannel::RecvDataPacket()` into a clear receive pipeline while preserving existing ACK/NAK/SACK behavior.

**Architecture:** Keep packet parsing/building in `UbTransportChannel` and keep retransmission decisions in `UbRetransController`. Add small private context structs and helper methods in `ub-transport.h/.cc` so `RecvDataPacket()` orchestrates parsing, immediate retransmission response, repeat packet response, receive-window advancement, response construction, and TA completion without embedding every detail.

**Tech Stack:** C++17-style ns-3 code, `Ptr<Packet>`, existing UnifiedBus transport tests, existing retransmission scratch scenarios.

---

## File Structure

- Modify: `src/unified-bus/model/protocol/ub-transport.h`
  - Add private helper structs: `ReceivedDataPacketContext`, `AckResponseContext`.
  - Add private helper declarations for parsing, tracing, response construction, receive-window processing, and TA completion.

- Modify: `src/unified-bus/model/protocol/ub-transport.cc`
  - Move code out of `RecvDataPacket()` into helpers.
  - Keep all helper implementations close to `RecvDataPacket()` so behavior remains easy to compare.

- Test: `src/unified-bus/test/ub-test.cc`
  - No planned edits.
  - Existing tests already cover ACK_WITHOUT_CETPH, selective receiver TPSACK, duplicate TPSACK, TPSACK-CC order, sender TPSACK handling, queue precedence, and OOO regression.

## Task 1: Add Context Structs And Parse Helper

**Files:**
- Modify: `src/unified-bus/model/protocol/ub-transport.h`
- Modify: `src/unified-bus/model/protocol/ub-transport.cc`

- [ ] **Step 1: Add private context structs**

In `src/unified-bus/model/protocol/ub-transport.h`, inside `class UbTransportChannel` private section, after `BufferedInboundPacket`, add:

```cpp
    struct ReceivedDataPacketContext
    {
        Ptr<Packet> packet;
        UbDatalinkPacketHeader dataLinkHeader;
        UbIpBasedNetworkHeader networkHeader;
        Ipv4Header ipv4Header;
        UdpHeader udpHeader;
        UbTransportHeader transportHeader;
        UbTransactionHeader transactionHeader;
        UbMAExtTah maExtHeader;
        UbFlowTag flowTag;
        uint64_t psn{0};
        uint32_t payloadBytes{0};
        uint32_t logicalBytes{0};
    };

    struct AckResponseContext
    {
        TpOpcode opcode{TpOpcode::TP_OPCODE_ACK_WITHOUT_CETPH};
        uint64_t psn{0};
        bool selectiveAck{false};
        std::optional<UbSelectiveAckExtTph> selectiveAckHeader;
        std::optional<UbCongestionExtTph> congestionHeader;
    };
```

- [ ] **Step 2: Add helper declarations**

In the same private section, near the existing helper declarations, add:

```cpp
    bool ParseReceivedDataPacket(Ptr<Packet> packet, ReceivedDataPacketContext& ctx);
    void TraceReceivedDataPacket(const ReceivedDataPacketContext& ctx);
```

- [ ] **Step 3: Implement `ParseReceivedDataPacket`**

In `src/unified-bus/model/protocol/ub-transport.cc`, before `RecvDataPacket()`, add:

```cpp
bool
UbTransportChannel::ParseReceivedDataPacket(Ptr<Packet> packet,
                                            ReceivedDataPacketContext& ctx)
{
    if (packet == nullptr) {
        NS_LOG_ERROR("Null packet received");
        return false;
    }

    ctx.packet = packet;
    packet->RemoveHeader(ctx.dataLinkHeader);
    packet->RemoveHeader(ctx.networkHeader);
    packet->RemoveHeader(ctx.ipv4Header);
    packet->RemoveHeader(ctx.udpHeader);
    packet->RemoveHeader(ctx.transportHeader);
    packet->RemoveHeader(ctx.transactionHeader);
    packet->RemoveHeader(ctx.maExtHeader);
    ctx.payloadBytes = packet->GetSize();
    ctx.logicalBytes = ctx.maExtHeader.GetLength();
    ctx.psn = ctx.transportHeader.GetPsn();
    packet->PeekPacketTag(ctx.flowTag);
    return true;
}
```

- [ ] **Step 4: Implement `TraceReceivedDataPacket`**

Add:

```cpp
void
UbTransportChannel::TraceReceivedDataPacket(const ReceivedDataPacketContext& ctx)
{
    m_hasReceivedAnyPsn = true;
    m_maxRcvPsn = std::max(m_maxRcvPsn, ctx.psn);
    NS_LOG_DEBUG("[Transport channel] Recv packet."
                  << " PacketUid: "  << ctx.packet->GetUid()
                  << " Tpn: " << m_tpn
                  << " Psn: " << ctx.psn
                  << " PacketType: Packet"
                  << " Src: " << m_src
                  << " Dst: " << m_dest
                  << " PacketSize: " << ctx.packet->GetSize());
    if (m_pktTraceEnabled) {
        UbPacketTraceTag traceTag;
        ctx.packet->PeekPacketTag(traceTag);
        TpRecvNotify(ctx.packet->GetUid(), ctx.psn, m_dest, m_src, m_dstTpn, m_tpn,
                     PacketType::PACKET, ctx.packet->GetSize(), ctx.flowTag.GetFlowId(), "", traceTag);
    }
}
```

- [ ] **Step 5: Use parse and trace helpers in `RecvDataPacket`**

Replace the header-local declarations and initial parsing block in `RecvDataPacket()` with:

```cpp
    ReceivedDataPacketContext ctx;
    if (!ParseReceivedDataPacket(p, ctx)) {
        return;
    }

    TraceReceivedDataPacket(ctx);
    Ptr<Packet> ackp = Create<Packet>(0);
    ackp->AddPacketTag(ctx.flowTag);
```

Then temporarily replace old local variable uses:

```cpp
psn -> ctx.psn
TpHeader -> ctx.transportHeader
TaHeader -> ctx.transactionHeader
NetworkHeader -> ctx.networkHeader
ipv4Header -> ctx.ipv4Header
udpHeader -> ctx.udpHeader
pktHeader -> ctx.dataLinkHeader
payloadBytes -> ctx.payloadBytes
logicalBytes -> ctx.logicalBytes
flowTag -> ctx.flowTag
p -> ctx.packet
```

- [ ] **Step 6: Run focused receiver tests**

Run:

```bash
./ns3 build
./test.py -s unified-bus-transport-ooo-regression
```

Expected:

- Build succeeds.
- `unified-bus-transport-ooo-regression` passes.

- [ ] **Step 7: Commit**

```bash
git add src/unified-bus/model/protocol/ub-transport.h \
        src/unified-bus/model/protocol/ub-transport.cc
git commit -m "refactor(transport): parse received data packet context"
```

## Task 2: Extract Transport Response Packet Builder

**Files:**
- Modify: `src/unified-bus/model/protocol/ub-transport.h`
- Modify: `src/unified-bus/model/protocol/ub-transport.cc`

- [ ] **Step 1: Add helper declarations**

In `ub-transport.h`, add private methods:

```cpp
    Ptr<Packet> BuildTransportResponsePacket(const ReceivedDataPacketContext& ctx,
                                             const AckResponseContext& response);
    void EnqueueTransportResponse(Ptr<Packet> response, const char* logType, uint64_t psn);
```

- [ ] **Step 2: Implement `BuildTransportResponsePacket`**

In `ub-transport.cc`, before `RecvDataPacket()`, add:

```cpp
Ptr<Packet>
UbTransportChannel::BuildTransportResponsePacket(const ReceivedDataPacketContext& ctx,
                                                 const AckResponseContext& response)
{
    Ptr<Packet> responsePacket = Create<Packet>(0);
    responsePacket->AddPacketTag(ctx.flowTag);

    UbAckTransactionHeader ackTaHeader;
    ackTaHeader.SetTaOpcode(TaOpcode::TA_OPCODE_TRANSACTION_ACK);
    ackTaHeader.SetIniTaSsn(ctx.transactionHeader.GetIniTaSsn());
    ackTaHeader.SetIniRcId(ctx.transactionHeader.GetIniRcId());

    UbTransportHeader tpHeader = ctx.transportHeader;
    tpHeader.SetTPOpcode(response.opcode);
    tpHeader.SetRspSt(0);
    tpHeader.SetRspInfo(0);
    tpHeader.SetPsn(static_cast<uint32_t>(response.psn));
    tpHeader.SetSrcTpn(m_tpn);
    tpHeader.SetDestTpn(m_dstTpn);

    responsePacket->AddHeader(ackTaHeader);
    if (response.selectiveAck) {
        NS_ASSERT_MSG(response.selectiveAckHeader.has_value(),
                      "Selective response requires SAETPH.");
        responsePacket->AddHeader(*response.selectiveAckHeader);
    }
    if (response.congestionHeader.has_value()) {
        responsePacket->AddHeader(*response.congestionHeader);
    }
    responsePacket->AddHeader(tpHeader);
    responsePacket->AddHeader(ctx.udpHeader);
    UbPort::AddIpv4Header(responsePacket,
                          ctx.ipv4Header.GetDestination(),
                          ctx.ipv4Header.GetSource());
    responsePacket->AddHeader(ctx.networkHeader);
    UbDataLink::GenPacketHeader(responsePacket,
                                false,
                                true,
                                ctx.dataLinkHeader.GetCreditTargetVL(),
                                ctx.dataLinkHeader.GetPacketVL(),
                                0,
                                1,
                                UbDatalinkHeaderConfig::PACKET_IPV4);
    return responsePacket;
}
```

- [ ] **Step 3: Implement `EnqueueTransportResponse`**

Add:

```cpp
void
UbTransportChannel::EnqueueTransportResponse(Ptr<Packet> response,
                                             const char* logType,
                                             uint64_t psn)
{
    if (m_ackQ.empty()) {
        m_headArrivalTime = Simulator::Now();
    }
    m_ackQ.push(response);
    NS_LOG_DEBUG("[Transport channel] Send " << logType << ". "
                  << " PacketUid: "  << response->GetUid()
                  << " Tpn: " << m_tpn
                  << " Psn: " << psn
                  << " PacketType: " << logType
                  << " Src: " << m_src
                  << " Dst: " << m_dest
                  << " PacketSize: " << response->GetSize());
    TriggerTransportTransmit();
}
```

- [ ] **Step 4: Convert TPNAK construction to the builder**

In the `receiveDecision.shouldNak` branch, replace the manual `ackp` construction with:

```cpp
        AckResponseContext response;
        response.opcode = receiveDecision.responseOpcode;
        response.psn = receiveDecision.responsePsn;
        Ptr<Packet> responsePacket = BuildTransportResponsePacket(ctx, response);
        EnqueueTransportResponse(responsePacket, "tpnak", response.psn);
        return;
```

Keep the existing `NS_LOG_DEBUG` semantic by preserving the log type string as `"tpnak"` or choosing `"Nak"` consistently with the current text.

- [ ] **Step 5: Convert duplicate packet response construction to the builder**

In the duplicate packet branch, replace manual packet construction with:

```cpp
        AckResponseContext response;
        response.opcode = selectiveAck ? decision.responseOpcode
                                       : TpOpcode::TP_OPCODE_ACK_WITHOUT_CETPH;
        response.psn = decision.responsePsn;
        response.selectiveAck = selectiveAck;
        if (selectiveAck) {
            NS_ASSERT_MSG(decision.selectiveAckHeader.has_value(),
                          "SELECTIVE receive decision requires SAETPH.");
            response.selectiveAckHeader = *decision.selectiveAckHeader;
        }
        if (response.opcode == TpOpcode::TP_OPCODE_SACK_WITH_CETPH) {
            response.congestionHeader =
                m_congestionCtrl->OnReceiverPrepareAckCongestionHeader(0, 0);
        }
        Ptr<Packet> responsePacket = BuildTransportResponsePacket(ctx, response);
        EnqueueTransportResponse(responsePacket, "ack", response.psn);
        return;
```

- [ ] **Step 6: Convert normal ACK/SACK response construction to the builder**

After `m_retrans->BuildReceiveDecisionForCurrentState()`, replace manual packet construction with an `AckResponseContext` and `BuildTransportResponsePacket`.

Use:

```cpp
    AckResponseContext response;
    response.opcode = decision.responseOpcode;
    response.psn = decision.responsePsn;
    response.selectiveAck = decision.selectiveAck;
    if (decision.selectiveAck) {
        NS_ASSERT_MSG(decision.selectiveAckHeader.has_value(),
                      "SELECTIVE receive decision requires SAETPH.");
        response.selectiveAckHeader = *decision.selectiveAckHeader;
    }
    response.congestionHeader =
        m_congestionCtrl->OnReceiverPrepareAckCongestionHeader(psnStart, psnEnd);
    Ptr<Packet> responsePacket = BuildTransportResponsePacket(ctx, response);
    EnqueueTransportResponse(responsePacket, "ack", response.psn);
```

- [ ] **Step 7: Run ACK/SACK wire-format tests**

Run:

```bash
./ns3 build
./test.py -s unified-bus-examples
./test.py -s unified-bus-transport-ooo-regression
```

Expected:

- Build succeeds.
- Both suites pass.

- [ ] **Step 8: Commit**

```bash
git add src/unified-bus/model/protocol/ub-transport.h \
        src/unified-bus/model/protocol/ub-transport.cc
git commit -m "refactor(transport): centralize data response packet building"
```

## Task 3: Extract Immediate And Duplicate Response Paths

**Files:**
- Modify: `src/unified-bus/model/protocol/ub-transport.h`
- Modify: `src/unified-bus/model/protocol/ub-transport.cc`

- [ ] **Step 1: Add helper declarations**

In `ub-transport.h`, add:

```cpp
    bool HandleImmediateRetransReceiveDecision(const ReceivedDataPacketContext& ctx,
                                               const UbRetransReceiveDecision& decision);
    bool HandleRepeatedDataPacket(const ReceivedDataPacketContext& ctx);
    void NotifyLastPacketReceived(const ReceivedDataPacketContext& ctx);
```

- [ ] **Step 2: Implement `HandleImmediateRetransReceiveDecision`**

Add:

```cpp
bool
UbTransportChannel::HandleImmediateRetransReceiveDecision(
    const ReceivedDataPacketContext& ctx,
    const UbRetransReceiveDecision& decision)
{
    if (decision.suppressResponse) {
        NS_LOG_DEBUG("Suppress repeated GBN TPNAK,tpn:{" << m_tpn << "} psn:{"
                     << decision.responsePsn << "}");
        return true;
    }
    if (!decision.shouldNak) {
        return false;
    }

    AckResponseContext response;
    response.opcode = decision.responseOpcode;
    response.psn = decision.responsePsn;
    Ptr<Packet> responsePacket = BuildTransportResponsePacket(ctx, response);
    EnqueueTransportResponse(responsePacket, "tpnak", response.psn);
    return true;
}
```

- [ ] **Step 3: Implement `HandleRepeatedDataPacket`**

Add:

```cpp
bool
UbTransportChannel::HandleRepeatedDataPacket(const ReceivedDataPacketContext& ctx)
{
    if (!IsRepeatPacket(ctx.psn)) {
        return false;
    }

    const UbRetransReceiveDecision decision =
        m_retrans->BuildReceiveDecisionForCurrentState();
    if (decision.suppressResponse) {
        if (decision.selectiveAck) {
            NS_LOG_WARN("Suppressing duplicate-packet TPSACK because SelectiveAckBitmapBits cannot be resolved");
        }
        return true;
    }

    AckResponseContext response;
    response.opcode = decision.selectiveAck ? decision.responseOpcode
                                            : TpOpcode::TP_OPCODE_ACK_WITHOUT_CETPH;
    response.psn = decision.responsePsn;
    response.selectiveAck = decision.selectiveAck;
    if (decision.selectiveAck) {
        NS_ASSERT_MSG(decision.selectiveAckHeader.has_value(),
                      "SELECTIVE receive decision requires SAETPH.");
        response.selectiveAckHeader = *decision.selectiveAckHeader;
    }
    if (response.opcode == TpOpcode::TP_OPCODE_SACK_WITH_CETPH) {
        response.congestionHeader =
            m_congestionCtrl->OnReceiverPrepareAckCongestionHeader(0, 0);
    }
    Ptr<Packet> responsePacket = BuildTransportResponsePacket(ctx, response);
    EnqueueTransportResponse(responsePacket, "ack", response.psn);
    return true;
}
```

- [ ] **Step 4: Implement `NotifyLastPacketReceived`**

Add:

```cpp
void
UbTransportChannel::NotifyLastPacketReceived(const ReceivedDataPacketContext& ctx)
{
    if (!ctx.transportHeader.GetLastPacket()) {
        return;
    }
    LastPacketReceivesNotify(m_nodeId,
                             ctx.transportHeader.GetSrcTpn(),
                             ctx.transportHeader.GetDestTpn(),
                             ctx.transportHeader.GetTpMsn(),
                             ctx.transportHeader.GetPsn(),
                             m_dport);
}
```

- [ ] **Step 5: Replace inline branches in `RecvDataPacket`**

In `RecvDataPacket()`, replace the immediate NAK/suppress branch with:

```cpp
    if (HandleImmediateRetransReceiveDecision(ctx, receiveDecision)) {
        return;
    }
```

Replace the inline last-packet notify with:

```cpp
    NotifyLastPacketReceived(ctx);
```

Replace the inline duplicate branch with:

```cpp
    if (HandleRepeatedDataPacket(ctx)) {
        return;
    }
```

- [ ] **Step 6: Run duplicate response tests**

Run:

```bash
./ns3 build
./test.py -s unified-bus-transport-ooo-regression
```

Expected:

- Build succeeds.
- Suite passes.

- [ ] **Step 7: Commit**

```bash
git add src/unified-bus/model/protocol/ub-transport.h \
        src/unified-bus/model/protocol/ub-transport.cc
git commit -m "refactor(transport): extract data receive response branches"
```

## Task 4: Extract Receive Window Advancement And TA Completion

**Files:**
- Modify: `src/unified-bus/model/protocol/ub-transport.h`
- Modify: `src/unified-bus/model/protocol/ub-transport.cc`

- [ ] **Step 1: Add helper declarations**

In `ub-transport.h`, add:

```cpp
    bool UpdateReceiveWindowAndCollectCompletedTa(
        const ReceivedDataPacketContext& ctx,
        const UbRetransReceiveDecision& decision,
        uint32_t& psnStart,
        uint32_t& psnEnd,
        std::vector<Ptr<UbWqeSegment>>& completedTaUnits);
    void CompleteInboundTaUnits(const std::vector<Ptr<UbWqeSegment>>& completedTaUnits);
```

- [ ] **Step 2: Implement `UpdateReceiveWindowAndCollectCompletedTa`**

Move the current `psn >= m_psnRecvNxt` block into:

```cpp
bool
UbTransportChannel::UpdateReceiveWindowAndCollectCompletedTa(
    const ReceivedDataPacketContext& ctx,
    const UbRetransReceiveDecision& decision,
    uint32_t& psnStart,
    uint32_t& psnEnd,
    std::vector<Ptr<UbWqeSegment>>& completedTaUnits)
{
    if (ctx.psn < m_psnRecvNxt) {
        return true;
    }

    const bool outOfOrderPacket = ctx.psn > m_psnRecvNxt;
    if (!SetBitmap(ctx.psn)) {
        NS_LOG_WARN("Over Out-of-Order! Max Out-of-Order :" << m_psnOooThreshold);
        return false;
    }

    m_congestionCtrl->OnReceiverDataPacketReceived(ctx.psn,
                                                   ctx.payloadBytes,
                                                   ctx.networkHeader);
    m_bufferedInboundPackets[ctx.psn] = {ctx.transportHeader,
                                         ctx.transactionHeader,
                                         ctx.logicalBytes,
                                         ctx.payloadBytes,
                                         ctx.flowTag.GetFlowId()};

    if (outOfOrderPacket) {
        NS_LOG_DEBUG("Out-of-Order Packet,tpn:{" << m_tpn << "} psn:{"
                     << ctx.psn << "} expectedPsn:{" << m_psnRecvNxt << "}");
        return !decision.dropPacket;
    }

    uint32_t oldRecvNxt = m_psnRecvNxt;
    while (m_psnRecvNxt < oldRecvNxt + m_psnOooThreshold) {
        uint32_t currentBitIndex = m_psnRecvNxt - oldRecvNxt;
        if (currentBitIndex >= m_recvPsnWindow.GetWindowSize() ||
            !m_recvPsnWindow.Contains(m_psnRecvNxt)) {
            break;
        }
        auto bufferedIt = m_bufferedInboundPackets.find(m_psnRecvNxt);
        if (bufferedIt == m_bufferedInboundPackets.end()) {
            NS_LOG_WARN("Missing buffered inbound packet for contiguous psn " << m_psnRecvNxt
                        << " on tpn " << m_tpn);
            break;
        }
        Ptr<UbWqeSegment> completedTaUnit =
            TrackInboundTaPacket(bufferedIt->second.tpHeader,
                                 bufferedIt->second.taHeader,
                                 bufferedIt->second.logicalBytes,
                                 bufferedIt->second.payloadBytes,
                                 bufferedIt->second.taskId);
        if (completedTaUnit != nullptr) {
            completedTaUnits.push_back(completedTaUnit);
        }
        m_bufferedInboundPackets.erase(bufferedIt);
        m_psnRecvNxt++;
    }

    if (m_psnRecvNxt > oldRecvNxt) {
        NS_LOG_DEBUG("Updated m_psnRecvNxt from " << oldRecvNxt
                     << " to " << m_psnRecvNxt);
        m_retrans->ClearNakSuppressionIfGapClosed(m_psnRecvNxt);
        uint32_t shiftCount = m_psnRecvNxt - oldRecvNxt;
        RightShiftBitset(shiftCount);
        psnStart = oldRecvNxt;
        psnEnd = m_psnRecvNxt;
    }
    return true;
}
```

- [ ] **Step 3: Implement `CompleteInboundTaUnits`**

Add:

```cpp
void
UbTransportChannel::CompleteInboundTaUnits(
    const std::vector<Ptr<UbWqeSegment>>& completedTaUnits)
{
    for (const Ptr<UbWqeSegment>& completedTaUnit : completedTaUnits) {
        if (completedTaUnit == nullptr) {
            continue;
        }
        GetTransaction()->HandleInboundTaUnit(m_tpn, completedTaUnit);
        WqeSegmentCompletesNotify(m_nodeId,
                                  completedTaUnit->GetTaskId(),
                                  completedTaUnit->GetTaSsn());
    }
}
```

- [ ] **Step 4: Replace inline receive-window block in `RecvDataPacket`**

Replace the `psnStart` / `psnEnd` receive-window block with:

```cpp
    uint32_t psnStart = 0;
    uint32_t psnEnd = 0;
    std::vector<Ptr<UbWqeSegment>> completedTaUnits;
    if (!UpdateReceiveWindowAndCollectCompletedTa(ctx,
                                                  receiveDecision,
                                                  psnStart,
                                                  psnEnd,
                                                  completedTaUnits)) {
        return;
    }
```

Replace the final completed TA loop with:

```cpp
    CompleteInboundTaUnits(completedTaUnits);
```

- [ ] **Step 5: Run receive-window tests**

Run:

```bash
./ns3 build
./test.py -s unified-bus-transport-ooo-regression
./test.py -s unified-bus-examples
```

Expected:

- Build succeeds.
- Both suites pass.

- [ ] **Step 6: Commit**

```bash
git add src/unified-bus/model/protocol/ub-transport.h \
        src/unified-bus/model/protocol/ub-transport.cc
git commit -m "refactor(transport): extract receive window advancement"
```

## Task 5: Extract ACK Decision To Response Context And Final Cleanup

**Files:**
- Modify: `src/unified-bus/model/protocol/ub-transport.h`
- Modify: `src/unified-bus/model/protocol/ub-transport.cc`

- [ ] **Step 1: Add helper declaration**

In `ub-transport.h`, add:

```cpp
    bool BuildAckResponseFromDecision(const UbRetransReceiveDecision& decision,
                                      uint32_t psnStart,
                                      uint32_t psnEnd,
                                      AckResponseContext& response);
```

- [ ] **Step 2: Implement `BuildAckResponseFromDecision`**

Add:

```cpp
bool
UbTransportChannel::BuildAckResponseFromDecision(
    const UbRetransReceiveDecision& decision,
    uint32_t psnStart,
    uint32_t psnEnd,
    AckResponseContext& response)
{
    if (decision.suppressResponse) {
        if (decision.selectiveAck) {
            NS_LOG_WARN("Suppressing TPSACK because SelectiveAckBitmapBits cannot be resolved");
        }
        return false;
    }

    response.opcode = decision.responseOpcode;
    response.psn = decision.responsePsn;
    response.selectiveAck = decision.selectiveAck;
    if (decision.selectiveAck) {
        NS_ASSERT_MSG(decision.selectiveAckHeader.has_value(),
                      "SELECTIVE receive decision requires SAETPH.");
        response.selectiveAckHeader = *decision.selectiveAckHeader;
    }
    response.congestionHeader =
        m_congestionCtrl->OnReceiverPrepareAckCongestionHeader(psnStart, psnEnd);
    return true;
}
```

- [ ] **Step 3: Simplify final ACK/SACK block in `RecvDataPacket`**

Replace the final decision-to-packet code with:

```cpp
    AckResponseContext response;
    const UbRetransReceiveDecision ackDecision =
        m_retrans->BuildReceiveDecisionForCurrentState();
    if (!BuildAckResponseFromDecision(ackDecision, psnStart, psnEnd, response)) {
        return;
    }

    NS_LOG_DEBUG("RecvDataPacket ready to send ack psn: " << response.psn << " node: " << m_src);
    Ptr<Packet> responsePacket = BuildTransportResponsePacket(ctx, response);
    EnqueueTransportResponse(responsePacket, "ack", response.psn);
    CompleteInboundTaUnits(completedTaUnits);
```

- [ ] **Step 4: Verify `RecvDataPacket` is now orchestration-only**

Manually inspect `RecvDataPacket()` and confirm it contains only:

```cpp
ReceivedDataPacketContext ctx;
ParseReceivedDataPacket
TraceReceivedDataPacket
m_retrans->OnDataPacketReceived
HandleImmediateRetransReceiveDecision
NotifyLastPacketReceived
HandleRepeatedDataPacket
UpdateReceiveWindowAndCollectCompletedTa
m_retrans->BuildReceiveDecisionForCurrentState()
BuildAckResponseFromDecision
BuildTransportResponsePacket
EnqueueTransportResponse
CompleteInboundTaUnits
```

- [ ] **Step 5: Run full focused tests**

Run:

```bash
./ns3 build
./test.py -s unified-bus-examples
./test.py -s unified-bus-transport-ooo-regression
./test.py -s unified-bus
```

Expected:

- Build succeeds.
- `unified-bus-examples` passes.
- `unified-bus-transport-ooo-regression` passes.
- If `unified-bus` still crashes at `src/unified-bus/model/ub-queue-manager.cc:401` with `m_headroomPerPortBytes > 0`, record it as existing known failure.

- [ ] **Step 6: Run representative retransmission scenarios**

Run:

```bash
./ns3 run --no-build "scratch/ub-quick-example --case-path=scratch/retrans/GBN_fast/first_tp_packet_loss"
./ns3 run --no-build "scratch/ub-quick-example --case-path=scratch/retrans/SELE_fast/first_tp_packet_loss"
./ns3 run --no-build "scratch/ub-quick-example --case-path=scratch/retrans/SELE_fast/non_first_tp_packet_loss_markpsn"
```

Expected:

- Each program finishes normally.
- Generated trace files still include `TPACK`, `TPNAK`, and `TPSACK` in representative ACK traces.

- [ ] **Step 7: Commit**

```bash
git add src/unified-bus/model/protocol/ub-transport.h \
        src/unified-bus/model/protocol/ub-transport.cc
git commit -m "refactor(transport): simplify RecvDataPacket flow"
```

## Self-Review

Spec coverage:

- `RecvDataPacket()` clear main flow: covered by Tasks 1, 3, 4, and 5.
- Unified ACK/NAK/SACK construction: covered by Task 2.
- Packet parsing/building remains in transport: covered by all tasks; no `ub-retrans` edits are planned.
- Retrans strategy behavior unchanged: covered by using existing `m_retrans` calls and no `ub-retrans` edits.
- Trace and response type preservation: covered by Task 5 validation.

Placeholder scan:

- No unresolved implementation placeholders are present.
- Every helper signature used later is declared before it is used in the plan.

Type consistency:

- `ReceivedDataPacketContext` and `AckResponseContext` names match across all tasks.
- All helper signatures in implementation steps match their declarations.
- `std::optional` usage is valid because `ub-transport.h` already includes `ub-retrans.h`, which includes `<optional>`; if the compiler requires a direct include, add `#include <optional>` to `ub-transport.h` near the existing standard-library includes.
