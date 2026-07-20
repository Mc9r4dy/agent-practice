# Dev Container 根仓库 Git 集成设计

## 1. 背景与问题

`F:\project_shuqi` 是 `agent-practice` 总仓库，计划容纳指导手册与四个教学智能体。当前第一个智能体位于 `F:\project_shuqi\01_db-security-ops-teaching-agent`，其 Dev Container 配置由该子目录维护。

当前 Compose 将 `01_db-security-ops-teaching-agent` 挂载为容器内的 `/workspace`。Git 元数据却位于父目录 `F:\project_shuqi\.git`，因此本地 VS Code 可以识别总仓库，Dev Container 内无法访问 `.git`。直接把总仓库挂载到 `/workspace` 后，还会遇到两个已验证问题：Docker Desktop 的 Windows bind mount 在 Linux 容器内显示为 `root:root`，会触发 Git dubious ownership；VS Code 默认不会自动打开工作区父目录中的 Git 仓库。

## 2. 已确认目标

1. 保持 `F:\project_shuqi` 为四个智能体共用的唯一 Git 仓库；
2. Dev Container 内能够识别与主机相同的根仓库和 `main` 分支；
3. 打开第一个智能体的 Dev Container 后，默认进入该智能体目录；
4. VS Code 源代码管理面板自动识别父级总仓库，不依赖首次人工接受提示；
5. Git 只信任精确的 `/workspace` 仓库路径，不使用 `safe.directory=*`；
6. 不改变 MySQL 沙箱的端口、账号、网络隔离、初始化数据和持久化数据卷；
7. 不挂载 Docker Socket，不增加容器权限；
8. 明确区分 Windows 主机任务与 Linux 容器任务；
9. 明确 Dev Containers 的 Git 配置和凭据桥接边界；
10. 修改必须有自动化契约测试、运行验证、详细开发日志和明确回滚方式。

## 3. 方案比较

### 方案 A：挂载总仓库，默认进入 01 子目录（采用）

- 将主机 `F:\project_shuqi` 挂载到容器 `/workspace`；
- 将 Compose `working_dir` 与 Dev Container `workspaceFolder` 设为 `/workspace/01_db-security-ops-teaching-agent`；
- 容器内 `/workspace/.git` 对应主机总仓库的 `.git`；
- 在镜像的 Git 系统级配置中仅将 `/workspace` 加入 `safe.directory`；
- 在 Dev Container 的 VS Code 设置中将 `git.openRepositoryInParentFolders` 设为 `always`。

优点是主机和容器使用同一个 Git 工作树，后续四个智能体共享历史和根级忽略规则；配置直接符合当前总仓库决策。代价是 01 容器能够读写总仓库内其他智能体文件，因此四个智能体必须被视为同一开发信任边界。

### 方案 B：仅挂载 01 子目录并额外挂载 `.git`（不采用）

该方案需要同时处理 Git 工作树、`core.worktree`、相对路径和容器/主机路径差异，容易造成 Git 将文件判断为删除或工作树错位，也不利于后续四个智能体扩展。

### 方案 C：每个智能体拆分为独立仓库（不采用）

隔离最强，但与用户已经确认的 `agent-practice` 总仓库结构冲突，会增加四套远端、版本和公共材料同步成本。

## 4. 目标架构与配置职责

主机与容器目录映射如下：

| 主机路径 | 容器路径 | 用途 |
| --- | --- | --- |
| `F:\project_shuqi` | `/workspace` | 总仓库与 `.git` |
| `F:\project_shuqi\01_db-security-ops-teaching-agent` | `/workspace/01_db-security-ops-teaching-agent` | 当前智能体默认开发目录 |

配置职责如下：

- `infra/compose.yaml`：总仓库 bind mount 和容器进程默认工作目录；
- `.devcontainer/Dockerfile`：安装 Git，并通过受保护的系统级配置精确声明 `safe.directory=/workspace`；
- `.devcontainer/devcontainer.json`：VS Code 打开的 01 智能体目录，以及父仓库自动发现设置；
- `.vscode/tasks.json`：保留 Windows 主机沙箱管理任务，不承诺在 Linux 容器内运行；
- `tests/environment/test_compose_contract.py`：解析 YAML 后验证挂载源、挂载目标和默认工作目录；
- 新增或扩展 Dev Container 契约测试：解析 JSON 与 Dockerfile，验证 `workspaceFolder`、父仓库发现设置和精确 `safe.directory`；
- 当前设计、实施计划与使用说明：同步更新容器路径、任务边界和人工验收命令；
- `04_开发日志.md`：记录 RED/GREEN 测试、workspace 定向重建、Git 验证、安全影响和回滚证据。

## 5. 运行流程与任务边界

1. 用户先在本地 VS Code 使用“打开文件夹”打开 `F:\project_shuqi\01_db-security-ops-teaching-agent`，而不是直接从根目录执行 Reopen；
2. Dev Containers 读取该目录下的 `.devcontainer/devcontainer.json`；
3. Docker Compose 创建或更新 `shuqi-workspace`，复用已运行的 `shuqi-mysql-sandbox`；
4. `/workspace` 映射到总仓库，VS Code 打开 `/workspace/01_db-security-ops-teaching-agent`；
5. 镜像系统级 Git 配置使 `/workspace` 成为唯一额外信任仓库，避免 Windows bind mount 的所有权误判；
6. 容器专用 VS Code 设置允许源代码管理面板自动发现父目录 `/workspace` 的仓库；
7. 容器内 `git rev-parse --show-toplevel` 返回 `/workspace`，`git status -sb` 显示 `main` 与 `origin/main`；
8. 容器默认目录保持为 01 智能体目录，`pytest -q` 只运行该项目测试；
9. MySQL 沙箱继续通过 `127.0.0.1:3307` 暴露给主机，Windows `MySQL57` 的 3306 端口不变。

任务执行边界如下：

| 运行位置 | 允许和推荐的任务 | 不应执行的任务 |
| --- | --- | --- |
| Windows 主机 VS Code/PowerShell | `Sandbox: Preflight/Start/Status/Logs/Test/QuickReset/Rebuild/Stop`，Docker 与 MySQL57 宿主检查 | 不直接修改教学数据卷内部文件；本次实施和回滚禁止运行 `Rebuild` |
| Linux Dev Container | Python/Node 开发、`pytest`、Git status/diff/branch、经用户操作的 Git 远端命令 | 不运行依赖 `powershell.exe` 的宿主 Tasks，不管理 Docker Desktop，不连接 Windows MySQL57 |

`.vscode/tasks.json` 中八个现有沙箱任务全部是 Windows 主机任务，其数据影响分级如下：

- `Preflight`、`Status`、`Logs` 和 `Test`：诊断或测试任务，不重置教学数据；
- `Start` 和 `Stop`：项目生命周期任务；`Stop` 保留教学数据卷；
- `QuickReset`：破坏性教学状态重置，会执行 `002_seed.sql`，先删除九张教学表中的现有场景数据，再写回标准合成数据；只能在明确需要重置教学场景时由用户主动运行；
- `Rebuild`：完全重建任务，会执行 `down --volumes` 并删除教学 MySQL 数据卷；本次 Dev Container 实施和回滚明确禁止使用。

使用说明必须明确：进入容器后通过终端运行 `pytest` 和 Git 命令，不从容器运行上述 Tasks。本次不挂载 Docker Socket，也不为容器安装宿主控制能力。

## 6. Git 所有权、凭据与跨智能体安全边界

### Git 所有权

- Docker Desktop bind mount 在本机验证为 `root:root`，容器开发用户为 `vscode`；
- `.devcontainer/Dockerfile` 使用系统级受保护配置加入精确路径 `/workspace`；
- 禁止使用 `safe.directory=*`，也不信任 `/workspace/*` 或其他任意仓库；
- Dev Containers 复制的宿主 `.gitconfig` 可能在全局作用域重新引入宽泛 `safe.directory`，因此只检查系统级配置不足以证明最终信任边界；
- 契约测试约束项目提供的系统级配置，运行和人工验收使用 `git config --show-origin --get-all safe.directory` 检查所有有效受保护配置来源；
- 最终有效条目只允许精确的 `/workspace`；出现 `*`、`/workspace/*`、其他路径或无法识别的来源时均视为失败；
- 若宿主配置副本引入冲突，默认采用 fail-closed：停止验收，不自动修改宿主 Git 配置；只允许删除容器内复制的全局 `safe.directory` 冲突键，保留用户身份、credential helper 等其他 Git 配置，再重新执行全作用域检查；
- 契约测试和运行测试都必须验证精确路径，缺失或放宽均视为失败。

### Git 配置与凭据

- Dev Containers 可能在启动时复制宿主 `.gitconfig`，并通过会话级 credential helper 或 SSH agent 转发帮助容器访问远端；
- 这种行为不等于把令牌或私钥写入镜像，但意味着容器内 Git 进程可能在用户会话期间请求宿主凭据；
- 禁止把 PAT、密码、私钥或凭据帮助程序生成的秘密写入 Dockerfile、Compose、`.env`、项目文档和日志；
- 本阶段验收容器内仓库识别、只读远端访问和凭据帮助程序来源，不自动执行 commit、push、凭据登录或权限变更；
- `git ls-remote origin refs/heads/main` 可作为只读远端验证；日志只记录成功/失败和 SHA 比较结果，不记录 credential helper 完整命令行或秘密；
- 后续由用户在 VS Code 中主动执行同步或推送，属于显式用户操作。

### 跨智能体信任边界

- 总仓库读写挂载意味着 01 容器可访问未来 02—04 智能体文件；
- 四个智能体按同一开发者、同一课程项目、同一信任域管理；
- 未来智能体不得把真实生产凭据放在仓库目录，`.env` 只允许本地测试秘密并必须被根级忽略；
- 若未来需要运行不可信代码或把智能体分配给不同人员，应重新评审并改用独立仓库、独立 worktree 或外部秘密挂载，不能沿用本信任假设。

## 7. 错误处理与数据保护

- Compose 解析失败：停止重建，保留现有容器和数据卷，先修复配置；
- workspace 重建失败：不执行全局 prune，不删除 MySQL 数据卷，可恢复旧配置后定向重建 workspace；
- 容器内 Git 根目录不是 `/workspace` 或出现 dubious ownership：视为验收失败；
- Git 全作用域有效 `safe.directory` 出现通配符、额外路径或来源不明条目：停止验收，只处理容器内复制配置，不自动修改宿主配置；
- VS Code SCM 未自动识别父仓库：检查容器设置是否生效，不用人工提示掩盖配置缺失；
- 自动化测试失败：保留 RED/GREEN 输出并停止提交运行配置；
- MySQL 健康检查失败：只排查本项目 `shuqi-*` 资源，不连接、停止或修改 Windows `MySQL57`，不读写 `E:\MySql`；
- `.env` 继续由根级和项目级 `.gitignore` 排除，测试和日志不得输出实际密码；
- 不使用 `docker system prune`、`volume prune`、强制推送或历史重写；
- 本次实施与回滚均禁止调用 `sandbox.ps1 -Action Rebuild`，因为现行 Rebuild 会执行 `down --volumes`。

## 8. 测试与验收设计

### 阶段 A：提交前契约测试

先新增会失败的测试，要求：

1. 使用 YAML 解析 Compose，验证 workspace volume 源文本为 `../..`、目标为 `/workspace`，并根据 Compose 文件目录解析后等于总仓库根目录；
2. Compose `working_dir` 为 `/workspace/01_db-security-ops-teaching-agent`；
3. 使用 JSON 解析 `devcontainer.json`，验证 `workspaceFolder` 为同一路径；
4. 验证 `customizations.vscode.settings.git.openRepositoryInParentFolders` 为 `always`；
5. 验证 Dockerfile 只添加精确的 `safe.directory /workspace`，并拒绝 `*`；
6. 既有 MySQL 端口、网络、权限和数据卷契约保持通过。

确认测试因旧配置而失败后，再做最小配置修改并运行目标测试和全部测试。原始字符串匹配只能用于 Dockerfile 命令约束，JSON/YAML 配置必须按结构解析。

### 阶段 B：配置解析与定向重建

1. 执行 Compose `config --quiet`；
2. 在 01 智能体主机目录执行：

   ```powershell
   docker compose --project-name shuqi-db-agent --env-file .env -f infra/compose.yaml up -d --build --no-deps --force-recreate workspace
   ```

3. 不执行 `down --volumes`，不调用 `sandbox.ps1 -Action Rebuild`；
4. 定向重建前后记录 `shuqi-db-agent-mysql-data` 的存在性与 MySQL 容器 ID/健康状态，确认教学数据卷没有删除；
5. `docker inspect shuqi-workspace` 的源路径使用规范化比较，兼容 Windows 反斜杠和 Docker 输出形式，不做脆弱的显示字符串等值判断。

### 阶段 C：容器运行验收

- workspace 的 bind mount 规范化后等于 `F:\project_shuqi -> /workspace`；
- 容器默认目录为 `/workspace/01_db-security-ops-teaching-agent`；
- 以 `vscode` 用户运行 Git，不附加临时 `-c safe.directory=...`，`git rev-parse --show-toplevel` 返回 `/workspace`；
- `git status -sb` 显示 `main` 与 `origin/main`，不出现 dubious ownership；
- `git config --system --get-all safe.directory` 只包含目标精确路径，不包含 `*`；
- `git config --show-origin --get-all safe.directory` 检查所有有效作用域，最终条目只允许精确 `/workspace`，不存在 `*`、`/workspace/*`、其他路径或来源不明条目；
- 全量 pytest 通过；
- `shuqi-mysql-sandbox` 仍为 healthy，教学数据卷仍存在；
- 教学端口仍为 `127.0.0.1:3307->3306`；
- Windows `MySQL57` 仍为 Running，3306 不被项目容器占用。

### 阶段 D：Dev Container 连接后人工验收

用户从 01 智能体目录执行 `Dev Containers: Reopen in Container`，确认：

1. VS Code 左下角显示容器连接状态；
2. 终端默认目录为 `/workspace/01_db-security-ops-teaching-agent`；
3. 源代码管理面板无需接受父仓库提示即可识别 `/workspace`；
4. `git.openRepositoryInParentFolders` 的远端设置为 `always`；
5. `git config --show-origin --get-all safe.directory` 的有效结果仅为精确 `/workspace`；若宿主副本带入冲突项，按本设计在容器副本内处理并复验；
6. Git 配置/凭据桥接来源符合本设计，不存在写入镜像或项目文件的令牌；
7. 容器内只读 `git ls-remote` 可用；若用户不授权远端凭据使用，则记录该项未启用，不把它误判为仓库识别失败；
8. 八个 Windows-only 沙箱 Tasks 均不在容器内执行，且用户知晓 `QuickReset` 与 `Rebuild` 的数据影响。

自动化检查不冒充 GUI 人工步骤。只有实际 Reopen 后才能确认 Dev Containers 自身的设置和凭据桥接行为。

### 阶段 E：提交与远端验收

1. 提交前检查暂存清单不含 `.env`、缓存和实际秘密；
2. 实施提交完成后运行最终测试；
3. 追加最终开发日志并形成收尾提交；
4. 从主机执行普通 push，不使用 force；
5. 最终比较本地 `HEAD` 与远端 `refs/heads/main`；
6. 只有最后一个日志提交也已推送后，才要求工作树干净和本地/远端 SHA 一致。

## 9. 文档更新范围

更新描述当前有效架构的文档：

- `05_开发环境与教学沙箱设计.md`；
- `06_开发环境与教学沙箱实施计划.md`；
- `07_开发环境使用说明.md`；
- `04_开发日志.md`。

使用说明必须增加“本地主机任务/容器任务”矩阵、定向重建命令、父仓库 SCM 验证、Git 所有权说明和凭据桥接说明。历史日志中的旧路径、旧挂载状态和旧测试结果是当时证据，保持原文，不做伪造式批量替换。

## 10. 回滚设计

如果新挂载影响 Dev Container 使用，先通过新增反向提交恢复：

- Compose workspace 挂载为 `..:/workspace:cached`；
- Compose `working_dir` 为 `/workspace`；
- Dev Container `workspaceFolder` 为 `/workspace`；
- 移除本次新增的父仓库自动发现设置；
- 移除 Dockerfile 中精确的 `/workspace` safe.directory 配置。

随后在 01 智能体主机目录执行：

```powershell
docker compose --project-name shuqi-db-agent --env-file .env -f infra/compose.yaml up -d --build --no-deps --force-recreate workspace
```

回滚只重建 `shuqi-workspace`，不停止或重建 MySQL 服务，不删除 `shuqi-db-agent-mysql-data`。禁止使用 `sandbox.ps1 -Action Rebuild`、`reset --hard`、force push、全局 prune 或 volume prune。

## 11. 非目标

- 本次不开始智能体业务功能实现；
- 不新增第二至第四智能体目录；
- 不更换数据库版本或增加攻击工具；
- 不把宿主令牌、密码或私钥写入镜像和项目文件；
- 不自动执行 commit、push、凭据登录或 GitHub 权限变更；
- 不把 Windows 沙箱管理能力迁入 Linux 容器；
- 不改变 GitHub 仓库可见性、分支保护或协作权限。

## 12. 完成定义

只有以下条件同时满足，才能把开发环境阶段标记为完成：

1. YAML/JSON/Dockerfile 契约测试和全量 pytest 通过；
2. workspace 定向重建成功，MySQL 容器与数据卷未被删除；
3. `vscode` 用户无需临时参数即可使用 `/workspace` Git 仓库，所有有效 Git 配置作用域中的 `safe.directory` 仅允许精确 `/workspace`；
4. VS Code SCM 自动识别父仓库；
5. Git 凭据桥接边界已经人工确认并记录；
6. 八个 Windows 主机任务与 Linux 容器任务边界、`QuickReset`/`Rebuild` 数据影响写入使用说明；
7. MySQL57、3306/3307 端口隔离和沙箱健康状态通过；
8. 开发日志完整，最终本地与远端 SHA 一致，工作树干净；
9. 用户完成 VS Code GUI 连接确认。

完成上述环境闭环后，项目才进入智能体业务实现阶段。
