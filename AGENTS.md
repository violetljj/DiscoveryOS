# DiscoveryOS Agent Instructions

本文件是进入本仓库后必须读取的项目级工作约定。它保存长期有效的边界和执行规则，不保存容易过期的实验数字。开始任务前，先按任务读取下列真源：

1. `docs/PROJECT_CONTEXT.md`：项目目标、核心术语、架构和证据模型。
2. `docs/CURRENT_STATE.md`：已交付能力、当前 verdict、在研工作和下一道门。
3. `docs/DECISIONS.md`：已经确定、不得在无新证据时悄悄推翻的设计决策。
4. `docs/LOCAL_ENVIRONMENT.md`：本机常用解释器、工具、硬件和可调用 Codex CLI 的已验证位置。
5. 与任务直接相关的 admission、protocol 或 evidence 文档；不要无差别加载所有历史材料。

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

## 研究资产、复用与 freshness

- 默认规则是“旧题优先，新题后置”。测试资产分为可反复使用的开发资产和不可再生的科学资产；fresh task 的用途是升级 claim，不是查 bug。硬规则为 `NO_FRESH_TASK_FOR_DEBUGGING` 与 `FRESHNESS_IS_A_CLAIM_UPGRADE_RESOURCE`。
- 资产等级固定为：L0 Unit/Synthetic（无限复用）→ L1 Historical Failure Corpus（无限复用）→ L2 Consumed Dev Tasks/States（无限复用）→ L3 Locked Dev Holdout（有限开启，开启后按已消费开发资产管理）→ L4 Fresh Admission Tasks（一次性）→ L5 Blind Confirmation（极少且只在 winner 冻结后开启）。不得用低等级证据回答高等级问题。
- 日常 debugging、mechanics、failure reproduction、operator A/B、causal intervention、ablation、evaluator/budget/controller/parent/novelty 检查、性能 benchmark、deterministic replay 和 regression 默认只使用 L0-L2。刚实现、尚未证明 mechanics 或 causal transmission 的机制不得申请 L4/L5。
- 每个曾暴露真实 failure mode 的 task/state/receipt 都应作为长期回归资产登记；修复不得覆盖原始收据或改写历史 verdict。Parent starvation、weight collapse、novelty duplicate、functional basin trap、invalid propagation、evaluator mismatch、resource ceiling、contract transmission 等问题在相关机制改变后应重跑绑定的历史挑战。
- 开启 L4 前必须先在旧资产上形成相称证据链：mechanism works → control-flow changes → causal transmission exists → utility improves → 在多个相关 historical/consumed states 上不退化。通过这条链只获得 fresh admission 资格，不自动获得 search-value、generalization 或 superiority verdict。
- `新运行 ≠ 新 seed ≠ 新实例 ≠ 新任务分布 ≠ 新任务族 ≠ 新 evaluator regime`。Manifest/receipt 必须分别记录 instance、distribution、task family 和 evaluator regime 的 freshness/consumption 状态；数量统计不得只写 `fresh_tasks=N`。同一 family 的不同 seed 或规模变体通常只支持稳定性或 scaling，不得冒充 task-family generalization。
- 最强的泛化结论应保留未参与机制形成和调参的 task-family holdout；L5 final blind 只能在冻结 winner 后由 Certification 取得，永远不得回流选择 winner、阈值、prompt、operator 或策略。
- 复用结果按其资产等级限定 claim。Consumed Assignment 上的正向结果可以表述为 `OPERATOR_VALUE_DETECTED_ON_CONSUMED_ASSIGNMENT_DEV_STATE` 或同等窄结论，不得表述为 unseen-task generalization。重复次数、效应大小或回归全绿都不能单独提高 claim ceiling。

## 本地执行与性能

- Windows 本地环境的唯一维护入口是 `pwsh -NoProfile -File scripts/project.ps1 <doctor|bootstrap|test|run|rebuild>`。进入仓库先运行 `doctor`；不要裸用全局 `python`、`py -3.11` 或 `pip install`。项目 Python 由 `.python-version` 固定，依赖由 `pyproject.toml` 与 `uv.lock` 决定。
- `rebuild` 只允许删除解析后仍严格等于仓库根 `.venv` 且不是 junction/symlink 的目录；不得用它清理 `runs/`、收据、artifact 或任何 consumed evidence。

- 默认在当前本机完成开发、测试、benchmark 和正式研究运行。除非用户明确授权，或冻结协议本身要求特定外部设备/环境，不使用云端、远端 worker 或外部计算服务。
- 调用本机工具前先查 `docs/LOCAL_ENVIRONMENT.md`，并执行其中的轻量版本检查。路径清单是已验证快照，不替代运行时验证；尤其不要裸用解析到 WindowsApps 的 `codex`。
- 长时间或高资源任务启动前，先只读探测可用逻辑 CPU、内存、GPU/显存、磁盘空间和当前负载，再选择并发度、batch size、worker pool 和输出位置；不要硬编码某台机器的瞬时配置。
- 尽量利用本机性能：CPU-bound 独立单元优先采用有界多进程，I/O-bound 工作优先异步/流水化，GPU 工作在协议允许且数值语义不变时采用合适的 batch、预取和混合精度。独立 task/seed/arm 可并行，同一 Git worktree 的写操作和共享 create-once root 不并发。
- 并发度以实测吞吐、内存/显存余量和系统可交互性为准，逐级提高并保留安全余量；避免无界并行、内存换页、GPU OOM、磁盘打满或让机器长期失去响应。失败后不得用盲目提高并发重复冲击资源。
- 优先复用内容寻址缓存、已验证中间产物、断点续跑和 ledger 幂等状态，减少重复模型调用、重复 evaluator 执行和重复数据读取；缓存命中必须校验 contract/code/data/environment digest。
- 性能优化不得改变冻结 task、evaluator、seed、预算、数值容差或 acceptance gate。正式比较必须把本机资源指纹、worker/batch/concurrency 参数和实际 usage 写入 manifest/receipt，保证 matched-resource 公平与 replay 可解释。
- 只有本机资源确实成为已测量瓶颈，且当前阶段的 search value 已支持扩展时，才提出远端或分布式执行；迁移必须另行授权并保持同一证据权威。

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
