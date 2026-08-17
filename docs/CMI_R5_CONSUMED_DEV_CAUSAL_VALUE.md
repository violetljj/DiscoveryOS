# CMI-R5 Consumed Development Causal Value

## Protocol status

```text
CMI_R5_PROTOCOL_IMPLEMENTED
CMI_R5_NOT_YET_EXECUTED
ZERO_FRESH_TASKS
```

CMI-R5 asks whether the already-confirmed functional-basin-escape intervention improves utility relative to a source-local behavior-preserving intervention. It reuses exactly the two consumed CMI-R4 development states and opens no fresh search-value task.

Each pair freezes the same state, incumbent parent, one deterministic Operator invocation, zero model calls, zero tokens, functional probe, evaluator, timeout, and execution environment. CONTROL performs a source-local refactor that preserves the incumbent policy. TREATMENT applies the CMI-R4 functional-basin-escape Operator. Neither arm receives the positive-control source, reference score, evaluator output, or the other branch output.

Functional distance is only a manipulation check. The primary endpoints are final utility, two-allocation anytime AUC, incumbent replacement, breakthrough, validity, and cost. Breakthrough is frozen as reaching the reference score minus the state score resolution. A positive verdict requires treatment escape on both states, control escape on neither, utility delta above the state score resolution and AUC delta above half that resolution on both states, non-worse validity and breakthrough, strictly higher replacement rate, and matched zero-model/zero-token resources.

There is one deterministic pair per consumed state. Therefore R5 cannot estimate a general escape probability, sampling variance, or statistical significance. Even a positive result can support only `CMI_ESCAPE_CAUSAL_VALUE_ON_TWO_CONSUMED_DEV_STATES_ONLY`; it cannot establish fresh search value, superiority, or production readiness.
