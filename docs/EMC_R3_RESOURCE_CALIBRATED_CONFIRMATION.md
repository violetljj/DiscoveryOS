# EMC-R3 Resource-Calibrated Confirmation

## Status

```text
EMC_RESOURCE_CALIBRATION_R1_PROTOCOL_IMPLEMENTED
EMC_R3_RESOURCE_CALIBRATED_CONFIRMATION_PROTOCOL_IMPLEMENTED
EMC_RESOURCE_CALIBRATION_R1_NOT_YET_SEALED
EMC_R3_NOT_YET_SEALED
NO_EXECUTABLE_MECHANISM_CONTRACT_ADMITTED
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
