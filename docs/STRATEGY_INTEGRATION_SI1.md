# Strategy Integration SI-1: Shinka-style Parent Selection + Novelty Core

## Status and claim ceiling

```text
CONTROLLER_BUDGET_REACHABILITY_REPAIRED
SEARCH_VALUE_MVP0_FAIL
DISCOVERYOS_SEARCH_VALUE_NOT_YET_ESTABLISHED
```

SI-1 is a mechanism integration and consumed-task development stage. Its maximum mechanics verdict is `SHINKA_PARENT_NOVELTY_MECHANICS_READY`; its pilot may report `DEVELOPMENT_SIGNAL_POSITIVE`, `DEVELOPMENT_SIGNAL_NEUTRAL`, or `DEVELOPMENT_SIGNAL_NEGATIVE`. It cannot report `SEARCH_VALUE_ESTABLISHED` or `SHINKA_MECHANISM_ADMITTED`.

The official-to-native mapping is frozen in [SHINKA_MECHANISM_MAPPING.md](SHINKA_MECHANISM_MAPPING.md).

## Four-arm development protocol

The runner `strategy-integration-si1` uses one already-consumed MVP-0 task from each of the three existing task families:

- `bounded_knapsack_alpha`
- `conflict_coloring_alpha`
- `load_balance_alpha`

No fresh scientific corpus is opened. For every task the arms are:

| Arm | Parent policy | Novelty policy |
|---|---:|---:|
| `CORE` | off | off |
| `CORE_PARENT` | on | off |
| `CORE_NOVELTY` | off | on |
| `CORE_PARENT_NOVELTY` | on | on |

All arms share the same task snapshot, starting candidate, Local Patch operator, provider/model/settings, evaluator, controller action ordering, three-step limit, fidelity, and `100,000` token / `1,800` wall-second / `300` CPU-second envelope. Structural Escape, promotion, model bandits, and additional operators are disabled for attribution. Novelty arms freeze two total generation attempts per action for this small pilot; the worst case is preflight-reserved.

Both `--model` and `--reasoning-effort` are mandatory launch parameters. The sealed manifest records their exact values; the runner has no silent SI-1 model or effort default.

Independent task arms execute concurrently up to three workers. Arms for the same task run in separate waves so Git worktree bookkeeping for one repository is not mutated concurrently.

## Mechanics acceptance

Deterministic tests cover:

- quality exploitation and non-zero exploration;
- parent exposure deconcentration, invalid exclusion, archive/incumbent eligibility, seed sensitivity, receipt replay, and no fabricated structural roots;
- exact and near-duplicate paths, novel acceptance, bounded exhaustion, receipt replay, and retry diagnostics;
- worst-case novelty budget preflight;
- the real `PARENT → LOCAL_PATCH → NOVELTY_CHECK → RESAMPLE → ACCEPT → EVALUATE → SETTLE` loop;
- rejected duplicate receives no evaluation and prior evidence payload remains byte-equivalent as canonical data.

Pilot results are appended only after mechanics pass and the consumed-task run finishes. Old MVP-0 and MVP0-BR evidence files are never rewritten.

## Consumed-task development outcome

The completed R3 pilot froze `gpt-5.6-sol` at reasoning effort `medium` through `codex-cli 0.147.0`. Its sealed manifest digest is `f555a90aa1312bba42075a1b08886f93bef04b032d2b134e91fcfccbf2595e4f`.

| Arm | Median final improvement | Median anytime AUC | Total tokens | Valid candidate rate | Effective parents | Duplicate evaluations avoided | Resample tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| `CORE` | 0.41094003 | 0.32462208 | 181,898 | 0.8889 | 3.0000 | 0 | 0 |
| `CORE_PARENT` | 0.41094003 | 0.33187517 | 181,153 | 0.8889 | 1.8899 | 0 | 0 |
| `CORE_NOVELTY` | 0.41094003 | 0.33321483 | 193,083 | 0.6667 | 2.6300 | 2 | 20,960 |
| `CORE_PARENT_NOVELTY` | 0.41094003 | 0.32646309 | 182,857 | 1.0000 | 2.6667 | 1 | 20,426 |

Parent selection did not increase realized parent diversity in this three-step pilot and did not improve final performance. Novelty rejection avoided three duplicate evaluations across its two arms, at the cost of two additional LLM calls, 41,386 tokens, and 67.89 seconds of generation wall time. No arm improved later marginal search value over `CORE`; all reported 0.00555556. Structural-root diversity remains `null` because SI-1 did not introduce a reliable root semantic.

The original R3 aggregate used strict receipt-count equality and therefore produced a false `MECHANICS_NOT_READY` when a budget-preflight STOP correctly wrote one extra parent-selection receipt. The original report remains immutable. The final `si1-development-audited-report-v2.json` is an append-only correction bound to the original report digest, the superseded first audit digest, manifest digest, raw ledgers, and corrected analysis-code digest. It verifies executed-action step coverage, aggregates valid-candidate rate from gate-feasible policy metrics, and records zero additional model calls.

Final bounded verdicts:

```text
SHINKA_PARENT_NOVELTY_MECHANICS_READY
DEVELOPMENT_SIGNAL_POSITIVE
DISCOVERYOS_SEARCH_VALUE_NOT_YET_ESTABLISHED
```

The positive development signal is caused only by fewer duplicate evaluations. It is not parent-selection value, search-value admission, generalization evidence, or Shinka mechanism admission. The stop rule is satisfied; SI-1 does not proceed to fresh admission or add further strategy mechanisms.
