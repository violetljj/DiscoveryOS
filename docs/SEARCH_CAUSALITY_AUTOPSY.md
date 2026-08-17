# SI-2 Search Causality Autopsy

## Verdict

```text
SI2_SEARCH_CAUSALITY_AUTOPSY_COMPLETE
CONSUMED_TASK_DIAGNOSTIC_ONLY_NO_SUPERIORITY_CLAIM
DO_NOT_OPEN_SI3_FRESH_BUDGET
```

本阶段只读取 SI-2 已消费的 9-task discovery cohort，没有模型调用、evaluator 调用或 fresh-task 消耗，也没有写回 SI-2 create-once root。最终诊断收据写入独立、忽略的 `runs/si2-search-causality-autopsy-r3`，并绑定分析实现、原 manifest、discovery report、27 个内部 arm task records 和 27 个 ledger 的 SHA-256。

最终 autopsy record SHA-256 为 `558236d6a80add65177e9f53f6d1ef1b8ae3c677c53eb0e9c1e982102a60914f`；81 个非 baseline candidate records 中有 70 个成功 materialize，11 个保留为原始 patch-stack mechanics failure。

这次 autopsy 支持的最强结论不是“三个 arm 生成了相同候选”。实际可重建的候选中，CURRENT/CORE/Vanilla 在 9 个任务上均没有 exact-source 或 coarse Python-AST structural fingerprint 重合；但三臂在 9/9 task 的 final improvement 仍完全相同。更准确的信号是：

> 搜索轨迹在源码和粗结构层面确实发生分化，但这些分化没有转化为可分辨的最终搜索价值。

这排除了“所有机制纯粹没有运行”这一过强解释，但没有证明分化到达了不同 algorithmic basin。当前收据没有预冻结的 algorithmic-root classifier、跨臂 behavioral trace 或统一 basin label，因此不能把 syntactic/AST divergence 升级成 scientific diversity。

## Observable intervention

CURRENT 的 9 个 task 中：

| Observation | Count |
|---|---:|
| Parent policy invoked | 27 |
| Multi-parent opportunity | 18 |
| Non-incumbent parent selected | 6 |
| Novelty check | 24 |
| Novelty rejection | 2 |
| Novelty resample attempt | 0 |

这些数字证明 parent 与 novelty 曾直接改变控制流：有 6 次 parent 选择偏离 incumbent，2 次 proposal 被 novelty 阻止继续 evaluation。它们不证明下游 causal value，因为没有冻结的 paired counterfactual generation 可以回答“若采用默认决策，下一候选和最终结果会怎样”。

评价轨迹也并非普遍相同：CURRENT 对 CORE 仅 1/9 task 完全相同，CURRENT 对 Vanilla 为 3/9，CORE 对 Vanilla 为 2/9。结合 9/9 final tie，更像是不同路径收敛到等价 outcome ceiling，而不是逐步轨迹完全复制。

11 个 candidate record 因其原始 patch stack 无法 materialize 而没有源码/AST signature；这是 SI-2 已记录 mechanics failure 的诊断表现，不做 repair，也不把缺失 candidate 当作相同或不同算法。

## What remains unidentifiable

- `algorithmic root`：没有在生成前冻结分类器。
- `behavioral signature`：没有保存统一输入上的 per-candidate output trace。
- `cross-arm basin escape`：CURRENT/CORE 的 local patch 继承 arm 内 baseline label，Vanilla 使用 arm-specific generic label，二者不可直接比较。
- 完整 `Mechanism Intervention Rate` 的因果版本：可观察 control-flow change，但没有 paired no-intervention counterfactual。
- memory injection effect：没有专用 invocation/intervention receipt。

因此本阶段不能声称“强模型内部能力压倒了外部机制”已被因果识别；它仍是与观测一致、但尚未排除替代解释的架构假设。

## Admission gate before the next fresh trial

1. 新机制必须保存 intervention receipt：policy invocation、默认动作、实际动作、即时控制流差异和资源成本。
2. 在候选生成前冻结跨臂 algorithmic-root classifier 与 behavioral-signature probe。
3. 先在 mechanics-only sandbox 证明干预改变 proposal 或 basin，并产生 coverage、重复避免或成本收益；不能只证明 policy 被调用。
4. 下一正式设计应把 `STRONG_AGENT_DIRECT` 作为默认一级 operator；只有预注册的 stagnation、uncertainty、basin collapse 或 multi-objective conflict 触发更重搜索。
5. fresh SI-3 只有在上述 admission 通过后才可封存；SI-2 的 9+3 tasks 不用于阈值、prompt、parent、novelty 或 escalation tuning。

开发原则冻结为：

> Stop adding mechanisms. Start proving interventions.
