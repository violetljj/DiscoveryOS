# Generator Conditioning Fidelity V1

## Status and purpose

```text
GENERATOR_CONDITIONING_FIDELITY_PROTOCOL_IMPLEMENTED
GCF_SYNTHETIC_IDENTIFIABILITY_FIXTURE_TESTED
NO_REAL_CONDITIONING_CHANNEL_ADMITTED
NO_FRESH_DOWNSTREAM_VALUE_TRIAL_AUTHORIZED
```

GCF asks a question that is upstream of search value:

> Under a frozen generator contract, does changing one conditioning channel produce a stagewise, semantic response that survives stochastic generation?

It does not ask which controller is better. It separates channel detectability, semantic transmission, and downstream value so that an upstream policy cannot receive fresh causal budget when its signal is not reaching generated descendants.

## Parent settlement

The read-only `parent-cib-r1-settlement` command exposes the CIB-R1 closeout as a digest-bound machine record:

```text
CAUSALLY_INERT_IN_CURRENT_REAL_GENERATION_REGIME
PARENT_SCIENTIFIC_PRIORITY_WITHDRAWN
PARENT_IMPLEMENTATION_AND_LINEAGE_CAPABILITY_RETAINED
NO_RETRY_ON_CONSUMED_CIB_R1_SURFACE
DO_NOT_OPEN_SI3_FRESH_BUDGET
```

`CAUSALLY_INERT` is a budget and governance decision for the complete frozen CIB-R1 generation contract. Its scope is the current Parent policy, CIB-R1 prompt/context binding, batched three-step stochastic generator, frozen model configuration, and consumed validation surface. It is not a universal zero-effect claim about Parent mechanisms.

Reopening requires all of a new versioned generation or inheritance contract, a new hypothesis, new calibration, and independent CIB admission. Adding seeds on the consumed surface, retuning Parent probability, changing margins, prompt tuning after observing the result, or treating ties as weak positive signal is prohibited.

## Frozen measurement chain

GCF records one frozen signature at each stage:

```text
condition
  -> proposal
  -> implementation
  -> repair
  -> final source
  -> hidden behavior
  -> utility
```

The V1 protocol accepts only deterministic, digest-bound stage probes, behavioral probes, and utility evaluators. A marker can calibrate whether input was read, but lexical copying alone cannot admit semantic transmission. Real runs must blind evaluation from condition labels and must not use the candidate generator as its own subjective classifier.

## Channels and null control

V1 freezes three independently varied channels:

- `PARENT_SOURCE`: base task, failure evidence, and mechanism brief remain fixed.
- `FAILURE_EVIDENCE`: Parent and mechanism brief remain fixed; mutually exclusive evidence requires distinguishable repairs.
- `MECHANISM_BRIEF`: Parent and failure evidence remain fixed; mutually exclusive briefs require distinguishable mechanisms.

Every intervention pair must have same-condition independent-draw null pairs. The decision is not whether two stochastic outputs differ, but whether cross-condition stage or behavior distance reproducibly exceeds the state-local null envelope plus a frozen margin.

## Gate cascade

```text
GCF-0 Calibration
  positive controls establish that the frozen observation chain can recover a known signal

GCF-1 Stagewise Detectability
  condition separation is measured at proposal, implementation, repair, and final output

GCF-2 Semantic Transmission
  final-stage separation and hidden behavioral separation both reproduce across states

GCF-3 Downstream Causal Value Eligibility
  utility improvement reproduces only after GCF-2; this authorizes a new preregistered trial,
  but does not itself establish search value
```

Synthetic calibration, consumed mechanics states, and consumed development traces may support GCF-0 through GCF-2 mechanics and diagnosis. They cannot produce a generalization, superiority, or search-value claim. A real channel that passes GCF-2 may only become eligible for a separately sealed downstream causal-value trial with a new contract, hypothesis, calibration, margin, and independent surface.

## Machine contract and synthetic fixture

The implementation lives in `src/discoveryos/benchmarks/conditioning_fidelity.py`. It provides immutable state, trace, and pair contracts; create-once manifest, pair receipts, and report records; state-local null envelopes; condition survival curves; and independent semantic/value verdict fields.

The no-model fixture contains two states per channel and 36 paired receipts. It deliberately calibrates three decision-table rows:

| Synthetic channel | Frozen fixture response | Expected gate result |
|---|---|---|
| Parent source | stage signatures survive, hidden behavior does not change | structural response only; GCF-2 fails |
| Failure evidence | stage and behavior signatures survive, utility ties | GCF-2 passes; downstream value not established |
| Mechanism brief | stage, behavior, and utility separation survive | eligible for a later GCF-3 trial |

These are constructed sensitivity cases. The report always emits an empty `real_channels_admitted` list, zero model calls and fresh-task consumption, and `fresh_downstream_trial_authorized: false`.

## Entrypoints

```powershell
$env:PYTHONPATH = "src"
python -m discoveryos parent-cib-r1-settlement
python -m discoveryos gcf-seal-synthetic --workspace runs/gcf-synthetic-r1
python -m discoveryos gcf-run-synthetic `
  --workspace runs/gcf-synthetic-r1 `
  --manifest-digest <sealed-digest>
```

No real generator call is part of these entrypoints. A future real GCF protocol must be sealed before the first model call and must version the generation contract rather than modifying the consumed CIB-R1 root.
