# CMI-R1 Real Probe Calibration

## 当前状态

```text
CMI_R1_REAL_PROBE_CALIBRATION_PROTOCOL_IMPLEMENTED
CMI_R1_REAL_PROBE_CALIBRATION_NOT_YET_EXECUTED
NO_REAL_BOTTLENECK_ESTABLISHED
NO_REAL_MECHANISM_BRIEF_AUTHORIZED
NO_FRESH_SEARCH_VALUE_BUDGET
```

CMI-R1 是现实诊断前的零模型硬门。它不生成候选，而是在两个从未消费的 development episodes 上验证 evaluator、perfect implementation control 和 functional-output assay 是否足以区分预构造差异。

## 冻结 states

| Role | Task ID | Evaluator seeds | Functional-probe seeds |
|---|---|---|---|
| state 1 | `cmi_r1_assignment_probe_alpha` | `21101, 21121, 21139, 21157, 21179, 21211` | `23117, 23131, 23159` |
| state 2 | `cmi_r1_coverage_probe_alpha` | `22109, 22123, 22147, 22171, 22193, 22229` | `24109, 24133, 24151` |

这些 task IDs 与 seeds 不属于 SI-2、GCF、EMC 或 Direct/Repair 已消费 roots。R1 root 为 create-once；执行后这两个 episodes 只承担 probe-calibration 角色，不能改作 Operator value 或 search-value evidence。

## 预声明门

每个 state 都必须通过：

1. baseline 与 reference 均能通过 public test 和冻结 evaluator；
2. reference 至少比 baseline 高一个冻结 `score_resolution`；
3. baseline、三个 intermediate controls 与 reference 组成的 7 个预声明顺序 pair 至少恢复 6 个；
4. baseline 重复执行的 functional signature distance 精确为零；
5. baseline/reference functional signature distance 至少为 `0.10`。

Assignment 的 functional signature 是三个独立实例上的 facility assignment 向量；coverage 的 signature 是三个独立实例上的 covered-element indicator。它们不使用 candidate 自报标签或源码文本距离。

## 权威和资源边界

```text
model_calls = 0
provider_calls = 0
fresh_search_value_tasks_consumed = 0
claim_ceiling = PROBE_SENSITIVITY_NOT_REAL_BOTTLENECK_DIAGNOSIS
```

只有两状态全部通过，才输出 `MAY_PREREGISTER_BOUNDED_CMI_REAL_DIAGNOSIS`。这不是现实 bottleneck verdict，也不授权 Mechanism Brief、Operator 或 fresh search-value budget。

## 执行入口

```powershell
$env:PYTHONPATH = "src"
python -m discoveryos cmi-r1-seal-probes --workspace runs/cmi-r1-real-probe-calibration
python -m discoveryos cmi-r1-run-probes --workspace runs/cmi-r1-real-probe-calibration --manifest-digest <digest>
```
