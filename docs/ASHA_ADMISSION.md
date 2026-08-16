# R1.0-A Multi-Fidelity Search Admission

## 冻结结论

`deterministic_asha_admission_v1` 在 12 个独立 benchmark seed 上获得：

- ASHA 对 Random：`8 胜 / 4 平 / 0 负`；
- paired win rate：`66.7%`，冻结门槛为至少 `8/12`；
- median best-found quality delta：`+0.06`；
- 每个 seed、每个 arm 的实际 CPU 消耗均为 `54`；
- promotion、mechanical retry、evidence output 与 resource reconciliation 全部可 replay；
- 所有注入的 evaluator exception 均为 `NOT_EVALUABLE`，未进入算法质量排名；
- final-blind receipt：`0`。

因此 verdict 是：

```text
ASHA_ADMITTED_SYNTHETIC_ONLY
```

这只证明当前 ASHA mechanics 能在这个预先冻结、低高保真部分相关且包含反转的 synthetic domain 中产生 search-value；不能外推为 BlindAssist、真实代码搜索或一般算法发现能力。

## 冻结协议

```text
candidate pool: 18
eta: 3
rung-low:    G1, CPU 1  × 18
rung-medium: G2, CPU 3  × 6
rung-high:   G3, CPU 9  × 2
ASHA total actual CPU: 54

Random: G3, CPU 9 × 6
Random total actual CPU: 54
```

候选曲线包含一个低预算非头名、G2 反超并在 G3 最优的 late-rung champion，以及一个 G1 头名但高预算退化的 decoy。硬检查要求最终 high-rung leader 不能只是 G1 leader，防止把单次 proxy 排名伪装成 multi-rung search。

PASS 条件在正式 run 前冻结为：

- paired wins 至少 `ceil(12 × 0.60) = 8`；
- median paired delta 大于 `0`；
- 两臂实际 CPU 均等于 `54`；
- mechanics/replay 全通过；
- final blind 为 `0`。

## 诚实限制

ASHA 的每 seed experiment-wall 累计中位数约 `23.49s`，Random 约 `2.07s`。两臂使用同一个 `120s` wall budget ceiling，且 ASHA 赢得 best quality，但本结果不支持“ASHA wall-time 更省”的结论。该差距主要暴露了多 experiment 的 ledger/receipt/queue 开销，进入真实 benchmark 前应继续报告 makespan 与 experiment-wall，而不能只看 CPU reservation。

本 benchmark 也没有使用 GPU、LLM token、真实代码 patch 或 BlindAssist 数据。因此 R1.0-A PASS 只授权进入 LLM Local Patch admission，不授权 BOHB、Meta-Strategy 或产品/科学 superiority claim。

## 重放命令

```powershell
$env:PYTHONPATH = "src"
python -m discoveryos asha-admission --workspace runs/asha-admission --seeds 12
```

正式本地 run 的 create-once report 位于：

```text
runs/asha-admission-r1a-admitted/admission-artifacts/records/asha-admission-report.json
```
