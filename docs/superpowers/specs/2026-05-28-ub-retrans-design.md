# UB 传输层重传重构设计

## 目标

将 RTP 重传逻辑从 `ub-transport.cc` 中拆出，放到
`src/unified-bus/model/protocol/` 下独立的 `ub-retrans.h/.cc` 模块中。

本次重构需要保持现有对外行为和 ns-3 Attribute 配置方式稳定，同时让
`UbTransportChannel` 更专注于传输层公共流程：

- packet 解析和 packet 构造
- ACK/CNP 队列
- WQE segment 调度和完成
- 接收缓存和事务完成
- trace 回调
- 拥塞控制集成点
- 端口发送触发

新的重传模块负责重传策略、RTO 管理，以及不同重传模式专属的状态。

## 规范背景

UB Base Specification 2.0.1 的 6.4.2 节将重传机制拆成两条轴：

- 重传范围：GoBackN 或选择性重传
- 触发方式：快速重传或超时重传

超时重传是必须启用的机制，快速重传是可选机制。两者同时启用时，超时重传作为快速重传的兜底机制，用于处理尾 data packet 丢失、尾 ACK/SACK 丢失、负反馈或选择性反馈丢失等场景。

重构后需要保持以下四种有效工作模式：

- GBN with fast retransmission
- GBN without fast retransmission
- selective retransmission with fast retransmission
- selective retransmission without fast retransmission

选择性重传配合快速重传时，还可以启用 MarkPSN。MarkPSN 状态必须从
`UbTransportChannel` 中移出。

## 新增文件

新增：

- `src/unified-bus/model/protocol/ub-retrans.h`
- `src/unified-bus/model/protocol/ub-retrans.cc`

更新：

- `src/unified-bus/CMakeLists.txt`

只有当测试或其它模块需要直接 include 重传类型时，才需要把
`model/protocol/ub-retrans.h` 加入 public header 列表。否则它可以作为内部 model header，由
`ub-transport.h/.cc` include。

## 高层架构

`UbTransportChannel` 持有一个重传控制器：

```cpp
std::unique_ptr<UbRetransController> m_retrans;
```

重传模块包含：

```cpp
class UbRetransController;
class UbRetransStrategy;
class UbGbnRetransStrategy;
class UbSelectiveRetransStrategy;
```

`UbRetransController` 是 `UbTransportChannel` 使用的稳定集成入口。它持有通用重传配置和 RTO 状态，选择当前生效的策略，并把不同模式下的行为分发给具体 strategy。

`UbRetransStrategy` 是模式接口。`UbGbnRetransStrategy` 和
`UbSelectiveRetransStrategy` 分别实现 GBN 和选择性重传行为。

controller 可以持有 `UbTransportChannel` 的引用，但访问 transport 状态时应通过窄接口完成。重传模块不应变成第二个 transport 实现，也不应随意修改与重传无关的 channel 状态。

## 状态归属

以下通用重传字段从 `UbTransportChannel` 移到 `UbRetransController`：

- 是否启用重传
- 初始 RTO
- 当前 RTO
- 最大重传次数
- 剩余重传次数
- 重传指数退避因子
- 重传 timer event
- 重传模式
- 是否启用快速重传
- 选择性 ACK bitmap 配置
- 是否启用 selective MarkPSN

以下 selective-only 字段移到 `UbSelectiveRetransStrategy`：

- sent PSN state map
- selective retransmission queue
- 每个 PSN 的 ACK、missing、retransmit 计数状态
- MarkPSN retransmission phase 标记
- MarkPSN awaiting-first-new 标记
- MarkPSN 是否有效以及 MarkPSN 值
- last first selective retransmission PSN 是否有效以及对应值

以下 GBN-only 字段移到 `UbGbnRetransStrategy`：

- last GBN NAK PSN suppression state

以下公共传输字段保留在 `UbTransportChannel`：

- 发送和接收 PSN 游标
- 已接收的最大 PSN
- 是否已经收到过 PSN
- 接收 bitmap/window
- buffered inbound packet map
- WQE segment vector
- ACK 和 CNP 队列
- congestion control 对象
- trace sources 和 trace helpers
- transaction completion helpers

这些字段不只服务重传，也参与正常 transport 发送、接收和事务完成流程。

## Controller 接口

controller 提供与 transport 事件对应的高层接口：

```cpp
class UbRetransController
{
public:
    explicit UbRetransController(UbTransportChannel& transport);

    Ptr<Packet> TryGetNextRetransmissionPacket();

    void OnNewDataPacketSent(uint64_t psn,
                             Ptr<Packet> packet,
                             uint32_t payloadBytes,
                             uint32_t logicalBytes,
                             Ptr<UbWqeSegment> segment);

    UbRetransAckResult OnTransportResponse(const UbTransportHeader& tph,
                                           TpOpcode opcode,
                                           const UbSelectiveAckExtTph* saetph,
                                           const UbCongestionExtTph* cetph);

    UbRetransReceiveDecision OnDataPacketReceived(const UbTransportHeader& tph,
                                                  uint32_t payloadBytes,
                                                  uint32_t logicalBytes);

    UbRetransTimeoutResult OnTimeout();

    void StartTimerIfNeeded();
    void RestartTimerAfterAckProgress();
    void CancelTimer();
};
```

实现时可以根据代码需要调整具体函数签名，但方向需要保持一致：transport 上报事件，重传模块返回决策。

## 返回结果类型

使用小型结果结构体，避免函数参数列表过长。

```cpp
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
    uint64_t responsePsn{0};
    TpOpcode responseOpcode{TpOpcode::TP_OPCODE_ACK_WITHOUT_CETPH};
    std::optional<UbSelectiveAckExtTph> selectiveAckHeader;
};

struct UbRetransTimeoutResult
{
    bool triggerTransmit{false};
};
```

`UbTransportChannel` 根据这些 decision 执行真正的 packet 构造、入队、trace、timer 交互和端口触发。

## 重构后的 Transport 流程

`GetNextPacket()` 保留控制包优先级，只把重传包选择交给重传模块：

```cpp
SendCnpIfAny();
SendAckIfAny();

if (Ptr<Packet> p = m_retrans->TryGetNextRetransmissionPacket()) {
    return p;
}

return TrySendNewDataPacket();
```

新 data packet 生成并通过拥塞控制后：

```cpp
m_retrans->OnNewDataPacketSent(psn, packet, payloadBytes, logicalBytes, segment);
m_retrans->StartTimerIfNeeded();
```

`RecvTpAck()` 负责解析 response，然后把 ACK/SACK/NAK 的模式相关语义交给重传模块：

```cpp
UbRetransAckResult result =
    m_retrans->OnTransportResponse(tph, opcode, saetphOrNull, cetphOrNull);

ApplyAckProgress(result);
```

`RecvDataPacket()` 负责解析 header 并维护公共接收状态，然后询问重传模块是否需要回复应答：

```cpp
UbRetransReceiveDecision decision =
    m_retrans->OnDataPacketReceived(tph, payloadBytes, logicalBytes);

ApplyReceiveDecision(decision);
MaybeQueueTransportResponse(decision);
```

`ReTxTimeout()` 可以变成很薄的转发函数：

```cpp
m_retrans->OnTimeout();
```

RTO 的退避、重传次数统计、重新调度、是否触发发送，都由 controller 负责。

## Strategy 职责

### GBN Strategy

`UbGbnRetransStrategy` 负责：

- sender 侧 TPNAK 处理
- 从 NAK PSN 开始的 GBN 快速重传
- 从 `SndUna` 开始的 RTO 重传
- receiver 侧乱序处理
- 重复 TPNAK 抑制
- 接收 gap 关闭后清理 TPNAK 抑制状态

它不构造完整 ACK packet，只返回接收决策，要求 transport 去排队 TPACK 或 TPNAK。

### Selective Strategy

`UbSelectiveRetransStrategy` 负责：

- 保留已发送 packet 副本用于重传
- sender 侧 TPSACK 处理
- 从 TPACK 或 TPSACK 更新累计 ACK 状态
- 根据 SAETPH 收集缺失 PSN
- 选择性重传队列管理
- 重复入队抑制
- 每个 PSN 的重传计数
- 稀疏重传 packet 选择
- RTO 时把 outstanding 且未 ACK 的 PSN 放入重传队列
- receiver 侧 selective ACK bitmap 构造
- MarkPSN 阶段切换

它拥有 `SentPsnState` 和 MarkPSN 状态机。

## Attribute 兼容性

对外 ns-3 attributes 仍挂在 `UbTransportChannel` 上，名字保持不变。内部存储迁移到
`UbRetransController`。

对于原来直接绑定成员变量的 attribute，改成 transport getter/setter 转发：

```cpp
MakeBooleanAccessor(&UbTransportChannel::SetRetransEnable,
                    &UbTransportChannel::GetRetransEnable)
```

setter 转发到 `m_retrans->SetEnable(...)`，getter 转发到
`m_retrans->GetEnable()`。现有配置文件和命令行覆盖方式保持可用。

## 函数迁移清单

将以下内容从 `ub-transport.cc/.h` 移动或重写到 `ub-retrans.cc/.h`：

- `SentPsnState`
- `ResolveSelectiveAckBitmapBits`
- `GetSelectiveAckBitmapBits`
- `GetSelectiveAckBase`
- `BuildSelectiveAckHeader`
- `RetainSentPsn`
- `MarkPsnAcked`
- `AcknowledgeCumulativePsn`
- `AdvanceSendUnaFromAckState`
- `CollectMissingPsnsFromSelectiveAck`
- `GetMissingPsnsFromSelectiveAck`
- `QueueSelectiveRetransmission`
- `CompactSelectiveRetransmissionQueue`
- `HasPendingSelectiveRetransmission`
- `CanSendSelectiveRetransmission`
- `GetNextSelectiveRetransmissionSize`
- `GetNextSelectiveRetransmissionLogicalBytes`
- `PrepareGbnRetransmissionFromPsn`
- `IsSelectiveMarkPsnEnabled`
- `SelectiveAckReportsReceivedAtOrAboveMarkPsn`
- `EnterSelectiveMarkPsnRetransPhase`
- `FinishSelectiveMarkPsnRetransPhaseIfDone`
- `MaybeMarkFirstNewSelectivePacket`
- RTO event scheduling and backoff logic

在 `UbTransportChannel` 中保留或新增这些公共 helper：

- data packet 生成
- response packet 构造和入队
- inbound TA packet 跟踪
- WQE segment 完成
- trace notification helpers
- congestion control 对象归属
- port 查找和 transmit trigger wrapper

## 错误处理

未知 retransmission mode 保持 assertion failure。

Malformed TPSACK 解析仍留在 transport packet parsing 里，因为这是 header decoding，不是重传策略。

非法 selective ACK bitmap 配置由 controller 或 selective strategy 检查。如果配置非法，receive decision 应按当前行为抑制 TPSACK，保持行为兼容。

重传次数耗尽时，第一阶段保持当前 assertion 行为。后续可以再替换为规范定义的 TP Channel error reporting 路径。

## 测试

优先运行现有聚焦测试：

- selective receiver TPSACK for receive gap
- selective receiver returning to TPACK after gap closes
- first-packet-loss TPSACK behavior
- duplicate packet TPSACK behavior
- sender TPSACK consumption
- local sink TPSACK dispatch
- default GBN out-of-order silence
- GBN fast TPNAK behavior

然后运行重传场景族：

- `GBN_fast`
- `GBN_unfast`
- `SELE_fast`
- `SELE_unfast`

如果新增直接单测，优先覆盖少依赖完整 packet 构造的状态逻辑：

- selective missing PSN queue deduplication
- MarkPSN phase transitions
- GBN TPNAK-triggered send cursor rollback
- RTO backoff and attempt accounting

## 迁移计划

按小步、行为保持的方式实施：

1. 添加 `ub-retrans.h/.cc` 和 CMake entries，不改变行为。
2. 引入 `UbRetransController` 和 attribute forwarding，同时保留旧逻辑生效。
3. 将 RTO 状态和 timeout handling 移入 controller。
4. 将 GBN TPNAK/RTO 逻辑移入 `UbGbnRetransStrategy`。
5. 将 selective sent-PSN state、retransmission queue 和 TPSACK processing 移入
   `UbSelectiveRetransStrategy`。
6. 将 MarkPSN 状态移入 `UbSelectiveRetransStrategy`。
7. 简化 `GetNextPacket`、`RecvTpAck`、`RecvDataPacket` 和 `ReTxTimeout`，使其变为公共流程加 controller 调用。
8. 删除 `UbTransportChannel` 中过时的状态和 test-only accessors；仍被测试需要的 accessor 转发到 controller。

## 风险

风险最高的区域是：

- ns-3 attribute 初始化顺序和 controller 构造时机
- selective retransmission 的 packet copy 生命周期
- flow 完成和 object disposal 时的 RTO timer 取消
- 拥塞控制 callback 时机保持不变
- trace 输出格式和 packet type 分类保持不变
- 当前直接读取 transport private state 的 test-only accessors

缓解方式：保持 public attributes 和 trace 名字稳定，一次只迁移一组行为，并在每个迁移阶段后运行聚焦测试。
