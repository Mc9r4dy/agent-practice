import json
import re
from pathlib import Path

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
