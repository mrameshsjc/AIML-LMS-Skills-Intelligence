"""
10 - Split the data into a training set and a test set.

LESSON
    A model must be judged on data it has NEVER seen, just as a student is
    tested with new questions, not the ones they practised. So we set 20 % of
    the rows aside as a TEST set and never use them for training or choosing.

    STRATIFIED split: both parts keep the same share of completed enrolments
    (about 67 %), so the test is fair. A fixed random seed (42) makes the split
    identical on every machine.

    Why not split by date? A time-based split (train on older enrolments,
    test on newer) is even more realistic and worth trying with real LMS
    data. With 443 synthetic rows, a stratified random split is the clearer
    first lesson.

HOW TO RUN (from the project folder)
    PS> python data_science/10_split_data.py

INPUT    data/processed/ml/features.csv (built by script 09 if missing)
OUTPUT   data/processed/ml/train.csv and test.csv
"""

import argparse

import pandas as pd
from _common import explain, heading

from app.data_processing.loader import load_all, resolve_folder
from app.ml.features import LABEL, FeatureBuilder
from app.ml.train import SEED, split_data

parser = argparse.ArgumentParser(description="Lesson 10: train/test split.")
parser.add_argument("--data", default="data/sample", help="raw data, used only if features.csv is missing")
parser.add_argument("--folder", default="data/processed/ml", help="folder with features.csv")
args = parser.parse_args()

folder = resolve_folder(args.folder)
features_file = folder / "features.csv"
if features_file.exists():
    table = pd.read_csv(features_file)
else:
    print("features.csv not found - building it (script 09 does this step with explanations).")
    table = FeatureBuilder(load_all(args.data)).training_table()
    folder.mkdir(parents=True, exist_ok=True)
    table.to_csv(features_file, index=False, lineterminator="\n")

train, test = split_data(table)
train.to_csv(folder / "train.csv", index=False, lineterminator="\n")
test.to_csv(folder / "test.csv", index=False, lineterminator="\n")

heading(f"Train / test split (80 % / 20 %, stratified, seed {SEED})")
summary = pd.DataFrame(
    {
        "rows": [len(table), len(train), len(test)],
        "completed share": [table[LABEL].mean(), train[LABEL].mean(), test[LABEL].mean()],
    },
    index=["all", "train", "test"],
)
print(summary.to_string(formatters={"completed share": "{:.1%}".format}))
explain("""
The completed share is (almost) the same in all three rows: that is what 'stratified' means.
The test rows are now locked away until script 12.
""")
print(f"\nSaved train.csv and test.csv in {folder}")
print("Next: python data_science/11_train_model.py")
