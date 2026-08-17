# EvoX Typed Strategy State-Machine Parity Slice

## Status

```text
EVOX_TYPED_STRATEGY_STATE_MACHINE_MECHANICS_READY
EVOX_DEPLOY_OBSERVE_SCORE_TERMINAL_PROVENANCE_READY
EVOX_PARENT_AND_VARIATION_CONTROL_TRANSMISSION_CONFIRMED_ZERO_MODEL
EVOX_RUNTIME_GENERATION_CONTEXT_TRANSMISSION_CONFIRMED_ZERO_MODEL
EVOX_CANDIDATE_BEHAVIOR_VALUE_NOT_EVALUATED
EVOX_SEARCH_VALUE_NOT_EVALUATED
ADA_AND_EVOX_BOUNDED_PARITY_SLICES_MECHANICS_READY
P2_REMAINS_FROZEN_PENDING_PROFILE_REVISION_AND_FAIRNESS_GATE
```

This slice implements only the bounded EvoX closure frozen by
[`ADA_EVOX_MECHANISM_PARITY_AUDIT.md`](ADA_EVOX_MECHANISM_PARITY_AUDIT.md). It does not import the official EvoX runtime, executable strategy generation, a private strategy database, cross-task memory, a private evaluator/budget/winner, or fresh assets.

## Implemented vertical slice

`EvoXStrategyStateMachine` owns a frozen, typed, content-addressed strategy space. Each strategy controls both a bounded parent-selection mode and a bounded variation mode. The initial deployed strategy performs current-parent component transfer; a non-improving valid observation switches to incumbent cross-lineage recombination; a failed deployment/evaluation rolls back to the recorded fallback; improvement retains the deployed strategy.

The same-run lifecycle is explicit and ledger-backed:

```text
plan -> deploy -> generation guidance -> observe -> score -> retain | switch | rollback
```

Deployment and settlement are immutable graph nodes. Edges record strategy deployment, observation, score, terminal transition and the resulting active strategy. A new deployment is rejected while an earlier deployment lacks terminal settlement. The decision binds the exact deployment, strategy spec, parent mode and variation mode; missing or altered bindings fail closed before generation.

The unified Harness controller remains responsible for routing. The strategy state machine may select a bounded parent and supply variation guidance, but candidates, evidence, budgets and verdicts remain under the existing `SearchState`, `ExperimentExecutor`, Evidence Ledger and `GateEngine` authorities. No second population, score authority or search loop was added.

## Zero-model parity evidence

Focused tests establish:

- deterministic, content-addressed strategy plans and deployment bindings;
- explicit `deploy -> observe -> score -> switch/retain/rollback` provenance;
- positive evidence retains the deployed strategy;
- non-improving valid evidence switches parent selection from current parent to incumbent and variation from component transfer to cross-lineage recombination;
- missing result/evidence rolls back to the frozen fallback;
- a pending deployment blocks another deployment;
- tampered decision bindings fail before generation;
- a real Harness loop transmits the exact deployed strategy receipt and variation mode into the structural generation request and settles the deployment from unified evaluator evidence.

All providers in these tests are deterministic local fixtures. No external model, scientific evaluator run or fresh/SEALED asset was used. The evidence proves runtime control and context transmission only; it does not prove that a model follows the strategy, improves candidate behavior or creates search value.

## Next gate

The bounded Ada and EvoX slices now satisfy their zero-model mechanics/transmission gate. P2 is still frozen: the four comparison Profiles must next be revised to express `neither`, `Ada-only`, `EvoX-only` and shared `Ada+EvoX`, content-addressed again, and checked through one zero-model matched-resource fairness test. Only then may a separate frozen P2 development protocol authorize model calls.
