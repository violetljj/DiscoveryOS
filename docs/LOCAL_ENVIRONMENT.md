# DiscoveryOS 本机环境清单

> 验证日期：2026-08-17。本文件记录当前开发机上的可用位置和选择规则。版本、剩余空间及 Codex Desktop 管理的路径可能变化，正式运行前必须重新执行轻量验证；不要把本页快照当作冻结实验 receipt。

## 首选项目入口

| 用途 | 首选位置 | 已验证状态 |
|---|---|---|
| 仓库根 | `E:\DiscoveryOS` | `main` 跟踪 `origin/main` |
| 项目 Python | `E:\DiscoveryOS\.venv\Scripts\python.exe` | Python 3.11.9 |
| 源码导入 | `E:\DiscoveryOS\src` | 运行测试/CLI 时设置 `PYTHONPATH=src` |
| site-packages | `E:\DiscoveryOS\.venv\Lib\site-packages` | editable `discoveryos 0.1.0` |

项目当前 `pyproject.toml` 的 runtime dependencies 为空，核心只依赖 Python 3.11+ 标准库。现有 `.venv` 没有 `pip` 模块；不要假设 `.venv\Scripts\pip.exe` 存在。日常运行使用：

```powershell
$env:PYTHONPATH = "src"
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
& .\.venv\Scripts\python.exe -m discoveryos --help
```

如需改变依赖，应先更新 `pyproject.toml` 和锁定策略，再用 `uv` 创建/同步环境；不要临时向现有 venv 安装未记录包后把结果当作可重放证据。

## 常用工具

`E:\codex-tools\bin` 提供统一包装器，并为其子进程设置配套 PATH。对脚本和可重放运行，优先使用下表的显式位置，避免同名工具解析漂移。

| 工具 | 推荐入口 | 实际程序/当前版本 |
|---|---|---|
| Python（通用） | `E:\codex-tools\bin\python.cmd` | `E:\codex-tools\tools\python-3.14\python.exe`；3.14.5 |
| pip（通用 Python） | `E:\codex-tools\bin\pip.cmd` | 上述 Python 的 `-m pip` |
| uv | `E:\codex-tools\bin\uv.cmd` | `E:\codex-tools\tools\uv-bin\uv.exe`；0.11.15 |
| Git | `D:\Git\cmd\git.exe` | 2.55.0.windows.2 |
| bundled Git | `E:\codex-tools\bin\git.cmd` | `E:\codex-tools\tools\git\cmd\git.exe`；2.54.0.windows.1 |
| GitHub CLI | `E:\codex-tools\bin\gh.cmd` | `E:\codex-tools\tools\gh\bin\gh.exe`；2.92.0 |
| PowerShell | 当前 Codex runtime 的 `pwsh.exe` | 7.6.4；路径在 `%USERPROFILE%\.cache\codex-runtimes\...` 下，运行时用 `$PSHOME` 解析 |
| NVIDIA 工具 | `C:\Windows\System32\nvidia-smi.exe` | 驱动/GPU 状态查询 |

快速验证：

```powershell
& .\.venv\Scripts\python.exe --version
& E:\codex-tools\bin\uv.cmd --version
& D:\Git\cmd\git.exe --version
& E:\codex-tools\bin\gh.cmd --version
& C:\Windows\System32\nvidia-smi.exe
```

Git 有系统安装版和 bundled 版。交互式仓库操作当前优先 `D:\Git\cmd\git.exe`；正式 manifest/receipt 必须记录实际解析到的 executable/version，而不是只记录命令名。

## 可调用的 Codex CLI

### 首选入口

```text
%USERPROFILE%\.codex\.sandbox-bin\codex.exe
```

2026-08-17 已验证：

```text
codex-cli 0.148.0-alpha.9
```

PowerShell 调用方式：

```powershell
$codexCli = Join-Path $env:USERPROFILE ".codex\.sandbox-bin\codex.exe"
& $codexCli --version
& $codexCli exec --help
```

每次封存含模型调用的实验前必须：

1. 用 `Test-Path -LiteralPath $codexCli` 确认文件存在；
2. 运行 `--version`，拒绝空值、`unknown` 或启动错误；
3. 把解析后的绝对路径、版本、model、reasoning effort 和相关 settings 写入 manifest；
4. 在第一次模型调用前冻结这些字段，运行中不得静默换 CLI/provider。

### 已知不可用入口

裸命令 `codex` 当前会解析到：

```text
C:\Program Files\WindowsApps\OpenAI.Codex_*\app\resources\codex.exe
```

该入口在子进程中已验证为 `拒绝访问` / WinError 5，不得用于 DiscoveryOS provider。`.codex\.sandbox-bin` 下的 `codex-command-runner-*.exe` 也不是 CLI，它们需要内部 pipe 协议，不能用 `--version` 代替 Codex CLI。

### PATH 集成（已启用）

不覆盖或拼接保存整段用户 PATH。`E:\codex-tools\bin` 已在 WindowsApps 之前，当前已新增：

```bat
@echo off
"%USERPROFILE%\.codex\.sandbox-bin\codex.exe" %*
```

文件位置为 `E:\codex-tools\bin\codex.cmd`。2026-08-17 已在全新 PowerShell 子进程中验证：

```powershell
Get-Command codex -All
codex --version
```

首个解析结果为 `E:\codex-tools\bin\codex.cmd`，`codex --version` 返回 `codex-cli 0.148.0-alpha.9`，`codex exec --help` 正常。WindowsApps 入口仍会出现在后续候选中，但不再优先命中。

包装器只解决命令解析，没有修改用户/系统 PATH。Codex Desktop 更新后仍需重新验证版本和实际 exe；如果 `%USERPROFILE%\.codex\.sandbox-bin\codex.exe` 消失，包装器应 fail closed，而不是退回 WindowsApps。

## 本机性能快照

| 资源 | 2026-08-17 观测值 |
|---|---|
| CPU | Intel Core Ultra 7 251HX；18 cores / 18 logical processors |
| 内存 | 15.43 GiB |
| GPU | NVIDIA GeForce RTX 5060 Laptop GPU；8151 MiB；driver 610.88 |
| C: | 400.0 GiB，总剩余约 203.6 GiB |
| E: | 195.3 GiB，总剩余约 93.4 GiB |

这些值只用于初始容量判断。高资源运行仍须读取实时可用内存/显存、磁盘余量和系统负载；不要根据总容量直接开满并发。独立 task/seed/arm 可并行，共享 Git worktree、SQLite 写热点和 create-once output root 应隔离或串行。

## 环境漂移处理

- 首选路径不存在或版本变化时，先重新发现并验证，不自动退回 WindowsApps `codex`。
- 工具升级可能提高工程能力，但已封存实验继续使用其冻结 provider/environment；新版本创建新 manifest，不混写旧 root。
- `.venv`、Codex runtime cache 和 Desktop-managed binaries 都是本机资产，不提交到 Git。
- 本页发生路径/版本变化时及时更新验证日期；历史实验以其 manifest/receipt 为准。
