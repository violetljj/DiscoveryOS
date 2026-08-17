# CMI Search Value R1

## Protocol status

```text
CMI_SEARCH_VALUE_R1_V1_NOT_EVALUABLE_RESOURCE_ENVELOPE
CMI_SEARCH_VALUE_R1_V2_NOT_EVALUABLE_INVALID_DESCENDANT_TERMINALIZATION
CMI_SEARCH_VALUE_R1_V3_PROTOCOL_IMPLEMENTED
CMI_SEARCH_VALUE_R1_V3_PREFLIGHT_REQUIRED
CMI_SEARCH_VALUE_NOT_YET_ESTABLISHED
```

CMI Search Value R1 asks one question: on an otherwise identical bounded search, does making the frozen CMI functional-basin-escape Operator available improve final search value? It is the first complete-search comparison authorized by CMI-R7. It does not modify CMI, its Brief, applicability threshold, evaluator, parent rule, Local Patch policy, task selection, or claim ceiling.

V1 sealed manifest `0a82137cdda8d406885b276e20b04308515e78ea5bf461a60c2a5e20e32114e7` at commit `1a3e3b5`, then failed before the first terminal task receipt because four actual provider calls totaled `85,348` tokens against the frozen `80,000` arm ceiling. The last generation correctly settled `BUDGET_EXHAUSTED`, but report aggregation raised instead of emitting a terminal `NOT_EVALUABLE` record. Failure receipt SHA-256 `fde8384ea996e1b588f5ba62b04b7fd71d7da85675eedac2d4b96cb0b7a9f438` admits no scientific output; the partial first task and the entire V1 cohort cannot be reused.

V2 was a resource-only validity repair with a new salt, all-new unscreened cohort and `120,000` ceiling. It failed before its first terminal task receipt when the second prefix descendant was correctly evaluated as `INVALID_MECHANICS/PATCH_APPLY_FAILURE`, but the paired runner then tried to materialize that invalid candidate's source and escalated the expected invalid observation into a process error. Failure receipt SHA-256 `1a40a742f6b2584210eb705146beef44c9d56747230ccd0f244772780324d02a` admits no scientific output; V2 is not reusable.

V3 preserves the V2 resource repair and all scientific semantics, uses another new unscreened cohort, and changes only invalid-descendant terminalization: invalid candidates retain their evidence/failure receipt, are excluded from eligibility and parent replacement, and do not undergo source materialization. Before V3 may seal, the exact runner must complete a real-provider preflight on consumed development tasks.

## Paired search design

The complete population is six unscreened instance-fresh tasks, with three Capacitated Assignment and three Budgeted Weighted Coverage instances. Evaluator seeds and functional-probe seeds are derived from the frozen protocol salt without outcome screening. The tasks are instance-fresh but not distribution-, family-, or evaluator-regime-fresh.

Each task begins with an exact shared two-step Local Patch prefix. This common-random-prefix design gives both scientific arms the same model outputs, evaluator evidence, incumbent, elapsed resource ledger, and opportunity state before the intervention decision.

- If the prefix is not CMI-eligible, both arms share the same two-step Local Patch fallback. The task remains in the population and must tie exactly.
- If eligible, `CMI_DISABLED` uses the default Local Patch action while `CMI_ENABLED` invokes the frozen CMI Operator. Both then run one downstream Local Patch step under the same provider, prompt policy, budget ceiling, evaluator, parent replacement rule, and stopping rule.

The only treatment difference is whether CMI may replace the intervention action at an eligible state. Shared physical model calls are credited independently and identically to both scientific arms; this reduces execution cost without changing per-arm resource accounting.

## Frozen applicability and attribution

An opportunity requires two technically valid prefix descendants and sufficient remaining action budget. Eligibility additionally requires:

- the two generated source digests are distinct;
- their frozen functional signatures are within distance `0.10`;
- their evaluator scores differ by no more than the task resolution;
- the task belongs to one of the two R7-admitted categories.

Every task records:

```text
opportunity
  -> eligibility
  -> invocation
  -> accepted descendant
  -> retained after intervention
  -> downstream Local Patch parentage
  -> downstream retained contribution
```

`downstream retained contribution` requires the CMI candidate to replace the incumbent, become the downstream parent, and leave the final CMI-enabled result ahead of control by at least the frozen task resolution.

## Frozen gates

Search advantage requires all six tasks evaluable, wins greater than losses, zero losses, strictly positive median final-utility and anytime-AUC deltas, and a one-sided exact sign test at alpha `0.10`.

Causal transmission requires at least four eligible invocations, at least one invocation per family, every invoked descendant technically accepted, at least two downstream retained contributions, and at least one contribution per family.

Cost protection requires CMI-enabled model tokens not exceed control, evaluator-call counts match, and aggregate enabled/control elapsed time remain at most `2.0x`.

Only simultaneous passage of Search advantage, Causal transmission, and Cost protection can emit:

```text
CMI_SEARCH_VALUE_ESTABLISHED_ON_FROZEN_ASSIGNMENT_COVERAGE_REGIME
```

Search advantage without transmission emits `SEARCH_ADVANTAGE_OBSERVED_BUT_NOT_ATTRIBUTABLE_TO_CMI`. A valid comparison that fails the positive gate emits `CMI_SEARCH_VALUE_NOT_ESTABLISHED`. Protocol invalidity and execution failure remain `INVALID` or `NOT_EVALUABLE`, never a scientific loss.

## Commands

After the V3 implementation commit is clean, immutable, and has passed real-provider consumed-task preflight:

```powershell
$env:PYTHONPATH = "src"
python -m discoveryos cmi-search-value-r1-seal `
  --workspace runs/cmi-search-value-r1-v3 `
  --cmi-r7-workspace E:/DiscoveryOS/runs/cmi-r7-fresh-causal-replication `
  --cmi-r7-report-sha256 3072e74c1a0114920f98c7930097a5488dd8a50763709a073513a1ef4dca763f `
  --model gpt-5.6-sol `
  --reasoning-effort medium `
  --codex-command C:/Users/26442/.codex/.sandbox-bin/codex.exe
python -m discoveryos cmi-search-value-r1-run `
  --workspace runs/cmi-search-value-r1-v3 `
  --manifest-digest <sealed-manifest-digest> `
  --model gpt-5.6-sol `
  --reasoning-effort medium `
  --codex-command C:/Users/26442/.codex/.sandbox-bin/codex.exe
```

The second command consumes all six exact fresh tasks once. Partial task receipts are retained, but a partial task directory without a terminal create-once receipt fails closed.
