# SI-1R: Parent Effectiveness & Novelty Cost Repair

## Verdict and claim ceiling

```text
SI1_PARENT_EFFECTIVENESS_REPAIRED
SI1_NOVELTY_COST_REPAIRED
DISCOVERYOS_SEARCH_VALUE_NOT_YET_ESTABLISHED
```

SI-1R used only the three already-consumed MVP-0 development tasks. It opened zero fresh tasks and zero blind tasks. These verdicts mean that the two exposed mechanics defects were repaired; they do not mean that parent selection improved benchmark outcomes, that Shinka mechanisms were admitted, or that DiscoveryOS search value was established.

The sealed repair manifest is `runs/strategy-integration-si1r-gpt56sol-medium-r1/protocol-artifacts/records/si1r-development-manifest.json`, digest `0e99329cef52367bf542d86901243c2d7a7cf5a632ebd7a1d84c99a9ecf9123a`. The append-only audited report is `runs/strategy-integration-si1r-gpt56sol-medium-r1/result-artifacts/records/si1r-development-audited-report-v2.json`, digest `30b6d40f1e15cd7aaeb68dc089273c7708c57aea8846689d6a737695a894d5ad`. The original report remains unchanged; audit v2 corrects only its inherited SI-1 protocol label and records zero additional model or evaluator calls.

## 1. Parent opportunity autopsy

The versioned, model-free autopsy reconstructed all 18 SI-1 parent-selection receipts from the frozen R3 ledgers (`si1r-frozen-autopsy-v2.json`, digest `92f237f6fa034c7d8c4d6195884c8e3550db6762f0cc0c3e8e578ad6d8a0c4a1`).

| Observation | Count |
|---|---:|
| Parent opportunities | 18 |
| Initial single-parent opportunities | 6 |
| Multi-parent opportunities | 12 |
| Multi-parent opportunities with maximum probability >= 0.95 | 7 |
| Selected parent differed from incumbent | 3 |
| Archive visibility failures | 0 |

The first action in each parent-enabled arm was genuinely `POOL_STARVATION`: only the baseline had valid evidence. After that, the archive was visible and the controller supplied repeated opportunities. The dominant defect was `WEIGHT_COLLAPSE`: `selection_lambda=10` plus MAD normalization frequently produced probabilities near `0.999977 / 0.000023`. The three non-incumbent selections did not increase aggregate parent diversity, so SI-1 also exhibited `SELECTION_RANDOMNESS_NO_EFFECT` at the pilot aggregate level. There was no `ARCHIVE_VISIBILITY_FAILURE` and no general `CONTROLLER_OPPORTUNITY_STARVATION`.

Each new receipt now carries pool size, eligible count, candidate ids/scores/lineages/generations/exposures, weights/probabilities, incumbent identity, selected-is-incumbent, and available lineage/root counts. Structural-root count remains `null`; SI-1R does not invent a structural-root semantic.

## 2. Parent pool and policy repair

The unified ledger-backed Candidate/Research Graph remains the only parent source. Valid evidence-backed incumbent, recent, archived, and historical candidates stay eligible; invalid candidates remain excluded. No Shinka-specific population database was added.

SI-1R retains the existing quality-times-inverse-exposure weights but caps any one candidate at probability `0.8` when multiple candidates are eligible, redistributing excess mass proportionally. This prevents numerical monopoly without promoting invalid or obviously ineligible candidates.

The deterministic effectiveness fixture records `unique_parent_count > 1`, `effective_parent_count > 1`, and higher entropy than the uncapped SI-1 policy. In the real development pilot, three of 18 executed parent selections chose a legal non-incumbent parent; all were receipt-backed and passed controller replay before execution. The maximum observed multi-parent probability was exactly `0.8`.

The repair does not claim outcome value: `CORE_PARENT` and `CORE_PARENT_NOVELTY` still did not exceed CORE aggregate parent diversity, and median final improvement remained tied on the first three arms while the combined arm was lower on `load_balance_alpha`.

## 3. Novelty cost autopsy

Frozen SI-1 had three duplicate rejections and two automatic resamples:

| Metric | SI-1 |
|---|---:|
| Duplicate evaluations avoided | 3 |
| Resample calls | 2 |
| Extra generation tokens | 41,386 |
| Extra generation wall | 67.89 s |
| Tokens per avoided evaluation | 13,795.33 |
| Wall per avoided evaluation | 22.63 s |
| Resample emitted-candidate rate | 1.0 |
| Resample mechanically-valid rate | 1.0 |
| Resample incumbent-improvement rate | 0.0 |

Novelty judgment itself consumed no LLM tokens. The excess came from the unconditional `REJECT_RESAMPLE` path after a cheap deterministic rejection.

## 4. Cheap-first cascade and resampling economics

The deterministic cascade is now strict:

```text
L0 exact code artifact/hash
  -> L1 normalized token fingerprint
  -> L2 token-shingle structural similarity
  -> L3 deterministic AST semantic difference only for L2-high-similarity rows
```

L0/L1 rejection never computes L3. No novelty judgment invokes an LLM.

Duplicate rejection and resampling are separate decisions. SI-1R compares the frozen generation reserve against both the remaining action budget and the evaluation reserve that would be avoided. A resample that is more expensive in any resource dimension becomes `NOVELTY_REJECT_AND_STOP_UNAFFORDABLE`; it does not consume a second generation call. The repair does not increase the arm resource envelope.

## 5. Development pilot

The pilot froze `gpt-5.6-sol`, reasoning effort `medium`, and `codex-cli 0.148.0-alpha.9`. It ran with two task workers on the local 18-logical-CPU machine after a resource probe. Total generation usage across all 12 task-arms was 719,922 tokens.

| Arm | Median final improvement | Median anytime AUC | Total tokens | Median tokens-to-best | Median wall-to-best | Valid rate | Effective parents | Parent entropy | Parent gini | Avoided evals | Resample calls/tokens/wall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `CORE` | 0.41094003 | 0.33344496 | 176,567 | 19,046 | 31.31 s | 1.0000 | 3.0000 | 1.0986 | 0.0000 | 0 | 0 / 0 / 0 |
| `CORE_PARENT` | 0.41094003 | 0.33083960 | 179,023 | 19,492 | 44.74 s | 0.7778 | 2.6300 | 0.9446 | 0.0556 | 0 | 0 / 0 / 0 |
| `CORE_NOVELTY` | 0.41094003 | 0.32550971 | 187,010 | 21,738 | 44.62 s | 0.7778 | 2.6300 | 0.9446 | 0.0556 | 2 | 0 / 0 / 0 |
| `CORE_PARENT_NOVELTY` | 0.41094003 | 0.32620009 | 177,322 | 20,621 | 31.10 s | 0.6667 | 1.8899 | 0.6365 | 0.1667 | 2 | 0 / 0 / 0 |

All arms retained the same median marginal improvement after the first successful candidate except the combined arm, which was lower (`0.0` versus `0.00555556`). No new stepping-stone or search-value evidence was observed.

Compared with frozen SI-1, SI-1R avoided four duplicate evaluations with zero resample calls, zero extra generation tokens, and zero extra generation wall. The deterministic novelty checks used 0.0355 seconds total wall and zero LLM tokens. Thus extra generation cost per avoided evaluation fell from 13,795.33 tokens / 22.63 seconds to zero.

## 6. Resource and BR regression checks

- `selected_but_unaffordable_action_count == 0`.
- `GENERATION_BUDGET_EXCEEDED == 0`.
- All 12 task-arm resource checks passed.
- Controller decision replay, parent receipt replay-in-loop, budget preflight, novelty receipt creation, rejection-without-evaluation, and SQLite cleanup paths passed targeted tests.
- The original SI-1 manifest, reports, audited report v2, and ledgers were read-only; SI-1R created new autopsy and pilot roots.

## 7. Final interpretation and stop rule

Parent selection now demonstrably changes the realized parent distribution when legal alternatives exist, and novelty retains duplicate-evaluation avoidance without automatic expensive regeneration. BR affordability and reachability mechanics did not regress. The SI-1R stop rule is therefore satisfied.

Do not hand-tune final benchmark scores or add another strategy. A fresh SI-1 admission may be discussed next, but it has not been opened or authorized by this result.
