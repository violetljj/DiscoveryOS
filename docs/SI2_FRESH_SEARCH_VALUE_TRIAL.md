# SI-2: Fresh Search-Value Trial

## Stage status and question

```text
SI2_PROTOCOL_DESIGN_OPEN
SI2_NOT_SEALED
SI2_EXECUTION_NOT_AUTHORIZED
DISCOVERYOS_SEARCH_VALUE_NOT_YET_ESTABLISHED
```

SI-2 is the first stage whose primary purpose is scientific search-value evidence rather than mechanism diagnosis. It asks one question:

> On never-consumed research tasks, does the current complete DiscoveryOS search stack find better candidates than strong simpler baselines under the same frozen model, evaluator contract, starting state, and resource envelope?

The stage transition closes SI-1R. The `719,922` generation tokens from its consumed-task pilot established only that parent selection changes real decisions and that novelty can avoid duplicate evaluation without extra generation. They do not enter SI-2 evidence, select SI-2 tasks, or raise the claim ceiling.

This document is a stage charter, not a sealed experiment manifest. No task suite, external challenger/version, provider snapshot, replicate count, budget, statistical threshold, or execution order is frozen yet. No candidate-model call or task outcome may be inspected until those fields and the implementation digests are sealed create-once.

## 1. Fixed comparison shape

SI-2 has four system-level arms. Parent and novelty are not separate confirmatory arms.

| Arm | Role | Boundary |
|---|---|---|
| `CORE` | Minimal unified search-kernel control | Frozen minimal operator/controller surface; no SI-1 parent or novelty mechanisms |
| `CURRENT_DISCOVERYOS` | SI-1R-era complete internal stack | Exact committed stack sealed before task outcomes; no mid-trial mechanism changes |
| `VANILLA_STRONG_AGENT` | Strong non-OS agent baseline | Same model/settings/tools and task context, with a frozen bounded direct-agent workflow but no DiscoveryOS research state |
| `EXTERNAL_STRONG_BASELINE` | Existing algorithm-discovery comparator | Exactly one named official implementation/version in isolated Benchmark Mode; no access to or writes into DiscoveryOS internal state |

The external arm is not chosen post hoc. Before sealing, its official source revision, license, runnable adapter, model compatibility, prompt/configuration, resource accounting, and evaluator handoff must pass a mechanics-only preflight that reveals no SI-2 task outcomes. If no challenger can meet the common contract without semantic distortion, SI-2 records `EXTERNAL_BASELINE_NOT_EVALUABLE` and does not replace it after seeing results. That condition does not invalidate the three internal arms, but it prevents an external-competitiveness claim.

## 2. Freshness and task cohorts

SI-2 uses two non-overlapping cohorts:

1. **Fresh discovery cohort**: used for the four-arm matched-resource comparison and winner freeze.
2. **Confirmation cohort**: never available to Discovery Mode; opened only after the system winner and analysis code are frozen.

Before any candidate-model call, the manifest must bind every task's provenance, source/license, task-family identity, mutable targets, baseline artifact, evaluator/data digests, oracle or scoring contract, difficulty/headroom admission, and cohort role. It must demonstrate zero overlap with every consumed MVP-0, BR-A, SI-1, and SI-1R task by task id, source digest, target artifact, and generated-instance lineage. Broader semantic contamination that cannot be ruled out must be disclosed; “fresh” means unconsumed by this project and unavailable to the trial arms before seal, not guaranteed absence from model pretraining.

Task admission and exclusion are outcome-blind. A task may be excluded after sealing only for a preregistered protocol-validity reason. Exclusions, `INVALID`, mechanics failures, hard-constraint failures, scientific losses, and `NOT_EVALUABLE` remain separate counts.

## 3. Matched-resource contract

For each task, replicate, and arm, freeze the same:

```text
task statement and allowed context
starting repository/candidate and tool permissions
candidate model, reasoning settings, provider and CLI version
evaluator, development data, fidelity and hard constraints
input+output token ceiling
generation wall ceiling and total arm wall ceiling
CPU/GPU/device ceilings where material
cache accounting and network policy
replicate seeds and execution-order randomization
```

Unused resources do not transfer between tasks, replicates, or arms. Cache tokens, evaluator calls, generation tokens, generation wall, total wall, CPU/GPU/device use, failures, and reservations are reported separately. Concurrency may improve throughput but must not change per-arm ceilings, task semantics, seeds, or evaluator results. Each arm gets an isolated ledger/workspace and immutable receipts.

The primary score surface is token-matched. Wall and evaluator efficiency are secondary evidence and cannot compensate for losing the primary search-value gate.

## 4. Frozen metrics

### Primary

- **Matched-token final best**: best valid development score reached by the common token checkpoint/ceiling, paired by task and replicate.
- **Anytime AUC**: area under best-so-far improvement versus normalized consumed generation-token budget, with checkpoints and integration rule frozen before execution.
- **Fresh-task win rate**: paired task-level win/tie/loss from the frozen aggregation rule; replicate aggregation and tie tolerance must be fixed before seal.

### Secondary

- evaluator calls and avoided evaluations;
- input/output/cache and total generation tokens;
- generation wall, evaluator wall, total wall, and time/tokens to best;
- valid candidate rate and mechanics-failure rate;
- structural diversity and basin diversity, only if their identity/equivalence definitions are deterministic and frozen before execution.

Parent entropy, parent exposure, novelty rejection counts, operator mix, and similar mechanism traces are diagnostics only. They cannot rescue a failed primary result or trigger an in-trial policy change.

## 5. Verdict separation

The sealed manifest must preregister exact task count, replicate count, tie tolerance, uncertainty interval, multiplicity handling, minimum evaluable coverage, and pass/fail rule before outcomes are visible. The rule must preserve these distinct claims:

- `DISCOVERYOS_SEARCH_VALUE_ESTABLISHED_ON_SI2_DISTRIBUTION` requires `CURRENT_DISCOVERYOS` to pass the frozen primary gate against both `CORE` and `VANILLA_STRONG_AGENT` under matched resources.
- `DISCOVERYOS_EXTERNAL_COMPETITIVENESS_ESTABLISHED_ON_SI2_DISTRIBUTION` is a separate verdict requiring the frozen comparison against `EXTERNAL_STRONG_BASELINE`; it is not implied by beating the internal baselines.
- Efficiency or diversity improvements without the primary gate produce an efficiency/development finding only; they do not establish search value.
- Protocol invalidity, insufficient evaluable coverage, or broken resource matching produces `SI2_NOT_EVALUABLE`, not a scientific loss.
- Failure of the frozen scientific gate produces `SI2_SEARCH_VALUE_NOT_ESTABLISHED`, not a claim that all future DiscoveryOS designs are ineffective.

Until the manifest is sealed and the trial passes, the repository-wide verdict remains:

```text
DISCOVERYOS_SEARCH_VALUE_NOT_YET_ESTABLISHED
```

## 6. Winner freeze and confirmation

The fresh discovery cohort determines one create-once system winner using the preregistered rule. Only after the winner, code revision, configuration, candidate outputs, analysis code, and confirmation gate are frozen may Certification Mode obtain capability for the separate confirmation cohort.

Confirmation data never changes the winner, controller, prompts, thresholds, task exclusions, or system configuration. A failed confirmation remains a failed confirmation; it does not reopen SI-2 development or authorize choosing the runner-up. Passing confirmation supports only the frozen task-distribution and claim ceiling. It does not imply product, safety, general algorithmic superiority, or production-ready blind isolation.

## 7. Development freeze and blockers

From this stage transition until the SI-2 result is closed:

> Do not add or tune search mechanisms, parent policies, novelty thresholds, operators, prompts, or controller heuristics.

The only exception is a blocker that would make the trial invalid or non-executable, such as resource-accounting mismatch, evaluator leakage, task contamination, adapter failure, nondeterministic aggregation, or a mechanics defect that prevents an arm from implementing its frozen semantics. A blocker fix must:

1. be documented before any affected outcome is used;
2. create a new protocol version and experiment root if the sealed surface changes;
3. invalidate, rather than mix, affected partial results;
4. receive mechanics-only regression coverage without opening fresh or confirmation outcomes;
5. not improve search policy under the label of infrastructure repair.

## 8. Seal prerequisites

SI-2 execution remains closed until one create-once manifest and its validator bind at least:

- fresh discovery and confirmation rosters plus contamination receipts;
- exact four arm definitions and implementation/source digests;
- external baseline identity and mechanics-preflight verdict;
- model/provider/tool versions, prompts/settings, network/tool policy, and environment fingerprint;
- task/replicate counts, seeds, schedule, budgets, reservations, and concurrency policy;
- evaluator/data/fidelity/hard-constraint bindings;
- metric formulas, checkpoints, tie rules, missingness/exclusion rules, uncertainty and multiplicity treatment;
- search-value, external-competitiveness, and confirmation gates;
- claim ceilings and explicit final-blind access count of zero before winner freeze;
- `model_calls_before_seal = 0` and a clean committed experiment revision.

Only after the validator passes may the status move from `SI2_PROTOCOL_DESIGN_OPEN` to `SI2_SEALED_PRE_MODEL`.
