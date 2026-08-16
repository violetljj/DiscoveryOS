# DiscoveryOS Agent Instructions

本文件是进入本仓库后必须读取的项目级工作约定。它保存长期有效的边界和执行规则，不保存容易过期的实验数字。开始任务前，先按任务读取下列真源：

1. `docs/PROJECT_CONTEXT.md`：项目目标、核心术语、架构和证据模型。
2. `docs/CURRENT_STATE.md`：已交付能力、当前 verdict、在研工作和下一道门。
3. `docs/DECISIONS.md`：已经确定、不得在无新证据时悄悄推翻的设计决策。
4. 与任务直接相关的 admission、protocol 或 evidence 文档；不要无差别加载所有历史材料。

如果代码、当前状态和旧文档冲突，先核查 Git 历史、测试及不可变收据，再修正文档；不得选择对预期结论最有利的一份材料。

## 项目使命

DiscoveryOS 是证据优先的统一算法研究内核。它把外部算法发现系统中有价值的机制重构成共享 Research Graph、Candidate/Evidence Store、Budget/Fidelity Controller、Memory 和 Runtime 上的内部原语。官方外部系统只允许作为隔离的 Benchmark Mode challenger，不能把各自的 population、memory、budget 或 evaluator 语义带进 Discovery Mode。

优先交付可运行、可重放、可证伪的纵向切片。不要用规格占位、空接口或机制数量代替实际发现能力；也不要为了治理完整而拖垮探索能力。探索策略可以快速演进，但证据权威、硬门、盲测隔离和 claim ceiling 不可绕过。

## 不可变权威边界

- 冻结 `ProblemContract` 定义目标、约束、fidelity/evaluator/data 绑定、winner rule 和 claim ceiling。
- `GateEngine` 是科学 verdict 权威。controller、operator、scheduler、Pareto utility 和任何 scalar score 只能决定资源分配，不能宣布科学胜负。
- mechanics smoke、单 seed、synthetic、development、消融或 consumed-task 结果不能升级为算法优越性、产品、安全或生产可用证据。
- 协议违规、系统/机械失败、hard-constraint failure、科学负结果和 `NOT_EVALUABLE` 必须分开记录；不得把 fail-closed 或无结果改写成负面科学结论。
- Discovery Mode 不得读取 G7 final blind。只有 winner 已按冻结规则确定后，Certification Mode 才能取得 G7 capability；blind 结果永远不得换 winner。
- receipt、artifact、contract、evaluator、data split、candidate 和 environment digest 是证据边界。create-once 或 consumed 资产不得原地修改、补写或通过换目录重跑来改写结论。
- replay 必须重新验证绑定并在要求时重执行冻结 evaluator，不能只验证 JSON 能解析或 hash 字段存在。
- 当前 `SplitVault` 是应用层 fail-closed capability，不是抵御同一 OS 用户恶意代码的安全沙箱。没有独立服务/身份隔离，不得声称 production blind isolation。

## 实施规则

- 修改前先运行 `git status --short --branch`，识别用户已有的 staged、modified 和 untracked 工作。共享工作树中不得覆盖、格式化、暂存或提交与本任务无关的改动。
- 优先做最小、可验证的纵向改动。新机制必须复用统一 candidate/evidence/budget/evaluator 权威，不能另建平行 verdict 或隐式预算系统。
- evaluator、协议门、任务选择、数据 split、winner rule 或 claim ceiling 的变化属于证据语义变化，必须显式版本化并新增协议/决策记录；不能把新旧结果混为同一实验。
- 任何模型调用前，先冻结需要防止事后选择的 task、模型/版本、prompt/settings、预算、evaluator、seed/replicate 和 acceptance gate。已看见候选输出后不得换题、放宽门槛或补免费调用。
- 失败默认 fail closed，并保留可诊断原因。相同失败重复两次且无新证据时，停止盲目重试，改查假设、状态和持久化证据。
- 生成物和运行目录放在忽略的 `runs/` 或明确的 artifact 根；只提交协议、代码、测试和适合公开且已脱敏的摘要/收据。
- 文档必须使用诚实的状态词，并明确区分 `implemented`、`mechanics ready`、`protocol only`、`development signal`、`admitted`、`not evaluable` 和 `production ready`。

## 验证规则

验证范围与改动风险成比例：

- 文档变更：检查链接、状态词、路径和 `git diff --check`。
- 隔离代码变更：运行受影响测试文件或最小 unittest target。
- module/API、budget、ledger、evaluator 或 gate 变更：运行相关模块测试，并覆盖 replay、idempotency、失败路径和不可变性。
- 跨模块证据语义、构建系统或正式 admission 变更：运行完整测试套件及协议要求的冻结验证。

默认测试入口：

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

测试通过只证明其覆盖的行为，不自动提高 claim ceiling。Windows 上涉及 SQLite 的测试还应确认连接关闭和临时目录可清理，不能忽略 `WinError 32` 或资源泄漏警告。

## Git 交付

- 默认直接在 `main` 主分支工作并向 `origin/main` 交付；只有用户明确指定其他分支、仓库策略禁止直推，或并发/隔离风险要求独立分支时才切换，并在行动前说明原因。
- 只暂存本任务拥有的路径，提交前检查 `git diff --cached --check` 和 staged diff。
- 将较长工作拆成边界清晰、可独立验证的阶段。每个阶段达到其验收标准并完成相称验证后，自动暂存该阶段拥有的文件、提交并推送；无需等待用户再次说“提交”或“推送”，也不主动创建 PR。
- 阶段提交前确认 `main` 与 `origin/main` 没有意外分歧；推送后确认本地与远端提交一致。不要为了制造提交而拆分尚未闭合或无法独立验证的中间状态。
- 遇到重叠 WIP、非 fast-forward、远端分歧、凭据问题或无法证明归属的改动时停止，不做自动 merge、reset、stash 或清理。
- Commit message 描述实际交付，不把 mechanics 写成 admission，也不把开发信号写成 scientific win。

## 文档维护契约

以下变化必须与代码在同一任务、最好同一提交中更新文档：

- 项目定位、模块职责或权威边界变化：更新 `docs/PROJECT_CONTEXT.md` 和必要的 `docs/DECISIONS.md`。
- 新阶段启动、完成、失败、撤回或 claim ceiling 变化：更新 `docs/CURRENT_STATE.md` 及对应协议/结果文档。
- 新的不可逆协议决策：追加 `docs/DECISIONS.md`，保留旧决策并标注 superseded，禁止静默改史。
- 状态数字、commit、模型版本和实验结果只写入阶段文档或 `CURRENT_STATE`，不要塞进本文件。

任务结束前确认新成员只阅读本文件及其路由文档，就能回答：系统要解决什么、谁有 verdict 权、当前真正证明了什么、哪些能力尚未证明、下一步允许做什么。
