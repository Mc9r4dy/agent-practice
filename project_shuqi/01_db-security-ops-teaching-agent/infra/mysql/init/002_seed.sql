USE shuqi_sandbox;

SET FOREIGN_KEY_CHECKS = 0;
DELETE FROM scenario_event;
DELETE FROM backup_catalog;
DELETE FROM db_audit_log;
DELETE FROM web_access_log;
DELETE FROM permission_snapshot;
DELETE FROM account_inventory;
DELETE FROM service_request;
DELETE FROM citizen_profile;
DELETE FROM scenario_state;
SET FOREIGN_KEY_CHECKS = 1;

INSERT INTO citizen_profile VALUES
  (1, 'SYNTH-BIZ-0001', '测试用户甲', 'SYNTH-ID-0001', '18800000001', '2026-07-01 09:00:00'),
  (2, 'SYNTH-BIZ-0002', '测试用户乙', 'SYNTH-ID-0002', '18800000002', '2026-07-01 09:05:00'),
  (3, 'SYNTH-BIZ-0003', '测试用户丙', 'SYNTH-ID-0003', '18800000003', '2026-07-01 09:10:00'),
  (4, 'SYNTH-BIZ-0004', '测试用户丁', 'SYNTH-ID-0004', '18800000004', '2026-07-01 09:15:00');

INSERT INTO service_request VALUES
  (101, 1, '社保查询', 'COMPLETED', '2026-07-10 10:00:00'),
  (102, 2, '证照办理', 'PROCESSING', '2026-07-10 10:10:00'),
  (103, 3, '公积金查询', 'COMPLETED', '2026-07-10 10:20:00'),
  (104, 4, '信息变更', 'PROCESSING', '2026-07-10 10:30:00'),
  (105, 1, '办件评价', 'COMPLETED', '2026-07-10 10:40:00');

INSERT INTO account_inventory VALUES
  ('svc_portal', '10.10.20.%', 'application', 'ACTIVE', '2026-07-16 23:45:00', 'HIGH', '业务账号权限超过职责范围'),
  ('report_reader', '10.10.30.15', 'reporting', 'ACTIVE', '2026-07-16 17:20:00', 'LOW', '来源和权限符合基线'),
  ('temp_dba', '%', 'administrator', 'ACTIVE', '2026-07-17 02:13:00', 'CRITICAL', '来源范围过宽且为新增高权限账号'),
  ('legacy_user', '10.10.40.%', 'legacy', 'ACTIVE', '2025-12-01 08:00:00', 'MEDIUM', '长期未使用仍启用');

INSERT INTO permission_snapshot VALUES
  (201, 'svc_portal', 'shuqi_sandbox.citizen_profile', 'SELECT', 1, 'LOW'),
  (202, 'svc_portal', 'shuqi_sandbox.permission_snapshot', 'UPDATE', 0, 'HIGH'),
  (203, 'report_reader', 'shuqi_sandbox.v_backup_status', 'SELECT', 1, 'LOW'),
  (204, 'temp_dba', '*.*', 'ALL PRIVILEGES', 0, 'CRITICAL'),
  (205, 'legacy_user', 'shuqi_sandbox.*', 'SELECT', 0, 'MEDIUM');

INSERT INTO web_access_log VALUES
  (301, '2026-07-17 02:10:01', '198.51.100.23', '/api/search', '[模拟异常参数，已脱敏，不可执行]', 500, 'SQL_INJECTION_TRACE'),
  (302, '2026-07-17 02:10:03', '198.51.100.23', '/api/search', '[重复异常请求，已脱敏]', 500, 'SQL_INJECTION_TRACE'),
  (303, '2026-07-17 02:11:30', '203.0.113.8', '/login', 'account=temp_dba', 200, 'UNUSUAL_LOGIN'),
  (304, '2026-07-17 09:00:00', '192.0.2.10', '/health', 'normal health check', 200, 'NORMAL');

INSERT INTO db_audit_log VALUES
  (401, '2026-07-17 02:10:02', 'svc_portal', '198.51.100.23', '异常条件查询摘要（不可执行）', 'citizen_profile', 4, 'SUSPICIOUS_QUERY'),
  (402, '2026-07-17 02:12:00', 'svc_portal', '198.51.100.23', '非工作时段批量读取摘要', 'citizen_profile', 4000, 'BULK_READ'),
  (403, '2026-07-17 02:13:00', 'temp_dba', '203.0.113.8', '权限盘点事件摘要', 'permission_snapshot', 5, 'PRIVILEGED_ACCESS'),
  (404, '2026-07-17 09:05:00', 'report_reader', '10.10.30.15', '备份状态只读查询', 'backup_catalog', 3, 'NORMAL');

INSERT INTO backup_catalog VALUES
  (501, 'full_20260715.sql.gz', '2026-07-15 01:00:00', 1048576, 'SYNTH-CHECKSUM-OK-001', 1, 1, '校验通过'),
  (502, 'full_20260716.sql.gz', '2026-07-16 01:00:00', 1048600, 'SYNTH-CHECKSUM-BAD-002', 0, 0, '校验值不一致'),
  (503, 'full_20260717.sql.gz', '2026-07-17 01:00:00', 0, 'SYNTH-CHECKSUM-MISSING-003', 0, 0, '备份任务失败');

INSERT INTO scenario_event VALUES
  ('EVT-001', '2026-07-17 02:10:01', '入口迹象', 'WEB_LOG', '301', '发现模拟异常请求', '关联数据库审计事件', 'HIGH'),
  ('EVT-002', '2026-07-17 02:10:02', '异常查询', 'DB_LOG', '401', '识别可疑查询摘要', '检查应用账号权限', 'HIGH'),
  ('EVT-003', '2026-07-17 02:12:00', '批量访问', 'DB_LOG', '402', '识别批量读取', '限制账号并保存证据', 'CRITICAL'),
  ('EVT-004', '2026-07-17 02:13:00', '异常账号', 'ACCOUNT', 'temp_dba', '识别异常高权限账号', '锁定教学账号快照', 'CRITICAL'),
  ('EVT-005', '2026-07-17 02:20:00', '备份异常', 'BACKUP', '503', '识别最新备份不可用', '选择有效备份验证', 'HIGH'),
  ('EVT-006', '2026-07-17 02:30:00', '处置闭环', 'STATE', 'SCN-DB-001', '完成证据汇总', '生成教学处置报告', 'MEDIUM');

INSERT INTO scenario_state VALUES
  ('SCN-DB-001', '1.0.0', 'INITIALIZED', 'STANDARD-RESET-001', '2026-07-17 00:00:00');
