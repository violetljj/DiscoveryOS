# MVP0-BR — Budget / Action Reachability Repair

## Final verdict

```text
CONTROLLER_BUDGET_REACHABILITY_REPAIRED
```

The scientific state remains frozen and unchanged:

```text
SEARCH_VALUE_MVP0_FAIL
DISCOVERYOS_SEARCH_VALUE_NOT_YET_ESTABLISHED
```

MVP0-BR is a deterministic mechanics admission. It makes no Search-Value, algorithm-superiority, product, safety, or final-blind claim. It used zero new LLM generations and consumed no fresh task.

## Frozen anchors and immutability

- Mechanics commit: `ec301a18f6543e8c07d62b49bc8cf784f90b137d`
- MVP-0 protocol commit: `c6e77681158fc9bb33e9a526f4d74d8c50cc1548`
- Manifest digest: `0928e6f243d91399ae8002456754850b32091adfe72af55da46df58c52d6c7c3`
- Frozen manifest file SHA-256 before/after BR: `9d8389050fe86dbce0725c1692bbf1910b1a6f5c8438c20caaf6ec3e5768aa0a`
- Frozen report file SHA-256 before/after BR: `65165720000269e2abfb07d0e5d220c928f61ef865d320f394d6aa223b295a15`
- Full frozen workspace tree digest before/after read-only autopsy (1,004 files, 3,717,295 bytes): `52ceec6b69e77c46a9d582ff86f9c98428b792a18fd4423d7c6616f95a93d276`

The complete 17-action reconstruction, with all requested per-action fields, is in [MVP0_BR_FROZEN_AUTOPSY.json](evidence/MVP0_BR_FROZEN_AUTOPSY.json). It is derived only from the frozen manifest, report, eight DiscoveryOS ledgers, generation records, evaluation receipts, and anytime traces.

## 1. Frozen MVP-0 autopsy

The eight DiscoveryOS arms settled 17 actions: 16 Local Patch actions and one Promote Fidelity action. Structural Escape and Replicate were never reached.

| Action index | Attempted | Started | Completed | Candidate emitted | Valid | Admitted | Incumbent improved | Tokens | Wall seconds |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 152,444 | 293.686 |
| 1 | 8 | 8 | 2 | 2 | 2 | 2 | 0 | 166,645 | 461.405 |
| 2 | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0.948 |

All six failed index-1 actions had the exact frozen signature `GENERATION_BUDGET_EXCEEDED:tokens`. Their generation usages were 20,363–22,005 tokens against a 20,000-token slice. This is a budget-estimation failure after generation start, not evidence that six candidate artifacts were intrinsically invalid. The frozen MVP-0 accounting is not rewritten: its reported 35.3% invalid rate remains authoritative for MVP-0.

## 2. DOS_FIRST_LOCAL_ONLY counterfactual

`DOS_FIRST_LOCAL_ONLY` truncates each frozen arm immediately after its first Local Patch and recomputes the same metrics without any model call.

| Metric | FULL_DOS | DOS_FIRST_LOCAL_ONLY | Difference |
|---|---:|---:|---:|
| Median final improvement | 0.469133415 | 0.469133415 | 0 |
| Median Anytime AUC | 0.318119985 | 0.318119985 | 0 |
| Total tokens | 319,089 | 152,444 | -166,645 |
| Summed action wall | 756.039s | 293.686s | -462.353s |
| Frozen-style invalid rate | 35.3% | 0.0% | -35.3 pp |

Every arm had the same final improvement after the first Local as at FULL_DOS. Every arm also had the same Anytime AUC within the frozen report's rounding precision. Therefore the observed marginal Search-Value after the first Local was zero, while resource cost was strictly positive.

## 3. Action marginal value

Action index 0 contributed the entire observed aggregate final-improvement sum (`3.209744278`) and aggregate Anytime-AUC sum (`2.19840860`). Index 1 contributed zero to both despite consuming more tokens and wall time than index 0. Index 2 was a zero-token promotion evaluation and did not improve the incumbent.

This is a frozen-trace diagnosis, not a rule that a second Local can never be useful on another task.

## 4. Budget-flow diagnosis

The frozen arm envelope was 60,000 tokens, 300 CPU-seconds, and 1,200 wall-seconds. The old controller nevertheless passed a 20,000-token action floor to each generative operator as if it were an isolated total generation budget.

The observed flow was:

```text
60,000 arm tokens
-> first Local generation: 18,500–19,784
-> first evaluation: 0 LLM tokens, 0.125–0.219 CPU-s, 0.78–1.01 wall-s
-> remaining tokens: 40,216–41,500
-> second Local selected with a new isolated 20,000-token ceiling
-> six actual generations: 20,363–22,005
-> post-generation reconciliation failure
```

The failures separate into five mechanics categories:

1. **Budget allocation failure:** action-local slices were not expressed as components of one replayable arm-level reservation.
2. **Budget estimation failure:** the 20k floor was below the frozen second-call p90/max of 22,005 tokens.
3. **Generation overshoot:** six generations completed above their local slice and were discarded only at reconciliation.
4. **Evaluation reserve failure:** controller preflight did not separately hold the frozen rung evaluation request or settlement capacity.
5. **Controller action-selection failure:** a second Local could be selected without preserving a complete downstream Structural action.

## 5. Action reachability matrix

The repair rounds the frozen second-Local nearest-rank p90/max (`22,005`) deterministically to a 25k generation reserve. A complete G1 generative action reserves 25k tokens + 5 CPU-s + 331 wall-s, including the existing 5 CPU/30 wall evaluation rung and an explicit 1 wall-second settlement reserve. The total arm envelope remains exactly 60k/300/1,200.

| Action | Required state | Minimum predecessor | Complete start reserve | Downstream reserve | Frozen MVP-0 reachability | BR deterministic reachability |
|---|---|---|---|---|---|---|
| LOCAL_PATCH | active branch, Local capacity | none | 25k tokens, 5 CPU-s, 331 wall-s | one Structural reserve when Structural remains legal | reached, but six second calls were mis-sized | reachable |
| STRUCTURAL_ESCAPE | one budget-derived stagnant generation, lineage and failure evidence | one Local | 25k tokens, 5 CPU-s, 331 wall-s | none | dead in observed arms | reachable |
| REPLICATE | valid evidence, uncertainty/proximity, replicate count below 2 | one Local in admission fixture | 5 CPU-s, 31 wall-s | none | dead because frozen minimum was already 1 | reachable |
| PROMOTE_FIDELITY | promotion eligible, acceptable uncertainty, 2 replicates | one Local in admission fixture | 10 CPU-s, 61 wall-s | none | reached once | reachable |
| STOP | no legal affordable action or exhausted frontier | none | zero | none | reachable | reachable |

The old frozen trace has six eligible-but-unexecutable and six selected-but-actually-unaffordable second Local actions when reconstructed against observed minimum completion cost. The repaired deterministic admission has zero selected-but-unaffordable actions.

The stagnation horizon is no longer chosen by intuition. It is derived dimension-by-dimension as:

```text
min floor((arm_budget - structural_complete_cost) / local_complete_cost) = 1
```

The token dimension is binding: `(60,000 - 25,000) / 25,000 = 1`. Thus one complete Local plus one complete Structural fits; two Locals plus Structural do not. No arm ceiling was increased.

## 6. Root cause

Three independent conditions combined:

- `resource_floor` conflated minimum action admission, generation ceiling, and complete action cost.
- `stagnation_generations=2` combined with a two-Local family limit. Because all first Locals improved, a non-improving second Local could only produce stagnation count 1 just as Local capacity reached zero. Structural was therefore unreachable even before considering its resource cost.
- `minimum_replicates=1` combined with one baseline evaluation, while eligibility required `replicate_count < minimum_replicates`. Replicate was unreachable by construction.

Conflict Coloring losses were not caused by incumbent regression. In both losses, the first valid DiscoveryOS candidate remained the final DiscoveryOS incumbent; it simply scored below Vanilla. The old scientific losses remain unchanged.

## 7. Code changes

- Action costs now expose generation, evaluation, settlement, and downstream reserves separately while retaining one complete-action floor.
- Decisions bind `budget_reserved`, `reserved_downstream_budget`, component reserves, preflight status, and any rejected action into their deterministic digest and replay comparison.
- An unaffordable proposed action becomes deterministic `STOP_BUDGET_INSUFFICIENT` with `ACTION_REJECTED_PREFLIGHT_BUDGET`; it is never emitted as an executable decision.
- Generative operators receive only their generation reserve. Evaluation and settlement capacity remain held in the arm decision.
- New event semantics record `ACTION_PLANNED`, `ACTION_REJECTED_PREFLIGHT_BUDGET`, `ACTION_STARTED`, `ACTION_EXECUTION_FAILED`, `CANDIDATE_EMITTED`, `CANDIDATE_INVALID`, and `CANDIDATE_VALID` without changing old events.
- Anytime settlement rejects any regression of a previously observed valid incumbent.
- `mvp0_br_controller_config()` is a new protocol version. The frozen `mvp0_controller_config()` and all old artifacts remain untouched.

## 8. Deterministic mechanics admission

The machine-readable admission receipt is [MVP0_BR_MECHANICS_ADMISSION.json](evidence/MVP0_BR_MECHANICS_ADMISSION.json). The fixtures reach and replay all required paths:

```text
LOCAL_PATCH -> STOP
LOCAL_PATCH -> STRUCTURAL_ESCAPE
LOCAL_PATCH -> REPLICATE
LOCAL_PATCH -> PROMOTE_FIDELITY
LOCAL_PATCH -> LOCAL_PATCH (only without a required Structural reserve)
```

They also prove:

- `selected_but_unaffordable_action_count == 0`;
- budget shortage returns STOP before executor entry and emits no candidate;
- decision replay is deterministic;
- reservation, actual usage, reconciliation, downstream reserve, and remaining budget are present in the settled trace;
- nominal fake-provider mechanics contain zero `GENERATION_BUDGET_EXCEEDED` events;
- worse, invalid, rejected, evaluation-failed, and Structural-failed successors cannot settle a regressed incumbent.

## 9. Test results

Focused mechanics admission passed, and the final complete repository suite passed `48/48` tests in 77.857 seconds. `git diff --check` and Python compile checks also passed. No Search-Value benchmark or fresh generation was run.

## 10. BR PASS checklist

| Condition | Result |
|---|---|
| selected-but-unaffordable is zero | PASS |
| nominal deterministic `GENERATION_BUDGET_EXCEEDED` is zero | PASS |
| every existing action is reachable in a legal frozen fixture | PASS |
| insufficient budget deterministically stops without a candidate | PASS |
| total arm envelope is unchanged | PASS |
| decision replay is deterministic | PASS |
| reservation/reconciliation is replayable | PASS |
| incumbent monotonicity scenarios pass | PASS |
| old MVP-0 manifest/report/receipts are unchanged | PASS |
| complete test suite | PASS |

No Strategy Integration mechanism was started. This round stops at Budget / Action Reachability Repair.
