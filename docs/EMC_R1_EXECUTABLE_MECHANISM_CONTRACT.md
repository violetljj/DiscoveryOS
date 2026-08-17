# EMC-R1 Executable Mechanism Contract

## Status

```text
EMC_R1_PROTOCOL_IMPLEMENTED
EMC_R1_NOT_YET_SEALED
```

EMC-R1 is a new protocol and create-once workspace. It does not modify, replay, or reinterpret any GCF-V2 root. Its narrow question is whether a generator that receives a frozen Structured Mechanism Object plus a deterministically compiled Executable Mechanism Contract produces implementations whose required and forbidden paths are independently observed at runtime.

## Claim ceiling

The maximum positive claim is:

```text
EXECUTABLE_MECHANISM_CONTRACT_TRANSMISSION_ON_TWO_NEW_DEV_STATES_ONLY
```

It cannot establish mechanism utility, search value, general generator obedience, algorithm superiority, fresh-task value, or production readiness. Hidden evaluator score is record-only.

## Frozen interface

The deterministic compiler maps each Mechanism Object to:

- exact required function names;
- forbidden function names;
- required entrypoint call edges;
- externally collected runtime counter bounds;
- API, feasibility, input-immutability, and standard-library invariants;
- a content digest over the complete executable contract.

The implementation request sees the task, base source, canonical Mechanism Object, and executable contract. It does not see the condition ID, instrumentation source, or hidden evaluator. Candidate-authored counters are non-authoritative. A separate harness uses Python profiling to observe calls originating from `algorithm.py`, and public plus hidden task evaluators independently check validity.

## Cheap-first gates

1. `E0_INSTRUMENTATION_SENSITIVITY_NO_MODEL`: two positive and two negative synthetic controls must be classified exactly; zero model calls.
2. `E1_PROVIDER_AND_RESOURCE_PREFLIGHT_ONE_CALL`: one non-scientific schema/provider call must be evaluable within 60,000 tokens.
3. `E2_IMPLEMENTATION_CALIBRATION_SIX_CALLS`: three independent draws for each of two contracts on a new assignment state. Every draw must be evaluable, source-valid, invariant-valid, and pass static plus runtime contract checks; the two runtime counter signatures must separate with zero within-condition categorical variation.
4. `E3_INDEPENDENT_IMPLEMENTATION_VALIDATION_SIX_CALLS`: the same frozen requirements on a new coverage state, available only after E2 passes.

The 60,000-token per-call ceiling is a new-protocol executability bound based on the previously observed GCF-V2 maximum of 53,655 tokens. It does not alter GCF-V2. The current provider exposes usage after completion, so the frozen gate is a receipt-time ceiling check rather than a claimed transport-level hard stop.

## Failure semantics

- Instrumentation mismatch blocks every model call.
- Provider or resource failure is `NOT_EVALUABLE`, not a semantic negative.
- Invalid task behavior is distinct from static contract failure.
- Static source compliance without independently observed runtime activation fails the runtime gate.
- Calibration failure blocks validation.
- A positive validation remains two-state development evidence and does not authorize a fresh value trial.

## Commands

```powershell
$codexCli = Join-Path $env:USERPROFILE ".codex\.sandbox-bin\codex.exe"
$env:PYTHONPATH = "src"
python -m discoveryos emc-r1-seal --workspace runs/emc-r1-executable-contract --model gpt-5.6-sol --codex-command $codexCli --reasoning-effort medium
python -m discoveryos emc-r1-instrumentation --workspace runs/emc-r1-executable-contract --manifest-digest <digest> --model gpt-5.6-sol --codex-command $codexCli --reasoning-effort medium
python -m discoveryos emc-r1-preflight --workspace runs/emc-r1-executable-contract --manifest-digest <digest> --model gpt-5.6-sol --codex-command $codexCli --reasoning-effort medium
python -m discoveryos emc-r1-calibrate --workspace runs/emc-r1-executable-contract --manifest-digest <digest> --model gpt-5.6-sol --codex-command $codexCli --reasoning-effort medium
python -m discoveryos emc-r1-validate --workspace runs/emc-r1-executable-contract --manifest-digest <digest> --model gpt-5.6-sol --codex-command $codexCli --reasoning-effort medium
```

The workspace becomes consumed when a scientific implementation phase runs. Do not change contracts, states, probes, replicates, gates, or ceilings in place after observing results.
