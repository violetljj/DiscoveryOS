# DiscoveryOS 决策记录

本文件记录会影响后续实现的长期决策。新决策追加，不删除历史；如需替代旧决策，新增条目并写明 `Supersedes`、迁移范围和证据理由。

## D-001：统一内核，不做多系统 runtime 编排

- **状态**：Accepted
- **决定**：Discovery Mode 只保留一套 Research Graph、Candidate/Evidence Store、Budget/Fidelity Controller、Memory、Runtime 和 evaluator authority。外部发现系统的有效思想必须重构为内部机制；官方 runtime 仅作为隔离 Benchmark Mode challenger。
- **原因**：并列多套 population、memory、budget 和 verdict 语义会破坏可比性、谱系与证据权威。
- **后果**：新增 adapter 不能写入内部 candidate DB 或策略状态；新增 mechanism 必须使用统一合同、账本、预算和收据。

## D-002：冻结合同与 GateEngine 拥有科学裁决权

- **状态**：Accepted
- **决定**：`ProblemContract` 冻结评估语义，`GateEngine` 对 evidence validity、hard constraints、scientific feasibility 和 claim ceiling 作最终裁决。
- **原因**：搜索策略若同时定义评分和宣布胜负，会产生自我认证与门槛漂移。
- **后果**：controller score、Pareto scalarization、novelty、parent weight、ASHA ranking 和 scheduling utility 都只能分配资源；任何旁路 verdict 都是架构缺陷。

## D-003：final blind 与 winner selection 单向隔离

- **状态**：Accepted
- **决定**：Discovery 不访问 G7。winner 在 development evidence 上按冻结规则 create-once 确定后，Certification 才能获得 final-blind capability；G7 结果不得改变 winner。
- **原因**：防止盲测变成可反复查询的调参集。
- **后果**：发现命令的 blind receipt count 必须为零；认证必须验证 candidate freeze；生产部署还需把 vault 提升为独立服务或身份。

## D-004：收据和实验根 create-once，重放重新计算

- **状态**：Accepted
- **决定**：artifact、receipt、冻结 manifest 和正式实验根以内容摘要和 identity 绑定，创建后不可原地改写。Replay 在适用时重执行冻结 evaluator，而不是只读取已存 verdict。
- **原因**：可编辑的“证据”和只做结构校验的 replay 无法发现 evaluator/data/contract 漂移。
- **后果**：协议或实现发生实质变化时创建新版本/新实验根；旧的 consumed corpus 和负结果继续保留，不通过换 workspace 翻案。

## D-005：预算是两阶段、可重放的科学边界

- **状态**：Accepted
- **决定**：资源采用 reservation -> execution -> actual usage -> reconciliation -> evidence 的两阶段账本；调度准入同时考虑已结算消耗和未结算预留。
- **原因**：只记录最终消耗会在并发和失败时超卖预算，也无法公平比较 search policy。
- **后果**：超预算或 reservation rejection 形成独立系统失败，不能计为算法科学负例；LLM input/output/cache、wall、CPU、GPU/device 分开记录。

## D-006：先证明 search value，再扩展复杂基础设施

- **状态**：Accepted
- **决定**：以 matched model/task/start/evaluator/resource 的冻结比较先验证 unified loop 的增量价值，再考虑远端集群、BOHB/qNEHVI、learned controller、Meta-Strategy 或 Advisor。
- **原因**：更复杂的 orchestration 会增加吞吐与机制数量，但不能回答搜索是否优于简单基线。
- **后果**：没有通过相应 admission 的机制只能标记 mechanics/development；效率改善不能补偿 search-value gate 失败。

## D-007：探索自由与评估权威分离

- **状态**：Accepted
- **决定**：允许 operator portfolio、parent selection、novelty、structural rewrite 和未来策略快速探索，但 evaluator、hard gates、blind evidence 与 claim ceiling 保持独立和不可变。
- **原因**：研究系统既不能因过度治理失去发现能力，也不能让发现策略给自己颁发结论。
- **后果**：新机制默认可在 mechanics 或预注册 development 范围试验；晋升必须经过独立、冻结、matched-resource 的 admission。

## D-008：状态与长期规则分层保存

- **状态**：Accepted
- **决定**：根 `AGENTS.md` 保存稳定执行规则；`PROJECT_CONTEXT.md` 保存架构真相；本文件保存决策原因；`CURRENT_STATE.md` 保存会变化的 verdict、在研项目和下一道门。
- **原因**：把所有信息塞入单一入口会快速过期并增加每次任务的上下文成本；只靠对话又无法跨任务稳定复用。
- **后果**：阶段状态变化时不改写长期原则；涉及架构或权威的变化必须同步更新对应层，并保留历史。

## D-009：本机优先并自适应利用计算资源

- **状态**：Accepted
- **决定**：开发、验证、benchmark 和正式运行默认使用当前本机；每次高资源运行根据实时 CPU、内存、GPU/显存、磁盘和负载选择有界并行、batch、缓存与断点续跑策略。远端/云端执行需要明确授权或冻结环境要求。
- **原因**：本机执行减少环境漂移、传输和协调成本，也更容易绑定代码、数据、资源与收据；静态并发参数则可能浪费硬件或造成换页、OOM 和系统失去响应。
- **后果**：独立 task/seed/arm 应在资源允许时并行，但共享 worktree/create-once root 的写入保持串行；性能参数和实际 usage 进入 manifest/receipt，优化不能改变协议语义或 matched-resource 公平面。

## D-010：Parent 概率去垄断与 novelty resample 经济门分离

- **状态**：Accepted
- **决定**：当统一 archive 中存在多个合法 parent 时，parent sampler 必须保留可审计的非垄断概率面；当前 SI-1R policy 将单候选概率上限冻结为 `0.8`。Novelty rejection 只判定候选是否重复，是否重新调用 generator 是独立预算决定；只有 frozen generation reserve 不高于剩余 action budget 且不高于被避免的 evaluation reserve 时才可 resample。
- **原因**：SI-1 冻结证据显示多 parent 时仍有 7/12 次权重塌缩，而三次 duplicate rejection 后的两次自动 resample 消耗 41,386 tokens 和 67.89 秒且没有 improvement。把 rejection 与 resample 绑定会用更贵 generation 替代便宜 evaluation。
- **后果**：Receipt 必须保存完整 parent opportunity 和选择概率；invalid/不兼容 candidate 仍不可因概率修复获得 parent rights。Cheap novelty 层级先行，昂贵层只在前级不确定时运行；不可负担的 duplicate 默认 `REJECT_AND_STOP` 或交还 controller，不增加 arm 总预算。

## D-011：SI-1R 后冻结机制开发，以 fresh system-level trial 决定 search value

- **状态**：Accepted
- **决定**：SI-1R 作为 Search-Value Trial 前最后一次机制维修正式收口。下一阶段 SI-2 只做四个 system-level arms：`CORE`、`CURRENT_DISCOVERYOS`、`VANILLA_STRONG_AGENT` 和一个预先冻结的 `EXTERNAL_STRONG_BASELINE`；不再把 Parent、Novelty 或其他内部机制拆成 confirmatory ablation。SI-2 结果闭合前禁止新增或调优搜索机制，除非发现会使协议无效或不可执行的 blocker。
- **原因**：SI-1R 已用 `719,922` generation tokens 证明 parent probability cap 改变真实选择、novelty cheap-first cascade 避免无效计算，但没有建立 outcome superiority。继续消费同一 pilot corpus 的边际证据价值低，并会放大事后调参风险。
- **后果**：SI-2 必须在任何模型调用前冻结 fresh/confirmation cohorts、四臂实现、matched resources、replicates、指标、统计门、winner rule 和 claim ceiling。Search value、external competitiveness 与 confirmation 分开裁决；效率和 diversity 不能补偿 primary gate 失败。任何 blocker 修复如改变封存面，必须新建协议版本/实验根并使受影响 partial results 失效。

## D-012：SI-2 V1 以 task breadth、官方 Shinka 和 exact sign gate 换取有界强证据

- **状态**：Accepted
- **决定**：SI-2 V1 使用 9 个 fresh discovery tasks（3 个新算法族各 3 个隐藏确定性实例）和 3 个 winner-freeze 后才开放的 confirmation tasks。每个 task/arm 只做 1 个 model replicate、3 次 generation，跨臂匹配 100,000 input+output tokens / 1,800 wall seconds。内部 evaluator 另有 300 CPU 秒安全上限，但它不是跨臂 matched gate。外部 baseline 固定为官方 ShinkaEvolve commit `2bf8cfeb6fd39c79555cd94a8f395d64e740aae8`，通过本地 Headless Codex 使用相同模型和 reasoning effort。
- **原因**：在可承受总调用量内，9 个独立 fresh tasks 比在少数任务上重复 seed 更直接检验 task-level search value；Shinka 有可审计 official runtime、Apache-2.0 license 和本机 Codex 路由，不需要切换 provider/API 权限面。Exact sign test 对小样本不过度依赖分布假设。
- **后果**：`CURRENT_DISCOVERYOS` 对 CORE 与 Vanilla 的两个 confirmatory comparison 必须同时满足方向、median final/AUC 和 one-sided exact sign test，并用 Holm 控制 family-wise alpha `0.10`；至少 8/9 tasks evaluable。单 replicate 的通过只支持冻结 task distribution 和 model/config，不支持跨 model-seed 稳定性。外部 competitiveness 和 confirmation 继续单独裁决。

## D-013：SI-2 以 search value 未建立收口，Vanilla winner confirmation 不升级 DiscoveryOS claim

- **状态**：Accepted
- **决定**：接受 SI-2 的冻结 verdict `SI2_SEARCH_VALUE_NOT_ESTABLISHED`。CURRENT 对 CORE 与 Vanilla 在 9/9 fresh tasks 的 final comparison 全部为 tie，两个 median final delta 均为零、median AUC delta 均为负、Holm sign gates 均失败。按预注册 tie-break 冻结的 `VANILLA_STRONG_AGENT` 在 3 个 withheld tasks 上通过 confirmation，但该结果只确认 winner 的绝对改进能力，不能改写为 DiscoveryOS superiority。Shinka 9/9 runtime failures 保持 `EXTERNAL_BASELINE_NOT_EVALUABLE`，不算科学 loss，也不补位重跑。
- **原因**：完整 CURRENT stack 在相同 model/evaluator/预算下没有找到任何 CORE 或 Vanilla 未找到的 final discovery；小幅 AUC 差异还略偏向 Vanilla。Confirmation 没有重新比较四臂，外部 arm 又在 generation 前因 Windows Headless `spawn EINVAL` 失去可评估性，因此都不能救回 search-value 或 external-competitiveness claim。
- **后果**：SI-2 的 9+3 tasks 全部 consumed，禁止用于策略调优或同分布翻案。原 discovery report 的 secondary token-summary 类型错误通过独立 create-once correction 修正，不改 primary、winner 或 verdict。如继续研究 external competitiveness 或新搜索设计，必须先在 mechanics-only 环境解决 blocker，再使用新协议、新 fresh cohort 和新实验根；在新 admission 前不扩大算力或机制面。

## D-014：停止按机制数量推进，以可识别 intervention 作为 fresh admission 前置门

- **状态**：Accepted
- **决定**：SI-2 后不再以增加 parent、novelty、branch、generation、prompt 或外部机制作为默认推进路线。每个新搜索机制必须先在不消耗 fresh search-value cohort 的 mechanics-only sandbox 中证明：它在可审计 receipt 中相对冻结默认动作改变了控制流，并通过预冻结的 algorithmic-root、behavioral-signature 或资源效用指标产生可识别差异。下一代 system-level 设计以 `STRONG_AGENT_DIRECT` 为默认一级 operator，只有预注册的 stagnation、uncertainty、basin collapse 或 multi-objective conflict 才升级重搜索。
- **原因**：SI-2 autopsy 显示 CURRENT 的 parent 与 novelty 确实发生直接 intervention，三臂候选源码和粗 AST 结构也有分化，但 9/9 final improvement 仍完全相同。现有收据无法识别跨臂 algorithmic basin、behavioral signature 或 paired no-intervention counterfactual；继续加机制会扩大事后解释空间，而不能回答哪些干预真正改变搜索命运。
- **后果**：SI-3 fresh budget 暂不开放。机制 admission receipt 必须绑定 policy invocation、冻结默认动作、实际动作、即时差异和资源成本；algorithmic-root/behavioral probes 必须在模型调用前冻结。Consumed SI-2 只用于诊断，不用于调参或 superiority claim。开发原则为 `Stop adding mechanisms. Start proving interventions.`

## D-015：CIB 用 state-local null、positive sensitivity 和后代持续性判定价值传导

- **状态**：Accepted
- **决定**：Causal Intervention Bench 的基本单位是同一冻结 decision state 上的 paired branch。Null control 使用 default action `A/A` 的独立 stochastic draws，在每个 state 内形成噪声 envelope；positive control 只证明观测链能检测预构造的行为与 utility 差异。真实 intervention 必须依次证明 behavioral manipulation 超出 null、效果穿过 immediate child、utility 或 matched-cost efficiency 受益，并在至少两个独立 states 上复现。Proposal/algorithmic-root 标签只作解释面，冻结 behavioral signature 是主要 manipulation check。
- **原因**：SI-2 已证明 source/AST trajectory 分化，但 9/9 final utility 完全持平。只比较 source、只观察即时 child，或没有 null/positive controls，都无法区分机制无效、模型随机噪声、效果未传导和 evaluator/任务不敏感。
- **后果**：Synthetic fixture 只能把 CIB 提升为 `MECHANICS_READY`，其构造性 `INTERVENTION_VALUE_ADMITTED` 不授予现实机制 admission。Actual Parent policy 在 consumed dev states 上的 semantics-preserving replay 也只能证明 causal path 可执行；为 exercise 选择的 states/sources/seeds、deterministic zero-variance null 和非生成式 downstream 不能替代真实机制 gate。真实机制必须分开 calibration 与 validation states，先冻结 probe/margin 后再验证；通过 CIB 仅获得 SI-3 fresh-budget eligibility 的候选资格，不直接建立 DiscoveryOS search value。SI-3 在此之前保持关闭。

## D-016：Parent 的下一道门是 consumed-state real downstream paired trial

- **状态**：Accepted
- **决定**：不启动 SI-3。CIB-R1 从 SI-2 中实际发生 non-incumbent selection 的 consumed states 冻结 calibration/validation split，在相同强模型、prompt contract、预算和 evaluator 下比较 incumbent parent 与实际 selected parent。每个 branch 用独立 provider request 生成三步 descendant chain；null、positive sensitivity、validity、fitness、replacement、anytime value 和成本共同进入预注册 gate。
- **原因**：现有 Parent-dev replay 已证明 policy intervention 能沿构造的 deterministic downstream 传到 utility，但没有真实生成随机性，也没有回答这种传导在 strong agent 下是否稳定、为正且值得成本。整套系统 A/B 即使出现差异，也无法单独归因 Parent。
- **后果**：只有跨 state paired gate 通过才可写 `REAL_PARENT_MECHANISM_CAUSAL_VALUE`，且只获得另行冻结 fresh trial 的候选资格。校准失败、provider failure、行为改变但 utility 等价和稳定负/零效应分别记录；任何结果都不改写 SI-2，也不自动开放或执行 SI-3。

## D-017：CIB-R1 未建立 strong stochastic generator 下的 Parent 边际因果价值

- **状态**：Accepted
- **决定**：接受 CIB-R1 verdict `PARENT_INTERVENTION_VALUE_NOT_ESTABLISHED_UNDER_STRONG_STOCHASTIC_GENERATOR`。实际 SI-2 Parent receipts 的 non-incumbent intervention 保持 control-flow 事实，但在冻结强模型 downstream 中没有产生超出 state-local stochastic null 的 behavioral manipulation，九个 intervention pairs 的 final descendant value 全为 tie。因此 Parent 不获得现实机制 admission，也不获得 fresh search-value budget 资格。
- **原因**：Calibration 与 validation 的 58 个 branches 全部可评估、资源门通过、live sensitivity 成立，排除了 bench 完全失灵或系统失败这一解释。与此同时，`0/3` states 通过 behavioral manipulation、`0/3` 通过 persistence/benefit、exact-sign `p=1.0`，没有支持稳定正向效应的证据。
- **后果**：SI-3 继续关闭，不在 CIB-R1 consumed states 上改 prompt、margin、operator、state split 或增加 replicate 追逐正结果。该负结论只约束冻结的 consumed-state/model/operator surface；不得扩写为 Parent 普遍无效，但也不得用 mechanics、deterministic replay 或完整系统偶然胜负绕过此 admission。
