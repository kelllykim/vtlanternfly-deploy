-- migrate.sql
-- Upgrades a database built from the OLD schema.sql to the new one,
-- keeping existing users, reports and points.
-- Run once, in this order:  migrate.sql  ->  schema.sql  ->  data.sql  ->  migrate_constraints.sql

-- users: recruiting columns
ALTER TABLE users
    ADD COLUMN invite_code VARCHAR(16) NULL UNIQUE AFTER is_admin,
    ADD COLUMN invited_by  INT NULL AFTER invite_code,
    ADD CONSTRAINT fk_users_invited_by FOREIGN KEY (invited_by) REFERENCES users(id) ON DELETE SET NULL,
    ADD INDEX idx_users_major (major);

-- reports: manual review and simulated-data columns
ALTER TABLE reports
    ADD COLUMN reviewed_by  INT NULL AFTER review_status,
    ADD COLUMN reviewed_at  TIMESTAMP NULL AFTER reviewed_by,
    ADD COLUMN review_note  VARCHAR(255) NULL AFTER reviewed_at,
    ADD COLUMN is_simulated BOOLEAN NOT NULL DEFAULT FALSE AFTER review_note,
    ADD CONSTRAINT fk_reports_reviewer FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE SET NULL,
    ADD INDEX idx_reports_user_status (user_id, review_status),
    ADD INDEX idx_reports_status_stage (review_status, life_stage_verified),
    ADD INDEX idx_reports_created (created_at);

-- badges: display order
ALTER TABLE badges
    ADD COLUMN sort_order INT NOT NULL DEFAULT 0;