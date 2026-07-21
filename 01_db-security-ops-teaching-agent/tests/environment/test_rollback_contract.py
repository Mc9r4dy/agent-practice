import json
import re
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = ROOT.parent
USAGE = ROOT / "07_开发环境使用说明.md"
PLAN = ROOT / "06_开发环境与教学沙箱实施计划.md"
ROLLBACK = ROOT / "scripts" / "rollback-environment.ps1"
HEADING = "### 12.2 环境阶段完整回滚"
INVOCATION = (
    "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "
    ".\\01_db-security-ops-teaching-agent\\scripts\\rollback-environment.ps1"
)


def fenced_blocks(text: str) -> list[str]:
    return re.findall(r"```[^\r\n]*\r?\n(.*?)```", text, re.I | re.S)


def test_rollback_has_one_documented_entry_point_and_one_executable_source() -> None:
    usage = USAGE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    assert usage.count(HEADING) == 1
    before, section = usage.split(HEADING, 1)
    assert INVOCATION not in before
    executable_blocks = [
        block
        for block in fenced_blocks(usage)
        if re.search(r"rollback-environment\.ps1|git\s+revert", block, re.I)
    ]
    assert executable_blocks == [INVOCATION + "\n"]
    assert ROLLBACK.is_file(), "canonical rollback helper must be versioned"
    helper = ROLLBACK.read_text(encoding="utf-8")
    assert helper.count("$Base = '25351d020a9ef413d9288010028acba579fe7938'") == 1
    assert helper.count("$Marker = '^Harden rollback and environment security contracts$'") == 1
    for duplicate_source in (usage, plan):
        assert "25351d020a9ef413d9288010028acba579fe7938" not in duplicate_source
        assert "^Close final Dev Container review gaps$" not in duplicate_source
        assert "git revert --no-commit" not in duplicate_source
    assert "07_开发环境使用说明.md` 第 12.2 节" in plan
    assert "不得复制维护第二份脚本" in plan
    assert section.count(INVOCATION) == 1

    canonical_source_candidates = []
    candidate_paths = sorted(ROOT.rglob("*.ps1")) + sorted(
        path
        for path in ROOT.rglob("*.md")
        if path.name != "04_开发日志.md" and ".superpowers" not in path.parts
    )
    for path in candidate_paths:
        text = path.read_text(encoding="utf-8")
        if re.search(
            r"25351d020a9ef413d9288010028acba579fe7938|"
            r"Harden\s+rollback\s+and\s+environment\s+security\s+contracts|"
            r"git\s+revert\s+--no-commit",
            text,
            re.I,
        ):
            canonical_source_candidates.append(path)
    assert canonical_source_candidates == [ROLLBACK]


def test_executable_rollback_source_excludes_destructive_commands() -> None:
    assert ROLLBACK.is_file()
    helper = ROLLBACK.read_text(encoding="utf-8").lower()
    for forbidden in (
        "git reset --hard",
        "git clean -fd",
        "--force-with-lease",
        "git push --force",
        "down --volumes",
        "docker system prune",
        "docker volume prune",
        "quickreset",
    ):
        assert forbidden not in helper


def test_preflight_and_recovery_are_structurally_fail_closed() -> None:
    assert ROLLBACK.is_file()
    helper = ROLLBACK.read_text(encoding="utf-8")
    required = (
        "$ExpectedRoot = 'F:\\project_shuqi'",
        "rev-parse --show-toplevel",
        "status --porcelain=v1 --untracked-files=all",
        "Set-Location -LiteralPath $actualRoot",
        "Invoke-RollbackPreflight",
        "Ensure-LocalProcessExclusion",
        "'info/exclude'",
        "git revert --no-commit",
        "git revert --abort",
        "Restore-PreRollbackTrackedState",
        "Restore-PreRollbackWorkspace",
        "$workspaceMutationAttempted = $true",
        "Assert-IndexReadyForRollbackCommit",
        "Assert-FullStatusClean",
        "MANUAL RECOVERY REQUIRED",
    )
    for fragment in required:
        assert fragment in helper
    assert helper.index("Invoke-RollbackPreflight") < helper.index(
        "Ensure-LocalProcessExclusion"
    )
    assert helper.index("Invoke-RollbackPreflight") < helper.index(
        "git revert --no-commit"
    )
    assert helper.index("Assert-IndexReadyForRollbackCommit") < helper.index(
        "git commit"
    )
    assert helper.rindex("Assert-FullStatusClean") > helper.index("git push")


BASE_SCENARIO = {
    "root": {"exitCode": 0, "lines": [r"F:\project_shuqi"]},
    "branch": {"exitCode": 0, "lines": ["main"]},
    "status": {"exitCode": 0, "lines": []},
    "head": {"exitCode": 0, "lines": ["a" * 40]},
    "remote": {"exitCode": 0, "lines": [f"{'a' * 40}\trefs/heads/main"]},
    "mysql57": {"status": "Running", "pid": 4242},
    "listeners3306": [
        {"localAddress": "::", "localPort": 3306, "owningProcess": 4242}
    ],
}


def run_contract_scenario(tmp_path: Path, scenario: dict) -> subprocess.CompletedProcess[str]:
    assert ROLLBACK.is_file(), "PowerShell behavioral boundary is missing"
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")
    return subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROLLBACK),
            "-ContractTestScenario",
            str(path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="explicit host Windows PowerShell contract gate; run this test on the host",
)
@pytest.mark.parametrize(
    "mutation",
    [
        {"root": {"exitCode": 0, "lines": [r"F:\wrong-repository"]}},
        {"branch": {"exitCode": 0, "lines": ["feature"]}},
        {"status": {"exitCode": 9, "lines": []}},
        {"status": {"exitCode": 0, "lines": ["?? hidden.txt"]}},
        {
            "remote": {
                "exitCode": 0,
                "lines": [f"{'b' * 40}\trefs/heads/main"],
            }
        },
        {"mysql57": {"status": "Running", "pid": 0}},
        {
            "listeners3306": [
                {"localAddress": "::", "localPort": 3306, "owningProcess": 9999}
            ]
        },
    ],
)
def test_preflight_failures_execute_no_mutation(
    tmp_path: Path,
    mutation: dict,
) -> None:
    scenario = deepcopy(BASE_SCENARIO)
    scenario.update(mutation)
    result = run_contract_scenario(tmp_path, scenario)
    assert result.returncode != 0
    assert "MUTATION:" not in result.stdout


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="explicit host Windows PowerShell contract gate; run this test on the host",
)
def test_valid_preflight_reaches_mutation_boundary(tmp_path: Path) -> None:
    result = run_contract_scenario(tmp_path, deepcopy(BASE_SCENARIO))
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines().count("MUTATION:rollback-boundary") == 1


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="explicit host Windows PowerShell contract gate; run this test on the host",
)
@pytest.mark.parametrize(
    ("failure", "workspace_attempted"),
    [
        ("revert failed", False),
        ("environment missing", False),
        ("log confirmation cancelled", False),
        ("compose config failed", False),
        ("workspace recreate failed", True),
        ("pytest failed", True),
        ("rollback commit failed", True),
    ],
)
def test_every_precommit_failure_executes_verified_recovery(
    tmp_path: Path,
    failure: str,
    workspace_attempted: bool,
) -> None:
    scenario = deepcopy(BASE_SCENARIO)
    scenario["workflowFailure"] = failure
    scenario["workspaceMutationAttempted"] = workspace_attempted
    scenario["recoveryFailures"] = []
    result = run_contract_scenario(tmp_path, scenario)
    assert result.returncode != 0
    assert result.stdout.splitlines().count("RECOVERY:tracked-state") == 1
    expected_workspace_events = 1 if workspace_attempted else 0
    assert result.stdout.splitlines().count("RECOVERY:workspace") == expected_workspace_events
    normalized_stderr = result.stderr.replace("\r", "").replace("\n-", "-")
    assert "automatic pre-rollback restoration was verified" in normalized_stderr
    assert "MANUAL RECOVERY REQUIRED" not in normalized_stderr


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="explicit host Windows PowerShell contract gate; run this test on the host",
)
def test_failed_automatic_recovery_emits_exact_manual_evidence(tmp_path: Path) -> None:
    scenario = deepcopy(BASE_SCENARIO)
    scenario["workflowFailure"] = "pytest failed"
    scenario["workspaceMutationAttempted"] = True
    scenario["recoveryFailures"] = ["checked revert abort failed"]
    result = run_contract_scenario(tmp_path, scenario)
    assert result.returncode != 0
    assert "MANUAL RECOVERY REQUIRED" in result.stderr
    assert "preRollbackHead='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'" in result.stderr
    assert "workspaceMutationAttempted=True" in result.stderr
    assert "checked revert abort failed" in result.stderr
