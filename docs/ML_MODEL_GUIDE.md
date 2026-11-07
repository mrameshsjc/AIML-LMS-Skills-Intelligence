# ML Model Guide

This guide explains every algorithm the engine uses: why it was chosen, what the alternatives were, and how it works inside. Each section is added in the phase that introduces the technique.

| Technique | Used for | Phase | Status |
| --- | --- | --- | --- |
| Rule-based formula | Skill gaps, gap score, match % (APIs 1 and 2) | 5–6 | Done |
| TF-IDF + cosine similarity | Related roles (API 2) | 6 | Done |
| Hybrid scoring | Course recommendations (API 3) | 7 | Done |
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
