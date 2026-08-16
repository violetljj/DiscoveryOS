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

## 明确尚未建立或尚未实现

- 一般性 DiscoveryOS search value、跨任务/模型稳定优势。
- BOHB/qNEHVI、正式 G3-G6 策略、multi-branch credit、完整 crossover/rollback、learned controller、Meta-Strategy Evolver 和 Advisor。
- 远端 GPU/device worker、分布式队列、生产级 heartbeat/checkpoint/cache。
- 外部 official challenger 的完整隔离 adapter 与公平 benchmark。
- 独立服务/OS identity 的 hostile-worker blind isolation。
- 产品可用性、安全性、真实世界效果或生产 readiness。

## 当前下一道门

1. SI-1R 已满足 repair stop rule；停止继续调参或增加 strategy。
2. 如需继续，只能先讨论并预注册新的、未污染的 SI-1 fresh admission；不得从 SI-1R 直接晋升。
3. 若设计新 admission，必须在任何候选模型调用前冻结 task provenance、matched-resource surface、replicates、gate 和 claim ceiling。
4. 只有 search value 在冻结分布上成立后，才扩大到远端执行、更多策略或生产 blind isolation。

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
