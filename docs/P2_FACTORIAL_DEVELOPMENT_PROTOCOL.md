# P2 Ada × EvoX Factorial Development Protocol

## Pre-seal status

```text
P2_FACTORIAL_PROTOCOL_IMPLEMENTED
P2_FACTORIAL_TASK_PREFLIGHT_PASS_ZERO_MODEL
P2_FACTORIAL_PROTOCOL_NOT_YET_SEALED_ON_CLEAN_COMMIT
P2_MODEL_CALLS_NOT_YET_AUTHORIZED
P2_SEARCH_VALUE_NOT_EVALUATED
```

This protocol answers three separate development questions on consumed L2 assets: the main effect of trajectory-conditioned Ada local adaptation, the main effect of online EvoX strategy adaptation, and their interaction. It does not test official-system parity, fresh-task generalization or superiority.

## Frozen design prepared for sealing

- Arms: `neither / Ada-only / EvoX-only / Ada+EvoX`.
- Factor controls: all arms retain one local-refinement and one structural-escape capability. Ada replaces a trajectory-unconditioned local control; EvoX replaces a strategy-unconditioned structural control.
- Tasks: six consumed MVP-0 development tasks, selected without P2 outcomes as the first two lexical identities in each of three existing families.
- Replicates: two paired replicates per task and arm; the four arms form one randomized execution block for each task-replicate.
- Maximum size: 12 paired blocks, 48 arm runs and 336 provider-call slots.
- Per task-replicate-arm envelope: 7 generation calls, 7 evaluator calls, 140,000 input-plus-output tokens, 2,100 wall seconds and 420 CPU seconds.
- Provider prepared for live seal: `gpt-5.6-sol`, reasoning effort `medium`, read-only ephemeral Codex execution, per-call timeout 300 seconds. The exact executable digest, CLI version and local/structural schema settings are bound only during the clean-commit seal.
- No novelty resampling, free repair, task replacement, cross-arm budget transfer or unused-budget filling.

## Primary estimands

For every paired task-replicate block, normalize final feasible improvement by that task's frozen score resolution and denote the four responses by `Y00`, `Y10`, `Y01`, `Y11`.

- Ada main effect: `0.5 × ((Y10 − Y00) + (Y11 − Y01))`.
- EvoX main effect: `0.5 × ((Y01 − Y00) + (Y11 − Y10))`.
- Ada × EvoX interaction: `Y11 − Y10 − Y01 + Y00`.

All three directions are predeclared positive. Each requires a median paired effect of at least one task-resolution step plus a one-sided exact paired sign test under Holm family-wise alpha `0.05`. Contrasts are computed inside paired blocks before aggregation; subtracting arm-level medians is forbidden. `Ada+EvoX` versus `neither` is descriptive and cannot establish synergy.

## Stop and failure semantics

- Controller stop is terminal; unused resources disappear.
- Invalid candidates consume their generation/evaluator slots and cannot replace the incumbent.
- Provider failure consumes a call slot and receives no free retry.
- Evaluator failure invalidates the complete paired four-arm block; there is no backfill.
- Timeout or budget failure stops the arm and marks the paired block `NOT_EVALUABLE_RESOURCE`.
- All 12 paired blocks are required for a scientific estimand verdict. Otherwise the protocol result is `NOT_EVALUABLE`, not an algorithm loss.
- After the first model call, no task, mechanism, threshold, evaluator, resource envelope, gate or same-revision rerun may change.

## Claim ceiling and next action

A positive result can establish only a bounded factorial development signal on these consumed tasks. P3 requires a positive replayable interaction plus `Ada+EvoX` noninferiority to both single-factor arms and `neither`; otherwise diagnosis remains on consumed traces.

The next action is mechanical: commit this protocol implementation, verify a clean source snapshot and provider executable, run the create-once zero-model seal, then record its manifest digest here. No model call is permitted before that seal succeeds.
