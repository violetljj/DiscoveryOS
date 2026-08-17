# DiscoveryOS 当前状态

> 状态日期：2026-08-17。这里是进入项目后的状态入口；正式实验的冻结协议和完整结果仍以对应阶段文档与不可变收据为准。

## 结论先行

```text
DISCOVERYOS_KERNEL_ADMITTED
DISCOVERYOS_ACTION_CONTROLLER_MECHANICS_READY
DISCOVERYOS_AUTONOMOUS_SEARCH_LOOP_MECHANICS_READY
CONTROLLER_BUDGET_REACHABILITY_REPAIRED
SEARCH_VALUE_MVP0_FAIL
DISCOVERYOS_SEARCH_VALUE_NOT_YET_ESTABLISHED
DISCOVERYOS_PRODUCTION_NOT_READY
SI1_PARENT_EFFECTIVENESS_REPAIRED
SI1_NOVELTY_COST_REPAIRED
SI2_SEARCH_VALUE_NOT_ESTABLISHED
SI2_VANILLA_WINNER_CONFIRMED_ON_WITHHELD_COHORT
SI2_EXTERNAL_BASELINE_NOT_EVALUABLE
SI2_SEARCH_CAUSALITY_AUTOPSY_COMPLETE
CAUSAL_INTERVENTION_BENCH_MECHANICS_READY
CIB_SYNTHETIC_SENSITIVITY_ESTABLISHED
PARENT_CIB_DEVELOPMENT_TRACE_COMPLETE
PARENT_VALUE_TRANSMISSION_DETECTED_ON_SEMANTICS_PRESERVING_DEV_REPLAY
NO_REAL_MECHANISM_INTERVENTION_ADMITTED
NEXT_FRESH_SEARCH_TRIAL_NOT_ADMITTED
CIB_R1_REAL_DOWNSTREAM_COMPLETE
PARENT_INTERVENTION_VALUE_NOT_ESTABLISHED_UNDER_STRONG_STOCHASTIC_GENERATOR
REAL_PARENT_MECHANISM_NOT_ADMITTED
```

当前系统是可运行、可测试、可重放的研究内核，不是已经证明一般搜索优势的发现系统，也不是生产级 blind/security sandbox。

默认执行环境是当前本机。高资源任务应先探测实时 CPU、内存、GPU/显存、磁盘和负载，再以有界并行、缓存与断点续跑提高吞吐；远端或云端执行不是默认路径，需要单独授权或冻结协议要求。

## 已交付并有代码/测试支撑

- 冻结 `ProblemContract`、候选/实验/证据 identity、evaluator/data/artifact digest binding。
- SQLite WAL `EvidenceLedger`、create-once artifacts/receipts、Research Graph lineage。
- 多维资源 reservation、usage、reconciliation、拒绝与 overrun 的独立记录。
- G0/G1/G2 discovery、Pareto/winner freeze、独立 G7 certification 和 evaluator replay 的端到端垂直切片。
- `SplitVault` 对 discovery/fidelity/frozen candidate 的 fail-closed capability 检查。
- 可执行代码 bundle、临时 Git worktree runner、路径策略、超时进程树终止和 run receipts。
- ASHA mechanics admission；bounded Local Patch、一次 mechanical repair 和 generation provenance。
- Structural Rewrite mechanics、ledger-backed state projector、deterministic action controller、unified executor 和 anytime settlement。
- residual-headroom task admission 与 matched-resource Search-Value MVP 协议/runner。

## 已冻结的关键结果

### Kernel / ASHA

- Phase 0 + Phase 1 kernel 的 discovery -> winner freeze -> certification -> replay 垂直切片已验证。
- ASHA 的 synthetic matched-budget admission 只证明 multi-fidelity mechanics，未授权更广泛算法或产品结论。

### Local Patch

- BR-A fresh readmission 中 One-shot 与 Iterative 都达到 mechanics/reliability `8/8`，paired 为 `0 win / 8 tie / 0 loss`。
- 正式 verdict 保持 `LLM_LOCAL_PATCH_NOT_ADMITTED`：可靠性通过，但没有建立额外 search value。
- 原 6-task corpus 和 BR-A 8-task corpus 已 consumed，不得通过增加 repair、换目录或同分布重跑改写结论。

### Search-Value MVP-0

- autonomous mechanics loop 已接通，但正式 MVP-0 结论为 `SEARCH_VALUE_MVP0_FAIL`。
- 后续修复了 controller 在冻结预算下的 action reachability，并保持旧 manifest/report/receipts 不变。
- 该修复只能说明 mechanics/预算可达性已修正，不能回写或升级旧 MVP-0 科学结果。

## SI-1 / SI-1R development 结果

- SI-1 已将 Shinka-style parent selection 与 novelty rejection 原生接入统一 ledger/search loop，mechanics verdict 为 `SHINKA_PARENT_NOVELTY_MECHANICS_READY`；其正向 development signal 只来自避免重复 evaluation。
- SI-1R 对冻结 SI-1 records 的 autopsy 证明：首步存在真实 pool starvation，但主要 parent 缺陷是多候选时的权重塌缩，不是 archive visibility 或 controller opportunity 缺失；novelty 高成本来自 rejection 后无条件昂贵 resample。
- Parent 的单候选概率上限和完整 opportunity receipt 已在 deterministic fixture 与真实 consumed-task trace 中改变合法 parent 分布；novelty cheap-first cascade 与 affordability gate 将四次 avoided evaluation 的 resample generation overhead 降为零。
- 有界 verdict 为 `SI1_PARENT_EFFECTIVENESS_REPAIRED` 与 `SI1_NOVELTY_COST_REPAIRED`。真实 pilot 没有提高最终 median、没有新 stepping-stone，且 parent arms 未超过 CORE aggregate diversity；因此仍是 development mechanics，不是 search-value admission。
- SI-1R 已正式收口。其累计 `719,922` generation tokens 不再支持继续在 consumed pilot corpus 上调 parent、novelty 或 selection diagnostics；结果保持 `DISCOVERYOS_SEARCH_VALUE_NOT_YET_ESTABLISHED`。

## SI-2 正式结果

- create-once manifest `c71c6b553778cbbe60dd4c683d5973ed6fa43e1c94e58a7903dfd626de37816d` 在 commit `b6c9c55` 上以 0 pre-seal model calls、0 pre-winner blind access 封存 9 个 discovery tasks、3 个 confirmation tasks、四臂、`gpt-5.6-sol / medium`、预算和统计门。
- `CURRENT_DISCOVERYOS` 对 CORE 为 `0 win / 9 tie / 0 loss`，median final delta `0`、median token-AUC delta `-0.00058338`、exact sign `p=1.0`；对 Vanilla 同为 `0 / 9 / 0`，median final delta `0`、median token-AUC delta `-0.00068489`、`p=1.0`。Holm 两项均失败，正式 verdict 为 `SI2_SEARCH_VALUE_NOT_ESTABLISHED`。
- 三条内部 arm 的 median final improvement 均为 `0.21951735`。冻结 winner rule 先比较 final、再比较 AUC，因此 Vanilla 以 median AUC `0.17699025` 排第一，CURRENT 为 `0.17630536`，CORE 为 `0.17508045`；这不是 CURRENT 的 search-value 证据。
- Vanilla 在 winner freeze 后的 3/3 withheld tasks 均取得可分辨 improvement，median 为 `0.21749171`，资源门全部通过，verdict 为 `SI2_WINNER_CONFIRMED_ON_WITHHELD_COHORT`。Confirmation 只确认冻结 winner 的绝对改进能力，不构成 withheld 四臂 superiority 比较。
- 官方 ShinkaEvolve 在 9/9 discovery tasks 的运行时 model-availability 检查中触发 Windows `spawn EINVAL`，均在 generation 前 fail closed 为 `EXTERNAL_BASELINE_NOT_EVALUABLE`；因此 external competitiveness 没有建立，也不能把这些 arm 记为科学负结果。
- 原 discovery report 的 secondary arm token 汇总错误地只接受整数，而逐 task `ResourceUsage` 把整数 token 序列化为浮点数。原报告保持不可变；绑定其 SHA256 与全部 36 个 source-record hashes 的 correction `5ee6e699517ca2e66e993f1acbccbcc144f3ee98a91e83bd1a45ec084e1e0efe` 给出 CORE `555,104`、CURRENT `559,835`、Vanilla `553,395` tokens。该修正不重算 primary、winner 或 verdict。

## 明确尚未建立或尚未实现

- 一般性 DiscoveryOS search value、跨任务/模型稳定优势。
- BOHB/qNEHVI、正式 G3-G6 策略、multi-branch credit、完整 crossover/rollback、learned controller、Meta-Strategy Evolver 和 Advisor。
- 远端 GPU/device worker、分布式队列、生产级 heartbeat/checkpoint/cache。
- 可评估的 official external challenger 公平 benchmark；SI-2 的 Shinka adapter 已实现，但正式运行因 Windows Headless availability blocker 为 `NOT_EVALUABLE`。
- 独立服务/OS identity 的 hostile-worker blind isolation。
- 产品可用性、安全性、真实世界效果或生产 readiness。

## SI-2 Search Causality Autopsy

- 对 SI-2 consumed discovery traces 的零模型、零 evaluator 诊断已完成；它不产生 superiority claim，也未写回 SI-2 create-once root。
- 可重建候选在 exact-source 与 coarse Python-AST 结构层面跨臂没有重合，但三臂仍在 9/9 tasks 得到相同 final improvement；这支持“搜索路径分化没有转化为可分辨 outcome value”，不支持“候选或 algorithmic basin 完全相同”。
- CURRENT 的 parent policy 调用 27 次，其中 18 次存在多 parent、6 次选择非 incumbent；novelty 检查 24 次、拒绝 2 次、resample 0 次。它们是直接 control-flow intervention，不是下游 counterfactual causal proof。
- 当前 SI-2 instrumentation 不能识别 algorithmic root、跨臂 behavioral signature、统一 basin 或无干预反事实，因此下一阶段先补 causal admission，不开放 SI-3 fresh budget。完整边界见 [`SEARCH_CAUSALITY_AUTOPSY.md`](SEARCH_CAUSALITY_AUTOPSY.md)。

## Causal Intervention Bench V1

- 已实现 create-once 的 paired intervention harness，冻结 decision state、policy/default/actual action、behavioral probe、matched downstream budget、独立 stochastic draws 和分层 effect receipts。
- Null control 使用 state-local `A/A` 独立重复估计 stochastic envelope；positive control 只验证 bench sensitivity，不计入机制收益。Gate 分开识别 intervention 未发生、行为改变但 utility 等价、即时效果未传导和可复现的 intervention value。
- 首个 no-model synthetic fixture 冻结 3 个 states，运行 27 个 pairs；positive、behavior、immediate、persistence 和 benefit checks 均为 `3/3`，证明 bench 能检测预构造差异，状态为 `CAUSAL_INTERVENTION_BENCH_MECHANICS_READY`。
- Manifest digest 为 `36906c865a48022ddd61f6257e7698d0a1a71127cd7273a416405de26f4b40ac`，最终 report SHA-256 为 `17261f398218713c29212e6f4b16ef18f20951ab0a7d45455d79981fc38827f2`；模型调用、真实 evaluator 调用和 fresh-task 消耗均为零。
- Synthetic fixture 的 `INTERVENTION_VALUE_ADMITTED` 只验证 gate 可达，不 admit 现实 Parent、Novelty 或 Memory，也不建立 search value。SI-3 仍保持关闭；完整边界见 [`CAUSAL_INTERVENTION_BENCH.md`](CAUSAL_INTERVENTION_BENCH.md)。
- 实际 `ShinkaWeightedParentSelectionPolicy` 已接入三个 consumed MVP-0 dev states：3/3 receipts 可重放地选择 non-incumbent parent，18 个 paired receipts 检出 3/3 behavioral、immediate、persistence 和 benefit effects。Parent-dev manifest digest 为 `92558fb944b9062ce88b7f3fd2aa6e86968251cc9ded2365dfe120b55e517ec6`，report SHA-256 为 `50404450613130fba2b9823c2b3e50504dc4e8883506952fb3e3778a9394ad67`。
- Parent-dev 只建立 `PARENT_VALUE_TRANSMISSION_DETECTED_ON_SEMANTICS_PRESERVING_DEV_REPLAY`：states/sources/seeds 为 mechanics 构造，null 是 deterministic zero-variance，downstream 不生成真实 child。因此它证明实际 policy 的 causal path 可观测，不 admit 现实 Parent value，也不改变 SI-3 gate。

## CIB-R1 real downstream Parent trial

- 从 SI-2 actual non-incumbent receipts 冻结 2 个 calibration states 与 3 个 validation states；validation 横跨 balanced cut、weighted coverage 和 capacitated assignment，未读取 fresh 或 blind task。
- `gpt-5.6-sol / medium` 以相同 prompt contract、60,000-token branch ceiling 和独立 provider requests 生成三步 descendant chain。Calibration `16/16` branches evaluable 并冻结 behavioral margin `0.28635642` 与 utility margin `0.005`。
- Validation `42/42` branches evaluable，live positive sensitivity 达到冻结的 `2/3` state minimum；但 actual Parent intervention 在 `0/3` states 超出 null+margin，benefit/persistence 同为 `0/3`。
- 九个 intervention pairs 的 final descendant effect 为 `0 positive / 9 tie / 0 negative`，median final、validity-rate 与 replacement-rate delta 均为 `0`，exact-sign `p=1.0`。正式 verdict 为 `PARENT_INTERVENTION_VALUE_NOT_ESTABLISHED_UNDER_STRONG_STOCHASTIC_GENERATOR`。
- 总计 58 model calls、`1,298,797` input+output tokens、29 paired receipts、0 fresh tasks；manifest digest `f14902c185470fb9fcb71bf28a7eb4a3c9562d4109db742d9147f47112fc0b4e`，report SHA-256 `7fbd3db909dc5d8da11bca9d12f164e0f0cb520333cf9aab012945d7afe74f72`。

## 当前下一道门

1. SI-2 已 consumed，禁止在其 9+3 tasks 上调 parent、novelty、prompt、预算或阈值，也不得用同分布重跑改写 `SI2_SEARCH_VALUE_NOT_ESTABLISHED`。
2. 如仍需 external competitiveness，先在 mechanics-only 环境修复 Windows Headless `spawn EINVAL`，再用新协议版本、新 fresh tasks 和新 create-once root；不得补跑 SI-2 外部空位。
3. 任何下一代搜索设计必须解释为何三条内部系统在 9/9 tasks 上 final 完全持平，并用新鲜 cohort 证伪；不能把更复杂机制或 confirmation 的 Vanilla 绝对改进误写为 DiscoveryOS superiority。
4. 新机制进入 fresh trial 前必须先接入 CIB：用 outcome-blind calibration states 冻结 probe/margin，再在未参与校准的 representative dev states 上用真实 stochastic downstream 证明超出 null、可持续且跨 state 复现的 intervention value。Synthetic sensitivity 和 semantics-preserving Parent replay 都不能替代该 admission。
5. 在新的 search-value admission 成立前，不扩展远端计算、生产 blind isolation 或更多机制数量。
6. CIB-R1 已完成：58/58 branches evaluable、资源门通过且 fresh task 消耗为零，但 Parent 在 3/3 validation states 未产生超出 stochastic null 的 downstream behavioral manipulation，9 个 intervention pairs 的 final descendant delta 全为 tie。Parent 不获得现实机制 admission，SI-3 继续关闭；不得在这些 consumed states 上换 margin、prompt、operator 或增加 replicate 翻案。

## 状态更新规则

- 只有通过对应协议门并存在可重放证据，才能把能力从“在研”移动到“已交付”。
- 新结果必须保留 negative、invalid 和 not-evaluable 的区别，并链接具体阶段文档。
- 工作树或分支的临时状态不能成为科学真相；合并/提交后更新本页的在研描述。
- 如本页与 create-once manifest、receipt 或阶段结果冲突，以不可变证据为准并修正本页。

## 相关文档

- 项目和术语：[`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md)
- 长期设计决策：[`DECISIONS.md`](DECISIONS.md)
- 架构路线：[`ARCHITECTURE.md`](ARCHITECTURE.md)
- Local Patch：[`LLM_LOCAL_PATCH_ADMISSION.md`](LLM_LOCAL_PATCH_ADMISSION.md)、[`LLM_LOCAL_PATCH_RELIABILITY.md`](LLM_LOCAL_PATCH_RELIABILITY.md)
- MVP-0：[`SEARCH_VALUE_MVP0.md`](SEARCH_VALUE_MVP0.md)、[`MVP0_BUDGET_REACHABILITY_REPAIR.md`](MVP0_BUDGET_REACHABILITY_REPAIR.md)
- SI-1：[`STRATEGY_INTEGRATION_SI1.md`](STRATEGY_INTEGRATION_SI1.md)、[`SHINKA_MECHANISM_MAPPING.md`](SHINKA_MECHANISM_MAPPING.md)
- SI-1R：[`SI1_PARENT_NOVELTY_REPAIR.md`](SI1_PARENT_NOVELTY_REPAIR.md)
- SI-2：[`SI2_FRESH_SEARCH_VALUE_TRIAL.md`](SI2_FRESH_SEARCH_VALUE_TRIAL.md)
- SI-2 causal autopsy：[`SEARCH_CAUSALITY_AUTOPSY.md`](SEARCH_CAUSALITY_AUTOPSY.md)
- Causal Intervention Bench：[`CAUSAL_INTERVENTION_BENCH.md`](CAUSAL_INTERVENTION_BENCH.md)
- CIB-R1 real downstream Parent trial：[`CIB_R1_REAL_DOWNSTREAM_CAUSAL_TRIAL.md`](CIB_R1_REAL_DOWNSTREAM_CAUSAL_TRIAL.md)
