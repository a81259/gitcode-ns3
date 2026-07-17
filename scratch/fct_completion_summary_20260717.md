# 最近 FCT 汇总

单位均为 `us`。标准版取 `case01_标准topo`；重编号后的 test09/test10 scale 版按等效流量倍率、test 和拓扑场景分别列出，不跨场景聚合。

scale 80 / 40 / 20 分别直接乘以 5.5，记为 scale 440 / 220 / 110。下方 FCT 保留原始跑数，未将 FCT 本身按 5.5 线性换算。

## 标准版（case01）

test01–04 已按刷新后的流量重跑；其中 test01 的 `traffic.csv` 仅保留 pod1 内节点 0–71 的通信，`traffic.original.csv` 保持全量。

| Test | 完成任务数 | 平均完成时间 | 最大完成时间 |
|---|---:|---:|---:|
| test01_tp_all_gather | 72 | 79.194680 | 79.209935 |
| test02_cp_all_to_all | 216 | 301.648622 | 310.993163 |
| test03_tp_reduce_scatter | 72 | 360.799144 | 360.814899 |
| test04_tp_reduce_scatter | 72 | 182.667296 | 182.683051 |
| test05_pp_send_recv | 64 | 362.013431 | 362.584371 |
| test06_epxetp_all_to_all | 504 | 1,659.177984 | 1,666.908336 |
| test07_etp_all_reduce | 72 | 2,155.327862 | 2,155.343618 |

## test09 / test10（按 scale 分开看）

不对 5 个拓扑场景再做平均；下列“平均完成时间”和“最大完成时间”均为该 test + case 的原始统计值。

### Scale 440

| Test | 场景 | 完成任务数 | 平均完成时间 | 最大完成时间 |
|---|---|---:|---:|---:|
| test09_dp_all_gather | case01 标准 topo | 6,840 | 5.067877 | 11.261579 |
| test09_dp_all_gather | case02 故障 1 | 6,840 | 5.035568 | 19.161712 |
| test09_dp_all_gather | case03 故障 2 | 6,840 | 5.072870 | 11.257813 |
| test09_dp_all_gather | case04 故障 3 | 6,840 | 5.049550 | 11.275743 |
| test09_dp_all_gather | case05 故障 4 | 6,840 | 5.193688 | 19.424555 |
| test10_dp_reduce_scatter | case01 标准 topo | 6,840 | 5.068969 | 11.307382 |
| test10_dp_reduce_scatter | case02 故障 1 | 6,840 | 5.017088 | 31.500992 |
| test10_dp_reduce_scatter | case03 故障 2 | 6,840 | 5.087390 | 11.844029 |
| test10_dp_reduce_scatter | case04 故障 3 | 6,840 | 5.060559 | 11.789624 |
| test10_dp_reduce_scatter | case05 故障 4 | 6,840 | 5.159535 | 19.728786 |

### Scale 220

| Test | 场景 | 完成任务数 | 平均完成时间 | 最大完成时间 |
|---|---|---:|---:|---:|
| test09_dp_all_gather | case01 标准 topo | 6,840 | 8.726022 | 19.627444 |
| test09_dp_all_gather | case02 故障 1 | 6,840 | 8.840637 | 41.030192 |
| test09_dp_all_gather | case03 故障 2 | 6,840 | 8.770398 | 20.060209 |
| test09_dp_all_gather | case04 故障 3 | 6,840 | 8.703550 | 20.074974 |
| test09_dp_all_gather | case05 故障 4 | 6,840 | 9.167568 | 38.182561 |
| test10_dp_reduce_scatter | case01 标准 topo | 6,840 | 8.767128 | 19.669678 |
| test10_dp_reduce_scatter | case02 故障 1 | 6,840 | 8.815044 | 53.185172 |
| test10_dp_reduce_scatter | case03 故障 2 | 6,840 | 8.774550 | 20.483129 |
| test10_dp_reduce_scatter | case04 故障 3 | 6,840 | 8.736615 | 20.309718 |
| test10_dp_reduce_scatter | case05 故障 4 | 6,840 | 9.111641 | 39.322856 |

### Scale 110

| Test | 场景 | 完成任务数 | 平均完成时间 | 最大完成时间 |
|---|---|---:|---:|---:|
| test09_dp_all_gather | case01 标准 topo | 6,840 | 15.528142 | 36.526117 |
| test09_dp_all_gather | case02 故障 1 | 6,840 | 15.958315 | 72.697110 |
| test09_dp_all_gather | case03 故障 2 | 6,840 | 15.586772 | 39.904736 |
| test09_dp_all_gather | case04 故障 3 | 6,840 | 15.545083 | 39.599087 |
| test09_dp_all_gather | case05 故障 4 | 6,840 | 16.682726 | 76.073000 |
| test10_dp_reduce_scatter | case01 标准 topo | 6,840 | 15.488102 | 36.549376 |
| test10_dp_reduce_scatter | case02 故障 1 | 6,840 | 15.988740 | 88.874723 |
| test10_dp_reduce_scatter | case03 故障 2 | 6,840 | 15.450771 | 40.287999 |
| test10_dp_reduce_scatter | case04 故障 3 | 6,840 | 15.495495 | 40.192642 |
| test10_dp_reduce_scatter | case05 故障 4 | 6,840 | 16.532700 | 78.531465 |

机器可读的逐场景数据见同目录的 `fct_completion_summary_20260717.csv`。

## 数据来源

- `20260717-test01-04-standard-rerun-after-traffic-refresh/artifacts/standard_case01_parallel4/fct_summary.csv`
- `20260716-scale40-test08-09-then-standard-case01/artifacts/stage2_standard_case01/fct_summary.csv`
- `20260716-test08-test09-scale80-packet-spray-rr/artifacts/test08_09_scale80_all_cases_v2/fct_summary.csv`
- `20260716-scale40-test08-09-then-standard-case01/artifacts/stage1_test08_09_scale40/fct_summary.csv`
- `20260717-test08-test09-scale20-packet-spray-rr/artifacts/test08_09_scale20_all_cases/fct_summary.csv`
