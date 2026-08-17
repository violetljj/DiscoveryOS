# CMI-R5 Consumed Development Causal Value

## Protocol status

```text
CMI_R5_PROTOCOL_IMPLEMENTED
CMI_R5_CAUSAL_VALUE_DETECTED_ON_TWO_CONSUMED_DEV_STATES
ZERO_FRESH_TASKS
```

CMI-R5 asks whether the already-confirmed functional-basin-escape intervention improves utility relative to a source-local behavior-preserving intervention. It reuses exactly the two consumed CMI-R4 development states and opens no fresh search-value task.

Each pair freezes the same state, incumbent parent, one deterministic Operator invocation, zero model calls, zero tokens, functional probe, evaluator, timeout, and execution environment. CONTROL performs a source-local refactor that preserves the incumbent policy. TREATMENT applies the CMI-R4 functional-basin-escape Operator. Neither arm receives the positive-control source, reference score, evaluator output, or the other branch output.

Functional distance is only a manipulation check. The primary endpoints are final utility, two-allocation anytime AUC, incumbent replacement, breakthrough, validity, and cost. Breakthrough is frozen as reaching the reference score minus the state score resolution. A positive verdict requires treatment escape on both states, control escape on neither, utility delta above the state score resolution and AUC delta above half that resolution on both states, non-worse validity and breakthrough, strictly higher replacement rate, and matched zero-model/zero-token resources.

There is one deterministic pair per consumed state. Therefore R5 cannot estimate a general escape probability, sampling variance, or statistical significance. Even a positive result can support only `CMI_ESCAPE_CAUSAL_VALUE_ON_TWO_CONSUMED_DEV_STATES_ONLY`; it cannot establish fresh search value, superiority, or production readiness.

## Result

R5 was sealed on implementation commit `4465f0e`. The create-once manifest digest is `09260d9c235a22c4a6a348021a834079b9cbb742c040be9af9549d1b0d28ba5b`; the result report SHA-256 is `6457625fcf02d9d720a143f62dbf10927adce445863eca8b7b08259070be7b0d`.

Both pairs were evaluable and all eight predeclared gates passed. Assignment final utility increased from `0.34062651` to `0.54166344` (`+0.20103693`) and two-allocation AUC increased by `0.10051846`. Coverage final utility increased from `0.89600231` to `0.99369163` (`+0.09768933`) and AUC increased by `0.04884466`.

Across the two consumed states, functional escape rate changed from `0.0` to `1.0`, replacement rate from `0.0` to `1.0`, breakthrough rate from `0.0` to `0.5`, and valid-candidate rate remained `1.0` in both arms. Mean final utility changed from `0.61831441` to `0.76767753`; mean AUC changed from `0.61831441` to `0.69299597`.

Both arms used two deterministic Operator invocations, zero model calls, and zero tokens. Treatment evaluator wall time totaled `1.11799s` versus `0.73911s` for control, about `1.51x`; absolute Operator time was below one millisecond in both arms. This cost observation is descriptive and is not a production efficiency claim.

The verdict is `CMI_R5_CAUSAL_VALUE_DETECTED_ON_TWO_CONSUMED_DEV_STATES`. It establishes a paired causal-value positive only for this deterministic escape Operator against this behavior-preserving local control on the two consumed states. It does not estimate probability or significance, establish general CMI value or fresh search value, or authorize fresh budget.
