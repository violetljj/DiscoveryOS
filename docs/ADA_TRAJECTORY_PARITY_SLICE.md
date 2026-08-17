# Ada Trajectory Adaptation Parity Slice

## Status

```text
ADA_TRAJECTORY_PARITY_SLICE_MECHANICS_READY
ADA_TRAJECTORY_CONTROL_TRANSMISSION_CONFIRMED_ZERO_MODEL
ADA_TRAJECTORY_GENERATION_CONTEXT_TRANSMISSION_CONFIRMED_ZERO_MODEL
ADA_CANDIDATE_BEHAVIOR_VALUE_NOT_EVALUATED
ADA_SEARCH_VALUE_NOT_EVALUATED
EVOX_TYPED_STRATEGY_STATE_MACHINE_MECHANICS_READY
P2_REMAINS_FROZEN_PENDING_PROFILE_REVISION_AND_FAIRNESS_GATE
```

This slice implements only the Ada closure frozen by [`ADA_EVOX_MECHANISM_PARITY_AUDIT.md`](ADA_EVOX_MECHANISM_PARITY_AUDIT.md). It does not import islands, UCB scheduling, a QD archive, migration, paradigm generation or any private evaluator/budget/winner authority.

## Implemented vertical slice

`AdaTrajectoryPolicy` projects the selected ledger-backed `BranchSearchState` into a typed, content-addressed `AdaTrajectoryReceipt`:

- a bounded four-outcome improvement window;
- a decayed accumulated positive-improvement signal;
- sibling outcomes (`IMPROVED`, `TIED`, `REGRESSED`);
- bounded lineage receipt references;
- deterministic `EXPLORE` or `REFINE` mode and exploration intensity.

High accumulated improvement selects narrow `REFINE`; weak progress selects broader `EXPLORE`. The configuration, projected state, mode and intensity are all covered by the receipt digest.

The Harness router binds the exact mode, intensity and receipt digest into `SearchDecision.reason_codes`. The Ada operator reconstructs the receipt from the same immutable `SearchState` before generation and fails closed if any bound Ada code differs or is absent. Only after that check does the unified executor add the receipt, sibling outcomes and mode-specific guidance to the normal Local Patch generation context. Direct and structural operators receive none of this Ada context.

The slice does not change `ProblemContract`, `ExperimentExecutor`, Evidence Ledger, evaluator, `GateEngine`, budget settlement or winner semantics.

## Zero-model parity evidence

Focused tests establish:

- identical policy/state projections are deterministic and content-addressed;
- productive and weak trajectories produce different decision IDs, modes, intensities and generation guidance;
- the improvement window is bounded and old outcomes cannot dominate it;
- removing the trajectory receipt binding causes generation guidance to fail closed;
- a real Harness loop sends no Ada context during Direct bootstrap, then sends the reconstructed Ada receipt and sibling outcome in the next Ada request;
- all static Profile children still boot through the same Harness runtime with authority and budget surfaces unchanged.

The provider in these tests is a local deterministic fixture; no model/provider or fresh asset was used. This proves runtime control and context transmission, not that a stochastic model follows the guidance, produces better candidates, or improves search value.

## Next gate

Ada parity is closed only at the mechanism-transmission level requested for this stage. The separate EvoX state-machine slice has now passed its zero-model mechanics/transmission gate; see [`EVOX_STRATEGY_PARITY_SLICE.md`](EVOX_STRATEGY_PARITY_SLICE.md). P2 remains frozen until the four arms are revised, re-digested and checked by the shared zero-model fairness gate.
