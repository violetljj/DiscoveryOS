# Search-Value MVP-0: Vanilla vs DiscoveryOS

## 结论边界

本协议只回答：在相同模型、任务、起点和总资源 ceiling 下，DiscoveryOS unified loop 是否比一次直接 Vanilla 生成更能把预算转化为算法改进。

协议封存前状态必须是：

```text
SEALED_PRE_MODEL
model_calls_before_seal = 0
```

无论结果如何，本轮都不授权一般性算法优越、生产可用、安全或 final-blind 声明。实验中发现的代码缺陷记为 `INVALID_MECHANICS`，不得修改当前 revision 后继续混合结果。

## 冻结锚点

- autonomous mechanics anchor：`ec301a18f6543e8c07d62b49bc8cf784f90b137d`
- provider/model：封存时写入 manifest；预定 `codex-cli 0.148.0-alpha.9` / `gpt-5.4` / `medium`
- task 数量：8
- task 来源：独立确定性难度生成器，不复用 R1.0-B 或 BR-A consumed corpus
- 每个 task 必须有 baseline 双重 deterministic replay、exact oracle、至少 4 个 score-resolution step headroom，以及至少两类 trajectory

## 两个 arms

### Vanilla One-shot

- 从冻结 baseline 接收完整 task statement、mutable source 和 baseline development evidence。
- 允许一次 bounded direct generation。
- 不弱化 prompt，不提供免费 repair 或第二次科学调用。

### DiscoveryOS Unified Loop

```text
Ledger-backed State
→ deterministic Decision
→ Local / Structural / Replicate / Promote / Stop
→ real Evaluation
→ Evidence + Settlement
→ next State
```

- 单 active branch。
- 每个 algorithm family 最多 2 次 Local Patch。
- 全程最多 1 次 Structural Escape、6 个 settled steps。
- Controller、Local prompt、Structural prompt、resource floors 与 ASHA rungs 在 manifest 中冻结。

## 公平面与资源

每个 task/arm 独立冻结：

```text
same model and reasoning settings
same task statement
same repository commit
same mutable file
same evaluator and development data
same starting candidate
same 60,000 input+output token ceiling
same 1,200 second wall ceiling
same 300 CPU-second ceiling
unused budget cannot transfer
```

Local 与 Structural 使用各自动作所需的冻结 output schema，但共享同一模型、reasoning effort 和 CLI version。cache tokens 单独报告，不计入 input+output token ceiling。

## 指标

Primary：

```text
task win / tie / loss
final improvement
success rate
Anytime AUC
```

Anytime：

```text
best improvement @ 25% / 50% / 75% / 100% token budget
tokens and wall to first improvement
tokens and wall to best
```

Guardrails：

```text
invalid generation rate
mechanics failure rate
actual input+output tokens
actual wall and compute
final-blind receipts = 0
```

## 最低 PASS 门

必须同时满足：

```text
DiscoveryOS task wins > losses
median final improvement >= Vanilla
median Anytime AUC >= Vanilla
all resource protection checks pass
```

paired win rate `>= 60%` 单独标记为 strong positive signal，但不是最低 PASS 的替代条件。效率不能补偿 search value 缺失，任何资源超限都会使最低 PASS 失败。

## 禁止事项

在本轮正式结果结束前不新增 BOHB、qNEHVI、multi-branch bandit、learned controller、Meta-Strategy、Advisor、memory、rewrite operator、distributed worker 或 production blind service。不得在看到任一 arm 的模型输出后换题、放宽阈值或重跑当前 revision。
