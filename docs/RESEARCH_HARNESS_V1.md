# DiscoveryOS Research Harness V1

## Status

```text
RESEARCH_HARNESS_V1_EXECUTION_BACKBONE_MECHANICS_READY
MANIFEST_BOUND_RESEARCH_PROFILE_READY
P2_STATIC_COMPOSITION_PROFILES_READY
CAPABILITY_CONTRACT_ROUTING_V1_1_READY
PROFILE_TO_SEARCH_RUN_REPLAY_BINDING_READY
LIVE_BUDGET_EVALUATOR_AUTHORITY_BOUND
SEPARATE_LOCAL_AND_STRUCTURAL_PROVIDERS_READY
CORE_CLI_ISOLATED_FROM_HISTORICAL_PROTOCOL_RUNNERS
HISTORICAL_PROTOCOL_REPLAY_COMPATIBILITY_PRESERVED
STATIC_HARNESS_COMPOSITION_VALUE_NOT_EVALUATED
P2_DEVELOPMENT_PROTOCOL_NOT_SEALED
MECHANISM_COMPLETE_PARITY_NOT_ESTABLISHED
P2_PROTOCOL_PAUSED_PENDING_PROFILE_REVISION_AND_FAIRNESS_GATE
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

### First-class P2 static arms

V1 now exposes four frozen arm definitions through `static_composition_profiles()`:

- `lineage_static_v1`: Direct bootstrap followed by Ada-role local lineage refinement, with structural capability absent;
- `structural_static_v1`: Direct bootstrap plus EvoX-role structural escape, with Ada capability absent;
- `naive_parallel_v1`: two isolated child profiles, one lineage and one structural, both with cross-seeding disabled; a formal runner must split the total arm budget before either child starts and apply the frozen winner rule only after both settle;
- `harness_static_v1`: Direct + Ada + EvoX in one shared research state with deterministic cross-strategy handoff.

Every child profile boots through `HarnessSearchRuntime`; no baseline requires a compatibility-only direct `SearchLoopRunner` path. In the V1.1 closure, each operator plugin binds one or more typed roles from `BOOTSTRAP_PROPOSAL`, `LOCAL_REFINEMENT`, `STRUCTURAL_ESCAPE` and `META_STRATEGY` into both its manifest digest and strategy descriptor. `HarnessResearchController` resolves those roles without containing Direct/Ada/EvoX operator or strategy ids. Missing capabilities and multiple providers for the same capability fail closed; the router never silently substitutes a different action class. Cross-strategy handoff is also derived from the source and target capabilities rather than source-system names.

This is a composition contract, not package discovery or a plugin marketplace. `standard_research_plugins()` remains the static built-in catalog, and a Profile currently admits at most one provider for each routed capability unless a future, separately versioned selection policy is frozen. Because capability declarations enter manifest digests, this closure creates new Profile identities; earlier run manifests and receipts remain bound to their original code/manifest identities and are not rewritten.

This code defines the arms but does not yet seal a task wave or make model calls. In particular, the naive-parallel parent settlement and matched budget split remain responsibilities of the forthcoming frozen P2 protocol runner.

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
- all four P2 arm definitions, capability-aware subset routing, disabled naive handoff and matched reservation surfaces;
- create-once Profile-to-Run binding and fail-closed replay under code-bundle drift;
- Profile → Harness runtime → unified executor → evaluator/ledger settlement;
- core CLI and benchmark-package imports do not load historical runners;
- historical CLI commands remain reachable through lazy compatibility routing.

These tests establish only execution mechanics and dependency isolation. They do not establish official Ada/EvoX parity, static composition value, adaptive value, generalization or superiority.

## Mechanism parity audit

The source-bound [`ADA_EVOX_MECHANISM_PARITY_AUDIT.md`](ADA_EVOX_MECHANISM_PARITY_AUDIT.md) confirms that the current Ada/EvoX plugins are mechanism-role proxies, not mechanism-complete ports. Ada currently retains lineage-local refinement but not the official hierarchical adaptive loop. EvoX currently retains a stagnation-triggered structural solution rewrite but not the official evolution of parent-selection and variation strategy.

P2 sealing is paused for a bounded, zero-model parity closure: trajectory-conditioned Ada local adaptation and a typed same-run EvoX strategy deployment/switch/rollback slice. The audit explicitly excludes wholesale runtime import, private archives or evaluators, unrestricted strategy-code generation, cross-task memory and fresh assets.

Both bounded slices are implemented. [`ADA_TRAJECTORY_PARITY_SLICE.md`](ADA_TRAJECTORY_PARITY_SLICE.md) records receipt-bound trajectory control and generation-context transmission. [`EVOX_STRATEGY_PARITY_SLICE.md`](EVOX_STRATEGY_PARITY_SLICE.md) records typed same-run strategy deployment, observation, scoring and retain/switch/rollback, including changes to parent selection and variation guidance. These zero-model tests establish mechanics/transmission only; they do not establish candidate behavior or value. No P2 Profile is scientifically unlocked until the comparison arms are revised, re-digested and pass the common fairness gate.

## Remaining deliberate legacy boundary

`SearchLoopRunner`, `DeterministicActionController`, ledger projector and unified executor remain stable Kernel/Runtime primitives. Historical protocols can still instantiate them directly to preserve replay behavior. New search work must enter through `HarnessSearchRuntime`; direct construction is compatibility-only and must not become a new default path.

Parent/Novelty/CMI and old protocol runners remain frozen regression/evidence assets. Moving them to new paths would change historical import bindings without adding scientific value, so V1 isolates them from default imports instead of deleting or rewriting them.

## Next gate

Next revise and re-digest four explicit comparison Profiles: `neither`, `Ada-only`, `EvoX-only` and shared `Ada+EvoX`. They must pass a zero-model check for the same executor, evaluator, ledger, total budget, reservation surface and resource envelope before sealing the matched-resource P2 protocol. That later protocol must freeze exact task instances, any child budget split and settlement, provider executable/version/settings, model calls, evaluator-call ceilings, wall/resource envelopes, statistics, winner rule and stop conditions. V1 mechanics do not authorize broader adaptive routing, cross-task memory, Harness evolution, fresh assets or stronger claims.
