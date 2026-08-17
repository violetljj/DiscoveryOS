# CMI-R6 Consumed Distribution Replication Admission

## Protocol status

```text
CMI_R6_PROTOCOL_IMPLEMENTED
CMI_R6_NOT_YET_EXECUTED
ZERO_FRESH_TASKS
```

CMI-R6 is the final low-cost admission gate before any fresh CMI causal validation can be proposed. It freezes the exact R5 escape and local-control implementation hashes and evaluates every compatible consumed SI-2 state: four capacitated-assignment states and four weighted-coverage states across the discovery and confirmation cohorts. Balanced Cut is excluded by the frozen compatibility rule because the R5 Operator has no implementation for that category.

No state is selected using its prospective R6 utility. Each state receives the same incumbent, one deterministic control invocation, one deterministic treatment invocation, frozen evaluator and newly frozen functional-probe seeds. Functional distance remains a manipulation check; state-level utility sign, family-level medians, validity, replacement, breakthrough, and evaluator-cost penalty determine admission.

This is not blind, mechanism-formation-independent replication. The exact SI-2 state identities and evaluator seeds were not used in CMI-R3/R4/R5, but the Assignment/Coverage task families and SI-2 intermediate heuristic evidence were available before R6 and are related to the frozen Operator decompositions. Using the complete compatible population prevents state cherry-picking; it does not remove this family-level contamination. The result is therefore consumed-distribution robustness evidence only.

The primary gate requires all eight states to be technically evaluable, zero control escapes, at least seven treatment escapes, at least seven positive utility effects beyond state resolution, no negative effect beyond resolution, positive median utility and AUC effects in both task categories, non-worse validity and breakthrough, strictly higher replacement rate, aggregate treatment/control evaluator runtime no greater than `2.0x`, and no state runtime ratio above `3.0x`.

Passing can emit `CMI_FRESH_CAUSAL_VALIDATION_ADMISSION_READY`, which authorizes only separate preregistration of a very small fresh causal protocol. It does not execute fresh tasks or establish probability, significance, cross-category generalization, fresh search value, superiority, or production readiness.
