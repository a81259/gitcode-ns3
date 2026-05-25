# UB 传输层重传机制更新说明

本文档记录在拉取选择性重传 PR 后，本地为验证和修复 6.4 可靠传输机制所做的主要修改。后续提交时可随代码和 `scratch/retrans` 用例一起携带。

## 1. 修改范围

本轮更新主要围绕以下目标展开：

- 支持按 PSN、包类型、出现次数精确注入重传相关故障。
- 修复 GoBackN 快速重传场景下 TPNAK 的生成和处理。
- 完善选择性重传 sender/receiver 对 TPSACK、Bitmap、MaxRcvPSN 的处理。
- 实现选择性重传配合快速重传时的 MarkPSN 机制。
- 构建覆盖 GBN/SELE、fast/unfast 四类模式的对照 case。
- 根据 runlog 生成并保留每个 case 的 `runlog_flow.svg`，方便和文档流程图对齐检查。

## 2. 代码侧主要更新

### 2.1 重传故障注入

新增 `retrans_fault.csv` 机制，相关实现集中在：

- `src/unified-bus/model/ub-fault.cc`
- `src/unified-bus/model/ub-fault.h`

当 `UB_FAULT_ENABLE=true` 时，原有 `fault.csv` 仍可使用，同时会尝试读取同目录下的 `retrans_fault.csv`。

`retrans_fault.csv` 支持按以下条件匹配：

- `packetType`: `DATA`、`TPACK`、`TPSACK`、`TPNAK`、`ANY`
- `psn`: 指定 PSN 或 `any`
- `lastPacket`: `true`、`false`、`any`
- `direction`: `forward`、`reverse`、`any`
- `dropCount`: 丢弃前 N 次匹配包
- `delayNs` / `delayCount`: 延迟前 N 次匹配包
- `nodeId` / `portId` / `taskId`: 限定注入位置和业务

schema 说明见：

- `scratch/retrans/retrans_fault_schema.md`

### 2.2 TPNAK 与 GBN 快速重传

为 GBN fast 场景补充 TPNAK 支持：

- 在 `TpOpcode` 中加入 `TP_OPCODE_NAK_WITHOUT_CETPH`。
- Receiver 检测到 GBN 乱序且 gap 未恢复时发送 TPNAK。
- Sender 收到 TPNAK 后从 NAK 指示的 PSN 开始 GoBackN 快速重传。
- 对重复 gap 抑制重复 TPNAK，避免同一个缺口持续刷 NAK。

涉及文件：

- `src/unified-bus/model/ub-datatype.h`
- `src/unified-bus/model/protocol/ub-transport.cc`
- `src/unified-bus/model/protocol/ub-transport.h`

### 2.3 选择性重传 sender 状态

在 sender 侧维护已发送 PSN 状态，用于处理 TPSACK：

- 保留已发送包副本，用于选择性重传。
- 根据 TPSACK bitmap 标记已接收 PSN。
- 根据 TPSACK bitmap 和 MaxRcvPSN 找出缺失 PSN。
- 对缺失 PSN 建立选择性重传队列。
- 避免重复入队和重复重传。

核心状态包括：

- `m_sentPsnState`
- `m_selectiveRetransmitQ`
- `SentPsnState::acknowledged`
- `SentPsnState::selectivelyReportedMissing`
- `SentPsnState::retransmitPending`
- `SentPsnState::retransmitCount`

### 2.4 MarkPSN 机制

新增配置开关：

```txt
default ns3::UbTransportChannel::EnableSelectiveMarkPsn "true"
```

MarkPSN 只在以下条件同时成立时生效：

- `RetransmissionMode == SELECTIVE`
- `EnableFastSelectiveRetrans == true`
- `EnableSelectiveMarkPsn == true`

主要逻辑：

1. 选择性重传阶段结束后，进入“等待首个新包”状态。
2. 发送后续第一个新包时记录为 `m_selectiveMarkPsn`。
3. 收到 TPSACK 后，如果 bitmap 表明 `>= MarkPSN` 的包已经被 receiver 接收，则进入下一轮重传阶段。
4. 非首次丢失的 TP Packet 可以被快速识别并再次重传，不必等待 RTO。

核心函数：

- `IsSelectiveMarkPsnEnabled`
- `MaybeMarkFirstNewSelectivePacket`
- `SelectiveAckReportsReceivedAtOrAboveMarkPsn`
- `EnterSelectiveMarkPsnRetransPhase`
- `FinishSelectiveMarkPsnRetransPhaseIfDone`

### 2.5 ACK/NAK/SACK trace 输出

为方便读 runlog，将各类 transport response 都归到 ACK trace 文件中：

- TPACK 显示为 `ACK(PSN=...)`
- TPNAK 显示为 `NAK(PSN=...)`
- TPSACK 显示为 `SACK(PSN=...,MAX=...,BM=...)`

这样可以直接用：

- `AllPacketTrace_PKT_node_0.tr`
- `AllPacketTrace_ACK_node_1.tr`

对照流程图检查 sender/receiver 的包序、时间和 RTO。

## 3. 测试 case 组织

测试目录：

```txt
scratch/retrans/
```

四类模式：

```txt
GBN_fast/
GBN_unfast/
SELE_fast/
SELE_unfast/
```

每个 case 一般包含：

```txt
network_attribute.txt
topology.csv
node.csv
routing_table.csv
traffic.csv
retrans_fault.csv
runlog/
runlog_flow.svg
figure*.png
```

其中：

- `figure-6-xx.png` 表示该 case 有文档中的直接对应流程图。
- `figure-similar-6-xx.png` 表示文档没有该 case 的专属图，使用相似流程图辅助对照。
- `runlog_flow.svg` 是根据当前 runlog 整理出的实际流程图。

当前 case 覆盖：

### GBN_fast

- `first_tp_packet_loss`
- `non_first_tp_packet_loss`
- `tail_tp_packet_loss`
- `tpack_loss_followup_ok`
- `tail_tpack_loss`
- `tpnak_loss`

### GBN_unfast

- `first_tp_packet_loss`
- `non_first_tp_packet_loss`
- `out_of_order_no_actual_loss`
- `tail_tp_packet_loss`
- `tpack_loss_followup_ok`
- `tail_tpack_loss`

### SELE_fast

- `first_tp_packet_loss`
- `non_first_tp_packet_loss_no_markpsn`
- `non_first_tp_packet_loss_markpsn`
- `tail_tp_packet_loss`
- `tpack_loss_followup_ok`
- `tail_tpack_loss`
- `tpsack_loss_followup_ok`
- `tail_tpsack_loss`

### SELE_unfast

- `first_tp_packet_loss`
- `non_first_tp_packet_loss`
- `out_of_order_no_actual_loss`
- `tail_tp_packet_loss`
- `tpack_loss_followup_ok`
- `tail_tpack_loss`
- `tpsack_loss_followup_ok`
- `tail_tpsack_loss`

## 4. 已验证的关键行为

### 4.1 GBN_fast

- 首次 TP Packet 丢失时，receiver 回复 TPNAK，sender 立即 GoBackN 快速重传。
- 非首次 TP Packet 丢失时，第一次由 TPNAK 触发重传，重传再次丢失后等待 RTO。
- 尾 TP Packet 丢失无法由 receiver 检测，需要 RTO 触发。
- TPACK 丢失但后续 TPACK 到达时，累计确认可以完成流程。
- 尾 TPACK 丢失时，需要 RTO。
- TPNAK 丢失时，sender 依赖 RTO 继续重传。

### 4.2 GBN_unfast

- 检测乱序但实际未丢包时，后续累计 TPACK 可以取消 RTO。
- 实际丢包时，不启用快速重传，等待 RTO。
- 非首次丢包场景中，原包和第一次超时重传均丢失时，需要第二段 RTO；图中已标出 `25600ns` 和 `51200ns`。

### 4.3 SELE_fast

- 首次丢包时，TPSACK bitmap 指示缺失 PSN，sender 只重传缺失包。
- 无 MarkPSN 的非首次丢失场景，需要等待 RTO 后再次重传。
- 启用 MarkPSN 后，TPSACK 确认 MarkPSN 及之后的包到达时，可以快速识别非首次丢失并再次重传。
- TPSACK 丢失时，后续 TPSACK 仍可触发正确重传。
- 尾包丢失和尾 ACK/SACK 丢失仍需要 RTO。

### 4.4 SELE_unfast

- 不启用快速重传时，TPSACK 只更新 sender 状态，不立即重传。
- 实际丢包依赖 RTO。
- 乱序但未实际丢包时，后续 TPACK 可以累计确认并取消 RTO。
- 非首次丢包中，原包和第一次超时重传均丢失时，需要第二段 RTO；图中已标出 `25600ns` 和 `51200ns`。

## 5. 注意事项

- `fault.csv` 的概率丢包方式不适合验证文档流程图，因为无法稳定指定某个 PSN 或某类 ACK 丢失。
- `retrans_fault.csv` 是为 6.4 重传机制验证新增的确定性故障注入方式。
- `runlog_flow.svg` 是当前 runlog 的可视化结果，不是协议规范原图。
- 对于 `figure-similar-*.png` 的 case，应以文字说明和相似流程共同判断，不应误认为文档存在完全一一对应的原图。
- 当前没有保留生成 SVG 的脚本，只保留生成后的 `runlog_flow.svg`，避免后续提交携带临时生成工具。
