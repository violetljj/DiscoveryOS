# CMI-R4 Functional Basin Escape Operator Mechanics

## Protocol status

```text
CMI_R4_PROTOCOL_IMPLEMENTED
CMI_R4_FUNCTIONAL_BASIN_ESCAPE_OPERATOR_MECHANICS_CONFIRMED_ON_TWO_DEV_STATES
NO_OPERATOR_CAUSAL_VALUE_TRIAL_AUTHORIZED
NO_FRESH_SEARCH_VALUE_BUDGET_AUTHORIZED
```

CMI-R4 asks exactly one mechanics question:

```text
Structured Functional-Basin-Escape Brief
-> Real Operator
-> Valid Runtime Candidate
-> State-local Functional Distance > 0.10
```

It does not ask whether the escaped candidate improves utility. It consumes no fresh search-value task, performs no model call, and does not compare utility or AUC.

## Frozen design

The create-once protocol must bind the admitted CMI-R3 manifest and report before observing Operator output. It freezes two new development states with task identities and probe seeds absent from shipped protocols: one capacitated-assignment state and one weighted-coverage state.

The development-only `FunctionalBasinEscapeOperator` must read the frozen causal target, required context, decomposition intervention, functional fingerprint, and source-only prohibition. Its runtime trace must prove those fields reached candidate generation. The Operator receives the incumbent and public task category only; it never receives the positive-control source or evaluator feedback.

Each state runs four isolated paths:

- baseline: frozen incumbent;
- null: the unchanged incumbent;
- positive: receipt-bound alternative implementation, isolated from the Operator;
- treatment: the actual Operator output.

The report records source distance, AST-node structural distance, state-local functional distance, and an independent descendant-behavior distance. Source or structural distance is diagnostic only. The treatment fingerprint passes only when the candidate is public-test valid and its functional distance from the incumbent is strictly greater than `0.10`.

## Frozen gates and outcomes

Both states must satisfy all of the following:

- null functional distance is exactly `0`;
- positive-control functional distance is greater than `0.10`;
- treatment is valid and has functional distance greater than `0.10`;
- the Brief-to-generation trace is complete;
- the positive control and evaluator feedback did not enter generation.

Outcomes remain distinct:

```text
CMI_R4_FUNCTIONAL_BASIN_ESCAPE_OPERATOR_MECHANICS_CONFIRMED_ON_TWO_DEV_STATES
CMI_R4_FUNCTIONAL_BASIN_ESCAPE_OPERATOR_MECHANICS_NOT_ESTABLISHED_ON_DEV
CMI_R4_NOT_EVALUABLE_CONTROL_OR_PROBE
```

Binding drift, authority mismatch, repository drift, or create-once violation fail closed before a scientific result is written. A passing result can establish only bounded two-state development mechanics. It cannot establish causal value, search value, superiority, or production readiness, and it does not by itself authorize a fresh budget.

## Result

The protocol was sealed against implementation commit `aed8261`. The create-once manifest digest is `05a7c426aeba12c7a13ca51485799a738835520ff094cf3ab46090d36c8397dc`; the result report SHA-256 is `6e284e4efce34d0ed4b461989be40a2aebaa5ad410e130da2a59642ed71c6e13`.

Both development states passed. Assignment treatment functional distance was `0.49382716` and independent descendant-behavior distance was `0.41975309`; coverage treatment functional distance was `0.30000000` and descendant-behavior distance was `0.31111111`. Both null distances were exactly `0`. Positive-control functional distances were `0.45679012` and `0.30000000`. Baseline, null, positive, and treatment candidates all passed their frozen public validity checks.

The runtime trace bound all five required Brief field paths to candidate generation. Both treatments differed from their isolated positive controls, and both traces recorded `positive_control_received=false` and `evaluator_feedback_received=false`.

Usage was exactly zero model calls, zero evaluator calls, zero fresh search-value tasks, and 24 local public/probe process calls across two newly consumed development states. The result establishes only that this deterministic minimal Operator transmits the admitted Brief into measurable functional basin escape on these two states. Causal value, general escape probability, utility/AUC improvement, search value, superiority, and production readiness remain unestablished.
