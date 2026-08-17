# CIB-R1 Real Downstream Causal Trial

## Verdict

```text
CIB_R1_REAL_DOWNSTREAM_COMPLETE
PARENT_INTERVENTION_VALUE_NOT_ESTABLISHED_UNDER_STRONG_STOCHASTIC_GENERATOR
REAL_PARENT_MECHANISM_NOT_ADMITTED
DO_NOT_OPEN_SI3_FRESH_BUDGET
```

CIB-R1 asks one bounded causal question:

> Holding state, budget, model, operator contract, randomness distribution, and evaluator fixed, does the parent-policy intervention causally improve the distribution of generated descendants?

It uses only already-consumed SI-2 development states. It does not access confirmation/final blind data, consume a fresh task, reopen SI-2, or compare complete systems. Passing can establish `REAL_PARENT_MECHANISM_CAUSAL_VALUE` on this consumed development surface and make Parent eligible for a separately sealed fresh trial; it cannot establish DiscoveryOS search superiority.

The create-once manifest digest is `f14902c185470fb9fcb71bf28a7eb4a3c9562d4109db742d9147f47112fc0b4e`; manifest file SHA-256 is `ffcb7be9e67e65bdfef187648619654735cdfd3c8d2295a282f508b700bb9a01`. Calibration SHA-256 is `a0803571cfd463c8b5543337a4198353337650c1020624749776776b44a9ca9e`; final report SHA-256 is `7fbd3db909dc5d8da11bca9d12f164e0f0cb520333cf9aab012945d7afe74f72`.

## Result

Calibration completed with `16/16` evaluable branches. Both calibration states detected the copy-through positive control, freezing behavioral margin `0.2863564212655271` and utility margin `0.005` before validation.

Validation then completed all 42 branches and 21 pairs. Together, calibration and validation used 58 independent provider requests, 29 paired receipts, `1,050,691` input tokens, `248,106` output tokens and `267,776` cached-input tokens. Input plus output usage was `1,298,797` tokens; summed provider wall time was `5,322.938` seconds. No fresh task was consumed, every branch was evaluable, and every frozen resource ceiling passed.

The primary result was exactly null at the registered utility endpoints:

- live positive-control sensitivity was detected in `2/3` validation states, satisfying the frozen minimum;
- actual Parent intervention behavior exceeded state-local null plus the calibrated margin in `0/3` states;
- persistent or beneficial intervention value appeared in `0/3` states;
- the nine intervention pairs were `0 positive / 9 tie / 0 negative` on final descendant value;
- median final descendant, validity-rate and incumbent-replacement deltas were all `0`; one-sided exact-sign `p = 1.0`;
- no generated descendant replaced the already-strong incumbent on this surface.

The historical policy intervention itself was real: each source receipt selected a non-incumbent. What failed was downstream manipulation and value transmission under the strong stochastic generator. Parent choice did not produce a descendant distribution distinguishable from the incumbent-parent null at the frozen margins. This does not prove Parent is universally useless; it establishes that its marginal causal value is not demonstrated on the consumed SI-2 state/model/operator surface and provides no basis for fresh budget.

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

The ignored run root uses create-once manifest, calibration, branch, pair and final-report records. Completed branch checkpoints are reused after interruption, so a resume does not silently repeat model calls. Post-run verification recomputed the manifest and calibration digests and checked all 29 pair hashes, all 58 branch checkpoint digests and every final source binding.

## Evidence limits

- Validation contains three consumed states, one per SI-2 task family, under one model/config and one batched three-descendant operator contract.
- Codex CLI exposes no replayable numeric generation seed; independence is separate processes/requests with frozen draw identities, not deterministic seed reproduction.
- The three descendants are emitted in one model call without evaluator feedback between steps. This tests parent sensitivity of a bounded strong-agent generation operator, not a full multi-turn search loop.
- One coverage null pair showed large stochastic validity/utility spread; the state-local envelope correctly made that state harder, not easier, to admit.
- The negative result does not change `SI2_SEARCH_VALUE_NOT_ESTABLISHED`, establish general mechanism inferiority, or authorize a product claim.
