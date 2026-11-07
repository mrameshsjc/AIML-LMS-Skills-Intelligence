"""
12 - Evaluate the model on the test set it has never seen.

LESSON
    The test rows were locked away in script 10. Now we find out how the
    registered model really performs, and compare it with a BASELINE that
    always says "completes" (about 67 % accurate, ROC AUC 0.5).

      accuracy    share of right predictions (threshold 0.5)
      precision   predicted "completes" -> how often right
      recall      real completers -> how many found
      f1          balance of precision and recall
      roc_auc     ranking quality - what API 3 relies on

    Then: which features does the model rely on? (feature importance)

BE HONEST ABOUT THE RESULT
    The data is synthetic: completion was generated from simple rules PLUS
    randomness. The model can only rediscover those rules, so a modest score
    (ROC AUC around 0.7) is expected and correct. It demonstrates the method;
    it says nothing about real employees.

HOW TO RUN (from the project folder)
    PS> python data_science/12_evaluate_model.py

INPUT    data/processed/ml/test.csv and the current model in models/
OUTPUT   printed metrics and reports/ml/feature_importance.png
"""

import argparse
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from _common import explain, heading  # noqa: E402

from app.data_processing.loader import resolve_folder  # noqa: E402
from app.ml.evaluate import evaluate, feature_importance  # noqa: E402
from app.ml.model_registry import load_current  # noqa: E402

parser = argparse.ArgumentParser(description="Lesson 12: evaluate the completion model.")
parser.add_argument("--folder", default="data/processed/ml", help="folder with test.csv")
parser.add_argument("--models", default="models", help="model registry folder")
parser.add_argument("--out", default="reports/ml", help="folder for the chart")
args = parser.parse_args()

loaded = load_current(args.models)
test_file = resolve_folder(args.folder) / "test.csv"
if loaded is None or not test_file.exists():
    sys.exit("No model or test set. Run scripts 10 and 11 first.")
pipeline, card = loaded
test = pd.read_csv(test_file)

heading(f"1. Test metrics - {card['algorithm']} version {card['version']} on {len(test)} unseen rows")
m = evaluate(pipeline, test)
rows = [
    ("accuracy", m["accuracy"], m["baseline_accuracy"]),
    ("roc_auc", m["roc_auc"], m["baseline_roc_auc"]),
    ("precision", m["precision"], None),
    ("recall", m["recall"], None),
    ("f1", m["f1"], None),
]
print(pd.DataFrame(rows, columns=["metric", "model", "always 'completes'"]).to_string(index=False))
better = m["roc_auc"] > m["baseline_roc_auc"]
explain(f"""
ROC AUC {m["roc_auc"]} vs 0.5 for the baseline: the model {"DOES" if better else "does NOT"} rank
completers above droppers better than chance. Accuracy is close to the baseline because most
enrolments complete anyway - that is why accuracy alone is misleading for unbalanced data.
""")

heading("2. Confusion matrix (threshold 0.5)")
cm = m["confusion_matrix"]
print(
    pd.DataFrame(
        [[cm["true_negative"], cm["false_positive"]], [cm["false_negative"], cm["true_positive"]]],
        index=["really dropped", "really completed"],
        columns=["predicted dropped", "predicted completed"],
    ).to_string()
)
explain("""
Many dropped enrolments are predicted 'completed' (false positives): with only a weak signal, the model
leans towards the majority class. For API 3 this is fine - it uses the PROBABILITY to rank courses,
not the yes/no answer.
""")

heading("3. What does the model rely on?")
importance = feature_importance(pipeline)
print(importance.head(10).to_string(index=False))
kind = importance.columns[1]
explain("""
For logistic regression these are coefficients: negative = makes completion LESS likely. Expect
skills_too_advanced near the top with a negative value - the rule found by EDA. Coefficients of
features that move together are unreliable one by one: prereq_count and prereq_missing go as a pair,
and difficulty_Advanced can come out POSITIVE although Advanced courses complete less often (52 %),
because skills_too_advanced already carries that penalty. Never read one coefficient alone as cause.
""")

top = importance.head(10).iloc[::-1]
fig, ax = plt.subplots(figsize=(8, 4.6), dpi=120)
fig.patch.set_facecolor("#fcfcfb")
ax.set_facecolor("#fcfcfb")
ax.barh(top["feature"], top[kind], height=0.6, color="#2a78d6")
ax.axvline(0, color="#52514e", linewidth=0.8)
ax.xaxis.grid(True, color="#e4e3df")
ax.set_axisbelow(True)
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.tick_params(colors="#52514e", labelsize=9)
ax.set_xlabel(
    kind.capitalize() + (" (negative = less likely to complete)" if kind == "coefficient" else ""),
    color="#52514e",
)
fig.suptitle(
    f"What the {card['algorithm'].replace('_', ' ')} relies on",
    x=0.02,
    ha="left",
    fontsize=12,
    fontweight="bold",
    color="#0b0b0b",
)
fig.tight_layout()
out = resolve_folder(args.out)
out.mkdir(parents=True, exist_ok=True)
fig.savefig(out / "feature_importance.png", facecolor="#fcfcfb")
print(f"\nChart saved: {out / 'feature_importance.png'}  ->  next: python data_science/13_predict.py")
