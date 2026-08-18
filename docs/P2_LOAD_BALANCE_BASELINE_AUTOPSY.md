# P2 `load_balance_alpha` Baseline Autopsy

## 核心结论

`load_balance_alpha` 的 untouched baseline **本身可被 evaluator 合法评分**。V3 的两个 replicate 在任何 generation call 前关闭，不是因为 task、initial source、materialization、evaluator contract、output parser、reference/dependency 或 score 有缺陷，而是因为 baseline evaluation 恰好跨越连续的 Windows Modern Standby / hibernate 状态；60 秒 evaluator deadline 把低功耗停顿计入 wall time，分别落成 `TIMEOUT:test` 与 `TIMEOUT:repository_setup`，随后又被资源 reconciliation 包装为 `BUDGET_EXHAUSTED:wall_seconds:prior=...`。

正式 failure class 为：

`ENVIRONMENT_INFRA_FAILURE_HOST_LOW_POWER_STATE_CONTAMINATION`

两个 replicate 的**直接失败分支不同，但底层原因相同**。P2 block runner 最后只保留通用 `BASELINE_EVALUATOR_NOT_EVALUABLE:neither` terminal label，因此若不读取 evidence receipt、command artifact 和 host power events，会丢失这个区别。

本轮 0 generation calls、未修改或续跑 V3 root、未实现 Executability Gate、未修任何 evaluator/runner 代码。

## 从 command 到 terminal 的完整路径

### seed `17082602`

1. baseline resource reservation：`2026-08-17T22:11:42.272129Z`，预算 `60s wall / 10s CPU`。
2. build command 正常：`python -m py_compile algorithm.py`，`exit=0`，`0.244s wall / 0.172s CPU`。
3. public test command：`python public_tests.py`，最终 `exit=0`，但 receipt 标记 `timed_out=true`，`12946.685s wall / 0.078s CPU`。
4. evaluator command与 output parser 均未执行；receipt 为 `NOT_EVALUABLE`。
5. runner 分支先产生 `TIMEOUT:test`；scheduler reconciliation 看到 `12948.247s > 60s`，写成 `BUDGET_EXHAUSTED:wall_seconds:prior=TIMEOUT:test`。
6. P2 preparation loop 只检查 `baseline.validity is NOT_EVALUABLE`，把 block terminal 收敛为 `BASELINE_EVALUATOR_NOT_EVALUABLE:neither`。

对应主机事件：Kernel-Power Record `50110` 在 `2026-08-17T22:11:38.6426638Z` 进入 Modern Standby；Record `50115` 在 `2026-08-18T01:47:28.2461457Z` 退出。test 的约 12946.7 秒 wall interval 几乎完全落在这段低功耗窗口内。

### seed `17082601`

1. baseline experiment 在 `2026-08-18T01:47:31.848088Z` 创建，reservation 在 `01:47:31.955798Z` 写入。
2. Kernel-Power Record `50119` 在 `01:47:31.5412449Z` 记录 `Hibernate from Sleep - Standby Battery Budget Exceeded`。
3. 运行停在 repository verification/worktree setup 后、首个可持久化 command log 前；恢复后 `_remaining(deadline)` 已小于零，outer runner branch 产生 `TIMEOUT:repository_setup`。因此该 receipt 的 command artifacts 为空。
4. Kernel-General Record `50122` 记录系统时间从 `01:47:33.395457600Z` 跳到 `05:20:07.500000000Z`，增量 `12754104ms`；Power-Troubleshooter Record `50144` 给出的低功耗窗口是 `01:47:28.244056300Z → 05:20:10.472102100Z`。
5. scheduler reconciliation 记录 `12760.051s wall / 0.046875s CPU`，最终为 `BUDGET_EXHAUSTED:wall_seconds:prior=TIMEOUT:repository_setup`，随后同样被 P2 terminal label 泛化。

materialized repository 仍留有原运行创建的 prunable temp worktree reference，目标为已经不存在的 `C:/Users/26442/AppData/Local/Temp/discoveryos-worktree-cj90wpsn/repo`。Autopsy 只读取该 provenance，没有 prune 或修改 V3 repository。

## Exact replay

从两个 V3 materialized repositories 的冻结 commit 出发，在独立临时目录中：

1. 以 `core.autocrlf=false` 克隆，保持 `requirements.lock` 字节身份；
2. 使用同一 frozen baseline marker patch；
3. 通过相同 `ExecutableCandidateEvaluator → IsolatedRepositoryRunner` 路径；
4. 执行相同 build、public test、evaluation 和 output parser；
5. 不调用 provider，不生成候选，不写 V3 root。

| V3 source | Full evaluator validity | score | valid | failure |
|---|---|---:|---:|---|
| `load_balance_alpha-seed-17082601` | `VALID` | `0.3565120065120065` | `1.0` | `null` |
| `load_balance_alpha-seed-17082602` | `VALID` | `0.3565120065120065` | `1.0` | `null` |

两次 replay 都在约 `0.7s` wall 内完成。V3 seal manifest 在 scientific execution 前也已经对同一 baseline 得到两次完全一致的 `0.3565120065120065`。因此原失败不可归因为 baseline 语义或 evaluator 评分路径。

普通 Windows clone 首次会受 checkout 配置影响；不显式保留 source repo 的 `core.autocrlf=false` 会令临时副本的 `requirements.lock` 发生 CRLF 字节漂移，并正确触发 `ENVIRONMENT_LOCK_MISMATCH`。这是 replay-induced drift，不是 V3 原 failure；正式 replay 已绑定原配置。该诊断同时说明 future replay gate 必须验证 materialized bytes，不能只复制文本含义。

## `alpha ↔ beta` differential

| Surface | alpha vs beta |
|---|---|
| `algorithm.py` / initial source | 完全相同；SHA-256 `7fb14e...ddd0` |
| `public_tests.py` | 完全相同；SHA-256 `babb16...d477` |
| `requirements.lock` | 完全相同；SHA-256 `38e945...cf4` |
| build / test / evaluation commands | 完全相同 |
| runner、evaluator wrapper、parser path | 完全相同 evaluator binding `5781bc...c120` |
| reference source | 完全相同 digest `87c6aa...ea1a` |
| three intermediate sources | 完全相同 digests |
| evaluator source | 只有 `CASES` workload 不同；其余 contract、validity 与 JSON shape 相同 |
| sealed baseline replays | alpha `0.356512... ×2`；beta `0.363105... ×2`，均 finite/valid/deterministic |
| V3 execution timing | beta blocks 2/5 在低功耗窗口前可评估；alpha blocks 7/8 与 standby/hibernate 对齐 |

两个 alpha materializations 的 Git tree 都等于 manifest-bound `e61dcc123018cdc0d223662ccf13f83eac7a8ee8`；两个 beta tree 都等于 `e741be4c0fbceab082b3e91c876540fcc7cd0ed4`。alpha 两个 replicate 的四个 task file digest 完全一致。没有 materialization divergence。

`evaluate.py` 的唯一 task-level差异是冻结 `CASES`；alpha case 数与规模不高于足以解释 3.5 小时执行的量级，而且 exact replay 的 evaluation command 约 `0.05s`。所以 differential 反对 `TASK_NOT_BASELINE_EVALUABLE`、`EVALUATOR_CONTRACT_DEFECT` 与 `MATERIALIZATION_DEFECT`，支持时间相关的 environment failure。

## Failure classification

| Candidate class | Verdict | 证据 |
|---|---|---|
| `TASK_NOT_BASELINE_EVALUABLE` | rejected | seal replay 与两次 exact replay 均 finite、valid、deterministic |
| `EVALUATOR_CONTRACT_DEFECT` | rejected | full evaluator/parser replay通过；beta 共用相同 contract path |
| `MATERIALIZATION_DEFECT` | rejected | replicate file/tree identities 完全匹配 manifest |
| initial source / build / import defect | rejected | source相同，build成功，exact replay成功 |
| output parsing / non-finite score | rejected | 原运行未到 parser；replay JSON 合法且 score finite |
| dependency / reference data defect | rejected | stdlib-only lock，reference/intermediate 绑定相同且不在失败路径 |
| `ENVIRONMENT_INFRA_FAILURE` | **confirmed** | 两次 receipt 的巨大 wall/极低 CPU 与独立 host power events 对齐 |

更精确的最终类别是 `ENVIRONMENT_INFRA_FAILURE_HOST_LOW_POWER_STATE_CONTAMINATION`，其两个 observed subtypes 为：

- `HOST_SUSPEND_TIMEOUT_DURING_TEST`
- `HOST_HIBERNATE_DEADLINE_EXPIRED_DURING_REPOSITORY_SETUP`

## Claim ceiling 与下一步边界

这次 autopsy 只证明 V3 的两个 `load_balance_alpha` baseline failures 是同一 host low-power infrastructure class 的不同 runner manifestations。它不恢复 V3、不授权删 task、补 block或重算 9/12 estimands，也不实现或通过 Executability Gate。

Gate 设计阶段现在有一个必须保持的语义：baseline evaluability 不能只检查 terminal `VALID/NOT_EVALUABLE`；还必须绑定 materialized bytes、逐 command terminal/timing、host sleep/hibernate timeline 与完整原始 failure chain，避免 reconciliation 和 block terminal label 抹平最低层原因。Gate 的实现与 consumed L0-L2 population validation 留给下一独立阶段。

机器可读摘要见 [`evidence/P2_LOAD_BALANCE_BASELINE_AUTOPSY_V1.json`](evidence/P2_LOAD_BALANCE_BASELINE_AUTOPSY_V1.json)。
