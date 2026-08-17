# Causal Mechanism Intelligence R0

## 结论先行

```text
CMI_R0_PROTOCOL_IMPLEMENTED
CMI_R0_SYNTHETIC_DIAGNOSTIC_SENSITIVITY_PASSED
NO_REAL_BOTTLENECK_ESTABLISHED
NO_REAL_MECHANISM_BRIEF_AUTHORIZED
NO_FRESH_SEARCH_VALUE_BUDGET
```

CMI-R0 把 DiscoveryOS 从“收到一个 Operator 后执行和评估”推进到最小的“先区分竞争瓶颈，再决定是否允许形成 Mechanism Brief”。它是 Search/Research 平面的诊断器，不是新 evaluator；科学 verdict 仍只属于冻结 `ProblemContract` 与 `GateEngine`。

## 为什么现在做

EMC-R3 已证明 structured contract 能进入真实运行路径并产生稳定、不同的 Direct/Repair runtime signature。EMC Operator Causal Value R1 随后得到 6/6 intervention pairs 全 tie，final utility、AUC、validity、replacement 与 breakthrough delta 全为零。因此当前缺口不是继续证明 Repair 被执行，而是判断失败来自哪一个可证伪瓶颈，并避免在诊断前继续堆 Operator。

## R0 最小对象

实现位于 `src/discoveryos/mechanism_intelligence.py`：

- `FailurePhenotypeReceipt`：绑定 episode、source、contract 与标准化 failure metrics；
- `BottleneckHypothesis`：冻结 causal target、applicability preconditions、expected observations、falsifiers 与 required probes；
- `DiagnosticProbeResult`：绑定 probe spec digest、phenotype identity、观察值、validity 和实际资源使用；
- `MechanismDiagnosisSession`：强制 hypothesis/probe/result 顺序与唯一终态。

状态机为：

```text
OBSERVED_FAILURE
  -> HYPOTHESES_FROZEN
  -> PROBES_FROZEN
  -> DIAGNOSED
  -> MECHANISM_BRIEF_ALLOWED | NO_ACTIONABLE_BOTTLENECK
```

`MECHANISM_BRIEF_ALLOWED` 的必要条件是恰好一个 hypothesis 为 `SUPPORTED`，其余竞争 hypothesis 全部为 `REFUTED`。任何 `UNRESOLVED` 或 `NOT_EVALUABLE` 都不能被沉默地当作反证；probe identity、phenotype binding 或资源上限不匹配直接失败。

## Synthetic sensitivity fixture

R0 冻结一个有效候选但 utility stagnation 的 synthetic phenotype，以及三个竞争解释：

| Hypothesis | Probe | Support region | Refute region |
|---|---|---:|---:|
| `H3_EVALUATOR_INSENSITIVITY` | frozen ranked-control recovery | `<= 0.2` | `>= 0.8` |
| `H4_IMPLEMENTATION_BOTTLENECK` | perfect-implementation eligibility delta | `>= 0.2` | `<= 0.01` |
| `H5_STRUCTURAL_BASIN_LOCK` | functional basin diversity | `<= 0.1` | `>= 0.5` |

Null control 的三个观察都落在未决区，必须终止为 `NO_ACTIONABLE_BOTTLENECK`。Positive control 预构造为 evaluator 与 implementation hypotheses 被反证、structural basin lock 被支持，必须唯一输出 `H5_STRUCTURAL_BASIN_LOCK`。这只验证诊断状态机的可达性与 fail-closed 行为，不是现实 mechanism evidence。

Create-once synthetic mechanics run 已完成：manifest digest 为 `a6f3986da9f234bcbb417e3c2cbb5ea9b0e69cb3303b2e6706149c84d4788984`，report SHA-256 为 `bac3c68811d4f903cb080004378dfdaabe05e9e2e3784816b53bd86f406c8001`。Null terminal 为 `NO_ACTIONABLE_BOTTLENECK`；positive terminal 为 `MECHANISM_BRIEF_ALLOWED`，且唯一 synthetic hypothesis 为 `H5_STRUCTURAL_BASIN_LOCK`。

## 资源与证据边界

```text
model_calls = 0
evaluator_calls = 0
fresh_task_budget_consumed = 0
real_bottleneck_established = false
real_mechanism_brief_authorized = false
fresh_search_value_budget_authorized = false
```

Manifest、scenario receipts 和 report 使用 create-once records，并绑定 protocol implementation SHA-256。可通过以下入口复现 synthetic mechanics：

```powershell
$env:PYTHONPATH = "src"
python -m discoveryos cmi-r0-seal --workspace runs/cmi-r0-synthetic
python -m discoveryos cmi-r0-run-synthetic --workspace runs/cmi-r0-synthetic --manifest-digest <digest>
```

## 下一道门

下一步不是自动生成 Structural Escape Operator。现实 CMI-R1 必须先：

1. 选择 never-consumed development episodes；
2. 在读取 probe output 前冻结 phenotype、竞争 hypothesis、probe、阈值和预算；
3. 证明 evaluator positive control、implementation control 与 functional-basin assay 在该 domain 可执行；
4. 只有一个瓶颈 hypothesis 被唯一支持后，才另行冻结 Mechanism Brief；
5. 新 Operator 仍须通过 applicability、realized intervention、causal reachability、null/positive controls 和独立 dev value gates。

R0 不授权现实 probe、模型调用、新 Operator、dev value trial 或 fresh search-value trial。
