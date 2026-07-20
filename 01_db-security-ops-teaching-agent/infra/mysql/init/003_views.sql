USE shuqi_sandbox;

CREATE OR REPLACE VIEW v_account_audit AS
SELECT
  account_name,
  source_scope,
  role_name,
  status,
  last_active_at,
  risk_level,
  risk_reason
FROM account_inventory;

CREATE OR REPLACE VIEW v_permission_audit AS
SELECT
  p.id,
  p.account_name,
  a.source_scope,
  p.object_name,
  p.privilege_name,
  p.expected_allowed,
  p.risk_level
FROM permission_snapshot AS p
JOIN account_inventory AS a
  ON a.account_name = p.account_name;

CREATE OR REPLACE VIEW v_suspicious_activity AS
SELECT
  d.id AS db_event_id,
  d.event_time,
  d.account_name,
  d.source_ip,
  d.statement_summary,
  d.affected_object,
  d.row_estimate,
  d.risk_label,
  w.id AS web_event_id,
  w.path,
  w.request_excerpt
FROM db_audit_log AS d
LEFT JOIN web_access_log AS w
  ON w.source_ip = d.source_ip
  AND ABS(TIMESTAMPDIFF(SECOND, w.event_time, d.event_time)) <= 5;

CREATE OR REPLACE VIEW v_backup_status AS
SELECT
  id,
  backup_name,
  created_at,
  size_bytes,
  checksum_value,
  checksum_valid,
  restore_ready,
  status_reason
FROM backup_catalog;
