# 架构与路线图

## 固定定位

DiscoveryOS 是一个证据优先的 Algorithm Discovery Harness：稳定内核只保留冻结权威、统一 Research/Candidate/Evidence Graph、预算与执行底座；AdaEvolve、EvoX、Shinka、Direct LLM、ASHA 等机制通过 Research Plugins 在同一状态上组合。原版系统保留为隔离 external challengers，用于检验统一 Harness 是否真的更强。

系统理念与 Kernel/Plugin/Profile 的长期准入约束以 [`SYSTEM_PHILOSOPHY.md`](SYSTEM_PHILOSOPHY.md) 为准。本文件描述结构与路线，不单独创造新的 evidence authority。

当前正式状态：

```text
DISCOVERYOS_KERNEL_ADMITTED
DISCOVERYOS_ACTION_CONTROLLER_MECHANICS_READY
DISCOVERYOS_AUTONOMOUS_SEARCH_LOOP_MECHANICS_READY
RESEARCH_HARNESS_V0_MECHANICS_READY
HYBRID_SEARCH_VALUE_NOT_EVALUATED
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
Frozen authority kernel
├── ProblemContract / Evaluator / GateEngine / Budget
├── Candidate + Evidence + Artifact Store
├── Research Graph / Harness Graph
└── Runtime / Replay / SplitVault
                         │
                  ResearchContext
                         │
                  Research Profile
├── proposal: Direct LLM
├── lineage: Ada-style refinement/routing
├── meta-strategy: EvoX-style structural revision
├── parent/novelty: Shinka-style primitives
├── budget/fidelity: ASHA/BOHB primitives
└── routing/memory: replaceable Search-plane plugins
```

这些机制读取和写入同一状态空间，由统一 action-acquisition layer 决定“下一单位资源最应花在哪里”：生成候选、增加 seed、提升 fidelity、转向 device、做 ablation、跨分支迁移还是 structural rewrite。

## Discovery Mode 与 Benchmark Mode

| Mode | 系统角色 | 状态与权威 |
|---|---|---|
| Discovery Mode | 把外部系统的有效思想重构为内部 planner/operator/budget/memory policy | 只使用 DiscoveryOS 的统一 graph、candidate、evidence、budget、memory 和 runtime |
| Benchmark Mode | 运行 Official Shinka/Ada/EvoX/MLEvolve/AlphaEvolve 等原版 external challengers | 独立运行时与状态隔离；通过冻结 adapter 接受同一任务、预算和 evaluator contract |

adapter 的存在不代表外部系统进入内部控制循环。其职责是隔离运行、contract translation、预算/收据归一化和公平对照；external challenger 不能写入 Discovery Mode 的 candidate DB、memory 或策略状态。

## 三个权威平面与 Harness 组合层

| 平面 | 当前权威 | 能做什么 | 不能做什么 |
|---|---|---|---|
| Evidence | frozen evaluator + split binding + receipts | 产生可重放观察 | 自己修改协议或 claim |
| Search | CMI diagnosis + operator + safe racing + Pareto | 形成瓶颈假设、选择诊断 probe 与下一笔资源 | 修改 evaluator、读取 final blind 或宣布科学胜利 |
| Harness | Research Profile + plugins + state router | 组合或替换 Search-plane 服务、记录 strategy handoff | 覆盖 authority service、自动提高 claim ceiling |
| Claim | GateEngine + contract ceiling | 限制可声明范围 | 把 scheduling utility 当作 verdict |

Evidence、Search、Claim 是三个权威平面；Harness 是 Search plane 内的组合层，不增加第四种裁决权。系统中的 scalar 只允许用于调度。协议违规、mechanics failure、hard-constraint failure、科学结果和 claim ceiling 分开记录。

## 当前代码边界

```text
src/discoveryos/
├── contracts/     # frozen schemas, codecs, protocol admission
├── graph/         # hypothesis/component/strategy/claim nodes
├── evaluation/    # evaluator registry, hard gates, Pareto, replay
├── harness/       # typed context, plugin lifecycle, profiles, strategy composition
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

1. **Research Harness V0**：已实现 typed/scoped context、插件生命周期、静态 Profile、Direct/Ada/EvoX 策略 provenance、state routing 与 cross-seeding graph mechanics。
2. **Static composition development gate**：冻结 Direct/Ada、EvoX、naive parallel、DOS Harness 四臂 matched-resource protocol；先用合格的 DEV/consumed bank 资产做 mechanics 和效用校准，不用 fresh task debugging。
3. **Harness adaptation gate**：只有静态组合相对强基线产生正向证据后，才冻结 profile mutation space、反馈、选择、rollback 与资源边界，比较 Static vs Adaptive。
4. **Memory-conditioned gate**：只有 adaptive value 成立后，才比较 Adaptive Reset vs Adaptive Warm，并保持 task-family/freshness 层级诚实。
5. **Harness evolution**：最后才允许搜索 Profile/HarnessGraph 本身；frozen outer authority、feedback-fidelity bound 与 backbone capability bound 不得绕过。

每阶段都必须用独立 benchmark 证明增量价值；mechanics smoke、单 seed 或 development improvement 都不允许升级成算法优越性、安全性或产品结论。
