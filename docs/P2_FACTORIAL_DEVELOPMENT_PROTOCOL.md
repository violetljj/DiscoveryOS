# P2 Ada × EvoX Factorial Development Protocol

## Sealed status

```text
P2_FACTORIAL_PROTOCOL_SEALED_PRE_MODEL
P2_FACTORIAL_TASK_PREFLIGHT_PASS_ZERO_MODEL
P2_MODEL_CALLS_AUTHORIZED_NOT_STARTED
P2_SEARCH_VALUE_NOT_EVALUATED
```

This protocol answers three separate development questions on consumed L2 assets: the main effect of trajectory-conditioned Ada local adaptation, the main effect of online EvoX strategy adaptation, and their interaction. It does not test official-system parity, fresh-task generalization or superiority.

## Frozen design

- Arms: `neither / Ada-only / EvoX-only / Ada+EvoX`.
- Factor controls: all arms retain one local-refinement and one structural-escape capability. Ada replaces a trajectory-unconditioned local control; EvoX replaces a strategy-unconditioned structural control.
- Tasks: six consumed MVP-0 development tasks, selected without P2 outcomes as the first two lexical identities in each of three existing families.
- Replicates: two paired replicates per task and arm; the four arms form one randomized execution block for each task-replicate.
- Maximum size: 12 paired blocks, 48 arm runs and 336 provider-call slots.
- Per task-replicate-arm envelope: 7 generation calls, 7 evaluator calls, 140,000 input-plus-output tokens, 2,100 wall seconds and 420 CPU seconds.
- Provider: `gpt-5.6-sol`, reasoning effort `medium`, read-only ephemeral Codex execution, per-call timeout 300 seconds.
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

## Create-once seal binding

- Source commit: `ced4dd2b617e821adc41b2d7fcaf8c1c560ffbf9`.
- Tracked source-tree digest: `f1c3bdea1d5ae8886de662585fbc3ddc3c59e480b26bb3df535946d9cc5d6485`.
- Profile fairness digest: `6e9fd6c741cd0f52c885575044342053ea39b2547f68a24343648b3f89d3eaf6`.
- Protocol manifest digest: `8970fe227571e28a29d7baf0a7d911b6b306398051f00c2eaba7d13991528500`.
- Manifest file SHA-256: `e0a7411d85d7b59c0798f5e412346472f170adb20e1d82112cd99138d4aeec52`.
- Provider: `codex-cli 0.148.0-alpha.9`; executable SHA-256 `f29f609375f3731d8db507a95124862a84e306982e30ba4300ddce5638bc6946`.
- Local create-once record: ignored path `runs/p2-factorial-development-v1/protocol-artifacts/records/p2-factorial-development-v1-manifest.json`.
- Seal and disk replay verification used zero model calls and opened zero fresh/SEALED assets.

The execution authority verifies manifest integrity, exact source commit/tree, clean worktree, profile/fairness binding, task implementation and provider executable/settings before a run. Because this status document is committed after the seal, model execution must use a separate clean worktree checked out at the sealed source commit; current `main` is not silently treated as equivalent.

## Claim ceiling and next action

A positive result can establish only a bounded factorial development signal on these consumed tasks. P3 requires a positive replayable interaction plus `Ada+EvoX` noninferiority to both single-factor arms and `neither`; otherwise diagnosis remains on consumed traces.

The protocol now authorizes only its exact P2 development run. No model call has started. The next action is to execute the sealed 12-block schedule from the bound commit without changing tasks, mechanisms, thresholds, evaluator, resources or gates.
