# Dev Container 根仓库 Git 集成设计

## 1. 背景与问题

`F:\project_shuqi` 是 `agent-practice` 总仓库，计划容纳指导手册与四个教学智能体。当前第一个智能体位于 `F:\project_shuqi\01_db-security-ops-teaching-agent`，其 Dev Container 配置由该子目录维护。

当前 Compose 将 `01_db-security-ops-teaching-agent` 挂载为容器内的 `/workspace`。Git 元数据却位于父目录 `F:\project_shuqi\.git`，因此本地 VS Code 可以识别总仓库，Dev Container 内却无法访问 `.git`。这会导致容器内的 VS Code 源代码管理、`git status`、分支信息及提交操作失效。

## 2. 已确认目标

1. 保持 `F:\project_shuqi` 为四个智能体共用的唯一 Git 仓库；
2. Dev Container 内能够识别与主机相同的根仓库和 `main` 分支；
3. 打开第一个智能体的 Dev Container 后，默认仍进入该智能体目录，而不是要求开发者手工切换目录；
4. 不改变 MySQL 沙箱的端口、账号、网络隔离、初始化数据和持久化数据卷；
5. 不挂载 Docker Socket，不扩大容器权限；
6. 修改必须有自动化契约测试、运行验证、详细开发日志和明确回滚方式。

## 3. 方案比较

### 方案 A：挂载总仓库，默认进入 01 子目录（采用）

- 将主机 `F:\project_shuqi` 挂载到容器 `/workspace`；
- 将 Compose `working_dir` 与 Dev Container `workspaceFolder` 设为 `/workspace/01_db-security-ops-teaching-agent`；
- 容器内 `/workspace/.git` 对应主机总仓库的 `.git`。

优点是 Git 模型与主机完全一致，后续四个智能体也能共享历史和根级忽略规则；配置简单，符合当前总仓库决策。代价是容器可读写总仓库内其他智能体文件，但这与统一仓库的开发方式一致。

### 方案 B：仅挂载 01 子目录并额外挂载 `.git`（不采用）

该方案需要同时处理 Git 工作树、`core.worktree`、相对路径和容器/主机路径差异，容易造成 Git 将文件判断为删除或工作树错位，也不利于后续四个智能体扩展。

### 方案 C：每个智能体拆分为独立仓库（不采用）

隔离最强，但与用户已经确认的 `agent-practice` 总仓库结构冲突，会增加四套远端、版本和公共材料同步成本。

## 4. 目标架构

主机与容器目录映射如下：

| 主机路径 | 容器路径 | 用途 |
| --- | --- | --- |
| `F:\project_shuqi` | `/workspace` | 总仓库与 `.git` |
| `F:\project_shuqi\01_db-security-ops-teaching-agent` | `/workspace/01_db-security-ops-teaching-agent` | 当前智能体默认开发目录 |

涉及的配置职责如下：

- `infra/compose.yaml`：负责总仓库绑定挂载和容器进程默认工作目录；
- `.devcontainer/devcontainer.json`：负责 VS Code 连接后打开 01 智能体目录；
- `tests/environment/test_compose_contract.py`：约束挂载源、容器目标和默认工作目录，防止以后回退到“容器内无 Git”的配置；
- 当前设计、实施计划与使用说明：同步更新容器路径解释和人工验收命令；
- `04_开发日志.md`：记录 RED/GREEN 测试、容器重建、Git 验证、安全影响和回滚证据。

## 5. 运行流程

1. 用户在本地 VS Code 打开 `01_db-security-ops-teaching-agent`；
2. Dev Containers 读取该目录下的 `.devcontainer/devcontainer.json`；
3. Docker Compose 创建或更新 `shuqi-workspace` 和 `shuqi-mysql-sandbox`；
4. `/workspace` 映射到总仓库，VS Code 打开 `/workspace/01_db-security-ops-teaching-agent`；
5. 容器内执行 `git rev-parse --show-toplevel` 应返回 `/workspace`；
6. 容器内执行 `pytest -q` 时，测试范围仍是 01 智能体项目；
7. MySQL 沙箱继续通过 `127.0.0.1:3307` 暴露给主机，既有 Windows `MySQL57` 的 3306 端口不变。

## 6. 错误处理与安全边界

- Compose 解析失败：停止重建，保留现有容器和数据卷，先修复配置；
- workspace 重建失败：不执行全局 prune，不删除 MySQL 数据卷，可恢复旧配置后重新启动；
- 容器内 Git 根目录不是 `/workspace`：视为验收失败，不宣布 Dev Container 集成完成；
- 自动化测试失败：保留 RED/GREEN 输出并停止提交运行配置；
- MySQL 健康检查失败：只排查本项目 `shuqi-*` 资源，不连接、停止或修改 Windows `MySQL57`，不读写 `E:\MySql`；
- `.env` 继续由根级和项目级 `.gitignore` 排除，测试和日志不得输出实际密码；
- 不使用 `docker system prune`、`volume prune`、强制推送或历史重写。

## 7. 测试与验收设计

### 自动化契约测试

先新增会失败的测试，要求：

1. workspace 绑定挂载源为 Compose 文件上两级，即总仓库根目录；
2. 容器挂载目标为 `/workspace`；
3. Compose `working_dir` 为 `/workspace/01_db-security-ops-teaching-agent`；
4. Dev Container `workspaceFolder` 为同一路径；
5. 既有 MySQL 端口、网络和权限契约保持通过。

在确认测试因旧配置而失败后，再做最小配置修改并运行目标测试与全部测试。

### 运行验收

重建 workspace 后验证：

- `docker inspect shuqi-workspace` 显示 `F:\project_shuqi -> /workspace`；
- 容器默认目录为 `/workspace/01_db-security-ops-teaching-agent`；
- 容器内 `git rev-parse --show-toplevel` 返回 `/workspace`；
- 容器内 `git status -sb` 能显示 `main` 与 `origin/main`；
- 全量 pytest 通过；
- `shuqi-mysql-sandbox` 为 healthy；
- 教学端口仍为 `127.0.0.1:3307->3306`；
- Windows `MySQL57` 仍为 Running，3306 不被项目占用；
- 本地与远端分支 SHA 一致且工作树干净。

### 人工验收

用户从 01 智能体目录执行 `Dev Containers: Reopen in Container`，确认 VS Code 左下角显示容器连接状态、终端默认目录正确、源代码管理面板能够识别总仓库。自动化验证不冒充这一 GUI 人工步骤。

## 8. 文档更新范围

仅更新描述当前有效架构的文档：

- `05_开发环境与教学沙箱设计.md`；
- `06_开发环境与教学沙箱实施计划.md`；
- `07_开发环境使用说明.md`；
- `04_开发日志.md`。

历史日志中的旧路径与旧挂载状态是当时的真实证据，保持原文，不做伪造式批量替换。

## 9. 回滚设计

如果新挂载影响 Dev Container 使用，可将：

- Compose workspace 挂载恢复为 `..:/workspace:cached`；
- Compose `working_dir` 恢复为 `/workspace`；
- Dev Container `workspaceFolder` 恢复为 `/workspace`；

然后只重建 `shuqi-workspace`。MySQL 数据卷、初始化脚本与端口配置不需要回滚。Git 提交可通过新增反向提交撤销，不使用 `reset --hard` 或 force push。

## 10. 非目标

- 本次不开始智能体业务功能实现；
- 不新增第二至第四智能体目录；
- 不更换数据库版本或增加攻击工具；
- 不自动执行 Git 提交功能或把宿主凭据复制进镜像；
- 不改变 GitHub 仓库可见性、分支保护或协作权限。

## 11. 完成定义

只有在配置契约、运行容器、容器内 Git、全量测试、MySQL 隔离和文档日志均通过验证，并由用户完成 VS Code GUI 连接确认后，才能把“开发环境阶段”标记为完成并进入智能体业务实现阶段。
