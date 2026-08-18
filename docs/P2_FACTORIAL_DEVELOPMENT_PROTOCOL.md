# P2 Ada × EvoX Factorial Development Protocol

## Current status

```text
P2_FACTORIAL_V1_EXECUTION_AUTHORITY_FAILED_PRE_MODEL
P2_FACTORIAL_V1_MODEL_CALLS_ZERO
P2_FACTORIAL_V2_TASK_COMMIT_IDENTITY_FAILED_PRE_MODEL
P2_FACTORIAL_V2_MODEL_CALLS_ZERO
P2_FACTORIAL_V3_COMPLETED_NOT_EVALUABLE
P2_FACTORIAL_V3_REPLAY_PASS
P2_FACTORIAL_ESTIMANDS_NOT_COMPUTED
P2_V4_PREMODEL_DESIGN_STATISTICAL_SEAL_FROZEN
P2_V4_SCIENTIFIC_GENERATION_NOT_AUTHORIZED
P3_NOT_AUTHORIZED
```

V1 remains an immutable historical seal. Its first independent-worktree execution-authority check failed before any model call because `harness_code_bundle_digest()` hashed checkout line endings: the LF sealing checkout and CRLF detached worktree produced different Profile/fairness identities from byte-equivalent normalized sources. The frozen V1 source also lacked a bound 12-block execution, settlement and replay entrypoint. V1 therefore produced no scientific result and must not be executed or repaired in place.

V2 fixed the cross-worktree identity and bound the runner, but its first block failed before any model call because task repositories are generated with a new commit timestamp: content-identical trees received different commit IDs between seal and execution. Its partial root is immutable and cannot resume. V3 preserves the same scientific design and makes the generated task Git tree authoritative while retaining the ephemeral commit only as diagnostic provenance.

## Frozen V3 design

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

A positive result could have established only a bounded factorial development signal on these consumed tasks. It could not establish official AdaEvolve/EvoX parity, fresh-task generalization, DiscoveryOS superiority or production readiness.

V3 is closed. It does not authorize P3, a replacement cohort, backfill, resampling or repair of its consumed root. P2 V4 retains the same scientific question but is a new independent protocol revision: its pre-model design/statistical rules are frozen in [`P2_FACTORIAL_V4_PREMODEL_STATISTICAL_SEAL.md`](P2_FACTORIAL_V4_PREMODEL_STATISTICAL_SEAL.md). V4 cannot use V3 as a tunable cohort and currently has no cohort manifest or generation authority.

## V3 execution result

V3 was sealed and executed from a clean detached worktree at commit `8d9b80d301407e2028e51024d5b96bce9b93e5f5`. The frozen Profile fairness digest was `4753549b6d454bdaba9a2bec6795fcc8314a3563058270609cf86129226916c7`; the protocol manifest digest was `86622585040bc1c88604b73d2bde978267e792741f6b026da997ab196602fef5`, and the manifest file SHA-256 was `54e537a5c4a95b68380c40993cc0ad4f90d901c769be25dff1465da3dda637b2`. Provider execution remained bound to `codex-cli 0.148.0-alpha.9` and `gpt-5.6-sol`.

All 12 scheduled blocks reached create-once terminals, but only 9 were fully evaluable. One `bounded_knapsack_beta` block was invalidated when the `neither` arm accumulated `3944.295` wall seconds against the frozen `2100`-second ceiling. Both `load_balance_alpha` replicate blocks failed before model generation because the frozen baseline evaluator returned `BASELINE_EVALUATOR_NOT_EVALUABLE:neither`; all eight affected arm records are preflight terminals. Per the frozen all-block rule, the aggregate is therefore:

```text
status=NOT_EVALUABLE
completed_blocks=12
evaluable_blocks=9
estimands=null
p3_authorized=false
```

The run recorded 172 generation calls, 176 evaluator calls and 3,415,877 input-plus-output tokens. The nine evaluable blocks are descriptive only: eight had identical final response across all four arms, while one `load_balance_beta` block had `Ada+EvoX=24.3000` versus `25.4758` for the other arms. That isolated difference is not an estimand and cannot be interpreted as a negative interaction after the protocol became non-evaluable.

Frozen replay passed with no issues. The canonical report digest is `e68ed3ade290dce7ef1b85129842c5fe68125dbb3aa4eb42fcf3f123807faa01`; the report file SHA-256 is `888e240fce971ae23f8ebf9d17a8bd0a4c8300961cb8ce1608713da60467d38d`.
