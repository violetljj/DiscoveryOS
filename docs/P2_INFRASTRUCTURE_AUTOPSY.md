# P2 Infrastructure Autopsy

## 结论

`bounded_knapsack_beta-seed-17082601 / neither` 的 `3944.295s` 不是 provider/network wait，也不是算法 CPU 资源耗尽。它是一次可直接对齐 Windows Modern Standby 事件的主机挂起计时污染：本地 evaluator runner 的未细分区间跨越待机，实际记录的 Git patch、build、test 与 evaluator command 都在亚秒级完成。

因此 V3 的失败性质进一步收窄为 `INFRA_FAILURE_HOST_SUSPEND_TIMING_CONTAMINATION`。这不恢复 V3 的可评估性，不改变 `NOT_EVALUABLE`，不授权重跑、不允许用 9/12 blocks 计算 estimand，也不回答 Ada/EvoX 的科学问题。P3 保持关闭。

## 边界与方法

- 数据源只包括已消费的 `runs/p2-factorial-development-v3` receipts、per-arm SQLite ledger、content-addressed command/provider artifacts，以及本机 Windows System event log。
- 新增分析器 `discoveryos.benchmarks.p2_infrastructure_autopsy` 以 SQLite read-only URI 打开 ledger，只读既有 artifact；本次 `generation_calls_executed=0`。
- 关键统计与 Kernel-Power event identity 固化在 [`evidence/P2_INFRASTRUCTURE_AUTOPSY_V1.json`](evidence/P2_INFRASTRUCTURE_AUTOPSY_V1.json)，避免本机 event log 轮转后只剩叙述性结论。
- V3 create-once root 未修改、未续跑、未补 block、未重新聚合科学 outcome。
- `load_balance_alpha` 的 baseline failure 留给独立 autopsy；本文不根据 wall-time 证据猜测它的原因。

## 异常 arm 的逐秒分解

以下以 arm record 的 `end_to_end_makespan=3950.079s` 为闭合总量。`actual_usage.wall_seconds=3944.295s` 与 provider + evaluator receipts 精确相等；两者之间没有未入账科学资源。

| 类别 | 秒 | 占 end-to-end | 证据定义 |
|---|---:|---:|---|
| Provider calls | 58.703 | 1.486% | 两次 generation receipt：`38.187s`、`20.516s` |
| Git patch commands | 1.203 | 0.030% | 三次 baseline/patch-stack `git apply --recount` command receipts |
| Local build + public test | 0.799 | 0.020% | `py_compile` 与 `public_tests.py` command receipts |
| Evaluator command | 0.329 | 0.008% | 三次 `evaluate.py` command receipts |
| Runner uninstrumented interval | 3881.575 | 98.266% | runner-reported wall 减全部 command receipts；包含主机待机区间 |
| Scheduler/evidence overhead | 1.686 | 0.043% | evidence receipt wall 减 runner-reported wall |
| Outer harness residual | 5.784 | 0.146% | end-to-end 减 provider 与 evidence receipt wall |
| **合计** | **3950.079** | **100.000%** | 闭合到 arm end-to-end receipt |

异常 arm 的总 CPU 只有 `0.9375s`，wall/CPU ratio 为 `4207.25`。第二个候选的 evaluator receipt 是 `3882.199s wall / 0.390625s CPU / exit_code=0`；其内部 command receipts 分别为 patch `0.235/0.265/0.219s`、build `0.270s`、test `0.086s`、evaluate `0.138s`，全部 `timed_out=false`。候选是一个小型 Pareto-frontier knapsack 实现，冻结 evaluator 只有六个 5-item cases；现有证据反对“算法计算本身运行了约 64 分钟”。

## 主机待机对齐

Windows System log 的 `Microsoft-Windows-Kernel-Power` 事件给出：

| RecordId | Event | UTC | 原因 |
|---:|---:|---|---|
| 50104 | 506，进入 Modern Standby | `2026-08-17T21:04:05.4377906Z` | Idle Timeout |
| 50108 | 507，退出 Modern Standby | `2026-08-17T22:11:38.6404400Z` | Austerity Battery Drain Budget Exceeded |

异常 experiment 在 `2026-08-17T21:06:57.455394Z` 创建，resource reservation 在 `21:06:57.610578Z` 写入，在 `22:11:39.859071Z` reconciliation。从 experiment 创建到退出待机的重叠为 `3881.185s`，几乎完全解释 `3881.575s` runner-uninstrumented interval。恢复后 command receipts 正常完成并返回 `exit_code=0`，随后 wall reconciliation 才以 `BUDGET_EXHAUSTED:wall_seconds` fail closed。

这说明当前 timeout 和 wall ceiling 会把 OS suspend 时间计入科学 wall usage，但现有 receipts 没有记录 suspend-aware provenance；这是基础设施可评估性缺口，不是提高算法 wall budget 的理由。

## 正常 arms 对照

39 个 `EVALUABLE` arms 的只读统计为：

| 指标 | min | median | p95 | max |
|---|---:|---:|---:|---:|
| actual wall seconds | 51.765 | 158.831 | 228.220 | 230.094 |
| actual CPU seconds | 0.344 | 0.656 | 1.563 | 2.125 |
| wall/CPU ratio | 82.79 | 231.51 | 446.24 | 536.30 |
| outer harness residual seconds | 3.751 | 7.082 | 11.551 | 20.000 |

正常 arms 的 wall/CPU ratio 本来也很高，因为 provider latency 计入 wall、provider CPU 不在本地 evaluator CPU 中；所以 ratio 单独不能证明网络故障。异常 arm 的 ratio 仍高于正常最大值约 `7.85x`，而主机 power events 和 command-level receipts 给出了更强的归因证据。

## Provider path 对照

- 172 个既有 generation calls 的 duration 为 `15.719–83.641s`，median `32.141s`，p95 `60.468s`。异常 arm 的 `38.187s` 与 `20.516s` 都在正常范围内。
- 54 个 generation records 的 terminal status 是 `GENERATION_BUDGET_EXCEEDED:tokens`；这是冻结 token ceiling 的 fail-closed 结果，不是 timeout、retry 或 transport failure。
- transport logs 没有 retry event。原始文本中两个 `timeout` 字样来自生成内容/说明，不是 transport timeout event。
- 172/172 transport logs 都含同一个非终止 error item：`codex-code-mode-host.exe` 缺失，随后仍有 `agent_message` 和 `turn.completed`。它是 provider path 的一致性污染和未来 Executability Gate 应阻断的配置缺口，但因为所有 calls 都出现，且异常 arm provider durations 正常，它不能解释单个 3944 秒 outlier。

## Claim ceiling 与下一步

本 autopsy 只建立：

`P2_V3_WALL_OUTLIER_ATTRIBUTED_TO_HOST_SUSPEND_TIMING_CONTAMINATION`

它不建立：

- V3 的 P2 factorial estimands；
- Ada/EvoX main effect 或 interaction；
- provider/network 是本次 outlier 的原因；
- `load_balance_alpha` baseline failure 的原因；
- P3、fresh task、generalization 或 superiority authorization。

下一步顺序固定为：独立回答 `load_balance_alpha` baseline 为什么不可评估，然后在 consumed L0-L2 上实现零 generation-call Executability Gate。Gate 至少应要求 baseline evaluable、materialization replay、无 host-suspend overlap、正常 CPU/wall baseline、provider timing/terminal receipt 完整且无 transport error item；未来新 P2 还必须预声明 suspend、timeout、retry 与 transport failure 的 `INFRA_FAILURE` 语义。只有这些基础设施门通过，才允许新 cohort、新 create-once root 和重新 seal 的 P2；不得续跑 V3 或删掉已见失败 task。
