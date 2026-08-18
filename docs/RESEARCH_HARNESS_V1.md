# DiscoveryOS Research Harness V1

## Status

```text
RESEARCH_HARNESS_V1_EXECUTION_BACKBONE_MECHANICS_READY
MANIFEST_BOUND_RESEARCH_PROFILE_READY
P2_FACTORIAL_PROFILES_REFROZEN
CAPABILITY_CONTRACT_ROUTING_V1_1_READY
PROFILE_TO_SEARCH_RUN_REPLAY_BINDING_READY
LIVE_BUDGET_EVALUATOR_AUTHORITY_BOUND
SEPARATE_LOCAL_AND_STRUCTURAL_PROVIDERS_READY
CORE_CLI_ISOLATED_FROM_HISTORICAL_PROTOCOL_RUNNERS
HISTORICAL_PROTOCOL_REPLAY_COMPATIBILITY_PRESERVED
STATIC_HARNESS_COMPOSITION_VALUE_NOT_EVALUATED
P2_DEVELOPMENT_PROTOCOL_SEALED_PRE_MODEL
MECHANISM_COMPLETE_PARITY_NOT_ESTABLISHED
P2_ZERO_MODEL_FACTORIAL_FAIRNESS_GATE_PASS
P2_V4_PREMODEL_DESIGN_STATISTICAL_SEAL_FROZEN
P2_V4_SCIENTIFIC_GENERATION_NOT_AUTHORIZED
ADA_TRAJECTORY_CONTROL_TRANSMISSION_CONFIRMED_ZERO_MODEL
EVOX_TYPED_STRATEGY_STATE_MACHINE_MECHANICS_READY
EVOX_PARENT_AND_VARIATION_CONTROL_TRANSMISSION_CONFIRMED_ZERO_MODEL
DISCOVERYOS_SEARCH_VALUE_NOT_YET_ESTABLISHED
```

V1 is an execution-architecture refactor. It performs no new model call, opens no fresh/SEALED asset, changes no evaluator or GateEngine rule, and creates no scientific result. V0 remains an immutable description of the earlier composition-only mechanics and is superseded only as the default runtime profile.

## What V1 changes

### Profile to execution backbone

`HarnessSearchRuntime` is now the single composition path from a frozen `ResearchProfile` to the existing `SearchLoopRunner`:

```text
ResearchProfile
  -> verify every PluginManifest digest
  -> boot typed ResearchContext
  -> resolve ACTION_CONTROLLER + OPERATOR_REGISTRY
  -> build UnifiedActionExecutor from the registry
  -> run the ledger-backed SearchLoopRunner
  -> settle terminal Harness events
  -> reverse-order plugin teardown
```

The unified evaluator, receipt, budget reservation/reconciliation and GateEngine path is retained. Harness code selects Search-plane services; it does not fork a second executor or verdict system.

### Manifest-bound profiles

Every `PluginManifest` now binds:

- plugin id and version;
- source system and source revision;
- license status;
- implementation digest;
- authority scope;
- failure semantics and replay contract;
- declared Search-plane capabilities;
- typed `requires` and `provides` services.

Every `PluginSelection` freezes the expected manifest digest. Profile boot fails closed on a mismatch, and the profile id includes those bindings plus config and order. Plugin graph nodes use manifest digests rather than only `plugin_id@version`.

The current source-role metadata is intentionally narrow. Ada/EvoX names still describe mechanism roles implemented inside DiscoveryOS; `UNSPECIFIED_REFERENCE_LICENSE_INTERNAL_IMPLEMENTATION` is not external-runtime admission and must be replaced by exact upstream license/source bindings before an official port claim.

### Re-frozen P2 factorial arms

`static_composition_profiles()` now exposes four one-runtime, 2x2 factorial arms:

- `neither`: Direct, trajectory-unconditioned local refinement control and strategy-unconditioned structural escape control;
- `ada_only`: replace only the local control with trajectory-conditioned Ada adaptation;
- `evox_only`: replace only the structural control with the typed same-run EvoX strategy state machine;
- `ada_evox`: replace both controls with the bounded parity slices in one shared research state.

Every arm is exactly one `HarnessSearchRuntime`; no baseline requires a compatibility-only direct `SearchLoopRunner` path and there is no child-budget settlement difference. Direct and Router selections, including `bootstrap_steps=1` and `allow_cross_seed=true`, are identical. All arms expose the same bootstrap/local/structural action capabilities; only the implementation occupying the Ada and EvoX factor positions changes. In the V1.1 closure, each operator plugin binds one or more typed roles from `BOOTSTRAP_PROPOSAL`, `LOCAL_REFINEMENT`, `STRUCTURAL_ESCAPE` and `META_STRATEGY` into both its manifest digest and strategy descriptor. `HarnessResearchController` resolves those roles without containing Direct/Ada/EvoX operator or strategy ids. Missing capabilities and multiple providers for the same capability fail closed; the router never silently substitutes a different action class. Cross-strategy handoff is also derived from the source and target capabilities rather than source-system names.

This is a composition contract, not package discovery or a plugin marketplace. `standard_research_plugins()` remains the static built-in catalog, and a Profile currently admits at most one provider for each routed capability unless a future, separately versioned selection policy is frozen. Because capability declarations enter manifest digests, this closure creates new Profile identities; earlier run manifests and receipts remain bound to their original code/manifest identities and are not rewritten.

The older lineage/structural/naive-parallel/static-Harness helper Profiles remain compatibility surfaces for earlier design history but are no longer returned as the current P2 comparison arms. This code does not seal a task wave or make model calls.

### Profile-to-run binding

Every new Harness run must supply a `HarnessRunManifest`. Build now fails closed unless it matches:

- the exact Profile id and ordered PluginManifest digests;
- the `SearchRunSpec`, contract, evaluator bindings, seeds, total budget, winner rule and claim ceiling;
- root-candidate environment and task-instance digests;
- local and structural provider/model/settings identities plus recorded executable versions;
- Git commit, tracked-tree digest, clean-worktree assertion and a transitive Harness code-bundle digest.

The ledger records an explicit `PROFILE_EXECUTED_SEARCH_RUN` edge and a create-once manifest node. `replay_harness_run_binding()` rechecks the stored node/edge and current bindings; code, profile, provider, source-tree or frozen-run drift is invalid rather than best-effort replay.

### Real authority services and provider separation

The root context now binds the actual `ExperimentExecutor` as live budget/evaluation authority. Construction fails unless contract, ledger and artifact identities match. This preserves the existing reservation, reconciliation and fail-closed evidence path.

Direct/Ada local refinement and EvoX structural revision use distinct provider services. This removes the V0 assumption that one provider/schema can safely serve both local-patch and structural-rewrite requests.

### Historical surface isolation

The installed core CLI now contains only authority-kernel demo/status/replay and profile inspection commands. Historical SI-2/CIB/GCF/EMC/CMI runners are loaded only when requested:

```powershell
python -m discoveryos --help
python -m discoveryos legacy --help
python -m discoveryos cmi-r7-run-fresh --help  # direct compatibility, lazy load
```

`discoveryos.benchmarks` is also lazy. Historical package-level exports remain compatible, while new work should import concrete modules. Protocol-neutral `SearchValueTask` and source normalization live in `benchmarks/task_types.py` instead of an MVP-0 experiment module.

No historical runner, protocol document, negative result or regression test was deleted. Isolation is not evidence erasure.

## Mechanics evidence

Focused tests establish:

- manifest binding and mismatch rejection;
- authority inheritance and override rejection;
- atomic boot, reverse rollback and teardown;
- Direct/Ada/EvoX registry composition and deterministic routing;
- a previously unknown operator id routes solely from its declared capability;
- duplicate capability providers fail closed instead of depending on plugin names or load order;
- all four one-runtime P2 factorial Profiles, exact Ada/EvoX factor presence, and rejection of unauthorized Profile differences;
- identical runtime, executor, evaluator, budget, reservation, provider and resource-envelope surfaces across the four arms;
- one unified Ledger/Research Graph authority per arm, including all loaded operators and EvoX strategy state, with separate job-scoped physical ledgers across arms;
- create-once Profile-to-Run binding and fail-closed replay under code-bundle drift;
- Profile → Harness runtime → unified executor → evaluator/ledger settlement;
- core CLI and benchmark-package imports do not load historical runners;
- historical CLI commands remain reachable through lazy compatibility routing.

These tests establish only execution mechanics and dependency isolation. They do not establish official Ada/EvoX parity, static composition value, adaptive value, generalization or superiority.

## Mechanism parity audit

The source-bound [`ADA_EVOX_MECHANISM_PARITY_AUDIT.md`](ADA_EVOX_MECHANISM_PARITY_AUDIT.md) confirms that the current Ada/EvoX plugins are mechanism-role proxies, not mechanism-complete ports. Ada currently retains lineage-local refinement but not the official hierarchical adaptive loop. EvoX currently retains a stagnation-triggered structural solution rewrite but not the official evolution of parent-selection and variation strategy.

P2 sealing was paused for a bounded, zero-model parity closure: trajectory-conditioned Ada local adaptation and a typed same-run EvoX strategy deployment/switch/rollback slice. That closure is complete. The audit continues to exclude wholesale runtime import, private archives or evaluators, unrestricted strategy-code generation, cross-task memory and fresh assets.

Both bounded slices are implemented. [`ADA_TRAJECTORY_PARITY_SLICE.md`](ADA_TRAJECTORY_PARITY_SLICE.md) records receipt-bound trajectory control and generation-context transmission. [`EVOX_STRATEGY_PARITY_SLICE.md`](EVOX_STRATEGY_PARITY_SLICE.md) records typed same-run strategy deployment, observation, scoring and retain/switch/rollback, including changes to parent selection and variation guidance. The comparison Profiles have now been revised, re-digested and passed the common zero-model fairness gate; see [`P2_FACTORIAL_ZERO_MODEL_FAIRNESS_GATE.md`](P2_FACTORIAL_ZERO_MODEL_FAIRNESS_GATE.md). These tests establish mechanics/transmission and execution fairness only; they do not establish candidate behavior or value.

## Remaining deliberate legacy boundary

`SearchLoopRunner`, `DeterministicActionController`, ledger projector and unified executor remain stable Kernel/Runtime primitives. Historical protocols can still instantiate them directly to preserve replay behavior. New search work must enter through `HarnessSearchRuntime`; direct construction is compatibility-only and must not become a new default path.

Parent/Novelty/CMI and old protocol runners remain frozen regression/evidence assets. Moving them to new paths would change historical import bindings without adding scientific value, so V1 isolates them from default imports instead of deleting or rewriting them.

## Next gate

V1 failed its first independent-worktree authority check before any model call because the Harness digest was line-ending sensitive and the frozen source lacked a complete runner. V2 normalized CRLF/LF and bound the 12-block runner, but its first block exposed a second pre-model identity bug: generated task repositories use timestamp-varying commit IDs despite identical trees. V3 bound the stable task Git tree, sealed from commit `8d9b80d`, and completed all 12 scheduled terminals. Only 9 paired blocks were evaluable: one exceeded the frozen wall ceiling and both `load_balance_alpha` replicates failed baseline-evaluator preflight. The frozen all-block rule therefore closed V3 as `NOT_EVALUABLE`, with `estimands=null` and `p3_authorized=false`; replay passed with no issues. V1/V2/V3 roots remain immutable. See [`P2_FACTORIAL_DEVELOPMENT_PROTOCOL.md`](P2_FACTORIAL_DEVELOPMENT_PROTOCOL.md).

The successor V4 design is now frozen before runner or manifest implementation. It preserves the V3 factorial estimands, exact sign/Holm/effect and P3 rules, uses at most 24 distinct problem-family blocks, requires a 24/24 full-cohort Executability Gate before any model call, and permits only machine-proven whole-block recovery for a bounded whitelist of exogenous host failures. The current Bank has only 16 eligible external DEV families, so Bank expansion precedes V4 implementation and no scientific generation is authorized. See [`P2_FACTORIAL_V4_PREMODEL_STATISTICAL_SEAL.md`](P2_FACTORIAL_V4_PREMODEL_STATISTICAL_SEAL.md).
