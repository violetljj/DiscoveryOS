# AdaEvolve / EvoX Mechanism Parity Audit

## Status

```text
ADA_EVOX_MECHANISM_PARITY_AUDIT_COMPLETE
CURRENT_ADA_PROFILE_MECHANISM_ROLE_ONLY
CURRENT_EVOX_PROFILE_MECHANISM_ROLE_ONLY
MECHANISM_COMPLETE_PARITY_NOT_ESTABLISHED
OFFICIAL_RUNTIME_PARITY_NOT_ESTABLISHED
P2_PROTOCOL_PAUSED_PENDING_BOUNDED_PARITY_CLOSURE
ZERO_MODEL_CALLS
ZERO_EVALUATOR_CALLS
ZERO_FRESH_ASSETS
```

本审计回答一个窄问题：当前 DiscoveryOS 的 Ada/EvoX 命名究竟吸收了官方系统的哪些搜索机制，以及在四臂 P2 之前最少还必须补什么。它不接纳官方 runtime，不评价搜索效果，也不授权 fresh/SEALED 资产。

## Source binding and claim ceiling

审计绑定以下真源：

- SkyDiscover 官方仓库 commit `8a840394e19ee4bfb3fb0a62762b902561a7efeb`，与 Benchmark Bank v1 已登记 revision 一致；
- 官方 AdaEvolve 论文：[arXiv:2602.20133](https://arxiv.org/abs/2602.20133)；
- 官方 EvoX 论文：[arXiv:2602.23413](https://arxiv.org/abs/2602.23413)；
- DiscoveryOS `main` commit `2904eff`。

论文和官方实现可以证明机制存在、作者的实验设计及作者报告的结果；它们不能单独证明某个组件是性能收益的唯一原因。本审计因此把“实现存在”“论文消融支持”和“本项目推断”分开，不把相关性写成因果性。

## Classification

| Status | Meaning |
| --- | --- |
| `FULLY_ABSORBED` | 该机制的控制语义已由统一 Harness 表达，并有相称 mechanics tests |
| `PARTIALLY_ABSORBED` | 有相关原语，但缺少官方机制的关键闭环、状态或反馈 |
| `MISSING` | 当前 Profile 没有该机制 |
| `INTENTIONALLY_NOT_IMPORTED` | 为保持 Kernel/authority 边界而明确不复制；由现有权威替代或延后 |
| `BENCHMARK_ONLY` | 只适合作为隔离的官方 challenger，不进入 Discovery Mode |

## AdaEvolve audit

官方 AdaEvolve 是三级自适应系统，而不是“对同一 parent 连续做局部 patch”：每轮按 accumulated improvement signal 调整岛内探索强度；以 decayed-magnitude UCB 在岛间分配资源；全局停滞时生成新 paradigm。官方实现还把 parent、inspiration、sibling attempts、evaluator feedback 和质量-多样性 archive 送入生成上下文。

| Official mechanism | Official evidence | DiscoveryOS mapping | Status | P2 disposition |
| --- | --- | --- | --- | --- |
| Lineage-preserving local refinement | Ada context/controller mutate a selected parent and expose sibling attempts | `AdaLineageOperator(LocalPatchOperator)` preserves parent lineage/provenance | `PARTIALLY_ABSORBED` | Keep; add trajectory context closure |
| Evaluator/failure-aware prompt context | Context builder injects parent artifacts, previous attempts and outcomes | Local Patch receives bounded failure/evidence inputs, but no Ada sibling/trajectory assembler | `PARTIALLY_ABSORBED` | Must close before P2 |
| Per-island accumulated improvement state | `AdaptiveState` records normalized improvement and derives intensity each iteration | Generic stagnation counters exist; no per-frontier accumulated signal or frozen intensity mapping | `MISSING` | Must close in bounded form |
| Adaptive explore/exploit generation mode | Intensity changes sampling and mode-aware prompting | Router chooses local versus structural actions, but Ada arm does not adapt local generation mode | `MISSING` | Must close in Ada arm |
| Decayed-UCB island allocation | `MultiDimensionalAdapter.select_dimension_ucb()` | Unified budget and branches exist, but no UCB frontier scheduler | `MISSING` | Defer unless a predeclared historical challenge proves necessity |
| Quality-diversity archive and parent sampling | `UnifiedArchive` combines Pareto/fitness and novelty, then samples by mode | Ledger/graph stores candidates; parent policy exists, but neither is an Ada QD archive | `PARTIALLY_ABSORBED` | No private archive; add only a typed view/policy if admitted separately |
| Migration / dynamic island spawning | Ada database migrates and can spawn islands | Branch creation exists without Ada migration/spawn policy | `PARTIALLY_ABSORBED` | Defer |
| Global-stagnation paradigm breakthrough | Paradigm generator creates tactics from prior solutions/improvements | Structural Rewrite jumps basin but changes a solution, not an Ada tactic object | `PARTIALLY_ABSORBED` | Structural arm covers current P2 role; do not duplicate |
| Private database, evaluator, budget and winner | Full official runtime owns these operationally | DiscoveryOS authority remains unified | `INTENTIONALLY_NOT_IMPORTED` | Never import as scientific authority |
| Full official AdaEvolve runtime | External SkyDiscover runtime | Not normalized to DiscoveryOS authority/lifecycle/replay | `BENCHMARK_ONLY` | Optional external challenger only |

### Ada evidence judgment

The paper defines local adaptation, global bandit allocation and meta-guidance as AdaEvolve's three levels and reports component ablations on two benchmarks. That supports treating them as designed components, but not claiming all three are universally necessary. For the immediate composition question, the smallest defensible closure is **trajectory-conditioned local adaptation**, not wholesale import of islands, archive and migration.

## EvoX audit

官方 EvoX 的核心不是“偶尔做一次更大的 candidate rewrite”，而是把搜索策略本身作为可演化对象：内层按当前策略生成 solution，外层监控 search window；停滞时根据 population state、历史策略及其部署收益生成新搜索程序，验证后切换，并在失败时 rollback。策略改变 parent/inspiration selection 与 variation，而不只改变 solution 内容。

| Official mechanism | Official evidence | DiscoveryOS mapping | Status | P2 disposition |
| --- | --- | --- | --- | --- |
| Stagnation-triggered change | Controller monitors a fixed search window | Action controller has frozen stagnation thresholds | `FULLY_ABSORBED` for trigger mechanics | Keep |
| Structural variation of a solution | Strategies may request structural variation | `EvoXMetaStrategyOperator(StructuralRewriteOperator)` performs lineage-preserving escape | `FULLY_ABSORBED` as a solution operator, not as EvoX | Keep with narrow label |
| Search strategy as evolvable object | `SearchStrategy` plus search-strategy DB hold executable strategies | `strategy_id` is provenance only; no strategy object controls search | `MISSING` | Must close before P2 |
| Coupled solution/strategy loops | Controller runs solution evolution and demand-driven strategy evolution | One solution loop with deterministic router | `MISSING` | Must close in bounded single runtime |
| Strategy performance window/score | `LogWindowScorer` scores deployed strategies from solution improvement | No deployment-bound strategy receipt or score | `MISSING` | Must close before P2 |
| Population-conditioned strategy generation | Context summarizes population, prior strategies, evaluator and search window | Structural brief has lineage/stagnation evidence, not strategy feedback | `PARTIALLY_ABSORBED` | Deterministic projection required; LLM summary optional |
| Evolving selection and variation | Strategy controls sampling/context and problem-specific variation | Parent policy and operator registry are fixed Profile services | `PARTIALLY_ABSORBED` | Bounded strategy space must change both |
| Validate, switch, migrate and rollback | Controller validates strategy, migrates DB and restores fallback | Plugin boot rollback exists, not per-deployment strategy rollback | `PARTIALLY_ABSORBED` | Must close without second authority |
| Historical strategy memory | DB retains strategy, state descriptor and observed performance | Ledger can store receipts; no strategy-deployment service | `PARTIALLY_ABSORBED` | Same-run only; cross-task memory remains P4 |
| Private solution/search DBs and evaluator | Full official runtime owns operational state | DiscoveryOS keeps unified authority | `INTENTIONALLY_NOT_IMPORTED` | Use Graph/Profile objects, not private scientific DB |
| Full official EvoX runtime | External SkyDiscover runtime | Not normalized to DiscoveryOS authority/lifecycle/replay | `BENCHMARK_ONLY` | Optional external challenger only |

### EvoX evidence judgment

The paper's same-budget case study and initialization ablation support the claim that strategy evolution can add value on the reported tasks; they do not make every implementation detail causal. The central parity defect is nevertheless unambiguous: current DiscoveryOS revises the candidate algorithm, while official EvoX revises the algorithm that selects and varies candidates.

## Audit verdict

Current P2 arms are mechanically fair **mechanism-role proxies**, but are not yet a fair test of “AdaEvolve + EvoX composition”:

```text
Ada role today  = lineage-preserving local patch
EvoX role today = stagnation-triggered structural candidate rewrite

Official Ada core  = hierarchical adaptive allocation and guidance
Official EvoX core = demand-driven evolution of the search strategy itself
```

Running P2 now could answer whether two existing DOS operators cooperate, but not whether the useful cores of AdaEvolve and EvoX cooperate. The latter is the intended claim, so P2 protocol sealing is paused.

This does **not** justify importing both runtimes. The bounded parity closure is frozen to two slices:

1. **Ada trajectory adaptation slice**
   - typed per-frontier improvement state derived only from unified Evidence Ledger data;
   - deterministic, content-addressed mapping to a bounded local explore/refine mode;
   - parent evaluator feedback plus prior sibling-attempt outcomes in generation context;
   - no private archive, evaluator, budget, score or winner.
2. **EvoX strategy evolution slice**
   - typed, content-addressed `SearchStrategySpec` controlling bounded parent selection and variation;
   - deployment receipt binding strategy, search-window inputs, budget and downstream outcomes;
   - stagnation-triggered proposal from a pre-frozen strategy space, validation, switch and rollback;
   - same-run history only; no cross-task memory or private authority.

UCB islands, full QD archive, migration, dynamic island spawn, unrestricted strategy-code generation, cross-task strategy memory and official runtime embedding are outside this closure. Adding any requires a separate gap hypothesis and decision.

## Admission gate before P2

The two slices must pass a zero-model P0/P1.5 gate on L0-L2 assets before four-arm sealing:

- typed dependencies, authority override fail-closed, scope and lifecycle rollback;
- content-addressed profile/strategy/provenance and deterministic replay;
- budget failure and deployment rollback without duplicate evaluator/model calls;
- counterfactual controls showing Ada state changes local mode and EvoX strategy changes both parent selection and variation;
- causal transmission to candidate/evaluation behavior on historical or consumed states;
- no evaluator, GateEngine, winner rule, claim ceiling or fresh-asset change.

If either slice fails causal transmission, it is removed or diagnosed on L0-L2; P2 is not rescued by adding more official features. Once both pass, the four profiles are revised, re-digested and the matched-resource P2 protocol can be sealed. Any positive result remains development composition-value evidence, not official runtime parity or superiority.

## Post-audit implementation status

Both bounded slices are now mechanics-ready. The Ada slice has zero-model trajectory-conditioned control/generation-context transmission evidence; see [`ADA_TRAJECTORY_PARITY_SLICE.md`](ADA_TRAJECTORY_PARITY_SLICE.md). The EvoX slice has typed same-run deployment, observation, scoring, retain/switch/rollback provenance and zero-model parent/variation transmission evidence; see [`EVOX_STRATEGY_PARITY_SLICE.md`](EVOX_STRATEGY_PARITY_SLICE.md). Neither establishes candidate behavior or search value. P2 remains frozen until the four comparison Profiles are revised, re-digested and pass the common zero-model fairness gate.
