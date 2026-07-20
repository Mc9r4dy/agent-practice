# Dev Container 根仓库 Git 集成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `F:\project_shuqi` 总仓库安全挂载到 Dev Container 的 `/workspace`，同时以 01 智能体子目录作为默认工作目录，使容器命令行和 VS Code SCM 都能识别同一个 Git 仓库，并保持 MySQL 教学数据卷与 Windows MySQL57 不变。

**Architecture:** Compose 负责把总仓库映射到 `/workspace` 并将 workspace 服务工作目录定位到 `/workspace/01_db-security-ops-teaching-agent`；Dockerfile 用系统级受保护 Git 配置只信任精确 `/workspace`；Dev Container 设置负责打开 01 子目录并自动发现父级仓库。实施采用契约测试 RED/GREEN、只重建 `shuqi-workspace`、自动运行验收和最终 VS Code GUI 人工验收四层闭环。

**Tech Stack:** Docker Desktop、Docker Compose v2、Dev Containers、VS Code、Git 2.39+、Python 3.13、pytest 9.1.1、PyYAML 6.0.3、PowerShell 7/Windows PowerShell。

## Global Constraints

- 总仓库固定为 `F:\project_shuqi`，01 智能体目录固定为 `F:\project_shuqi\01_db-security-ops-teaching-agent`。
- 容器总仓库路径固定为 `/workspace`，默认工作目录固定为 `/workspace/01_db-security-ops-teaching-agent`。
- Git system 配置与最终所有有效配置作用域只允许精确 `safe.directory=/workspace`；禁止 `*`、`/workspace/*` 和其他额外路径。
- 不自动修改宿主 Git 配置；若 Dev Containers 复制的容器全局配置引入冲突，只清理容器副本中的 `safe.directory` 键。
- MySQL 沙箱保持 `mysql:8.4`、`127.0.0.1:3307->3306`、数据卷 `shuqi-db-agent-mysql-data` 和现有初始化数据。
- Windows `MySQL57` 与 `E:\MySql` 不连接、不停止、不修改、不读写。
- 不挂载 Docker Socket，不增加 privileged、capability 或宿主控制权限。
- 本次实施和回滚禁止运行 `sandbox.ps1 -Action Rebuild`、`down --volumes`、全局 prune 和 volume prune。
- `.vscode/tasks.json` 的八个 `Sandbox: ...` 任务只在 Windows 主机运行；容器内只运行 Git、pytest 和应用开发命令。
- `.env`、实际密码、PAT、私钥和 credential helper 完整命令不得进入源文件、测试输出、开发日志或 Git 历史。
- 历史日志与旧实施计划中的原始状态保留；只新增当前状态说明，不伪造性改写历史证据。

## Planned File Map

| 文件 | 职责 | 变更方式 |
| --- | --- | --- |
| `tests/environment/test_compose_contract.py` | YAML/JSON/Dockerfile 结构契约 | 修改 |
| `tests/environment/test_repository_contract.py` | 当前文档与主机/容器边界契约 | 修改 |
| `infra/compose.yaml` | 根仓库挂载和默认工作目录 | 修改 |
| `.devcontainer/Dockerfile` | 精确 system `safe.directory` | 修改 |
| `.devcontainer/devcontainer.json` | 子目录 workspaceFolder 与父仓库发现 | 修改 |
| `05_开发环境与教学沙箱设计.md` | 当前架构与最终完成条件 | 修改 |
| `06_开发环境与教学沙箱实施计划.md` | 原计划之上的补充实施状态 | 修改 |
| `07_开发环境使用说明.md` | 最终操作、任务边界、Git 与回滚说明 | 修改 |
| `04_开发日志.md` | 每个 RED/GREEN、重建、故障和验收证据 | 修改 |

---

### Task 1: 用契约测试实现根仓库挂载、精确 Git 信任和父仓库发现

**Files:**
- Modify: `tests/environment/test_compose_contract.py`
- Modify: `infra/compose.yaml`
- Modify: `.devcontainer/Dockerfile`
- Modify: `.devcontainer/devcontainer.json`
- Modify: `04_开发日志.md`

**Interfaces:**
- Consumes: `ROOT = Path(__file__).resolve().parents[2]`，其中 `ROOT` 是 01 智能体目录，`ROOT.parent` 是总仓库。
- Produces: `/workspace` 根仓库挂载、`/workspace/01_db-security-ops-teaching-agent` 默认目录、精确 system `safe.directory`、VS Code 父仓库自动发现。

- [x] **Step 1: 记录未修改前基线**

在 01 智能体目录运行：

```powershell
docker exec -u vscode shuqi-workspace pytest -q
docker inspect shuqi-workspace --format '{{.Config.WorkingDir}} {{range .Mounts}}{{.Source}}=>{{.Destination}}{{end}}'
docker exec -u vscode shuqi-workspace sh -lc 'git rev-parse --show-toplevel'
```

Expected: `20 passed`；workdir 为 `/workspace`；挂载源为 01 子目录；Git 命令以“not a git repository”失败。把命令、退出码和输出摘要写入 `04_开发日志.md`，不得把失败写成通过。

- [x] **Step 2: 写入失败契约测试**

在 `tests/environment/test_compose_contract.py` 顶部增加：

```python
import json
import re
```

在常量区增加：

```python
DEVCONTAINER = ROOT / ".devcontainer" / "devcontainer.json"
DOCKERFILE = ROOT / ".devcontainer" / "Dockerfile"
AGENT_CONTAINER_PATH = "/workspace/01_db-security-ops-teaching-agent"


def load_devcontainer() -> dict:
    return json.loads(DEVCONTAINER.read_text(encoding="utf-8"))
```

把 `test_internal_network_and_devcontainer_target` 最后的原始字符串断言替换为结构断言：

```python
    devcontainer = load_devcontainer()
    assert devcontainer["service"] == "workspace"
```

在文件末尾增加：

```python
def test_workspace_mounts_repository_root_and_opens_agent_folder() -> None:
    workspace = load_compose()["services"]["workspace"]
    assert workspace["working_dir"] == AGENT_CONTAINER_PATH

    workspace_mounts = [
        item for item in workspace["volumes"] if ":/workspace:" in item
    ]
    assert len(workspace_mounts) == 1
    source, target, mode = workspace_mounts[0].rsplit(":", 2)
    assert target == "/workspace"
    assert mode == "cached"
    assert source == "../.."
    assert (COMPOSE.parent / source).resolve() == ROOT.parent.resolve()

    devcontainer = load_devcontainer()
    assert devcontainer["workspaceFolder"] == AGENT_CONTAINER_PATH


def test_devcontainer_limits_git_trust_and_discovers_parent_repo() -> None:
    devcontainer = load_devcontainer()
    vscode = devcontainer["customizations"]["vscode"]
    assert vscode["settings"]["git.openRepositoryInParentFolders"] == "always"

    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    safe_directory_targets = re.findall(
        r"git config --system --add safe\.directory\s+(\S+)",
        dockerfile,
    )
    assert safe_directory_targets == ["/workspace"]
    safe_directory_lines = [
        line for line in dockerfile.splitlines() if "safe.directory" in line
    ]
    assert all("*" not in line for line in safe_directory_lines)
```

- [x] **Step 3: 运行目标测试并确认 RED**

```powershell
docker exec -u vscode shuqi-workspace pytest -q `
  tests/environment/test_compose_contract.py::test_workspace_mounts_repository_root_and_opens_agent_folder `
  tests/environment/test_compose_contract.py::test_devcontainer_limits_git_trust_and_discovers_parent_repo
```

Expected: 2 failed。失败应分别指向旧 `working_dir/workspaceFolder/volume` 和缺失的 `settings/safe.directory`；如果因语法或路径错误失败，先修正测试再继续。

- [x] **Step 4: 最小修改 Compose**

把 `infra/compose.yaml` 的 workspace 片段改为：

```yaml
    working_dir: /workspace/01_db-security-ops-teaching-agent
    command: sleep infinity
```

并把 workspace volume 改为：

```yaml
    volumes:
      - ../..:/workspace:cached
```

MySQL service、端口、网络、env_file 与命名卷不得改动。

- [x] **Step 5: 最小修改 Dockerfile**

把 `.devcontainer/Dockerfile` 的 `RUN` 指令改为：

```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends default-mysql-client git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory /workspace \
    && useradd --create-home --shell /bin/bash vscode \
    && pip install --no-cache-dir pytest==9.1.1 PyYAML==6.0.3 PyMySQL==1.2.0
```

不得使用 `safe.directory '*'`、`safe.directory=*` 或 `/workspace/*`。

- [x] **Step 6: 最小修改 Dev Container**

把 `.devcontainer/devcontainer.json` 的 `workspaceFolder` 改为：

```json
"workspaceFolder": "/workspace/01_db-security-ops-teaching-agent"
```

把 `customizations.vscode` 改为以下结构，保留原扩展列表：

```json
"vscode": {
  "settings": {
    "git.openRepositoryInParentFolders": "always"
  },
  "extensions": [
    "ms-azuretools.vscode-docker",
    "ms-python.python",
    "ms-python.vscode-pylance",
    "Vue.volar"
  ]
}
```

- [x] **Step 7: 运行 GREEN 与回归测试**

```powershell
docker exec -u vscode shuqi-workspace pytest -q `
  tests/environment/test_compose_contract.py::test_workspace_mounts_repository_root_and_opens_agent_folder `
  tests/environment/test_compose_contract.py::test_devcontainer_limits_git_trust_and_discovers_parent_repo
docker exec -u vscode shuqi-workspace pytest -q
docker compose --project-name shuqi-db-agent --env-file .env -f infra/compose.yaml config --quiet
```

Expected: 目标测试 2 passed；全量测试 22 passed；Compose 命令退出码 0。

- [x] **Step 8: 记录日志并提交 Task 1**

向 `04_开发日志.md` 追加一条记录，至少包含基线、RED、三个配置文件的最小改动、GREEN、完整测试数、秘密检查、未重建容器、MySQL57 未触碰和回滚方式。

```powershell
git diff --check
git add -- tests/environment/test_compose_contract.py infra/compose.yaml .devcontainer/Dockerfile .devcontainer/devcontainer.json 04_开发日志.md
git diff --cached --check
git commit -m "Implement Dev Container root repository contract"
git push origin main
```

Expected: 普通 fast-forward push 成功；不得使用 force。

---

### Task 2: 用文档契约同步当前架构、主机任务和破坏性动作边界

**Files:**
- Modify: `tests/environment/test_repository_contract.py`
- Modify: `05_开发环境与教学沙箱设计.md`
- Modify: `06_开发环境与教学沙箱实施计划.md`
- Modify: `07_开发环境使用说明.md`
- Modify: `04_开发日志.md`

**Interfaces:**
- Consumes: Task 1 的容器路径、Git 信任和 VS Code 设置。
- Produces: 当前有效使用说明；原历史计划的补充状态；GUI 验收前仍未勾选的最终条件。

- [x] **Step 1: 写入失败文档契约测试**

在 `tests/environment/test_repository_contract.py` 末尾增加：

```python
def test_docs_describe_final_devcontainer_and_task_boundaries() -> None:
    usage = (ROOT / "07_开发环境使用说明.md").read_text(encoding="utf-8")
    for required in (
        r"F:\project_shuqi",
        "/workspace/01_db-security-ops-teaching-agent",
        "git config --show-origin --get-all safe.directory",
        "git.openRepositoryInParentFolders",
        "git ls-remote origin refs/heads/main",
        "凭据桥接",
        "四个智能体",
        "Preflight/Start/Status/Logs/Test/QuickReset/Rebuild/Stop",
        "QuickReset",
        "九张教学表",
        "down --volumes",
        "Windows 主机任务",
        "Linux Dev Container",
    ):
        assert required in usage

    environment_design = (ROOT / "05_开发环境与教学沙箱设计.md").read_text(
        encoding="utf-8"
    )
    assert "挂载总仓库" in environment_design
    assert "/workspace/01_db-security-ops-teaching-agent" in environment_design

    old_plan = (ROOT / "06_开发环境与教学沙箱实施计划.md").read_text(
        encoding="utf-8"
    )
    assert "根仓库集成补充实施状态" in old_plan
    assert "2026-07-20-devcontainer-root-git-integration-implementation.md" in old_plan
```

- [x] **Step 2: 运行目标测试并确认 RED**

```powershell
docker exec -u vscode shuqi-workspace pytest -q `
  tests/environment/test_repository_contract.py::test_docs_describe_final_devcontainer_and_task_boundaries
```

Expected: 1 failed，至少缺少新容器路径、全作用域 Git 命令和补充实施状态。

- [x] **Step 3: 更新环境设计当前架构**

在 `05_开发环境与教学沙箱设计.md` 的 workspace 组件说明中写入以下当前条款：

```markdown
- 挂载总仓库 `F:\project_shuqi` 到 `/workspace`；
- VS Code 与容器进程默认进入 `/workspace/01_db-security-ops-teaching-agent`；
- Git system 配置只信任精确 `/workspace`，并在 Dev Container 连接后检查所有有效配置作用域；
- VS Code 通过 `git.openRepositoryInParentFolders=always` 自动发现父级总仓库。
```

在 VS Code Tasks 段落增加：

```markdown
八个 `Sandbox: Preflight/Start/Status/Logs/Test/QuickReset/Rebuild/Stop` 均为 Windows 主机任务。`QuickReset` 会删除九张教学表的当前场景数据并重放合成种子；`Rebuild` 会执行 `down --volumes` 删除教学卷，本次根仓库集成实施和回滚禁止运行。
```

保持“VS Code 可以连接开发容器”复选框为 `[ ]`，直到 Task 4 GUI 验收通过。

- [x] **Step 4: 给旧实施计划增加补充状态，不改写历史**

在 `06_开发环境与教学沙箱实施计划.md` 的 Implementation Status 后增加：

```markdown
### 根仓库集成补充实施状态（2026-07-20）

- 本文 Task 1—8 保留首次环境建设的历史计划与证据，不批量改写当时的路径和 Git 状态；
- 当前总仓库已建立并连接 `https://github.com/Mc9r4dy/agent-practice.git`；
- Dev Container 根仓库集成由 `docs/superpowers/plans/2026-07-20-devcontainer-root-git-integration-implementation.md` 接续实施；
- 原 Task 8 Step 6 只有在新计划的容器自动验收与 VS Code GUI 验收均通过后才能完成。
```

- [x] **Step 5: 更新使用说明的当前路径、Git 和任务边界**

在 `07_开发环境使用说明.md` 中写明：

```markdown
总仓库：`F:\project_shuqi` → `/workspace`

当前智能体：`F:\project_shuqi\01_db-security-ops-teaching-agent` → `/workspace/01_db-security-ops-teaching-agent`
```

把“进入 Dev Container”步骤改为先在本地打开 01 子目录，再 Reopen；容器终端验收命令使用：

```bash
pwd
git rev-parse --show-toplevel
git status -sb
git config --show-origin --get-all safe.directory
pytest -q
```

Expected: `pwd` 为 01 容器路径；Git 根为 `/workspace`；有效 `safe.directory` 只包含精确 `/workspace`。

增加以下任务边界文字：

```markdown
`Sandbox: Preflight/Start/Status/Logs/Test/QuickReset/Rebuild/Stop` 全部是 Windows 主机任务，不在 Linux Dev Container 内运行。`QuickReset` 会删除九张教学表的现有教学场景数据后重放合成种子；`Rebuild` 会执行 `down --volumes` 删除教学数据卷，本次根仓库集成实施和回滚禁止使用。
```

增加 Git 冲突处理：

```markdown
若 `git config --show-origin --get-all safe.directory` 出现 `*`、`/workspace/*` 或额外路径，停止验收。不要自动修改宿主 Git 配置；只清理容器内复制的全局 `safe.directory` 冲突键，然后重新检查。
```

增加凭据桥接与跨智能体信任边界：

```markdown
Dev Containers 可能复制宿主 `.gitconfig`，并通过会话级 credential helper 或 SSH agent 提供凭据桥接；这不等于把令牌写入镜像。不得在镜像、项目文件或日志中记录 PAT、私钥、密码或 credential helper 的完整值。只读远端可用 `git ls-remote origin refs/heads/main` 验证；若用户不授权凭据使用，记录为“未启用”，不误判为本地仓库识别失败。

当前 `/workspace` 挂载整个总仓库，因此 01 容器可以读写四个智能体的文件，四个智能体按同一开发信任域管理。真实生产凭据不得放入仓库目录；未来运行不可信代码或多人隔离开发时必须重新评审独立仓库、worktree 或外部秘密挂载。
```

- [x] **Step 6: 运行文档 GREEN 与全部测试**

```powershell
docker exec -u vscode shuqi-workspace pytest -q `
  tests/environment/test_repository_contract.py::test_docs_describe_final_devcontainer_and_task_boundaries
docker exec -u vscode shuqi-workspace pytest -q
```

Expected: 目标测试 1 passed；全量测试 23 passed。

- [x] **Step 7: 记录日志并提交 Task 2**

日志必须记录 RED/GREEN、三份文档的当前/历史边界、QuickReset/Rebuild 影响、未勾选 GUI 条件和回滚方式。

```powershell
git diff --check
git add -- tests/environment/test_repository_contract.py 05_开发环境与教学沙箱设计.md 06_开发环境与教学沙箱实施计划.md 07_开发环境使用说明.md 04_开发日志.md
git commit -m "Document Dev Container host and container boundaries"
git push origin main
```

---

### Task 3: 只重建 workspace 并完成自动化运行验收

**Files:**
- Modify: `04_开发日志.md`

**Interfaces:**
- Consumes: Task 1 配置和 Task 2 使用说明。
- Produces: 不删除 MySQL 卷的运行证据、容器内 Git 与 23 项测试通过证据。

- [x] **Step 1: 捕获不可变基线**

在 01 智能体目录的 Windows PowerShell 运行：

```powershell
$mysqlBefore = docker inspect shuqi-mysql-sandbox | ConvertFrom-Json
$mysqlIdBefore = $mysqlBefore.Id
$mysqlHealthBefore = $mysqlBefore.State.Health.Status
$volumeBefore = docker volume inspect shuqi-db-agent-mysql-data | ConvertFrom-Json
$mysql57Before = Get-Service MySQL57

if ($mysqlHealthBefore -ne 'healthy') { throw 'MySQL sandbox must be healthy before workspace-only recreation' }
if (-not $volumeBefore) { throw 'Teaching volume is missing' }
if ($mysql57Before.Status -ne 'Running') { throw 'MySQL57 baseline changed' }
```

Expected: 三个条件全部通过。失败时停止，不运行 Rebuild。

- [x] **Step 2: 预检 Compose 与定向重建计划**

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\scripts\sandbox.ps1 -Action Preflight
docker compose --project-name shuqi-db-agent --env-file .env -f infra/compose.yaml config --quiet
docker compose --dry-run --project-name shuqi-db-agent --env-file .env -f infra/compose.yaml up -d --build --no-deps --force-recreate workspace
```

Expected: Preflight/config 通过；dry-run 只出现 `shuqi-workspace` Recreate，不出现 MySQL Recreate、volume remove 或 `down --volumes`。

- [x] **Step 3: 定向重建 workspace**

```powershell
docker compose --project-name shuqi-db-agent --env-file .env -f infra/compose.yaml up -d --build --no-deps --force-recreate workspace
```

Expected: 只构建并重建 `shuqi-workspace`。禁止改用 `sandbox.ps1 -Action Rebuild`。

- [x] **Step 4: 验证挂载、工作目录与 Git**

```powershell
$inspect = docker inspect shuqi-workspace | ConvertFrom-Json
$workspaceMount = $inspect.Mounts | Where-Object Destination -eq '/workspace'
$actualSource = [IO.Path]::GetFullPath($workspaceMount.Source).TrimEnd('\')
$expectedSource = [IO.Path]::GetFullPath('F:\project_shuqi').TrimEnd('\')
if ($actualSource -ne $expectedSource) { throw "Unexpected mount: $actualSource" }
if ($inspect.Config.WorkingDir -ne '/workspace/01_db-security-ops-teaching-agent') { throw 'Unexpected workdir' }

docker exec -u vscode shuqi-workspace pwd
docker exec -u vscode shuqi-workspace git rev-parse --show-toplevel
docker exec -u vscode shuqi-workspace git status -sb
$safeDirectoryOutput = @(docker exec -u vscode shuqi-workspace git config --show-origin --get-all safe.directory)
if ($LASTEXITCODE -ne 0) { throw 'No effective safe.directory entry' }
if ($safeDirectoryOutput.Count -ne 1) { throw 'Unexpected safe.directory count' }
if ($safeDirectoryOutput[0] -notmatch '^file:/etc/gitconfig\s+/workspace$') {
  throw "Unexpected safe.directory source or value: $($safeDirectoryOutput[0])"
}
```

Expected: mount 源为总仓库；pwd 为 01 容器路径；Git 根为 `/workspace`；分支显示 `main...origin/main`；safe.directory 只有 `file:/etc/gitconfig` 提供的精确 `/workspace`。

若全作用域出现额外值，停止验收；只在容器副本中执行以下精确清理后复验：

```bash
git config --global --unset-all safe.directory
git config --show-origin --get-all safe.directory
```

不得对宿主执行该清理命令。清理后必须重新运行上面的 `$safeDirectoryOutput` 精确断言，不能只目视输出。

- [x] **Step 5: 验证测试、MySQL 卷、服务与端口**

```powershell
docker exec -u vscode shuqi-workspace pytest -q

$mysqlAfter = docker inspect shuqi-mysql-sandbox | ConvertFrom-Json
$volumeAfter = docker volume inspect shuqi-db-agent-mysql-data | ConvertFrom-Json
if ($mysqlAfter.Id -ne $mysqlIdBefore) { throw 'MySQL container was recreated' }
if ($mysqlAfter.State.Health.Status -ne 'healthy') { throw 'MySQL sandbox is not healthy' }
if (-not $volumeAfter) { throw 'Teaching volume was deleted' }
if ((Get-Service MySQL57).Status -ne 'Running') { throw 'MySQL57 changed' }

Get-NetTCPConnection -State Listen -LocalPort 3306,3307 |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

Expected: 23 passed；MySQL container ID 与之前相同；卷存在；MySQL healthy；MySQL57 Running；3307 只监听 loopback，3306 保持原服务。

- [x] **Step 6: 秘密、Git 与回滚验收**

```powershell
git status --short
git check-ignore -v 01_db-security-ops-teaching-agent/.env
git diff --check

$passwordValues = @(
  Get-Content -LiteralPath .\01_db-security-ops-teaching-agent\.env -Encoding UTF8 |
    Where-Object { $_ -match '^[^#=]*PASSWORD=' } |
    ForEach-Object { ($_ -split '=', 2)[1] } |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
)
$exactSecretHits = 0
foreach ($secret in $passwordValues) {
  $null = git grep --quiet -F -e $secret --
  if ($LASTEXITCODE -eq 0) { $exactSecretHits++ }
  elseif ($LASTEXITCODE -ne 1) { throw 'Exact secret scan failed' }
}

$genericPattern = 'gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----'
$null = git grep --quiet -I -E -e $genericPattern --
if ($LASTEXITCODE -eq 0) { $genericSecretHits = 1 }
elseif ($LASTEXITCODE -eq 1) { $genericSecretHits = 0 }
else { throw 'Generic secret scan failed' }

"Exact secret value hits: $exactSecretHits"
"Generic secret pattern hits: $genericSecretHits"
if ($exactSecretHits -ne 0 -or $genericSecretHits -ne 0) {
  throw 'Tracked secret-like content detected'
}
```

从 `.env` 仅读取密码值进行内存精确扫描，`git grep` 仅扫描被跟踪内容；日志只记录两个命中数，不输出值或匹配行。通用 GitHub/OpenAI/AWS/私钥模式命中必须为 0。

若运行验收失败且用户决定回滚，先创建反向提交恢复 Task 2 和 Task 1（按提交信息定位，不使用 reset）：

```powershell
$task2 = git log -1 --format=%H --grep='^Document Dev Container host and container boundaries$'
$task1 = git log -1 --format=%H --grep='^Implement Dev Container root repository contract$'
if (-not $task1 -or -not $task2) { throw 'Rollback commit not found' }
git revert --no-edit $task2
git revert --no-edit $task1
docker compose --project-name shuqi-db-agent --env-file .env -f infra/compose.yaml up -d --build --no-deps --force-recreate workspace
docker inspect shuqi-mysql-sandbox --format '{{.Id}} {{.State.Health.Status}}'
docker volume inspect shuqi-db-agent-mysql-data
```

回滚后运行完整 pytest、MySQL ID/健康/卷检查并普通 push；禁止 `reset --hard`、force push、Rebuild、全局 prune 或 volume prune。

- [x] **Step 7: 记录运行证据并提交 Task 3**

日志必须记录 MySQL 前后 ID、卷存在性、dry-run、构建结果、挂载规范化路径、有效 Git 配置来源、pytest 数量、端口、秘密扫描和回滚命令。

```powershell
git add -- 04_开发日志.md
git commit -m "Verify workspace-only Dev Container recreation"
git push origin main
git ls-remote origin refs/heads/main
```

---

### Task 4: 完成 VS Code GUI 人工验收并关闭环境阶段

**Files:**
- Modify: `05_开发环境与教学沙箱设计.md`
- Modify: `06_开发环境与教学沙箱实施计划.md`
- Modify: `04_开发日志.md`

**Interfaces:**
- Consumes: Task 3 已运行的新 workspace。
- Produces: 用户确认的 Dev Containers GUI 证据与开发环境阶段最终关闭状态。

- [ ] **Step 1: 用户从正确的本地目录 Reopen**

在本地 Windows VS Code 选择 `File > Open Folder...`，打开：

```text
F:\project_shuqi\01_db-security-ops-teaching-agent
```

然后执行 `Dev Containers: Reopen in Container`。不要从 `F:\project_shuqi` 根窗口直接 Reopen。

- [ ] **Step 2: 用户确认 GUI 与终端证据**

在 Dev Container 终端运行：

```bash
pwd
git rev-parse --show-toplevel
git status -sb
git config --show-origin --get-all safe.directory
git config --show-origin --get-regexp '^credential(\..*)?\.helper$' |
  awk '{ print $1, $2, "<redacted>" }'
git ls-remote origin refs/heads/main
pytest -q
```

Expected:

- VS Code 左下角显示 Dev Container；
- pwd 为 `/workspace/01_db-security-ops-teaching-agent`；
- Git 根为 `/workspace`；
- SCM 无需接受父仓库提示即可显示 `main`；
- safe.directory 最终有效值只有精确 `/workspace`；
- credential helper 只记录来源与键名，值保持 `<redacted>`，没有令牌写入镜像或项目文件；
- `git ls-remote` 返回 `refs/heads/main`，或在用户不授权远端凭据时明确记录“未启用”；
- pytest 为 23 passed；
- Windows-only `Sandbox: ...` Tasks 不在容器内运行。

`git.openRepositoryInParentFolders` 应通过 VS Code 远端设置界面确认值为 `always`；Git CLI 不暴露 VS Code 设置，因此必须以远端设置界面和 SCM 实际行为为证据。credential helper 命令只输出脱敏后的来源与键名，不得把完整值复制到日志。

- [ ] **Step 3: 勾选最终环境完成条件**

只有用户确认 Step 2 后：

- 把 `05_开发环境与教学沙箱设计.md` 中“VS Code 可以连接开发容器”改为 `[x]`；
- 把 `06_开发环境与教学沙箱实施计划.md` 的原 Task 8 Step 6 改为 `[x]`；
- 在 Implementation Status 写明环境阶段已关闭、下一阶段进入智能体 MVP。

- [ ] **Step 4: 追加最终日志并执行全量验证**

日志记录用户确认时间、GUI 状态、容器路径、SCM、safe.directory、测试数、MySQL/端口未变和下一阶段。

```powershell
docker exec -u vscode shuqi-workspace pytest -q
docker ps --filter 'name=shuqi-' --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
Get-Service MySQL57 | Select-Object Name,Status
git diff --check
```

Expected: 23 passed；MySQL healthy；3307 loopback；MySQL57 Running；diff check 通过。

- [ ] **Step 5: 最终提交、推送与 SHA 核对**

```powershell
git add -- 05_开发环境与教学沙箱设计.md 06_开发环境与教学沙箱实施计划.md 04_开发日志.md
git commit -m "Complete Dev Container environment acceptance"
git push origin main
$local = git rev-parse HEAD
$remote = ((git ls-remote origin refs/heads/main) -split "`t")[0]
if ($local -ne $remote) { throw 'Remote SHA mismatch' }
git status -sb
```

Expected: 本地与远端 SHA 一致；工作树干净；开发环境阶段正式完成。

## Plan Self-Review Checklist

- [x] 最终设计 12 个章节的每项要求都映射到 Task 1—4。
- [x] Compose、Dev Container 和 Dockerfile 行为都有先行 RED 测试。
- [x] 文档当前状态有先行 RED 测试，历史证据不被批量改写。
- [x] 所有运行变更只重建 workspace，不删除或重建 MySQL 容器与数据卷。
- [x] system 和最终有效 Git 配置都拒绝通配 safe.directory。
- [x] 八个 Windows Tasks 与 Linux 容器边界完整，QuickReset/Rebuild 数据影响明确。
- [x] 自动验收与 GUI 人工验收严格分开。
- [x] 每个任务都有日志、回滚、提交、普通 push 和明确预期结果。
- [x] 没有临时空白项、延期描述或未定义命令。
