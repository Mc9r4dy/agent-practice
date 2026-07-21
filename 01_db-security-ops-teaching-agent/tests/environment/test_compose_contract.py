import json
from copy import deepcopy
from pathlib import Path
import shlex
import subprocess

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
    assert set(workspace) == {
        "container_name",
        "build",
        "working_dir",
        "command",
        "environment",
        "volumes",
        "depends_on",
        "networks",
        "restart",
    }
    assert workspace["container_name"] == "shuqi-workspace"
    assert workspace["build"] == {
        "context": "..",
        "dockerfile": ".devcontainer/Dockerfile",
    }
    assert workspace["working_dir"] == AGENT_CONTAINER_PATH
    assert workspace["command"] == "sleep infinity"
    assert workspace["environment"] == {
        "MYSQL_HOST": "mysql-sandbox",
        "MYSQL_PORT": "3306",
        "MYSQL_DATABASE": "shuqi_sandbox",
        "MYSQL_APP_USER": "sandbox_app",
        "MYSQL_READER_USER": "sandbox_reader",
        "SANDBOX_MYSQL_APP_PASSWORD": "${SANDBOX_MYSQL_APP_PASSWORD}",
        "SANDBOX_MYSQL_READER_PASSWORD": "${SANDBOX_MYSQL_READER_PASSWORD}",
    }
    assert workspace["volumes"] == ["../..:/workspace:cached"]
    assert workspace["depends_on"] == {
        "mysql-sandbox": {"condition": "service_healthy"}
    }
    assert workspace["networks"] == ["dev-net", "sandbox-net"]
    assert workspace["restart"] == "unless-stopped"


def assert_mysql_security_contract(mysql: dict) -> None:
    """Reject MySQL service options that can escape the sandbox boundary."""
    assert set(mysql) == {
        "container_name",
        "image",
        "command",
        "env_file",
        "environment",
        "ports",
        "volumes",
        "healthcheck",
        "networks",
        "restart",
    }
    assert mysql["container_name"] == "shuqi-mysql-sandbox"
    assert mysql["image"] == "mysql:8.4"
    assert mysql["env_file"] == ["../.env"]
    assert mysql["environment"] == {
        "MYSQL_ROOT_PASSWORD": "${SANDBOX_MYSQL_ROOT_PASSWORD}",
        "MYSQL_DATABASE": "shuqi_sandbox",
    }
    assert mysql["ports"] == ["127.0.0.1:${SANDBOX_MYSQL_PORT:-3307}:3306"]
    assert mysql["volumes"] == [
        "mysql-sandbox-data:/var/lib/mysql",
        "./mysql/init:/docker-entrypoint-initdb.d:ro",
    ]
    assert mysql["healthcheck"] == {
        "test": [
            "CMD-SHELL",
            "mysqladmin ping -h 127.0.0.1 -uroot -p$${MYSQL_ROOT_PASSWORD} --silent",
        ],
        "interval": "5s",
        "timeout": "5s",
        "retries": 24,
        "start_period": "20s",
    }
    assert mysql["networks"] == ["dev-net", "sandbox-net"]
    assert mysql["restart"] == "unless-stopped"


def assert_devcontainer_security_contract(devcontainer: dict) -> None:
    """Reject Dev Container options that bypass the Compose service contract."""
    assert set(devcontainer) == {
        "name",
        "dockerComposeFile",
        "service",
        "workspaceFolder",
        "shutdownAction",
        "runServices",
        "remoteUser",
        "customizations",
        "postCreateCommand",
    }
    assert devcontainer == {
        "name": "数据库安全运维教学智能体",
        "dockerComposeFile": "../infra/compose.yaml",
        "service": "workspace",
        "workspaceFolder": AGENT_CONTAINER_PATH,
        "shutdownAction": "none",
        "runServices": ["mysql-sandbox", "workspace"],
        "remoteUser": "vscode",
        "customizations": {
            "vscode": {
                "settings": {"git.openRepositoryInParentFolders": "always"},
                "extensions": [
                    "ms-azuretools.vscode-docker",
                    "ms-python.python",
                    "ms-python.vscode-pylance",
                    "Vue.volar",
                ],
            }
        },
        "postCreateCommand": "python --version && node --version && pytest --version",
    }


def assert_safe_directory_contract(dockerfile: str) -> None:
    """Allow only the reviewed instructions and shell-token-normalized trust command."""
    logical_lines: list[str] = []
    current = ""
    for raw_line in dockerfile.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        current = f"{current} {stripped}".strip()
        if current.endswith("\\"):
            current = current[:-1].rstrip()
            continue
        logical_lines.append(current)
        current = ""
    assert not current

    instructions = [line.split(maxsplit=1) for line in logical_lines]
    assert [parts[0].upper() for parts in instructions] == [
        "FROM",
        "FROM",
        "COPY",
        "RUN",
        "WORKDIR",
        "USER",
        "CMD",
    ]
    assert instructions[0][1] == "node:24-bookworm-slim AS node_runtime"
    assert instructions[1][1] == "python:3.13-slim-bookworm"
    assert instructions[2][1] == "--from=node_runtime /usr/local/ /usr/local/"
    assert shlex.split(instructions[3][1], posix=True) == [
        "apt-get",
        "update",
        "&&",
        "apt-get",
        "install",
        "-y",
        "--no-install-recommends",
        "default-mysql-client",
        "git",
        "curl",
        "ca-certificates",
        "&&",
        "rm",
        "-rf",
        "/var/lib/apt/lists/*",
        "&&",
        "git",
        "config",
        "--system",
        "--add",
        "safe.directory",
        "/workspace",
        "&&",
        "useradd",
        "--create-home",
        "--shell",
        "/bin/bash",
        "vscode",
        "&&",
        "pip",
        "install",
        "--no-cache-dir",
        "pytest==9.1.1",
        "PyYAML==6.0.3",
        "PyMySQL==1.2.0",
    ]
    assert instructions[4][1] == "/workspace"
    assert instructions[5][1] == "vscode"
    assert json.loads(instructions[6][1]) == ["sleep", "infinity"]


def test_services_image_and_local_port() -> None:
    compose = load_compose()
    assert set(compose) == {"name", "services", "networks", "volumes"}
    assert compose["name"] == "shuqi-db-agent"
    assert compose["networks"] == {
        "dev-net": {"name": "shuqi-dev-net"},
        "sandbox-net": {"name": "shuqi-sandbox-net", "internal": True},
    }
    assert compose["volumes"] == {
        "mysql-sandbox-data": {"name": "shuqi-db-agent-mysql-data"}
    }
    services = compose["services"]
    assert set(services) == {"workspace", "mysql-sandbox"}
    mysql = services["mysql-sandbox"]
    assert_mysql_security_contract(mysql)
    assert mysql["image"] == "mysql:8.4"
    assert mysql["ports"] == [
        "127.0.0.1:${SANDBOX_MYSQL_PORT:-3307}:3306"
    ]
    assert mysql.get("privileged") is not True
    workspace = services["workspace"]
    assert_workspace_security_contract(workspace)
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
    devcontainer = load_devcontainer()
    assert_devcontainer_security_contract(devcontainer)
    assert devcontainer["shutdownAction"] == "none"


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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("extends", {"file": "host.yaml", "service": "workspace"}),
        ("volumes_from", ["host-controller"]),
        ("pid", "host"),
        ("ipc", "host"),
        ("network_mode", "host"),
    ],
)
def test_workspace_security_contract_rejects_inherited_and_host_namespace_variants(
    field: str,
    value: object,
) -> None:
    workspace = deepcopy(load_compose()["services"]["workspace"])
    workspace[field] = value
    with pytest.raises(AssertionError):
        assert_workspace_security_contract(workspace)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("extends", {"file": "host.yaml", "service": "mysql"}),
        ("volumes_from", ["host-controller"]),
        ("privileged", True),
        ("devices", ["/dev/sda:/dev/sda"]),
        ("cap_add", ["SYS_ADMIN"]),
        ("pid", "host"),
        ("network_mode", "host"),
        ("volumes", ["/var/lib/mysql:/var/lib/mysql"]),
        ("ports", ["0.0.0.0:3307:3306"]),
    ],
)
def test_mysql_security_contract_rejects_unexpected_service_variants(
    field: str,
    value: object,
) -> None:
    mysql = deepcopy(load_compose()["services"]["mysql-sandbox"])
    mysql[field] = value
    with pytest.raises(AssertionError):
        assert_mysql_security_contract(mysql)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mounts", ["source=/var/run/docker.sock,target=/var/run/docker.sock,type=bind"]),
        ("runArgs", ["--privileged"]),
        ("containerEnv", {"DOCKER_HOST": "unix:///var/run/docker.sock"}),
        ("hostRequirements", {"gpu": "optional"}),
        ("workspaceMount", "source=/,target=/host,type=bind"),
    ],
)
def test_devcontainer_security_contract_rejects_bypass_variants(
    field: str,
    value: object,
) -> None:
    devcontainer = deepcopy(load_devcontainer())
    devcontainer[field] = value
    with pytest.raises(AssertionError):
        assert_devcontainer_security_contract(devcontainer)


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


def test_running_container_effective_system_git_trust_is_exact() -> None:
    if not Path("/.dockerenv").exists():
        pytest.skip("effective system Git config is verified inside shuqi-workspace")
    result = subprocess.run(
        [
            "git",
            "config",
            "--system",
            "--show-origin",
            "--get-all",
            "safe.directory",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["file:/etc/gitconfig\t/workspace"]


@pytest.mark.parametrize(
    "injection",
    [
        "\nRUN git config --system --add safe.directory /tmp\n",
        "\nRUN git config --system --add SAFE.Directory /tmp\n",
        "\nRUN git config --system --replace-all safe.directory /tmp\n",
        "\nRUN git config --system safe.directory /tmp\n",
        "\nRUN printf '[safe]\\n directory = /tmp\\n' >> /etc/gitconfig\n",
        "\nRUN GIT_CONFIG_SYSTEM=/tmp/gitconfig git config --add safe.directory /tmp\n",
        "\nRUN git config --system --add safe.\"directory\" '*'\n",
        "\nRUN git config --system --add 'safe.'directory /tmp\n",
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
