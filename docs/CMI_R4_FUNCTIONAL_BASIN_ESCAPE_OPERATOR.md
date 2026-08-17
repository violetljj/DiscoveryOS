# CMI-R4 Functional Basin Escape Operator Mechanics

## Protocol status

```text
CMI_R4_PROTOCOL_IMPLEMENTED
CMI_R4_NOT_YET_EXECUTED
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
