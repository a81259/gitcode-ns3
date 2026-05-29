# UB Transport 主流程重构设计

## 背景

`RecvDataPacket()` 已经被拆成较清晰的接收流水线。`ub-transport.cc` 中仍有两个主干函数承担了较多职责：

- `RecvTpAck()`：处理 CNP、TPNAK、TPACK、TPSACK，并在 ACK 推进后完成 RTO、WQE segment、发送触发等收尾。
- `TryGetNextNewDataPacket()`：处理发送前限制检查、选择 segment、生成 data packet、通知重传和拥塞控制、更新发送状态。

本次重构目标是让这两个函数保留主流程编排职责，把协议分支和重复收尾逻辑拆到命名明确的私有 helper 中。重构不改变重传策略、RTO 计算、包格式、trace 语义或发送顺序。

## 目标

1. `RecvTpAck()` 按协议分支组织：
   - CNP 独立早返回。
   - TPNAK 独立早返回。
   - TPACK/TPSACK 走统一 ACK response 路径。
   - ACK 推进后的 RTO reset、WQE 完成、idle/继续发送作为公共收尾。

2. `TryGetNextNewDataPacket()` 按发送流水线组织：
   - 发送前公共限制检查。
   - 构造下一包发送上下文。
   - 发送新 data packet 并更新发送侧状态。

3. 增加少量注释，只解释关键流程边界和早返回原因，不写逐行解释。

## 非目标

- 不修改 `ub-retrans.*` 的重传策略行为。
- 不修改 `GenDataPacket()` 的 header 构造细节。
- 不修改 ACK/SACK/TPNAK/CNP wire format。
- 不调整 RTO 静态/动态模式逻辑。
- 不引入新的测试用例，优先依赖已有 focused suite 和代表性 retrans 场景验证行为不变。

## RecvTpAck 设计

新增私有上下文结构：

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

新增 helper：

```cpp
bool ParseTransportResponsePacket(Ptr<Packet> packet, TransportResponseContext& ctx);
bool HandleReceivedCnp(const TransportResponseContext& ctx);
bool HandleReceivedTpNak(const TransportResponseContext& ctx);
bool HandleReceivedAckOrSack(const TransportResponseContext& ctx,
                             uint64_t previousSndUna,
                             UbRetransAckResult& ackResult);
void FinalizeTransportAckProgress(const TransportResponseContext& ctx,
                                  uint64_t previousSndUna);
void CompleteAckedWqeSegments(const TransportResponseContext& ctx);
void UpdateSenderAfterTransportAck(const TransportResponseContext& ctx,
                                   uint64_t previousSndUna);
```

`RecvTpAck()` 最终形态：

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

职责划分：

- `ParseTransportResponsePacket()` 负责空指针检查、TP opcode 分类、按 opcode 移除 CETPH/SAETPH/CNP/TA header。 malformed TPSACK 保持现有 WARN 后丢弃。
- `HandleReceivedCnp()` 负责 CNP header 转成 congestion notification 并早返回。
- `HandleReceivedTpNak()` 负责 TPNAK debug/trace、调用 `m_retrans->OnTransportResponse()`、必要时触发发送，并早返回。
- `HandleReceivedAckOrSack()` 负责 ACK/TPSACK 公共响应处理：CETPH 拥塞通知、SACK trace、调用 retrans controller、处理 `ignoreResponse` 和 `triggerTransmit`。
- `FinalizeTransportAckProgress()` 负责普通 ACK/SACK 后的公共收尾。
- `CompleteAckedWqeSegments()` 从公共收尾中拆出 WQE segment 完成逻辑，保持原有 `ShouldCompleteOnTpAck()`、`ProcessWqeSegmentComplete()`、`WqeSegmentCompletesNotify()` 和 `ApplyNextWqeSegment()` 时机。
- `UpdateSenderAfterTransportAck()` 处理 `m_tpFullFlag` 恢复、transport idle 通知、必要时触发发送。

关键注释建议：

- 在 CNP/TPNAK helper 前说明它们是控制/负反馈路径，不进入 ACK 推进收尾。
- 在 `FinalizeTransportAckProgress()` 中说明只有 `m_psnSndUna` 推进时才重置 RTO。
- 在 WQE 完成循环前说明浅流水按仍可继续发送的 active segment 计数。

## TryGetNextNewDataPacket 设计

新增私有上下文结构：

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

新增 helper：

```cpp
bool CanTrySendNewDataPacket();
bool BuildNextDataSendContext(NewDataSendContext& ctx);
Ptr<Packet> SendNewDataPacket(const NewDataSendContext& ctx);
void NotifyNewDataPacketSent(const NewDataSendContext& ctx, Ptr<Packet> packet);
void AdvanceNewDataSendState(const NewDataSendContext& ctx, Ptr<Packet> packet);
```

`TryGetNextNewDataPacket()` 最终形态：

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

职责划分：

- `CanTrySendNewDataPacket()` 处理空 segment、inflight limit、对应 debug trace 和 `m_sendWindowLimited` 更新。
- `BuildNextDataSendContext()` 遍历 `m_wqeSegmentVector`，找到第一个未完成 segment，计算 progress/payload/wire/total bytes，并处理 CC limited 早返回。
- `SendNewDataPacket()` 调用 `GenDataPacket()` 并串联发送后的状态更新。
- `NotifyNewDataPacketSent()` 负责重传保留、拥塞控制发送通知、first/last packet notify 和 debug 日志。
- `AdvanceNewDataSendState()` 负责 `UpdateSentBytes()`、`m_psnSndNxt++`、`TraceTpDebugState("SEND_PACKET")`、启动 RTO、浅流水补 segment、更新 `m_headArrivalTime`。

关键注释建议：

- 在 `BuildNextDataSendContext()` 中说明它只选择新 data packet，不处理重传包。
- 在 `AdvanceNewDataSendState()` 中保留浅流水注释，因为这是现有行为的语义说明。

## 数据流

`RecvTpAck()` 数据流：

```text
Packet
  -> TransportResponseContext
  -> CNP / TPNAK early return
  -> retrans controller ACK/SACK update
  -> ACK progress finalization
```

`TryGetNextNewDataPacket()` 数据流：

```text
WQE segment vector
  -> NewDataSendContext
  -> GenDataPacket()
  -> retrans/congestion/trace notify
  -> PSN and segment send state update
```

## 错误处理

- Null ACK packet：保持现有 error log 后返回。
- malformed TPSACK：保持现有 WARN 后返回。
- CNP/TPNAK：处理完成后早返回，不进入 ACK progress finalization。
- CC limited / inflight limited / no segment：保持现有 trace 和 `nullptr` 返回行为。

## 测试策略

每个阶段至少运行：

```bash
./ns3 build
./test.py -s unified-bus-transport-ooo-regression
./test.py -s unified-bus-examples
git diff --check
```

收尾时运行代表性重传场景：

```bash
./ns3 run --no-build "scratch/ub-quick-example --case-path=scratch/retrans/GBN_fast/first_tp_packet_loss"
./ns3 run --no-build "scratch/ub-quick-example --case-path=scratch/retrans/SELE_fast/first_tp_packet_loss"
./ns3 run --no-build "scratch/ub-quick-example --case-path=scratch/retrans/SELE_fast/non_first_tp_packet_loss_markpsn"
```

## 实施顺序

1. 先重构 `RecvTpAck()`，因为它和重传 ACK 状态、RTO reset、WQE 完成关系最密切。
2. 再重构 `TryGetNextNewDataPacket()`，整理发送侧主流程。
3. 每一步独立提交，便于回退和审查。
