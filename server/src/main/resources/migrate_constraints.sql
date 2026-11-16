-- migrate_constraints.sql
-- Run LAST, after data.sql has filled the lessons table.

-- Remove any duplicate point awards before adding the uniqueness rules
-- (keeps the earliest row for each report / each user+lesson).
DELETE p1 FROM point_events p1
JOIN point_events p2
  ON p1.report_id = p2.report_id AND p1.id > p2.id
WHERE p1.report_id IS NOT NULL;

DELETE p1 FROM point_events p1
JOIN point_events p2
  ON p1.user_id = p2.user_id AND p1.lesson_id = p2.lesson_id AND p1.id > p2.id
WHERE p1.lesson_id IS NOT NULL;

ALTER TABLE point_events
    ADD UNIQUE KEY uq_points_report (report_id),
    ADD UNIQUE KEY uq_points_lesson (user_id, lesson_id),
    ADD CONSTRAINT fk_points_lesson FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE SET NULL;

ALTER TABLE quiz_passes
    ADD CONSTRAINT fk_quiz_lesson FOREIGN KEY (lesson_index) REFERENCES lessons(id) ON DELETE CASCADE;