-- ============================================================
-- QuantAI AI — MySQL Initialization Script
-- Run as root:  mysql -u root -p < scripts/mysql_init.sql
-- ============================================================

-- Create schemas
CREATE DATABASE IF NOT EXISTS `quantai_data`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS `quantai_app`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ── User 1: quantai_readonly ─────────────────────────────────────────────────
-- SELECT only on quantai_data. Used for ALL generated SQL queries.
CREATE USER IF NOT EXISTS 'quantai_readonly'@'%'
  IDENTIFIED BY 'YourPassword';
GRANT SELECT ON `quantai_data`.* TO 'quantai_readonly'@'%';

-- Also allow SELECT on quantai_app for history lookups from readonly contexts
GRANT SELECT ON `quantai_app`.* TO 'quantai_readonly'@'%';

-- ── User 2: quantai_import ───────────────────────────────────────────────────
-- CREATE/INSERT/DROP/ALTER/INDEX on quantai_data only. Used only by upload pipeline.
CREATE USER IF NOT EXISTS 'quantai_import'@'%'
  IDENTIFIED BY 'YourPassword';
GRANT CREATE, INSERT, DROP, ALTER, INDEX, SELECT ON `quantai_data`.* TO 'quantai_import'@'%';

-- ── User 3: quantai_app ──────────────────────────────────────────────────────
-- Read/write on quantai_app only. Used for metadata, history, settings.
CREATE USER IF NOT EXISTS 'quantai_app'@'%'
  IDENTIFIED BY 'YourPassword';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, REFERENCES ON `quantai_app`.* TO 'quantai_app'@'%';

FLUSH PRIVILEGES;

-- ── MySQL mode settings ──────────────────────────────────────────────────────
-- Ensure strict mode and ONLY_FULL_GROUP_BY are enabled (best practice for 8.0)
-- These are defaults in MySQL 8.0 but explicitly noted here.

SELECT 'MySQL initialization complete. Schemas: quantai_data, quantai_app. Users: quantai_readonly, quantai_import, quantai_app' AS status;
