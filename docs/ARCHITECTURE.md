# 架构与路线图

## 固定定位

DiscoveryOS 是一个统一算法研究内核：吸收并重组 AdaEvolve、ShinkaEvolve、EvoX、MLEvolve、DeltaEvolve、PACEvolve、AgentNAS、BOHB/ASHA 等系统中的有效机制，使它们共享统一 Research Graph、Evidence Model、Candidate Store、Budget/Fidelity Controller、Memory 和异步执行底座；原版系统保留为隔离的 external challengers，用于检验统一内核是否真的更强。

当前正式状态：

```text
DISCOVERYOS_KERNEL_ADMITTED
DISCOVERYOS_ACTION_CONTROLLER_MECHANICS_READY
DISCOVERYOS_AUTONOMOUS_SEARCH_LOOP_MECHANICS_READY
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
| Search | operator + safe racing + Pareto | 选择下一笔资源 | 读取 final blind 或宣布科学胜利 |
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

1. **统一接口与 BR-A 封口**：candidate/evidence/artifact/budget/fidelity 接口已形成垂直切片；BR-A 保持 `LLM_LOCAL_PATCH_NOT_ADMITTED`，不再修 parser 或在 consumed corpus 上寻求翻案。
2. **Search-Value MVP**：单 active branch 的真实闭环已经由 `LedgerBackedSearchStateProjector -> DeterministicActionController -> UnifiedActionExecutor -> SearchLoopRunner` 接通 Local Patch、Structural Escape、Replicate、ASHA Promote 与 Stop，并为每笔结算写入 create-once anytime trace。State 只投影 ledger 中的 candidate/evidence/action settlement；`scheduling_utility` 只分配搜索资源，不覆盖 Gate/Pareto 的科学裁决。下一步停止扩展 controller，直接运行 matched-resource Search-Value MVP。R1.0-SP-A 只作为 pre-model task-selection guard，不是独立产品阶段。
3. **严格 matched-resource benchmark**：立即在多个预冻结 headroom task family 上，以 matched model/token/wall/compute/evaluator 比较 Vanilla one-shot 与 DiscoveryOS unified loop；先回答 search value，不添加 agent framework、LLM planner 或 distributed queue。Anytime、效率和 search-behavior 指标与最终 task outcome 一起报告。
4. **远端并行计算**：只有首轮 Search-Value MVP 暴露出真实吞吐瓶颈后，才实现多进程与远端 CPU/GPU/device worker、heartbeat、retry、checkpoint/cache 和真实 resource measurement，避免先为未经证明的 action model 建集群。
5. **Search value 成立后补生产隔离**：只有稳定优势成立后，才把 final-blind 独立服务身份、一次性票据、shadow 查询预算和 hostile-worker isolation 提升为最高优先级。
6. **后续内部机制**：逐项 admission novelty/parent selection、branch credit、crossover/rollback、BOHB/qNEHVI 和更强 multi-fidelity；不把 mechanics smoke、单 seed 或 development improvement 当算法证据。
7. **Meta-Strategy / Advisor**：只在基础 search value 成立后实现受限 Meta-Strategy evolution，并只用通过复验和消融晋升的轨迹训练 Advisor。

每阶段都必须用独立 benchmark 证明增量价值；mechanics smoke、单 seed 或 development improvement 都不允许升级成算法优越性、安全性或产品结论。
