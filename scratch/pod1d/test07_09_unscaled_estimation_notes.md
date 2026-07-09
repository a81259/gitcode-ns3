# Test07-09 原始流量估算说明

单位为 `us`。`max_complete_us` 取自 `task_statistics.csv` 中最大的 `taskCompletesTime(us)`。

## 实测输入

用于三点拟合的实测值如下：

| case | scale80 | scale40 | scale20 |
|---|---:|---:|---:|
| test07 case01_standard | 36.034895 | 64.104729 | 116.585819 |
| test07 case04_l1_l2_lane_down | 35.360859 | 65.325278 | 114.758932 |
| test07 case05_l1_l2_port_down | 36.381248 | 65.291457 | 117.322570 |

用于比例外推的 scale40 实测值如下：

| test | case01 | case02 | case03 | case04 | case05 |
|---|---:|---:|---:|---:|---:|
| test07 | 64.104729 | 82.509996 | 63.394548 | 65.325278 | 65.291457 |
| test08 | 58.004114 | 73.016778 | 58.105480 | 59.426624 | 58.288470 |

test09 不单独拟合，按 traffic 原始总量比例从 test07 推算：

```text
test09 / test07 = 1161805431168 / 1366829927712 = 0.85
```

## 基础公式

定义：

```text
x = 当前流量 / 原始流量 = 1 / 缩小倍数
T(x) = a*x + b
```

基础公式如下：

| 编号 | 来源 | 公式 | T(1) |
|---|---|---|---:|
| F1 | test07 case01，scale20/40/80 三点拟合 | `T1(x) = 2141.055920*x + 9.794350` | 2150.850270 |
| F2 | test07 case04，scale20/40/80 三点拟合 | `T2(x) = 2097.291120*x + 10.644032` | 2107.935152 |
| F3 | test07 case05，scale20/40/80 三点拟合 | `T3(x) = 2147.408006*x + 10.365691` | 2157.773697 |

## 估算公式

| test | case | 估算公式 | T(1) |
|---|---|---|---:|
| test07 | case01_standard | `F1` | 2150.850270 |
| test07 | case02_host_l1_lane_down | `(82.509996 / 64.104729) * F1` | 2768.386201 |
| test07 | case03_host_l1_port_down | `(63.394548 / 64.104729) * F1` | 2127.022184 |
| test07 | case04_l1_l2_lane_down | `F2` | 2107.935152 |
| test07 | case05_l1_l2_port_down | `F3` | 2157.773697 |
| test08 | case01_standard | `(58.004114 / 64.104729) * F1` | 1946.161636 |
| test08 | case02_host_l1_lane_down | `(73.016778 / 64.104729) * F1` | 2449.868506 |
| test08 | case03_host_l1_port_down | `(58.105480 / 64.104729) * F1` | 1949.562681 |
| test08 | case04_l1_l2_lane_down | `(59.426624 / 64.104729) * F1` | 1993.889878 |
| test08 | case05_l1_l2_port_down | `(58.288470 / 64.104729) * F1` | 1955.702386 |
| test09 | case01_standard | `0.85 * test07 case01` | 1828.222718 |
| test09 | case02_host_l1_lane_down | `0.85 * test07 case02` | 2353.128256 |
| test09 | case03_host_l1_port_down | `0.85 * test07 case03` | 1807.968845 |
| test09 | case04_l1_l2_lane_down | `0.85 * test07 case04` | 1791.744868 |
| test09 | case05_l1_l2_port_down | `0.85 * test07 case05` | 1834.107631 |

简要口径：

```text
test07 case01/04/05: 使用 scale20/40/80 三点线性拟合。
test07 case02/03: 使用 scale40 相对 case01 的比例乘以 F1。
test08: 使用 scale40 相对 test07 case01 的比例乘以 F1。
test09: 按 traffic 原始总量比例 0.85 从 test07 同 case 推算。
```
