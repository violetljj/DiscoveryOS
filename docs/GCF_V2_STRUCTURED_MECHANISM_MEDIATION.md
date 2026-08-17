# GCF-V2 Structured Mechanism Mediation

## Current status

```text
GCF_V2_STRUCTURED_MEDIATION_PROTOCOL_IMPLEMENTED
GCF_V2_R1_NOT_EVALUABLE_PROVIDER_SCHEMA
GCF_V2_R2_NOT_YET_SEALED
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

R2 first performs one non-scientific provider/schema preflight using the exact proposal provider and schema. A failure blocks the scientific schedule after one call and preserves the CLI transport diagnostic in the receipt.

Two new development-only tasks are frozen before calls: weighted coverage and balanced graph cut, each with new evaluator seeds. For each state, both mutually exclusive conditions receive three independent proposal draws. After preflight, the first scientific gate costs 12 calls, each capped at 8,000 input-plus-output tokens.

The proposal gate requires all draws to be evaluable and contract-compliant, resource ceilings to pass, and between-condition categorical separation to exceed the maximum same-condition stochastic distance in both states. Failure blocks implementation with zero implementation calls.

Only after proposal admission may the 12 corresponding Mechanism Objects receive isolated implementation calls, each capped at 30,000 tokens. Source and hidden-behavior distances are separately compared against their state-local within-condition envelopes plus frozen margins. Utility is recorded but excluded from mediation admission.

The maximum calibration cost is 25 calls including preflight. The first scientific stopping point has a predeclared aggregate ceiling of 96,000 tokens, under 18% of the GCF-R1 calibration usage ceiling implied by its observed 536,852-token run.

## R1 executability closeout

R1 sealed manifest `bdefaf6f50e6cfd2676f9eb32f95d9f42fbd44817b65f5717f90c52565bc22bc` at commit `c4fd8a4`. All 12 scheduled proposal invocations exited at the provider/schema boundary with CLI exit code `1`, zero reported tokens, zero contract-compliant objects, and zero evaluable draws. The create-once calibration record SHA-256 is `4e40a0ce0d8a41731a294154081f4d56210f021c7fa1b7c2f21d9ea914eaad88`.

The official Structured Outputs reference documents a supported JSON Schema subset and does not include `uniqueItems`; R1 used that keyword on four arrays. R1 is therefore closed as `GCF_V2_R1_NOT_EVALUABLE_PROVIDER_SCHEMA`, not as a semantic failure. Implementation remained blocked with zero calls. R2 removes the unsupported keyword, retains manual uniqueness validation after parsing, and adds the one-call preflight. R1 artifacts are not modified or replayed.

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
  --workspace runs/gcf-v2-structured-mediation-r2 `
  --model gpt-5.6-sol --reasoning-effort medium --codex-command $codexCli --max-workers 2

python -m discoveryos gcf-v2-preflight-provider `
  --workspace runs/gcf-v2-structured-mediation-r2 --manifest-digest <sealed-digest> `
  --model gpt-5.6-sol --reasoning-effort medium --codex-command $codexCli

python -m discoveryos gcf-v2-calibrate-proposals `
  --workspace runs/gcf-v2-structured-mediation-r2 --manifest-digest <sealed-digest> `
  --model gpt-5.6-sol --reasoning-effort medium --codex-command $codexCli

python -m discoveryos gcf-v2-run-implementation `
  --workspace runs/gcf-v2-structured-mediation-r2 --manifest-digest <sealed-digest> `
  --model gpt-5.6-sol --reasoning-effort medium --codex-command $codexCli
```

The create-once manifest binds the repository commit, implementation files, task/evaluator artifacts, provider version, model/settings, schemas, prompts, schedules, token ceilings, probes, margins, and local environment observation. Remote execution is not authorized by this protocol.
