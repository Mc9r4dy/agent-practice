import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REQUIRED_ENV_KEYS = {
    "SANDBOX_MYSQL_PORT",
    "SANDBOX_MYSQL_ROOT_PASSWORD",
    "SANDBOX_MYSQL_APP_PASSWORD",
    "SANDBOX_MYSQL_READER_PASSWORD",
}


def test_env_is_ignored() -> None:
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in {line.strip() for line in lines}


def test_env_example_is_complete_and_nonsecret() -> None:
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    values = dict(
        line.split("=", 1)
        for line in lines
        if line and not line.startswith("#")
    )
    assert REQUIRED_ENV_KEYS <= values.keys()
    assert values["SANDBOX_MYSQL_PORT"] == "3307"
    for key in REQUIRED_ENV_KEYS - {"SANDBOX_MYSQL_PORT"}:
        assert values[key] == "change_me_local_only"


def test_runtime_env_is_randomized_when_present() -> None:
    runtime = ROOT / ".env"
    if not runtime.exists():
        return
    values = dict(
        line.split("=", 1)
        for line in runtime.read_text(encoding="utf-8").splitlines()
        if line
    )
    assert all(
        values[key] != "change_me_local_only"
        for key in REQUIRED_ENV_KEYS - {"SANDBOX_MYSQL_PORT"}
    )


def test_vscode_tasks_route_through_one_script() -> None:
    tasks = json.loads(
        (ROOT / ".vscode" / "tasks.json").read_text(encoding="utf-8")
    )["tasks"]
    expected = {
        "Preflight",
        "Start",
        "Status",
        "Logs",
        "Test",
        "QuickReset",
        "Rebuild",
        "Stop",
    }
    assert {
        item["label"].removeprefix("Sandbox: ") for item in tasks
    } == expected
    for item in tasks:
        action = item["label"].removeprefix("Sandbox: ")
        assert item["type"] == "process"
        assert item["command"] == "powershell.exe"
        assert item["args"] == [
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "${workspaceFolder}\\scripts\\sandbox.ps1",
            "-Action",
            action,
        ]


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


def test_docs_assign_compose_lifecycle_to_explicit_windows_tasks() -> None:
    usage = (ROOT / "07_开发环境使用说明.md").read_text(encoding="utf-8")
    for required in (
        "shutdownAction=none",
        "关闭或切换 VS Code 不自动停止 Compose",
        "Sandbox: Stop",
        "Sandbox: Status/Start",
        "Reload Window/Reopen in Container",
        "不要 Rebuild/QuickReset",
    ):
        assert required in usage


def test_current_docs_include_fail_closed_full_environment_rollback() -> None:
    usage = (ROOT / "07_开发环境使用说明.md").read_text(encoding="utf-8")
    rollback_section = usage.split("### 12.2 环境阶段完整回滚", 1)[1]
    rollback_script = rollback_section.split("```powershell", 1)[1].split("```", 1)[0]
    required_fragments = (
        "25351d020a9ef413d9288010028acba579fe7938",
        "^Close final Dev Container review gaps$",
        "$preRollbackHead = git rev-parse HEAD",
        '$commits = @(git rev-list "$base..$rollbackHead")',
        "git revert --no-commit $commits",
        "git revert --abort",
        "git restore --source=$preRollbackHead --staged --worktree -- 01_db-security-ops-teaching-agent/04_开发日志.md",
        "--no-deps --force-recreate workspace",
        "Get-Service MySQL57",
        "git push origin main",
        "git ls-remote origin refs/heads/main",
        "git reset --hard",
        "force push",
        "down --volumes",
        "QuickReset",
    )
    for required in required_fragments:
        assert required in rollback_section, f"07 rollback missing {required}"


def test_rollback_checks_main_and_synced_remote_before_docker_or_revert() -> None:
    usage = (ROOT / "07_开发环境使用说明.md").read_text(encoding="utf-8")
    rollback_script = usage.split("### 12.2 环境阶段完整回滚", 1)[1]
    rollback_script = rollback_script.split("```powershell", 1)[1].split("```", 1)[0]
    required_guards = (
        "$branch = git branch --show-current",
        "if ($LASTEXITCODE -ne 0 -or $branch -cne 'main')",
        "$remoteLines = @(git ls-remote origin refs/heads/main)",
        "if ($LASTEXITCODE -ne 0 -or $remoteLines.Count -ne 1)",
        "$remoteHead = ($remoteLines[0] -split '\\s+')[0]",
        "if ([string]::IsNullOrWhiteSpace($remoteHead) -or $remoteHead -ne $preRollbackHead)",
    )
    for required in required_guards:
        assert required in rollback_script
        assert rollback_script.index(required) < rollback_script.index(
            "docker inspect shuqi-mysql-sandbox"
        )
        assert rollback_script.index(required) < rollback_script.index(
            "git revert --no-commit $commits"
        )


def test_rollback_requires_mysql57_to_own_every_3306_listener() -> None:
    usage = (ROOT / "07_开发环境使用说明.md").read_text(encoding="utf-8")
    rollback_script = usage.split("### 12.2 环境阶段完整回滚", 1)[1]
    rollback_script = rollback_script.split("```powershell", 1)[1].split("```", 1)[0]
    for required in (
        "if ($mysql57PidBefore -le 0)",
        "$port3306ConnectionsBefore = @(Get-NetTCPConnection -State Listen -LocalPort 3306)",
        "$foreign3306Before = @($port3306ConnectionsBefore | Where-Object { $_.OwningProcess -ne $mysql57PidBefore })",
        "if ($port3306ConnectionsBefore.Count -eq 0 -or $foreign3306Before.Count -ne 0)",
        "if (Compare-Object $port3306Before $port3306After)",
    ):
        assert required in rollback_script


def test_plan_references_usage_as_the_only_canonical_rollback_script() -> None:
    plan = (ROOT / "06_开发环境与教学沙箱实施计划.md").read_text(encoding="utf-8")
    supplement = plan.split("## 终审修复补充（2026-07-21）", 1)[1]
    assert "`07_开发环境使用说明.md` 第 12.2 节" in supplement
    assert "不得复制维护第二份脚本" in supplement
    assert "```powershell" not in supplement
    assert "$base =" not in supplement


def test_root_git_plan_maps_gitignore_to_process_material_exclusions() -> None:
    plan = (
        ROOT
        / "docs"
        / "superpowers"
        / "plans"
        / "2026-07-20-devcontainer-root-git-integration-implementation.md"
    ).read_text(encoding="utf-8")
    planned_file_map = plan.split("## Planned File Map", 1)[1].split("\n## ", 1)[0]
    gitignore_rows = [
        line for line in planned_file_map.splitlines() if "`.gitignore`" in line
    ]
    assert len(gitignore_rows) == 1, "Planned File Map must include root .gitignore"
    assert "流程材料" in gitignore_rows[0]
