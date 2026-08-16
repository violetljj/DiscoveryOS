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
