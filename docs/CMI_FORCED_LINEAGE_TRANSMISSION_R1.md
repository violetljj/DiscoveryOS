# CMI Forced-Lineage Transmission R1

## Protocol status

```text
CMI_FORCED_LINEAGE_TRANSMISSION_R1_PROTOCOL_IMPLEMENTED
CMI_FORCED_LINEAGE_STEPPING_STONE_VALUE_UNKNOWN
NO_FRESH_TASK_BUDGET
NO_SELECTION_POLICY_CHANGE
```

## Question

The closed CMI Search Value R1 V3 traces establish that all five invoked CMI descendants were valid but immediately weaker than both the retained incumbent and the simultaneous control descendant. They do not contain a real `CMI parent -> child -> grandchild` lineage, so downstream stepping-stone value remains unidentified.

R1 asks exactly one consumed-development question:

> Can a weaker CMI descendant generate better downstream descendants than matched control-descendant and incumbent starting parents?

It does not retry Search Value R1, change the CMI Operator, modify selection, grant a retention quota or bonus, or open a fresh/SEALED task.

## Frozen population and arms

The complete population is the five eligible, already-consumed V3 states: three Capacitated Assignment and two Budgeted Weighted Coverage states. Generation 0 source code and scores are loaded from the immutable V3 task receipts, treatment/control ledgers and content-addressed candidate artifacts.

| Arm | Forced Generation 0 parent | Purpose |
|---|---|---|
| A `INCUMBENT_LINEAGE` | retained prefix incumbent | original local-search baseline |
| B `CONTROL_DESCENDANT_LINEAGE` | simultaneous V3 control descendant | controls for changing parent |
| C `CMI_DESCENDANT_LINEAGE` | simultaneous V3 CMI descendant | tests CMI stepping-stone transmission |

Every arm uses the same `bounded_llm_local_patch_v1` generator, prompt template, model/settings, `80,000` token ceiling, `1,200s` wall ceiling, evaluator and two-child horizon. Arm order follows a frozen Latin rotation by state index. A valid child is forcibly used as the next generation's parent regardless of fitness; an invalid child terminates that lineage and is not converted into a scientific loss.

## Endpoints and gates

Generation 0 never counts as success. The primary endpoint is:

```text
best utility among newly generated downstream descendants
CMI_DESCENDANT_LINEAGE minus CONTROL_DESCENDANT_LINEAGE
```

Anytime AUC starts at the forced Generation 0 parent and integrates over the matched downstream token ceiling. Incumbent-lineage comparisons are diagnostic rather than the primary gate.

The strict positive gate requires all of the following:

- all five states and all three arms are technically evaluable;
- exactly two provider calls per arm;
- C beats B by more than the task resolution on all five states, with zero ties or losses;
- every state in both families is positive;
- median primary delta and median anytime-AUC delta are strictly positive.

Passing can emit only `CMI_STEPPING_STONE_SIGNAL_DETECTED_ON_CONSUMED_V3_STATES` and authorize a consumed-development hypothesis about non-myopic archive/parent policy. It does not establish end-to-end search value, unseen-task generalization or superiority and does not open fresh budget.

A technically valid failure emits `CMI_FORCED_LINEAGE_VALUE_NOT_ESTABLISHED_ON_CONSUMED_V3_STATES` and closes further CMI Search integration under the current Operator: no fresh CMI task, selection tuning, retention quota, bonus or another lineage extension. Protocol/execution failure remains `NOT_EVALUABLE` and permits only a versioned validity or executability repair.

## Commands

After this implementation is committed and the worktree is clean:

```powershell
$env:PYTHONPATH = "src"
python -m discoveryos cmi-forced-lineage-r1-seal `
  --workspace runs/cmi-forced-lineage-transmission-r1 `
  --source-workspace E:/DiscoveryOS-cmi-search-value-r1/runs/cmi-search-value-r1-v3 `
  --real-provider-preflight E:/DiscoveryOS-cmi-search-value-r1/runs/cmi-search-value-r1-v3-real-provider-preflight/terminal-preflight-report.json `
  --real-provider-preflight-sha256 428c2b214bde79ab445470d4a8120c570de6b1d0ab50f83190029dae25872b61 `
  --model gpt-5.6-sol `
  --reasoning-effort medium `
  --codex-command C:/Users/26442/.codex/.sandbox-bin/codex.exe
python -m discoveryos cmi-forced-lineage-r1-run `
  --workspace runs/cmi-forced-lineage-transmission-r1 `
  --manifest-digest <sealed-manifest-digest> `
  --model gpt-5.6-sol `
  --reasoning-effort medium `
  --codex-command C:/Users/26442/.codex/.sandbox-bin/codex.exe
```

The workspace is create-once. The runner writes one terminal receipt per task and refuses to resume a partial task without a terminal receipt.
