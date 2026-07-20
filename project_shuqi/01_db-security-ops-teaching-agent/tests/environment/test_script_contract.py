from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "sandbox.ps1"


def test_script_actions_and_fixed_targets() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for action in (
        "Preflight",
        "Start",
        "Status",
        "Logs",
        "Test",
        "QuickReset",
        "Rebuild",
        "Stop",
    ):
        assert action in text
    assert "$ProjectName = 'shuqi-db-agent'" in text
    assert "$MysqlContainer = 'shuqi-mysql-sandbox'" in text
    assert "$MysqlVolume = 'shuqi-db-agent-mysql-data'" in text
    assert "E:\\MySql" in text


def test_script_has_no_global_cleanup() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()
    assert "docker system prune" not in text
    assert "docker volume prune" not in text
    assert "docker container prune" not in text


def test_quick_reset_does_not_put_password_on_command_line() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '-p"$MYSQL_ROOT_PASSWORD"' not in text
    assert 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD"' in text
