# 架构与路线图

## 固定定位

DiscoveryOS 是一个统一算法研究内核：吸收并重组 AdaEvolve、ShinkaEvolve、EvoX、MLEvolve、DeltaEvolve、PACEvolve、AgentNAS、BOHB/ASHA 等系统中的有效机制，使它们共享统一 Research Graph、Evidence Model、Candidate Store、Budget/Fidelity Controller、Memory 和异步执行底座；原版系统保留为隔离的 external challengers，用于检验统一内核是否真的更强。

当前正式状态：

```text
DISCOVERYOS_KERNEL_ADMITTED
DISCOVERYOS_ACTION_CONTROLLER_MECHANICS_READY
DISCOVERYOS_AUTONOMOUS_SEARCH_LOOP_MECHANICS_READY
CMI_R0_PROTOCOL_IMPLEMENTED
CMI_R0_SYNTHETIC_DIAGNOSTIC_SENSITIVITY_PASSED
DISCOVERYOS_SEARCH_VALUE_NOT_YET_ESTABLISHED
DISCOVERYOS_PRODUCTION_NOT_READY
```

明确不采用下面这种多系统编排：

```text
DiscoveryOS
├── AdaEvolve runtime
├── ShinkaEvolve runtime
├── EvoX runtime
└── meta-controller selects a runtime
```

这会产生多套 population、candidate DB、memory、budget controller 和 evaluator 语义，破坏统一证据边界。Discovery Mode 的正确形态是：

```text
Unified Research Graph / Evidence / Candidate Store
                         │
Unified Budget + Fidelity + Async Runtime + Memory
                         │
Failure Phenotype + Competing Hypotheses + Diagnostic Probes
                         │
Internal mechanism primitives
├── novelty / parent explore-exploit / diversity pressure
├── branch budget / stagnation-aware allocation / exploration reserve
├── strategy spec / meta-strategy mutation / strategy admission
├── cross-branch reference / progressive history / branch review
├── semantic-delta memory / crossover / rollback / context
├── constrained NAS operators
└── BOHB / ASHA / Hyperband scheduling mechanisms
```

这些机制读取和写入同一状态空间，由统一 action-acquisition layer 决定“下一单位资源最应花在哪里”：生成候选、增加 seed、提升 fidelity、转向 device、做 ablation、跨分支迁移还是 structural rewrite。

## Discovery Mode 与 Benchmark Mode

| Mode | 系统角色 | 状态与权威 |
|---|---|---|
| Discovery Mode | 把外部系统的有效思想重构为内部 planner/operator/budget/memory policy | 只使用 DiscoveryOS 的统一 graph、candidate、evidence、budget、memory 和 runtime |
| Benchmark Mode | 运行 Official Shinka/Ada/EvoX/MLEvolve/AlphaEvolve 等原版 external challengers | 独立运行时与状态隔离；通过冻结 adapter 接受同一任务、预算和 evaluator contract |

adapter 的存在不代表外部系统进入内部控制循环。其职责是隔离运行、contract translation、预算/收据归一化和公平对照；external challenger 不能写入 Discovery Mode 的 candidate DB、memory 或策略状态。

## 不可越权的三条平面

| 平面 | 当前权威 | 能做什么 | 不能做什么 |
|---|---|---|---|
| Evidence | frozen evaluator + split binding + receipts | 产生可重放观察 | 自己修改协议或 claim |
| Search | CMI diagnosis + operator + safe racing + Pareto | 形成瓶颈假设、选择诊断 probe 与下一笔资源 | 修改 evaluator、读取 final blind 或宣布科学胜利 |
| Claim | GateEngine + contract ceiling | 限制可声明范围 | 把 scheduling utility 当作 verdict |

系统中的 scalar 只允许用于调度。协议违规、mechanics failure、hard-constraint failure、科学结果和 claim ceiling 分开记录。

## 当前代码边界

```text
src/discoveryos/
├── contracts/     # frozen schemas, codecs, protocol admission
├── graph/         # hypothesis/component/strategy/claim nodes
├── evaluation/    # evaluator registry, hard gates, Pareto, replay
├── operators/     # deterministic Action Controller + Random, ASHA, Local Patch, Structural Rewrite
├── memory/        # semantic delta and progressive context
├── mechanism_intelligence.py # failure phenotype, competing hypotheses, diagnostic probes, fail-closed research state
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

1. **CMI-R0 最小纵向切片**：已实现 failure phenotype、竞争 bottleneck hypothesis、冻结 diagnostic probe、资源绑定结果与 fail-closed 状态机；synthetic null/positive controls 只验证诊断 mechanics。
2. **现实 probe protocol**：选择 never-consumed development episodes，在读取输出前冻结 phenotype、竞争 hypotheses、probe semantics、阈值、预算和 fail-closed terminal。先验证 evaluator control、perfect-implementation control 与 functional-basin assay，不生成 Operator。
3. **Mechanism Brief admission**：只有恰好一个瓶颈 hypothesis 被支持且竞争解释全部被反证，才允许冻结包含 preconditions、causal target、required context、observable fingerprint、interactions 与 failure modes 的 Mechanism Brief。
4. **Operator Admission Funnel**：新 Operator 依次证明 applicability、realized functional intervention、causal reachability、state-local null/positive controls 和独立 dev value；任一层失败即关闭当前版本。
5. **Fresh search-value trial**：只有独立 dev value gate 通过后，才申请 never-consumed tasks、matched resources 与新 create-once root。此前不扩展机制数量、远端计算或生产 blind isolation。
6. **后续组合与学习**：积累多个独立 admitted mechanisms 后，才实现 applicability learning、mechanism composition 与 credit assignment；Meta-Strategy/Advisor 仍需等待基础 search value 成立。

每阶段都必须用独立 benchmark 证明增量价值；mechanics smoke、单 seed 或 development improvement 都不允许升级成算法优越性、安全性或产品结论。
