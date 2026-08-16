# R1.0-BR Local Patch Validity Repair

## 阶段结论

R1.0-B 的负结果已由提交 `d817b1d` 冻结并推送。R1.0-BR 只修候选生产可靠性，不修改 evaluator、原 search-value PASS 门、每个 root generation 最多一次 repair 的限制，也不增加模型搜索调用。

BR-A fresh readmission 已完成：可靠性门通过，但原 search-value 门失败。正式 verdict 继续是 `LLM_LOCAL_PATCH_NOT_ADMITTED`；这次负结果把当前瓶颈从 patch transport/reliability 移到了 operator/search policy，仍不授权进入 R1.0-C。

## Invalid Autopsy

对 `runs/local-patch-admission-r1` 的冻结 ledger、generation provenance、CandidateBundle 和 evidence 做了只读 autopsy；没有重调模型，也没有重跑科学 evaluator。

| 项目 | One-shot | Iterative |
|---|---:|---:|
| generations / materialized candidates | 8 / 8 | 20 / 20 |
| invalid candidates | 4 (50%) | 15 (75%) |
| repairs | 2 | 9 |

19 个 invalid 的主 failure taxonomy：

- `patch_parse_failure`: 14；
- `syntax_error`: 1；
- `unit_test_failure`: 4；
- `repair_failed`: 7（这是与上述根因重叠的 repair outcome 标签）；
- schema、path、environment lock、runtime、timeout 和 malformed evaluator output：0。

14 个 patch parse failure 中有 11 个可由确定性的 Git hunk recount 恢复。科学 lineage 中 invalid candidate 成为下一代 scientific parent 的次数为 0；但有 3 次在回退到有效 parent 后仍沿用了失败 child 的 evidence summary，形成 parent/evidence context mismatch。

不可变 autopsy v2 report file SHA-256：`0f80de9d063f02555b77acb75ba35a37b68b2a7eb3de7567d0ee54ce0710b4e7`（report 内部 canonical payload digest：`5433b9ee313019acbc0f7013a517e61f05ef150a7744f466d777c728b167b6a9`）。

## Reliability Repair

修复严格限于 mechanics：

- prompt 明确要求准确 hunk counts，并禁止 binary、rename、copy、create/delete、mode/dependency change；
- proposal validation 限制 64 KiB、400 changed lines，并要求 old/new headers 与显式 `target_files` 完全一致；
- 新版 `executable-candidate-v3` 将 `patch_apply_policy=recount_hunks` 冻结进 CandidateBundle；
- v1/v2 bundle 缺省保持 `strict_counts`，不能用新规则重解释旧冻结 candidate；
- runner 在 build/test 之前给出 `PATCH_PARSE_FAILURE` / `PATCH_APPLY_FAILURE` 和 patch stderr artifact；repair 仍只能读取机械诊断；
- scientific generation 必须使用当前 best feasible executable parent 及其匹配 evidence；invalid / NOT_EVALUABLE 只能进入一次 mechanical repair，不得进入正常 scientific lineage。

## BR-D Consumed Mechanics Replay

在 consumed corpus 的冻结 candidates 上，只重放 patch apply、environment lock、compile 和 public unit tests；没有模型调用、科学 evaluator 或科学 metrics。

| Arm | Mechanically invalid before | With v3 recount development policy |
|---|---:|---:|
| One-shot | 4/8 (50%) | 1/8 (12.5%) |
| Iterative | 15/20 (75%) | 5/20 (25%) |

这只说明确定性 repair 对当前 failure mode 有效，不是新的 admission，也不会覆盖旧 evidence。不可变 BR-D mechanics report file SHA-256：`2874676503470e06c367bfb2d5ef3ec2c8a0e5553685f7e89607f5f02b60f5f8`（report 内部 canonical payload digest：`10f35026b43d6282cd1fa82bc032698d7028c0fca69bda8d7e74cc769a1ae797`）。

## BR-A Fresh Readmission（已完成）

fresh corpus 必须有 6–8 个未消费的同等级真实代码任务，匹配 LOC、mutable scope、baseline headroom 和 test complexity；provider/model、每 task 每 LLM arm 90k token ceiling、CPU/wall/context/evaluator 与 One-shot/Iterative protocol保持一致。

Reliability gate：

```text
One-shot invalid rate <= 40%
Iterative invalid rate <= 40%
Iterative - One-shot invalid rate <= 10 percentage points
final-blind receipts = 0
all accepted candidate/evidence replay = PASS
```

原 search-value gate原封不动：successful tasks `+2`、summed improvement `+0.25`、paired wins 至少 2、paired losses 为 0。预冻结 policy digest：`015d99ede6f634d2fda921c9cfd5eed0ba3443d89b74c20e2b0f17130206db52`。

正式执行使用 8 个 fresh task；task id、category、target file 和 algorithm-source hash 与 consumed corpus 均零重叠。CandidateBundle 固定为 v3，repair policy 固定为 `recount_hunks`，provider/model 固定为 `codex-cli 0.148.0-alpha.9` / `gpt-5.4` / `medium`。task-set hash 为 `65400055073b58b205ff18591f6637a5d7cffaabfe33636bbce357f19c506acb`，sealed admission manifest digest 为 `00db70884e42769c4ac5a02e0fd1d280f679f39573c2d11b05dde04e96b8fe97`。

| Gate layer | One-shot | Iterative | Result |
|---|---:|---:|---|
| patch mechanics valid | 8/8 | 8/8 | PASS |
| executable / public tests valid | 8/8 | 8/8 | PASS |
| reliability invalid rate | 0% | 0% | PASS，gap 0pp |
| successful tasks | 8/8 | 8/8 | no `+2` margin |
| summed improvement | 5.50357143 | 5.50357143 | no `+0.25` margin |
| paired result | — | 0 win / 8 tie / 0 loss | search-value FAIL |

所有 accepted evidence replay 通过，final-blind receipts 为 0，matched-token ceiling 通过；两臂各 8 次 scientific call、0 次 model repair。One-shot 实际 input/output/cache tokens 为 `139467 / 5300 / 97280`，Iterative 为 `139469 / 6291 / 105472`。确定性 recount 在 G0 分别记录 16 次、1.7912s 和 16 次、1.8243s，模型 token 均为 0。

不可变 BR-A report file SHA-256：`147c19936b3b213b90cbf1d661ccef60dad9e5c6b8c93ae8a6b3e7cfde641d9c`；sealed manifest file SHA-256：`69466b53bd8b0cd0db2bbf9c65f038fccb69c70c555a923a16c601c39279d843`。没有 task replacement、threshold relaxation 或第二套 gate 解释。

第一次 pre-model 启动尝试因 WindowsApps 暴露的 `codex` 对子进程返回 `PermissionError` 而 fail-closed；两臂 ledger 均记录 0 tokens、无 raw response/provenance，未消费 task。正式 seal 要求 provider version 非 `unknown`，并使用本机可执行的 `C:\Users\26442\.codex\.sandbox-bin\codex.exe`。该基础设施 abort 不进入 BR-A verdict。

## Readmission 结论

```text
reliability = PASS
search_value = FAIL
LLM_LOCAL_PATCH_NOT_ADMITTED
```

因此不再把 parser/repair 当作当前主瓶颈，也不再在 consumed 或 BR-A corpus 上追加 repair/replay 来寻求翻案。后续若继续研究，必须面向 operator/search policy，并使用新的预冻结证据设计；在新的 admission 通过前，Local Patch 不进入 DiscoveryOS 搜索内核。
