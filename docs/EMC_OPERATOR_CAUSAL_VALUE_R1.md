# EMC Operator Causal Value R1

## Status

```text
EMC_OPERATOR_CAUSAL_VALUE_R1_PROTOCOL_IMPLEMENTED_NOT_RUN
FRESH_SEARCH_VALUE_BUDGET_NOT_AUTHORIZED
```

This protocol is the only causal-value trial authorized by the EMC-R3 result. It does not reopen EMC-R3 and does not ask again whether the generator obeys the executable contracts. It asks whether two already-observable runtime Operators produce different downstream value under the same model, resource authority, evaluator family and development-state role.

## Frozen comparison

The comparison has three pair kinds:

```text
Direct vs Direct  -> Direct stochastic null
Repair vs Repair  -> Repair stochastic null
Direct vs Repair  -> Operator intervention
```

Calibration uses one new capacitated-assignment state and one new weighted-coverage state. Each state runs two Direct-null and two Repair-null pairs, for 16 independent calls. If every branch remains evaluable, within the inherited 78,000-token ceiling, source-valid and compliant with static, runtime and invariant obligations, the protocol freezes:

- utility margin: the greater of the largest task score resolution and maximum absolute calibration null score difference;
- anytime-AUC margin: the greater of the largest task score resolution and maximum absolute calibration same-condition trajectory-AUC difference.

Validation uses an independent new assignment state and an independent new coverage state. Each runs two Direct-null pairs, two Repair-null pairs and three Direct/Repair intervention pairs, for 28 calls. The state-local envelope is the greater of the frozen calibration margin and that validation state's same-condition null effect. This rule is sealed before any model call.

The provider remains `gpt-5.6-sol / medium`, must match the EMC-R3 authority, and every request uses the durable at-most-once invocation journal. The source EMC-R3 validation record and its resource authority are hash-bound at seal.

## Repair applicability

Every state must pass a zero-model applicability witness before the manifest can be created. The frozen baseline and frozen reference must both be valid, the reference must improve evaluator score by at least the task's score resolution, and at least one frozen evaluator probe must improve. This establishes observable repair headroom for the state; it does not establish that a generated `emc_improve` will exploit it.

The implementation never sees the hidden evaluator, pair kind, branch role or the other branch's output. Direct and Repair see only the same task/base source plus their own canonical Mechanism Object and executable contract.

## Endpoints and manipulation gate

The registered endpoints are:

- final utility;
- matched-call anytime AUC over replicate-ordered cumulative best;
- validity rate;
- incumbent-replacement rate;
- breakthrough probability relative to the frozen reference threshold.

The independently observed runtime signature remains a manipulation check, not a utility endpoint. Direct must remain `[1,0,0]`, Repair must remain `[1,1,0]`, and every static/runtime/invariant contract layer must pass. If this portability gate fails, utility is marked uninterpretable even if scores differ.

The positive primary gate requires both validation states to exceed their final-utility and anytime-AUC envelopes, a one-sided exact sign test at `alpha = 0.10`, positive median final effect beyond the registered envelope, non-worse median validity/replacement/breakthrough rates, and no state contributing more than 75% of positive effect.

## Locked interpretation

- Runtime separated and primary value gate positive: `OPERATOR_CAUSAL_VALUE_DETECTED_ON_DEV`.
- Runtime separated but primary value gate fails: `DIRECT_REPAIR_OPERATOR_CAUSAL_VALUE_NOT_ESTABLISHED_ON_DEV`.
- Runtime not separated or contract layers fail: `EMC_OCV_R1_CONTRACT_PORTABILITY_FAILED_UTILITY_NOT_INTERPRETABLE`.
- Provider or resource failure: `EMC_OCV_R1_NOT_EVALUABLE_RESOURCE_OR_PROVIDER`.

No outcome establishes general DiscoveryOS search value, system superiority, fresh-task confirmation or production readiness. A positive development result can only authorize separately sealing a fresh confirmation/search-value question; a null result closes the current Direct/Repair value claim instead of reopening EMC instrumentation.

## Commands

```powershell
$env:PYTHONPATH = "src"
$codexCli = Join-Path $env:USERPROFILE ".codex\.sandbox-bin\codex.exe"

python -m discoveryos emc-ocv-r1-seal `
  --workspace runs/emc-operator-causal-value-r1 `
  --emc-r3-workspace runs/emc-r3-resource-calibrated-confirmation `
  --emc-r3-validation-record-sha256 d6c2d4bb4b89d116014cb25f1d2232e889abd6dd059c10f407b9d55235ee05ec `
  --model gpt-5.6-sol --reasoning-effort medium --codex-command $codexCli --max-workers 2

python -m discoveryos emc-ocv-r1-calibrate `
  --workspace runs/emc-operator-causal-value-r1 --manifest-digest <digest> `
  --model gpt-5.6-sol --reasoning-effort medium --codex-command $codexCli

python -m discoveryos emc-ocv-r1-validate `
  --workspace runs/emc-operator-causal-value-r1 --manifest-digest <digest> `
  --model gpt-5.6-sol --reasoning-effort medium --codex-command $codexCli
```

The root is create-once. Tasks, seeds, endpoints, margins, pair counts, ordering, gate and claim ceiling cannot change after seal.
