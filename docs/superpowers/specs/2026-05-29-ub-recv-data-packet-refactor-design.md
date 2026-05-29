# UB RecvDataPacket 重构设计

## 背景

`UbTransportChannel::RecvDataPacket()` 目前承担了过多职责：数据包头解析、接收 trace、GBN 立即 NAK 决策、重复包响应、接收窗口推进、乱序缓存、TA unit 完成、ACK/NAK/SACK packet 构造和入队都在同一个函数里。重传策略已经迁入 `ub-retrans.h/.cc` 后，这个函数仍然偏长，主要问题变成 transport 公共流程和 response packet 构造重复代码混在一起。

本次重构只整理 `RecvDataPacket()` 的结构，不改变 GBN、选择性重传、快速重传、MarkPSN、SACK bitmap、拥塞控制、trace 或 WQE/TA 完成语义。

## 目标

- 让 `RecvDataPacket()` 变成一条清晰主流程。
- 统一 ACK/NAK/SACK packet 构造逻辑，避免 duplicate path 和 normal path 重复拼 header。
- 保持 packet parsing/building 仍在 `UbTransportChannel`，不迁入 `ub-retrans`。
- 保持 retrans controller 只返回决策，transport 继续负责按决策构造响应包。
- 保持现有测试和场景行为不变。

## 非目标

- 不调整 `UbRetransController` / GBN / SELECTIVE / MarkPSN 的策略逻辑。
- 不改变 `RecvTpAck()`、`GetNextPacket()` 或 RTO 逻辑。
- 不新增业务属性。
- 不修改 scratch 场景配置。
- 不改变 trace 文本格式和 packet 分类。

## 设计

### 1. 接收数据包上下文

新增一个 transport 私有结构，用来承载 `RecvDataPacket()` 解析出来的包头、tag 和尺寸信息。

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
```

对应 helper：

```cpp
bool ParseReceivedDataPacket(Ptr<Packet> packet, ReceivedDataPacketContext& ctx);
void TraceReceivedDataPacket(const ReceivedDataPacketContext& ctx);
```

`ParseReceivedDataPacket()` 保留当前 header remove 顺序，填充 `psn`、`payloadBytes`、`logicalBytes` 和 `flowTag`。空包检查仍保留在 `RecvDataPacket()` 顶层或 parse helper 中。

### 2. 响应包上下文

新增一个 transport 私有结构，描述将要构造的 ACK/NAK/SACK。

```cpp
struct AckResponseContext
{
    TpOpcode opcode;
    uint64_t psn{0};
    bool selectiveAck{false};
    std::optional<UbSelectiveAckExtTph> selectiveAckHeader;
    std::optional<UbCongestionExtTph> congestionHeader;
};
```

对应 helper：

```cpp
Ptr<Packet> BuildTransportResponsePacket(const ReceivedDataPacketContext& ctx,
                                         const AckResponseContext& response);
void EnqueueTransportResponse(Ptr<Packet> response, const char* logType, uint64_t psn);
```

`BuildTransportResponsePacket()` 统一处理：

- `UbAckTransactionHeader`
- 可选 `UbSelectiveAckExtTph`
- 可选 `UbCongestionExtTph`
- `UbTransportHeader`
- UDP/IP/network/datalink headers

`EnqueueTransportResponse()` 统一处理：

- `m_headArrivalTime`
- `m_ackQ.push(response)`
- response 发送 debug log
- `TriggerTransportTransmit()`

### 3. 立即重传响应处理

GBN fast retrans 下，`m_retrans->OnDataPacketReceived(psn)` 可能返回 `shouldNak` 或 `suppressResponse`。新增 helper：

```cpp
bool HandleImmediateRetransReceiveDecision(const ReceivedDataPacketContext& ctx,
                                           const UbRetransReceiveDecision& decision);
```

语义：

- `suppressResponse`：记录现有 debug log 并返回 true。
- `shouldNak`：构造 TPNAK response，入队并触发发送，返回 true。
- 其他：返回 false，主流程继续。

### 4. 重复包响应处理

重复包路径当前和普通 ACK/SACK 路径有大量重复。新增 helper：

```cpp
bool HandleRepeatedDataPacket(const ReceivedDataPacketContext& ctx);
```

语义：

- 若 `IsRepeatPacket(ctx.psn)` 为 false，返回 false。
- 调用 `m_retrans->BuildReceiveDecisionForCurrentState()`。
- 若 suppress，保持现有 warning/return 行为。
- 若是普通 ACK，duplicate path 继续使用 `TP_OPCODE_ACK_WITHOUT_CETPH`，保持旧行为。
- 若是 selective ACK，按 decision 构造 SACK。
- 入队 response 并触发发送后返回 true。

### 5. 接收窗口推进与 TA 完成收集

把 receive bitmap、乱序缓存、连续 PSN 推进和 completed TA unit 收集拆成 helper：

```cpp
bool UpdateReceiveWindowAndCollectCompletedTa(const ReceivedDataPacketContext& ctx,
                                              const UbRetransReceiveDecision& decision,
                                              uint32_t& psnStart,
                                              uint32_t& psnEnd,
                                              std::vector<Ptr<UbWqeSegment>>& completedTaUnits);
```

语义：

- 保持 `SetBitmap()` 越界时 warning 并停止处理。
- 保持 `OnReceiverDataPacketReceived()` 调用位置。
- 保持 out-of-order + GBN drop 行为。
- 保持 `m_bufferedInboundPackets` 写入和连续 PSN 推进逻辑。
- 保持 `ClearNakSuppressionIfGapClosed()` 和 `RightShiftBitset()` 调用。

返回值表示主流程是否应继续构造普通 ACK/SACK。

### 6. 普通 ACK/SACK 构造

新增 helper：

```cpp
bool BuildAckResponseFromDecision(const UbRetransReceiveDecision& decision,
                                  uint32_t psnStart,
                                  uint32_t psnEnd,
                                  AckResponseContext& response);
```

语义：

- suppress 时保持当前 warning/return 行为，返回 false。
- selective ACK 时要求 `decision.selectiveAckHeader.has_value()`。
- 按 `decision.responseOpcode` 和 `decision.responsePsn` 设置 response。
- 调用 `m_congestionCtrl->OnReceiverPrepareAckCongestionHeader(psnStart, psnEnd)` 生成 CETPH。

### 7. 主流程目标形态

重构后 `RecvDataPacket()` 目标形态如下：

```cpp
void
UbTransportChannel::RecvDataPacket(Ptr<Packet> packet)
{
    ReceivedDataPacketContext ctx;
    if (!ParseReceivedDataPacket(packet, ctx)) {
        return;
    }

    TraceReceivedDataPacket(ctx);

    const UbRetransReceiveDecision receiveDecision =
        m_retrans->OnDataPacketReceived(ctx.psn);
    if (HandleImmediateRetransReceiveDecision(ctx, receiveDecision)) {
        return;
    }

    if (ctx.transportHeader.GetLastPacket()) {
        NotifyLastPacketReceived(ctx);
    }

    if (HandleRepeatedDataPacket(ctx)) {
        return;
    }

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

    AckResponseContext response;
    const UbRetransReceiveDecision ackDecision =
        m_retrans->BuildReceiveDecisionForCurrentState();
    if (!BuildAckResponseFromDecision(ackDecision, psnStart, psnEnd, response)) {
        return;
    }

    Ptr<Packet> responsePacket = BuildTransportResponsePacket(ctx, response);
    EnqueueTransportResponse(responsePacket, "Ack", response.psn);
    CompleteInboundTaUnits(completedTaUnits);
}
```

## 行为保持点

- TPNAK、TPACK、TPSACK 的 opcode 和 header 顺序保持不变。
- duplicate packet 的普通 ACK 仍使用 `TP_OPCODE_ACK_WITHOUT_CETPH`。
- selective ACK bitmap 仍由 `m_retrans->BuildReceiveDecisionForCurrentState()` 提供。
- `m_ackQ` 入队、`m_headArrivalTime` 更新、`TriggerTransportTransmit()` 时机保持不变。
- inbound TA unit 完成仍在 response 入队后处理。
- `LastPacketReceivesNotify()` 时机保持不变。
- GBN out-of-order drop 仍发生在 receive bitmap 和 receiver accounting 更新之后。

## 验证计划

运行：

```bash
./ns3 build
./test.py -s unified-bus-examples
./test.py -s unified-bus-transport-ooo-regression
./test.py -s unified-bus
```

若 `./test.py -s unified-bus` 仍触发既有 `ub-queue-manager.cc:401 m_headroomPerPortBytes > 0`，记录为既有问题，不作为本次重构失败依据。

再运行代表性场景：

```bash
./ns3 run --no-build "scratch/ub-quick-example --case-path=scratch/retrans/GBN_fast/first_tp_packet_loss"
./ns3 run --no-build "scratch/ub-quick-example --case-path=scratch/retrans/SELE_fast/first_tp_packet_loss"
./ns3 run --no-build "scratch/ub-quick-example --case-path=scratch/retrans/SELE_fast/non_first_tp_packet_loss_markpsn"
```

并检查 trace 中仍能看到 `TPACK`、`TPNAK`、`TPSACK`。
