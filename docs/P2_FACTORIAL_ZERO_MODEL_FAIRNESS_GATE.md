# P2 Factorial Zero-Model Fairness Gate

## Status

```text
P2_FACTORIAL_PROFILES_REFROZEN
P2_ZERO_MODEL_FACTORIAL_FAIRNESS_GATE_PASS
P2_FACTORIAL_V1_PROTOCOL_SEALED_HISTORICAL
P2_FACTORIAL_V1_EXECUTION_AUTHORITY_FAILED_PRE_MODEL
P2_FACTORIAL_V2_PENDING_CREATE_ONCE_SEAL
P2_SEARCH_VALUE_NOT_EVALUATED
```

This gate closes only the execution-fairness prerequisite created by D-060. It used deterministic local fixtures, made no external model call, opened no fresh/SEALED asset and produced no candidate-behavior or search-value result.

## Re-frozen 2x2 Profiles

`static_composition_profiles()` now returns four one-runtime arms:

| Arm | Ada trajectory slice | EvoX strategy slice | Profile id |
|---|---:|---:|---|
| `neither` | off | off | `profile_fdef41d2505d96de7231ed19` |
| `ada_only` | on | off | `profile_fb49389a6909abedeaf03184` |
| `evox_only` | off | on | `profile_33463b8b06be00e9aea43f81` |
| `ada_evox` | on | on | `profile_4d94994c9187c74cad4a20a0` |

The V2-preseal Profile audit digest is `4753549b6d454bdaba9a2bec6795fcc8314a3563058270609cf86129226916c7`; the exact sealed digest must be rechecked from the committed detached worktree. Direct and Router selections are byte-identical across arms, including `bootstrap_steps=1` and `allow_cross_seed=true`. Every arm always has exactly one `LOCAL_REFINEMENT` and one `STRUCTURAL_ESCAPE` provider. Ada replaces the trajectory-unconditioned local control; EvoX replaces the strategy-unconditioned structural control. Thus the factors change guidance/state semantics without removing an action capability or generation opportunity. Every arm is static and has one content-addressed Profile and one `HarnessSearchRuntime`; the prior two-child naive-parallel topology is not part of this factorial question.

## Executable fairness invariants

`audit_p2_factorial_profiles()` fails closed unless the four exact arms have one Profile each, common Direct/Router bindings match and the two factor positions are exactly local-control/Ada and structural-control/EvoX.

`P2ZeroModelRuntimeSurface.capture()` and `audit_p2_zero_model_runtime_fairness()` additionally require:

- the same `HarnessSearchRuntime`, `SearchLoopRunner`, projector, `UnifiedActionExecutor`, `ExperimentExecutor`, Ledger and Research Graph types;
- identical contract and evaluator bindings;
- identical run budget, ASHA rungs, action limits, seeds, controller cost/reservation policy, provider bindings, environment, winner rule and claim ceiling;
- identical initial action reservation, generation, evaluation, settlement, novelty and downstream-budget surfaces;
- executable and reservation-matched bootstrap, local-refinement and structural-escape paths in all four arms;
- one object-identical Ledger authority inside each arm across the Harness event sink, Research Graph, projector, unified executor, evaluator/budget executor, trace recorder, every operator and the EvoX strategy state machine when loaded;
- a distinct job-scoped physical ledger for each arm, preventing cross-arm candidate, strategy, lineage, evidence or budget contamination.

Focused tests also demonstrate that tampering with a factor plugin surface, sharing a physical ledger, changing the frozen resource surface or creating an additional authority fails the audit.

## Scientific question and claim ceiling

The eventual P2 comparison is a 2x2 factorial test of:

1. the main effect of trajectory-conditioned Ada local adaptation;
2. the main effect of online EvoX search-strategy adaptation;
3. their interaction, represented by `(Ada+EvoX - Ada-only) - (EvoX-only - neither)` under the predeclared metric and aggregation rule.

This document does not choose tasks, provider versions, model-call ceilings, evaluator-call ceilings, statistics, winner thresholds or stop conditions. Those belong to a separate create-once P2 development protocol. Until that protocol is frozen before the first model call, P2 remains scientifically unexecuted and no static-composition, search-value, generalization or superiority claim is authorized.

## Next gate

Seal the matched-resource P2 development protocol on L0-L2 assets only. It must bind exact task instances, all provider executable/model/settings identities, per-arm calls and resource envelopes, evaluator semantics, factorial estimands, multiplicity/statistics, winner rule, stop conditions, replay and the development-only claim ceiling. No new search mechanism may be added during that seal.
