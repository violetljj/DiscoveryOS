# Causal Intervention Bench V1

## Verdict

```text
CAUSAL_INTERVENTION_BENCH_MECHANICS_READY
CIB_SYNTHETIC_SENSITIVITY_ESTABLISHED
NO_REAL_MECHANISM_INTERVENTION_ADMITTED
DO_NOT_OPEN_SI3_FRESH_BUDGET
```

本阶段把 SI-2 autopsy 暴露出的缺口实现为最小可运行观测层。它只运行确定性的 synthetic mechanics fixture，不调用模型、不执行真实 task evaluator、不消费 fresh task，也不读取或写回 SI-2 create-once root。

Synthetic fixture 的 create-once manifest digest 为 `36906c865a48022ddd61f6257e7698d0a1a71127cd7273a416405de26f4b40ac`；manifest file SHA-256 为 `bea39a2803507d454c995d4bff6fc11186831bd067c9007f7dfbe1621f61eee5`。最终报告 SHA-256 为 `17261f398218713c29212e6f4b16ef18f20951ab0a7d45455d79981fc38827f2`。

该结果只证明 bench 能保存并判别预先构造的 null、intervention 和 positive effects。报告中的 `INTERVENTION_VALUE_ADMITTED` 明确属于 `SYNTHETIC_PARENT_INTERVENTION_FIXTURE`，不是现实 Parent、Novelty、Memory 机制 admission，也不是 search-value 证据。

## Frozen paired design

每个冻结 decision state 保存：

- state、mechanism、policy、default action、intervention action 和 positive-control action identity；
- candidate 生成前冻结的 behavioral probe digest；
- 相同 downstream step、token 和 evaluator-call ceiling；
- policy invocation、实际 treatment action、独立 stochastic draw 和即时 control-flow change receipt。

每个 state 执行三种 pair：

```text
NULL          default A vs default A, independent draws
INTERVENTION  default A vs selected alternative B
POSITIVE      default A vs deliberately distinct positive action P
```

V1 fixture 冻结 3 个 validation states。每个 state 使用 4 个 null pairs、3 个 intervention pairs 和 2 个 positive pairs，共 27 个 create-once paired receipts。Null envelope 在每个 state 内分别用独立 `A/A` repeats 的最大绝对差构造，不把跨 state 差异误当 stochastic variance。

Positive control 只判断观测链是否有能力识别行为和后代 utility 差异，不计入被测机制收益。Proposal semantic digest 保留为解释面；主要 manipulation check 使用冻结 behavioral signature，因为随机生成可以让 source/semantic identity 变化却不产生行为差异。

## Measurement and gate

每个 branch 保存：

```text
proposal semantics digest
behavioral signature
immediate fitness
descendant best-of-k
anytime AUC
token cost
evaluator cost
```

Admission cascade 为：

1. intervention receipt、state binding 和 matched downstream budget 有效；
2. behavioral distance 超过 state-local null envelope 与冻结 margin；
3. effect 超过 immediate child，并在 descendant final 与 anytime AUC 中持续；
4. benefit 出现在 utility，或在等价 utility 下出现超过 null 的成本收益；
5. effect 至少在 2 个独立 decision states 上复现。

诊断终态保持分离：

```text
BENCH_SENSITIVITY_NOT_ESTABLISHED
INTERVENTION_NOT_REALIZED
BEHAVIOR_CHANGED_UTILITY_EQUIVALENT
IMMEDIATE_EFFECT_NOT_TRANSMITTED
INTERVENTION_VALUE_ADMITTED
```

Synthetic run 的 positive control、behavior change、immediate effect、persistence 和 benefit 均在 `3/3` states 被检测到，因此 bench sensitivity 成立。该构造结果用于验证 gate 的可达性，不估计现实 effect size。

## Parent-policy development trace

在 synthetic sensitivity 通过后，V1 又把实际 `ShinkaWeightedParentSelectionPolicy` 接入 CIB。该阶段使用三个已消费的 MVP-0 development tasks：bounded knapsack、conflict coloring 和 load balance；不重写旧结果，也不把这些 task 重新用于 search-value admission。

```text
PARENT_CIB_DEVELOPMENT_TRACE_COMPLETE
PARENT_VALUE_TRANSMISSION_DETECTED_ON_SEMANTICS_PRESERVING_DEV_REPLAY
REAL_PARENT_MECHANISM_NOT_ADMITTED
```

Parent-dev manifest digest 为 `92558fb944b9062ce88b7f3fd2aa6e86968251cc9ded2365dfe120b55e517ec6`，manifest file SHA-256 为 `22176d19fcd13d8d669b7a32e0c74f5a6d147783c885d55d7bccfa21bd59f8ec`，最终 report SHA-256 为 `50404450613130fba2b9823c2b3e50504dc4e8883506952fb3e3778a9394ad67`。

三个冻结 policy receipts 均可重放，并都选择了 non-incumbent alternative parent。每个 state 有 2 个 null、2 个 intervention 和 2 个 positive pairs，共 18 个 paired receipts。冻结 probe 直接执行仓库内受信任的算法源码，并在任务的已消费 evaluator cases 上生成行为向量和 domain utility；没有启动真实 evaluator 子进程。

观测到的 alternative-minus-incumbent utility delta 为：

| State | Behavioral distance | Immediate / descendant / AUC delta |
|---|---:|---:|
| bounded knapsack | `4.0000` | `+0.345814` |
| conflict coloring | `2.6352` | `+0.074729` |
| load balance | `3.8730` | `+0.626821` |

这建立的是一个有界 development signal：真实 policy invocation 能被绑定到 parent 改变，而该 parent 差异能穿过一个相同的 deterministic、semantics-preserving downstream replay 到达行为和 utility。它仍不是现实 Parent value admission，原因是：

- states、alternative sources 和 seeds 是为 mechanism exercise 构造的，不是 outcome-blind representative sample；
- `A/A` null 在 deterministic replay 中为零，不能估计 strong-agent stochasticity；
- downstream operator 不生成新 child，只复放被选 parent 的语义，因此 persistence 是可检测性检查，不代表真实多代传导；
- probe 使用 consumed development cases，不能建立 fresh search value。

## Evidence boundary and next gate

当前允许的最强状态是 `MECHANICS_READY`：

- 没有真实 Parent、Novelty 或 Memory frozen-state adapter；
- 已有实际 Parent policy adapter，但没有 representative strong-agent candidate generator；Novelty 与 Memory 仍没有 frozen-state adapter；
- Parent-dev 只在进程内执行受信任源码和 frozen probes，没有启动正式 task evaluator process；
- 没有 calibration/validation state split；V1 thresholds 来自预声明 synthetic fixture，而不是由生成结果拟合；
- 没有现实模型 stochastic null distribution；
- 没有建立 algorithmic-basin change 或 DiscoveryOS search value。

下一步不是开启 SI-3，而是为一个真实机制实现 CIB adapter。真实 admission 必须先用 calibration states 冻结 probe/margin，再在未参与校准的 dev states 上运行；不得用同一 states 同时定义差异阈值并宣布 admission。只有一个真实机制取得可重放的 `INTERVENTION_VALUE_ADMITTED` 后，才可另行判断 `SI3_FRESH_BUDGET_ELIGIBLE`。

CIB-R1 已把这一门实现为 actual consumed SI-2 Parent receipts 上的 strong-agent stochastic downstream protocol；在其封存和执行完成前状态仍为 `PROTOCOL_READY_NOT_SEALED`。见 [`CIB_R1_REAL_DOWNSTREAM_CAUSAL_TRIAL.md`](CIB_R1_REAL_DOWNSTREAM_CAUSAL_TRIAL.md)。

## Entrypoints

```powershell
$env:PYTHONPATH = "src"
python -m discoveryos cib-seal-synthetic --workspace runs/cib-synthetic-r1
python -m discoveryos cib-run-synthetic `
  --workspace runs/cib-synthetic-r1 `
  --manifest-digest 36906c865a48022ddd61f6257e7698d0a1a71127cd7273a416405de26f4b40ac

python -m discoveryos cib-seal-parent-dev --workspace runs/cib-parent-dev-r1
python -m discoveryos cib-run-parent-dev `
  --workspace runs/cib-parent-dev-r1 `
  --manifest-digest 92558fb944b9062ce88b7f3fd2aa6e86968251cc9ded2365dfe120b55e517ec6
```

运行产物位于忽略的 `runs/cib-synthetic-r1` 与 `runs/cib-parent-dev-r1`；只提交实现、测试和本阶段诚实摘要。
