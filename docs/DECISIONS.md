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

## D-018：以完整冻结生成合同结算 Parent，而非对机制本体作普遍零效应宣判

- **状态**：Accepted
- **决定**：将 CIB-R1 的预算与治理状态冻结为 `CAUSALLY_INERT_IN_CURRENT_REAL_GENERATION_REGIME`。作用域同时绑定当前 Parent policy、CIB-R1 prompt/context、三步 batched stochastic generator、冻结 model configuration 和 consumed validation surface；科学决定为 `NOT_ADMITTED`，预算为 `CLOSED`，differentiation claim 撤回，同时保留 implementation、lineage 和历史 control-flow receipt。
- **原因**：CIB-R1 的 live sensitivity、可评估性和资源门均成立，但 Parent 在 `0/3` states 改变下游 behavior、`0/3` states 产生 benefit，九个 final pairs 全 tie。这足以关闭同一合同上的继续投资，却没有覆盖其他 inheritance contract、模型、prompt binding 或独立 surface。
- **后果**：禁止在 consumed CIB-R1 surface 上加 seeds、调 Parent probability、事后换 margin、调 prompt 或将 ties 改写为弱正信号。只有新版本 generation/inheritance contract、新 hypothesis、新 calibration 和独立 CIB admission 全部成立时才可重新开放；该状态不得缩写成“Parent 永远无效”。

## D-019：以 Generator Conditioning Fidelity 作为昂贵下游因果预算的前置门

- **状态**：Accepted
- **决定**：在继续研究 controller、Parent、Failure Evidence 或 Operator value 前，先对 `PARENT_SOURCE`、`FAILURE_EVIDENCE` 和 `MECHANISM_BRIEF` 分别执行单变量 conditioning 诊断。GCF 用 same-condition 独立 stochastic null，逐阶段测量 proposal、implementation、repair、final 的 condition survival，并用冻结 hidden behavioral probe 区分结构响应与语义执行。GCF-0 calibration、GCF-1 detectability、GCF-2 semantic transmission 和 GCF-3 downstream causal value eligibility 分开裁决。
- **原因**：CIB-R1 只说明 Parent 条件没有在最终 downstream 产生可分辨价值，不能定位条件未进入 proposal、计划未翻译、repair 同质化、结构差异未变成行为，还是 behavior 存活但 utility 为 tie。直接再跑 controller A/B 会继续混淆生成通道与上游策略价值。
- **后果**：Synthetic identifiability corpus 和 consumed mechanics/development states 可用于 GCF-0 至 GCF-2 诊断，但不得产生 generalization 或 search-value claim。只有现实 channel 在独立 validation states 上通过 GCF-2，才有资格以新 contract、hypothesis、calibration、margin 和独立 surface 预注册 GCF-3 trial；conditioning fidelity 是 downstream value 的必要条件，不是充分条件。

## D-020：停止扩展 GCF 框架，先用 Mechanism Brief 现实诊断检验 transmission

- **状态**：Accepted
- **决定**：第一个现实 GCF channel 固定为 `MECHANISM_BRIEF`，优先于 Failure Evidence 和 Parent Source。使用 CIB-R1 的 2 个 calibration 与 3 个跨任务族 validation consumed states，只改变 constructive greedy 与 iterative local improvement 两份互斥 brief；generator 输出 proposal、implementation、repair、final 四个阶段，确定性 AST/文本 probe 与冻结 hidden behavior probe 对 state-local A/A、B/B stochastic null 作 paired comparison。
- **原因**：明确 mechanism instruction 是最直接、最可能被 generator 执行的上游控制信号。如果它不能穿过 staged generator 并形成 hidden behavior separation，继续优化 parent、planner、memory 或 scheduler 缺少必要的执行通道基础。增加框架功能或单元测试数量不能替代这一现实识别问题。
- **后果**：协议共冻结 66 个独立 model calls；calibration proposal detectability 失败即阻断 validation。GCF-2 只要求跨至少 2/3 validation states 的 final structural 与 hidden-behavior separation，utility 只记录、不参与 transmission admission。正结果仅允许另行预注册独立 GCF-3 value trial；负结果转向 generator interface/execution contract，不依次调 prompt、brief、margin 或 consumed state 追逐通过。

## D-021：GCF-R1 因 proposal calibration 失败而阻断 validation

- **状态**：Accepted
- **决定**：接受 `GCF_R1_CALIBRATION_FAILED` 与 `MECHANISM_BRIEF_REAL_SEMANTIC_TRANSMISSION_NOT_ESTABLISHED`。24 个 calibration branches 全部 evaluable、final valid 且资源合规，但 constructive greedy 与 iterative local improvement 的 proposal signature 在 `0/2` states 超过 same-condition null 加冻结 margin，因此严格执行预注册 blocker，不运行后续 42 个 validation calls。
- **原因**：两个 calibration states 的 proposal A/B distance 都小于各自 null envelope，无法证明冻结 proposal detector 对现实 channel 有足够 sensitivity。Implementation、repair 和 final 结构 separation 虽为 `2/2`，hidden behavior 只有 `1/2`，又没有独立 validation，不能绕过 calibration gate 拼成 positive transmission claim。
- **后果**：GCF-R1 consumed root 关闭，不改 proposal probe、margin、prompt、brief、state 或 replicate 数追逐通过。后续若继续，应提出新版本 structured proposal 或 executable mechanism contract，用新 calibration evidence 验证；在现实 GCF-2 admission 前保持 fresh value trial 和 SI-3 关闭。

## D-022：本地 control plane 与按需远端 compute plane 分离

- **状态**：Accepted as architecture direction; not implemented
- **决定**：DiscoveryOS controller、Research Graph、Evidence Ledger、planner、LLM generation、长期 candidate/artifact 状态与 verdict 权威保留在本地；经用户授权的 AutoDL/其他远端只作为 ephemeral evaluator worker。远端 job 必须绑定 Git commit、candidate bundle、contract/evaluator/data/environment digest、预算和输出 schema，返回 create-once result bundle，由本地验证后写 ledger；远端不得直接写权威 ledger 或取得 final-blind capability。
- **原因**：CPU-heavy、独立 candidate evaluation 适合弹性并行，而 generation、规划和长期证据状态不应随临时 worker 生命周期漂移。Commit-pinned checkout 与 digest-bound result 能避免本地代码变化后无法解释远端分数。
- **后果**：该方向目前是 protocol/architecture only，不是吞吐或 search-value improvement。实现顺序从单个 commit-pinned、fail-closed worker 的纵向切片开始，验证 transport、身份、资源计量、超时、幂等、结果签名和本地 admission 后，才扩展 32C 或多节点 worker pool。已经 seal 的实验不得中途迁移环境；只有新协议可在首个 model/evaluator call 前冻结远端环境。

## D-023：以隔离的 Structured Mechanism Object 替代自由文本 proposal 中介

- **状态**：Accepted; protocol implemented; not yet run
- **决定**：GCF-V2 把 proposal 与 implementation 拆成两个独立 provider request。第一阶段只把 task、base source 和自然语言 mechanism brief 转换为 schema-constrained、canonical、content-addressed Mechanism Object；第二阶段只接收 task、base source 和该对象，不得读取原 brief、condition ID 或 proposal raw response。Categorical control-flow fields 是 proposal admission signature；解释文本不能覆盖与冻结 condition contract 冲突的字段。
- **原因**：GCF-R1 在 proposal `0/2` 的同时出现 implementation/repair/final `2/2`，说明同一 staged call 中的后续代码阶段可能绕过 proposal 并重新解释原 brief。继续用自由文本 proposal 做 parent、novelty 或 research-taste 的中间表示缺少稳定控制证据，也无法区分 proposal mediation 与直接 context reuse。
- **后果**：新协议使用两个新 development calibration states 和每 condition/state 三次独立 draw。先运行 12-call、8,000-token-per-call proposal gate，只有 2/2 states 的 between-condition categorical separation 超过 within-condition stochastic envelope 且所有对象合规时，才开放 12-call implementation gate。Implementation 的 source 与 hidden behavior 分开裁决，utility 只记录；正 calibration 只获得独立 validation 的预注册资格，不能开放 fresh value trial、SI-3 或 superiority claim。Executable obligations 与 runtime counter enforcement 留给通过该中介门后的 V3，不与 V2 同时建设。

## D-024：GCF-V2 R1 provider/schema 失败按 NOT_EVALUABLE 关闭并以前置 preflight 修复

- **状态**：Accepted; R1 closed; R2 executability repair implemented
- **决定**：GCF-V2 R1 的 12/12 proposal invocations 全部在 Codex CLI/schema 边界以 exit `1`、0 tokens 失败，记为 `GCF_V2_R1_NOT_EVALUABLE_PROVIDER_SCHEMA`，不得写成 structured proposal semantic failure。R1 root 保持 create-once，不修改 schema、不补跑。R2 使用新 protocol ID、新 workspace 和新 seal；移除官方 Structured Outputs 支持子集未包含的 `uniqueItems`，同时保留 parse 后 uniqueness 检查。
- **原因**：R1 没有产生任何可评估 Mechanism Object，因而没有进入 condition separation gate。一次 schema transport 缺陷被并发复制成 12 次失败，也证明 scientific schedule 前缺少廉价 executability check。
- **后果**：R2 在 scientific draws 前冻结并执行一次 non-scientific provider/schema preflight，保存 transport error excerpt；失败即停止，成功才开放原 12-call proposal schedule。该修复只恢复协议可执行性，不改变 task、condition、replicate、proposal admission、implementation isolation、behavior gate 或 claim ceiling。

## D-025：以实测 CLI 固定成本修正 R3 ceiling，并把两个 proposal states 改为顺序门

- **状态**：Accepted; R2 closed; R3 implemented; not yet run
- **决定**：接受 R2 preflight 的 provider/schema/contract success，但因 17,497 tokens 超过冻结 8,000 ceiling，将 R2 关闭为 `GCF_V2_R2_PREFLIGHT_RESOURCE_BLOCKED`，不运行 scientific schedule。R3 使用新 protocol ID、root 和 seal，把 preflight/proposal per-call ceiling 冻结为 25,000；weighted coverage 的 3A+3B 为 calibration，只有通过才运行 balanced cut 的 3A+3B independent proposal validation，两者通过才运行 12 个 isolated implementations。
- **原因**：Codex CLI 的固定 model-visible context 已超过原 8,000 ceiling，R2 阻断是 executability/resource-contract 问题，不是 Mechanism Object 失败。顺序 state gate 使最早的科学失败只消耗六 calls；按独立 R2 preflight 的观测约为 104,982 tokens，即 GCF-R1 的 19.6%，同时保留每 condition 三次 same-state stochastic replication。
- **后果**：R2 root 不修改、不重跑。R3 不改变 schema semantics、conditions、每 state replicate 数、task/evaluator content、between-vs-within 判据、implementation isolation、source/behavior margins 或 claim ceiling。Calibration 失败阻断 proposal validation；validation 失败阻断 implementation；任何 positive calibration 仍不建立 utility 或 search value。

## D-026：R3 建立 structured object channel，但 implementation 因资源违规保持 NOT_EVALUABLE

- **状态**：Accepted; R3 closed
- **决定**：接受 R3 proposal calibration 与 independent proposal validation 的正向 development evidence：两个 task families 均为 6/6 evaluable/compliant、within categorical variance `0`、between median `2.23607`，因此可写 `STRUCTURED_MECHANISM_OBJECT_CHANNEL_DETECTED_ON_TWO_DEV_STATES`。最终 implementation verdict 必须保持 `GCF_V2_R3_NOT_EVALUABLE_RESOURCE_CEILING`，因为 3/12 calls 超过冻结 30,000-token ceiling；不得把 hidden behavior `0/2` 写成正式 semantic negative。
- **原因**：Structured Object 已证明比 R1 free-text proposal 更稳定地承载 categorical condition，且 implementation 在 source structure 上 `2/2` 分离；但 resource violation 使完整 mediation evidence 不合规。Behavior between-condition distance 在两个 states 都未超过 within-condition envelope 加 margin，虽是强诊断信号，仍不能绕过资源 gate。
- **后果**：R3 create-once root 关闭，不提高 ceiling、改 margin/probe、补 replicates 或以 utility record-only 数字追逐 positive。`NO_STRUCTURED_MECHANISM_CHANNEL_ADMITTED`、fresh value trial 与 SI-3 保持关闭。下一候选是新版本 Executable Mechanism Contract，用新 states 和预冻结的 required/forbidden call paths、replacement points、invariants、runtime counters 与 failure semantics 直接约束实现；它仍须独立通过 behavior transmission，不能继承 R3 的 positive proposal verdict为 search value。

## D-027：Executable Mechanism Contract 必须由独立 instrumentation 裁决

- **日期**：2026-08-17
- **决定**：EMC-R1 不再把 source embedding 或模型自报 counter 当作 executable evidence。Structured Mechanism Object 由 deterministic compiler 在 implementation 调用前转成 required/forbidden function、entrypoint call edge、runtime counter bounds 和 invariants，并绑定 digest。候选不知道 profile probe 内容；独立 harness 从 `algorithm.py` 的真实 call events 生成权威 counter evidence。
- **原因**：GCF-V2 已检测到 structured object 与 source separation，但 resource violation 使 runtime behavior 未知。若 counter 由候选自行写入或只看函数是否出现，semantic claim 仍可能与实际执行脱节。
- **后果**：EMC-R1 使用全新 assignment/coverage development states 与 create-once root，按 E0 无模型 sensitivity、E1 单次 provider/resource preflight、E2 六次 calibration、E3 六次 independent validation 顺序执行。60,000-token ceiling 只属于新协议，按 receipt post-check fail closed；不得回改 GCF-V2。任何 positive 仍只支持 two-state contract-transmission development claim，utility、fresh value trial 与 SI-3 不自动开放。

## D-028：EMC-R1 implementation enum blocker 关闭原 root，R2 只修 executability

- **日期**：2026-08-17
- **决定**：EMC-R1 的 E0 通过后，E1 在 provider 调用前因不存在的 `GenerationKind.STRUCTURAL_REWRITE` 抛出 `AttributeError`。R1 记为 `EMC_R1_NOT_EVALUABLE_IMPLEMENTATION_ENUM`，0 provider calls、0 tokens，不产生 semantic result，也不原地修改 create-once root。EMC-R2 使用已有 `GenerationKind.PROPOSAL`，换新 protocol ID、records、state IDs 与 workspace。
- **原因**：该失败是封存后暴露的纯 executability blocker，不是 Mechanism Object、contract 或 runtime behavior 的证据。原地修改会破坏 manifest 的 commit/source binding。
- **后果**：R2 保持 R1 的 objects、compiler、tasks、seeds、probe、replicates、gate、60,000-token ceiling 与 claim ceiling；不得趁版本切换调整科学语义。

## D-029：EMC-R2 calibration 因 ceiling 与重复调用审计失败而关闭

- **日期**：2026-08-17
- **决定**：R2 的 E0 与 E1 通过；E2 六个唯一 checkpoint 虽全部通过 source validity、static contract、external runtime counters 与 invariant canary，仍以 `EMC_R2_CALIBRATION_NOT_EVALUABLE_RESOURCE_AND_DUPLICATE_CALL` 关闭。原因是 1/6 persisted implementation calls 使用 61,681 tokens，超过冻结 60,000 ceiling；同时 interrupted aggregation 后的恢复与迟到 worker 对同一 create-once record 发生冲突，证明至少多发 1 次未入账 provider invocation。
- **原因**：资源门和 matched-call accounting 是协议有效性，不因 executable diagnostics 看起来正向而豁免。已入账 7 calls、255,420 tokens 不是实际完整 usage；只能诚实声明至少 8 calls、超过 255,420 tokens，不能猜测未持久化 duplicate 的 tokens。
- **后果**：E3 validation 保持 0 calls，`NO_EXECUTABLE_MECHANISM_CONTRACT_ADMITTED`，fresh value trial 与 SI-3 继续关闭。R2 root 不提高 ceiling、不改变 resume semantics、不补 replicate 或重跑相同 states。未来若修复，应先做 mechanics-only durable in-flight ownership，且不得用 R2 的 6/6 diagnostics 追逐同一科学 pass。

## D-030：provider invocation 使用不可猜测重发的 durable journal

- **日期**：2026-08-17
- **决定**：每个受保护 provider request 在进入外部调用前，必须以 request identity 原子创建 owner claim；正常返回或 `GenerationProviderError` 后立即创建 terminal record，绑定 response、transport、usage、provider request ID 与 failure semantics。恢复时只有完整 terminal 才能零调用重放；claim 存在而 terminal 缺失一律记为状态未知并永久禁止自动 reclaim/retry，除非未来能证明 provider 端支持同一 identity 的幂等执行。任何 phase 在创建 worker pool 前先审计全部 journal；存在一个 orphan claim 即阻断该 phase 的所有新调用。
- **原因**：最终 draw checkpoint 比 provider side effect 晚。用 checkpoint 缺失推断“调用未发生”会在迟到 worker、进程中断或聚合失败时重复消费模型预算，并破坏 matched-call accounting。超时或本机 PID 消失也不能证明外部 provider 没有完成调用。
- **后果**：该机制只建立 crash-safe、at-most-once 的调用 mechanics；它不能恢复 R2 未持久化的 duplicate usage，不能把 R2 的诊断 6/6 升级为 admission，也不自动授权 R3。新的科学协议必须先在非科学故障夹具和资源校准上验证 journal，再使用新 states、独立 root 和预冻结 ceiling。

## D-031：EMC-R3 以独立资源 authority 回答 fresh-state confirmation 问题

- **日期**：2026-08-17
- **决定**：先封存并运行四调用的 `EMC_RESOURCE_CALIBRATION_R1`，只记录 schema executability、exact token 与 wall distribution。科学 ceiling 在资源调用前冻结为 `ceil(max(61,681, observed_max) * 1.25 / 1,000) * 1,000`，且不得超过 100,000。资源 authority 通过后，EMC-R3 才可绑定其 record SHA-256，在全新 assignment calibration 与 coverage validation states 上各运行 3A+3B。
- **原因**：R2 已产生正向 actuation diagnostics，但资源 ceiling 与重复调用使其不可评价。新的问题不是补跑 R2，而是在已修复调用权威和独立实测 ceiling 下，对两份 never-consumed states 做 confirmatory transmission。资源测量必须先于科学封存，避免看到 scientific output 后选择 ceiling。
- **后果**：E0 或 E2 失败立即阻断后续调用。E3 positive 只支持 two-state development transmission，并授权另行预注册 Operator causal-value protocol；它不建立 utility/search value，也不直接发放 fresh search-value budget。任何 resource、provider 或 orphaned invocation failure 都记为 `NOT_EVALUABLE`。

## D-032：确认 resource-calibrated executable actuation，转向 Operator causal value

- **日期**：2026-08-17
- **决定**：接受 `EMC_RESOURCE_CALIBRATION_R1_PASSED` 与 `EMC_R3_EXECUTABLE_CONTRACT_TRANSMISSION_CONFIRMED_ON_TWO_NEW_DEV_STATES`。资源 corpus 4/4 evaluable，推导 ceiling `78,000`；R3 的 assignment calibration 与独立 coverage validation 各 6/6 通过 source validity、static contract、external runtime counters、invariant canary 与 ceiling。两个 states 上 Direct/Repair signature 均稳定为 `[1,0,0]` / `[1,1,0]`，within-condition categorical variation 为零。
- **原因**：R3 使用 never-consumed states、独立资源 authority、create-once receipts 和 durable at-most-once journal，修复了 R2 的两项不可评价原因。12 scientific calls 共 `500,474` tokens，最大 `57,118`；审计得到 12 claims、12 terminals、12 checkpoints、0 orphan、0 duplicate，因此 actuation observation 不再受 resource/accounting violation 污染。
- **后果**：允许另行预注册一个 Operator causal-value protocol，比较已确认可执行的机制是否产生超出同条件 stochastic null 的 utility/value。不得把 EMC-R3 的 record-only utility、两状态 transmission 或 resource compliance 写成 search value、算法优越性或生产能力；fresh search-value execution 仍关闭，直到独立 value gate 通过。

## D-033：Direct/Repair value 必须超过双同条件 stochastic null

- **日期**：2026-08-17
- **决定**：EMC Operator Causal Value R1 使用 Direct/Direct 与 Repair/Repair 两类独立 pair 校准和复核 stochastic envelope，再以 Direct/Repair pair 检验 Operator intervention。两个 assignment/coverage states 只用于 calibration，另外两个预声明 states 只用于 validation。每个 state 在 seal 前必须由 valid baseline 与 valid reference 的冻结 evaluator/probe 差异证明存在 repair applicability；不得在无 headroom state 上把 tie 解释成 Operator 无效。
- **原因**：EMC-R3 已经回答 executable actuation，继续增加 schema、signature 或 state 只会重复 transmission 证据。下一问题是 downstream value，但强 stochastic generator 的自然波动不能由跨条件 raw difference 直接归因；同条件 null、预冻结 margin 和独立 validation 是最小充分的因果门。
- **后果**：calibration 运行 16 calls，validation 运行 28 calls，沿用 EMC-R3 的 provider、78,000 per-call ceiling、contract compiler、external profile instrumentation 与 durable invocation journal。Final utility 和 matched-call anytime AUC 是 efficacy gate，validity/replacement/breakthrough 是预注册 guardrail。任何 contract/signature portability failure 使 utility 不可解释；资源/provider failure 为 `NOT_EVALUABLE`；runtime 分离但 value gate 失败则关闭当前 Direct/Repair value claim，不回头修改 EMC。即使 positive，也只得到 two-state development Operator value，不直接建立 DiscoveryOS search value。

## D-034：执行通道继续成立，但关闭当前 Direct/Repair value claim

- **日期**：2026-08-17
- **决定**：接受 `DIRECT_REPAIR_OPERATOR_CAUSAL_VALUE_NOT_ESTABLISHED_ON_DEV`。Calibration 与 validation 共 44/44 branches 全部 evaluable、资源合规并通过所有 executable contract 层；Direct/Repair runtime signatures 在四个 states 上继续严格分离。六个 validation intervention pairs 的 final utility effect 全在冻结 envelope 内为 tie，两个 states 的 anytime AUC、validity、replacement 和 breakthrough effect 也均为零。
- **原因**：utility manipulation 可解释且资源/accounting 完整，因此不能再用 generator 不服从、contract 未进入 runtime、instrumentation 失敏或 ceiling 不可评价解释 value null。`p=1.0`、`0/2` beneficial states 与全部 primary efficacy gate failure 直接回答了当前冻结 Operator 选择没有建立因果 value；这不证明所有 Operator 或所有任务上普遍无效。
- **后果**：当前 Direct/Repair Operator claim 与科学优先级关闭。Consumed root 不改 margin、task、prompt、contract、endpoint 或 replicate 数，不继续扩展 EMC schema/signature，也不开放 fresh search-value budget。未来若提出不同 Operator，必须有新的 mechanism hypothesis、applicability contract、预注册 null calibration 和独立 value surface；不得把本次 transmission positive 复用成 value evidence。

## D-035：新 Operator 前先建立可证伪的机制诊断闭环

- **日期**：2026-08-17
- **决定**：新增 `CAUSAL_MECHANISM_INTELLIGENCE_R0`，但只实现最小纵向切片：冻结 failure phenotype、至少两个竞争 bottleneck hypotheses、精确覆盖它们的 cheap diagnostic probes、资源绑定结果与确定性状态机。只有恰好一个 hypothesis 为 `SUPPORTED` 且其余全部为 `REFUTED` 时，状态机才输出 `MECHANISM_BRIEF_ALLOWED`；`UNRESOLVED`、`NOT_EVALUABLE`、多 hypothesis supported 或绑定/预算违规均 fail closed。CMI 属于 Search/Research 平面，永远不拥有科学 verdict 或 claim ceiling 权威。
- **原因**：EMC-R3 已建立真实执行通道，Direct/Repair R1 又在该通道上得到所有 value endpoint 为零的可解释 null。当前主要缺口不再是继续增加 Operator 插槽，而是从失败 phenotype 区分 representation ceiling、evaluator insensitivity、implementation bottleneck、structural basin lock 等竞争解释，并让 Operator 由仍存活的瓶颈理论推导。
- **后果**：R0 只运行零模型、零 evaluator、零 fresh-task 的 null/positive synthetic controls；positive 只证明预构造 `H5_STRUCTURAL_BASIN_LOCK` 可被恢复，不建立现实 bottleneck。现实阶段必须另行封存 never-consumed dev states、probe semantics、阈值、预算和独立 value surface。此前不得选择新 Operator、生成现实 Mechanism Brief 或开放 fresh search-value budget。

## D-036：现实诊断先通过零模型 probe calibration

- **日期**：2026-08-17
- **决定**：CMI-R1 只在两个从未消费的 assignment/coverage development episodes 上校准诊断工具，不生成候选。每个 state 冻结 baseline、三个 intermediate controls、reference、六个 evaluator seeds 与三个独立 functional-probe seeds。必须同时满足 baseline/reference valid、reference headroom 至少一个 score resolution、7 个预声明 ranked pairs 至少恢复 6 个、same-source functional distance 精确为零、baseline/reference functional distance 至少 `0.10`。
- **原因**：若 evaluator control、perfect implementation control 或 functional basin assay 本身不敏感，直接花模型预算进行现实瓶颈诊断只会得到不可解释的 null。把该门放在 provider 前可以用秒级本地执行排除 instrumentation failure。
- **后果**：R1 无模型、无 provider、无 fresh search-value task。两状态任一失败即关闭当前 probe 定义，不得进入现实诊断。全部通过也只授权另行预注册小规模现实诊断，不建立现实 bottleneck、不生成 Mechanism Brief、不选择 Operator。
