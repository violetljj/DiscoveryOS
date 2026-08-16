# Residual-headroom Search-policy Admission

## 结论先行

R1.0-SP-A 把 Local Patch 这一局部研究对象从“能否可靠运行”升级为“同一个模型在相同总预算下，不同内部 search mechanism 能否把预算转化为更多有效 improvement”。协议代码已经冻结 task-admission、四臂公平面、指标定义和 search-value gate，但尚未冻结任何真实 task suite，也没有调用候选模型。因此当前 claim ceiling 只有：

```text
SEARCH_POLICY_PROTOCOL_ONLY
```

它只是统一搜索内核里的局部 mechanism admission，不是完整的 DiscoveryOS search-kernel admission。它不授权任何 operator 进入 DiscoveryOS 搜索内核，也不授权 final-blind、产品、安全或一般性 superiority 声明。

## 与总体架构的关系

DiscoveryOS 不把 AdaEvolve、ShinkaEvolve、EvoX、MLEvolve 等完整系统作为本协议的 arms。Discovery Mode 只使用它们被拆解、重构后的机制原语，并让这些原语共享统一 Research Graph、Evidence Model、Candidate Store、Budget/Fidelity Controller、Memory 和 Async Runtime。官方原版系统只在 Benchmark Mode 作为隔离 external challengers。

因此这里的 `lineage_preserving`、`structural_escape` 等名称表示统一状态空间内的 controller/mechanism 变体，不是启动另一套 population、candidate database、memory、budget controller 或 evaluator 语义。即使某一变体通过本协议，也不能推出整个统一搜索内核已经通过 admission。

## 为什么另开协议

BR-A 已经消除了 patch transport、parser 和 replay 可靠性混杂：One-shot 与 Iterative 都是 mechanics `8/8`、tests `8/8`、invalid `0%`。两者最终 improvement 完全相同，paired 为 `0 win / 8 tie / 0 loss`，说明冻结任务没有 residual headroom 可供 Iterative 展示额外 search value。

同一结果下，Iterative output tokens 为 `6291`，One-shot 为 `5300`，前者高约 `18.7%`。这只能作为 BR-A 分布内的效率观察，不能外推到困难任务；它说明下一协议必须同时报告 search value 和资源转换效率，而不是把“可靠”当作“有搜索价值”。

## Task admission 必须先于任何候选模型调用

每个任务都必须由 `ResidualHeadroomEvidence` 提供独立、内容寻址的证据，并同时满足：

1. baseline 可执行，至少两次 deterministic replay 一致；
2. admission 前候选模型调用数严格为 `0`；
3. headroom 来源只能是 exact oracle、近似上界、早于本协议的历史 baseline，或独立难度生成器；
4. 证据来源独立于所有被比较 policy；
5. baseline 到 reference 至少有 4 个 score-resolution step；
6. 至少有 2 个可验证的 improvement magnitude；
7. 至少有 2 类有意义的 edit/operator trajectory；
8. evaluator、initial state、baseline receipt、task-selection provenance 与 basin labeler 均有冻结 digest。

One-shot probe、任一 challenger probe、模型生成后的换题、阈值放宽和 task replacement 都是 fail-closed protocol violation。先跑 One-shot 再筛难题不产生可接受的 search-policy evidence。

## 公平比较面

在这个局部 mechanism 实验中冻结四臂：

- `one_shot`
- `iterative_local`
- `lineage_preserving`
- `structural_escape`

所有臂必须在 DiscoveryOS 的统一 Candidate/Evidence 状态空间内运行，并共享同一个 provider/model/version/settings、同一个每 task 初始状态、同一个 evaluator、同一个 replicate schedule，以及相同的 input-plus-output token ceiling 和 wall-time ceiling。cache tokens 单独报告；repair 或 controller 调用不获得免费模型预算。未使用预算不能跨 task 或 replicate 转移。

每个 policy 的 controller 与 prompt template 都单独冻结 digest。这样改变 search policy 不会暗中改变模型、evaluator、任务或总预算。

## 指标的精确定义

| Metric | 定义 | 角色 |
|---|---|---|
| best improvement | 相对冻结 baseline 的最佳 feasible、方向归一化 score delta | primary |
| AUC over token budget | best-so-far improvement 对累计 input+output tokens 的面积，再除以 token ceiling | co-primary trajectory metric |
| success | 是否达到至少 1 个冻结 score-resolution step | task-level |
| valid candidate rate | mechanically valid / materialized candidates | reliability guardrail |
| basin-jump rate | 跨冻结 basin label 的 improving valid transitions / 全部 improving valid transitions | structural diagnostic |
| tokens-to-improvement | 首次达到 1 个 resolution step 时的累计 input+output tokens；未达到则 null | efficiency |
| wall-time-to-improvement | 首次达到 1 个 resolution step 时的累计 wall seconds；未达到则 null | efficiency |

basin labeler 必须在候选模型调用前冻结。它是结构诊断，不是事后为某条 trajectory 定义的标签。

## Search-value gate

每个 challenger 分别与 `one_shot` 做 task-paired 比较，不能从三条 challenger 中事后挑最好的一条再宣称整个 operator family 胜出。单个 challenger 的 admission 至少需要：

- best-improvement paired win rate `>= 50%`；
- best-improvement paired loss rate `<= 25%`；
- median best-improvement delta `>= 1` 个 score-resolution step；
- median AUC delta `> 0`；
- valid-candidate-rate 相对 One-shot 的退化不超过 `10pp`；
- 无预算超限、accepted evidence 全 replay、final-blind receipts 为 `0`。

tokens-to-improvement、wall-time-to-improvement 或更低生成开销不能补偿 search-value gate 失败。即使某一 policy 通过，claim 也只限冻结 task 分布与冻结模型/预算配置，不产生困难任务、一般 operator 或产品 superiority 声明。

## 两阶段封存

1. 当前代码/文档先冻结协议 schema、admission logic、指标和 gate；不创建 task-level 科学结果。
2. 收集独立 headroom evidence 后，调用 `seal_search_policy_protocol(...)` 生成 create-once manifest。只有 manifest 状态为 `SEALED_PRE_MODEL` 且 digest 验证通过，未来 runner 才可开始任何候选模型调用。

如果没有足够任务通过 admission，正确结果是“不启动实验”，不是降低 headroom 或 resolution 门槛。
