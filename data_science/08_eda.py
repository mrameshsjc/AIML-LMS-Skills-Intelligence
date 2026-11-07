"""
08 - Exploratory Data Analysis (EDA): what does the data tell us?

LESSON
    EDA means looking at the data with simple counts, averages and charts
    BEFORE building models, to understand it and to spot surprises. This script
    answers seven questions and saves one chart per question:

      1. How are employees spread across departments?
      2. What skill levels do employees have?
      3. Which skills are most common?
      4. How do course enrolments end?
      5. Does starting a course above your level hurt completion?   <- key for ML (Phase 8)
      6. Which roles have the largest skill gaps today?             <- preview of Phase 5
      7. How are course scores distributed?

KEY IDEAS
    merge()      join two tables on a shared column (like VLOOKUP / SQL JOIN)
    groupby()    split rows into groups, then count / average each group
    rate         part / whole, e.g. completed / (completed + dropped)
    Matplotlib   Python's standard charting library; we save charts as PNG

WHY CHARTS ARE SAVED, NOT SHOWN
    matplotlib.use("Agg") draws into files without opening windows, so the
    script runs the same in PyCharm, a terminal, Docker or GitHub Actions.
    Open the PNGs from the reports/eda folder.

HOW TO RUN (from the project folder)
    PS> python data_science/08_eda.py
    PS> python data_science/08_eda.py --data data/processed --out reports/eda_processed

INPUT    the 11 CSV files in --data (default data/sample); should be clean (run 07 first if not)
OUTPUT   7 PNG charts in --out (default reports/eda) and the findings printed
"""

import argparse

import matplotlib

matplotlib.use("Agg")  # draw to files only, no windows

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from _common import explain, heading  # noqa: E402

from app.data_processing.loader import load_all, resolve_folder  # noqa: E402

# Chart style: one calm blue for every bar (each chart has a single series), dark text,
# light grid behind the bars. Colours from the project's validated reference palette.
BLUE, INK, MUTED, GRID, SURFACE = "#2a78d6", "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

parser = argparse.ArgumentParser(description="Lesson 08: exploratory data analysis.")
parser.add_argument("--data", default="data/sample", help="folder with the CSV files (default data/sample)")
parser.add_argument("--out", default="reports/eda", help="folder for the charts (default reports/eda)")
args = parser.parse_args()
out = resolve_folder(args.out)
out.mkdir(parents=True, exist_ok=True)

data = load_all(args.data, typed=True)
emp, emp_skills, skills = data["employees.csv"], data["employee_skills.csv"], data["skills.csv"]
roles, role_req = data["job_roles.csv"], data["role_required_skills.csv"]
history, course_skills = data["training_history.csv"], data["course_skills.csv"]


def bar_chart(
    labels, values, title, subtitle, filename, horizontal=False, fmt="{:.0f}", xlabel="", value_label=""
):
    """Save a single-series bar chart with value labels at the bar ends.

    One series, so no legend: the title says what is shown. Bars are drawn on a
    light surface with a recessive grid; text uses ink colours, never the bar colour.
    """
    fig, ax = plt.subplots(figsize=(8, 0.45 * len(labels) + 1.6 if horizontal else 4.6), dpi=120)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    positions = range(len(labels))
    if horizontal:
        bars = ax.barh(positions, values, height=0.6, color=BLUE)
        ax.set_yticks(list(positions), labels)
        ax.invert_yaxis()  # largest first, top to bottom
        ax.xaxis.grid(True, color=GRID, linewidth=0.8)
        ax.set_xlabel(xlabel or value_label, color=MUTED)
        ax.margins(x=0.08)  # room for the value labels at the bar ends
    else:
        bars = ax.bar(positions, values, width=0.6, color=BLUE)
        ax.set_xticks(list(positions), labels)
        ax.yaxis.grid(True, color=GRID, linewidth=0.8)
        ax.set_xlabel(xlabel, color=MUTED)
        ax.set_ylabel(value_label, color=MUTED)
        ax.margins(y=0.12)  # room for the value labels above the bars
    ax.bar_label(bars, labels=[fmt.format(v) for v in values], padding=3, color=INK, fontsize=9)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left" if not horizontal else "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=9)
    fig.suptitle(title, x=0.02, ha="left", fontsize=12, fontweight="bold", color=INK)
    ax.set_title(subtitle, loc="left", fontsize=9, color=MUTED)
    fig.tight_layout()
    fig.savefig(out / filename, facecolor=SURFACE)
    plt.close(fig)
    print(f"  chart saved: {out / filename}")


# ---------------------------------------------------------------------------
heading("1. Employees per department")
per_dept = emp.groupby("department").size().sort_values(ascending=False)
print(per_dept.to_string())
bar_chart(
    per_dept.index,
    per_dept.values,
    f"{per_dept.index[0]} is the largest department",
    f"Employees per department ({len(emp)} in total)",
    "01_employees_per_department.png",
    horizontal=True,
)

# ---------------------------------------------------------------------------
heading("2. Skill levels held")
level_counts = emp_skills["current_level"].value_counts().sort_index()
share_3_plus = (emp_skills["current_level"] >= 3).mean()
print(level_counts.to_string())
print(f"{share_3_plus:.0%} of recorded skills are at level 3 (Intermediate) or above.")
bar_chart(
    [f"{lvl}" for lvl in level_counts.index],
    level_counts.values,
    f"{share_3_plus:.0%} of recorded skills are Intermediate or above",
    "Number of employee-skill records per proficiency level (1 = Beginner, 5 = Expert)",
    "02_skill_level_distribution.png",
    value_label="Records",
    xlabel="Proficiency level",
)

# ---------------------------------------------------------------------------
heading("3. Most common skills")
explain("merge() adds the skill name to each employee-skill row, using skill_id as the shared column.")
named = emp_skills.merge(skills[["skill_id", "skill_name"]], on="skill_id", how="left")
top = named.groupby("skill_name")["employee_id"].nunique().sort_values(ascending=False).head(12)
print(top.to_string())
bar_chart(
    top.index,
    top.values,
    f"{top.index[0]} is the most widespread skill",
    "Employees holding each skill, top 12",
    "03_top_skills.png",
    horizontal=True,
)

# ---------------------------------------------------------------------------
heading("4. How enrolments end")
status_order = ["Completed", "Dropped", "In Progress", "Enrolled"]
status = history["status"].value_counts().reindex(status_order, fill_value=0)
finished = status["Completed"] + status["Dropped"]
completion_rate = status["Completed"] / finished
print(status.to_string())
print(f"Completion rate of finished enrolments: {completion_rate:.0%} (completed / (completed + dropped))")
bar_chart(
    status.index,
    status.values,
    f"{completion_rate:.0%} of finished enrolments are completed",
    f"Enrolments by status ({len(history)} in total)",
    "04_training_status.png",
    value_label="Enrolments",
)

# ---------------------------------------------------------------------------
heading("5. Does starting above your level hurt completion?")
explain("""
For each finished enrolment we compare the course's starting level (level_from) with the learner's
current level in that skill. 'Jump' = level_from - current level (missing skill = level 0).
A jump of 2 or more means the course starts well above what the learner knows.
""")
jumps = course_skills.merge(history[["employee_id", "course_id", "status"]], on="course_id")
jumps = jumps.merge(
    emp_skills[["employee_id", "skill_id", "current_level"]], on=["employee_id", "skill_id"], how="left"
)
jumps["current_level"] = jumps["current_level"].fillna(0)
jumps["jump"] = jumps["level_from"] - jumps["current_level"]
# A course can raise several skills; use its largest jump for that enrolment.
per_enrolment = jumps.groupby(["employee_id", "course_id", "status"], as_index=False)["jump"].max()
done = per_enrolment[per_enrolment["status"].isin(["Completed", "Dropped"])].copy()
done["group"] = pd.cut(
    done["jump"], bins=[-10, 0, 1, 10], labels=["At or below my level", "1 level above", "2+ levels above"]
)
by_jump = done.groupby("group", observed=False).agg(
    enrolments=("status", "size"), completed=("status", lambda s: (s == "Completed").sum())
)
by_jump["completion_rate"] = by_jump["completed"] / by_jump["enrolments"]
print(by_jump.to_string(formatters={"completion_rate": "{:.0%}".format}))
low, high = by_jump["completion_rate"].iloc[0], by_jump["completion_rate"].iloc[-1]
bar_chart(
    [str(g) for g in by_jump.index],
    (by_jump["completion_rate"] * 100).round(1).tolist(),
    f"Completion falls from {low:.0%} to {high:.0%} when a course starts 2+ levels too high",
    "Completion rate of finished enrolments, by how far the course starts above the learner's level",
    "05_completion_by_level_jump.png",
    value_label="Completion rate (%)",
    fmt="{:.0f}%",
)
explain("""
This pattern is what an ML model can learn in Phase 8. Remember: the data is synthetic and was
generated with this rule, so the chart shows the method working, not a fact about real people.
""")

# ---------------------------------------------------------------------------
heading("6. Skill gaps against each employee's current role")
explain("""
For each employee and each skill their current role requires: gap = required - current (never below 0;
missing skill = level 0). Then we add up the gaps per employee and average them per role.
Phase 5 turns exactly this calculation into the Skills Analysis API.
""")
req = emp[["employee_id", "current_role_id"]].merge(role_req, left_on="current_role_id", right_on="role_id")
req = req.merge(
    emp_skills[["employee_id", "skill_id", "current_level"]], on=["employee_id", "skill_id"], how="left"
)
req["gap"] = (req["required_level"] - req["current_level"].fillna(0)).clip(lower=0)
per_employee = req.groupby(["employee_id", "role_id"], as_index=False)["gap"].sum()
per_role = (
    per_employee.merge(roles[["role_id", "role_title"]], on="role_id")
    .groupby("role_title")["gap"]
    .mean()
    .sort_values(ascending=False)
)
print(per_role.round(2).to_string())
bar_chart(
    per_role.index,
    per_role.round(1).values,
    f"{per_role.index[0]}s have the largest gap to their own role",
    "Average total skill gap (levels) to the employee's current role",
    "06_avg_gap_by_role.png",
    horizontal=True,
    fmt="{:.1f}",
    xlabel="Average gap in levels",
)

# ---------------------------------------------------------------------------
heading("7. Course scores")
scores = history.loc[history["status"] == "Completed", "score"].dropna().astype(int)
bins = pd.cut(scores, bins=[49, 59, 69, 79, 89, 100], labels=["50-59", "60-69", "70-79", "80-89", "90-100"])
score_counts = bins.value_counts().sort_index()
print(scores.describe().round(1).to_string())
bar_chart(
    score_counts.index.astype(str),
    score_counts.values,
    f"Median score is {scores.median():.0f}",
    f"Completed enrolments by score band ({len(scores)} scores)",
    "07_score_distribution.png",
    value_label="Enrolments",
    xlabel="Score",
)

heading("Summary")
print(f"Charts saved in {out}")
print(f"- {len(emp)} employees in {emp['department'].nunique()} departments; largest: {per_dept.index[0]}.")
print(f"- {share_3_plus:.0%} of skill records are level 3+; most widespread skill: {top.index[0]}.")
print(f"- {completion_rate:.0%} of finished enrolments are completed.")
print(f"- Completion: {low:.0%} if the course fits the level, {high:.0%} if it starts 2+ levels higher.")
print(f"- Largest average gap to own role: {per_role.index[0]} ({per_role.iloc[0]:.1f} levels).")
