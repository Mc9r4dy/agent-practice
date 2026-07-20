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
