# DiscoveryOS 系统理念

## 一句话定位

DiscoveryOS 是证据优先的 Algorithm Discovery Harness，不是某一种搜索算法，也不是把多个完整算法发现 runtime 套在一起的编排器。它用极小、稳定且不可越权的内核统一问题、候选、预算、评估、证据与科学裁决，再用可替换 Research Plugins 组合和演化研究过程。

## 五条长期原则

1. **权威内核最小化**：`ProblemContract`、Evaluator、`GateEngine`、Candidate/Evidence/Artifact Store、Budget、Research Graph 与 Runtime 构成稳定内核。只有必须跨策略共享且承担权威语义的能力才能进入内核。
2. **能力默认插件化**：proposal、lineage、parent policy、meta-strategy、routing、memory 与 profile adaptation 默认是插件或 profile policy，不因“常用”而进入核心。
3. **一个研究世界**：所有候选都属于 DiscoveryOS，所有正式 evidence、budget debit、graph edge 和 verdict 都写回统一权威。`operator_id`、`strategy_id` 与来源名称只是 provenance，不创建第二套 population、账本或胜负规则。
4. **复用优先于发明**：优先复用已准入的标准算法、外部机制与现有原语。新增自研机制必须先写明现有 Direct、Ada、EvoX、Shinka、ASHA/BOHB 类能力无法覆盖的具体缺口，并给出可证伪假设；“机制更多”本身不是进步。
5. **证据驱动 Harness 演化**：profile、routing、memory 或 Harness 自身只能沿预声明的证据阶梯演化。适应性不能修改 evaluator、GateEngine、winner rule、claim ceiling 或已冻结协议。

## Kernel、Plugin 与 Profile

```text
Frozen authority kernel
  contract / evaluator / GateEngine / budget
  candidate + evidence + artifact / graph / runtime
                         │
                  ResearchContext
                         │
          content-addressed ResearchProfile
                         │
     proposer / lineage / meta-strategy / router / memory
```

- **Kernel** 决定什么输入合法、资源如何结算、证据如何绑定以及谁能宣布科学 verdict。
- **Plugin** 提供可替换的 Search-plane 行为，只能通过声明过的 typed service 与统一 context 读写。
- **Profile** 是插件、配置、依赖、顺序和路由规则的内容寻址组合。进入正式比较的 profile 必须在运行前冻结；任何变化都产生新 revision 与 digest，不能原地覆盖。
- Search plane 可以快速变化，但不是第四个证据权威平面。AlgorithmGraph、HarnessGraph 与 EvidenceGraph 可以分别表达候选谱系、profile 谱系和证据绑定，最终仍落在同一 ledger 与 GateEngine 权威下。

## 外部系统的接入边界

外部算法发现引擎只有满足以下条件时，才可作为 Discovery Mode 的 Research Plugin：

- 输入输出归一为 DiscoveryOS `CandidateSpec`、Evidence、Budget 与 Graph 语义；
- 内部 population、memory、score、scheduler 与 evaluator 只是临时实现状态，不具有科学权威；
- source、version、license、code/config digest、依赖和资源 envelope 已绑定；
- lifecycle、scope、failure、dispose、provenance 与 replay 行为可审计；
- 不能读取 final blind capability，不能绕过统一 budget，也不能直接宣布 winner。

任一条件不成立时，该系统只能进入隔离的 Benchmark Mode。Pi 与 DeepSeek Harness 目前仅是 minimal-kernel、scope、lifecycle 和 profile 设计参考，不是运行时依赖，也不自动获得 plugin admission。

同进程 `ResearchContext` 隔离是组合与防误用边界，不是针对恶意插件的安全沙箱。未经独立进程、服务身份或 capability 隔离，不得声称 hostile-plugin isolation 或 production security。

## 研究准入阶梯

```text
P0 mechanics
  -> P1 单插件 causal/value
  -> P2 静态 profile composition value
  -> P3 adaptive profile value
  -> P4 memory-conditioned value
  -> P5 harness-evolution value
```

- 每一级只授权下一级的协议设计，不自动建立下一层价值。
- P0 必须覆盖 typed dependency、authority override fail-closed、lifecycle rollback、scope、provenance、budget failure 与 deterministic replay。
- P1 先证明插件实际改变 control flow，并把差异传到候选或 outcome；mechanics 或调用次数不等于 value。
- P2 必须用 matched resources 比较强单策略、朴素组合与静态 Harness，不能只和弱基线比较。
- P3 必须冻结可观察信号、选择空间、更新频率、rollback、outer anchor 与停止规则；适应过程不得接触受保护 outcome。
- P4 必须证明 memory 的来源、freshness、污染边界、作用域和增量价值；跨任务记忆不能把 SEALED/blind 信息回流搜索。
- P5 必须把 profile mutation、selection、rollback 与 claim ceiling 作为独立协议；“Harness 能改自己”不等于“改得更好”。
- Debugging、mechanics 与阶段 P0-P4 的形成默认只用 L0-L2；fresh/SEALED 资产只用于事前声明的 claim upgrade。

## 当前默认研发路线

当前默认 V1 profile 是 Direct bootstrap + Ada lineage + EvoX meta-strategy + deterministic router，并通过 `HarnessSearchRuntime` 接入统一搜索循环。下一科学问题是：在冻结任务与 matched resources 下，这个静态组合是否优于强单策略和朴素并行组合。

在该问题得到正向、可重放证据前：

- 不把 adaptive routing、cross-task memory 或 Harness evolution 作为默认实现主线；
- 不新增 fresh task，不升级 superiority/generalization claim；
- 不因官方外部 runtime 的名气而放弃统一权威边界；
- 不再把新增自研 Operator 数量当作主要进展指标。

当前 V1 执行实现与 claim ceiling 见 [`RESEARCH_HARNESS_V1.md`](RESEARCH_HARNESS_V1.md)；V0 历史 mechanics 见 [`RESEARCH_HARNESS_V0.md`](RESEARCH_HARNESS_V0.md)，项目当前状态见 [`CURRENT_STATE.md`](CURRENT_STATE.md)。

## 设计审查清单

新增能力前必须能回答：

1. 它为什么是 plugin/profile policy，而不是 kernel？若要进 kernel，哪项跨策略权威语义无法在现有边界表达？
2. 它读写哪些 typed services？是否可能形成私有 evaluator、budget、ledger、population 或 verdict？
3. candidate、evidence、resource usage、failure 和 handoff 如何进入统一 provenance 与 replay？
4. 现有已准入机制为什么不能覆盖该缺口？新假设如何被否证？
5. 当前处于 P0-P5 哪一级？使用哪一等级资产，最高允许什么 claim？
6. 失败时如何 fail closed、rollback 和 dispose，是否会污染 parent context 或 create-once evidence？
