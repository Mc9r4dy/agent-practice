import base64
import json
import os
import re
import secrets
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
DESIGN = ROOT / "05_开发环境与教学沙箱设计.md"
DEV_LOG = ROOT / "04_开发日志.md"
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
    assert helper.count("$Marker = '^Close final rollback security gates$'") == 1
    for duplicate_source in (usage, plan):
        assert "25351d020a9ef413d9288010028acba579fe7938" not in duplicate_source
        assert "^Close final Dev Container review gaps$" not in duplicate_source
        assert "git revert --no-commit" not in duplicate_source
    assert "07_开发环境使用说明.md` 第 12.2 节" in plan
    assert "不得复制维护第二份脚本" in plan
    assert section.count(INVOCATION) == 1

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


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def create_isolated_rollback_repository(tmp_path: Path) -> dict:
    work = tmp_path / "work"
    remote = tmp_path / "remote.git"
    work.mkdir()
    git(work, "init", "-b", "main")
    git(work, "config", "user.name", "Rollback Contract")
    git(work, "config", "user.email", "rollback@example.invalid")
    git(work, "config", "core.autocrlf", "false")

    agent = work / ROOT.name
    log = agent / "rollback-log.md"
    compose = agent / "infra" / "compose.yaml"
    agent.mkdir()
    compose.parent.mkdir(parents=True)
    log.write_bytes(b"historical-entry\r\n")
    compose.write_text("name: isolated-test\n", encoding="utf-8")
    (work / ".gitignore").write_text("**/.env\n", encoding="utf-8")
    (work / ".rollback-contract-isolated").write_text("isolated test only\n", encoding="utf-8")
    password_values = {
        "root": f"root-{secrets.token_hex(24)}",
        "app": f"app-{secrets.token_hex(24)}",
    }
    (agent / ".env").write_text(
        "TEST_ONLY=not-a-secret\n"
        f"SANDBOX_MYSQL_ROOT_PASSWORD={password_values['root']}\n"
        f"SANDBOX_MYSQL_APP_PASSWORD={password_values['app']}\n",
        encoding="utf-8",
    )
    (work / "stage.txt").write_text("base\n", encoding="utf-8")
    git(work, "add", ".")
    git(work, "commit", "-m", "isolated rollback base")
    base = git(work, "rev-parse", "HEAD")

    (work / "stage.txt").write_text("environment-one\n", encoding="utf-8")
    git(work, "add", "stage.txt")
    git(work, "commit", "-m", "isolated environment one")
    (work / "stage.txt").write_text("environment-two\n", encoding="utf-8")
    log.write_bytes(log.read_bytes() + b"pre-rollback-entry\r\n")
    git(work, "add", "stage.txt", str(log.relative_to(work)))
    git(work, "commit", "-m", "Close final rollback security gates")
    head = git(work, "rev-parse", "HEAD")
    original_log = log.read_bytes()

    git(tmp_path, "init", "--bare", str(remote))
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-u", "origin", "main")
    return {
        "work": work,
        "agent": agent,
        "log": log,
        "base": base,
        "head": head,
        "original_log": original_log,
        "password_values": password_values,
    }


def isolated_scenario(repo: dict, edited_log: bytes | None = None) -> dict:
    if edited_log is None:
        edited_log = repo["original_log"] + b"\r\nrollback evidence appended\r\n"
    return {
        "mode": "isolated",
        "expectedRoot": str(repo["work"]),
        "base": repo["base"],
        "marker": "^Close final rollback security gates$",
        "logPath": str(repo["log"].relative_to(repo["work"])).replace("\\", "/"),
        "mysql57": {"status": "Running", "pid": 4242},
        "listeners3306": [
            {"localAddress": "::", "localPort": 3306, "owningProcess": 4242}
        ],
        "listeners3307": [
            {"localAddress": "127.0.0.1", "localPort": 3307, "owningProcess": 5252}
        ],
        "confirmation": "ROLLBACK-LOG-APPENDED",
        "editedLogBase64": base64.b64encode(edited_log).decode("ascii"),
        "failureRules": [],
    }


def run_isolated_scenario(
    tmp_path: Path,
    scenario: dict,
    work: Path,
) -> subprocess.CompletedProcess[str]:
    scenario_path = tmp_path / "isolated-scenario.json"
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
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
            str(scenario_path),
        ],
        cwd=work,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="real rollback recovery path requires host Windows PowerShell",
)
@pytest.mark.parametrize(
    ("failure_rule", "remove_env", "confirmation", "workspace_recovery"),
    [
        (
            {
                "file": "git",
                "arguments": ["revert", "--no-commit"],
                "occurrence": 1,
                "afterExecute": True,
                "exitCode": 31,
            },
            False,
            "ROLLBACK-LOG-APPENDED",
            False,
        ),
        (None, True, "ROLLBACK-LOG-APPENDED", False),
        (None, False, "CANCEL", False),
        (
            {
                "file": "docker",
                "arguments": ["compose", "config", "--quiet"],
                "occurrence": 1,
                "afterExecute": False,
                "exitCode": 32,
            },
            False,
            "ROLLBACK-LOG-APPENDED",
            False,
        ),
        (
            {
                "file": "docker",
                "arguments": ["compose", "up", "workspace"],
                "occurrence": 1,
                "afterExecute": False,
                "exitCode": 33,
            },
            False,
            "ROLLBACK-LOG-APPENDED",
            True,
        ),
        (
            {
                "file": "docker",
                "arguments": ["exec", "pytest", "-q"],
                "occurrence": 1,
                "afterExecute": False,
                "exitCode": 34,
            },
            False,
            "ROLLBACK-LOG-APPENDED",
            True,
        ),
        (
            {
                "file": "git",
                "arguments": ["commit"],
                "occurrence": 1,
                "afterExecute": False,
                "exitCode": 35,
            },
            False,
            "ROLLBACK-LOG-APPENDED",
            True,
        ),
    ],
)
def test_failures_use_real_production_catch_and_recovery(
    tmp_path: Path,
    failure_rule: dict | None,
    remove_env: bool,
    confirmation: str,
    workspace_recovery: bool,
) -> None:
    repo = create_isolated_rollback_repository(tmp_path)
    scenario = isolated_scenario(repo)
    scenario["confirmation"] = confirmation
    if failure_rule is not None:
        scenario["failureRules"] = [failure_rule]
    if remove_env:
        (repo["agent"] / ".env").unlink()

    result = run_isolated_scenario(tmp_path, scenario, repo["work"])
    normalized_stderr = result.stderr.replace("\r", "").replace("\n-", "-")
    assert result.returncode != 0
    assert "Invoke-ContractRollbackSimulation" not in result.stdout
    assert "CALL:git restore" in result.stdout
    assert "CALL:git diff --cached --quiet" in result.stdout
    assert "automatic pre-rollback restoration was verified" in normalized_stderr
    assert git(repo["work"], "rev-parse", "HEAD") == repo["head"]
    assert git(repo["work"], "status", "--porcelain=v1", "--untracked-files=all") == ""
    assert result.stdout.count("RECOVERY:workspace") == (1 if workspace_recovery else 0)
    if workspace_recovery:
        assert result.stdout.count("CALL:docker compose") >= 3


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="real rollback recovery path requires host Windows PowerShell",
)
def test_real_recovery_failure_emits_manual_evidence(tmp_path: Path) -> None:
    repo = create_isolated_rollback_repository(tmp_path)
    scenario = isolated_scenario(repo)
    scenario["failureRules"] = [
        {
            "file": "docker",
            "arguments": ["exec", "pytest", "-q"],
            "occurrence": 1,
            "afterExecute": False,
            "exitCode": 41,
        },
        {
            "file": "git",
            "arguments": ["restore", "--staged", "--worktree", "."],
            "occurrence": 1,
            "afterExecute": False,
            "exitCode": 42,
        },
    ]
    result = run_isolated_scenario(tmp_path, scenario, repo["work"])
    normalized_stderr = result.stderr.replace("\r", "").replace("\n-", "-")
    compact_stderr = re.sub(r"\s+", "", normalized_stderr)
    assert result.returncode != 0
    assert "MANUAL RECOVERY REQUIRED" in normalized_stderr
    assert f"preRollbackHead='{repo['head']}'" in normalized_stderr
    assert "workspaceMutationAttempted=True" in compact_stderr
    assert "trackedrestorefailedwithnativeexit42" in compact_stderr
    assert "RECOVERY:workspace" in result.stdout


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="real rollback recovery path requires host Windows PowerShell",
)
def test_checked_abort_failure_is_manual_recovery_evidence(tmp_path: Path) -> None:
    repo = create_isolated_rollback_repository(tmp_path)
    scenario = isolated_scenario(repo)
    scenario["failureRules"] = [
        {
            "file": "docker",
            "arguments": ["exec", "pytest", "-q"],
            "occurrence": 1,
            "afterExecute": False,
            "exitCode": 51,
            "createSequencer": True,
        },
        {
            "file": "git",
            "arguments": ["revert", "--abort"],
            "occurrence": 1,
            "afterExecute": False,
            "exitCode": 52,
        },
    ]
    result = run_isolated_scenario(tmp_path, scenario, repo["work"])
    compact_stderr = re.sub(r"\s+", "", result.stderr)
    assert result.returncode != 0
    assert "CALL:git revert --abort" in result.stdout
    assert "MANUALRECOVERYREQUIRED" in compact_stderr
    assert "revertabortfailedwithnativeexit52" in compact_stderr


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="real rollback success path requires host Windows PowerShell",
)
def test_valid_log_append_completes_isolated_production_path(tmp_path: Path) -> None:
    repo = create_isolated_rollback_repository(tmp_path)
    suffix = b"\r\nverified rollback evidence\r\n"
    scenario = isolated_scenario(repo, repo["original_log"] + suffix)
    result = run_isolated_scenario(tmp_path, scenario, repo["work"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert repo["log"].read_bytes() == repo["original_log"] + suffix
    assert git(repo["work"], "status", "--porcelain=v1", "--untracked-files=all") == ""
    assert git(repo["work"], "log", "-1", "--format=%s") == "Rollback complete environment stage"
    assert git(repo["work"], "rev-parse", "HEAD") == git(
        repo["work"], "ls-remote", "--exit-code", "origin", "refs/heads/main"
    ).split()[0]


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="append-only log validation requires host Windows PowerShell",
)
@pytest.mark.parametrize(
    ("edit", "expected_error"),
    [
        (lambda original: original[:-1], "append-only"),
        (lambda original: b"X" + original[1:] + b"suffix", "append-only"),
        (lambda original: b"X" + original[1:], "append-only"),
        (lambda original: original + b" \r\n\t", "non-whitespace"),
        (
            lambda original: original + b"\r\npassword=supersecret123\r\n",
            "secret-safety",
        ),
    ],
)
def test_log_rejects_non_append_edits_whitespace_and_secrets(
    tmp_path: Path,
    edit,
    expected_error: str,
) -> None:
    repo = create_isolated_rollback_repository(tmp_path)
    scenario = isolated_scenario(repo, edit(repo["original_log"]))
    result = run_isolated_scenario(tmp_path, scenario, repo["work"])
    normalized_stderr = result.stderr.replace("\r", "").replace("\n-", "-")
    assert result.returncode != 0
    assert expected_error in normalized_stderr
    assert "CALL:git add" not in result.stdout
    assert git(repo["work"], "rev-parse", "HEAD") == repo["head"]
    assert repo["log"].read_bytes() == repo["original_log"]


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="runtime .env secret-value validation requires host Windows PowerShell",
)
@pytest.mark.parametrize(
    "suffix_kind",
    ["root_assignment", "app_assignment", "raw_value", "ordinary_note"],
)
def test_runtime_env_password_values_are_private_and_rejected_from_log_suffix(
    tmp_path: Path,
    suffix_kind: str,
) -> None:
    repo = create_isolated_rollback_repository(tmp_path)
    private_values = repo["password_values"]
    suffixes = {
        "root_assignment": (
            b"\r\nSANDBOX_MYSQL_ROOT_PASSWORD="
            + private_values["root"].encode("utf-8")
            + b"\r\n"
        ),
        "app_assignment": (
            b"\r\nSANDBOX_MYSQL_APP_PASSWORD="
            + private_values["app"].encode("utf-8")
            + b"\r\n"
        ),
        "raw_value": b"\r\nobserved value " + private_values["root"].encode("utf-8") + b"\r\n",
        "ordinary_note": b"\r\nrollback verification completed without credentials\r\n",
    }
    scenario = isolated_scenario(repo, repo["original_log"] + suffixes[suffix_kind])
    result = run_isolated_scenario(tmp_path, scenario, repo["work"])
    combined_output = result.stdout + result.stderr
    output_exposed_private_value = any(
        value in combined_output for value in private_values.values()
    )
    assert not output_exposed_private_value

    if suffix_kind == "ordinary_note":
        assert result.returncode == 0, "ordinary rollback note was rejected"
        assert git(repo["work"], "log", "-1", "--format=%s") == (
            "Rollback complete environment stage"
        )
    else:
        assert result.returncode != 0
        assert "secret-safety" in result.stderr.replace("\r", "").replace("\n-", "-")
        assert "CALL:git add" not in result.stdout
        assert git(repo["work"], "rev-parse", "HEAD") == repo["head"]
        assert repo["log"].read_bytes() == repo["original_log"]


def powershell_command_asts(path: Path) -> list[dict]:
    env = os.environ.copy()
    env["ROLLBACK_AST_TARGET"] = str(path)
    script = r"""
$tokens = $null
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile(
    $env:ROLLBACK_AST_TARGET, [ref]$tokens, [ref]$errors
)
if (@($errors).Count -ne 0) { throw ($errors -join '; ') }
$assignments = @($ast.FindAll({
    param($node)
    $node -is [Management.Automation.Language.AssignmentStatementAst]
}, $true) | Sort-Object { $_.Extent.StartOffset })

function New-ConstantResolution {
    param([bool]$Known, [bool]$IsArray, [object[]]$Values)
    return [pscustomobject]@{ known = $Known; isArray = $IsArray; values = @($Values) }
}

function Resolve-ConstantAst {
    param($Node, [hashtable]$Constants)
    if ($null -eq $Node) { return New-ConstantResolution $false $false @() }
    if ($Node -is [Management.Automation.Language.CommandExpressionAst]) {
        return Resolve-ConstantAst $Node.Expression $Constants
    }
    if ($Node -is [Management.Automation.Language.StringConstantExpressionAst] -or
        $Node -is [Management.Automation.Language.ConstantExpressionAst]) {
        return New-ConstantResolution $true $false @([string]$Node.Value)
    }
    if ($Node -is [Management.Automation.Language.VariableExpressionAst]) {
        $name = $Node.VariablePath.UserPath
        if ($Constants.ContainsKey($name)) { return $Constants[$name] }
        return New-ConstantResolution $false $false @()
    }
    if ($Node -is [Management.Automation.Language.ParenExpressionAst]) {
        return Resolve-ConstantAst $Node.Pipeline $Constants
    }
    if ($Node -is [Management.Automation.Language.PipelineAst]) {
        if ($Node.PipelineElements.Count -ne 1) {
            return New-ConstantResolution $false $false @()
        }
        return Resolve-ConstantAst $Node.PipelineElements[0] $Constants
    }
    if ($Node -is [Management.Automation.Language.StatementBlockAst]) {
        if ($Node.Statements.Count -ne 1) {
            return New-ConstantResolution $false $false @()
        }
        return Resolve-ConstantAst $Node.Statements[0] $Constants
    }
    if ($Node -is [Management.Automation.Language.ArrayExpressionAst]) {
        $inner = Resolve-ConstantAst $Node.SubExpression $Constants
        if (-not $inner.known) { return $inner }
        return New-ConstantResolution $true $true @($inner.values)
    }
    if ($Node -is [Management.Automation.Language.ArrayLiteralAst]) {
        $items = [Collections.Generic.List[object]]::new()
        foreach ($element in $Node.Elements) {
            $resolved = Resolve-ConstantAst $element $Constants
            if (-not $resolved.known) { return New-ConstantResolution $false $true @() }
            foreach ($value in @($resolved.values)) { $items.Add($value) }
        }
        return New-ConstantResolution $true $true @($items)
    }
    if ($Node -is [Management.Automation.Language.BinaryExpressionAst] -and
        $Node.Operator -eq [Management.Automation.Language.TokenKind]::Plus) {
        $left = Resolve-ConstantAst $Node.Left $Constants
        $right = Resolve-ConstantAst $Node.Right $Constants
        if (-not $left.known -or -not $right.known) {
            return New-ConstantResolution $false ($left.isArray -or $right.isArray) @()
        }
        if (-not $left.isArray -and -not $right.isArray) {
            return New-ConstantResolution $true $false @(
                ([string]$left.values[0]) + ([string]$right.values[0])
            )
        }
        return New-ConstantResolution $true $true @(@($left.values) + @($right.values))
    }
    if ($Node -is [Management.Automation.Language.CommandAst] -and
        $Node.GetCommandName() -ceq 'Join-Path' -and $Node.CommandElements.Count -ge 3) {
        $parts = [Collections.Generic.List[string]]::new()
        foreach ($element in @($Node.CommandElements[1..($Node.CommandElements.Count - 1)])) {
            $resolved = Resolve-ConstantAst $element $Constants
            if (-not $resolved.known -or $resolved.values.Count -ne 1) {
                return New-ConstantResolution $false $false @()
            }
            $parts.Add([string]$resolved.values[0])
        }
        return New-ConstantResolution $true $false @(($parts -join '\'))
    }
    return New-ConstantResolution $false $false @()
}

function Get-ConstantsBefore {
    param([int]$Offset)
    $constants = @{
        PSScriptRoot = New-ConstantResolution $true $false @(
            [IO.Path]::GetDirectoryName($env:ROLLBACK_AST_TARGET)
        )
    }
    foreach ($assignment in $assignments) {
        if ($assignment.Extent.EndOffset -gt $Offset) { break }
        if ($assignment.Left -isnot [Management.Automation.Language.VariableExpressionAst]) {
            continue
        }
        $resolved = Resolve-ConstantAst $assignment.Right $constants
        if ($resolved.known) {
            $constants[$assignment.Left.VariablePath.UserPath] = $resolved
        }
    }
    return $constants
}

$commands = @($ast.FindAll({
    param($node)
    $node -is [Management.Automation.Language.CommandAst]
}, $true) | ForEach-Object {
    $constants = Get-ConstantsBefore $_.Extent.StartOffset
    $resolvedTokens = [Collections.Generic.List[string]]::new()
    $resolvedName = $_.GetCommandName()
    if ([string]::IsNullOrWhiteSpace($resolvedName)) {
        $commandResolution = Resolve-ConstantAst $_.CommandElements[0] $constants
        if ($commandResolution.known -and $commandResolution.values.Count -eq 1) {
            $resolvedName = [string]$commandResolution.values[0]
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($resolvedName)) {
        $resolvedTokens.Add($resolvedName)
    }
    if ($_.CommandElements.Count -gt 1) {
        foreach ($element in @($_.CommandElements[1..($_.CommandElements.Count - 1)])) {
            if ($element -is [Management.Automation.Language.CommandParameterAst]) { continue }
            $resolved = Resolve-ConstantAst $element $constants
            if ($resolved.known) {
                foreach ($value in @($resolved.values)) {
                    $resolvedTokens.Add([string]$value)
                }
            }
        }
    }
    $ancestor = $_.Parent
    while ($null -ne $ancestor -and $ancestor -isnot [Management.Automation.Language.FunctionDefinitionAst]) {
        $ancestor = $ancestor.Parent
    }
    [pscustomobject]@{
        name = $_.GetCommandName()
        text = $_.Extent.Text
        line = $_.Extent.StartLineNumber
        functionName = if ($null -eq $ancestor) { $null } else { $ancestor.Name }
        resolvedTokens = @($resolvedTokens)
    }
})
ConvertTo-Json -Compress -Depth 5 -InputObject $commands
"""
    result = subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", script],
        env=env,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    parsed = json.loads(result.stdout)
    return parsed if isinstance(parsed, list) else [parsed]


def run_native_allowlist_probe(
    executable: str,
    arguments: list[str],
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["ROLLBACK_AST_TARGET"] = str(ROLLBACK)
    env["ROLLBACK_ALLOWLIST_PROBE"] = json.dumps(
        {"file": executable, "arguments": arguments}
    )
    script = r"""
$tokens = $null
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile(
    $env:ROLLBACK_AST_TARGET, [ref]$tokens, [ref]$errors
)
if (@($errors).Count -ne 0) { exit 90 }
$definitions = @($ast.FindAll({
    param($node)
    $node -is [Management.Automation.Language.FunctionDefinitionAst]
}, $true) | ForEach-Object { $_.Extent.Text })
Invoke-Expression ($definitions -join "`n")
$ProjectName = 'shuqi-db-agent'
$EnvFile = '01_db-security-ops-teaching-agent/.env'
$ComposeFile = '01_db-security-ops-teaching-agent/infra/compose.yaml'
$WorkspaceContainer = 'shuqi-workspace'
$MysqlContainer = 'shuqi-mysql-sandbox'
$MysqlVolume = 'shuqi-db-agent-mysql-data'
$LogPath = '01_db-security-ops-teaching-agent/04_开发日志.md'
$probe = $env:ROLLBACK_ALLOWLIST_PROBE | ConvertFrom-Json
try {
    Assert-NativeCommandAllowed -File ([string]$probe.file) -Arguments @($probe.arguments)
    [Console]::Out.WriteLine('ALLOWED')
    exit 0
} catch {
    [Console]::Out.WriteLine('REJECTED')
    exit 3
}
"""
    return subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", script],
        env=env,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )


def executable_tokens(command_text: str) -> list[str]:
    matches = re.findall(r"'([^']*)'|\"([^\"]*)\"|([A-Za-z0-9_./:=+-]+)", command_text)
    return [
        token.lower()
        for match in matches
        if (token := next((item for item in match if item), ""))
    ]


def dangerous_ast_commands(commands: list[dict]) -> list[str]:
    dangerous: list[str] = []
    for command in commands:
        tokens = executable_tokens(command["text"])
        tokens.extend(token.lower() for token in command.get("resolvedTokens", []))
        joined = " ".join(tokens)
        if (
            ("git" in tokens and "reset" in tokens and "--hard" in tokens)
            or ("git" in tokens and "clean" in tokens and any(t.startswith("-fd") for t in tokens))
            or ("git" in tokens and "push" in tokens and any(t.startswith("--force") for t in tokens))
            or ("docker" in tokens and "system" in tokens and "prune" in tokens)
            or ("docker" in tokens and "volume" in tokens and "prune" in tokens)
            or ("docker" in tokens and "down" in tokens and "--volumes" in tokens)
            or ("invoke-compose" in tokens and "down" in tokens and "--volumes" in tokens)
            or "quickreset" in joined
        ):
            dangerous.append(command["text"])
    return dangerous


def resolved_rollback_entry_points(commands: list[dict]) -> list[str]:
    findings = []
    for command in commands:
        tokens = [token.lower() for token in command.get("resolvedTokens", [])]
        if not tokens:
            continue
        helper_tokens = [
            token
            for token in tokens
            if token.replace("\\", "/").endswith("rollback-environment.ps1")
        ]
        invokes_helper = bool(helper_tokens) and (
            tokens[0] in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}
            or tokens[0] in helper_tokens
        )
        if tokens[0] == "invoke-rollback" or invokes_helper:
            findings.append(command["text"])
    return findings


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="PowerShell executable-code AST gate runs on the Windows host",
)
@pytest.mark.parametrize(
    "source",
    [
        "Invoke-Native -File 'git' -Arguments @('reset', '--hard')",
        "Invoke-Native -File 'git' -Arguments @('clean', '-fdx')",
        "Invoke-Native -File 'git' -Arguments @('push', '--force', 'origin', 'main')",
        "Invoke-Native -File 'docker' -Arguments @('system', 'prune')",
        "Invoke-Native -File 'docker' -Arguments @('volume', 'prune')",
        "Invoke-Native -File 'docker' -Arguments @('compose', 'down', '--volumes')",
        "Invoke-Compose -Arguments @('down', '--volumes')",
    ],
)
def test_ast_gate_detects_wrapper_and_array_dangerous_commands(
    tmp_path: Path,
    source: str,
) -> None:
    mutant = tmp_path / "mutant.ps1"
    mutant.write_text(source, encoding="utf-8")
    assert dangerous_ast_commands(powershell_command_asts(mutant)) == [source]


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="PowerShell constant/data-flow AST gate runs on the Windows host",
)
@pytest.mark.parametrize(
    "source",
    [
        "$tool = 'git'\n$arguments = @('reset', '--hard')\n"
        "Invoke-Native -File $tool -Arguments $arguments",
        "$tool = ('g' + 'it')\n$verb = ('re' + 'set')\n"
        "$arguments = @(($verb), ('--' + 'hard'))\n"
        "Invoke-Native -File ($tool) -Arguments ($arguments)",
    ],
)
def test_ast_gate_detects_variable_and_concatenated_dangerous_vectors(
    tmp_path: Path,
    source: str,
) -> None:
    mutant = tmp_path / "indirected-mutant.ps1"
    mutant.write_text(source, encoding="utf-8")
    findings = dangerous_ast_commands(powershell_command_asts(mutant))
    assert len(findings) == 1
    assert "Invoke-Native" in findings[0]


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="resolved native-command allowlist runs on the Windows host",
)
@pytest.mark.parametrize(
    ("executable", "arguments", "allowed"),
    [
        ("git", ["status", "--porcelain=v1", "--untracked-files=all"], True),
        ("docker", ["inspect", "shuqi-mysql-sandbox"], True),
        ("git", ["reset", "--hard"], False),
        ("git", ["clean", "-fdx"], False),
        ("git", ["push", "--force", "origin", "main"], False),
        ("git", ["revert", "--no-commit", "a" * 40], False),
        (
            "git",
            ["restore", f"--source={'a' * 40}", "--staged", "--worktree", "--", "."],
            False,
        ),
        ("docker", ["system", "prune"], False),
        ("docker", ["volume", "prune"], False),
        (
            "docker",
            [
                "compose",
                "--project-name",
                "shuqi-db-agent",
                "--env-file",
                "01_db-security-ops-teaching-agent/.env",
                "-f",
                "01_db-security-ops-teaching-agent/infra/compose.yaml",
                "down",
                "--volumes",
            ],
            False,
        ),
        ("powershell.exe", ["-Command", "Write-Output", "unsafe"], False),
    ],
)
def test_runtime_allowlist_checks_resolved_native_vectors(
    executable: str,
    arguments: list[str],
    allowed: bool,
) -> None:
    result = run_native_allowlist_probe(executable, arguments)
    assert (result.returncode == 0) is allowed
    assert result.stdout.strip() == ("ALLOWED" if allowed else "REJECTED")


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="PowerShell executable-code AST gate runs on the Windows host",
)
def test_ast_gate_ignores_comments_and_unused_documentation_strings(tmp_path: Path) -> None:
    harmless = tmp_path / "harmless.ps1"
    harmless.write_text(
        "# Invoke-Native -File 'git' -Arguments @('reset','--hard')\n"
        "# & Invoke-Rollback -Baseline $baseline\n"
        "$documentation = \"git clean -fd and rollback-environment.ps1 are prohibited\"\n"
        "Write-Output 'safe'\n",
        encoding="utf-8",
    )
    commands = powershell_command_asts(harmless)
    assert dangerous_ast_commands(commands) == []
    assert resolved_rollback_entry_points(commands) == []


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="PowerShell executable-code AST gate runs on the Windows host",
)
def test_production_ast_proves_required_calls_and_control_order() -> None:
    commands = powershell_command_asts(ROLLBACK)
    assert dangerous_ast_commands(commands) == []
    command_texts = [command["text"] for command in commands]
    assert any("Invoke-Rollback -Baseline" in text for text in command_texts)
    production_entries = resolved_rollback_entry_points(commands)
    assert len(production_entries) == 1
    assert "Invoke-Rollback -Baseline" in production_entries[0]
    assert any("Assert-IsolatedContractRoot" in text for text in command_texts)
    native_boundary = [
        command for command in commands if command["functionName"] == "Invoke-Native"
    ]
    allowlist_calls = [
        command for command in native_boundary if command["name"] == "Assert-NativeCommandAllowed"
    ]
    boundary_guard = next(
        command
        for command in allowlist_calls
        if "-File $File -Arguments $Arguments" in command["text"]
    )
    assert boundary_guard["line"] == min(command["line"] for command in native_boundary)
    assert any("'rev-parse', '--git-dir'" in command["text"] for command in allowlist_calls)
    assert not any("Invoke-ContractRollbackSimulation" in text for text in command_texts)
    assert any(
        "Invoke-Native" in text and "'git'" in text and "'revert'" in text and "'--no-commit'" in text
        for text in command_texts
    )
    assert any(
        "Invoke-Native" in text and "'git'" in text and "'revert'" in text and "'--abort'" in text
        for text in command_texts
    )
    ensure_line = next(
        command["line"] for command in commands if command["name"] == "Ensure-LocalProcessExclusion"
    )
    commit_list_line = max(
        command["line"]
        for command in commands
        if command["name"] == "Invoke-Native" and "'rev-list'" in command["text"]
    )
    revert_line = next(
        command["line"]
        for command in commands
        if command["name"] == "Invoke-Native" and "'--no-commit'" in command["text"]
    )
    assert commit_list_line < ensure_line < revert_line


SUPPORTED_EXECUTABLE_SUFFIXES = {".ps1", ".psm1", ".cmd", ".bat", ".sh"}
EXPECTED_EXECUTABLE_SOURCES = {
    Path("infra/mysql/init/004_accounts.sh"),
    Path("scripts/rollback-environment.ps1"),
    Path("scripts/sandbox.ps1"),
}


def executable_source_files(root: Path) -> list[Path]:
    sources = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXECUTABLE_SUFFIXES:
            continue
        if ".superpowers" in path.parts:
            continue
        sources.append(path)
    return sorted(sources)


@pytest.mark.parametrize("suffix", sorted(SUPPORTED_EXECUTABLE_SUFFIXES))
def test_executable_inventory_enumerates_unexpected_files_regardless_of_content(
    tmp_path: Path,
    suffix: str,
) -> None:
    unexpected = tmp_path / f"harmless-but-unexpected{suffix}"
    unexpected.write_text("ordinary harmless content\n", encoding="utf-8")
    assert executable_source_files(tmp_path) == [unexpected]


@pytest.mark.parametrize("suffix", sorted(SUPPORTED_EXECUTABLE_SUFFIXES))
def test_source_enumeration_detects_duplicate_supported_entry_points(
    tmp_path: Path,
    suffix: str,
) -> None:
    canonical = tmp_path / "rollback-environment.ps1"
    duplicate = tmp_path / f"duplicate{suffix}"
    canonical.write_text("$Marker = '^Close final rollback security gates$'", encoding="utf-8")
    duplicate.write_text("powershell ./rollback-environment.ps1", encoding="utf-8")
    assert executable_source_files(tmp_path) == [duplicate, canonical]


@pytest.mark.parametrize("suffix", sorted(SUPPORTED_EXECUTABLE_SUFFIXES))
def test_source_enumeration_detects_noncontiguous_wrapper_revert_tokens(
    tmp_path: Path,
    suffix: str,
) -> None:
    canonical = tmp_path / "rollback-environment.ps1"
    duplicate = tmp_path / f"duplicate{suffix}"
    canonical.write_text("function Invoke-Rollback { Write-Output safe }", encoding="utf-8")
    duplicate.write_text(
        "Invoke-Native -File 'git' -Arguments @('revert', '--no-commit')",
        encoding="utf-8",
    )
    assert executable_source_files(tmp_path) == [duplicate, canonical]


def test_repository_has_exactly_one_supported_executable_rollback_source() -> None:
    relative_sources = {
        path.relative_to(ROOT) for path in executable_source_files(ROOT)
    }
    assert relative_sources == EXPECTED_EXECUTABLE_SOURCES


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="PowerShell constant/data-flow entry-point gate runs on the Windows host",
)
@pytest.mark.parametrize(
    "source",
    [
        "$leaf = 'rollback-' + 'environment.ps1'\n"
        "$runner = 'powershell' + '.exe'\n"
        "& $runner -File (Join-Path $PSScriptRoot $leaf)",
        "$entry = 'Invoke-' + 'Rollback'\n& $entry -Baseline $baseline",
    ],
)
def test_ast_gate_resolves_concatenated_rollback_entry_points(
    tmp_path: Path,
    source: str,
) -> None:
    duplicate = tmp_path / "sandbox.ps1"
    duplicate.write_text(source, encoding="utf-8")
    findings = resolved_rollback_entry_points(powershell_command_asts(duplicate))
    assert len(findings) == 1


def test_design_status_and_documented_exclusion_order_are_current() -> None:
    design = DESIGN.read_text(encoding="utf-8")
    usage = USAGE.read_text(encoding="utf-8")
    assert "环境实施与 VS Code Dev Containers 人工连接验收均已完成" in design
    assert "待 VS Code Dev Containers 人工连接确认" not in design
    section = usage.split(HEADING, 1)[1]
    marker_validation = "marker、祖先关系、线性范围和 commit list"
    exclusion = "`.git/info/exclude`"
    assert marker_validation in section
    assert section.index(marker_validation) < section.index(exclusion)


def test_final_marker_and_dev045_correct_published_dev044_counts() -> None:
    helper = ROLLBACK.read_text(encoding="utf-8")
    log = DEV_LOG.read_text(encoding="utf-8")
    assert helper.count("$Marker = '^Close final rollback security gates$'") == 1
    assert log.count("## DEV-20260721-045：") == 1
    dev045 = log.split("## DEV-20260721-045：", 1)[1]
    assert "DEV-044" in dev045 and "更正" in dev045
    assert "46 passed" in dev045
    assert "74 passed, 33 skipped" in dev045
    assert "71 passed" in dev045
    assert "80 passed, 52 skipped" in dev045


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="PowerShell executable-code AST gate runs on the Windows host",
)
def test_log_guards_are_executable_before_staging() -> None:
    commands = powershell_command_asts(ROLLBACK)
    append_guards = [
        command["line"] for command in commands if command["name"] == "Assert-AppendOnlyRollbackLog"
    ]
    password_loaders = [
        command["line"] for command in commands if command["name"] == "Get-PrivatePasswordValues"
    ]
    secret_guards = [
        command["line"] for command in commands if command["name"] == "Assert-AppendedLogSecretSafe"
    ]
    stage_logs = [
        command["line"]
        for command in commands
        if command["name"] == "Invoke-Native"
        and "'add'" in command["text"]
        and "$LogPath" in command["text"]
    ]
    assert len(append_guards) == 1, "append-only guard must execute exactly once"
    assert len(password_loaders) == 1, "runtime password values must load exactly once"
    assert len(secret_guards) == 1, "secret guard must execute exactly once"
    assert len(stage_logs) == 1, "log staging must execute exactly once"
    assert append_guards[0] < password_loaders[0] < secret_guards[0] < stage_logs[0]
