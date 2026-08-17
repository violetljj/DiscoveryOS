# EMC-R1 Executable Mechanism Contract

## Status

```text
EMC_R1_PROTOCOL_IMPLEMENTED
EMC_R1_NOT_EVALUABLE_IMPLEMENTATION_ENUM
EMC_R2_PROTOCOL_IMPLEMENTED
EMC_R2_INSTRUMENTATION_SENSITIVITY_PASSED
EMC_R2_PROVIDER_PREFLIGHT_PASSED
EMC_R2_CALIBRATION_NOT_EVALUABLE_RESOURCE_AND_DUPLICATE_CALL
EMC_R2_VALIDATION_BLOCKED_NOT_RUN
NO_EXECUTABLE_MECHANISM_CONTRACT_ADMITTED
```

EMC-R1 was sealed at commit `cc95730`. Its E0 instrumentation sensitivity passed 4/4 controls with zero model calls, but E1 stopped before provider invocation because the implementation request referenced a nonexistent `GenerationKind.STRUCTURAL_REWRITE`. R1 is closed as `EMC_R1_NOT_EVALUABLE_IMPLEMENTATION_ENUM`: zero provider calls, zero tokens, and no semantic result. Its create-once root is not modified.

EMC-R2 changes only that executability blocker to the existing `GenerationKind.PROPOSAL`, uses a new protocol ID, record names, state IDs, and workspace, and otherwise retains the R1 mechanism objects, compiler, states, instrumentation, schedule, resource ceilings, gates, and claim ceiling. Neither version modifies, replays, or reinterprets GCF-V2. The narrow question remains whether a generator that receives a frozen Structured Mechanism Object plus a deterministically compiled Executable Mechanism Contract produces implementations whose required and forbidden paths are independently observed at runtime.

## R1 closeout

R1 manifest digest `3e9f31124bea203efdd4fec50a930ab71c09d878ac56308c22956f8e445edba6` and file SHA-256 `7266de0144e70d8054928dadeef170b3cd7ad80cee5930a6448ee07e42c4e4b5` bind commit `cc95730`. E0 passed all four controls; its record SHA-256 is `8fc76d79a3f3a9d7b4f6d0ee24f2683bd82045aec39779366c721219e6be78dc`. E1 then failed before provider invocation. R1 used zero provider calls and zero tokens and is permanently closed.

## R2 result

R2 was sealed at commit `fb643f5`. Manifest digest is `d4cd809cca120a139c4ef8b6faa01cf745c4361f4254313c14fd740a6196c684`; manifest file SHA-256 is `b169cf6ed32d054394807fcf8e3c38f49811a84a91cdf8976d0a3b8e7af9a210`.

E0 again passed 4/4 controls with zero model calls. Record SHA-256 is `5c93106a0b80e517e7bd821cd429130ac04ea85c0acc64466dc4372bd6e6f8b6`.

E1 passed with one evaluable call, 19,246 tokens, and 43.900 provider seconds. The generated implementation was source-valid and passed static contract, external runtime counters, and invariant canary. Record SHA-256 is `bbc82e2f29448df318567de04a4ad137cc04c7ea45fcefd75c21874a4faaee91`.

E2 produced six unique create-once draw checkpoints. All 6/6 were evaluable, hidden-evaluator valid, static-contract compliant, runtime-contract compliant, and invariant-canary compliant. Direct construction had the stable counter signature `[1,0,0]`; post-construction repair had `[1,1,0]`. Thus the checkpoint diagnostics show the frozen harness observing the two requested execution paths with zero within-condition categorical variation.

Those diagnostics are not an admitted scientific result. One of the six calls used 61,681 tokens, exceeding the frozen 60,000 ceiling by 1,681. In addition, an interrupted aggregation left five visible checkpoints while the sixth worker was still late; a resume launched that missing draw, then failed when the first worker won the create-once write. This proves at least one duplicate provider invocation for the same draw. The six admitted checkpoints plus preflight report 7 calls and 255,420 tokens, but actual usage is at least 8 calls and greater than 255,420 tokens; the exact duplicate-call usage was not persisted and cannot be reconstructed from the authoritative records.

The machine calibration record is therefore bounded by the stricter scoped verdict `EMC_R2_CALIBRATION_NOT_EVALUABLE_RESOURCE_AND_DUPLICATE_CALL`. Its record SHA-256 is `99309cb2edd503c6d351f8097b0de67d324ee5e124e87c7034f65d2a77024ebb`. E3 remained blocked with zero validation calls and zero fresh search-value tasks.

R2 is closed. Do not raise the ceiling, alter checkpoint/resume semantics, add replicates, or replay the same states to convert the diagnostic 6/6 into a pass. Any future protocol must use a new scientific question and fresh states; a mechanics-only repair may separately ensure that in-flight worker ownership is durably known before resume.

## Post-R2 mechanics repair

The provider boundary now writes a request-bound, create-once owner claim before entering an external call and a terminal response/usage record immediately after a normal return or provider failure. A complete terminal record can be recovered without another provider call. A claim without a terminal record is permanently fail closed: process exit, elapsed time, or a missing draw checkpoint is not treated as proof that the external call did not occur. A phase-level audit blocks every new worker when any orphan claim exists. Concurrent, completed-recovery, provider-failure-recovery, orphaned-claim, and binding-tamper fixtures cover this behavior.

This is `EMC_PROVIDER_INVOCATION_JOURNAL_MECHANICS_READY` only. It does not mutate either consumed EMC root, reconstruct R2 usage, admit executable transmission, or authorize validation/search-value work.

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
python -m discoveryos emc-r2-seal --workspace runs/emc-r2-executable-contract --model gpt-5.6-sol --codex-command $codexCli --reasoning-effort medium
python -m discoveryos emc-r2-instrumentation --workspace runs/emc-r2-executable-contract --manifest-digest <digest> --model gpt-5.6-sol --codex-command $codexCli --reasoning-effort medium
python -m discoveryos emc-r2-preflight --workspace runs/emc-r2-executable-contract --manifest-digest <digest> --model gpt-5.6-sol --codex-command $codexCli --reasoning-effort medium
python -m discoveryos emc-r2-calibrate --workspace runs/emc-r2-executable-contract --manifest-digest <digest> --model gpt-5.6-sol --codex-command $codexCli --reasoning-effort medium
python -m discoveryos emc-r2-validate --workspace runs/emc-r2-executable-contract --manifest-digest <digest> --model gpt-5.6-sol --codex-command $codexCli --reasoning-effort medium
```

The workspace becomes consumed when a scientific implementation phase runs. Do not change contracts, states, probes, replicates, gates, or ceilings in place after observing results.
