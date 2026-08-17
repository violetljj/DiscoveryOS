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
PARENT_INTERVENTION_CAUSALLY_INERT_IN_CURRENT_REAL_GENERATION_REGIME
PARENT_SCIENTIFIC_PRIORITY_WITHDRAWN
GENERATOR_CONDITIONING_FIDELITY_PROTOCOL_IMPLEMENTED
NO_REAL_CONDITIONING_CHANNEL_ADMITTED
GCF_R1_REAL_MECHANISM_BRIEF_PROTOCOL_IMPLEMENTED
GCF_R1_CALIBRATION_FAILED
MECHANISM_BRIEF_REAL_SEMANTIC_TRANSMISSION_NOT_ESTABLISHED
GCF_R1_VALIDATION_BLOCKED_NOT_RUN
GCF_V2_STRUCTURED_MEDIATION_PROTOCOL_IMPLEMENTED
GCF_V2_R1_NOT_EVALUABLE_PROVIDER_SCHEMA
GCF_V2_R2_PREFLIGHT_RESOURCE_BLOCKED
GCF_V2_R3_PROPOSAL_CALIBRATION_PASSED
GCF_V2_R3_PROPOSAL_VALIDATION_PASSED
STRUCTURED_MECHANISM_OBJECT_CHANNEL_DETECTED_ON_TWO_DEV_STATES
GCF_V2_R3_NOT_EVALUABLE_RESOURCE_CEILING
NO_STRUCTURED_MECHANISM_CHANNEL_ADMITTED
EMC_R1_PROTOCOL_IMPLEMENTED
EMC_R1_NOT_EVALUABLE_IMPLEMENTATION_ENUM
EMC_R2_PROTOCOL_IMPLEMENTED
EMC_R2_INSTRUMENTATION_SENSITIVITY_PASSED
EMC_R2_PROVIDER_PREFLIGHT_PASSED
EMC_R2_CALIBRATION_NOT_EVALUABLE_RESOURCE_AND_DUPLICATE_CALL
EMC_R2_VALIDATION_BLOCKED_NOT_RUN
EMC_PROVIDER_INVOCATION_JOURNAL_MECHANICS_READY
EMC_RESOURCE_CALIBRATION_R1_PROTOCOL_IMPLEMENTED
EMC_R3_RESOURCE_CALIBRATED_CONFIRMATION_PROTOCOL_IMPLEMENTED
EMC_RESOURCE_CALIBRATION_R1_PASSED
EMC_R3_INSTRUMENTATION_SENSITIVITY_PASSED
EMC_R3_CALIBRATION_PASSED
EMC_R3_EXECUTABLE_CONTRACT_TRANSMISSION_CONFIRMED_ON_TWO_NEW_DEV_STATES
EMC_OPERATOR_CAUSAL_VALUE_R1_COMPLETE
DIRECT_REPAIR_OPERATOR_CAUSAL_VALUE_NOT_ESTABLISHED_ON_DEV
EXECUTABLE_CONTRACT_TRANSMISSION_RECONFIRMED_IN_VALUE_TRIAL
DIRECT_REPAIR_OPERATOR_SCIENTIFIC_PRIORITY_CLOSED
CMI_R0_PROTOCOL_IMPLEMENTED
CMI_R0_SYNTHETIC_DIAGNOSTIC_SENSITIVITY_PASSED
NO_REAL_BOTTLENECK_ESTABLISHED
NO_REAL_MECHANISM_BRIEF_AUTHORIZED
CMI_R1_REAL_PROBE_CALIBRATION_PASSED
BOUNDED_CMI_REAL_DIAGNOSIS_PREREGISTRATION_AUTHORIZED
CMI_R2_REAL_DIAGNOSIS_COMPLETE
CMI_R2_FUNCTIONAL_BASIN_LOCK_SUPPORTED_ON_TWO_DEV_STATES
CMI_R2_DEVELOPMENT_MECHANISM_BRIEF_AUTHORIZED
NO_NEW_OPERATOR_AUTHORIZED
CMI_R3_PROTOCOL_IMPLEMENTED
CMI_R3_FUNCTIONAL_BASIN_ESCAPE_BRIEF_ADMITTED
CMI_R4_PROTOCOL_IMPLEMENTED
CMI_R4_FUNCTIONAL_BASIN_ESCAPE_OPERATOR_MECHANICS_CONFIRMED_ON_TWO_DEV_STATES
CMI_R5_PROTOCOL_IMPLEMENTED
CMI_R5_CAUSAL_VALUE_DETECTED_ON_TWO_CONSUMED_DEV_STATES
CMI_R6_PROTOCOL_IMPLEMENTED
CMI_R6_CONSUMED_DISTRIBUTION_REPLICATION_PASSED
CMI_FRESH_CAUSAL_VALIDATION_ADMISSION_READY
CMI_R7_PROTOCOL_IMPLEMENTED
CMI_R7_FRESH_CAUSAL_REPLICATION_PASSED
CMI_OPERATOR_ADMITTED_ON_FRESH_ASSIGNMENT_COVERAGE_STATES
CMI_ENABLED_SEARCH_VS_IDENTICAL_SEARCH_WITHOUT_CMI_PREREGISTRATION_AUTHORIZED
CMI_SEARCH_VALUE_R1_V1_NOT_EVALUABLE_RESOURCE_ENVELOPE
CMI_SEARCH_VALUE_R1_V2_NOT_EVALUABLE_INVALID_DESCENDANT_TERMINALIZATION
CMI_SEARCH_VALUE_R1_V3_PROTOCOL_IMPLEMENTED
CMI_SEARCH_VALUE_R1_V3_REAL_PROVIDER_PREFLIGHT_PASSED
CMI_SEARCH_VALUE_R1_V3_COMPLETED
CMI_SEARCH_VALUE_NOT_ESTABLISHED
BENCHMARK_BANK_V1_REGISTRY_IMPLEMENTED
BENCHMARK_BANK_V1_DEVELOPMENT_SLICE_EXECUTABLE
BENCHMARK_BANK_V1_R0_R1_ALGOTUNE_DEV_BATCH_EXECUTABLE
BENCHMARK_BANK_V1_R2_ALGOTUNE_DEV_BATCH_EXECUTABLE
BENCHMARK_BANK_V1_ALE_R3_ARTIFACTS_PINNED_EXECUTION_BLOCKED
BENCHMARK_BANK_V1_EXTERNAL_SCIENTIFIC_ADMISSION_NOT_ESTABLISHED
NO_ESCAPE_OPERATOR_IMPLEMENTED
NO_OPERATOR_VALUE_TRIAL_AUTHORIZED
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
- Benchmark Bank v1 的 47-family commit-pinned registry、DEV/SHADOW/SEALED 生命周期门、统一 adapter contract，以及可执行的 consumed Assignment/Coverage development 物化切片。

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
- Benchmark Bank 中 45 个外部 family 的本地 evaluator/adapters admission；被 catalogued 不等于可执行或科学 admitted。

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
7. Parent 现以 `CAUSALLY_INERT_IN_CURRENT_REAL_GENERATION_REGIME` 关闭当前冻结生成合同下的科学优先级和预算；该状态保留 Parent implementation、lineage 和历史 control-flow receipt，不宣称 Parent 机制普遍零效应。重新开放必须同时具备新版本 generation/inheritance contract、新 hypothesis、新 calibration 和独立 CIB admission。
8. 下一允许的诊断路线是 Generator Conditioning Fidelity。先分别检查 Parent source、Failure evidence 和 Mechanism brief 在 proposal、implementation、repair、final 与 hidden behavior 中是否超过 same-condition stochastic null；只有 GCF-2 semantic transmission 通过的现实 channel 才可预注册独立 GCF-3 downstream causal-value trial。当前仅实现并测试 synthetic identifiability fixture，尚无现实 channel admission，也未授权 fresh trial。
9. GCF-R1 已完成 calibration 并按冻结门 fail closed：24/24 branches evaluable、final source valid 且资源门通过；proposal detectability 为 `0/2`，因此 42-call validation 被阻断且实际调用为零。Implementation/repair/final 结构 separation 在 `2/2` calibration states 超过 null，hidden behavior 仅 `1/2`，只能作为 development diagnosis，不能建立现实 channel semantic transmission。不得在 consumed calibration root 上调 proposal probe、margin、prompt、brief 或 replicates 翻案。
10. 下一允许的 GCF 假设应版本化 generator interface，例如 structured proposal 或 explicit executable mechanism contract，并使用新 calibration evidence；不是继续完善通用框架，也不是绕过独立 behavior validation 直接开 fresh value trial。
11. GCF-V2 R1 在 commit `c4fd8a4` 封存后，12/12 proposal invocations 均以 CLI exit `1`、0 reported tokens 在 provider/schema 边界失败，0 个 object 可评估或合规；implementation 严格保持 0 calls。正式状态为 `GCF_V2_R1_NOT_EVALUABLE_PROVIDER_SCHEMA`，不是 structured interface 的语义负结果。R1 create-once root 不修改、不补跑。
12. GCF-V2 R2 的 1-call preflight 已证明 provider、修正 schema、parser 和 condition contract 全部可执行并产出合规对象，但实测 17,497 tokens 超过冻结 8,000 ceiling，因此以 `GCF_V2_R2_PREFLIGHT_RESOURCE_BLOCKED` 关闭；scientific proposal 与 implementation calls 均为零，不能形成语义结论。
13. GCF-V2 R3 已在 commit `c317a0c` 完成。Coverage proposal calibration 与 balanced-cut independent proposal validation 均为 6/6 evaluable/compliant、within categorical envelope `0`、between median `2.23607`，建立 `STRUCTURED_MECHANISM_OBJECT_CHANNEL_DETECTED_ON_TWO_DEV_STATES`；首六个 scientific calls 实耗 104,844 tokens，为 GCF-R1 的 19.53%。
14. R3 的 12/12 isolated implementations 全部 evaluable 且 source valid，source separation 为 `2/2`，hidden behavior 为 `0/2`；但 3/12 calls 超过冻结 30,000-token ceiling，最大 53,655，因此正式 verdict 是 `GCF_V2_R3_NOT_EVALUABLE_RESOURCE_CEILING`，不是 semantic negative。总计 25 calls、529,044 tokens、755.502 summed provider seconds，0 fresh search-value tasks。R3 root 关闭，不提高 ceiling、不改 probe/margin、不补 replicate；implementation validation、fresh value trial 和 SI-3 继续关闭。完整证据见 [`GCF_V2_STRUCTURED_MECHANISM_MEDIATION.md`](GCF_V2_STRUCTURED_MECHANISM_MEDIATION.md)。
15. 下一允许的 generator-interface 假设是新版本 Executable Mechanism Contract：使用新 states，在调用前冻结 required/forbidden call paths、replacement points、invariants 和 runtime counters。它必须重新通过独立 proposal/object、implementation 和 hidden-behavior gates；不得用 R3 的 source separation 或 utility record-only 数字替代 admission。
16. EMC-R1 作为独立 create-once 协议实现：Structured Mechanism Object 经 deterministic compiler 变成 required/forbidden functions、entrypoint call edges、外部 profile counters 与 invariants。候选自报 counter 不具证据权。顺序门为 0-call instrumentation sensitivity、1-call provider/resource preflight、6-call assignment calibration、6-call independent coverage validation。详见 [`EMC_R1_EXECUTABLE_MECHANISM_CONTRACT.md`](EMC_R1_EXECUTABLE_MECHANISM_CONTRACT.md)。
17. EMC-R1 在 commit `cc95730` 封存，E0 的 4/4 instrumentation controls 通过；E1 因不存在的 `GenerationKind.STRUCTURAL_REWRITE` 在 provider 前失败，0 provider calls、0 tokens，正式关闭为 `EMC_R1_NOT_EVALUABLE_IMPLEMENTATION_ENUM`。R1 root 不修补。EMC-R2 只把 request kind 修正为已有的 `PROPOSAL` 并换新 protocol/root，其余科学语义不变。
18. EMC-R2 在 commit `fb643f5` 封存。E0 4/4 通过；E1 以 1 call、19,246 tokens 通过。E2 的六个唯一 checkpoint 均 evaluable、source valid，并 6/6 通过 static contract、独立 runtime counter 与 invariant canary；两条件 signature 稳定为 `[1,0,0]` 和 `[1,1,0]`。但 1/6 calls 使用 61,681 tokens，超过冻结 60,000 ceiling；恢复期间还发生同一 draw 的 create-once writer race，证明至少 1 次重复 provider invocation，实际 usage 至少 8 calls 且超过已入账的 255,420 tokens，精确 usage 不可恢复。正式 verdict 为 `EMC_R2_CALIBRATION_NOT_EVALUABLE_RESOURCE_AND_DUPLICATE_CALL`；E3 validation 0 calls，R2 root 关闭，不提 ceiling、不补跑。完整证据边界见 [`EMC_R1_EXECUTABLE_MECHANISM_CONTRACT.md`](EMC_R1_EXECUTABLE_MECHANISM_CONTRACT.md)。
19. R2 后的 mechanics-only 修复为 provider 调用增加独立 durable journal：调用前原子写入 request-bound owner claim，正常返回或 provider failure 后立即持久化 terminal response、usage 与 request identity；已有 terminal 可零调用恢复，只有 claim 而无 terminal 时永久 fail closed，禁止根据 checkpoint 缺失猜测性重发。phase-level audit 还会在创建 worker pool 前因任一 orphan claim 阻断全部新调用。并发与 orphaned-claim 测试证明同一 request 不会重复进入 provider。该修复不修改 R2 root、不补计 R2 usage，也不授权新科学协议或提高 claim ceiling。
20. EMC Resource Calibration R1 在 commit `49462e0` 封存并通过：4/4 non-scientific calls evaluable，token distribution 为 `17,560–53,449`，总计 `140,495`；预冻结公式仍由历史最大 `61,681` 控制，推导 scientific ceiling `78,000`。resource record SHA-256 为 `49d86e376997ff98ffecf319198e3a7589282bf0b086215465655cbb9b2f84bc`。
21. EMC-R3 在同一 commit 以 manifest digest `aec9e99df6e1b7f214e553a1d4f6115057f5f183791546cf18be2cdc1bdfed64` 封存。E0 4/4 controls 通过；assignment calibration 与独立 coverage validation 均为 6/6 evaluable、source/static/runtime/invariant/resource 全部合规，Direct 与 Repair signatures 在两个 states 上分别稳定为 `[1,0,0]` 与 `[1,1,0]`。12 scientific calls 总计 `500,474` tokens，最大单调用 `57,118 < 78,000`；12 claims、12 terminals、12 draw checkpoints、0 orphan、0 duplicate。
22. 正式 verdict 为 `EMC_R3_EXECUTABLE_CONTRACT_TRANSMISSION_CONFIRMED_ON_TWO_NEW_DEV_STATES`，claim ceiling 仅为 resource-calibrated two-state development transmission。它证明 structured contract 能够可控且由独立 harness 观察地改变真实调用路径；utility 仍是 record-only，search value、superiority 与 production readiness 均未建立。下一步只授权另行预注册一个 Operator causal-value protocol，尚未运行，也未直接开放 fresh search-value budget。完整边界见 [`EMC_R3_RESOURCE_CALIBRATED_CONFIRMATION.md`](EMC_R3_RESOURCE_CALIBRATED_CONFIRMATION.md)。
23. EMC Operator Causal Value R1 已在 commit `8af61c2` 完成。Calibration 16/16 与 validation 28/28 calls 均 evaluable，source/static/runtime/invariant/resource 全通过；Direct/Repair signatures 持续稳定为 `[1,0,0]` / `[1,1,0]`，所以 utility 可解释，不是 contract portability failure。Calibration 冻结 utility margin `0.00667893`、AUC margin `0.005`。
24. 两个 validation states 的六个 Direct/Repair intervention pairs 为 `0 positive / 6 tie / 0 negative`，final utility、anytime AUC、validity、replacement 与 breakthrough delta 全为 `0`，exact-sign `p=1.0`。正式 verdict 为 `DIRECT_REPAIR_OPERATOR_CAUSAL_VALUE_NOT_ESTABLISHED_ON_DEV`。44 calls 总计 `1,951,194` tokens，最大 `69,055 < 78,000`；journal 为 44 claims / 44 terminals / 44 unique request IDs / 44 checkpoints / 0 orphan。当前 Direct/Repair claim 与科学优先级关闭，不回头修改 EMC、不补 replicate，也不开放 fresh search-value budget。完整结果见 [`EMC_OPERATOR_CAUSAL_VALUE_R1.md`](EMC_OPERATOR_CAUSAL_VALUE_R1.md)。
25. CMI-R0 已实现最小诊断纵向切片：`FailurePhenotypeReceipt`、`BottleneckHypothesis`、`DiagnosticProbeResult` 与确定性 fail-closed 状态机。Create-once synthetic run 的 manifest digest 为 `a6f3986da9f234bcbb417e3c2cbb5ea9b0e69cb3303b2e6706149c84d4788984`，report SHA-256 为 `bac3c68811d4f903cb080004378dfdaabe05e9e2e3784816b53bd86f406c8001`；null 保持 `NO_ACTIONABLE_BOTTLENECK`，positive control 唯一恢复预构造的 `H5_STRUCTURAL_BASIN_LOCK`。全程 0 model calls、0 evaluator calls、0 fresh tasks。该结果只证明诊断器能区分预构造输入，不建立现实 bottleneck、不授权现实 Mechanism Brief 或新 Operator，也不开放 fresh search-value budget。完整边界见 [`CAUSAL_MECHANISM_INTELLIGENCE_R0.md`](CAUSAL_MECHANISM_INTELLIGENCE_R0.md)。
26. CMI-R1 real probe calibration 已正式通过。Manifest digest 为 `930ff7a5974da5d41b7b1d949b5b1fbd373ef4204fb8040f89149e92ef70f65d`，report SHA-256 为 `7de7d2238102045373dd8fddd043b1e746df557e0d2137b0433f291ad394f037`。Assignment 与 coverage 均恢复 `6/7` ranked controls，reference headroom 分别为 `0.20914510` / `0.10170301`，same-source functional distance 均为 `0`，baseline/reference distance 为 `0.41975309` / `0.27777778`。全程 0 model/provider calls、0 fresh search-value tasks；只授权另行预注册 bounded real diagnosis，不建立现实 bottleneck。详见 [`CMI_R1_REAL_PROBE_CALIBRATION.md`](CMI_R1_REAL_PROBE_CALIBRATION.md)。
27. CMI-R2 bounded real diagnosis 已完成。Manifest digest 为 `e7729e2d186ce60acd00bf56f61b783c4d8025a8c2babe67c9824da9226d2a0f`，controls SHA-256 为 `7add4d0ec5aa490544b9a1e948b13b420a281b654a6599355b27018ae7ed7dad`，report SHA-256 为 `0dabc1d1fb9850266e5cbdb58a5868bffc45144c408d2d269df17504e47d3dfb`。6/6 calls evaluable/valid，合计 `116,729` tokens；evaluator sensitivity 与 valid-source rate 均为 `1.0`，反证 evaluator insensitivity 与 implementation bottleneck。每 state 的三个 source SHA-256 各不相同，但 evaluator score 与冻结 functional signature 各自完全相同，六个 within-state pair distances 全为 `0`；因此 `H5_STRUCTURAL_BASIN_LOCK` 在这两个 dev states 上被唯一支持，状态机输出 `MECHANISM_BRIEF_ALLOWED`。该结论不授权 Operator、value trial 或 fresh search-value budget。详见 [`CMI_R2_BOUNDED_REAL_DIAGNOSIS.md`](CMI_R2_BOUNDED_REAL_DIAGNOSIS.md)。
28. CMI-R3 functional-basin escape Mechanism Brief 已正式 admitted。Create-once manifest digest 为 `f69966c6a3f7530eb29556c4148dc0bfcc16ae6a441ad5bc0cefee090dafa595`，admission report SHA-256 为 `903837b1fd3de85ed51f12be45c65c9fc5e89933acf37ab39f2895c16bf12acf`。12/12 frozen checks 通过，模型调用、evaluator 调用和 fresh tasks 均为零；不同 source 文本本身不构成干预，未来候选必须有效且在 state-local functional probe 上距 incumbent envelope 大于 `0.10`。Claim ceiling 保持 `DEVELOPMENT_MECHANISM_BRIEF_ONLY`，Operator implementation、value trial 和 fresh search-value budget 仍全部未授权。详见 [`CMI_R3_FUNCTIONAL_BASIN_ESCAPE_BRIEF.md`](CMI_R3_FUNCTIONAL_BASIN_ESCAPE_BRIEF.md)。
29. CMI-R4 functional-basin-escape Operator mechanics 已在 commit `aed8261` 上封存并通过。Manifest digest 为 `05a7c426aeba12c7a13ca51485799a738835520ff094cf3ab46090d36c8397dc`，report SHA-256 为 `6e284e4efce34d0ed4b461989be40a2aebaa5ad410e130da2a59642ed71c6e13`。Assignment/coverage treatment 的 functional distance 分别为 `0.49382716` / `0.30000000`，独立 descendant-behavior distance 为 `0.41975309` / `0.31111111`；null 均为 `0`，positive controls 为 `0.45679012` / `0.30000000`，全部 public validity 与 Brief-to-generation causal reachability 检查通过。模型、evaluator 与 fresh search-value 调用均为零，共执行 24 个本地 public/probe 进程并消费两个新 development states。该结果只建立 deterministic minimal Operator 的 bounded mechanics；一般 escape probability、causal value、utility/AUC、search value 与 superiority 均未建立，R5 和 fresh budget 仍未授权。详见 [`CMI_R4_FUNCTIONAL_BASIN_ESCAPE_OPERATOR.md`](CMI_R4_FUNCTIONAL_BASIN_ESCAPE_OPERATOR.md)。
30. CMI-R5 consumed-development paired causal-value 已在 commit `4465f0e` 上封存并通过。Manifest digest 为 `09260d9c235a22c4a6a348021a834079b9cbb742c040be9af9549d1b0d28ba5b`，report SHA-256 为 `6457625fcf02d9d720a143f62dbf10927adce445863eca8b7b08259070be7b0d`。Assignment/coverage final utility delta 为 `+0.20103693` / `+0.09768933`，two-allocation AUC delta 为 `+0.10051846` / `+0.04884466`；escape rate `0 -> 1`、replacement `0 -> 1`、breakthrough `0 -> 0.5`、两臂 validity 均为 `1`。模型、token 与 fresh tasks 均为零；treatment/control evaluator 总耗时约为 `1.118s` / `0.739s`。正式 verdict 为 `CMI_R5_CAUSAL_VALUE_DETECTED_ON_TWO_CONSUMED_DEV_STATES`，仅适用于该 deterministic escape Operator 相对 behavior-preserving local control 的两个 consumed states；无概率、显著性、一般 CMI value 或 fresh search-value claim，fresh budget 继续关闭。详见 [`CMI_R5_CONSUMED_DEV_CAUSAL_VALUE.md`](CMI_R5_CONSUMED_DEV_CAUSAL_VALUE.md)。
31. CMI-R6 consumed-distribution replication 已在 commit `cd8e7f2` 上封存并通过。Manifest digest 为 `c4b0844fc3beae43f624194318611b3899865abe1199ad705e978294ff2ea876`，report SHA-256 为 `95213c5bb419cd995d2ddc588cc0d394698043da2a4c3fdceafcb10dcbae9dfe`。8/8 treatment 均 escape、utility 超过 state resolution 且 replacement，control 为 0/8；无 negative 或 tie，validity 两臂均为 `1`，breakthrough `0 -> 0.375`。Coverage/Assignment median utility delta 为 `0.08027348` / `0.18481032`，median AUC delta 为 `0.04013674` / `0.09240516`；aggregate/max-state evaluator runtime ratio 为 `0.99956x` / `1.25330x`，13 项 gate 全部通过。模型、token 与 fresh tasks 均为零。正式输出 `CMI_FRESH_CAUSAL_VALIDATION_ADMISSION_READY`，只授权另行预注册极小 fresh causal protocol，不授权执行。Task families 与历史 heuristic evidence 可见，因此这仍不是 blind independent replication，不建立概率、显著性、跨 family 泛化或 search value。详见 [`CMI_R6_CONSUMED_DISTRIBUTION_REPLICATION.md`](CMI_R6_CONSUMED_DISTRIBUTION_REPLICATION.md)。
32. Benchmark Bank v1 已实现并验证 47-family registry：R0/R1/R2/R3/R4/R5 分别为 `8/8/10/6/5/10`，四个外部来源绑定审计时 commit。Assignment 与 Coverage 两个 consumed families，以及 16 个 R0-R2 AlgoTune contract-derived families、32 个 external DEV instances，均可物化并运行 public/evaluator；29 个 families 仍为 `CATALOGUED`，0 个 external family scientifically admitted。R2 已覆盖全部 10 个 structural-search families，并在 bounded deterministic instances 上独立检查 input immutability、feasibility 与 exact objective。AlgoTune DEV adapters 绑定 pinned upstream task/description hash，使用纯标准库的独立本地 evaluator regimes，不冒充官方 AlgoTune evaluator。Registry validation 与物化测试不调用模型、不打开 SEALED shard、不消费 fresh instance；R2 claim ceiling 为 `EXTERNAL_R2_CONTRACT_DERIVED_DEVELOPMENT_ONLY`。详见 [`BENCHMARK_BANK_V1.md`](BENCHMARK_BANK_V1.md)。
33. CMI-R7 已在 commit `913ab5e` 上封存并通过。Manifest digest 为 `df1d2dd26730a5487e8e1e685339b7fd35430abd509cb4ea0433aa6458228209`，report SHA-256 为 `3072e74c1a0114920f98c7930097a5488dd8a50763709a073513a1ef4dca763f`。6/6 states 均 valid 且 paired utility delta 超过 state resolution，0 negative、0 tie；Assignment/Coverage 各 3/3 positive。Control 为 0/6 escape/replacement，Treatment 为 6/6；breakthrough 为 `0/6 -> 1/6`。Aggregate/max-state evaluator runtime ratio 为 `1.04189x` / `1.61769x`，6 项冻结 gate 全通过；6 matched pairs、24 evaluator calls、24 probe calls、0 model calls、0 tokens。六个 exact fresh states 已消费，不得重跑。正式输出 `CMI_OPERATOR_ADMITTED_ON_FRESH_ASSIGNMENT_COVERAGE_STATES`，只授权另行预注册 CMI-enabled Search vs identical Search without CMI。States 是 instance-fresh，不是 distribution、task-family 或 evaluator-regime fresh；search value、概率、显著性、跨 family 泛化和 superiority 仍未建立。详见 [`CMI_R7_FRESH_CAUSAL_REPLICATION.md`](CMI_R7_FRESH_CAUSAL_REPLICATION.md)。
34. ALE R3 六个 family 的 code commit、Hugging Face dataset commit、逐 ZIP LFS SHA-256/大小与 CC-BY-ND-4.0 数据许可证已绑定。官方 ZIP 将 public 工具/seeds 与 private seeds/standings 同包，stock session 初始化会同时生成 public/private inputs；当前 Bank 又缺少 native stdin program bundle，且本机 Docker CLI 可见但 Linux daemon 不可用。因此六题保持 `CATALOGUED`，执行 blocker 固定为 public-only selective extraction、native bundle 和 Docker judge preflight 三项。Registry 会拒绝缺少三项 digest 的伪 execution-ready 状态。本轮未下载/打开任何题目 ZIP，未读取 private seed，未运行 judge，也未消费 ALE shard。详见 [`BENCHMARK_BANK_V1.md`](BENCHMARK_BANK_V1.md)。
35. CMI Search Value R1 V1/V2 分别以 resource-envelope 与 invalid-descendant terminalization blocker 结算为 `NOT_EVALUABLE`，failure receipt SHA-256 为 `fde8384ea996e1b588f5ba62b04b7fd71d7da85675eedac2d4b96cb0b7a9f438` / `1a40a742f6b2584210eb705146beef44c9d56747230ccd0f244772780324d02a`，两批 cohort 均永久不可重用。V3 在 commit `79164cb`、manifest `5c1395d78efc1b102896471655cc9cf83b7d61585592172712b92a4191233d3b` 上完成全部六个 fresh tasks：`0 win / 6 tie / 0 loss`，median final/AUC delta 均为 `0`，exact-sign `p=1.0`。CMI 在 5/6 eligible tasks 上均被调用且 descendant 均 technically accepted，但 retained、downstream-parent 与 downstream retained contribution 均为 `0`；Search advantage 与 Causal transmission gate 失败。Cost gate 通过：enabled/control tokens `429,442 / 538,217`、evaluator calls `30 / 30`、elapsed `501.892s / 724.453s`。正式 verdict 为 `CMI_SEARCH_VALUE_NOT_ESTABLISHED`，report SHA-256 `de4850ae8c75bec35455e197356bd0dc608d47c7e6983a9a9025617ccea2a39b`。六个 V3 fresh tasks 已消费，不得重跑。详见 [`CMI_SEARCH_VALUE_R1.md`](CMI_SEARCH_VALUE_R1.md)。

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
- Generator Conditioning Fidelity：[`GENERATOR_CONDITIONING_FIDELITY.md`](GENERATOR_CONDITIONING_FIDELITY.md)
- GCF-R1 real Mechanism Brief：[`GCF_R1_REAL_MECHANISM_BRIEF.md`](GCF_R1_REAL_MECHANISM_BRIEF.md)
- GCF-V2 Structured Mechanism Mediation：[`GCF_V2_STRUCTURED_MECHANISM_MEDIATION.md`](GCF_V2_STRUCTURED_MECHANISM_MEDIATION.md)
- EMC-R1 Executable Mechanism Contract：[`EMC_R1_EXECUTABLE_MECHANISM_CONTRACT.md`](EMC_R1_EXECUTABLE_MECHANISM_CONTRACT.md)
- CMI-R0 Causal Mechanism Intelligence：[`CAUSAL_MECHANISM_INTELLIGENCE_R0.md`](CAUSAL_MECHANISM_INTELLIGENCE_R0.md)
- CMI-R1 real probe calibration：[`CMI_R1_REAL_PROBE_CALIBRATION.md`](CMI_R1_REAL_PROBE_CALIBRATION.md)
- CMI-R2 bounded real diagnosis：[`CMI_R2_BOUNDED_REAL_DIAGNOSIS.md`](CMI_R2_BOUNDED_REAL_DIAGNOSIS.md)
- CMI-R3 functional basin escape brief：[`CMI_R3_FUNCTIONAL_BASIN_ESCAPE_BRIEF.md`](CMI_R3_FUNCTIONAL_BASIN_ESCAPE_BRIEF.md)
- CMI-R4 functional basin escape Operator mechanics：[`CMI_R4_FUNCTIONAL_BASIN_ESCAPE_OPERATOR.md`](CMI_R4_FUNCTIONAL_BASIN_ESCAPE_OPERATOR.md)
- CMI-R5 consumed development causal value：[`CMI_R5_CONSUMED_DEV_CAUSAL_VALUE.md`](CMI_R5_CONSUMED_DEV_CAUSAL_VALUE.md)
- CMI-R6 consumed distribution replication：[`CMI_R6_CONSUMED_DISTRIBUTION_REPLICATION.md`](CMI_R6_CONSUMED_DISTRIBUTION_REPLICATION.md)
- CMI-R7 fresh-state causal replication：[`CMI_R7_FRESH_CAUSAL_REPLICATION.md`](CMI_R7_FRESH_CAUSAL_REPLICATION.md)
- CMI Search Value R1：[`CMI_SEARCH_VALUE_R1.md`](CMI_SEARCH_VALUE_R1.md)
- Benchmark Bank v1：[`BENCHMARK_BANK_V1.md`](BENCHMARK_BANK_V1.md)
