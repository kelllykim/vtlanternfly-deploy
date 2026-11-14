-- data.sql
-- VT LanternFly starting data. Run after schema.sql.

-- ---------------------------------------------------------------------------
-- Learn quizzes (ids match the frontend's lesson index: 0, 1, 2)
-- ---------------------------------------------------------------------------
INSERT IGNORE INTO lessons (id, title, points) VALUES
    (0, 'Life Stages',             10),
    (1, 'Host Trees',              10),
    (2, 'Look-alikes and Impact',  10);

-- ---------------------------------------------------------------------------
-- Badges
-- ---------------------------------------------------------------------------
INSERT IGNORE INTO badges (name, description, icon, sort_order) VALUES
    ('First Squash',      'Your first verified report.',                                        'bug',     1),
    ('Lanternfly Hunter', '10 verified reports.',                                               'target',  2),
    ('Pest Patrol',       '25 verified reports.',                                               'shield',  3),
    ('Campus Defender',   '50 verified reports.',                                               'trophy',  4),
    ('Egg Hunter',        'Your first verified egg mass.',                                      'egg',     5),
    ('Nymph Spotter',     'Your first verified nymph (black or red).',                          'bug',     6),
    ('Full Life Cycle',   'Verified reports of all four stages: egg mass, black nymph, red nymph and adult.', 'cycle', 7),
    ('Field Expert',      'Pass all three Learn quizzes.',                                      'book',    8),
    ('Recruiter',         'A friend joined through your invite.',                               'users',   9);

-- ---------------------------------------------------------------------------
-- Shared goals
-- ---------------------------------------------------------------------------
INSERT IGNORE INTO goals (scope, title, metric, target, starts_on, ends_on, is_active) VALUES
    ('campus', '100 verified campus reports before December', 'verified_reports', 100, NULL, '2026-11-30', TRUE),
    ('team',   '50 egg masses before December',               'egg_masses',        50, NULL, '2026-11-30', TRUE);

-- Two-week launch challenge from the draft report. Set the real dates and
-- change is_active to TRUE when it starts.
INSERT IGNORE INTO goals (scope, title, metric, target, starts_on, ends_on, is_active) VALUES
    ('challenge', 'Stomp Out Lanternflies', 'verified_reports', 50, NULL, NULL, FALSE);

-- ---------------------------------------------------------------------------
-- Weekly personal goals
-- ---------------------------------------------------------------------------
INSERT IGNORE INTO personal_goal_types (goal_key, title, metric, target, sort_order) VALUES
    ('report_3',   'Report 3 verified lanternflies this week', 'verified_reports', 3, 1),
    ('egg_mass_1', 'Find and scrape 1 egg mass',              'egg_masses',       1, 2),
    ('quiz_1',     'Complete a Learn quiz',                   'quizzes',          1, 3),
    ('invite_1',   'Invite 1 friend',                         'invites',          1, 4);