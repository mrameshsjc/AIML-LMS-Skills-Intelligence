"""
Synthetic LMS data generator (Phase 2).

PURPOSE
    Create 11 realistic, fully consistent CSV files that stand in for a real
    LMS database: employees, skills, job roles, courses, prerequisites and
    training history. Every later phase (validation, skill analysis, matching,
    recommendations, ML, RAG) is built and tested on this data.

WHY SYNTHETIC DATA
    - We must never use real employee data in this project.
    - We control the patterns, so we know what the right answers should be
      (for example, the Data Engineer example from the requirements).

WHY THE STANDARD LIBRARY ONLY (csv, random, datetime)
    The generator needs no extra installs, and it is easy to read line by line.
    Pandas is introduced in Phase 3, where we READ and VALIDATE this data.

WHY A FIXED RANDOM SEED
    `random.Random(42)` always produces the same sequence of "random" numbers.
    So everyone who runs this script gets byte-for-byte identical files, and a
    test can prove the committed CSVs match the generator.
    Change the seed (--seed 7) to get a different but equally valid dataset.

HOW THE DATA IS BUILT (in this order, because each step needs the previous one)
    1. skills                  42 skills in 7 categories
    2. skill_proficiency       the 1-5 proficiency scale
    3. job_roles               13 roles
    4. role_required_skills    5-9 required skills per role, with levels
    5. courses                 80 courses, 1-3 levels per skill, plus 2 capstones
    6. course_skills           which skill each course raises, from which level to which
    7. course_prerequisites    which course must be finished first
    8. employees               100 employees with departments and managers
    9. employee_skills         each employee's current level per skill
   10. career_goals            the role each employee wants next (about 70 %)
   11. training_history        course enrolments, completions, drops and scores

    Employee E1001 is the worked example from the requirements: a Software
    Developer who wants to become a Data Engineer, with exactly the levels
    given there (Python 3, SQL 2, AWS 1, Machine Learning 2, Docker 2).

HOW TO RUN (PowerShell, from the project folder, venv activated)
    PS> python scripts/generate_synthetic_data.py
    PS> python scripts/generate_synthetic_data.py --seed 7 --out data/raw/seed7

EXPECTED OUTPUT
    Writing synthetic LMS data to ...\\data\\sample (seed 42, as of 2026-10-31)
      skills.csv                   42 rows
      ...
      training_history.csv        ~450 rows
    Done: 11 files written.
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "data" / "sample"
DEFAULT_SEED = 42

# The data describes the world "as of" this date. It is fixed (not today's
# date) so the output never changes when you run the script on another day.
AS_OF = date(2026, 10, 31)

# ---------------------------------------------------------------------------
# 1. Skills: (short code, name, category, description)
#    The short code is used to build readable course IDs such as C-SQL-201.
# ---------------------------------------------------------------------------
SKILLS = [
    ("PY", "Python", "Programming", "General-purpose language for data, automation and AI."),
    ("JAVA", "Java", "Programming", "Object-oriented language for enterprise applications."),
    ("JS", "JavaScript", "Programming", "Language for web front ends and Node.js services."),
    ("SQL", "SQL", "Programming", "Querying and managing data in relational databases."),
    ("SCALA", "Scala", "Programming", "JVM language often used with Apache Spark."),
    ("R", "R", "Programming", "Language for statistics and data analysis."),
    ("DM", "Data Modeling", "Data Engineering", "Designing tables, keys and relationships."),
    ("ETL", "ETL and Data Pipelines", "Data Engineering", "Extracting, transforming and loading data."),
    ("SPARK", "Apache Spark", "Data Engineering", "Distributed processing of large datasets."),
    ("AIRFLOW", "Workflow Orchestration", "Data Engineering", "Scheduling pipelines, e.g. Apache Airflow."),
    ("KAFKA", "Data Streaming", "Data Engineering", "Real-time event streaming, e.g. Apache Kafka."),
    ("DWH", "Data Warehousing", "Data Engineering", "Designing and loading analytical warehouses."),
    ("STATS", "Statistics", "Data Analytics", "Descriptive and inferential statistics."),
    ("VIZ", "Data Visualization", "Data Analytics", "Choosing and building clear charts."),
    ("BI", "BI Reporting", "Data Analytics", "Dashboards in BI tools such as Power BI or Tableau."),
    ("EXCEL", "Advanced Excel", "Data Analytics", "Formulas, pivot tables and data models in Excel."),
    ("AWS", "AWS", "Cloud & DevOps", "Amazon Web Services cloud platform."),
    ("AZURE", "Azure", "Cloud & DevOps", "Microsoft Azure cloud platform."),
    ("GCP", "Google Cloud", "Cloud & DevOps", "Google Cloud Platform."),
    ("DOCKER", "Docker", "Cloud & DevOps", "Packaging applications as containers."),
    ("K8S", "Kubernetes", "Cloud & DevOps", "Running and scaling containers in clusters."),
    ("CICD", "CI/CD", "Cloud & DevOps", "Automated build, test and deployment pipelines."),
    ("LINUX", "Linux", "Cloud & DevOps", "Linux command line and system administration."),
    (
        "IAC",
        "Infrastructure as Code",
        "Cloud & DevOps",
        "Provisioning infrastructure with code, e.g. Terraform.",
    ),
    ("GIT", "Git", "Software Engineering", "Version control with branches and pull requests."),
    ("SD", "System Design", "Software Engineering", "Designing scalable, reliable software systems."),
    ("API", "REST API Design", "Software Engineering", "Designing and building HTTP APIs."),
    ("TEST", "Software Testing", "Software Engineering", "Test design, test levels and defect management."),
    ("AUTO", "Test Automation", "Software Engineering", "Automated UI and API tests."),
    ("SEC", "Security Fundamentals", "Software Engineering", "Secure coding, identity and data protection."),
    ("ML", "Machine Learning", "AI & ML", "Supervised and unsupervised learning with Scikit-learn."),
    ("DL", "Deep Learning", "AI & ML", "Neural networks for vision, text and tabular data."),
    ("NLP", "Natural Language Processing", "AI & ML", "Processing and understanding text."),
    ("MLOPS", "MLOps", "AI & ML", "Deploying, monitoring and retraining ML models."),
    ("LLM", "LLM Applications", "AI & ML", "Building applications on large language models, incl. RAG."),
    ("PROMPT", "Prompt Engineering", "AI & ML", "Writing effective instructions for LLMs."),
    ("AGILE", "Agile Practices", "Professional", "Scrum, Kanban and iterative delivery."),
    ("COMM", "Communication", "Professional", "Clear written and verbal communication."),
    ("PM", "Project Management", "Professional", "Planning, tracking and delivering projects."),
    ("STAKE", "Stakeholder Management", "Professional", "Aligning and managing stakeholders."),
    ("LEAD", "Leadership", "Professional", "Leading, coaching and developing people."),
    ("REQ", "Requirements Analysis", "Professional", "Eliciting and documenting requirements."),
]

PROFICIENCY = [
    (1, "Beginner", "Knows the basic ideas; needs step-by-step guidance."),
    (2, "Elementary", "Completes simple tasks with some help."),
    (3, "Intermediate", "Works independently on typical tasks."),
    (4, "Advanced", "Handles complex tasks and guides others."),
    (5, "Expert", "Recognised authority; sets standards and solves novel problems."),
]

# ---------------------------------------------------------------------------
# 3-4. Job roles and their required skills.
#   requirements: {skill_code: (required_level, is_mandatory)}
#   The Data Engineer requirements are EXACTLY the example in the project
#   documents, so later phases can be checked against the expected answer.
# ---------------------------------------------------------------------------
ROLES = [
    (
        "Software Developer",
        "Engineering",
        "Software Engineering",
        "Mid",
        {
            "PY": (3, True),
            "JAVA": (3, False),
            "SQL": (2, True),
            "GIT": (3, True),
            "API": (3, True),
            "TEST": (2, False),
            "AGILE": (2, False),
        },
    ),
    (
        "Senior Software Developer",
        "Engineering",
        "Software Engineering",
        "Senior",
        {
            "PY": (4, True),
            "SQL": (3, True),
            "SD": (4, True),
            "API": (4, True),
            "DOCKER": (3, False),
            "CICD": (3, False),
            "TEST": (3, False),
            "GIT": (4, False),
            "LEAD": (2, False),
        },
    ),
    (
        "Data Analyst",
        "Data & Analytics",
        "Data",
        "Mid",
        {
            "SQL": (4, True),
            "EXCEL": (4, True),
            "STATS": (3, True),
            "VIZ": (3, True),
            "BI": (3, False),
            "PY": (2, False),
            "COMM": (3, False),
        },
    ),
    (
        "Data Engineer",
        "Data & Analytics",
        "Data",
        "Mid",
        {"PY": (4, True), "SQL": (4, True), "AWS": (3, True), "ML": (2, False), "DOCKER": (3, False)},
    ),
    (
        "Data Scientist",
        "Data & Analytics",
        "Data",
        "Mid",
        {
            "PY": (4, True),
            "STATS": (4, True),
            "ML": (4, True),
            "SQL": (3, False),
            "VIZ": (3, False),
            "DL": (2, False),
            "COMM": (3, False),
        },
    ),
    (
        "Machine Learning Engineer",
        "AI & ML",
        "AI & ML",
        "Mid",
        {
            "PY": (4, True),
            "ML": (4, True),
            "MLOPS": (3, True),
            "DOCKER": (3, True),
            "AWS": (3, False),
            "SQL": (3, False),
            "DL": (3, False),
        },
    ),
    (
        "AI Engineer",
        "AI & ML",
        "AI & ML",
        "Mid",
        {
            "PY": (4, True),
            "LLM": (4, True),
            "PROMPT": (3, True),
            "NLP": (3, False),
            "ML": (3, False),
            "API": (3, False),
            "AWS": (2, False),
        },
    ),
    (
        "DevOps Engineer",
        "Cloud & Infrastructure",
        "Cloud & DevOps",
        "Mid",
        {
            "LINUX": (4, True),
            "DOCKER": (4, True),
            "K8S": (3, True),
            "CICD": (4, True),
            "AWS": (3, False),
            "IAC": (3, False),
            "GIT": (3, False),
            "PY": (2, False),
        },
    ),
    (
        "Cloud Architect",
        "Cloud & Infrastructure",
        "Cloud & DevOps",
        "Senior",
        {
            "AWS": (5, True),
            "SD": (4, True),
            "SEC": (4, True),
            "AZURE": (3, False),
            "IAC": (4, False),
            "K8S": (3, False),
            "STAKE": (3, False),
        },
    ),
    (
        "QA Engineer",
        "Quality Assurance",
        "Quality Engineering",
        "Mid",
        {
            "TEST": (4, True),
            "AUTO": (3, True),
            "PY": (2, False),
            "SQL": (2, False),
            "AGILE": (3, False),
            "API": (2, False),
        },
    ),
    (
        "Business Analyst",
        "Product & Business",
        "Business",
        "Mid",
        {
            "REQ": (4, True),
            "STAKE": (3, True),
            "COMM": (4, True),
            "SQL": (2, False),
            "EXCEL": (3, False),
            "AGILE": (3, False),
        },
    ),
    (
        "Project Manager",
        "PMO",
        "Management",
        "Senior",
        {"PM": (4, True), "STAKE": (4, True), "COMM": (4, True), "AGILE": (4, False), "LEAD": (3, False)},
    ),
    (
        "Engineering Manager",
        "Engineering",
        "Management",
        "Senior",
        {
            "LEAD": (4, True),
            "PM": (3, True),
            "COMM": (4, True),
            "SD": (3, False),
            "STAKE": (3, False),
            "AGILE": (3, False),
        },
    ),
]

# How many employees hold each role (adds up to 100).
ROLE_HEADCOUNT = {
    "Software Developer": 22,
    "Senior Software Developer": 8,
    "Data Analyst": 10,
    "Data Engineer": 8,
    "Data Scientist": 7,
    "Machine Learning Engineer": 5,
    "AI Engineer": 4,
    "DevOps Engineer": 8,
    "Cloud Architect": 3,
    "QA Engineer": 9,
    "Business Analyst": 6,
    "Project Manager": 4,
    "Engineering Manager": 6,
}

# Realistic next-step roles used to create career goals.
CAREER_MOVES = {
    "Software Developer": ["Senior Software Developer", "Data Engineer", "DevOps Engineer", "AI Engineer"],
    "Senior Software Developer": ["Engineering Manager", "Cloud Architect"],
    "Data Analyst": ["Data Scientist", "Data Engineer", "Business Analyst"],
    "Data Engineer": ["Machine Learning Engineer", "Cloud Architect"],
    "Data Scientist": ["Machine Learning Engineer", "AI Engineer"],
    "Machine Learning Engineer": ["AI Engineer"],
    "AI Engineer": ["Machine Learning Engineer"],
    "DevOps Engineer": ["Cloud Architect"],
    "Cloud Architect": ["Engineering Manager"],
    "QA Engineer": ["Software Developer", "DevOps Engineer"],
    "Business Analyst": ["Project Manager", "Data Analyst"],
    "Project Manager": ["Engineering Manager"],
    "Engineering Manager": [],
}

# ---------------------------------------------------------------------------
# 5-7. Courses.
#   Tier 101: Beginner,     raises a skill from 0 (none) to 2
#   Tier 201: Intermediate, raises a skill from 2 to 4
#   Tier 301: Advanced,     raises a skill from 4 to 5
#   Tier 150: single "Essentials" course, 0 to 3, for skills with one course
# ---------------------------------------------------------------------------
THREE_TIER = {"PY", "SQL", "AWS", "ML", "DOCKER", "K8S", "SPARK", "DL"}
ONE_TIER = {
    "SCALA",
    "R",
    "GCP",
    "EXCEL",
    "AIRFLOW",
    "KAFKA",
    "IAC",
    "BI",
    "AGILE",
    "COMM",
    "PM",
    "STAKE",
    "LEAD",
    "REQ",
}

TIERS = {
    101: ("Beginner", 0, 2, "{name} Fundamentals", (8, 16)),
    150: ("Intermediate", 0, 3, "{name} Essentials", (12, 20)),
    201: ("Intermediate", 2, 4, "{name} for Practitioners", (16, 24)),
    301: ("Advanced", 4, 5, "Advanced {name}", (24, 40)),
}

# Friendlier titles for some well-known courses.
TITLE_OVERRIDES = {
    "C-PY-101": "Python Programming Fundamentals",
    "C-SQL-101": "SQL Fundamentals",
    "C-SQL-201": "SQL for Data Engineering",
    "C-AWS-101": "AWS Cloud Foundations",
    "C-AWS-201": "AWS for Data and Application Workloads",
    "C-ML-101": "Introduction to Machine Learning",
    "C-DOCKER-201": "Docker in Production",
    "C-COMM-150": "Effective Business Communication",
}

# Capstones raise several skills at once (level 3 to 4) and have prerequisites.
CAPSTONES = [
    (
        "C-DE-401",
        "Data Engineering Capstone on AWS",
        ["SPARK", "AWS", "ETL"],
        ["C-SPARK-201", "C-AWS-201", "C-ETL-201"],
    ),
    (
        "C-MLE-401",
        "Machine Learning Engineering Capstone",
        ["ML", "MLOPS", "DOCKER"],
        ["C-ML-201", "C-MLOPS-201", "C-DOCKER-201"],
    ),
]

# Cross-skill prerequisites: course -> courses that must be completed first.
CROSS_PREREQUISITES = {
    "C-SPARK-101": ["C-PY-101", "C-SQL-101"],
    "C-ML-101": ["C-PY-101", "C-STATS-101"],
    "C-DL-101": ["C-ML-201"],
    "C-NLP-101": ["C-ML-201"],
    "C-MLOPS-101": ["C-ML-201", "C-DOCKER-101"],
    "C-LLM-101": ["C-PY-201"],
    "C-K8S-101": ["C-DOCKER-101"],
    "C-DOCKER-101": ["C-LINUX-101"],
    "C-ETL-101": ["C-SQL-101"],
    "C-DWH-101": ["C-SQL-101"],
    "C-AIRFLOW-150": ["C-PY-101", "C-ETL-101"],
    "C-KAFKA-150": ["C-ETL-101"],
    "C-CICD-101": ["C-GIT-101"],
    "C-AUTO-101": ["C-TEST-101"],
    "C-IAC-150": ["C-AWS-101"],
}

# ---------------------------------------------------------------------------
# 8. People: fictional names and locations.
# ---------------------------------------------------------------------------
FIRST_NAMES = [
    "Aarav",
    "Aditi",
    "Akash",
    "Ananya",
    "Arjun",
    "Bhavana",
    "Deepak",
    "Divya",
    "Ganesh",
    "Harini",
    "Ishaan",
    "Janani",
    "Karthik",
    "Kavya",
    "Lakshmi",
    "Manoj",
    "Meera",
    "Naveen",
    "Nisha",
    "Pooja",
    "Prakash",
    "Priya",
    "Rahul",
    "Revathi",
    "Sanjay",
    "Shalini",
    "Suresh",
    "Swathi",
    "Vikram",
    "Vidya",
    "Yusuf",
    "Zara",
    "Daniel",
    "Grace",
    "Omar",
    "Sofia",
    "Kevin",
    "Fatima",
    "Rohan",
    "Sneha",
]
LAST_NAMES = [
    "Kumar",
    "Sharma",
    "Iyer",
    "Reddy",
    "Nair",
    "Menon",
    "Rao",
    "Pillai",
    "Gupta",
    "Singh",
    "Krishnan",
    "Subramanian",
    "Patel",
    "Joshi",
    "Das",
    "Fernandes",
    "Khan",
    "Mathew",
    "Bose",
    "Varghese",
]
LOCATIONS = ["Chennai", "Bengaluru", "Hyderabad", "Pune", "Coimbatore"]

# The worked example from the requirements.
EXAMPLE_EMPLOYEE_ID = "E1001"
EXAMPLE_SKILLS = {
    "PY": 3,
    "SQL": 2,
    "AWS": 1,
    "ML": 2,
    "DOCKER": 2,
    "JAVA": 3,
    "GIT": 3,
    "API": 3,
    "TEST": 2,
    "AGILE": 2,
}
EXAMPLE_TRAINING = [  # course, enrolled, completed, score
    ("C-PY-101", date(2024, 8, 5), date(2024, 9, 2), 88),
    ("C-GIT-101", date(2024, 11, 4), date(2024, 11, 22), 91),
    ("C-SQL-101", date(2025, 3, 10), date(2025, 4, 2), 84),
]


def _random_date(rng: random.Random, start: date, end: date) -> date:
    """Return a random date between start and end (both included)."""
    return start + timedelta(days=rng.randint(0, (end - start).days))


def build_datasets(seed: int = DEFAULT_SEED) -> dict[str, list[dict]]:
    """Build all 11 tables in memory and return them as {file name: rows}.

    Each row is a dict whose keys are the CSV column names. Building in memory
    first lets the tests check the data without writing any files.
    """
    rng = random.Random(seed)

    # --- 1. skills ---------------------------------------------------------
    skill_id = {code: f"SK{i:03d}" for i, (code, *_rest) in enumerate(SKILLS, start=1)}
    skill_name = {code: name for code, name, *_rest in SKILLS}
    skills = [
        {"skill_id": skill_id[code], "skill_name": name, "category": category, "description": desc}
        for code, name, category, desc in SKILLS
    ]

    # --- 2. skill_proficiency ---------------------------------------------
    skill_proficiency = [
        {"level": level, "label": label, "description": desc} for level, label, desc in PROFICIENCY
    ]

    # --- 3-4. job_roles and role_required_skills ---------------------------
    role_id = {title: f"R{i:03d}" for i, (title, *_rest) in enumerate(ROLES, start=1)}
    role_reqs = {title: reqs for title, *_mid, reqs in ROLES}
    job_roles, role_required_skills = [], []
    for title, department, family, seniority, reqs in ROLES:
        job_roles.append(
            {
                "role_id": role_id[title],
                "role_title": title,
                "department": department,
                "job_family": family,
                "seniority": seniority,
                "description": f"{seniority}-level {title} in the {department} department.",
            }
        )
        for code, (level, mandatory) in reqs.items():
            role_required_skills.append(
                {
                    "role_id": role_id[title],
                    "skill_id": skill_id[code],
                    "required_level": level,
                    # Equal weights for now; the column exists so weights can be tuned later.
                    "importance_weight": 1.0,
                    "is_mandatory": mandatory,
                }
            )

    # --- 5-7. courses, course_skills, course_prerequisites -----------------
    courses, course_skills, course_prerequisites = [], [], []
    providers = ["Internal Academy", "Internal Academy", "External Partner", "Vendor Certification"]
    modes = ["Online", "Online", "Blended", "Classroom"]
    for code, name, *_rest in SKILLS:
        tiers = [101, 201, 301] if code in THREE_TIER else [150] if code in ONE_TIER else [101, 201]
        for tier in tiers:
            difficulty, level_from, level_to, title_tpl, (hmin, hmax) = TIERS[tier]
            course_id = f"C-{code}-{tier}"
            title = TITLE_OVERRIDES.get(course_id, title_tpl.format(name=name))
            courses.append(
                {
                    "course_id": course_id,
                    "course_title": title,
                    "description": f"{difficulty} course that raises {name} from level {level_from} "
                    f"to level {level_to}.",
                    "difficulty": difficulty,
                    "duration_hours": rng.randint(hmin, hmax),
                    "delivery_mode": rng.choice(modes),
                    "provider": rng.choice(providers),
                    "is_active": True,
                }
            )
            course_skills.append(
                {
                    "course_id": course_id,
                    "skill_id": skill_id[code],
                    "level_from": level_from,
                    "level_to": level_to,
                }
            )
            # Within one skill, each level requires the level below it.
            previous = {201: 101, 301: 201}.get(tier)
            if previous:
                course_prerequisites.append(
                    {"course_id": course_id, "prerequisite_course_id": f"C-{code}-{previous}"}
                )

    for course_id, title, codes, prereqs in CAPSTONES:
        courses.append(
            {
                "course_id": course_id,
                "course_title": title,
                "description": "Project-based capstone that raises "
                + ", ".join(skill_name[c] for c in codes)
                + " from level 3 to level 4.",
                "difficulty": "Advanced",
                "duration_hours": rng.randint(32, 48),
                "delivery_mode": "Blended",
                "provider": "Internal Academy",
                "is_active": True,
            }
        )
        for c in codes:
            course_skills.append(
                {"course_id": course_id, "skill_id": skill_id[c], "level_from": 3, "level_to": 4}
            )
        for p in prereqs:
            course_prerequisites.append({"course_id": course_id, "prerequisite_course_id": p})

    for course_id, prereqs in CROSS_PREREQUISITES.items():
        for p in prereqs:
            course_prerequisites.append({"course_id": course_id, "prerequisite_course_id": p})

    # Fail early if a prerequisite points to a course that does not exist.
    known_courses = {c["course_id"] for c in courses}
    unknown = {p["prerequisite_course_id"] for p in course_prerequisites} - known_courses
    unknown |= {p["course_id"] for p in course_prerequisites} - known_courses
    if unknown:
        raise ValueError(f"Prerequisites refer to unknown courses: {sorted(unknown)}")

    # --- 8. employees -------------------------------------------------------
    role_titles = [t for t in ROLE_HEADCOUNT for _ in range(ROLE_HEADCOUNT[t])]
    role_titles.remove("Software Developer")  # E1001 is added explicitly as a Software Developer
    rng.shuffle(role_titles)
    role_titles.insert(0, "Software Developer")
    department_of = {title: dept for title, dept, *_rest in ROLES}
    seniority_of = {title: sen for title, _dept, _fam, sen, _reqs in ROLES}

    employees, used_emails = [], set()
    for i, title in enumerate(role_titles):
        emp_id = f"E{1001 + i}"
        if emp_id == EXAMPLE_EMPLOYEE_ID:
            first, last = "Arjun", "Krishnan"
        else:
            first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        email_base = f"{first}.{last}".lower()
        email, n = f"{email_base}@example.com", 2
        while email in used_emails:  # keep e-mails unique
            email, n = f"{email_base}{n}@example.com", n + 1
        used_emails.add(email)
        senior = seniority_of[title] == "Senior"
        hire_start, hire_end = (
            (date(2012, 1, 1), date(2020, 12, 31)) if senior else (date(2016, 1, 1), date(2025, 12, 31))
        )
        employees.append(
            {
                "employee_id": emp_id,
                "first_name": first,
                "last_name": last,
                "email": email,
                "department": department_of[title],
                "current_role_id": role_id[title],
                "manager_id": "",
                "hire_date": date(2021, 6, 14)
                if emp_id == EXAMPLE_EMPLOYEE_ID
                else _random_date(rng, hire_start, hire_end),
                "location": "Chennai" if emp_id == EXAMPLE_EMPLOYEE_ID else rng.choice(LOCATIONS),
                "employment_status": "Active",
            }
        )

    # Managers: Project Managers manage PMO and Product; Engineering Managers manage everyone else.
    title_of = {e["employee_id"]: rt for e, rt in zip(employees, role_titles, strict=True)}
    eng_managers = [
        e["employee_id"] for e in employees if title_of[e["employee_id"]] == "Engineering Manager"
    ]
    proj_managers = [e["employee_id"] for e in employees if title_of[e["employee_id"]] == "Project Manager"]
    for e in employees:
        if title_of[e["employee_id"]] in ("Engineering Manager", "Project Manager"):
            continue  # top of this small organisation: no manager
        pool = proj_managers if e["department"] in ("PMO", "Product & Business") else eng_managers
        e["manager_id"] = rng.choice(pool)

    # --- 9. employee_skills -------------------------------------------------
    employee_skills = []
    all_codes = [code for code, *_rest in SKILLS]
    for e in employees:
        emp_id = e["employee_id"]
        if emp_id == EXAMPLE_EMPLOYEE_ID:
            levels = dict(EXAMPLE_SKILLS)
        else:
            levels = {}
            for code, (req, mandatory) in role_reqs[title_of[emp_id]].items():
                # People usually hold their role's skills near the required level.
                if not mandatory and rng.random() < 0.15:
                    continue  # sometimes a non-mandatory skill is missing
                levels[code] = max(1, min(5, req + rng.choice([-2, -1, -1, 0, 0, 0, 1])))
            # A few extra skills from outside the role, at lower levels.
            for code in rng.sample([c for c in all_codes if c not in levels], rng.randint(2, 4)):
                levels[code] = rng.randint(1, 3)
        for code, level in levels.items():
            employee_skills.append(
                {
                    "employee_id": emp_id,
                    "skill_id": skill_id[code],
                    "current_level": level,
                    "source": "assessment"
                    if emp_id == EXAMPLE_EMPLOYEE_ID
                    else rng.choices(["self", "manager", "assessment"], weights=[5, 3, 2])[0],
                    "assessed_date": date(2026, 9, 15)
                    if emp_id == EXAMPLE_EMPLOYEE_ID
                    else _random_date(rng, date(2025, 1, 1), AS_OF),
                }
            )

    # --- 10. career_goals ---------------------------------------------------
    career_goals = []
    for e in employees:
        emp_id = e["employee_id"]
        if emp_id == EXAMPLE_EMPLOYEE_ID:
            target = "Data Engineer"
        else:
            moves = CAREER_MOVES[title_of[emp_id]]
            if not moves or rng.random() > 0.7:
                continue  # about 30 % have no stated goal
            target = rng.choice(moves)
        career_goals.append(
            {
                "employee_id": emp_id,
                "target_role_id": role_id[target],
                "set_date": date(2026, 2, 1)
                if emp_id == EXAMPLE_EMPLOYEE_ID
                else _random_date(rng, date(2025, 6, 1), AS_OF),
                "goal_status": "Active",
            }
        )

    # --- 11. training_history ----------------------------------------------
    # Completion is decided by simple, documented rules (plus randomness), so the
    # ML model in Phase 8 has a real pattern to learn:
    #   * starting a course far above your current level lowers completion;
    #   * missing prerequisites lowers completion.
    course_skill_rows = {}
    for cs in course_skills:
        course_skill_rows.setdefault(cs["course_id"], []).append(cs)
    prereqs_of = {}
    for p in course_prerequisites:
        prereqs_of.setdefault(p["course_id"], []).append(p["prerequisite_course_id"])
    code_of_skill_id = {v: k for k, v in skill_id.items()}
    skill_levels = {}
    for es in employee_skills:
        skill_levels.setdefault(es["employee_id"], {})[code_of_skill_id[es["skill_id"]]] = es["current_level"]
    goal_of = {g["employee_id"]: g["target_role_id"] for g in career_goals}
    title_of_role = {v: k for k, v in role_id.items()}

    def tier_of(course_id: str) -> int:
        return int(course_id.rsplit("-", 1)[1])

    enrolments = []
    for e in employees:
        emp_id = e["employee_id"]
        if emp_id == EXAMPLE_EMPLOYEE_ID:
            for course_id, enrolled, completed, score in EXAMPLE_TRAINING:
                enrolments.append((emp_id, course_id, "Completed", enrolled, completed, score, 1))
            continue

        # Relevant skills: the current role's, plus the target role's if any.
        relevant = set(role_reqs[title_of[emp_id]])
        if emp_id in goal_of:
            relevant |= set(role_reqs[title_of_role[goal_of[emp_id]]])
        relevant_ids = {skill_id[c] for c in relevant}
        pool = sorted({cs["course_id"] for cs in course_skills if cs["skill_id"] in relevant_ids})
        chosen = rng.sample(pool, min(rng.randint(3, 7), len(pool)))
        if rng.random() < 0.2:  # occasionally a course outside the career path
            chosen.append(rng.choice(sorted(known_courses - set(chosen))))
        chosen.sort(key=tier_of)  # take lower-level courses first

        completed_so_far: set[str] = set()
        earliest = max(e["hire_date"], date(2023, 1, 1))
        for course_id in chosen:
            p_complete = 0.80
            for cs in course_skill_rows[course_id]:
                current = skill_levels[emp_id].get(code_of_skill_id[cs["skill_id"]], 0)
                if cs["level_from"] > current + 1:
                    p_complete -= 0.25  # course is too advanced for this person
            if any(p not in completed_so_far for p in prereqs_of.get(course_id, [])):
                p_complete -= 0.15  # prerequisites not completed

            roll = rng.random()
            if roll < 0.10:
                status = "Enrolled"
            elif roll < 0.22:
                status = "In Progress"
            else:
                status = "Completed" if rng.random() < p_complete else "Dropped"

            if status in ("Enrolled", "In Progress"):
                enrolled = _random_date(rng, max(earliest, date(2026, 7, 1)), AS_OF)
                completed, score = None, None
            else:
                enrolled = _random_date(rng, earliest, AS_OF - timedelta(days=60))
                completed = enrolled + timedelta(days=rng.randint(7, 60)) if status == "Completed" else None
                score = max(50, min(100, round(rng.gauss(78, 10)))) if status == "Completed" else None
            attempts = 2 if status == "Completed" and rng.random() < 0.15 else 1
            if status == "Completed":
                completed_so_far.add(course_id)
            enrolments.append((emp_id, course_id, status, enrolled, completed, score, attempts))

    enrolments.sort(key=lambda r: (r[0], r[3], r[1]))  # by employee, then date
    training_history = [
        {
            "enrollment_id": f"EN{i:04d}",
            "employee_id": emp_id,
            "course_id": course_id,
            "status": status,
            "enrolled_date": enrolled,
            "completed_date": completed or "",
            "score": "" if score is None else score,
            "attempts": attempts,
        }
        for i, (emp_id, course_id, status, enrolled, completed, score, attempts) in enumerate(
            enrolments, start=1
        )
    ]

    return {
        "skills.csv": skills,
        "skill_proficiency.csv": skill_proficiency,
        "job_roles.csv": job_roles,
        "role_required_skills.csv": role_required_skills,
        "courses.csv": courses,
        "course_skills.csv": course_skills,
        "course_prerequisites.csv": course_prerequisites,
        "employees.csv": employees,
        "employee_skills.csv": employee_skills,
        "career_goals.csv": career_goals,
        "training_history.csv": training_history,
    }


def write_datasets(datasets: dict[str, list[dict]], out_dir: Path) -> None:
    """Write each table to `<out_dir>/<file name>`.

    `lineterminator="\\n"` gives the same bytes on Windows and Linux, so Git
    does not see every line as changed when the files are regenerated.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for file_name, rows in datasets.items():
        with open(out_dir / file_name, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic LMS CSV files.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random seed (default 42)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output folder (default data/sample)")
    args = parser.parse_args()

    out_dir = args.out if args.out.is_absolute() else ROOT / args.out
    print(f"Writing synthetic LMS data to {out_dir} (seed {args.seed}, as of {AS_OF})")
    datasets = build_datasets(args.seed)
    write_datasets(datasets, out_dir)
    for file_name, rows in datasets.items():
        print(f"  {file_name:<28}{len(rows):>5} rows")
    print(f"Done: {len(datasets)} files written.")


if __name__ == "__main__":
    main()
