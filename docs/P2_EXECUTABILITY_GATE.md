# P2 Executability Gate V1

## 结论

DiscoveryOS 已实现并在 consumed L0-L2 population 上通过零 generation-call Executability Gate。它同时是 preventer 与 detector：Windows scientific session 必须先取得 `SYSTEM_REQUIRED + EXECUTION_REQUIRED` power request，确认 lease 建立时宿主机不在既有低功耗窗口内，完成 untouched baseline full-evaluator replay，随后才允许进入 scientific callback；session 结束前还必须完成 power-event 与 timing/provider provenance reconciliation。任一环节缺失均 fail closed，block 不能进入 factorial estimand。

正式资格状态为：

`EXECUTABILITY_GATE_QUALIFIED_ON_CONSUMED_L0_L2`

这只建立 mechanics/consumed-development executability。它不设计或 seal 新 P2，不恢复 V3，不决定 future infrastructure recovery/backfill，也不授权 P3、fresh/SEALED task 或任何 Ada/EvoX value claim。

机器可读摘要见 [`evidence/P2_EXECUTABILITY_GATE_QUALIFICATION_V1.json`](evidence/P2_EXECUTABILITY_GATE_QUALIFICATION_V1.json)。

## 执行顺序

```text
acquire Windows power-inhibition lease
  -> query current/recent power state
  -> reject an already-active standby/hibernate window
  -> materialize immutable task copy
  -> run untouched baseline twice through full evaluator/parser
  -> require finite VALID deterministic score and exact tree identity
  -> reconcile baseline timing/provider provenance
  -> optional scientific block
  -> reconcile scientific timing/provider provenance
  -> query overlapping sleep/resume/hibernate/clock events
  -> release inhibition lease
  -> admit only if every stage passed
```

Lease 必须覆盖 baseline、scientific callback 和 post-run reconciliation；release failure 同样阻止 admission。Power event query 使用 Windows System log 中 Kernel-Power `42/107/506/507`、Power-Troubleshooter `1` 与 Kernel-General clock-change `1`。查询前先验证 System log 可访问；provenance 不可用不会被伪装成“没有事件”。

第一次 live qualification 在 lease 建立前约 31 秒已经进入 Modern Standby（Kernel-Power record `50491 / event 506`）。原型在 post-run reconciliation 正确拒绝前两题，但这证明“成功 acquire lease”不能推翻一个已经开始的低功耗窗口。V1 因此加入 lease 后、baseline 前的 active-state precheck；host 醒来后重新执行 canonical qualification，六题全部 PASS。该开发过程没有 scientific generation call。

## 五层 gate

### 1. Host Power Integrity

`WindowsPowerInhibitionLease` 通过 `PowerCreateRequest` 同时建立 `PowerRequestSystemRequired` 与 `PowerRequestExecutionRequired`。API 不可用、任一 request 设置失败或最终清理失败都产生独立 infra failure。该 lease 防 idle low-power transition；显式 lid/power/user action 等仍由 post-run detector 审计。

### 2. Power-state provenance

Gate 读取最长 24 小时 lookback，以识别 session 开始前尚未闭合的 sleep/Modern Standby entry，并保留 session 内所有相关 transition。任何重叠统一分类为：

`INFRA_FAILURE_HOST_LOW_POWER_STATE_CONTAMINATION`

event source/权限/解析不可用则分类为 `INFRA_FAILURE_POWER_STATE_PROVENANCE_UNAVAILABLE`，不能冒充 host awake。

### 3. Baseline Evaluability

每个 task 在 0 generation calls 下必须满足：

- source Git tree、clone tree 与 manifest-bound tree 完全相同；clone 强制 `core.autocrlf=false`；
- untouched baseline 走两次完整 build/test/evaluator/parser；
- 两次均为 `VALID`，`valid=1.0`，score finite；
- score 在 `1e-12` tolerance 内确定性一致；
- 原始 timeout/failure signature 必须为空。

`load_balance_alpha` 在 canonical qualification 中再次得到 `0.3565120065120065 × 2`，与 V3 seal 和 immutable exact replay 一致。

### 4. Timing/provider reconciliation

`TimingBreakdown` 分开记录 provider wait、repository setup、build/test、evaluator、harness overhead、CPU 与 total wall。两次 baseline replay 的未解释 wall allowance 冻结为：

`max(2.0 seconds, 20% of total wall)`

2 秒绝对值覆盖 consumed qualification 中两次正常 runner worktree/Git 未细分区间；canonical 六题实际为 `1.024–1.062s`。比例项用于较长、但已单列 provider wait 的 session。V3 的约 `3881.575s` 未细分污染远超该门，不能再被结算成算法 wall resource。

Provider 的 call/terminal/timing receipt 数必须相等；retry、timeout 或 transport error 均为显式 infra failure。零 provider-call baseline 的三项计数必须共同为零。

### 5. Consumed L0-L2 qualification

Canonical live qualification 使用 V3 六个 L2 consumed tasks，每题从 seed `17082601` immutable materialization 独立 clone，并执行两次 untouched baseline：

| Task | score ×2 | total wall | CPU | power overlap | verdict |
|---|---:|---:|---:|---:|---|
| `bounded_knapsack_alpha` | `0.5890599680732508` | 1.937s | 0.234s | 0 | PASS |
| `bounded_knapsack_beta` | `0.4726732039907509` | 1.828s | 0.266s | 0 | PASS |
| `conflict_coloring_alpha` | `0.9052706552706553` | 1.844s | 0.219s | 0 | PASS |
| `conflict_coloring_beta` | `0.8199760983797986` | 1.844s | 0.219s | 0 | PASS |
| `load_balance_alpha` | `0.3565120065120065` | 1.907s | 0.266s | 0 | PASS |
| `load_balance_beta` | `0.36310499609679936` | 1.828s | 0.250s | 0 | PASS |

L0 adversarial matrix 对 awake、suspend、hibernate、timeout、100 秒 unexplained wall、lease failure 与 materialization drift 共 7 个 fixture 全部命中预期 class。Focused unit suite 另覆盖 non-finite/nondeterministic baseline、parser defect、provider receipt mismatch/retry/timeout/transport error、event provenance failure、lease release failure，以及 scientific callback 只有在 preflight PASS 后才会执行。

## Failure classes

Gate V1 至少输出：

- `INFRA_FAILURE_POWER_INHIBITION_UNAVAILABLE`
- `INFRA_FAILURE_POWER_INHIBITION_RELEASE_FAILED`
- `INFRA_FAILURE_POWER_STATE_PROVENANCE_UNAVAILABLE`
- `INFRA_FAILURE_HOST_LOW_POWER_STATE_CONTAMINATION`
- `INFRA_FAILURE_EXECUTION_TIMEOUT`
- `INFRA_FAILURE_TIMING_RECONCILIATION`
- `INFRA_FAILURE_PROVIDER_PROVENANCE_INCOMPLETE`
- `INFRA_FAILURE_PROVIDER_PATH`
- `MATERIALIZATION_DEFECT`
- `TASK_NOT_BASELINE_EVALUABLE`
- baseline/scientific execution exception classes

这些是 admission/infrastructure semantics，不是 GateEngine 的 scientific verdict，也不能用于推断某个 profile 或算法的好坏。

## Evidence boundary

- Canonical ignored receipt root：`runs/executability-gate-qualification-v1-final2`；receipt SHA-256 `7a18a651798e1d99dfe5c354a75cdd8cdff66c92b63020ab4d17071292401a7f`。
- Qualification digest：`ef3412803754d6412521fd51ef3a73965eca88ee55343db91670bc179361c56f`；Gate/qualification source digests 分别为 `8d965662...851987` / `6dac162f...e65736`。
- V3 manifest 只读 SHA-256：`54e537a5c4a95b68380c40993cc0ad4f90d901c769be25dff1465da3dda637b2`。
- 0 generation calls、0 provider calls、0 fresh/SEALED assets；V3 root 与 9/12 outcomes 未修改或重聚合。

下一步才允许单独设计新的 P2 revision。Future protocol 对 confirmed host infra failure 是整轮 `NOT_EVALUABLE`，还是允许事前冻结的 exact checkpoint continuation，仍是未决定的协议问题；本 Gate 不替该决定越权。
