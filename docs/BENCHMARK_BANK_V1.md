# DiscoveryOS Benchmark Bank v1

## Status

```text
BENCHMARK_BANK_V1_REGISTRY_IMPLEMENTED
BENCHMARK_BANK_V1_DEVELOPMENT_SLICE_EXECUTABLE
BENCHMARK_BANK_V1_SIX_ALGOTUNE_CONTRACT_DEV_FAMILIES_EXECUTABLE
BENCHMARK_BANK_V1_TEN_ALGOTUNE_R2_CONTRACT_DEV_FAMILIES_EXECUTABLE
BENCHMARK_BANK_V1_P2_V4_EIGHT_FAMILY_EXPANSION_EXECUTABLE
P2_V4_6_6_12_EXTERNAL_DEV_FAMILY_RESERVOIR_READY
P2_V41_DETERMINISTIC_OPCODE_EVALUATOR_REVISION_FROZEN
BENCHMARK_BANK_V1_ALE_R3_ARTIFACTS_PINNED_EXECUTION_BLOCKED
BENCHMARK_BANK_V1_SKYDISCOVER_R4_R5_SOURCE_TREES_AUDITED_EXECUTION_BLOCKED
BENCHMARK_BANK_V1_EXTERNAL_SCIENTIFIC_ADMISSION_NOT_ESTABLISHED
ZERO_FRESH_INSTANCES_CONSUMED
```

Benchmark Bank v1 makes the problem family a durable research asset while treating a sealed instance or shard as the consumable scientific unit. It does not declare all listed benchmarks runnable. The registry currently contains 49 core families: two internal consumed families and 24 external contract-derived AlgoTune families are `DEVELOPMENT_READY`; 23 families remain `CATALOGUED`; zero external family is `ADMITTED`.

The machine-readable authority is [`../benchmarks/bank/v1/registry.json`](../benchmarks/bank/v1/registry.json). The expanded and evaluator-revised R0-R5 bank has registry digest `8428268400f6c23c13e58b0476b08c25e0870980feb081c7481063efd7b97a0a`.

## Difficulty ladder

| Tier | Purpose | Families |
|---|---|---:|
| R0 | regression and mechanics | 8 |
| R1 | easy search-value smoke | 8 |
| R2 | structural search | 12 |
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

## Executable internal slice

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

## AlgoTune R0/R1 development batch

The first external development batch exposes six task contracts from pinned AlgoTune commit `dff9914c10800c7a031c9e8c3d4d1c8cd1b38906`:

| Tier | Family | Local DEV instances |
|---|---|---:|
| R0 | Connected Components | 2 |
| R0 | Dijkstra From Indices | 2 |
| R0 | 1D Convolution | 2 |
| R1 | Convex Hull | 2 |
| R1 | Cholesky Factorization | 2 |
| R1 | Linear System Solver | 2 |

The original adapter was `discoveryos.algotune_contract_dev.v1`. It materialized `algorithm.py`, `public_tests.py`, `evaluate.py`, `task-contract.json`, and `bank-instance.json`, with exact upstream task/description hashes and deterministic generated DEV cases. Its median wall-clock runtime score is retained only as historical development infrastructure and is superseded for the current registry by the V4.1 deterministic evaluator described below.

This is deliberately a standard-library contract-compatible development regime. It does not vendor or claim equivalence with AlgoTune's NumPy/SciPy/NetworkX evaluator/runtime, and it does not reproduce official performance results. Its claim ceiling is `EXTERNAL_CONTRACT_DERIVED_DEVELOPMENT_ONLY`. Promotion to `ADMITTED` still requires exact upstream environment execution, license receipt, resource envelope, partition construction and replay under a separately frozen protocol.

```powershell
$env:PYTHONPATH = "src"
python -m discoveryos benchmark-bank-materialize-dev `
  --family-id dijkstra `
  --instance-id dijkstra_dev_alpha `
  --output-dir runs/benchmark-bank-dev/dijkstra-alpha
python runs/benchmark-bank-dev/dijkstra-alpha/public_tests.py
python runs/benchmark-bank-dev/dijkstra-alpha/evaluate.py
```

## AlgoTune R2 structural-search development batch

The second external batch adds all ten registered R2 families, with two deterministic DEV instances each:

| Family | Upstream runtime dependency | Local exact DEV method |
|---|---|---|
| Multi-Dimensional Knapsack | OR-Tools | resource-state DP; exhaustive objective verifier |
| Job-Shop Scheduling | OR-Tools | bounded operation-order search |
| Capacitated Facility Location | CVXPY/HiGHS | bounded assignment search |
| Graph Coloring | NetworkX + OR-Tools | exact bounded coloring |
| Min-Cost Max-Flow | NetworkX | residual shortest augmenting paths |
| Earth Mover Distance | NumPy + POT | uniform-mass assignment DP |
| K-Centers | NetworkX + PySAT | all-pairs distance plus bounded center enumeration |
| Maximum Clique | OR-Tools | bounded subset enumeration |
| Maximum Independent Set | OR-Tools | bounded subset enumeration |
| Minimum Dominating Set | OR-Tools | bounded subset enumeration |

The original adapter was `discoveryos.algotune_r2_contract_dev.v1` with regime `DISCOVERYOS_STDLIB_ALGOTUNE_R2_CONTRACT_DEV_V1`. Its family-specific output, input-immutability, feasibility and exact-objective checks remain, but its wall-clock score is superseded in the current registry by the V4.1 deterministic evaluator. Invalid or suboptimal candidates still fail closed.

These instances exercise structural-search mechanics without adding OR-Tools, CVXPY, POT, NetworkX or PySAT to the DiscoveryOS core environment. They are not scale-equivalent to upstream instances and do not establish official AlgoTune performance, external competitiveness or scientific admission. Their claim ceiling is `EXTERNAL_R2_CONTRACT_DERIVED_DEVELOPMENT_ONLY`.

## P2 V4 outcome-blind family expansion

The third historical adapter, `discoveryos.algotune_p2v4_contract_dev.v1`, added eight families solely to satisfy the pre-model P2 V4 `6 R0 / 6 R1 / 12 R2` independent-family reservoir. Its family material remains contract-derived DEV evidence, not the upstream evaluator or scientific admission; its wall-clock score is likewise superseded by V4.1.

| Tier | Added family | Selection basis | DEV instances |
|---|---|---|---:|
| R0 | Affine Transform 2D | all three missing registered R0 contracts | 2 |
| R0 | Real Eigenvalues | all three missing registered R0 contracts | 2 |
| R0 | Minimum Spanning Tree | all three missing registered R0 contracts | 2 |
| R1 | Least Squares | first of five by frozen SHA-256 rank | 2 |
| R1 | FFT Convolution | second of five by frozen SHA-256 rank | 2 |
| R1 | Minimum-Weight Assignment | third of five by frozen SHA-256 rank | 2 |
| R2 | Minimum Vertex Cover | missing cover-selection structural contract | 2 |
| R2 | Traveling Salesman | missing sequence/cycle structural contract | 2 |

Every family binds the task and description SHA-256 from pinned AlgoTune commit `dff9914c10800c7a031c9e8c3d4d1c8cd1b38906`. The registry records the complete R1 rank, selected R0/R1/R2 identities, coverage rationale, `model_calls=0`, and `fresh_or_sealed_assets_opened=0`. The 16 new instances materialize deterministically, reject input mutation/invalid or suboptimal output, and passed their public/evaluator execution tests. Adapter source SHA-256 at this closure is `90197a9be80dc71a0d8ec2679de295e8b85c688602ce5fa2092aefd09d1b0e51`.

## P2 V4.1 deterministic evaluator revision

The current registry binds all 24 external contract-derived families to `discoveryos.algotune_p2v41_deterministic_dev.v1` and `DISCOVERYOS_P2V41_DETERMINISTIC_OPCODE_DEV_V1`. The score is the negative executed CPython 3.11 opcode count for frames from materialized `algorithm.py`; the family-specific correctness and input-immutability checks remain authoritative. This replaces wall-clock scoring only because an untouched baseline produced two valid scores differing by `0.004711276446948687`, which could not satisfy Executability Gate V1's `1e-12` determinism requirement.

Each task contract binds a positive score resolution plus two valid, distinct fixed-case lookup calibration scores. These calibration programs establish at least four reachable development-resolution steps and are never admitted as scientific candidates. All 48 DEV instances passed public tests and two full evaluator replays with identical score/opcode count. This remains a fixed-case DEV cost proxy, not official AlgoTune performance, hardware-independent complexity, generalization evidence, or scientific admission. The pre-model binding is recorded in [`P2_FACTORIAL_V4_PREMODEL_STATISTICAL_SEAL.md`](P2_FACTORIAL_V4_PREMODEL_STATISTICAL_SEAL.md).

This establishes only a candidate family reservoir. It does not choose the one primary instance per family, establish V4 residual headroom, run the cohort-wide power lease/Executability Gate, seal a V4 manifest, or authorize generation.

## ALE R3 audited blocker

The six R3 ALE families bind official code commit `f7d927906dc1dcd860ee086e4560d576438b1354` and Hugging Face dataset commit `0f426173b4e4e73b09b2b3631ae0490f66b75f99`. Every family records the exact Git LFS SHA-256 and byte size of its problem ZIP. Code is Apache-2.0; the dataset is CC-BY-ND-4.0.

They remain `CATALOGUED`, not `DEVELOPMENT_READY`, for three concrete reasons:

1. Each official problem ZIP co-bundles public seeds/tools with private seeds, standings and private-relative results. The stock loader reads both public and private seeds during session construction. A public-only selective extractor with a receipt has not been implemented.
2. ALE candidates are native/stdin programs evaluated by a Docker/Rust judge, while the current Bank executable contract is Python-module based. A digest-bound native program bundle is required instead of disguising C++/Rust execution as `algorithm.py`.
3. The local Docker 29.6.2 CLI is installed, but the Docker Desktop Linux daemon was unavailable during the 2026-08-17 preflight. No judge image, generator or evaluator was run.

Registry validation therefore requires all three blockers while an ALE family is catalogued and rejects any execution-ready state without `public_only_extraction_digest`, `native_program_bundle_digest`, and `docker_judge_preflight_digest`. No dataset ZIP was downloaded or opened during this audit, no private seed was read, and no ALE shard was consumed.

## SkyDiscover R4 systems audit

The five systems families bind SkyDiscover commit `8a840394e19ee4bfb3fb0a62762b902561a7efeb` and a deterministic SHA-256 over each tracked source-tree listing. A read-only syntax smoke parsed all selected R4/R5 Python files successfully. This is source integrity and mechanics preflight only; it is not an evaluator run.

| Family | Upstream dependencies | Data boundary | Current blocker |
|---|---|---|---|
| Cloudcast | NetworkX, Pandas | downloaded network profiles/configs | data digest/license and environment/evaluator preflight |
| EPLB | Torch | downloaded `expert-load.json` | data digest/license and environment/evaluator preflight |
| Prism | NumPy | generated public cases | frozen partition identity and environment/evaluator preflight |
| LLM-SQL | Pandas, NetworkX | five downloaded CSV datasets | data digests/licenses and environment/evaluator preflight |
| Transaction Scheduling | NumPy | repository-bundled public workloads | frozen partition identity and environment/evaluator preflight |

The frozen DiscoveryOS environment intentionally has no runtime dependencies. Runtime probing confirmed that NumPy, SciPy, Pandas, NetworkX, Torch, JAX and tqdm are unavailable there. Consequently none of the R4 families is marked `DEVELOPMENT_READY`; Prism and Transaction Scheduling are the shortest next adapter candidates because their current inputs are self-contained, while the other three first require explicit data provenance.

Registry validation requires every R4 entry to retain a source-tree digest, syntax result, dependency profile, data boundary and non-empty blocker set. Promotion additionally requires an adapter, evaluator and environment digest.

## SkyDiscover R5 public-frontier audit

All ten selected R5 paths exist at the same pinned SkyDiscover commit and have source-tree digests plus dependency profiles recorded in the registry. They rely on combinations of NumPy/SciPy and, for several families, JAX/Optax; the official evaluator runtime was not executed in the dependency-free project environment.

Every selected family publicly exposes its prompt, evaluator, initial program, fixed instance and target value. Several targets explicitly compare against published AlphaEvolve results; the referenced AlphaEvolve problem repository was separately checked out at pinned commit `8f447457957deac61e28bf1676746f0753b3b2f8`. These assets may become public replay/stress DEV tasks after an exact environment preflight, but they cannot support de-novo discovery or unseen-family claims.

Registry validation therefore fails closed if any R5 exposure flag or the `NEIGHBORING_HIDDEN_DISTRIBUTION_NOT_FROZEN` blocker is removed. A scientific generalization protocol would need a pre-frozen neighboring hidden distribution that was not inferred or tuned from the public prompt, verifier, fixed dimensions or target value.

## External sources and exposure boundaries

The v1 registry pins the source commits observed on 2026-08-17:

- [AlgoTune](https://github.com/oripress/AlgoTune): 154 speed/correctness tasks; code repository is MIT-licensed. v1 selects task IDs already present in its task tree, but admits none yet.
- [ALE-Bench](https://github.com/SakanaAI/ALE-Bench): score-based AHC tasks with public and private evaluation. Code is Apache-2.0 and the dataset is CC-BY-ND-4.0; private inputs/seeds are forbidden during search.
- [SkyDiscover benchmarks](https://github.com/skydiscover-ai/skydiscover/blob/main/benchmarks/README.md): math, ADRS systems, Frontier-CS and ALE integration examples. Per-benchmark dependencies and data still require separate audit.
- [AlphaEvolve problem repository](https://github.com/google-deepmind/alphaevolve_repository_of_problems): 67 public mathematical problems, often with prompts, verifiers, initial programs and final evolved programs. These are contamination-exposed SOTA replay/stress assets, not standalone evidence of de-novo discovery.

For public frontier problems, a future scientific generalization claim requires a pre-frozen neighboring hidden distribution, such as unseen size, shape, field, constraint or workload distribution. Public `n`, prompts, verifier, initial code or evolved solutions must be recorded as exposure, never silently treated as blind.

## Reservoir rule

New experiments select from the Bank before inventing a new family. A family is added only when the current Bank cannot exercise a predeclared mechanism or when a genuinely external generalization question requires it. Reservoir entries are discovery candidates, not admitted benchmarks, and screening them must not open SEALED content.
