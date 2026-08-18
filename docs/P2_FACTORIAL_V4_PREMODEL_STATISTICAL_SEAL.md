# P2 V4 / P2-R1 Pre-Model Design and Statistical Seal

## Status and authority

```text
P2_V4_PREMODEL_DESIGN_STATISTICAL_SEAL_FROZEN
P2_V4_MAXIMUM_BLOCKS_24
P2_V4_INDEPENDENT_FAMILY_COHORT_NOT_YET_AVAILABLE
P2_V4_COHORT_MANIFEST_NOT_SEALED
P2_V4_SCIENTIFIC_GENERATION_NOT_AUTHORIZED
P3_NOT_AUTHORIZED
```

This document freezes the design choices that must precede implementation of the V4 runner and create-once scientific manifest. It makes zero model/provider calls, opens no SHADOW/SEALED asset, and does not create an execution root. The later manifest must bind this tracked document by Git commit and SHA-256 and may only instantiate the rules below; changing the cohort rule, maximum `N`, recovery semantics, estimands, tests, thresholds, or P3 gate requires a new design revision before any scientific call.

V3 remains immutable and `NOT_EVALUABLE / estimands=null`. Its observed arm outcomes may not be used for effect estimation, family/task selection, threshold tuning, factor redesign, power assumptions, or tie-rate estimation. V3 may be used only for infrastructure diagnosis, engineering design, and monetary/resource calibration.

## Frozen scientific question

V4 retains the V3 2x2 factorial question and the same four matched single-runtime Profiles:

- Ada main effect;
- EvoX main effect;
- Ada × EvoX interaction;
- arms `neither / Ada-only / EvoX-only / Ada+EvoX` with the same capability-matched controls and common execution authority.

No factor, action capability, evaluator authority, estimand direction, resolution threshold, or P3 admission rule is changed in response to V3.

## Independent outcome-blind cohort

### Statistical unit and source

One paired four-arm block is one distinct Benchmark Bank problem family represented by one predesignated DEV instance. Two instances or seeds from the same family are not counted as independent blocks for the primary sign inference. V3 task identities, payload/tree identities, evaluator identities, and its three primary problem families are forbidden as V4 primary units.

The primary cohort must contain exactly 24 `DEVELOPMENT_READY` external contract-derived L2/DEV families, stratified before executability observations as:

| Difficulty tier | Families / blocks |
|---|---:|
| R0 | 6 |
| R1 | 6 |
| R2 | 12 |
| **Total** | **24** |

The current Bank has only 16 such families (`3 R0 / 3 R1 / 10 R2`), although it has 32 instances. It is therefore not sufficient for this design. At least eight additional eligible families are required (`+3 R0 / +3 R1 / +2 R2`) before a V4 cohort can be frozen. Reusing both alpha/beta instances as if they were independent families is prohibited.

### Outcome-blind admission and ordering

Eligibility may depend only on frozen metadata and zero-model evidence:

- Bank integration state, task family, difficulty tier, evidence role and partition;
- exact nonidentity with every V3 task/payload/tree/evaluator binding;
- deterministic materialization and replay identity;
- evaluator availability and full-parser `VALID` baseline evaluability;
- V3-inherited residual-headroom rule: at least four score-resolution steps and at least two distinct resolvable non-baseline steps, measured only from deterministic fixture/reference material;
- frozen resource envelope and Executability Gate result.

Eligibility must not depend on any V3 arm difference/tie or any V4 generated candidate. Within each tier, family selection and the single instance for each family use a manifest-bound SHA-256 rank over protocol id, Bank registry digest, family id and instance id; there is no human task picking after the candidate reservoir is frozen. If fewer than the required number pass, the cohort does not seal and scientific generation remains zero. A failed family is not silently replaced inside the same revision.

## Full-cohort executability before generation

The mandatory sequence is:

```text
freeze candidate reservoir and deterministic rank
  -> hold a continuous power-inhibition lease
  -> materialize all 24 provisional units immutably
  -> execute two untouched full-evaluator/parser baseline replays per unit
  -> require 24/24 Executability Gate PASS
  -> seal exact cohort, task trees, evaluator/environment digests and schedule
  -> verify the sealed manifest from a clean detached worktree
  -> only then enable scientific generation authority
```

The cohort gate inherits `DISCOVERYOS_EXECUTABILITY_GATE_V1`: finite deterministic `VALID` baselines, exact tree replay, power-state provenance, timing reconciliation, provider provenance and fail-closed lease lifecycle. A second attempt at sealing may occur only as a new manifest revision after the zero-model defect is corrected; it cannot use generated outcomes because none may exist.

Every scientific block attempt must reacquire the same class of lease and rerun its task/tree/environment plus baseline admission before its first arm generation call. The cohort-wide pass is not a permanent waiver for later host drift.

## Frozen estimands and inference

For each admitted block, final feasible improvement is divided by that task's frozen score resolution, yielding `Y00`, `Y10`, `Y01`, `Y11`. V4 inherits V3 exactly:

- Ada: `0.5 × ((Y10 - Y00) + (Y11 - Y01))`;
- EvoX: `0.5 × ((Y01 - Y00) + (Y11 - Y10))`;
- interaction: `Y11 - Y10 - Y01 + Y00`.

All directions are positive. Each estimand requires both:

1. median within-block contrast of at least `1.0` task-resolution step; and
2. a one-sided exact paired sign test, followed by Holm step-down family-wise correction at `0.05` across the three frozen estimands.

As in the V3 implementation, exact zero contrasts are reported as ties and omitted from the sign-test denominator; they remain in the median and therefore cannot evade the one-step effect gate. Contrasts are always computed within block. `Ada+EvoX` versus `neither` remains descriptive only.

P3 admission is unchanged: the interaction must be a positive replayable estimand and median `Y11` must be noninferior to each of `Y10`, `Y01`, and `Y00` at the frozen zero-step margin. Main effects receive individual verdicts but do not substitute for the interaction gate.

## Pure-theory sample-size calculation

The design calculation uses only the exact binomial tail under `H0: p=0.5`; it does not use V3 outcomes. To conservatively size each marginal test for the strictest first Holm threshold, it requires:

`P[Binomial(N, 0.5) >= k] <= 0.05 / 3`.

| Maximum N | Required positive non-tie blocks `k` | Null tail | Power at p=0.70 | p=0.75 | p=0.80 |
|---:|---:|---:|---:|---:|---:|
| 12 | 11 | 0.003174 | 0.085025 | 0.158382 | 0.274878 |
| 18 | 14 | 0.015442 | 0.332655 | 0.518669 | 0.716354 |
| 24 | 18 | 0.011328 | 0.388589 | 0.607412 | 0.811071 |

These are per-estimand conditional powers assuming all blocks are non-ties and the separate median-resolution gate is satisfied. They are not joint power for all three correlated contrasts; ties or heterogeneous weak effects reduce effective power. The table therefore does not support a claim that `N=24` guarantees 80% overall power. It shows that 12 is severely underpowered at the predeclared multiplicity gate, 18 is still only about 52% at `p=0.75`, and 24 is the smallest compared maximum reaching about 81% at `p=0.80`. V4 consequently freezes `maximum_blocks=24`.

No efficacy stop is allowed. A machine-only futility stop may be evaluated after a complete block only when, for every one of the three estimands, assigning every remaining scheduled block the most favorable positive non-tie sign would still produce an exact sign-test p-value greater than `0.05`. Because no estimand could then pass even the least stringent possible Holm threshold, the full factorial gate is mathematically unreachable. The check exposes only the terminal futility boolean, not interim effects. Any weaker, conditional, predictive, Bayesian, effect-looking, or conditional-power stop is forbidden.

## Narrow infrastructure recovery

### Recoverable attempt classes

Recovery is allowed only when a version-bound Executability Gate receipt supplies machine evidence for one of these exact classes:

- `INFRA_FAILURE_HOST_LOW_POWER_STATE_CONTAMINATION`, with overlapping Windows suspend, hibernate or Modern Standby event identity;
- `INFRA_FAILURE_POWER_INHIBITION_UNAVAILABLE` or `INFRA_FAILURE_POWER_INHIBITION_RELEASE_FAILED`, with the failed Windows API operation and error code;
- a pre-generation transient host materialization/environment failure with `generation_calls_executed=0`, an unchanged sealed source/task/environment digest, and a concrete OS process/filesystem error code. A digest mismatch or deterministic evaluator failure is not transient.

Power-event provenance unavailable, an unexplained clock jump, or a generic exception is not proof of an exogenous failure. New recoverable classes require a new pre-model protocol revision and adversarial Gate qualification; they cannot be added after observing an attempt.

### Nonrecoverable classes

The following consume the frozen scientific opportunity and receive no free retry:

- provider timeout, retry, transport error, malformed/invalid response, or a normally running provider call that exceeds its limit;
- algorithm/candidate build, public-test, evaluator, validity, CPU, wall, token, call or other resource failure;
- deterministic materialization/tree/environment drift, evaluator nondeterminism, baseline invalidity, missing provenance, or any failure without a whitelisted machine receipt;
- protocol, fairness, authority, ledger, replay or receipt violation.

These failures cannot be relabeled as infrastructure from elapsed wall time, low CPU, operator judgment, or cost alone.

### Retry unit and limits

For a whitelisted `EXOGENOUS_INFRA_FAILURE`, the complete four-arm attempt is censored and preserved immutably. No arm result from that attempt enters an estimand. The retry starts the entire block from its sealed initial materialization under its separately pre-randomized retry order; it never backfills only the failed arm.

```text
max_infra_retries_per_block = 1
max_infra_retries_global = 2
```

Exceeding either limit closes the protocol as `PROTOCOL_NOT_EVALUABLE_INFRA`. A nonwhitelisted block failure closes it under its frozen scientific/resource/protocol terminal; it does not spend an infra retry.

## Cost and budget accounting

Receipts and the aggregate ledger must separately record:

```text
scientific_generation_calls
scientific_tokens
infra_censored_generation_calls
infra_censored_tokens
total_paid_generation_calls
total_paid_tokens
```

`total_paid = scientific + infra_censored` is mandatory monetary accounting. Calls/tokens from a whitelisted censored attempt do not debit the replacement block's algorithm budget, but they remain immutable paid cost and are bounded by the retry caps. Calls/tokens from provider, algorithm, candidate or resource failures remain scientific debits.

Keeping the V3 per-arm ceilings provisionally unchanged gives a hard maximum of 672 generation calls and 13,440,000 scientific tokens for 24 uncensored blocks. V3 cost-only calibration was 3,415,877 tokens across 40 attempted scientific arms, or about 85,397 tokens per arm; linear calibration suggests about 8,198,105 tokens for 96 arms before infra loss. This calibration does not use or reveal effect outcomes and is not a budget entitlement. The final manifest must bind exact provider, executable, per-arm ceilings, total scientific ceiling and a separate maximum infra-loss ledger before authority opens.

## Next authorized work

The only authorized sequence is:

1. expand and validate the Benchmark Bank to at least the frozen `6/6/12` family reservoir without model calls;
2. implement the V4 cohort selector, full-cohort Gate, attempt-level recovery state machine, split cost ledger, aggregate/replay and focused adversarial tests;
3. run the 24/24 zero-model cohort gate;
4. create and verify a clean-worktree, create-once V4 manifest that binds this seal;
5. only then request scientific generation authority.

Until all five conditions hold, P2 V4 is `DESIGN_ONLY`, generation budget is zero, V3 remains closed, and P3 remains unauthorized.
