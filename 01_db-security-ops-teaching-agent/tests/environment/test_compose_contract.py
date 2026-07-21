import json
from copy import deepcopy
import re
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "infra" / "compose.yaml"
DEVCONTAINER = ROOT / ".devcontainer" / "devcontainer.json"
DOCKERFILE = ROOT / ".devcontainer" / "Dockerfile"
AGENT_CONTAINER_PATH = "/workspace/01_db-security-ops-teaching-agent"


def load_compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def load_devcontainer() -> dict:
    return json.loads(DEVCONTAINER.read_text(encoding="utf-8"))


def assert_workspace_security_contract(workspace: dict) -> None:
    """Reject workspace access that can control the host or elevate the container."""
    assert "privileged" not in workspace
    assert "cap_add" not in workspace
    assert "devices" not in workspace
    assert workspace["volumes"] == ["../..:/workspace:cached"]


def assert_safe_directory_contract(dockerfile: str) -> None:
    """Allow exactly one system-level trust entry for the mounted repository."""
    assert len(re.findall(r"safe\.directory", dockerfile, flags=re.IGNORECASE)) == 1
    assert "/etc/gitconfig" not in dockerfile
    assert "GIT_CONFIG_SYSTEM" not in dockerfile
    assert "--replace-all" not in dockerfile
    canonical_line = "&& git config --system --add safe.directory /workspace \\"
    assert [
        line for line in dockerfile.splitlines() if line.strip() == canonical_line
    ] == ["    " + canonical_line]


def test_services_image_and_local_port() -> None:
    services = load_compose()["services"]
    assert set(services) == {"workspace", "mysql-sandbox"}
    mysql = services["mysql-sandbox"]
    assert mysql["image"] == "mysql:8.4"
    assert mysql["ports"] == [
        "127.0.0.1:${SANDBOX_MYSQL_PORT:-3307}:3306"
    ]
    assert mysql.get("privileged") is not True
    workspace = services["workspace"]
    assert "env_file" not in workspace
    assert "SANDBOX_MYSQL_ROOT_PASSWORD" not in workspace["environment"]


def test_volume_mounts_do_not_touch_mysql57() -> None:
    mysql = load_compose()["services"]["mysql-sandbox"]
    assert "mysql-sandbox-data:/var/lib/mysql" in mysql["volumes"]
    assert "./mysql/init:/docker-entrypoint-initdb.d:ro" in mysql["volumes"]
    assert all("/etc/mysql/conf.d/sandbox.cnf" not in item for item in mysql["volumes"])
    assert all("E:\\MySql" not in item for item in mysql["volumes"])


def test_mysql_security_options_are_command_arguments() -> None:
    mysql = load_compose()["services"]["mysql-sandbox"]
    assert set(mysql["command"]) == {
        "--character-set-server=utf8mb4",
        "--collation-server=utf8mb4_0900_ai_ci",
        "--default-time-zone=+08:00",
        "--local-infile=0",
        "--skip-name-resolve=ON",
        "--max-connections=50",
        "--max-execution-time=5000",
        "--log-error-verbosity=2",
    }


def test_internal_network_and_devcontainer_target() -> None:
    compose = load_compose()
    assert compose["networks"]["sandbox-net"]["internal"] is True
    assert set(compose["services"]["mysql-sandbox"]["networks"]) == {
        "dev-net",
        "sandbox-net",
    }
    assert set(compose["services"]["workspace"]["networks"]) == {
        "dev-net",
        "sandbox-net",
    }
    devcontainer = load_devcontainer()
    assert devcontainer["service"] == "workspace"


def test_devcontainer_does_not_stop_compose_on_editor_shutdown() -> None:
    assert load_devcontainer()["shutdownAction"] == "none"


def test_workspace_has_no_container_host_escalation_paths() -> None:
    assert_workspace_security_contract(load_compose()["services"]["workspace"])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("privileged", True),
        ("cap_add", ["SYS_ADMIN"]),
        ("devices", ["/dev/sda:/dev/sda"]),
        ("volumes", ["../..:/workspace:cached", "/var/run/docker.sock:/var/run/docker.sock"]),
    ],
)
def test_workspace_security_contract_rejects_dangerous_variants(
    field: str,
    value: object,
) -> None:
    workspace = deepcopy(load_compose()["services"]["workspace"])
    workspace[field] = value
    with pytest.raises(AssertionError):
        assert_workspace_security_contract(workspace)


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

    assert_safe_directory_contract(DOCKERFILE.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "injection",
    [
        " && git config --system --add safe.directory /tmp",
        "\nRUN git config --system --add safe.directory /tmp",
        " && git config --system --add SAFE.Directory /tmp",
        " && git config --system --replace-all safe.directory /tmp",
        " && git config --system safe.directory /tmp",
        " && printf '[safe]\\n directory = /tmp\\n' >> /etc/gitconfig",
        " && GIT_CONFIG_SYSTEM=/tmp/gitconfig git config --add safe.directory /tmp",
    ],
)
def test_safe_directory_contract_rejects_bypass_variants(injection: str) -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8") + injection
    with pytest.raises(AssertionError):
        assert_safe_directory_contract(dockerfile)


def test_safe_directory_contract_rejects_echoed_canonical_text() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    echoed = dockerfile.replace(
        "&& git config --system --add safe.directory /workspace \\",
        "&& echo git config --system --add safe.directory /workspace \\",
    )
    assert echoed != dockerfile
    with pytest.raises(AssertionError):
        assert_safe_directory_contract(echoed)
