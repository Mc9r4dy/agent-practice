CREATE DATABASE IF NOT EXISTS shuqi_sandbox
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE shuqi_sandbox;

CREATE TABLE IF NOT EXISTS citizen_profile (
  id BIGINT PRIMARY KEY,
  business_code VARCHAR(32) NOT NULL UNIQUE,
  full_name VARCHAR(64) NOT NULL,
  id_token VARCHAR(32) NOT NULL,
  phone VARCHAR(32) NOT NULL,
  created_at DATETIME NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS service_request (
  id BIGINT PRIMARY KEY,
  citizen_id BIGINT NOT NULL,
  request_type VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL,
  submitted_at DATETIME NOT NULL,
  CONSTRAINT fk_request_citizen
    FOREIGN KEY (citizen_id) REFERENCES citizen_profile(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS account_inventory (
  account_name VARCHAR(64) PRIMARY KEY,
  source_scope VARCHAR(128) NOT NULL,
  role_name VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL,
  last_active_at DATETIME NULL,
  risk_level VARCHAR(16) NOT NULL,
  risk_reason VARCHAR(255) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS permission_snapshot (
  id BIGINT PRIMARY KEY,
  account_name VARCHAR(64) NOT NULL,
  object_name VARCHAR(128) NOT NULL,
  privilege_name VARCHAR(64) NOT NULL,
  expected_allowed TINYINT(1) NOT NULL,
  risk_level VARCHAR(16) NOT NULL,
  CONSTRAINT fk_permission_account
    FOREIGN KEY (account_name) REFERENCES account_inventory(account_name)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS web_access_log (
  id BIGINT PRIMARY KEY,
  event_time DATETIME NOT NULL,
  source_ip VARCHAR(45) NOT NULL,
  path VARCHAR(255) NOT NULL,
  request_excerpt VARCHAR(500) NOT NULL,
  response_status INT NOT NULL,
  risk_label VARCHAR(64) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS db_audit_log (
  id BIGINT PRIMARY KEY,
  event_time DATETIME NOT NULL,
  account_name VARCHAR(64) NOT NULL,
  source_ip VARCHAR(45) NOT NULL,
  statement_summary VARCHAR(500) NOT NULL,
  affected_object VARCHAR(128) NOT NULL,
  row_estimate INT NOT NULL,
  risk_label VARCHAR(64) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS backup_catalog (
  id BIGINT PRIMARY KEY,
  backup_name VARCHAR(128) NOT NULL UNIQUE,
  created_at DATETIME NOT NULL,
  size_bytes BIGINT NOT NULL,
  checksum_value VARCHAR(128) NOT NULL,
  checksum_valid TINYINT(1) NOT NULL,
  restore_ready TINYINT(1) NOT NULL,
  status_reason VARCHAR(255) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS scenario_event (
  event_id VARCHAR(32) PRIMARY KEY,
  event_time DATETIME NOT NULL,
  stage_name VARCHAR(64) NOT NULL,
  evidence_type VARCHAR(64) NOT NULL,
  evidence_key VARCHAR(128) NOT NULL,
  expected_finding VARCHAR(255) NOT NULL,
  expected_action VARCHAR(255) NOT NULL,
  severity VARCHAR(16) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS scenario_state (
  scenario_id VARCHAR(32) PRIMARY KEY,
  scenario_version VARCHAR(16) NOT NULL,
  state_name VARCHAR(32) NOT NULL,
  reset_marker VARCHAR(64) NOT NULL,
  updated_at DATETIME NOT NULL
) ENGINE=InnoDB;
