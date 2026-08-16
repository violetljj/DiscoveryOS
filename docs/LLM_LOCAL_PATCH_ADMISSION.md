# R1.0-B Bounded LLM Local Patch Admission

## 冻结 verdict

```text
LLM_LOCAL_PATCH_NOT_ADMITTED
```

本轮证明了 bounded LLM Local Patch 的机械闭环可以工作：模型能在受限上下文中提出真实代码 patch，候选被内容寻址冻结，经过 G0/G1/G2 build/test/evaluation，并能从冻结 candidate 精确 replay。它没有证明 iterative Local Patch 相对同模型 one-shot 具有足够稳定的额外搜索价值，因此不授权进入 BlindAssist fresh 四臂赛马。

## 冻结协议

- provider：`codex_exec`，Codex CLI `0.147.0`，ChatGPT subscription authentication；
- model：`gpt-5.4`，reasoning effort `medium`；
- tasks：6 个真实 Python code tasks，每个仅 1 个 mutable file，覆盖 parameter logic、local algorithm、data structure、numerical algorithm、state/timing algorithm、sequence algorithm；
- arms：`Baseline / One-shot LLM / Iterative Local Patch`；
- 每个 LLM arm、每个 task 的总 input+output token ceiling：`90,000`；cache tokens 独立报告；
- iterative scientific call limit：3；每个 root generation 最多 1 次 mechanical repair；
- repair 只能读取 patch/build/test/timeout 机械诊断，不能读取科学指标；
- G0 static/build、G1 cheap proxy、G2 hidden development；`G7 final-blind` 禁止；
- PASS 需要 mechanics 全通过，并同时满足：iterative 成功任务数至少比 one-shot 多 2、累计 improvement 至少多 `0.25`、paired wins 至少 2、paired losses 为 0。

generation request、raw response、provider/model/settings、prompt-template digest、context digest、input/output/cache tokens、latency 和 transport log 都进入不可变 artifact。模型生成本身不要求逐字 replay；要求精确 replay 的是冻结 CandidateBundle 的 build/test/evaluation/evidence。

## 正式结果

| Task | Baseline | One-shot | Iterative | Paired delta |
|---|---:|---:|---:|---:|
| adaptive_step | 0.3000 | 0.5000 | 0.8000 | +0.3000 |
| stable_topk | 0.3333 | 1.0000 | 1.0000 | 0.0000 |
| lru_cache | 0.3333 | 0.3333 | 1.0000 | +0.6667 |
| stable_softmax | 0.4286 | 0.8571 | 1.0000 | +0.1429 |
| debounce_state | 0.2500 | 0.2500 | 0.2500 | 0.0000 |
| merge_intervals | 0.3333 | 1.0000 | 0.3333 | -0.6667 |

冻结汇总：

- paired：`3 胜 / 2 平 / 1 负`，median paired delta `+0.07142857`；
- success tasks：one-shot `4/6`，iterative `4/6`；
- summed best feasible improvement：one-shot `1.96190477`，iterative `2.40476191`；
- mechanics：PASS；所有 evidence replay 完整，hard-gate violations `0`，final-blind receipts `0`；
- matched token ceiling：PASS；没有 arm 超过每任务 `90,000` ceiling；
- search value：FAIL；成功任务数没有形成 `+2` margin，并且 `merge_intervals` 出现 1 个 paired loss。

## 资源与失败率

| Arm | Input tokens | Output tokens | Cache tokens | CPU actual | Experiment-wall sum | End-to-end makespan | Orchestration overhead |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 0 | 0 | 0 | 2.578s | 17.231s | 20.830s | 3.599s |
| One-shot | 143,298 | 6,605 | 119,808 | 4.734s | 32.620s | 229.276s | 13.651s |
| Iterative | 353,867 | 14,717 | 286,208 | 6.125s | 43.611s | 487.450s | 31.779s |

按所有物化 candidate 重新审计后：one-shot invalid rate 为 `4/8 = 50%`，iterative 为 `15/20 = 75%`；one-shot 使用 2 次 repair，iterative 使用 9 次。高 invalid/repair rate 是当前最明确的改进对象，但不能通过放宽 evaluator、隐藏 mechanics failure 或追加免费模型调用来修饰。

本地不可变报告：

- 原始正式报告 SHA-256：`a4acce64a4a11079caea74849eda86b5a52b1b44c430dd7348c25cbe9c1269ec`；
- candidate-validity audited report SHA-256：`b082a1c4625dcb5ebdddaba7e14e92b1df2a97a3080f90b856aa0236bd3f789c`；
- audit 未重新调用模型，verdict 未变化。

## 授权边界

当前只允许继续改进 R1.0-B 本身并在全新 workspace 重跑同等级 admission。仍不授权：

- BlindAssist fresh target 四臂赛马；
- Portfolio；
- BOHB / qNEHVI；
- Structural Rewrite；
- Meta-Strategy；
- 学习型 Advisor。

首要问题不是新增搜索器，而是降低合法 patch 的 invalid/repair rate，并证明 iterative 在 matched-token 下能稳定增加成功任务数且不产生 paired loss。
