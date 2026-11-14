-- schema.sql
-- VT LanternFly database schema (MySQL 8)
--
-- Run against an empty database (on Railway the database is named `railway`):
--   mysql -h <HOST> -P <PORT> -u root -p railway -e "source schema.sql"
-- then run data.sql for the starting data.
--
-- Column names in the original six tables (users, reports, point_events,
-- badges, user_badges, quiz_passes) are unchanged, so the current backend keeps
-- working. Keep backend/db_models.py in sync with any change here.

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------------
-- Users and login
-- ---------------------------------------------------------------------------

-- One row per student account.
CREATE TABLE IF NOT EXISTS users (
                                     id                     INT AUTO_INCREMENT PRIMARY KEY,
                                     email                  VARCHAR(255) NOT NULL UNIQUE,
    password_hash          VARCHAR(255) NOT NULL,          -- bcrypt hash, never the password
    display_name           VARCHAR(100) NOT NULL,
    major                  VARCHAR(100),                   -- used by the Majors leaderboard
    anonymous              BOOLEAN NOT NULL DEFAULT FALSE, -- shows as "Anonymous Hokie" on leaderboards
    share_with_researchers BOOLEAN NOT NULL DEFAULT TRUE,  -- include this user's sightings in the research export
    is_admin               BOOLEAN NOT NULL DEFAULT FALSE, -- can review pending reports
    invite_code            VARCHAR(16) UNIQUE,             -- code this user shares to recruit friends
    invited_by             INT NULL,                       -- who recruited this user (Recruiter badge)
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_users_invited_by FOREIGN KEY (invited_by) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_users_major (major)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Login sessions. Store only a hash of the token.
CREATE TABLE IF NOT EXISTS user_sessions (
                                             id          INT AUTO_INCREMENT PRIMARY KEY,
                                             user_id     INT NOT NULL,
                                             token_hash  CHAR(64) NOT NULL UNIQUE,                   -- SHA-256 of the session token
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at  TIMESTAMP NOT NULL,
    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_sessions_user (user_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- Sightings
-- ---------------------------------------------------------------------------

-- One row per uploaded photo.
CREATE TABLE IF NOT EXISTS reports (
                                       id                  INT AUTO_INCREMENT PRIMARY KEY,
                                       user_id             INT NULL,                          -- kept as NULL if the account is deleted, so research data survives
                                       photo_hash          VARCHAR(64) NOT NULL UNIQUE,       -- SHA-256 of the photo; blocks duplicate uploads
    stored_name         VARCHAR(255) NOT NULL,             -- file name in the uploads folder
    lat                 DECIMAL(10, 8),
    lng                 DECIMAL(11, 8),
    captured_at         TIMESTAMP NULL,                    -- from photo EXIF
    location_source     VARCHAR(50),                       -- 'exif', 'browser', ...
    life_stage_claimed  VARCHAR(50),                       -- stage the user selected (for the +5 bonus)
    life_stage_verified VARCHAR(50),                       -- stage confirmed by the model or a reviewer
    detection_status    VARCHAR(50),                       -- 'detected', 'not_detected', 'unavailable'
    model_confidence    DECIMAL(5, 4),
    bbox                JSON,                              -- model bounding boxes
    review_status       ENUM('pending', 'approved', 'rejected') NOT NULL DEFAULT 'pending',
    reviewed_by         INT NULL,                          -- admin who approved/rejected it (NULL = automatic)
    reviewed_at         TIMESTAMP NULL,
    review_note         VARCHAR(255),
    is_simulated        BOOLEAN NOT NULL DEFAULT FALSE,    -- printed-image test sightings; never sent to researchers
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_reports_user     FOREIGN KEY (user_id)     REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT fk_reports_reviewer FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_reports_user_status (user_id, review_status),
    INDEX idx_reports_status_stage (review_status, life_stage_verified),
    INDEX idx_reports_created (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- Learning
-- ---------------------------------------------------------------------------

-- The three Learn quizzes. ids match the lesson index used by the frontend (0, 1, 2).
CREATE TABLE IF NOT EXISTS lessons (
                                       id     INT PRIMARY KEY,
                                       title  VARCHAR(100) NOT NULL,
    points INT NOT NULL DEFAULT 10
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Which user passed which quiz (once each).
CREATE TABLE IF NOT EXISTS quiz_passes (
                                           user_id      INT NOT NULL,
                                           lesson_index INT NOT NULL,
                                           passed_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                                           PRIMARY KEY (user_id, lesson_index),
    CONSTRAINT fk_quiz_user   FOREIGN KEY (user_id)      REFERENCES users(id)   ON DELETE CASCADE,
    CONSTRAINT fk_quiz_lesson FOREIGN KEY (lesson_index) REFERENCES lessons(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- Points and badges
-- ---------------------------------------------------------------------------

-- Points ledger: one row per award. A user's total is SUM(points).
CREATE TABLE IF NOT EXISTS point_events (
                                            id         INT AUTO_INCREMENT PRIMARY KEY,
                                            user_id    INT NOT NULL,
                                            report_id  INT NULL,                                   -- set for report points
                                            lesson_id  INT NULL,                                   -- set for quiz points
                                            points     INT NOT NULL,
                                            reason     VARCHAR(255) NOT NULL,                      -- e.g. 'Verified report: Egg mass'
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_points_user   FOREIGN KEY (user_id)   REFERENCES users(id)   ON DELETE CASCADE,
    CONSTRAINT fk_points_report FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE SET NULL,
    CONSTRAINT fk_points_lesson FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE SET NULL,
    UNIQUE KEY uq_points_report (report_id),               -- a report earns points only once
    UNIQUE KEY uq_points_lesson (user_id, lesson_id),      -- a quiz earns points only once per user
    INDEX idx_points_user (user_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- The badge catalog (filled by data.sql).
CREATE TABLE IF NOT EXISTS badges (
                                      id          INT AUTO_INCREMENT PRIMARY KEY,
                                      name        VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    icon        VARCHAR(50),
    sort_order  INT NOT NULL DEFAULT 0
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Badges each user has earned.
CREATE TABLE IF NOT EXISTS user_badges (
                                           user_id   INT NOT NULL,
                                           badge_id  INT NOT NULL,
                                           earned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                                           PRIMARY KEY (user_id, badge_id),
    CONSTRAINT fk_ub_user  FOREIGN KEY (user_id)  REFERENCES users(id)  ON DELETE CASCADE,
    CONSTRAINT fk_ub_badge FOREIGN KEY (badge_id) REFERENCES badges(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- Social: teams and friends
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS teams (
                                     id          INT AUTO_INCREMENT PRIMARY KEY,
                                     name        VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(255),
    invite_code VARCHAR(16) NOT NULL UNIQUE,               -- shared to let others join
    created_by  INT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_teams_creator FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Each user belongs to at most one team (remove uq_team_members_user to allow several).
CREATE TABLE IF NOT EXISTS team_members (
                                            team_id   INT NOT NULL,
                                            user_id   INT NOT NULL,
                                            role      ENUM('owner', 'member') NOT NULL DEFAULT 'member',
    joined_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_id, user_id),
    UNIQUE KEY uq_team_members_user (user_id),
    CONSTRAINT fk_tm_team FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
    CONSTRAINT fk_tm_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Friend requests. A friendship exists when status = 'accepted'.
CREATE TABLE IF NOT EXISTS friendships (
                                           requester_id INT NOT NULL,
                                           addressee_id INT NOT NULL,
                                           status       ENUM('pending', 'accepted', 'declined') NOT NULL DEFAULT 'pending',
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    responded_at TIMESTAMP NULL,
    PRIMARY KEY (requester_id, addressee_id),
    CONSTRAINT chk_friend_not_self CHECK (requester_id <> addressee_id),
    CONSTRAINT fk_fr_requester FOREIGN KEY (requester_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_fr_addressee FOREIGN KEY (addressee_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_fr_addressee (addressee_id, status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- Goals and challenges
-- ---------------------------------------------------------------------------

-- Shared goals shown in the app
CREATE TABLE IF NOT EXISTS goals (
                                     id         INT AUTO_INCREMENT PRIMARY KEY,
                                     scope      ENUM('campus', 'team', 'challenge') NOT NULL,
    title      VARCHAR(150) NOT NULL UNIQUE,
    metric     ENUM('verified_reports', 'egg_masses', 'nymphs', 'adults') NOT NULL,
    target     INT NOT NULL,
    starts_on  DATE NULL,                                  -- NULL = count from the beginning
    ends_on    DATE NULL,                                  -- NULL = no deadline
    is_active  BOOLEAN NOT NULL DEFAULT TRUE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- The weekly personal goals users can pick from on the Me tab.
CREATE TABLE IF NOT EXISTS personal_goal_types (
                                                   goal_key    VARCHAR(50) PRIMARY KEY,                   -- e.g. 'report_3'
    title       VARCHAR(150) NOT NULL,
    metric      ENUM('verified_reports', 'egg_masses', 'quizzes', 'invites') NOT NULL,
    target      INT NOT NULL,
    sort_order  INT NOT NULL DEFAULT 0
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- The goal each user picked for a given week (one per week).
CREATE TABLE IF NOT EXISTS user_goals (
                                          user_id    INT NOT NULL,
                                          week_start DATE NOT NULL,                              -- Monday of that week
                                          goal_key   VARCHAR(50) NOT NULL,
    chosen_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, week_start),
    CONSTRAINT fk_ug_user FOREIGN KEY (user_id)  REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_ug_goal FOREIGN KEY (goal_key) REFERENCES personal_goal_types(goal_key)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- Views (read-only shortcuts)
-- ---------------------------------------------------------------------------

-- Points total per user, for leaderboards and rank.
CREATE OR REPLACE VIEW user_points AS
SELECT u.id AS user_id,
       u.display_name,
       u.major,
       u.anonymous,
       COALESCE(SUM(p.points), 0) AS points
FROM users u
         LEFT JOIN point_events p ON p.user_id = u.id
GROUP BY u.id, u.display_name, u.major, u.anonymous;

-- Clean dataset for researchers
CREATE OR REPLACE VIEW research_sightings AS
SELECT r.id AS report_id,
       r.lat,
       r.lng,
       r.life_stage_verified AS life_stage,
       r.captured_at,
       r.created_at AS reported_at,
       r.location_source,
       r.model_confidence
FROM reports r
         LEFT JOIN users u ON u.id = r.user_id
WHERE r.review_status = 'approved'
  AND r.is_simulated = FALSE
  AND r.lat IS NOT NULL AND r.lng IS NOT NULL
  AND (u.id IS NULL OR u.share_with_researchers = TRUE);