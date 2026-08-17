# CMI-R6 Consumed Distribution Replication Admission

## Protocol status

```text
CMI_R6_PROTOCOL_IMPLEMENTED
CMI_R6_CONSUMED_DISTRIBUTION_REPLICATION_PASSED
CMI_FRESH_CAUSAL_VALIDATION_ADMISSION_READY
ZERO_FRESH_TASKS
```

CMI-R6 is the final low-cost admission gate before any fresh CMI causal validation can be proposed. It freezes the exact R5 escape and local-control implementation hashes and evaluates every compatible consumed SI-2 state: four capacitated-assignment states and four weighted-coverage states across the discovery and confirmation cohorts. Balanced Cut is excluded by the frozen compatibility rule because the R5 Operator has no implementation for that category.

No state is selected using its prospective R6 utility. Each state receives the same incumbent, one deterministic control invocation, one deterministic treatment invocation, frozen evaluator and newly frozen functional-probe seeds. Functional distance remains a manipulation check; state-level utility sign, family-level medians, validity, replacement, breakthrough, and evaluator-cost penalty determine admission.

This is not blind, mechanism-formation-independent replication. The exact SI-2 state identities and evaluator seeds were not used in CMI-R3/R4/R5, but the Assignment/Coverage task families and SI-2 intermediate heuristic evidence were available before R6 and are related to the frozen Operator decompositions. Using the complete compatible population prevents state cherry-picking; it does not remove this family-level contamination. The result is therefore consumed-distribution robustness evidence only.

The primary gate requires all eight states to be technically evaluable, zero control escapes, at least seven treatment escapes, at least seven positive utility effects beyond state resolution, no negative effect beyond resolution, positive median utility and AUC effects in both task categories, non-worse validity and breakthrough, strictly higher replacement rate, aggregate treatment/control evaluator runtime no greater than `2.0x`, and no state runtime ratio above `3.0x`.

Passing can emit `CMI_FRESH_CAUSAL_VALIDATION_ADMISSION_READY`, which authorizes only separate preregistration of a very small fresh causal protocol. It does not execute fresh tasks or establish probability, significance, cross-category generalization, fresh search value, superiority, or production readiness.

## Result

R6 was sealed on implementation commit `cd8e7f2`. The create-once manifest digest is `c4b0844fc3beae43f624194318611b3899865abe1199ad705e978294ff2ea876`; the result report SHA-256 is `95213c5bb419cd995d2ddc588cc0d394698043da2a4c3fdceafcb10dcbae9dfe`.

All eight states were technically evaluable, passed the manipulation check, escaped under treatment, improved utility beyond their state resolution, and replaced the incumbent. Control escaped and replaced on zero states. There were `8` positive utility signs, `0` negative signs, and `0` ties within resolution. Valid-candidate rate remained `1.0` in both arms; breakthrough rate changed from `0.0` to `0.375`.

Coverage median final-utility delta was `0.08027348` and median AUC delta was `0.04013674`. Assignment median final-utility delta was `0.18481032` and median AUC delta was `0.09240516`. Aggregate treatment/control evaluator runtime ratio was `0.99956x`; the maximum state ratio was `1.25330x`, below the frozen `2.0x` / `3.0x` guardrails.

All 13 replication checks passed. Usage was 8 matched control/treatment Operator pairs, 32 evaluator calls, 32 functional-probe calls, zero model calls, zero tokens, and zero fresh tasks. The verdict is `CMI_R6_CONSUMED_DISTRIBUTION_REPLICATION_PASSED`, and `CMI_FRESH_CAUSAL_VALIDATION_ADMISSION_READY` authorizes only separate preregistration. Fresh execution remains unauthorized.

The contamination disclosure remains controlling: this is robust sign consistency across the complete compatible consumed SI-2 population, not blind independent replication. It does not establish probability, significance, cross-task-family generalization, search value, or superiority.
