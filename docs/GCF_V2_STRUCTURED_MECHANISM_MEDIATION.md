# GCF-V2 Structured Mechanism Mediation

## Current status

```text
GCF_V2_STRUCTURED_MEDIATION_PROTOCOL_IMPLEMENTED
GCF_V2_R1_NOT_EVALUABLE_PROVIDER_SCHEMA
GCF_V2_R2_PREFLIGHT_RESOURCE_BLOCKED
GCF_V2_R3_PROPOSAL_CALIBRATION_PASSED
GCF_V2_R3_PROPOSAL_VALIDATION_PASSED
STRUCTURED_MECHANISM_OBJECT_CHANNEL_DETECTED_ON_TWO_DEV_STATES
GCF_V2_R3_NOT_EVALUABLE_RESOURCE_CEILING
NO_STRUCTURED_MECHANISM_CHANNEL_ADMITTED
NO_FRESH_VALUE_TRIAL_AUTHORIZED
```

GCF-V2 is a new versioned generator-interface diagnosis. It does not modify or replay the consumed GCF-R1 root. Its question is narrower than search value:

> Does a natural-language mechanism condition reliably produce a frozen structured Mechanism Object, and does a separate implementation generator that sees only that object transmit it into source structure and hidden behavior?

Passing calibration can establish structured mediation only on two new development calibration states. It cannot establish mechanism utility, DiscoveryOS superiority, generalization, or production readiness. Even a positive calibration only permits preregistration of an independent GCF-V2 validation protocol.

## Mechanism Object

The machine object contains:

```text
mechanism_family
hypothesis
algorithmic_change.replace / with
expected_control_flow
forbidden_fallbacks
invariants
expected_behavioral_signatures
failure_semantics
```

The admission signature uses categorical control-flow fields rather than free-text embedding distance. Explanatory fields remain evidence and future V3 inputs, but cannot substitute for a contradictory categorical contract. The object is canonicalized and content-addressed before implementation.

## Mediation isolation

The protocol uses two independent provider requests:

```text
task + base source + mechanism brief
  -> structured proposal request
  -> canonical immutable Mechanism Object

task + base source + canonical Mechanism Object
  -> implementation request
  -> executable source + frozen evaluator/probe
```

The implementation request cannot receive the original brief, condition ID, or proposal raw response. This prevents the implementation stage from bypassing the proposed intermediate representation by reinterpreting the original condition.

## Cheap-first calibration

R3 first performs one non-scientific provider/schema preflight using the exact proposal provider and schema. A failure blocks the scientific schedule after one call and preserves the CLI transport diagnostic in the receipt.

Two new development-only tasks are frozen before calls: weighted coverage is the calibration state and balanced graph cut is the independent proposal-validation state. Each state gives both mutually exclusive conditions three independent draws. After preflight, the first scientific gate costs only six calls on coverage. Failure stops before the six-call cut validation; both proposal phases must pass before implementation. Calls are capped at 25,000 input-plus-output tokens based on the R2 non-scientific executability observation.

Each proposal phase requires all draws to be evaluable and contract-compliant, resource ceilings to pass, and between-condition categorical separation to exceed the maximum same-condition stochastic distance. Failure blocks later phases with zero implementation calls.

Only after proposal admission may the 12 corresponding Mechanism Objects receive isolated implementation calls, each capped at 30,000 tokens. Source and hidden-behavior distances are separately compared against their state-local within-condition envelopes plus frozen margins. Utility is recorded but excluded from mediation admission.

The maximum calibration cost remains 25 calls including preflight. The first scientific stopping point is six calls; at R2's observed 17,497 tokens per call it is about 104,982 tokens, or 19.6% of GCF-R1's 536,852-token calibration.

## R1 executability closeout

R1 sealed manifest `bdefaf6f50e6cfd2676f9eb32f95d9f42fbd44817b65f5717f90c52565bc22bc` at commit `c4fd8a4`. All 12 scheduled proposal invocations exited at the provider/schema boundary with CLI exit code `1`, zero reported tokens, zero contract-compliant objects, and zero evaluable draws. The create-once calibration record SHA-256 is `4e40a0ce0d8a41731a294154081f4d56210f021c7fa1b7c2f21d9ea914eaad88`.

The official Structured Outputs reference documents a supported JSON Schema subset and does not include `uniqueItems`; R1 used that keyword on four arrays. R1 is therefore closed as `GCF_V2_R1_NOT_EVALUABLE_PROVIDER_SCHEMA`, not as a semantic failure. Implementation remained blocked with zero calls. R2 removed the unsupported keyword, retained manual uniqueness validation after parsing, and added the one-call preflight. R1 artifacts are not modified or replayed.

R2 sealed manifest `6f325e3ac0cd9ebd2efc9460b8b6068434da1a9bcb0cc40d2b8e715d8ba3ec84` at commit `15ed1a7`. Its one preflight call succeeded at the provider, schema, parsing, and condition-contract layers and returned a compliant object, but used 17,497 tokens against the frozen 8,000 ceiling. R2 therefore closed as `GCF_V2_R2_PREFLIGHT_RESOURCE_BLOCKED` with zero scientific proposal and implementation calls. R3 raises only the resource ceiling to 25,000 and splits the two proposal states into sequential calibration and validation gates; its mechanism schema, conditions, draws per state, evaluator surfaces, implementation isolation, margins, and claim ceiling remain unchanged.

## R3 result

R3 sealed manifest `3f3686b5d73ffec715edd7b8c686961a10d8db771bc9b9c55d554c1797ae19fb` at commit `c317a0c`; manifest file SHA-256 is `98de84497fe50143af0773da92cf1e8af13094b445515eef8036c40f4201a375`.

The non-scientific preflight passed with one compliant object and 17,492 tokens. Its human-readable status and draw ID retain an R2 label, while the authoritative `protocol_id`, manifest binding, pass field, schema digest, and provider binding correctly identify R3. The immutable naming defect is disclosed and does not change gate evaluation.

Both structured proposal phases passed:

```text
coverage calibration: 6/6 evaluable and compliant
  within-condition categorical envelope: 0
  between-condition median: 2.2360679775

balanced-cut validation: 6/6 evaluable and compliant
  within-condition categorical envelope: 0
  between-condition median: 2.2360679775
```

The first six scientific calls used 104,844 tokens, 19.53% of GCF-R1. All 12 scientific proposal calls used 209,975 tokens; including preflight, proposal-stage usage was 227,467 tokens. The calibration and validation record SHA-256 values are respectively `f5ccbbfd94badff89088771d38c33eb8d158f4d470903b1b23775721ceda0361` and `53f07b7dbf4fbcc15043f9ee4db0ea6aa1595b874bcbe35f016998b758a8b48b`.

The proposal evidence establishes `STRUCTURED_MECHANISM_OBJECT_CHANNEL_DETECTED_ON_TWO_DEV_STATES`: the brief reliably controlled the frozen categorical object under same-state replication and one cross-family validation state. This remains development calibration evidence, not generalization or value.

All 12 isolated implementation calls were evaluable and produced valid sources. Source structure separated in `2/2` states, but hidden behavior separated in `0/2`:

```text
coverage source:   between 1.26096 > within 0.98021 + 0.05
coverage behavior: between 0.01938 < within 0.02362 + 0.02

cut source:        between 0.98850 > within 0.83156 + 0.05
cut behavior:      between 0.20270 < within 0.38729 + 0.02
```

Three implementation calls exceeded the frozen 30,000-token ceiling (`37,205`, `37,717`, and `53,655`; median `19,875`, maximum `53,655`). Implementation usage was 301,577 tokens. Total usage was 25 calls and 529,044 tokens with summed provider wall time 755.502 seconds.

Because the resource gate failed, the authoritative final verdict is `GCF_V2_R3_NOT_EVALUABLE_RESOURCE_CEILING`, matching the machine report's `GCF_V2_NOT_EVALUABLE`. The `2/2` source and `0/2` behavior observations remain diagnostics and cannot establish a semantic negative. The final report SHA-256 is `8af5fb12a42e72e0c23baedc94d30095afebd23c4b5fa72d2c7fb0042f4cd823`.

Implementation validation, fresh value trial, and SI-3 remain closed. R3 must not be rerun with a larger ceiling, changed probe, new margin, or extra replicates. A future Executable Mechanism Contract may use new states and predeclared runtime obligations/counters, but it requires a new protocol and cannot reinterpret R3 as a value result.

## Verdict boundaries

```text
GCF_V2_PROPOSAL_CALIBRATION_FAILED
GCF_V2_NOT_EVALUABLE
STRUCTURED_MECHANISM_IMPLEMENTATION_INVALID
STRUCTURED_OBJECT_TO_IMPLEMENTATION_NOT_DETECTABLE
STRUCTURED_IMPLEMENTATION_WITHOUT_BEHAVIOR_MEDIATION
STRUCTURED_MECHANISM_MEDIATION_DETECTED_ON_CALIBRATION
```

The final positive verdict remains calibration evidence. Its only budget consequence is `ELIGIBLE_TO_PREREGISTER_INDEPENDENT_GCF_V2_VALIDATION`; fresh search-value budget and SI-3 remain closed.

## Entrypoints

```powershell
$env:PYTHONPATH = "src"
$codexCli = Join-Path $env:USERPROFILE ".codex\.sandbox-bin\codex.exe"

python -m discoveryos gcf-v2-seal-structured `
  --workspace runs/gcf-v2-structured-mediation-r3 `
  --model gpt-5.6-sol --reasoning-effort medium --codex-command $codexCli --max-workers 2

python -m discoveryos gcf-v2-preflight-provider `
  --workspace runs/gcf-v2-structured-mediation-r3 --manifest-digest <sealed-digest> `
  --model gpt-5.6-sol --reasoning-effort medium --codex-command $codexCli

python -m discoveryos gcf-v2-calibrate-proposals `
  --workspace runs/gcf-v2-structured-mediation-r3 --manifest-digest <sealed-digest> `
  --model gpt-5.6-sol --reasoning-effort medium --codex-command $codexCli

python -m discoveryos gcf-v2-validate-proposals `
  --workspace runs/gcf-v2-structured-mediation-r3 --manifest-digest <sealed-digest> `
  --model gpt-5.6-sol --reasoning-effort medium --codex-command $codexCli

python -m discoveryos gcf-v2-run-implementation `
  --workspace runs/gcf-v2-structured-mediation-r3 --manifest-digest <sealed-digest> `
  --model gpt-5.6-sol --reasoning-effort medium --codex-command $codexCli
```

The create-once manifest binds the repository commit, implementation files, task/evaluator artifacts, provider version, model/settings, schemas, prompts, schedules, token ceilings, probes, margins, and local environment observation. Remote execution is not authorized by this protocol.
