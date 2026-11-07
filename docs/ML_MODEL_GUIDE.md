# ML Model Guide

This guide explains every algorithm the engine uses: why it was chosen, what the alternatives were, and how it works inside. Each section is added in the phase that introduces the technique.

| Technique | Used for | Phase | Status |
| --- | --- | --- | --- |
| Rule-based formula | Skill gaps, gap score, match % (APIs 1 and 2) | 5–6 | Done |
| TF-IDF + cosine similarity | Related roles (API 2) | 6 | Done |
| Hybrid scoring | Course recommendations (API 3) | 7 | Done |
| Logistic Regression / Random Forest | Course completion prediction | 8 | Planned |
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
'''

## 4. Course recommendations: hybrid scoring

**Goal:** for each skill gap, find the courses that close it best, and say why.

**Why a hybrid of rules (not one ML model):** each part answers a question a learner or manager can check: does the course close my gap, does it start at my level, am I ready for it? A single model score would be harder to trust and impossible to explain. The one part that has to be learned, completion probability, is plugged in from the Phase 8 model as an extra signal.

| Part | Weight | Formula | Why it matters |
| --- | --- | --- | --- |
| Gap coverage | 0.50 | Σ gain / Σ gap over the course's gap skills, where gain = min(course_to, required) − max(current, course_from) | The main purpose of training is to close the gap |
| Level fit | 0.20 | Above the learner by *n*: 1 − 0.5n. Below by *n*: 1 − 0.2n, at least 0.5 | Phase 4 EDA: completion falls from 74% to 41% when a course starts 2+ levels too high |
| Prerequisite readiness | 0.15 | Share of prerequisites completed, or covered by the learner's current level | A course whose prerequisites are missing is not the next step |
| Completion probability | 0.15 | Phase 8 model | Learned from past enrolments |

**Missing parts are not treated as zero.** Until the completion model exists, its weight is redistributed proportionally: 0.50/0.85, 0.20/0.85 and 0.15/0.85. Treating it as zero would lower every score without telling anyone why. The response lists the `weights_used` and a note.

**Why "covered by your current level" counts as meeting a prerequisite.** Someone with Docker at level 2 should not be told to take *Docker Fundamentals* (0→2) first. Checking the prerequisite course's `level_to` against the learner's actual level avoids pointless repetition.

**Ordering:** mandatory gaps first, then the score. A business rule that a skill is mandatory outranks a slightly better fit for an optional skill.

**Code:** `app/services/training_recommendation.py`. Small pure functions (`useful_gain`, `level_fit`, `combine`) are tested on their own.

**Tuning:** the weights are in `WEIGHTS` at the top of the file. Change them in one place, run the tests, and the API docs explain the effect.

**Limits:**
- Scores rank courses for one person; they are not comparable across different people.
- Course duration and delivery mode are shown but not scored. A preference for short or online courses could be added as a fifth part later.
