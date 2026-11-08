# ML Model Guide

This guide explains every algorithm the engine uses: why it was chosen, what the alternatives were, and how it works inside. Each section is added in the phase that introduces the technique.

| Technique | Used for | Phase | Status |
| --- | --- | --- | --- |
| Rule-based formula | Skill gaps, gap score, match % (APIs 1 and 2) | 5–6 | Done |
| TF-IDF + cosine similarity | Related roles (API 2) | 6 | Done |
| Hybrid scoring | Course recommendations (API 3) | 7 | Done |
| Greedy selection + topological sort | Learning path order (API 4) | 10 | Done |
| Controlled retraining + MLflow | Model updates with a quality gate (API 6) | 16 | Done |
| Logistic Regression / Random Forest | Course completion prediction (API 3) | 8 | Done |
| Sentence embeddings + FAISS | Document search for the AI assistant | 12 | Planned |
| LLM (Ollama) + RAG | AI assistant answers | 11–13 | Planned |

## 1. When to use ML, and when not to

**Use the simplest technique that gives a correct, explainable answer.**

| Question | Technique | Why |
| --- | --- | --- |
| How far is E1001 from Data Engineer? | A formula | The levels are known; the answer is arithmetic. A model would only add error and hide the reason |
| Which roles need similar skills? | TF-IDF + cosine similarity | Needs a sense of "similar", and should weigh distinctive skills more than common ones. Still fully explainable through the shared skills |
| Will this learner complete this course? | A trained classifier (Phase 8) | No formula is known; the pattern has to be learned from past enrolments |
| Answer a free-text question | LLM + retrieval (Phases 11–13) | Only a language model handles open questions; retrieval keeps it grounded in approved documents |

## 2. Skill gaps and match percentage (rule-based)

For each skill the role requires: R = required level, C = current level (0 if the employee lacks the skill), and w = weight.

```
gap          = max(0, R - C)
gap score    = 100 × Σ(w × gap) / Σ(w × R)          0 = role-ready
match %      = 100 × Σ(w × min(C, R)) / Σ(w × R)
```

- **`min(C, R)` gives no extra credit for being above the requirement.** Being an expert in Python cannot hide a missing AWS skill.
- **Weights are all 1.0 in the sample data.** The `importance_weight` column lets a business make some skills count more without changing code.
- **Code:** `compute_gaps()` in `app/services/skill_analysis.py`, shared by APIs 1 and 2.

## 3. Related roles: TF-IDF + cosine similarity

**Goal:** given a role (for example Data Engineer), find the roles whose skill requirements are most alike, as natural alternatives or next steps.

### Step 1: describe each role as a "document"
Each required skill ID is repeated as many times as its required level:

```
Data Engineer  (Python 4, SQL 4, AWS 3, ML 2, Docker 3)
-> "SK001 SK001 SK001 SK001 SK004 SK004 SK004 SK004 SK017 SK017 SK017 SK031 SK031 SK020 SK020 SK020"
```

A higher level means more repetitions, so the skill counts more.

### Step 2: TF-IDF turns each document into numbers
- **TF (term frequency):** how often a skill appears in this role, so it is high for skills required at a high level.
- **IDF (inverse document frequency):** how *rare* a skill is across all 13 roles. Skills that many roles need, such as Python or Communication, get a low IDF. Skills only a few roles need, such as MLOps, get a high IDF.
- **TF × IDF:** large for skills that are both important to the role and distinctive. Two roles that share a rare skill are more alike than two that share a skill everyone needs. A test proves this with a small hand-made example.

### Step 3: cosine similarity compares the number lists
It measures the angle between two roles' vectors: **1.0** means an identical skill profile and **0.0** means no skills in common. Because it uses the angle, not the length, a role with 9 requirements and one with 5 can still be very similar.

### Results on the sample data

| Role | Most similar role | Similarity |
| --- | --- | --- |
| Project Manager | Engineering Manager | 0.90 |
| Data Engineer | Machine Learning Engineer | 0.72 |
| Data Analyst | Data Scientist | 0.59 |
| Software Developer | Senior Software Developer | 0.56 |

### Why TF-IDF and not something bigger?

| Alternative | Why not here |
| --- | --- |
| Count shared skills | Ignores levels, and treats a skill every role needs as just as informative as a rare one |
| Plain vectors of levels + cosine | Close, but common skills dominate the score. IDF fixes that in one line |
| Sentence embeddings / LLM | Roles here are a structured skill list, not free text. Embeddings would need a model download and give a less explainable answer. They are used in Phase 12, where the input is free-text documents |

**Library:** scikit-learn. `TfidfVectorizer(token_pattern=r"\S+", lowercase=False)` treats each skill ID as one token, and `cosine_similarity` compares every pair.

**Code:** `app/services/role_similarity.py`. The index is built once and cached, so requests do not recompute it.

**Limits:**
- Similarity is based only on required skills, so two roles in different departments can be similar.
- With only 13 roles, scores move noticeably when one role's requirements change.
- This is synthetic data: the results show the method, not real labour-market facts.

### How to improve it later
- Add the job family or department as extra tokens so related roles stay within career tracks.
- Use real `importance_weight` values (repeat tokens by weight × level).
- With hundreds of roles from a real LMS, keep TF-IDF but compute only the top N neighbours per role.

## 4. Course recommendations: hybrid scoring

**Goal:** for each skill gap, find the courses that close it best, and say why.

**Why a hybrid of rules (not one ML model):** each part answers a question a learner or manager can check: does the course close my gap, does it start at my level, am I ready for it? A single model score would be harder to trust and impossible to explain. The one part that has to be learned, completion probability, is plugged in from the Phase 8 model as an extra signal.

| Part | Weight | Formula | Why it matters |
| --- | --- | --- | --- |
| Gap coverage | 0.50 | Σ gain / Σ gap over the course's gap skills, where gain = min(course_to, required) − max(current, course_from) | The main purpose of training is to close the gap |
| Level fit | 0.20 | Above the learner by *n*: 1 − 0.5n. Below by *n*: 1 − 0.2n, at least 0.5 | Phase 4 EDA: completion falls from 74% to 41% when a course starts 2+ levels too high |
| Prerequisite readiness | 0.15 | Share of prerequisites completed, or covered by the learner's current level | A course whose prerequisites are missing is not the next step |
| Completion probability | 0.15 | Phase 8 model (section 5) | Learned from past enrolments |

**Missing parts are not treated as zero.** Until the completion model exists, its weight is redistributed proportionally: 0.50/0.85, 0.20/0.85 and 0.15/0.85. Treating it as zero would lower every score without telling anyone why. The response lists the `weights_used` and a note.

**Why "covered by your current level" counts as meeting a prerequisite.** Someone with Docker at level 2 should not be told to take *Docker Fundamentals* (0→2) first. Checking the prerequisite course's `level_to` against the learner's actual level avoids pointless repetition.

**Ordering:** mandatory gaps first, then the score. A business rule that a skill is mandatory outranks a slightly better fit for an optional skill.

**Code:** `app/services/training_recommendation.py`. Small pure functions (`useful_gain`, `level_fit`, `combine`) are tested on their own.

**Tuning:** the weights are in `WEIGHTS` at the top of the file. Change them in one place, run the tests, and the API docs explain the effect.

**Limits:**
- Scores rank courses for one person; they are not comparable across different people.
- Course duration and delivery mode are shown but not scored. A preference for short or online courses could be added as a fifth part later.

## 5. Course completion: a trained classifier

**Question:** will this learner complete this course? No formula is known, so the pattern is learned from 443 finished past enrolments (Completed = 1, Dropped = 0; 66.8 % completed). API 3 uses the predicted probability as its fourth score part.

### Features (11, built in `app/ml/features.py`)

| Feature | Meaning | Why |
| --- | --- | --- |
| `level_jump` | How far the course starts above the learner (largest over its skills) | Too-hard courses are dropped |
| `skills_too_advanced` | How many course skills start **2+ levels** above the learner | EDA showed a *threshold*: completion falls from 74 % to 41 % at a jump of 2. A linear model cannot find a threshold in `level_jump`, so this feature gives it directly |
| `prereq_count`, `prereq_missing` | Prerequisites, and those neither completed before nor covered by the learner's level | Missing foundations |
| `duration_hours` | Course length | Longer courses are harder to finish |
| `relevant_to_career` | 1 if the course raises a skill of the current or target role | Motivation |
| `prior_completed`, `prior_dropped` | The learner's earlier outcomes | Past behaviour |
| `difficulty`, `delivery_mode`, `seniority` | Categories (one-hot encoded) | Context |

### No data leakage
A feature may only use what was known **before** the enrolment. `score`, `attempts` and `completed_date` exist only after the outcome, so they are not features. The history features count only enrolments with an earlier `enrolled_date`. Tests check both rules.

Known limit: skill levels are a single snapshot (latest assessment), not the level at enrolment time. With real LMS history, use the level recorded at the enrolment date.

### Method
1. **Stratified 80/20 split** (seed 42): 354 training rows, 89 test rows, both with about 67 % completed. The test rows are not used until the end.
2. **Three candidates**, each a scikit-learn `Pipeline` (StandardScaler for numbers + OneHotEncoder for categories + model), so the same preparation runs at training and prediction time:
   - Logistic Regression: a weighted sum turned into a probability; easy to explain.
   - Decision Tree (max depth 4): a short flowchart of yes/no questions.
   - Random Forest (200 trees): many trees voting; strong but harder to explain.
3. **5-fold cross-validation** on the training rows; the best mean **ROC AUC** wins.
4. The winner is trained on all training rows, evaluated once on the test rows, and saved to the registry.

**Why ROC AUC?** API 3 uses the probability to *rank* courses, and ROC AUC measures exactly that: how often a completer gets a higher probability than a dropper (0.5 = coin flip, 1.0 = perfect). Accuracy is misleading here: always saying "completes" is already 66 % accurate.

### Results on the synthetic data

| Model | CV ROC AUC (mean ± std) |
| --- | --- |
| **Logistic Regression** | **0.637 ± 0.033** |
| Random Forest | 0.603 ± 0.044 |
| Decision Tree | 0.585 ± 0.045 |

| Test metric (89 unseen rows) | Model | Always "completes" |
| --- | --- | --- |
| ROC AUC | **0.693** | 0.500 |
| Accuracy | 0.685 | 0.663 |
| Precision / Recall / F1 | 0.701 / 0.915 / 0.794 | – |

The simplest model wins. With few rows and an outcome driven by a few simple effects, the extra flexibility of the trees does not help and makes their scores less stable (larger std). The strongest coefficient is `skills_too_advanced` (−0.66): one too-advanced skill clearly lowers the probability. For E1001: `C-AWS-101` 0.80, `C-SQL-201` 0.59, `C-MLOPS-201` 0.44.

**Honest reading:** the synthetic outcomes were generated from simple rules **plus randomness**, so a modest ROC AUC is the expected, correct result. The model demonstrates the method, not real-world accuracy, and every model card says `"synthetic_data": true`.

**Read coefficients with care.** Features that move together share their effect: `prereq_count` (−0.49) and `prereq_missing` (+0.24) should be read as a pair, and `difficulty_Advanced` comes out *positive* although Advanced courses complete less often (52 %), because `skills_too_advanced` already carries that penalty. A coefficient shows what the model uses, not a cause.

### Model registry (`app/ml/model_registry.py`)
Each training run saves a **new version** and never overwrites an old one:
`models/completion_model_vN.joblib` (the pipeline), `completion_model_vN.json` (model card: algorithm, date, features, CV and test metrics, seed), and the pointer `completion_model.json`. Roll back with `set_current(1)`. Phase 16 replaces this with MLflow; the idea stays the same.

### How API 3 uses it
`get_completion_predictor()` in `app/api/dependencies.py` loads the current version once at start-up (restart uvicorn after training). If there is no model, or `USE_COMPLETION_MODEL=false`, the API still works and shares the 15 % weight among the other three parts. The ranking changes only where courses were close, because the model is one signal among four.

### Alternatives considered

| Alternative | Why not now |
| --- | --- |
| Gradient boosting (XGBoost, LightGBM) | Strong on large tables; with 354 rows it would overfit like the forest, and it adds a dependency |
| Class weights / resampling | Useful when the minority class matters most. API 3 ranks by probability, so the threshold is not used |
| Time-based split | More realistic for real LMS data (train on older enrolments, test on newer). Recommended once real history exists |

### Limits and how to improve
- 443 rows: results change noticeably with a different seed. Real LMS history would give far more.
- Probabilities are not calibrated; check with a calibration curve before showing them as percentages to users.
- Retrain when new enrolment outcomes arrive (Phase 16 adds an admin-only `/ml/retrain` API with MLflow tracking).

**Code:** `app/ml/` (`features`, `train`, `evaluate`, `model_registry`, `predict`). **Scripts:** `data_science/09`–`13`. **Tests:** `tests/unit/test_completion_model.py`.

## 6. Learning path: greedy selection + topological sort

**Goal:** turn ranked courses into a plan, the courses that close every gap, in an order the learner can follow.

### Step 1: choose the courses (a greedy "climb")
For each gap skill, mandatory and largest first, start at the learner's level and repeat until the required level is reached:
1. Candidates are active courses that raise this skill above the current level and are not completed.
2. Prefer a course the learner can **start**: it begins at or below their level at that point. Otherwise take the one starting lowest.
3. Then prefer a course they are **already enrolled in** (finish what you started), then the one closing **most of the gap**, then the best **API 3 score**.
4. Assume the course brings every skill it teaches to its `level_to`, and climb on.

Example, AWS 1 → 3: `C-AWS-101` (0→2) can start now; then `C-AWS-201` (2→4) can start at 2 and finishes the gap.

**Why greedy?** Each choice can be explained in one sentence ("starts at your level and closes the most of the gap"). An optimiser, for example minimum total hours, might find a slightly shorter plan, but not one a learner could check. The sweep test runs all 100 employees × 13 roles (1,300 paths, under one second) and checks that every gap is either closed or reported.

### Step 2: add missing prerequisites
A chosen course whose prerequisite is not satisfied (not completed, not covered by the learner's level, the same rule as API 3) pulls the prerequisite into the path, recursively.

### Step 3: order with a topological sort
The courses and their "must come before" links form a **directed acyclic graph** (DAG):
- a prerequisite comes before the course that needs it;
- a lower course on the same skill comes before a higher one.

A **topological sort** lists the nodes so that every link points forward. Kahn's algorithm repeats: among the courses whose predecessors are all placed, pick the most urgent. Urgency is the API 3 order (mandatory first, then score), and a prerequisite inherits the urgency of the course that needs it, so it is placed just in time. If the data ever contained a loop, the sort would place the remaining courses anyway rather than fail; the Phase 3 validation already rejects prerequisite loops.

### Completed courses as evidence
In the synthetic data, as in real LMS data, a skill record is sometimes lower than the courses a person has completed. For example, `C-PY-101` (Python 0→2) is completed but the Python record says 0. The climb then allows courses starting at the completed course's `level_to`, explains this in the step's reason, and suggests a re-assessment. Gap and match numbers keep using the recorded levels, so APIs 1–4 report the same figures.

**Code:** `app/services/learning_path.py`. **Tests:** `tests/unit/test_learning_path.py` (E1001 example, the 1,300-path sweep, prerequisites, in-progress courses, evidence, uncovered skills).

**Limits:**
- The plan is sequential. It does not schedule courses in parallel or by calendar dates.
- "Completing a course brings the skill to `level_to`" is an assumption. Real progress should be confirmed by assessment.

## 7. Controlled retraining and MLflow (Phase 16)

**Goal:** retrain the completion model when new LMS data arrives, but let a new model into production **only if it is good enough**. A model that quietly got worse would make every recommendation worse without anyone noticing.

### The workflow (`app/ml/retraining.py`)

```
new data → validate → features → train (3 algorithms, 5-fold CV) → evaluate on unseen test rows
        → compare with the CURRENT model on the SAME rows → quality gate
        → register the version (always) → promote (only if approved) → MLflow → history
```

| Step | What happens | Stops when |
| --- | --- | --- |
| 1. Validate data | The checks from scripts 03–06 | Any error, so no model is trained on broken data |
| 2. Features | Training table as in section 5 | Fewer than `ML_MIN_TRAINING_ROWS` (200), or one outcome under 10 % |
| 3–4. Train, evaluate | Best of three algorithms; test metrics | – |
| 5. Compare | The current model is evaluated on the **same** test rows | – (skipped if there is no current model) |
| 6. Quality gate | `minimum_quality`: ROC AUC ≥ `ML_MIN_ROC_AUC` (0.60). `better_than_chance`: ROC AUC > 0.5. `no_regression`: not more than `ML_MAX_REGRESSION` (0.01) below the current model | – |
| 7. Register | A new version is **always** saved, with `status: approved` or `rejected` in its card | – |
| 8. Promote | Only an approved version becomes current (and only if `promote=true`) | – |
| 9. MLflow | Parameters, metrics, the model card, the model file; approved models registered | Never blocks: a tracking error is reported, the model is kept |
| 10. History | One line in `models/retraining_history.jsonl` | – |

**Why compare on the same rows?** Each run draws its own test rows. Comparing the new model's score on its rows with the old model's score on *other* rows would mix model quality with luck. Evaluating both on the new test rows makes the comparison fair.

**Why save rejected versions?** The history should show every attempt, not only the successes: what was tried, when, by whom, and why it failed.

**Results:** with the sample data, the first run is promoted (ROC AUC 0.693, the gate's floor is 0.60). A second run on the same data gives the same model (same seed), so `no_regression` passes with a change of +0.000. With `ML_MIN_ROC_AUC=0.95` the run is `rejected_by_quality_gate`: the new version is saved, but the current model stays in use.

### MLflow (`app/ml/tracking.py`)

MLflow keeps the **experiment record**:

| MLflow concept | What the engine stores |
| --- | --- |
| Experiment | `completion-model` (`MLFLOW_EXPERIMENT`) |
| Run | One per retraining: tags (status, requested_by, local_version), parameters (algorithm, seed, features, row counts), metrics (test metrics, each algorithm's CV ROC AUC, the current model's score), `model_card.json`, the model file |
| Registered model | `completion_model`: one MLflow version per **approved** model, tagged `local_version`, with the alias **`champion`** on the version in use |

The **API keeps loading models from `models/`**. That is fast, works offline and needs no MLflow server; MLflow is the history and audit trail around it. The `local_version` tag links the two.

**Store:** by default a SQLite file `mlruns/mlflow.db`, with model files in `mlruns/artifacts` (git-ignored). Set `MLFLOW_TRACKING_URI` for a shared MLflow server.

**View the runs:**
```powershell
mlflow ui --backend-store-uri sqlite:///mlruns/mlflow.db      # then open http://127.0.0.1:5000
```

**Without MLflow** (`MLFLOW_ENABLED=auto` and the package not installed, or `false`), retraining works exactly the same and the result says that MLflow was not used.

### Who may retrain
Only an administrator. API 6 requires the header `X-Admin-Key` matching `ADMIN_API_KEY`. Without a configured key, retraining through the API is switched off. The dashboard's Model page and `scripts/retrain.py` run on the server itself; Phase 17 adds login to the dashboard.

**After a promotion via API 6**, the API uses the new model from the next request, with no restart. After retraining from the dashboard or the script (separate processes), restart the API.

**Code:** `app/ml/retraining.py`, `app/ml/tracking.py`, `app/core/security.py`. **Tests:** `tests/unit/test_retraining.py` (the gate, rejection paths, history, lock, a real MLflow store when installed), `tests/api/test_ml_api.py`.
