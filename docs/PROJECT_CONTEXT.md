# DiscoveryOS 项目上下文

## 一句话定义

DiscoveryOS 是一个证据优先的统一算法研究内核：在冻结问题协议和评估权威下，让不同搜索机制共享候选、谱系、预算、证据与执行状态，并用可重放的门控结果约束结论。

它的目标不是把 ShinkaEvolve、AdaEvolve、EvoX 等完整 runtime 编排到一起，而是吸收其中可验证的机制，重构为 DiscoveryOS 内部原语。原版系统仅能在隔离的 Benchmark Mode 中作为公平 challenger。

## 产品与研究目标

系统最终希望持续回答三个不同问题：

1. **Mechanics**：候选生成、执行、预算、账本和重放是否正确工作？
2. **Search value**：在冻结任务和 matched resources 下，统一搜索是否比基线更有效地把预算转化为改进？
3. **Certification**：已冻结 winner 在未参与选择的 final blind 上是否满足冻结合同？

这三个问题不可互相替代。可运行不等于搜索有效，development improvement 不等于 blind certification，认证一个冻结候选也不等于生产安全。

## 核心数据流

```text
Frozen ProblemContract
  -> protocol/task admission
  -> operator produces content-addressed CandidateSpec
  -> scheduler reserves bounded resources
  -> frozen evaluator executes at an authorized fidelity/split
  -> create-once EvidenceRecord + artifacts + resource reconciliation
  -> GateEngine applies validity, hard constraints and claim ceiling
  -> feasible development evidence informs Pareto/search scheduling
  -> frozen winner
  -> separate Certification command obtains G7 final-blind capability
  -> replay revalidates bindings and evaluator output
```

## 三个权威平面

| 平面 | 权威 | 允许决定 | 不允许决定 |
|---|---|---|---|
| Evidence | frozen evaluator、data split、digest-bound receipt | 某次观察是否有效、可否重放 | 修改协议或扩大 claim |
| Search | operator、controller、scheduler、Pareto utility | 下一单位资源花在哪里 | 读取 final blind、宣布科学胜利 |
| Claim | `ProblemContract` + `GateEngine` | verdict 和最大可声明范围 | 把调度分数包装成结论 |

## 核心对象

- `ProblemContract`：目标、指标方向、硬约束、预算、数据/evaluator/fidelity 绑定、winner rule 和 claim ceiling。
- `CandidateSpec` / `ExecutableCandidateBundle`：内容寻址候选及其代码、环境、命令和 lineage。
- `ExperimentSpec`：trial、rung、replicate、attempt、resource fingerprint 和 promotion identity。
- `EvidenceRecord`：候选、合同、evaluator、split、输出、资源与有效性绑定的 create-once 收据。
- `EvidenceLedger`：SQLite WAL 持久化的研究图、预算、决策、settlement 和 receipt 索引。
- `GateEngine`：协议有效性、硬约束、科学可行性和 claim ceiling 的唯一裁决入口。
- `SplitVault`：按 mode/fidelity/candidate freeze 发放数据 capability 的 fail-closed 边界。
- `ReplayEngine`：检查不可变绑定并重执行冻结 evaluator，以发现数据、代码或输出漂移。

## 代码地图

| 路径 | 职责 |
|---|---|
| `src/discoveryos/contracts/` | 冻结 schema、codec、protocol admission、patch/bundle contracts |
| `src/discoveryos/graph/` | hypothesis、component、strategy、claim 及谱系模型 |
| `src/discoveryos/evaluation/` | evaluator registry、GateEngine、Pareto、winner、replay |
| `src/discoveryos/operators/` | Random、ASHA、Local Patch、Structural Rewrite、parent/novelty 等机制 |
| `src/discoveryos/runtime/` | ledger、artifact、vault、scheduler、provider invocation journal、repository runner、search loop |
| `src/discoveryos/memory/` | semantic delta 和 progressive context 基础接口 |
| `src/discoveryos/mechanism_intelligence.py` | failure phenotype、竞争瓶颈假设、冻结诊断 probe 与 fail-closed 研究状态机；只属于 Search/Research 平面 |
| `src/discoveryos/benchmarks/` | 冻结 admission/benchmark runner、Benchmark Bank registry/adapter 与任务定义 |
| `src/discoveryos/domains/` | 可执行领域包；当前含 deterministic clearance demo |
| `tests/` | mechanics、失败路径、协议封存、预算、重放和研究循环验证 |
| `docs/` | 架构、协议、正式结果、claim ceiling 与阶段状态 |

## 运行模式与数据角色

- `DISCOVERY`：只允许公开/开发数据与 G0/G1/G2 等已授权 fidelity；不得取得 final blind。
- `BENCHMARK`：隔离运行外部 challenger 并归一化合同、预算和收据；不得写入 Discovery Mode 内部状态。
- `CERTIFICATION`：只接受 discovery 已冻结的 candidate，在 G7 使用 final-blind；认证结果不回流换 winner。

`SplitVault` 当前只提供应用层能力隔离。面对同一 OS 身份下的 hostile code，需要独立服务或独立系统身份，这是生产化前的明确缺口。

## 证据等级与诚实措辞

从低到高应使用精确状态，不允许跳级：

```text
PROTOCOL_ONLY
MECHANICS_READY
DEVELOPMENT_SIGNAL_{POSITIVE|NEUTRAL|NEGATIVE}
ADMITTED_ON_FROZEN_DISTRIBUTION
CERTIFIED_ON_FINAL_BLIND
PRODUCTION_READY
```

`INVALID` 表示证据违反绑定或协议；`NOT_EVALUABLE` 表示系统没有产生可用于科学判断的结果；二者都不是算法失败。Synthetic、consumed-task 或 smoke 证据通常只能支持 mechanics 或 development 级声明。

## 常用入口

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
python -m discoveryos demo-discovery --workspace runs/clearance-demo
python -m discoveryos status --workspace runs/clearance-demo
python -m discoveryos demo-certify --workspace runs/clearance-demo
python -m discoveryos demo-replay --workspace runs/clearance-demo
```

阶段性 runner、冻结参数和结果必须以对应 `docs/*.md` 为准，不要根据命令名称推断其 admission 权威。

## 阅读路由

- 当前结论和下一步：`CURRENT_STATE.md`
- 已确定的设计原因：`DECISIONS.md`
- 本机依赖和工具位置：`LOCAL_ENVIRONMENT.md`
- 总体架构路线：`ARCHITECTURE.md`
- ASHA mechanics admission：`ASHA_ADMISSION.md`
- Local Patch verdict：`LLM_LOCAL_PATCH_ADMISSION.md`、`LLM_LOCAL_PATCH_RELIABILITY.md`
- Search-value MVP：`SEARCH_VALUE_MVP0.md`、`MVP0_BUDGET_REACHABILITY_REPAIR.md`
- Search policy protocol：`SEARCH_POLICY_ADMISSION.md`
- Shinka-style mechanism mapping / SI-1：`SHINKA_MECHANISM_MAPPING.md`、`STRATEGY_INTEGRATION_SI1.md`
- SI-1 parent/novelty repair：`SI1_PARENT_NOVELTY_REPAIR.md`
- SI-2 fresh search-value trial：`SI2_FRESH_SEARCH_VALUE_TRIAL.md`
- SI-2 consumed-trace causal diagnosis：`SEARCH_CAUSALITY_AUTOPSY.md`
- Causal Intervention Bench：`CAUSAL_INTERVENTION_BENCH.md`
- Generator Conditioning Fidelity：`GENERATOR_CONDITIONING_FIDELITY.md`
- First real Mechanism Brief GCF diagnosis：`GCF_R1_REAL_MECHANISM_BRIEF.md`
- Structured Mechanism Mediation / GCF-V2：`GCF_V2_STRUCTURED_MECHANISM_MEDIATION.md`
- Executable Mechanism Contract / EMC-R1：`EMC_R1_EXECUTABLE_MECHANISM_CONTRACT.md`
- Resource-calibrated EMC confirmation / EMC-R3：`EMC_R3_RESOURCE_CALIBRATED_CONFIRMATION.md`
- Direct/Repair Operator causal value / EMC-OCV-R1：`EMC_OPERATOR_CAUSAL_VALUE_R1.md`
- Causal Mechanism Intelligence / CMI-R0：`CAUSAL_MECHANISM_INTELLIGENCE_R0.md`
- Real probe calibration / CMI-R1：`CMI_R1_REAL_PROBE_CALIBRATION.md`
- Bounded real diagnosis / CMI-R2：`CMI_R2_BOUNDED_REAL_DIAGNOSIS.md`
- Functional basin escape Mechanism Brief / CMI-R3：`CMI_R3_FUNCTIONAL_BASIN_ESCAPE_BRIEF.md`
- Functional basin escape Operator mechanics / CMI-R4：`CMI_R4_FUNCTIONAL_BASIN_ESCAPE_OPERATOR.md`
- Consumed development causal value / CMI-R5：`CMI_R5_CONSUMED_DEV_CAUSAL_VALUE.md`
- Consumed distribution replication / CMI-R6：`CMI_R6_CONSUMED_DISTRIBUTION_REPLICATION.md`
- Fresh-state causal replication / CMI-R7：`CMI_R7_FRESH_CAUSAL_REPLICATION.md`
- Complete-search CMI on/off value trial：`CMI_SEARCH_VALUE_R1.md`
- CMI consumed-trace search transmission autopsy：`CMI_SEARCH_TRANSMISSION_AUTOPSY_R1.md`
- CMI consumed-V3 forced-lineage stepping-stone test：`CMI_FORCED_LINEAGE_TRANSMISSION_R1.md`
- 长期 Benchmark Bank、family/shard 生命周期与 adapter admission：`BENCHMARK_BANK_V1.md`
