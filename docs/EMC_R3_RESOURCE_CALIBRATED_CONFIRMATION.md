# EMC-R3 Resource-Calibrated Confirmation

## Status

```text
EMC_RESOURCE_CALIBRATION_R1_PROTOCOL_IMPLEMENTED
EMC_R3_RESOURCE_CALIBRATED_CONFIRMATION_PROTOCOL_IMPLEMENTED
EMC_RESOURCE_CALIBRATION_R1_PASSED
EMC_R3_INSTRUMENTATION_SENSITIVITY_PASSED
EMC_R3_CALIBRATION_PASSED
EMC_R3_EXECUTABLE_CONTRACT_TRANSMISSION_CONFIRMED_ON_TWO_NEW_DEV_STATES
EMC_OPERATOR_CAUSAL_VALUE_TRIAL_PROTOCOL_AUTHORIZED_NOT_RUN
```

EMC-R3 does not reopen R1 or R2. It asks a new confirmatory question on two never-consumed development states: under an independently calibrated per-call ceiling and durable at-most-once provider accounting, does the same deterministic Executable Mechanism Contract reproducibly actuate its mutually exclusive runtime paths?

## Independent resource authority

Before any scientific manifest is sealed, a separate four-call non-scientific corpus freezes representative implementation prompts at four source sizes. It records schema executability, exact token usage and wall time only; generated semantics are not scored or used for protocol selection.

The ceiling rule is frozen before those calls:

```text
ceil(max(61,681 historical tokens, observed calibration maximum) * 1.25 / 1,000) * 1,000
```

The derived ceiling must not exceed 100,000 tokens. All four calls must be evaluable with exact usage. The scientific manifest binds the resource result SHA-256, distribution, provider identity and formula. A failed resource calibration blocks EMC-R3.

## Fresh states and gates

- Calibration: new capacitated-assignment state `emc_r3_assignment_beta` with seeds `15101, 15121, 15139, 15161, 15187, 15217`.
- Independent validation: new weighted-coverage state `emc_r3_coverage_beta` with seeds `16111, 16127, 16139, 16183, 16217, 16223`.
- Each state has three independent Direct Construction draws and three Post-Construction Repair draws.
- E0: two positive and two negative instrumentation controls, zero model calls.
- E1: resource-calibration authority bound at seal, zero scientific calls.
- E2: six calibration calls; every draw must be evaluable, source-valid, invariant-valid, static-contract compliant, runtime-contract compliant and within the derived ceiling. Between-condition counter signatures must differ with zero within-condition categorical variation.
- E3: the same requirements on the independent validation state.

Every external call uses the durable invocation journal. A claim without a terminal record blocks the phase and is never guessed safe to retry.

## Interpretation

- E0 failure evaluates only instrumentation.
- Resource calibration failure is `NOT_EVALUABLE`, not a mechanism negative.
- E2 failure blocks E3.
- E3 success supports only `RESOURCE_CALIBRATED_EXECUTABLE_CONTRACT_TRANSMISSION_ON_TWO_NEW_DEV_STATES_ONLY` and authorizes designing a separate Operator causal-value protocol.
- E3 success does not establish utility, search value, superiority or production readiness, and does not itself authorize fresh search-value execution.

## Commands

```powershell
$codexCli = Join-Path $env:USERPROFILE ".codex\.sandbox-bin\codex.exe"
$env:PYTHONPATH = "src"
python -m discoveryos emc-resource-r1-seal --workspace runs/emc-resource-calibration-r1 --model gpt-5.6-sol --codex-command $codexCli --reasoning-effort medium
python -m discoveryos emc-resource-r1-run --workspace runs/emc-resource-calibration-r1 --manifest-digest <digest> --model gpt-5.6-sol --codex-command $codexCli --reasoning-effort medium
python -m discoveryos emc-r3-seal --workspace runs/emc-r3-resource-calibrated-confirmation --resource-workspace runs/emc-resource-calibration-r1 --resource-record-sha256 <sha256> --model gpt-5.6-sol --codex-command $codexCli --reasoning-effort medium
python -m discoveryos emc-r3-instrumentation --workspace runs/emc-r3-resource-calibrated-confirmation --manifest-digest <digest> --model gpt-5.6-sol --codex-command $codexCli --reasoning-effort medium
python -m discoveryos emc-r3-calibrate --workspace runs/emc-r3-resource-calibrated-confirmation --manifest-digest <digest> --model gpt-5.6-sol --codex-command $codexCli --reasoning-effort medium
python -m discoveryos emc-r3-validate --workspace runs/emc-r3-resource-calibrated-confirmation --manifest-digest <digest> --model gpt-5.6-sol --codex-command $codexCli --reasoning-effort medium
```

Both roots are create-once. Thresholds, tasks, contracts, replicates and ceilings cannot change after their respective seals.

## Results

Both protocols were sealed at commit `49462e0` with `gpt-5.6-sol / medium` and `codex-cli 0.148.0-alpha.9`.

Resource Calibration R1 used 4/4 evaluable calls with token costs `34,589`, `34,897`, `17,560`, and `53,449` (`140,495` total). Because the frozen historical maximum `61,681` exceeded the observed maximum, the frozen formula produced a `78,000`-token scientific ceiling. Resource result SHA-256 is `49d86e376997ff98ffecf319198e3a7589282bf0b086215465655cbb9b2f84bc`.

EMC-R3 manifest digest is `aec9e99df6e1b7f214e553a1d4f6115057f5f183791546cf18be2cdc1bdfed64`; manifest file SHA-256 is `08de47246f6df358b2b3d7c56c14f7d32e9ae1e0a8bbde593f1c62633afcd129`. E0 passed 4/4 controls with zero model calls; record SHA-256 is `900a7804b53179de47e7f33f6a7a882e0bacaaf1dcad85ac28b339bf505a442c`.

E2 assignment calibration passed 6/6 draws and used `245,080` tokens; record SHA-256 is `451063eba0474da4d1f96cf538b5e98255e74106bf3f31fe7b23c21f5fdea2bc`. E3 independent coverage validation also passed 6/6 and brought scientific usage to 12 calls and `500,474` tokens; validation record SHA-256 is `d6c2d4bb4b89d116014cb25f1d2232e889abd6dd059c10f407b9d55235ee05ec`. The maximum scientific call used `57,118` tokens.

In both states, Direct Construction had the single runtime signature `[1,0,0]` and Post-Construction Repair had `[1,1,0]`; all sources, static obligations, runtime obligations, invariant canaries and resource checks passed. Journal audit found 12 claims, 12 terminals, 12 draw checkpoints, zero orphan claims and no duplicate invocation evidence.

The maximum claim is `RESOURCE_CALIBRATED_EXECUTABLE_CONTRACT_TRANSMISSION_ON_TWO_NEW_DEV_STATES_ONLY`. Assignment utility was identical across both conditions. Coverage utility was record-only and not a frozen causal-value comparison. The result authorizes a separate Operator causal-value protocol but does not establish utility, search value, superiority or production readiness.
