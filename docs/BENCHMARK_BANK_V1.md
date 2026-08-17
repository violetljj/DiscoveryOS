# DiscoveryOS Benchmark Bank v1

## Status

```text
BENCHMARK_BANK_V1_REGISTRY_IMPLEMENTED
BENCHMARK_BANK_V1_DEVELOPMENT_SLICE_EXECUTABLE
BENCHMARK_BANK_V1_EXTERNAL_ADAPTERS_NOT_YET_ADMITTED
ZERO_FRESH_INSTANCES_CONSUMED
```

Benchmark Bank v1 makes the problem family a durable research asset while treating a sealed instance or shard as the consumable scientific unit. It does not declare all listed benchmarks runnable. The registry currently contains 47 core families: two internal consumed families are `DEVELOPMENT_READY`; 45 external families are only `CATALOGUED`; zero external family is `ADMITTED`.

The machine-readable authority is [`../benchmarks/bank/v1/registry.json`](../benchmarks/bank/v1/registry.json). Its initial validated digest is `b68ec31bea6ed3484d0204ad5ad4ec4ef71396a72ac1f2451d254eb2fbdce718`.

## Difficulty ladder

| Tier | Purpose | Families |
|---|---|---:|
| R0 | regression and mechanics | 8 |
| R1 | easy search-value smoke | 8 |
| R2 | structural search | 10 |
| R3 | long-horizon heuristic search | 6 |
| R4 | real systems optimization | 5 |
| R5 | public frontier/SOTA replay and stress | 10 |

`R0` through `R5` are difficulty tiers, not evidence levels. Evidence authority remains the L0-L5 research-asset ladder in `AGENTS.md` and the frozen `ProblemContract` plus `GateEngine`.

## Partition lifecycle

```text
Problem family
  -> DEV      reusable mechanics/development instances
  -> SHADOW   limited, audited periodic regression instances
  -> SEALED   create-once claim-upgrade shards
```

- DEV can be reused without a fresh claim. It cannot establish admission or unseen-task generalization.
- SHADOW is a locked development holdout. Opening it does not make it scientific admission evidence, and repeated use must be audited.
- SEALED is opened only for a pre-registered fresh admission or winner-frozen blind confirmation. Opening consumes that exact instance/shard, not the whole family.
- A sealed shard is denied for debugging even if technically available. Blind confirmation additionally requires winner freeze and selection isolation.

The bank gate controls corpus eligibility only. It cannot issue scientific verdicts or replace `ProblemContract`, `SplitVault`, evaluator bindings, receipts, replay, or `GateEngine`.

## Integration states

| State | Meaning |
|---|---|
| `CATALOGUED` | Name and pinned upstream provenance exist; execution is forbidden. |
| `DEVELOPMENT_READY` | A local adapter can materialize reusable consumed/dev instances; claim ceiling remains development-only. |
| `ADMITTED` | Adapter, evaluator, license audit and local preflight digests are frozen; a later scientific protocol may use it. |

Moving an external family to `ADMITTED` requires all of: an exact upstream commit, license/data-use audit, deterministic instance identity, evaluator and environment digest, local executable preflight, resource envelope, DEV/SHADOW/SEALED split construction, contamination assessment, and replay coverage. Catalog presence or an upstream evaluator is not enough.

## Executable v1 slice

The first adapter exposes the existing consumed SI-2 Assignment and Coverage families. It materializes a registered instance into:

```text
algorithm.py
public_tests.py
evaluate.py
bank-instance.json
```

These assets are reusable regression/development evidence only. The adapter does not copy SI-2 receipts, alter their verdict, create a new evaluator regime, or consume a fresh instance.

```powershell
$env:PYTHONPATH = "src"
python -m discoveryos benchmark-bank-validate
python -m discoveryos benchmark-bank-materialize-dev `
  --family-id assignment_consumed_dev `
  --instance-id capacitated_assignment_delta `
  --output-dir runs/benchmark-bank-dev/assignment-delta
```

## External sources and exposure boundaries

The v1 registry pins the source commits observed on 2026-08-17:

- [AlgoTune](https://github.com/oripress/AlgoTune): 154 speed/correctness tasks; code repository is MIT-licensed. v1 selects task IDs already present in its task tree, but admits none yet.
- [ALE-Bench](https://github.com/SakanaAI/ALE-Bench): score-based AHC tasks with public and private evaluation. Code is Apache-2.0 and the dataset is CC-BY-ND-4.0; private inputs/seeds are forbidden during search.
- [SkyDiscover benchmarks](https://github.com/skydiscover-ai/skydiscover/blob/main/benchmarks/README.md): math, ADRS systems, Frontier-CS and ALE integration examples. Per-benchmark dependencies and data still require separate audit.
- [AlphaEvolve problem repository](https://github.com/google-deepmind/alphaevolve_repository_of_problems): 67 public mathematical problems, often with prompts, verifiers, initial programs and final evolved programs. These are contamination-exposed SOTA replay/stress assets, not standalone evidence of de-novo discovery.

For public frontier problems, a future scientific generalization claim requires a pre-frozen neighboring hidden distribution, such as unseen size, shape, field, constraint or workload distribution. Public `n`, prompts, verifier, initial code or evolved solutions must be recorded as exposure, never silently treated as blind.

## Reservoir rule

New experiments select from the Bank before inventing a new family. A family is added only when the current Bank cannot exercise a predeclared mechanism or when a genuinely external generalization question requires it. Reservoir entries are discovery candidates, not admitted benchmarks, and screening them must not open SEALED content.
