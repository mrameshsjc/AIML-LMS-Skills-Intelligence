"""
09 - Feature engineering: turn LMS data into model inputs.

LESSON
    A model cannot read "employee E1001 took C-SQL-201". It needs numbers and
    categories that describe each enrolment, plus the answer it should learn
    (completed = 1, dropped = 0). Choosing those inputs - "features" - is
    usually the most important step in machine learning.

    This script builds one row per FINISHED enrolment (completed or dropped)
    with 11 features. Each one is explained in app/ml/features.py, and the
    table printed below shows how completion varies with the key ones.

    Watch for DATA LEAKAGE: features may only use what was known BEFORE the
    enrolment. The score or the completion date would make the model look
    perfect in testing and useless in practice, so they are not features.

HOW TO RUN (from the project folder)
    PS> python data_science/09_feature_engineering.py

INPUT    the 11 CSV files in --data (default data/sample)
OUTPUT   data/processed/ml/features.csv (one row per finished enrolment)
"""

import argparse

from _common import explain, heading

from app.data_processing.loader import load_all, resolve_folder
from app.ml.features import CATEGORICAL_FEATURES, FEATURES, LABEL, NUMERIC_FEATURES, FeatureBuilder

parser = argparse.ArgumentParser(description="Lesson 09: feature engineering.")
parser.add_argument("--data", default="data/sample", help="folder with the CSV files (default data/sample)")
parser.add_argument("--out", default="data/processed/ml", help="folder for features.csv")
args = parser.parse_args()

table = FeatureBuilder(load_all(args.data)).training_table()
out = resolve_folder(args.out)
out.mkdir(parents=True, exist_ok=True)
table.to_csv(out / "features.csv", index=False, lineterminator="\n")

heading("1. The feature table")
print(table.head(5).to_string(index=False))
print(f"\n{len(table)} finished enrolments x {len(FEATURES)} features (+ the label '{LABEL}')")
print(f"Numeric features:     {', '.join(NUMERIC_FEATURES)}")
print(f"Categorical features: {', '.join(CATEGORICAL_FEATURES)}")

heading("2. The label: what the model learns to predict")
rate = table[LABEL].mean()
print(
    f"completed = 1 in {table[LABEL].sum()} rows ({rate:.1%}); dropped = 0 in {(1 - table[LABEL]).sum()} rows"
)
explain("""
The classes are not balanced: about two thirds completed. A lazy model that always says "completes"
would already be right about 2 times in 3. Script 12 compares our model with exactly that baseline.
""")

heading("3. Does each feature relate to completion?")
explain("Completion rate per value of a few key features (only values with 10+ enrolments shown).")
for feature in ["skills_too_advanced", "prereq_missing", "difficulty", "relevant_to_career"]:
    grouped = table.groupby(feature)[LABEL].agg(rate="mean", enrolments="size")
    grouped = grouped[grouped["enrolments"] >= 10]
    print(f"\n{feature}:")
    print(grouped.to_string(formatters={"rate": "{:.0%}".format}))
explain("""
skills_too_advanced = number of the course's skills that start 2+ levels above the learner.
Completion drops sharply when it is 1 or more - the threshold found by EDA (script 08, chart 05).
It was added as its own feature because a linear model cannot discover a threshold by itself.
""")

heading("4. Saved")
print(f"{out / 'features.csv'}  ->  next: python data_science/10_split_data.py")
