# GCF-R1 Real Mechanism Brief Transmission

## Preregistered status

```text
GCF_R1_REAL_MECHANISM_BRIEF_PROTOCOL_IMPLEMENTED
NOT_YET_SEALED
NO_MODEL_CALLS_AUTHORIZED_BEFORE_SEAL
NO_FRESH_TASK_ACCESS
```

GCF-R1 is the first real Generator Conditioning Fidelity diagnosis. It is an experimental-capability use, not an algorithm search improvement. It asks only:

> Holding task, base source, model, prompt, budget, evaluator, and stochastic distribution fixed, does changing one mechanism brief produce stagewise structural and hidden-behavior separation beyond same-condition stochastic null?

Passing can establish `MECHANISM_BRIEF_SEMANTIC_TRANSMISSION_DETECTED` on consumed development states. It cannot establish mechanism utility, search value, system superiority, or production readiness, and it does not itself open a fresh trial.

## Consumed state split

The state frame is inherited without replacement from the completed, immutable CIB-R1 Parent protocol:

- calibration: `capacitated_assignment_delta` and `capacitated_assignment_eta`;
- validation: `balanced_cut_delta`, `budgeted_coverage_epsilon`, and `capacitated_assignment_epsilon`.

The validation surface spans balanced graph cut, budgeted weighted coverage, and capacitated assignment. The base source in every state is the frozen CIB-R1 incumbent. No SI-2 confirmation, final blind, or fresh task is accessed.

## Single-variable intervention

Condition A is `CONSTRUCTIVE_GREEDY`: construct the full solution in one deterministic marginal priority pass, with no optimization loop after construction.

Condition B is `ITERATIVE_LOCAL_IMPROVEMENT`: start feasible, then repeatedly apply a bounded improving swap, add-remove, reassignment, or partition move until convergence or a deterministic bound.

The condition briefs explicitly prohibit the competing mechanism. Task question, base source, failure context, model/settings, prompt template, token ceiling, and evaluator remain identical. Each branch is a separate provider request. The model is never asked to label its own compliance.

## Frozen staged contract and probes

One call returns four bound fields:

```text
proposal
implementation_source
repair_source
final_source
```

Stage signatures are deterministic lexical plus Python-AST mechanism features. The final hidden-behavior signature is the frozen vector of six task probe scores plus validity. Final utility is recorded to describe the response but is excluded from GCF-2.

For each state:

```text
A/A x 2  same-condition null
B/B x 2  same-condition null
A/B x 2  calibration intervention
A/B x 3  validation intervention
```

The state-local null envelope is the maximum A/A or B/B distance. An intervention stage survives only when median A/B distance exceeds null plus the predeclared stage margin `0.05`. Hidden behavior changes only when its median distance exceeds null plus `0.02`. Margins are not fit to intervention outputs.

The frozen total is 66 model calls: 24 calibration calls and, only if calibration passes, 42 validation calls. Every branch has a 50,000 input-plus-output token ceiling and all final sources must execute validly for semantic admission.

## Gates and verdicts

Calibration requires proposal detectability on both calibration states, all branches evaluable, and resource ceilings respected. If it fails, validation is blocked and the channel closes at the observed bottleneck.

Validation requires at least two of three states at each admitted boundary. The ordered verdicts are:

```text
MECHANISM_BRIEF_NOT_DETECTABLE_AT_PROPOSAL
MECHANISM_BRIEF_PROPOSAL_TO_IMPLEMENTATION_FAILED
MECHANISM_BRIEF_REPAIR_HOMOGENIZATION_DETECTED
MECHANISM_BRIEF_FINAL_SURVIVAL_NOT_ESTABLISHED
MECHANISM_BRIEF_STRUCTURAL_RESPONSE_WITHOUT_BEHAVIOR_TRANSMISSION
MECHANISM_BRIEF_SEMANTIC_TRANSMISSION_DETECTED
```

Provider/schema failures are `GCF_R1_NOT_EVALUABLE`. Executable but invalid final sources are recorded separately as `MECHANISM_BRIEF_RESPONSE_NOT_SEMANTICALLY_VALID`; invalidity cannot become semantic transmission.

Even on a positive verdict, the budget decision is only `ELIGIBLE_TO_PREREGISTER_INDEPENDENT_GCF3_VALUE_TRIAL`. A new value trial still requires a separate contract, hypothesis, calibration, margin, and independent surface.

## Entrypoints

```powershell
$env:PYTHONPATH = "src"
$codexCli = Join-Path $env:USERPROFILE ".codex\.sandbox-bin\codex.exe"

python -m discoveryos gcf-r1-seal-mechanism-brief `
  --workspace runs/gcf-r1-mechanism-brief `
  --source-workspace runs/cib-r1-parent-real `
  --source-manifest-digest f14902c185470fb9fcb71bf28a7eb4a3c9562d4109db742d9147f47112fc0b4e `
  --model gpt-5.6-sol --reasoning-effort medium --codex-command $codexCli --max-workers 2

python -m discoveryos gcf-r1-calibrate-mechanism-brief `
  --workspace runs/gcf-r1-mechanism-brief --manifest-digest <sealed-digest> `
  --model gpt-5.6-sol --reasoning-effort medium --codex-command $codexCli

python -m discoveryos gcf-r1-run-mechanism-brief `
  --workspace runs/gcf-r1-mechanism-brief --manifest-digest <sealed-digest> `
  --model gpt-5.6-sol --reasoning-effort medium --codex-command $codexCli
```

The ignored run root is create-once and resumable by branch checkpoint. After sealing, code, model, settings, schema, prompt, states, conditions, margins, schedule, and evidence bindings must not change.
