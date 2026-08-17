# CMI-R2 Bounded Real Diagnosis

## Protocol status

```text
CMI_R2_REAL_DIAGNOSIS_COMPLETE
CMI_R2_FUNCTIONAL_BASIN_LOCK_SUPPORTED_ON_TWO_DEV_STATES
CMI_R2_DEVELOPMENT_MECHANISM_BRIEF_AUTHORIZED
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

## Result

Manifest digest is `e7729e2d186ce60acd00bf56f61b783c4d8025a8c2babe67c9824da9226d2a0f`; the zero-model controls record SHA-256 is `7add4d0ec5aa490544b9a1e948b13b420a281b654a6599355b27018ae7ed7dad`; final report SHA-256 is `0dabc1d1fb9850266e5cbdb58a5868bffc45144c408d2d269df17504e47d3dfb`.

All 6 calls were evaluable, valid, and below the inherited ceiling. Total usage was `116,729` tokens. Evaluator recovery was `1.0`, valid-source rate was `1.0`, and median within-state functional distance was `0.0`. All three independently generated sources in each state had distinct source SHA-256 values but exactly identical frozen functional signatures and evaluator scores within that state.

The frozen diagnosis therefore refuted `H3_EVALUATOR_INSENSITIVITY` and `H4_IMPLEMENTATION_BOTTLENECK`, supported `H5_STRUCTURAL_BASIN_LOCK`, and terminated at `MECHANISM_BRIEF_ALLOWED`. This is evidence for functional basin lock on these two development states under the frozen Direct generation contract—not a universal representation-ceiling claim and not evidence that any particular escape Operator will work.
