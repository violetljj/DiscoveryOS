# CIB-R1 Real Downstream Causal Trial

## Pre-execution status

```text
CIB_R1_PROTOCOL_READY_NOT_SEALED
DO_NOT_OPEN_SI3_FRESH_BUDGET
```

CIB-R1 asks one bounded causal question:

> Holding state, budget, model, operator contract, randomness distribution, and evaluator fixed, does the parent-policy intervention causally improve the distribution of generated descendants?

It uses only already-consumed SI-2 development states. It does not access confirmation/final blind data, consume a fresh task, reopen SI-2, or compare complete systems. Passing can establish `REAL_PARENT_MECHANISM_CAUSAL_VALUE` on this consumed development surface and make Parent eligible for a separately sealed fresh trial; it cannot establish DiscoveryOS search superiority.

## Frozen source states

The sampling frame is the six SI-2 `CURRENT_DISCOVERYOS` receipts where the actual Parent policy selected a non-incumbent. The split is by receipt identity before any CIB-R1 model call:

- calibration: `capacitated_assignment_delta` step 2 and `capacitated_assignment_eta` step 1;
- validation: `balanced_cut_delta` step 2, `budgeted_coverage_epsilon` step 2, and `capacitated_assignment_epsilon` step 2.

Validation therefore contains three distinct tasks from three algorithm families. The remaining eligible receipt is not used. Every state binds the historical policy receipt, incumbent, selected parent, source artifacts, task contract, public tests, evaluator and score resolution.

## Real stochastic downstream

The candidate model is frozen to the same strong configuration used by SI-2: `gpt-5.6-sol`, reasoning effort `medium`, through the validated local Codex CLI. Each branch is an isolated provider request using one prompt contract and a 60,000-token ceiling. The response contains an ordered chain of three complete `algorithm.py` descendants. All three are executed against the original public test and frozen task evaluator.

The backend does not expose a reliable numeric seed. Replicates therefore use frozen draw identities and separate provider processes/requests, with provider request IDs and usage retained. They are independent stochastic draws, not claimed deterministic seed replay.

For each validation state:

```text
NULL          incumbent A vs incumbent A, 2 independent pairs
INTERVENTION  incumbent A vs actual selected non-incumbent B, 3 pairs
POSITIVE      incumbent A vs frozen baseline copy-through control P, 2 pairs
```

The positive control deliberately uses a separate copy-through sensitivity prompt and is excluded from mechanism value. Its only purpose is to verify the live model-output-to-evaluator observation chain. Null and intervention use the identical strong-agent prompt contract.

## Calibration and gate

Calibration runs before validation. It freezes:

- behavioral margin: `max(0.01, maximum calibration null behavioral distance)`;
- utility margin: `max(0.005, maximum validation score resolution, maximum calibration null absolute final delta)`.

Validation is blocked unless both calibration states show positive-control behavior and absolute downstream utility differences beyond calibrated null.

The primary paired causal gate requires all of the following:

1. all branches are evaluable and respect matched branch ceilings;
2. live positive-control sensitivity is established;
3. CIB benefit persists in at least two of three validation states;
4. the nine intervention pairs pass a one-sided exact sign test at `alpha = 0.10` and have positive median final descendant delta;
5. median descendant validity rate and incumbent-replacement rate are not worse;
6. no state contributes more than `75%` of total positive effect.

Endpoints are descendant validity probability, fitness, incumbent replacement, one-to-three-step cumulative descendant value, anytime AUC, tokens and wall time. Provider/schema failures are `NOT_EVALUABLE`, not scientific losses. Candidate code that executes but violates the frozen task contract remains an evaluable invalid outcome.

## Entrypoints

```powershell
$env:PYTHONPATH = "src"
$codexCli = Join-Path $env:USERPROFILE ".codex\.sandbox-bin\codex.exe"

python -m discoveryos cib-r1-seal-parent-real `
  --workspace runs/cib-r1-parent-real `
  --source-workspace runs/si2-fresh-search-value-r1 `
  --source-manifest-digest c71c6b553778cbbe60dd4c683d5973ed6fa43e1c94e58a7903dfd626de37816d `
  --model gpt-5.6-sol --reasoning-effort medium --codex-command $codexCli --max-workers 2

python -m discoveryos cib-r1-calibrate-parent-real `
  --workspace runs/cib-r1-parent-real --manifest-digest <sealed-digest> `
  --model gpt-5.6-sol --reasoning-effort medium --codex-command $codexCli

python -m discoveryos cib-r1-run-parent-real `
  --workspace runs/cib-r1-parent-real --manifest-digest <sealed-digest> `
  --model gpt-5.6-sol --reasoning-effort medium --codex-command $codexCli
```

The ignored run root uses create-once manifest, calibration, branch, pair and final-report records. Completed branch checkpoints are reused after interruption, so a resume does not silently repeat model calls.
