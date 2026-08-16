# 架构与路线图

## 不可越权的三条平面

| 平面 | 当前权威 | 能做什么 | 不能做什么 |
|---|---|---|---|
| Evidence | frozen evaluator + split binding + receipts | 产生可重放观察 | 自己修改协议或 claim |
| Search | operator + safe racing + Pareto | 选择下一笔资源 | 读取 final blind 或宣布科学胜利 |
| Claim | GateEngine + contract ceiling | 限制可声明范围 | 把 scheduling utility 当作 verdict |

系统中的 scalar 只允许用于调度。协议违规、mechanics failure、hard-constraint failure、科学结果和 claim ceiling 分开记录。

## 当前代码边界

```text
src/discoveryos/
├── contracts/     # frozen schemas, codecs, protocol admission
├── graph/         # hypothesis/component/strategy/claim nodes
├── evaluation/    # evaluator registry, hard gates, Pareto, replay
├── operators/     # bounded random-search operator; future portfolio hook
├── memory/        # semantic delta and progressive context
├── runtime/       # artifacts, SQLite ledger, split vault, async scheduler
└── domains/       # executable domain packs
```

顶层模块通过 `CandidateSpec`、`ExperimentSpec` 和 `EvidenceRecord` 交互。evaluator digest 与 data digest 都被冻结进证据；同一个 experiment 只能拥有一条 create-once receipt。

`ExperimentSpec` 的 experiment identity 还绑定 `trial_id`、`replicate_id`、`rung_id`、`resource_fingerprint`、`attempt_id`、`parent_trial_id` 和 `promotion_reason`。trial 可跨 rung 保持稳定，但不同资源档位、独立 seed 和 retry 不会再被 idempotency 合并。

预算采用两阶段账本：

```text
ResourceReservation
→ worker execution
→ ResourceUsage
→ ResourceReconciliation
→ evidence receipt
```

调度准入按“已结算实际消耗 + 尚未结算预留”计算。reservation 拒绝或实际超出预留/总预算时产生独立 `BUDGET_EXHAUSTED` 系统失败，不进入科学负结果。

真实代码候选采用 `ExecutableCandidateBundle`。内容寻址 artifact 同时冻结 manifest 与 `patch.diff`；runner 从 base commit 创建临时 worktree，校验修改路径与环境锁，依次运行 build/test/evaluation，并固化命令日志和 run receipt。子进程超时会终止整棵进程树；这一层不声称能够隔离同一 OS 身份下的恶意代码。

## 下一批实现顺序

1. **Local Patch operator/search policy**：R1.0-BR-A 已完成；fresh reliability gate 通过，但 One-shot 与 Iterative 在 8 个 task 上全部打平，原 search-value gate 失败，verdict 保持 `LLM_LOCAL_PATCH_NOT_ADMITTED`。不再继续修 parser 或在 consumed corpus 上 replay；任何后续 operator/search-policy 研究都必须使用新的预冻结 admission，不能提前进入 R1.0-C。
2. **R0.2 生产隔离**：final-blind 独立服务身份、一次性认证票据、shadow 聚合反馈与查询预算。
3. **R1.1 搜索组合扩展**：仅在 BlindAssist fresh target 四臂赛马证明组合价值后考虑 BOHB、Structural Rewrite 和更广 operator schema。
4. **R1.2 图搜索**：Hypothesis/Component effect ledger、分支预算、cross-branch transfer、自动消融、failure signature library。
5. **R2 策略层**：contextual bandit、停滞检测、受限 Meta-Strategy admission。
6. **R3 领域和计算**：BlindAssist domain pack、远端 GPU/device worker、checkpoint/cache、部署 parity。
7. **R4 学习型 Advisor**：只使用通过复验和消融晋升的轨迹训练 promotion/operator policy。

每阶段都必须用独立 benchmark 证明增量价值；mechanics smoke、单 seed 或 development improvement 都不允许升级成算法优越性、安全性或产品结论。
