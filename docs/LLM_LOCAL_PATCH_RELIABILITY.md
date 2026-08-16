# R1.0-BR Local Patch Validity Repair

## 阶段结论

R1.0-B 的负结果已由提交 `d817b1d` 冻结并推送。R1.0-BR 只修候选生产可靠性，不修改 evaluator、原 search-value PASS 门、每个 root generation 最多一次 repair 的限制，也不增加模型搜索调用。

当前状态是 **development evidence only**，不产生新的 Local Patch search-value claim，也不授权进入 R1.0-C。

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

## BR-A Fresh Readmission（预冻结）

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

在 fresh task artifact 与 protocol digest 冻结前，任何 consumed-corpus improvement 都只能报告为 `R1_0_BR_DEVELOPMENT_ONLY`，不能产生 `LLM_LOCAL_PATCH_ADMITTED_REAL_CODE_ONLY`。
