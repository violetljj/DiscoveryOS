# ShinkaEvolve → DiscoveryOS mechanism mapping

## Provenance

- Paper: [ShinkaEvolve: Towards Open-Ended And Sample-Efficient Program Evolution](https://arxiv.org/abs/2509.19349), arXiv v1, 2025-09-17.
- Official implementation: [SakanaAI/ShinkaEvolve](https://github.com/SakanaAI/ShinkaEvolve), inspected commit `2bf8cfeb6fd39c79555cd94a8f395d64e740aae8`.
- DiscoveryOS integration: `STRATEGY_INTEGRATION / SI-1`; no Shinka runtime, database, evaluator, island, budget system, or model router is imported.

The paper defines weighted parent sampling as a sigmoid fitness component multiplied by `1 / (1 + offspring_count)`. The inspected official source additionally normalizes the fitness delta from the median by median absolute deviation before the sigmoid. SI-1 records that source-version difference and follows the inspected official implementation.

## Parent selection

| Official mechanism | DiscoveryOS primitive | Preserved behavior | Adaptation | Intentionally omitted |
|---|---|---|---|---|
| Correct programs in an archive are eligible parents | `ParentCandidate` projected from ledger candidates and evidence | Invalid or non-evidence-backed candidates cannot be scientific parents | Candidate Store and ledger replace Shinka `programs` / `archive` tables | Shinka database and fix mode |
| Fitness relative to archive median | `ShinkaWeightedParentSelectionPolicy` | Median-relative fitness signal; maximize/minimize direction is explicit | Uses the frozen DiscoveryOS objective evidence | Multi-objective archive replacement |
| MAD-normalized sigmoid with configurable lambda | `exploitation_component` | Scale-robust sigmoid and policy-versioned lambda | A tiny positive component floor prevents numerical underflow from turning exploration into an accidental hard exclusion | Beam search and power-law alternatives |
| `1 / (1 + children_count)` novelty bonus | `exploration_component = 1 / (1 + parent_exposure_count)` | Repeatedly used parents lose weight without being permanently excluded | Ledger-backed parent selection receipts count exposure; no separate offspring database | Islands, migration, dynamic islands |
| Weighted stochastic draw | `ParentSelectionReceipt` | Normalized probability, frozen seed, random draw, chosen parent, and replay | Seed is derived from frozen run configuration plus settled step | Global process RNG and non-replayable SQL `RANDOM()` fallbacks |

Diagnostics are `parent_entropy`, `unique_parent_count`, `effective_parent_count`, `parent_exposure_gini`, incumbent/non-incumbent fractions, and optional structural-root diversity. SI-1 emits `null` for structural-root diversity because the current single-frontier graph does not provide a trustworthy basin/root identity; it does not manufacture one for reporting.

## Novelty rejection

| Official mechanism | DiscoveryOS primitive | Preserved behavior | Adaptation | Intentionally omitted |
|---|---|---|---|---|
| Embed mutable code and compute cosine similarity against the island subpopulation | `ShinkaStyleNoveltyPolicy` Level 1 | Cheap representation and cosine screen run before any expensive semantic decision | Local token-shingle representation avoids a new embedding service; comparison scope is selected parent, incumbent, recent candidates, and archive candidates | External embedding model and island-only scope |
| High similarity triggers an LLM meaningful-novelty judgment | Deterministic AST semantic-difference judge | High similarity alone is not automatically treated as semantic identity | Replayable local judge is the default; Level 0 normalized exact duplicate detection runs first | Novelty LLM calls in SI-1 and their model routing |
| Rejection sampling up to `max_novelty_attempts` | Executor-bounded proposal loop plus `NoveltyReceipt` | Reject → regenerate; attempts cannot be infinite; exhaustion is predefined | The default is deterministic reject on exhaustion; an explicit `ACCEPT_LAST` policy exists but is not used by the pilot | Unbounded retry and free retries |
| Only accepted code reaches execution/evaluation | `UnifiedActionExecutor` | Rejected proposals receive no scientific evaluator call | Rejected candidates and generation receipts remain auditable in the Candidate Store/ledger | Deleting or hiding rejected generations |

Every attempt records proposal/comparison digests, nearest candidate, exact/high-similarity flags, semantic decision, false-reject diagnostic, usage, attempt number, and policy version. Replay recomputes the assessment from the same proposal and comparison set.

## Budget and authority boundaries

- `ActionCost.novelty_resample_reserve` is part of the complete action floor. Enabling novelty requires this reserve to cover `(max_novelty_attempts - 1) × generation_reserve` before an executor can be constructed.
- Controller preflight includes the complete bounded retry path. Insufficient remaining resources yield `STOP_BUDGET_INSUFFICIENT`; no provider or evaluator starts.
- Generation, novelty, evaluation, and settlement remain inside the same arm envelope. Novelty does not create a second budget authority.
- Candidate/evidence/artifact authority remains DiscoveryOS-native. `GateEngine` still owns scientific feasibility; parent selection and novelty cannot declare winners or change frozen evidence.
- SI-1 does not include LLM/model bandits, islands, migration, Ada routing, EvoX, PACE, MLEvolve, or new mutation operators.
