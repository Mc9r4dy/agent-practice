#!/usr/bin/env bash
set -euo pipefail

: "${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD is required}"
: "${SANDBOX_MYSQL_READER_PASSWORD:?SANDBOX_MYSQL_READER_PASSWORD is required}"
: "${SANDBOX_MYSQL_APP_PASSWORD:?SANDBOX_MYSQL_APP_PASSWORD is required}"

MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" mysql --protocol=socket -uroot <<SQL
CREATE USER IF NOT EXISTS 'sandbox_reader'@'%' IDENTIFIED BY '${SANDBOX_MYSQL_READER_PASSWORD}';
CREATE USER IF NOT EXISTS 'sandbox_app'@'%' IDENTIFIED BY '${SANDBOX_MYSQL_APP_PASSWORD}';
GRANT SELECT ON shuqi_sandbox.v_account_audit TO 'sandbox_reader'@'%';
GRANT SELECT ON shuqi_sandbox.v_permission_audit TO 'sandbox_reader'@'%';
GRANT SELECT ON shuqi_sandbox.v_suspicious_activity TO 'sandbox_reader'@'%';
GRANT SELECT ON shuqi_sandbox.v_backup_status TO 'sandbox_reader'@'%';
GRANT SELECT ON shuqi_sandbox.* TO 'sandbox_app'@'%';
GRANT UPDATE ON shuqi_sandbox.scenario_state TO 'sandbox_app'@'%';
FLUSH PRIVILEGES;
SQL
