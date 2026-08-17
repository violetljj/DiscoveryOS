# CMI Search Transmission Autopsy R1

## Status

```text
CMI_SEARCH_TRANSMISSION_AUTOPSY_R1_COMPLETE
CMI_DESCENDANT_COMPETITION_FAILURE_DETECTED_ON_CONSUMED_V3_TRACES
CMI_SELECTION_INTEGRATION_DEFECT_NOT_ESTABLISHED
FORCED_RETENTION_DOWNSTREAM_VALUE_NOT_IDENTIFIABLE_OFFLINE
CMI_COMPOUNDING_SEARCH_VALUE_NOT_ESTABLISHED
DO_NOT_OPEN_FRESH_CMI_SEARCH_BUDGET
```

This is a zero-model, zero-evaluator autopsy of the six consumed CMI Search Value R1 V3 tasks. It binds the closed V3 manifest `5c1395d78efc1b102896471655cc9cf83b7d61585592172712b92a4191233d3b`, V3 report SHA-256 `de4850ae8c75bec35455e197356bd0dc608d47c7e6983a9a9025617ccea2a39b`, CMI-R7 report SHA-256 `3072e74c1a0114920f98c7930097a5488dd8a50763709a073513a1ef4dca763f`, every V3 task receipt, and the exact treatment/shared-prefix ledgers. It does not modify the consumed V3 root, call a provider, rerun an evaluator, or consume a fresh task.

The create-once autopsy record SHA-256 is `45e960bcad90ee0f777e202f089051662b6cb5450825fe1f97f32fc0f60b8b7d`.

## Result

The observed transmission funnel remains:

```text
opportunity -> eligible -> invoked -> accepted -> retained -> CMI parent -> contribution
     6             5          5          5           0           0             0
```

The autopsy localizes the first failure more precisely than the aggregate funnel. All five invoked CMI descendants were technically valid, but all five failed the frozen score threshold. None exceeded the active incumbent or the simultaneous CMI-disabled intervention.

| Category | Eligible | CMI above incumbent | CMI above control intervention | Median CMI minus incumbent | Median gap to retention threshold |
|---|---:|---:|---:|---:|---:|
| Capacitated Assignment | 3 | 0 | 0 | `-0.03908327` | `0.04208327` |
| Budgeted Weighted Coverage | 2 | 0 | 0 | `-0.01007647` | `0.01507647` |

The R7 and V3 evidence agrees at the declared objective level: both use the same supported categories and per-category score resolutions, and V3 emitted the same frozen per-category CMI Operator output digests observed in R7. Exact cross-protocol evaluator binary identity is not claimed because evaluator artifacts are task-specific. The observed reversal is therefore not evidence that V3 selection rewarded a different declared objective. It is consistent with the same fixed CMI decomposition being useful against the weaker R7 incumbents but inferior after the two-step Local Patch prefix produced stronger V3 incumbents.

The immediate diagnosis is `CMI_DESCENDANT_COMPETITION_FAILURE_DETECTED_ON_CONSUMED_V3_TRACES`, not a selection-policy defect. Forced retention would first replace the active parent with a lower-scoring candidate. These traces do not support weakening the frozen selection rule or spending fresh budget on another CMI-on/off search trial.

## Forced-retention boundary

The V3 task receipts serialize `observations[].parent_id` as a sequential observation-chain proxy. For all five eligible tasks, that proxy points from the downstream observation to the CMI observation. It is not the authoritative generation lineage.

The treatment ledgers' immutable `CandidateSpec.parent_ids` and the V3 `causal_trace` agree that every actual downstream Local Patch candidate was generated from the retained prefix incumbent, not from the rejected CMI candidate. Therefore the frozen run contains zero cached descendants conditioned on a CMI parent.

The autopsy can identify the immediate forced-retention effect—CMI was below incumbent in `5/5` eligible tasks—but cannot identify downstream compounding from existing offline evidence. Reusing the sequential observation proxy as if it were real parentage would contradict the ledger. Running a new provider continuation would be a new consumed-task intervention protocol, not an offline replay, and was not performed here.

## Interpretation and next gate

CMI-R7 remains valid: the Operator produced positive local causal value on its frozen fresh states. V3 also remains valid: end-to-end search value was not established. The autopsy shows that the missing bridge is already broken before retention because the current Operator is not incumbent-monotonic after a strong search prefix.

The next allowed question is narrower than `CMI x Selection Integration`: a separately frozen consumed-task protocol may test whether an incumbent-conditioned or monotonic CMI Operator can preserve the prefix incumbent's useful structure while adding the admitted basin-escape decomposition. It must establish candidate competition value before any forced-retention, lineage-continuation, selection-policy change, or fresh search-value proposal.

Claim ceiling remains:

```text
CONSUMED_V3_TRACE_DIAGNOSTIC_ONLY_NO_SEARCH_VALUE_OR_SUPERIORITY_CLAIM
```

## Reproduction

```powershell
$env:PYTHONPATH = "src"
python -m discoveryos cmi-search-transmission-autopsy `
  --workspace runs/cmi-search-value-r1-v3 `
  --manifest-digest 5c1395d78efc1b102896471655cc9cf83b7d61585592172712b92a4191233d3b `
  --source-report-sha256 de4850ae8c75bec35455e197356bd0dc608d47c7e6983a9a9025617ccea2a39b `
  --cmi-r7-report E:/DiscoveryOS/runs/cmi-r7-fresh-causal-replication/result-artifacts/records/cmi-r7-fresh-causal-report.json `
  --cmi-r7-report-sha256 3072e74c1a0114920f98c7930097a5488dd8a50763709a073513a1ef4dca763f `
  --output-workspace runs/cmi-search-transmission-autopsy-r1
```

The output is create-once. Reproduction requires a new output workspace and must not write into the consumed V3 source root.
