# CMI-R2 Bounded Real Diagnosis

## Protocol status

```text
CMI_R2_BOUNDED_REAL_DIAGNOSIS_PROTOCOL_IMPLEMENTED
CMI_R2_NOT_YET_SEALED
NO_REAL_BOTTLENECK_ESTABLISHED
NO_NEW_OPERATOR_AUTHORIZED
```

CMI-R2 is a two-state development diagnosis, not an Operator trial. It binds the passed CMI-R1 probe-calibration report and the existing `78,000` token/call resource authority, then permits exactly three independent Direct generations on each of two new dev episodes.

The new task IDs are `cmi_r2_assignment_diagnosis_beta` and `cmi_r2_coverage_diagnosis_beta`. Six evaluator seeds per state are new; functional probes retain the R1-calibrated measurement semantics.

## Frozen competing hypotheses

| Hypothesis | Measurement | Support | Refute |
|---|---|---:|---:|
| evaluator insensitivity | ranked-control recovery | `<= 0.50` | `>= 6/7` |
| implementation bottleneck | valid-source rate over 6 calls | `<= 0.50` | `>= 5/6` |
| functional basin lock | median within-state pair distance | `<= 0.10` | `>= 0.30` |

If fewer than three valid candidates exist in either state, functional diversity is `NOT_EVALUABLE`, never silently zero. A development Mechanism Brief is allowed only if exactly one hypothesis is supported and every competitor is refuted.

## Execution order and budget

```text
seal from clean commit
-> zero-model controls on both new states
-> at most 6 durable provider calls, max_workers <= 2
-> deterministic diagnosis
```

The claim ceiling is `TWO_STATE_DEVELOPMENT_DIAGNOSIS_ONLY`. R2 cannot authorize a new Operator or fresh search-value budget even if one bottleneck is uniquely supported.
