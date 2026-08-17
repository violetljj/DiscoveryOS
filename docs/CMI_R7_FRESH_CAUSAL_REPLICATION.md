# CMI-R7 Fresh Causal Replication

## Protocol status

```text
CMI_R7_PROTOCOL_IMPLEMENTED
CMI_R7_FRESH_SHARD_NOT_YET_SEALED
CMI_R7_FRESH_EXECUTION_NOT_YET_RUN
ZERO_R7_FRESH_STATES_CONSUMED
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
