# P2 Ada × EvoX Factorial Development Protocol

## Current status

```text
P2_FACTORIAL_V1_EXECUTION_AUTHORITY_FAILED_PRE_MODEL
P2_FACTORIAL_V1_MODEL_CALLS_ZERO
P2_FACTORIAL_V2_RUNNER_IMPLEMENTED
P2_FACTORIAL_V2_ZERO_MODEL_BLOCK_PREFLIGHT_PASS
P2_FACTORIAL_V2_PENDING_CREATE_ONCE_SEAL
P2_SEARCH_VALUE_NOT_EVALUATED
```

V1 remains an immutable historical seal. Its first independent-worktree execution-authority check failed before any model call because `harness_code_bundle_digest()` hashed checkout line endings: the LF sealing checkout and CRLF detached worktree produced different Profile/fairness identities from byte-equivalent normalized sources. The frozen V1 source also lacked a bound 12-block execution, settlement and replay entrypoint. V1 therefore produced no scientific result and must not be executed or repaired in place.

V2 preserves the scientific question, tasks, paired design, provider, resource ceilings, estimands, statistics and claim ceiling. It changes only the pre-model executability surface: Harness source digests normalize CRLF/LF, the complete runner is bound by the protocol source digest, and a real consumed-task four-arm block must pass without invoking the provider before sealing.

## Frozen design to be sealed as V2

- Arms: `neither / Ada-only / EvoX-only / Ada+EvoX`.
- Factor controls: every arm retains bootstrap, local-refinement and structural-escape capabilities. Ada replaces only the trajectory-unconditioned local control; EvoX replaces only the strategy-unconditioned structural control.
- Tasks: the same six consumed MVP-0 L2 development tasks, two per existing family.
- Replicates: two paired replicates per task; all four arms form one randomized block.
- Maximum size: 12 paired blocks and 48 arm runs.
- Per task-replicate-arm ceiling: 7 generation calls, 7 evaluator calls, 140,000 input-plus-output tokens, 2,100 wall seconds and 420 CPU seconds.
- Execution accounting: one bound baseline evaluator call plus at most six unified search steps; generation calls therefore remain at or below seven and evaluator calls at or below seven.
- Provider: `gpt-5.6-sol`, reasoning effort `medium`, read-only ephemeral Codex execution, 300-second per-call timeout.
- No novelty resampling, free repair, task replacement, cross-arm budget transfer, unused-budget filling or same-revision partial resume.

## Primary estimands

For each evaluable paired block, final feasible improvement is divided by the frozen task score resolution, producing `Y00`, `Y10`, `Y01` and `Y11`.

- Ada main effect: `0.5 × ((Y10 − Y00) + (Y11 − Y01))`.
- EvoX main effect: `0.5 × ((Y01 − Y00) + (Y11 − Y10))`.
- Ada × EvoX interaction: `Y11 − Y10 − Y01 + Y00`.

Every direction is predeclared positive. Each requires median paired effect of at least one task-resolution step and a one-sided exact paired sign test under Holm family-wise alpha `0.05`. Contrasts are computed inside blocks. `Ada+EvoX` versus `neither` is descriptive only. P3 additionally requires the positive replayable interaction and median `Y11` noninferiority with zero-step margin against `Y10`, `Y01` and `Y00`.

## Execution and failure semantics

- The manifest stores the exact randomized block and within-block arm order.
- Every block constructs four isolated physical ledgers, one authority per arm, and reruns the zero-model runtime fairness audit before any arm model call.
- Block start, fairness, arm terminal and block terminal records are create-once. A partial result root cannot resume under the same revision.
- Invalid candidates consume their slots and do not replace the incumbent. Provider failure consumes the attempted generation slot and gets no free retry.
- Evaluator failure invalidates the complete block. Timeout or resource overrun marks the block `NOT_EVALUABLE_RESOURCE`. There is no backfill.
- All 12 blocks must be evaluable. Otherwise the protocol result is `NOT_EVALUABLE`, never an algorithm loss.
- Replay revalidates manifest/source/provider authority and recomputes the aggregate from the 12 immutable block terminals.

## Claim ceiling and next action

A positive result can establish only a bounded factorial development signal on these consumed tasks. It cannot establish official AdaEvolve/EvoX parity, fresh-task generalization, DiscoveryOS superiority or production readiness.

The next action is to commit this V2 implementation, create a clean detached worktree at that commit, pass execution-authority verification, and create-once seal V2 before the first model call. Exact commit, source, Profile/fairness, provider and manifest digests will be recorded only after that seal succeeds.
