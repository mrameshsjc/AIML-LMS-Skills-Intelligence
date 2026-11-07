"""
13 - Predict: use the registered model, and see it inside API 3.

LESSON
    1. Ask the model directly: how likely is E1001 to complete each course?
    2. See how training recommendations (API 3) change when the model's
       completion_probability joins the score.

    The model gives a PROBABILITY (0-1), not a verdict. API 3 uses it as one
    of four score parts (15 %), next to gap coverage, level fit and
    prerequisites - so a learned signal adds to the rules without replacing them.

HOW TO RUN (from the project folder)
    PS> python data_science/13_predict.py
    PS> python data_science/13_predict.py --employee E1020

INPUT    the current model in models/ and the CSV files in --data
OUTPUT   printed predictions and recommendations
"""

import argparse
import sys

import pandas as pd
from _common import explain, heading

from app.ml.predict import CompletionPredictor
from app.repositories.csv_repository import CsvLmsRepository
from app.services.training_recommendation import TrainingRecommendationService

parser = argparse.ArgumentParser(description="Lesson 13: predict course completion.")
parser.add_argument("--employee", default="E1001")
parser.add_argument("--data", default="data/sample")
parser.add_argument("--models", default="models")
args = parser.parse_args()

predictor = CompletionPredictor.from_files(args.models, args.data)
if predictor is None:
    sys.exit("No registered model. Run: python data_science/10_split_data.py and 11_train_model.py")
repo = CsvLmsRepository(args.data)

heading(f"1. Completion probability for {args.employee} (model version {predictor.version})")
courses = ["C-SQL-201", "C-PY-201", "C-AWS-101", "C-AWS-201", "C-DOCKER-201", "C-MLOPS-201", "C-DL-301"]
features = predictor.features.features_for(args.employee, courses)
features.insert(0, "course_id", courses)
features["probability"] = [predictor(args.employee, c) for c in courses]
print(
    features[["course_id", "skills_too_advanced", "prereq_missing", "difficulty", "probability"]].to_string(
        index=False
    )
)
explain("""
Courses that start 2+ levels above the learner (skills_too_advanced >= 1) get a lower probability.
""")

heading("2. API 3 recommendations without and with the model")
without = TrainingRecommendationService(repo).recommend(args.employee)
with_model = TrainingRecommendationService(repo, completion_model=predictor).recommend(args.employee)
before = {r.course.course_id: (r.rank, r.score) for r in without.recommendations}
rows = [
    {
        "course": r.course.course_id,
        "rank before": before.get(r.course.course_id, ("-", None))[0],
        "score before": before.get(r.course.course_id, ("-", None))[1],
        "completion prob.": r.components["completion_probability"],
        "rank now": r.rank,
        "score now": r.score,
    }
    for r in with_model.recommendations
]
print(pd.DataFrame(rows).to_string(index=False))
print(f"\nWeights now: {with_model.weights_used}")
explain("""
With the model, all four parts count (0.50 / 0.20 / 0.15 / 0.15). Scores move a little; the order changes
only where courses were close. Mandatory gaps still come first. The API does this automatically once a
model is registered (restart uvicorn after training).
""")
