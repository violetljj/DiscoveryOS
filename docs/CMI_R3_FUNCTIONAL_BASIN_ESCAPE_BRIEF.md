# CMI-R3 Functional Basin Escape Mechanism Brief

## Protocol status

```text
CMI_R3_PROTOCOL_IMPLEMENTED
CMI_R3_FUNCTIONAL_BASIN_ESCAPE_BRIEF_ADMITTED
NO_ESCAPE_OPERATOR_IMPLEMENTED
NO_OPERATOR_VALUE_TRIAL_AUTHORIZED
```

CMI-R3 is a zero-model admission gate for one development Mechanism Brief. It binds the immutable CMI-R2 report and controls; it does not rerun the consumed R2 states, implement an Operator, or open search-value budget.

The authorized causal target is `functional_output_basin`. Applicability requires two independent states, sensitive frozen evaluators, high implementation validity, remaining evaluator headroom, and low within-state functional diversity. The required intervention fingerprint is a valid candidate whose state-local functional distance from the incumbent envelope is greater than `0.10`; different source text alone is explicitly insufficient.

The frozen causal path is:

```text
functional output basin escape
-> evaluator-relevant behavior change
-> replacement opportunity
-> utility or AUC difference
```

Null and positive controls are receipt-bound: same-source distance must remain `0`, while the frozen alternative implementation must exceed `0.10` on every bound state. Syntax repair, generic critique/reflection, source-only diversity, evaluator changes, reference leakage, and prompt/token differences are forbidden substitutes for the target mechanism.

Passing this gate can authorize only a separate create-once Operator protocol on new development states, with the intervention fingerprint checked before any utility comparison. It cannot establish that an escape Operator exists or has causal value.

## Result

The create-once manifest digest is `f69966c6a3f7530eb29556c4148dc0bfcc16ae6a441ad5bc0cefee090dafa595`; the admission report SHA-256 is `903837b1fd3de85ed51f12be45c65c9fc5e89933acf37ab39f2895c16bf12acf`.

All 12 frozen checks passed. The bound R2 receipts establish two independent states, evaluator sensitivity `1.0`, valid-source rate `1.0`, within-state functional distance `0`, state-local same-source distance `0`, positive-control distances above `0.10`, and positive reference headroom. The Brief also explicitly requires a non-source-only intervention, a causal path reaching utility/AUC, and fail-closed handling of leakage, invalidity, resource excess, one-state effects, and behavior-without-utility effects.

Usage remained exactly zero model calls, zero evaluator calls, and zero fresh tasks. The claim ceiling is `DEVELOPMENT_MECHANISM_BRIEF_ONLY`; `operator_implementation_authorized`, `operator_value_trial_authorized`, and `fresh_search_value_budget_authorized` are all `false`.
