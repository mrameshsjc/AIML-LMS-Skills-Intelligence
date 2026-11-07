-- =============================================================================
-- Migration 0001: create the 11 LMS tables (Phase 9)
--
-- One table per CSV file, with the same name (without .csv) and the same
-- columns. The rules from app/data_processing/schemas.py are repeated here as
-- database CONSTRAINTS, so the database itself refuses bad rows:
--   PRIMARY KEY   identifies a row; no duplicates
--   FOREIGN KEY   must point to an existing row in another table
--   UNIQUE        no two rows with the same value (e.g. email)
--   CHECK         allowed values and ranges (levels 1-5, statuses, ...)
--   NOT NULL      the value may not be empty
--
-- STRICT tables (SQLite 3.37+) refuse a value of the wrong type, e.g. the text
-- 'four' in an INTEGER column. Without STRICT, SQLite would quietly store it.
--
-- Types: TEXT, INTEGER, REAL. Dates are TEXT in ISO format (YYYY-MM-DD), which
-- sorts correctly. Booleans are INTEGER 0/1.
--
-- Never edit a migration that has already run somewhere: add 0002_... instead.
-- =============================================================================

CREATE TABLE skills (
    skill_id     TEXT PRIMARY KEY CHECK (skill_id GLOB 'SK[0-9][0-9][0-9]'),
    skill_name   TEXT NOT NULL UNIQUE,
    category     TEXT NOT NULL,
    description  TEXT NOT NULL
) STRICT;

CREATE TABLE skill_proficiency (
    level        INTEGER PRIMARY KEY CHECK (level BETWEEN 1 AND 5),
    label        TEXT NOT NULL,
    description  TEXT NOT NULL
) STRICT;

CREATE TABLE job_roles (
    role_id      TEXT PRIMARY KEY CHECK (role_id GLOB 'R[0-9][0-9][0-9]'),
    role_title   TEXT NOT NULL UNIQUE,
    department   TEXT NOT NULL,
    job_family   TEXT NOT NULL,
    seniority    TEXT NOT NULL CHECK (seniority IN ('Junior', 'Mid', 'Senior')),
    description  TEXT NOT NULL
) STRICT;

CREATE TABLE role_required_skills (
    role_id            TEXT NOT NULL REFERENCES job_roles (role_id),
    skill_id           TEXT NOT NULL REFERENCES skills (skill_id),
    required_level     INTEGER NOT NULL CHECK (required_level BETWEEN 1 AND 5),
    importance_weight  REAL NOT NULL CHECK (importance_weight BETWEEN 0 AND 10),
    is_mandatory       INTEGER NOT NULL CHECK (is_mandatory IN (0, 1)),
    PRIMARY KEY (role_id, skill_id)
) STRICT;

CREATE TABLE courses (
    course_id       TEXT PRIMARY KEY CHECK (course_id GLOB 'C-*-[0-9][0-9][0-9]'),
    course_title    TEXT NOT NULL,
    description     TEXT NOT NULL,
    difficulty      TEXT NOT NULL CHECK (difficulty IN ('Beginner', 'Intermediate', 'Advanced')),
    duration_hours  INTEGER NOT NULL CHECK (duration_hours BETWEEN 1 AND 200),
    delivery_mode   TEXT NOT NULL CHECK (delivery_mode IN ('Online', 'Blended', 'Classroom')),
    provider        TEXT NOT NULL,
    is_active       INTEGER NOT NULL CHECK (is_active IN (0, 1))
) STRICT;

CREATE TABLE course_skills (
    course_id   TEXT NOT NULL REFERENCES courses (course_id),
    skill_id    TEXT NOT NULL REFERENCES skills (skill_id),
    level_from  INTEGER NOT NULL CHECK (level_from BETWEEN 0 AND 4),
    level_to    INTEGER NOT NULL CHECK (level_to BETWEEN 1 AND 5),
    PRIMARY KEY (course_id, skill_id),
    CHECK (level_to > level_from)
) STRICT;

CREATE TABLE course_prerequisites (
    course_id               TEXT NOT NULL REFERENCES courses (course_id),
    prerequisite_course_id  TEXT NOT NULL REFERENCES courses (course_id),
    PRIMARY KEY (course_id, prerequisite_course_id),
    CHECK (course_id <> prerequisite_course_id)
) STRICT;

CREATE TABLE employees (
    employee_id        TEXT PRIMARY KEY CHECK (employee_id GLOB 'E[0-9][0-9][0-9][0-9]'),
    first_name         TEXT NOT NULL,
    last_name          TEXT NOT NULL,
    email              TEXT NOT NULL UNIQUE CHECK (email LIKE '%_@_%._%'),
    department         TEXT NOT NULL,
    current_role_id    TEXT NOT NULL REFERENCES job_roles (role_id),
    manager_id         TEXT REFERENCES employees (employee_id),   -- may be empty (top managers)
    hire_date          TEXT NOT NULL,
    location           TEXT NOT NULL,
    employment_status  TEXT NOT NULL CHECK (employment_status IN ('Active', 'Inactive'))
) STRICT;

CREATE TABLE employee_skills (
    employee_id    TEXT NOT NULL REFERENCES employees (employee_id),
    skill_id       TEXT NOT NULL REFERENCES skills (skill_id),
    current_level  INTEGER NOT NULL CHECK (current_level BETWEEN 1 AND 5),
    source         TEXT NOT NULL CHECK (source IN ('self', 'manager', 'assessment')),
    assessed_date  TEXT NOT NULL,
    PRIMARY KEY (employee_id, skill_id)
) STRICT;

CREATE TABLE career_goals (
    employee_id     TEXT PRIMARY KEY REFERENCES employees (employee_id),
    target_role_id  TEXT NOT NULL REFERENCES job_roles (role_id),
    set_date        TEXT NOT NULL,
    goal_status     TEXT NOT NULL CHECK (goal_status IN ('Active', 'Achieved', 'Withdrawn'))
) STRICT;

CREATE TABLE training_history (
    enrollment_id   TEXT PRIMARY KEY CHECK (enrollment_id GLOB 'EN[0-9][0-9][0-9][0-9]*'),
    employee_id     TEXT NOT NULL REFERENCES employees (employee_id),
    course_id       TEXT NOT NULL REFERENCES courses (course_id),
    status          TEXT NOT NULL CHECK (status IN ('Enrolled', 'In Progress', 'Completed', 'Dropped')),
    enrolled_date   TEXT NOT NULL,
    completed_date  TEXT,                                          -- only when Completed
    score           INTEGER CHECK (score BETWEEN 0 AND 100),       -- may be empty
    attempts        INTEGER NOT NULL CHECK (attempts BETWEEN 1 AND 5)
) STRICT;

-- Indexes make "find all rows for X" fast without scanning the whole table.
-- A primary key is already indexed by its FIRST column, so we only add
-- indexes for columns that are searched on their own.
CREATE INDEX ix_role_required_skills_skill ON role_required_skills (skill_id);
CREATE INDEX ix_course_skills_skill        ON course_skills (skill_id);
CREATE INDEX ix_employees_role             ON employees (current_role_id);
CREATE INDEX ix_employee_skills_skill      ON employee_skills (skill_id);
CREATE INDEX ix_training_history_employee  ON training_history (employee_id);
CREATE INDEX ix_training_history_course    ON training_history (course_id);
