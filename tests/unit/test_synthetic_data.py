"""
Integrity tests for the synthetic LMS data in data/sample (Phase 2).

WHY THESE TESTS MATTER
    Every later phase trusts this data. If an ID points to nothing, or a
    prerequisite chain loops forever, the bugs would appear much later and be
    hard to trace. These tests catch such problems the moment the data changes.

WHAT THEY CHECK
    - all 11 files exist with the expected columns;
    - sizes are in the ranges the requirements ask for;
    - every ID is unique (primary keys);
    - every reference points to an existing row (foreign keys);
    - levels, dates and statuses follow the business rules;
    - course prerequisites contain no loops;
    - the Data Engineer example from the requirements is present exactly;
    - the committed files are exactly what the generator produces.

HOW TO RUN
    PS> pytest tests/unit/test_synthetic_data.py -v

They use only the standard `csv` module, so they run without Pandas.
"""

import csv
import importlib.util
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "data" / "sample"
AS_OF = date(2026, 10, 31)

EXPECTED_COLUMNS = {
    "skills.csv": ["skill_id", "skill_name", "category", "description"],
    "skill_proficiency.csv": ["level", "label", "description"],
    "job_roles.csv": ["role_id", "role_title", "department", "job_family", "seniority", "description"],
    "role_required_skills.csv": [
        "role_id", "skill_id", "required_level", "importance_weight", "is_mandatory",
    ],
    "courses.csv": [
        "course_id", "course_title", "description", "difficulty",
        "duration_hours", "delivery_mode", "provider", "is_active",
    ],
    "course_skills.csv": ["course_id", "skill_id", "level_from", "level_to"],
    "course_prerequisites.csv": ["course_id", "prerequisite_course_id"],
    "employees.csv": [
        "employee_id", "first_name", "last_name", "email", "department",
        "current_role_id", "manager_id", "hire_date", "location", "employment_status",
    ],
    "employee_skills.csv": ["employee_id", "skill_id", "current_level", "source", "assessed_date"],
    "career_goals.csv": ["employee_id", "target_role_id", "set_date", "goal_status"],
    "training_history.csv": [
        "enrollment_id", "employee_id", "course_id", "status",
        "enrolled_date", "completed_date", "score", "attempts",
    ],
}  # fmt: skip


def load(name: str) -> list[dict]:
    """Read one CSV file into a list of dicts (one dict per row)."""
    with open(SAMPLE / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def data() -> dict[str, list[dict]]:
    """Load all files once for the whole test module (faster than per test)."""
    return {name: load(name) for name in EXPECTED_COLUMNS}


def ids(rows: list[dict], column: str) -> set[str]:
    return {r[column] for r in rows}


# --- Files and sizes -------------------------------------------------------


@pytest.mark.parametrize("name", list(EXPECTED_COLUMNS))
def test_file_exists_with_expected_columns(name):
    with open(SAMPLE / name, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header == EXPECTED_COLUMNS[name]


def test_dataset_sizes_match_requirements(data):
    assert len(data["employees.csv"]) == 100
    assert 10 <= len(data["job_roles.csv"]) <= 15
    assert 30 <= len(data["skills.csv"]) <= 50
    assert 50 <= len(data["courses.csv"]) <= 100
    assert len(data["training_history.csv"]) >= 300
    assert len(data["skill_proficiency.csv"]) == 5


# --- Primary keys ----------------------------------------------------------


@pytest.mark.parametrize(
    "name, key",
    [
        ("skills.csv", ("skill_id",)),
        ("job_roles.csv", ("role_id",)),
        ("courses.csv", ("course_id",)),
        ("employees.csv", ("employee_id",)),
        ("employees.csv", ("email",)),
        ("training_history.csv", ("enrollment_id",)),
        ("role_required_skills.csv", ("role_id", "skill_id")),
        ("course_skills.csv", ("course_id", "skill_id")),
        ("course_prerequisites.csv", ("course_id", "prerequisite_course_id")),
        ("employee_skills.csv", ("employee_id", "skill_id")),
        ("career_goals.csv", ("employee_id",)),
    ],
)
def test_keys_are_unique(data, name, key):
    keys = Counter(tuple(r[k] for k in key) for r in data[name])
    duplicates = [k for k, n in keys.items() if n > 1]
    assert not duplicates, f"duplicate {key} in {name}: {duplicates[:5]}"


# --- Foreign keys ----------------------------------------------------------


@pytest.mark.parametrize(
    "child, column, parent, parent_column",
    [
        ("role_required_skills.csv", "role_id", "job_roles.csv", "role_id"),
        ("role_required_skills.csv", "skill_id", "skills.csv", "skill_id"),
        ("course_skills.csv", "course_id", "courses.csv", "course_id"),
        ("course_skills.csv", "skill_id", "skills.csv", "skill_id"),
        ("course_prerequisites.csv", "course_id", "courses.csv", "course_id"),
        ("course_prerequisites.csv", "prerequisite_course_id", "courses.csv", "course_id"),
        ("employees.csv", "current_role_id", "job_roles.csv", "role_id"),
        ("employee_skills.csv", "employee_id", "employees.csv", "employee_id"),
        ("employee_skills.csv", "skill_id", "skills.csv", "skill_id"),
        ("career_goals.csv", "employee_id", "employees.csv", "employee_id"),
        ("career_goals.csv", "target_role_id", "job_roles.csv", "role_id"),
        ("training_history.csv", "employee_id", "employees.csv", "employee_id"),
        ("training_history.csv", "course_id", "courses.csv", "course_id"),
    ],
)
def test_references_point_to_existing_rows(data, child, column, parent, parent_column):
    missing = ids(data[child], column) - ids(data[parent], parent_column)
    assert not missing, f"{child}.{column} has values not in {parent}: {sorted(missing)[:5]}"


def test_managers_exist_and_are_not_self(data):
    employee_ids = ids(data["employees.csv"], "employee_id")
    for e in data["employees.csv"]:
        if e["manager_id"]:
            assert e["manager_id"] in employee_ids
            assert e["manager_id"] != e["employee_id"]


def test_every_course_raises_at_least_one_skill(data):
    assert ids(data["courses.csv"], "course_id") == ids(data["course_skills.csv"], "course_id")


def test_every_role_has_required_skills(data):
    assert ids(data["job_roles.csv"], "role_id") == ids(data["role_required_skills.csv"], "role_id")


def test_career_goal_differs_from_current_role(data):
    current = {e["employee_id"]: e["current_role_id"] for e in data["employees.csv"]}
    for g in data["career_goals.csv"]:
        assert g["target_role_id"] != current[g["employee_id"]]


# --- Business rules: levels ------------------------------------------------


def test_levels_are_on_the_1_to_5_scale(data):
    assert [int(r["level"]) for r in data["skill_proficiency.csv"]] == [1, 2, 3, 4, 5]
    for r in data["employee_skills.csv"]:
        assert 1 <= int(r["current_level"]) <= 5
    for r in data["role_required_skills.csv"]:
        assert 1 <= int(r["required_level"]) <= 5


def test_courses_raise_level(data):
    for r in data["course_skills.csv"]:
        assert 0 <= int(r["level_from"]) < int(r["level_to"]) <= 5, r


def test_prerequisites_have_no_loops(data):
    """A course must never (directly or indirectly) require itself.

    Uses depth-first search: if we reach a course that is still on the
    current path, we have found a loop.
    """
    graph: dict[str, list[str]] = {}
    for p in data["course_prerequisites.csv"]:
        assert p["course_id"] != p["prerequisite_course_id"]
        graph.setdefault(p["course_id"], []).append(p["prerequisite_course_id"])

    visiting, done = set(), set()

    def visit(course: str, path: list[str]) -> None:
        if course in done:
            return
        assert course not in visiting, "prerequisite loop: " + " -> ".join(path + [course])
        visiting.add(course)
        for prereq in graph.get(course, []):
            visit(prereq, path + [course])
        visiting.discard(course)
        done.add(course)

    for course in graph:
        visit(course, [])


# --- Business rules: training history and dates ---------------------------


def test_training_status_rules(data):
    allowed = {"Enrolled", "In Progress", "Completed", "Dropped"}
    for r in data["training_history.csv"]:
        assert r["status"] in allowed
        enrolled = date.fromisoformat(r["enrolled_date"])
        assert enrolled <= AS_OF
        if r["status"] == "Completed":
            completed = date.fromisoformat(r["completed_date"])
            assert enrolled <= completed <= AS_OF
            assert 0 <= int(r["score"]) <= 100
        else:
            assert r["completed_date"] == "" and r["score"] == "", r


def test_training_starts_after_hire_date(data):
    hired = {e["employee_id"]: date.fromisoformat(e["hire_date"]) for e in data["employees.csv"]}
    for r in data["training_history.csv"]:
        assert date.fromisoformat(r["enrolled_date"]) >= hired[r["employee_id"]], r


def test_no_real_email_domains(data):
    assert all(e["email"].endswith("@example.com") for e in data["employees.csv"])


# --- The worked example from the requirements -----------------------------


def test_data_engineer_example_matches_requirements(data):
    """Software Developer E1001 wants to become a Data Engineer (requirements, section 2)."""
    skill_name = {s["skill_id"]: s["skill_name"] for s in data["skills.csv"]}
    role_id = {r["role_title"]: r["role_id"] for r in data["job_roles.csv"]}

    required = {
        skill_name[r["skill_id"]]: int(r["required_level"])
        for r in data["role_required_skills.csv"]
        if r["role_id"] == role_id["Data Engineer"]
    }
    assert required == {"Python": 4, "SQL": 4, "AWS": 3, "Machine Learning": 2, "Docker": 3}

    current = {
        skill_name[r["skill_id"]]: int(r["current_level"])
        for r in data["employee_skills.csv"]
        if r["employee_id"] == "E1001"
    }
    assert {k: current[k] for k in required} == {
        "Python": 3, "SQL": 2, "AWS": 1, "Machine Learning": 2, "Docker": 2,
    }  # fmt: skip

    employee = next(e for e in data["employees.csv"] if e["employee_id"] == "E1001")
    goal = next(g for g in data["career_goals.csv"] if g["employee_id"] == "E1001")
    assert employee["current_role_id"] == role_id["Software Developer"]
    assert goal["target_role_id"] == role_id["Data Engineer"]


# --- The committed files are what the generator produces --------------------


def test_committed_files_match_generator(tmp_path):
    """Regenerating with the default seed gives the same content as data/sample.

    If this fails, someone edited a CSV by hand or changed the generator
    without regenerating: run `python scripts/generate_synthetic_data.py`.
    Line endings are ignored, because Git on Windows may convert them.
    """
    spec = importlib.util.spec_from_file_location(
        "generator", ROOT / "scripts" / "generate_synthetic_data.py"
    )
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)

    generator.write_datasets(generator.build_datasets(generator.DEFAULT_SEED), tmp_path)
    for name in EXPECTED_COLUMNS:
        fresh = (tmp_path / name).read_text(encoding="utf-8").splitlines()
        committed = (SAMPLE / name).read_text(encoding="utf-8").splitlines()
        assert fresh == committed, f"{name} differs from generator output"
