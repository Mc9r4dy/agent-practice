from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INIT = ROOT / "infra" / "mysql" / "init"


def read(name: str) -> str:
    return (INIT / name).read_text(encoding="utf-8")


def test_schema_has_all_tables_and_utf8mb4() -> None:
    sql = read("001_schema.sql").lower()
    tables = {
        "citizen_profile",
        "service_request",
        "account_inventory",
        "permission_snapshot",
        "web_access_log",
        "db_audit_log",
        "backup_catalog",
        "scenario_event",
        "scenario_state",
    }
    assert all(f"create table if not exists {name}" in sql for name in tables)
    assert "default character set utf8mb4" in sql


def test_seed_is_repeatable_and_synthetic() -> None:
    sql = read("002_seed.sql")
    assert "SET FOREIGN_KEY_CHECKS = 0" in sql
    assert "测试用户甲" in sql
    assert "SYNTH-ID-0001" in sql
    tables = (
        "citizen_profile",
        "service_request",
        "account_inventory",
        "permission_snapshot",
        "web_access_log",
        "db_audit_log",
        "backup_catalog",
        "scenario_event",
        "scenario_state",
    )
    for table in tables:
        assert f"INSERT INTO {table}" in sql


def test_views_cover_all_teaching_dimensions() -> None:
    sql = read("003_views.sql").lower()
    views = (
        "v_account_audit",
        "v_permission_audit",
        "v_suspicious_activity",
        "v_backup_status",
    )
    for view in views:
        assert f"create or replace view {view}" in sql


def test_account_script_uses_environment_passwords_and_minimal_grants() -> None:
    shell = read("004_accounts.sh")
    assert "SANDBOX_MYSQL_READER_PASSWORD" in shell
    assert "SANDBOX_MYSQL_APP_PASSWORD" in shell
    assert "GRANT SELECT ON shuqi_sandbox.v_account_audit" in shell
    assert "GRANT UPDATE ON shuqi_sandbox.scenario_state" in shell
    assert "GRANT ALL" not in shell.upper()
    assert "mysql.user" not in shell
    assert '-p"${MYSQL_ROOT_PASSWORD}"' not in shell
    assert 'MYSQL_PWD="${MYSQL_ROOT_PASSWORD}"' in shell
