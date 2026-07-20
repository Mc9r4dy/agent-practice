import pymysql
import pytest


pytestmark = pytest.mark.integration


def scalar(connection, sql: str):
    with connection.cursor() as cursor:
        cursor.execute(sql)
        return cursor.fetchone()[0]


def test_reader_can_query_training_views(reader_connection) -> None:
    views = (
        "v_account_audit",
        "v_permission_audit",
        "v_suspicious_activity",
        "v_backup_status",
    )
    for view in views:
        assert scalar(reader_connection, f"SELECT COUNT(*) FROM {view}") > 0


def test_ground_truth_counts(app_connection) -> None:
    expected = {
        "citizen_profile": 4,
        "service_request": 5,
        "account_inventory": 4,
        "permission_snapshot": 5,
        "web_access_log": 4,
        "db_audit_log": 4,
        "backup_catalog": 3,
        "scenario_event": 6,
        "scenario_state": 1,
    }
    for table, count in expected.items():
        assert scalar(app_connection, f"SELECT COUNT(*) FROM {table}") == count


def test_reader_cannot_write_or_read_mysql_user(reader_connection) -> None:
    forbidden_sql = (
        "UPDATE scenario_state SET state_name='BROKEN'",
        "SELECT User, Host FROM mysql.user",
    )
    for sql in forbidden_sql:
        with pytest.raises(pymysql.MySQLError):
            with reader_connection.cursor() as cursor:
                cursor.execute(sql)


def test_app_can_update_only_scenario_state(app_connection) -> None:
    with app_connection.cursor() as cursor:
        cursor.execute(
            "UPDATE scenario_state SET state_name='TEST_MUTATION' "
            "WHERE scenario_id='SCN-DB-001'"
        )
    assert (
        scalar(
            app_connection,
            "SELECT COUNT(*) FROM scenario_state "
            "WHERE state_name='TEST_MUTATION'",
        )
        == 1
    )

    with pytest.raises(pymysql.MySQLError):
        with app_connection.cursor() as cursor:
            cursor.execute("DELETE FROM citizen_profile WHERE id=1")

    with app_connection.cursor() as cursor:
        cursor.execute(
            "UPDATE scenario_state SET state_name='INITIALIZED' "
            "WHERE scenario_id='SCN-DB-001'"
        )
