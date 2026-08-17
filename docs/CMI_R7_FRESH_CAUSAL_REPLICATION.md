# CMI-R7 Fresh Causal Replication

## Protocol status

```text
CMI_R7_PROTOCOL_IMPLEMENTED
CMI_R7_FRESH_CAUSAL_REPLICATION_PASSED
CMI_OPERATOR_ADMITTED_ON_FRESH_ASSIGNMENT_COVERAGE_STATES
CMI_ENABLED_SEARCH_VS_IDENTICAL_SEARCH_WITHOUT_CMI_PREREGISTRATION_AUTHORIZED
SIX_R7_FRESH_STATES_CONSUMED
```

CMI-R7 is the single small fresh-state validation authorized by CMI-R6. It does not add an R6.1/R6.2 consumed replay. It freezes six exact neighboring-hidden instances together: three Capacitated Assignment states and three Budgeted Weighted Coverage states. The exact evaluator seeds are derived without screening from a protocol salt, family, state index, and case index. There is no task replacement after sealing.

These are fresh **instances/states**, not fresh task families, a fresh distribution, or a fresh evaluator regime. Assignment and Coverage were visible during mechanism formation, while the six exact R7 instances and their heuristic outcomes were not used in CMI-R3 through R6. The maximum claim is therefore fresh-state causal replication within the same two frozen families and evaluator regime.

Each state receives one deterministic Local Behavior Control invocation and one deterministic frozen CMI treatment invocation. Both arms use the same incumbent, evaluator, resolution, functional probe rule, and zero-model/zero-token budget. The CMI implementation, Brief, thresholds, and Operator parameters remain hash-bound to R6; no post-fresh tuning is permitted.

## Endpoint and gate

There is one primary endpoint:

```text
treatment_score - control_score > state_score_resolution
```

Functional escape, replacement, anytime AUC, and breakthrough remain supporting mechanism metrics, not co-primary endpoints.

The frozen success gate is intentionally small:

- all `6/6` states are technically valid;
- all `6/6` paired utility deltas exceed their state resolution;
- there are zero negative utility deltas beyond resolution;
- Assignment and Coverage each contribute `3/3` positive primary endpoints;
- aggregate treatment/control evaluator runtime is at most `2.0x`, and no state exceeds `3.0x`.

The six instances form a protocol-specific SEALED shard over the two existing Benchmark Bank families. This does not generically upgrade either family or any external adapter to `ADMITTED`; access is limited to this create-once R7 claim-upgrade protocol after the R6 gate.

If the gate passes, R7 may emit both `CMI_R7_FRESH_CAUSAL_REPLICATION_PASSED` and `CMI_OPERATOR_ADMITTED_ON_FRESH_ASSIGNMENT_COVERAGE_STATES`. That narrow admission only authorizes separate preregistration of `CMI-enabled Search vs identical Search without CMI`. It does not establish complete-search value, probability, significance, cross-task-family generalization, superiority, certification, or production readiness.

## Commands

After the implementation commit is clean and immutable:

```powershell
$env:PYTHONPATH = "src"
python -m discoveryos cmi-r7-seal-fresh `
  --cmi-r6-report-sha256 95213c5bb419cd995d2ddc588cc0d394698043da2a4c3fdceafcb10dcbae9dfe
python -m discoveryos cmi-r7-run-fresh --manifest-digest <sealed-manifest-digest>
```

The second command consumes all six exact instances once. A completed result root cannot be rerun or backfilled.

## Result

R7 was sealed and executed on implementation commit `913ab5e`. The create-once manifest digest is `df1d2dd26730a5487e8e1e685339b7fd35430abd509cb4ea0433aa6458228209`; the result report SHA-256 is `3072e74c1a0114920f98c7930097a5488dd8a50763709a073513a1ef4dca763f`.

All six states were technically evaluable and passed the single primary endpoint. Assignment utility deltas were `+0.18698661`, `+0.18896208`, and `+0.19221718`; Coverage utility deltas were `+0.10059052`, `+0.09804796`, and `+0.09464326`. Thus the result is `6/6` resolution-exceeding positives, `0` negatives, `0` ties, with each family contributing `3/3` positives.

The supporting mechanism trace was also consistent: Control escaped and replaced on `0/6`; Treatment escaped and replaced on `6/6`. Breakthrough changed from `0/6` to `1/6`. Aggregate treatment/control evaluator runtime was `1.04189x`, and the maximum state ratio was `1.61769x`; both frozen cost guardrails passed. All six gate checks passed. Usage was 6 matched pairs, 24 evaluator calls, 24 functional-probe calls, zero model calls, and zero tokens.

The verdict is `CMI_R7_FRESH_CAUSAL_REPLICATION_PASSED`, with the narrow operator status `CMI_OPERATOR_ADMITTED_ON_FRESH_ASSIGNMENT_COVERAGE_STATES`. This completes the chain from two-state consumed detection, through eight-state consumed-distribution replication, to six-state exact-instance-fresh replication. It does not establish complete-search value. The next authorized scientific action is separate preregistration of CMI-enabled Search versus otherwise identical Search without CMI.
