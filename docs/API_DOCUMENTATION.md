# API Documentation

The engine exposes seven business endpoints under `/api/v1`. They are stable contracts: the models, data source and LLM behind them can change without changing these requests and responses.

| # | Method and path | Status |
| --- | --- | --- |
| – | `GET /api/v1/health` | Live (Phase 1) |
| – | `GET /api/v1/health/llm` | Live (Phase 11): is Ollama running, is the model installed? |
| – | `GET /api/v1/health/rag` | Live (Phase 12): is the document index built, what does it contain? |
| – | `POST /api/v1/auth/token`, `GET /api/v1/auth/me` | Live (Phase 17): login and "who am I" |
| 1 | `POST /api/v1/skills/analyze` | **Live (Phase 5)** |
| 2 | `POST /api/v1/roles/match` | **Live (Phase 6)** |
| 3 | `POST /api/v1/trainings/recommend` | **Live (Phase 7)** |
| 4 | `GET /api/v1/learning-path/{employee_id}` | **Live (Phase 10)** |
| 5 | `POST /api/v1/ai/chat` | **Live (Phase 13)** |
<<<<<<< HEAD
| 6 | `POST /api/v1/ml/retrain` (+ `GET /api/v1/ml/status`) | **Live (Phase 16)**, administrators only |
| 7 | `POST /api/v1/rag/ingest` (+ `GET`, `DELETE /api/v1/rag/documents`) | **Live (Phase 13)**, upload/delete administrators only |
=======
| 6 | `POST /api/v1/ml/retrain` (+ `GET /api/v1/ml/status`) | **Live (Phase 16)**, admin key |
| 7 | `POST /api/v1/rag/ingest` (+ `GET`, `DELETE /api/v1/rag/documents`) | **Live (Phase 13)** |
>>>>>>> 3b18c7963333b5c28c29ad72afd8a9d2c7e5e314

**Try it:** start the server with `uvicorn app.main:app --reload` and open **http://127.0.0.1:8000/docs**. Every endpoint has a description, request examples, response examples and error examples there.

## Authentication (Phase 17)

Full details: [`SECURITY_GUIDE.md`](SECURITY_GUIDE.md).

| Server setting | APIs 1–5 | API 6, API 7 upload/delete |
| --- | --- | --- |
| `AUTH_ENABLED=false` (local default) | open | header `X-Admin-Key: <ADMIN_API_KEY>` |
| `AUTH_ENABLED=true` | header `Authorization: Bearer <token>`; employee = own data, manager = team, admin = everyone | admin's token **or** `X-Admin-Key` |

Get a token: `POST /api/v1/auth/token` with a **form** body `username=...&password=...` (in Swagger: the **Authorize** button).

```json
{"access_token": "eyJhbGciOi...", "token_type": "bearer", "expires_in": 3600, "role": "employee", "employee_id": "E1001"}
```

`GET /api/v1/auth/me` returns `username`, `role`, `employee_id`, `tenant`, `authenticated`, `can_view` (`everyone` / `team` / `self`) and `auth_enabled`. With login on, API 5 without `employee_id` answers personal questions about the logged-in employee. Health checks and `GET /api/v1/ml/status` stay open. Rate limits: 120 requests/minute per IP, assistant 20/minute, admin actions 10/hour, login 10/minute.

## Errors (all endpoints)

Every error has the same shape, so a client needs only one piece of error-handling code:

```json
{"error": {"code": "EMPLOYEE_NOT_FOUND", "message": "Employee E9999 does not exist.", "request_id": "3f2a9c1e"}}
```

| HTTP | Code | When |
| --- | --- | --- |
| 404 | `EMPLOYEE_NOT_FOUND`, `ROLE_NOT_FOUND`, `NOT_FOUND` | An ID in the request, or the URL, does not exist |
| 422 | `VALIDATION_ERROR` | A field has the wrong format. `details` lists every bad field |
| 422 | `UNKNOWN_SKILL`, `INVALID_LEVEL` | A what-if skill does not exist, or a level is outside 0–5 |
| 422 | `INVALID_ROLE_ID` | An entry in `role_ids` is not like `R004` |
<<<<<<< HEAD
| 401 | `AUTH_REQUIRED`, `INVALID_TOKEN`, `TOKEN_EXPIRED`, `ACCOUNT_DISABLED` | Login is on and the token is missing, invalid, expired, or its account is gone |
| 401 | `INVALID_CREDENTIALS` | Login: wrong username or password |
| 401 | `ADMIN_AUTH_REQUIRED` | API 6/7 admin actions: no valid `X-Admin-Key` or admin login |
| 403 | `ACCESS_DENIED` | Another employee's data (also for unknown IDs, for non-admins) |
| 403 | `ADMIN_ONLY` | Logged in, but not an administrator |
| 403 | `ADMIN_ACTIONS_DISABLED` | Login off and no `ADMIN_API_KEY` configured, so admin actions are off |
| 403 | `AUTH_DISABLED`, `WRONG_TENANT` | Login while login is off; an account of another organisation |
| 429 | `RATE_LIMITED` | Too many requests; the `Retry-After` header says how many seconds to wait |
=======
| 401 | `ADMIN_AUTH_REQUIRED` | API 6: the `X-Admin-Key` header is missing or wrong |
| 403 | `ADMIN_ACTIONS_DISABLED` | API 6: no `ADMIN_API_KEY` is configured on the server, so admin actions are off |
>>>>>>> 3b18c7963333b5c28c29ad72afd8a9d2c7e5e314
| 409 | `RETRAINING_IN_PROGRESS` | API 6: another retraining run is still running |
| 409 | `DOCUMENT_EXISTS`, `DUPLICATE_DOCUMENT`, `DOCUMENT_IS_APPROVED` | API 7: the name is taken (send `overwrite=true`), the same content exists under another name, or an approved document would be changed |
| 413 | `FILE_TOO_LARGE` | API 7: the upload exceeds `RAG_MAX_UPLOAD_MB` |
| 422 | `UNSUPPORTED_FILE_TYPE`, `EMPTY_FILE`, `INVALID_DOCUMENT` | API 7: not .pdf/.docx/.txt/.csv/.md, empty, or no readable text |
| 422 | `FILE_CONTENT_MISMATCH`, `INJECTION_SUSPECTED` | API 7: the content does not match the extension (e.g. a renamed program); text that tries to instruct the assistant |
| 503 | `INDEX_BUILD_FAILED` | API 7: the index could not be rebuilt (the change is rolled back) |
| 503 | `LLM_UNAVAILABLE` | API 4 `explain=true` or API 5 with `LLM_PROVIDER=ollama` while Ollama is down (with `auto`, the fallback answers instead) |
| 500 | `INTERNAL_ERROR` | Unexpected. The details are in the server log, findable by `request_id` |

Every response carries an `X-Request-ID` header. Send your own `X-Request-ID` (as the LMS will later) and it is reused, so one ID follows a request across systems.

## API 1 – Skills analysis

`POST /api/v1/skills/analyze`

Compares an employee's current skill levels with the levels a target role requires.

### Request

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `employee_id` | text | yes | `E` + 4 digits, e.g. `E1001` |
| `target_role_id` | text | no | `R` + 3 digits. If omitted: the employee's career goal, or else their current role |
| `current_skills` | list | no | What-if levels for this analysis only: `[{"skill": "SQL", "level": 4}]`. `skill` is a name (any letter case) or an ID; `level` is 0–5, where 0 means "does not have it". At most 50 items |

```json
{"employee_id": "E1001", "target_role_id": "R004"}
```

### Response (200)

| Field | Meaning |
| --- | --- |
| `employee_id`, `employee_name` | Who was analysed |
| `current_role`, `target_role` | `{role_id, title}` |
| `target_source` | `request`, `career_goal` or `current_role`: where the target came from |
| `skills` | Every skill the target role requires, most urgent first (mandatory, then largest gap). Each has `current_level`, `required_level`, `gap`, `mandatory` and `status` (`met`, `below_required` or `missing`) |
| `skill_profile` | All skills the employee has, with `required_for_target` |
| `missing_skills` | Required skills at level 0 |
| `gap_score` | 100 × Σ(weight × gap) / Σ(weight × required). **0 = role-ready** |
| `match_percentage` | 100 × Σ(weight × min(current, required)) / Σ(weight × required) |
| `mandatory_gaps` | How many mandatory skills are below the required level |
| `role_ready` | `true` when there are no gaps |
| `suggestions` | One action per gap, most urgent first |
| `summary` | One-sentence explanation |
| `overrides_applied` | What-if levels used, e.g. `["SQL = 4"]` |
| `engine_version` | Version of the engine that produced the answer |

**Worked example** (E1001 → Data Engineer):

| Skill | Current | Required | Gap | Mandatory |
| --- | --- | --- | --- | --- |
| AWS | 1 | 3 | 2 | yes |
| SQL | 2 | 4 | 2 | yes |
| Python | 3 | 4 | 1 | yes |
| Docker | 2 | 3 | 1 | no |
| Machine Learning | 2 | 2 | 0 | no |

- **Required total:** 4 + 4 + 3 + 2 + 3 = 16.
- **Gaps:** 1 + 2 + 2 + 0 + 1 = 6, so `gap_score` = 100 × 6 / 16 = **37.5**.
- **Covered:** 3 + 2 + 1 + 2 + 2 = 10, so `match_percentage` = 100 × 10 / 16 = **62.5**.

```json
{
  "employee_id": "E1001",
  "employee_name": "Arjun Krishnan",
  "current_role": {"role_id": "R001", "title": "Software Developer"},
  "target_role": {"role_id": "R004", "title": "Data Engineer"},
  "target_source": "request",
  "skills": [
    {"skill_id": "SK017", "skill": "AWS", "category": "Cloud & DevOps", "current_level": 1, "required_level": 3, "gap": 2, "mandatory": true, "status": "below_required"},
    {"skill_id": "SK004", "skill": "SQL", "category": "Programming", "current_level": 2, "required_level": 4, "gap": 2, "mandatory": true, "status": "below_required"}
  ],
  "missing_skills": [],
  "gap_score": 37.5,
  "match_percentage": 62.5,
  "mandatory_gaps": 3,
  "role_ready": false,
  "suggestions": [
    "Raise AWS (mandatory) from level 1 to 3.",
    "Raise SQL (mandatory) from level 2 to 4.",
    "Raise Python (mandatory) from level 3 to 4.",
    "Raise Docker from level 2 to 3."
  ],
  "summary": "Arjun Krishnan meets 1 of 5 skill requirements for Data Engineer; 4 need improvement (3 mandatory). Match 62.5%, gap score 37.5 (0 = role-ready).",
  "overrides_applied": [],
  "engine_version": "0.1.0"
}
```
(The `skills` list is shortened here; the real response has all 5 skills, plus `skill_profile`.)

**What-if:** send `"current_skills": [{"skill": "SQL", "level": 4}, {"skill": "Python", "level": 4}, {"skill": "AWS", "level": 3}, {"skill": "Docker", "level": 3}]` and the response shows `"role_ready": true` and `"gap_score": 0.0`. Stored data is never changed.

### Try it from PowerShell
```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/skills/analyze `
  -ContentType "application/json" -Body '{"employee_id": "E1001", "target_role_id": "R004"}'
```

### How it works inside
`app/api/v1/skills.py` (HTTP only) → `SkillAnalysisService.analyze()` in `app/services/skill_analysis.py` (the logic) → `LmsRepository` (data). Today the repository is `CsvLmsRepository`, reading the folder named by `DATA_DIR`, which defaults to `data/sample`. The pure function `compute_gaps()` is shared with API 2, so both APIs always give the same numbers.

## API 2 – Job role matching

`POST /api/v1/roles/match`

Scores an employee against every job role (or a chosen list), ranks them, explains each match, and suggests related roles.

### Request

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `employee_id` | text | yes | `E` + 4 digits |
| `role_ids` | list | no | Compare only these roles, e.g. `["R002", "R004"]`. Default: all 13 roles. Repeats are ignored |
| `target_role_id` | text | no | A role of special interest. It is always returned in `target`, even outside the top N, and related roles are found for it. Default: the employee's career goal |
| `top_n` | number | no | How many ranked roles to return, 1–20. Default 5 |
| `current_skills` | list | no | What-if levels, exactly as in API 1 |

```json
{"employee_id": "E1001"}
```

### Response (200)

| Field | Meaning |
| --- | --- |
| `matches` | The top N roles, best first. Each has `rank`, `match_percentage`, `gap_score`, `readiness`, `is_current_role`, `is_career_goal`, `matching_skills`, `needs_improvement` and `missing_skills` (each with current and required level), `mandatory_gaps` and `explanation` |
| `target` | The target role's result, with its `rank` among all compared roles (0 = not among them) |
| `related_to`, `related_roles` | Roles whose required skills are most similar to the target, or to the best non-current role if there is no target. Each has `similarity` (0–1), `shared_skills` and `employee_match_percentage` |
| `career_goal`, `current_role`, `roles_considered`, `summary`, `overrides_applied`, `engine_version` | As named |

**Ranking:** highest `match_percentage` first. Ties go to fewer mandatory gaps, then alphabetical order.

**Readiness:**

| Label | Match % |
| --- | --- |
| Ready | 100 |
| Close | 80–99 |
| Developing | 50–79 |
| Early | below 50 |

The match percentage is computed with the same formula and code as API 1, so `/roles/match` and `/skills/analyze` always agree.

### Example (E1001)

| Rank | Role | Match | Readiness | Note |
| --- | --- | --- | --- | --- |
| 1 | Software Developer | 100% | Ready | current role |
| 2 | QA Engineer | 62.5% | Developing | 2 mandatory gaps |
| 3 | Data Engineer | 62.5% | Developing | career goal, 3 mandatory gaps |
| 4 | Senior Software Developer | 50% | Developing | |
| 5 | Machine Learning Engineer | 43.5% | Early | |

Summary: *"Arjun Krishnan's best match is Software Developer (current role) at 100%. Best other role: QA Engineer at 62.5% (Developing). Target Data Engineer: 62.5% (Developing, rank 3 of 13)."*

Related to Data Engineer:

| Role | Similarity | Shared skills | E1001's match |
| --- | --- | --- | --- |
| Machine Learning Engineer | 0.72 | Python, SQL, AWS, Docker, Machine Learning | 43.5% |
| Data Scientist | 0.39 | Python, SQL, Machine Learning | 30.4% |
| Senior Software Developer | 0.36 | Python, SQL, Docker | 50% |

How the similarity is computed is explained in [`ML_MODEL_GUIDE.md`](ML_MODEL_GUIDE.md).

### Try it from PowerShell
```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/roles/match `
  -ContentType "application/json" -Body '{"employee_id": "E1001", "top_n": 3}'
```

## API 3 – Training recommendations

`POST /api/v1/trainings/recommend`

Recommends courses that close an employee's skill gaps for a target role. Each course comes with a score, the parts of that score, and a reason.

### Request

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `employee_id` | text | yes | `E` + 4 digits |
| `target_role_id` | text | no | Default: the career goal, else the current role (as in API 1) |
| `skills` | list | no | Only recommend for these skills (names or IDs). Default: every gap |
| `max_results` | number | no | 1–30, default 10 |
| `include_enrolled` | true/false | no | Default `true`. With `false`, courses the employee is already enrolled in are left out |

```json
{"employee_id": "E1001"}
```

### Which courses are considered
- **Included:** active courses that raise at least one of the employee's gap skills by at least one level.
- **Excluded:** courses the employee has already **completed**.
- **Flagged:** courses the employee is enrolled in, or dropped before, keep their `enrollment_status`, and the reason mentions it.

### The score
```
score = 0.50 × gap_coverage + 0.20 × level_fit + 0.15 × prereq_ready + 0.15 × completion_probability
```

| Part | Meaning | Example |
| --- | --- | --- |
| `gap_coverage` | Share of the gap in the course's skills that it closes. Gain per skill = min(course_to, required) − max(current, course_from) | SQL 2→4 needed, course 2→4: 2/2 = **1.0**. AWS 1→3 needed, course 0→2: 1/2 = **0.5** |
| `level_fit` | 1.0 when the course starts at your level. Starts *n* levels above you: 1 − 0.5n. Starts *n* below (revision): 1 − 0.2n, at least 0.5 | AWS-201 starts at 2, you are at 1: **0.5** |
| `prereq_ready` | Share of prerequisites that are completed **or** already covered by your skill level | Docker-101 ends at level 2 and you have Docker 2: satisfied |
| `completion_probability` | Probability (0–1) from the Phase 8 completion model | C-SQL-201 for E1001: **0.59** |

**Without a model** (none trained yet, or `USE_COMPLETION_MODEL=false`), `completion_probability` is `null` and its 15% weight is shared proportionally among the other three parts: `weights_used` = 0.588 / 0.235 / 0.176. **With a model** (train it with `data_science/11_train_model.py`, then restart the API), all four weights are used and `notes` names the model version and that it was trained on synthetic data. For E1001 the order stays the same; C-SQL-201 scores 0.94 instead of 1.00. The model is explained in [`ML_MODEL_GUIDE.md`](ML_MODEL_GUIDE.md) section 5.

**Order:** courses that address a **mandatory** gap come first; within each group, the highest score first. A perfect course for an optional skill therefore appears after courses for mandatory skills.

### Response (200)

| Field | Meaning |
| --- | --- |
| `recommendations` | `rank`, course details, `skills_covered` (current, required, course_from, course_to, gap_closed), `prerequisites` (`satisfied`, `how`), `score`, `components`, `addresses_mandatory_gap`, `enrollment_status`, `reason` |
| `skill_gaps` | The gaps considered, e.g. `"SQL 2->4 (mandatory)"` |
| `uncovered_skills` | Gap skills that no available course can close |
| `weights_used`, `notes` | How the score was combined, plus anything to be aware of |
| `target_role`, `target_source`, `gap_score`, `match_percentage` | As in API 1 |

### Example (E1001 → Data Engineer)

| Rank | Course | Score | Coverage | Fit | Prereqs | Why |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | C-SQL-201 SQL for Data Engineering | 1.00 | 1.0 | 1.0 | 1.0 | SQL 2→4 exactly; C-SQL-101 completed |
| 2 | C-PY-201 Python for Practitioners | 0.95 | 1.0 | 0.8 | 1.0 | Python 3→4; starts at 2, so part of it is revision |
| 3 | C-AWS-101 AWS Cloud Foundations | 0.66 | 0.5 | 0.8 | 1.0 | Closes 1 of the 2 AWS levels |
| 4 | C-AWS-201 AWS for Data and Application Workloads | 0.41 | 0.5 | 0.5 | 0.0 | Starts above AWS 1; complete C-AWS-101 first |
| 5 | C-DOCKER-201 Docker in Production | 1.00 | 1.0 | 1.0 | 1.0 | Docker is not mandatory, so it is listed after the mandatory gaps |

Reason for rank 1: *"Your SQL is level 2 and Data Engineer needs level 4; this course takes it from level 2 to 4. Prerequisites met (C-SQL-101 completed)."*

The order in which to take these courses (AWS-101 before AWS-201) is the job of the learning path, API 4.

### Try it from PowerShell
```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/trainings/recommend `
  -ContentType "application/json" -Body '{"employee_id": "E1001"}'
```

## API 4 – Personalised learning path

`GET /api/v1/learning-path/{employee_id}`

API 3 ranks courses one by one; API 4 turns them into a **plan**: the courses that close every gap, in an order the learner can follow, with progress and one next action. It reads data and changes nothing, so it is a `GET` and the options are query parameters.

### Request

| Part | Type | Default | Meaning |
| --- | --- | --- | --- |
| `employee_id` (path) | `E` + 4 digits | – | The employee |
| `target_role_id` (query) | `R` + 3 digits | career goal, else current role | Role to prepare for |
| `include_optional` (query) | bool | `true` | `false` plans for mandatory skills only |
| `explain` (query) | bool | `false` | Add a plain-language `explanation` written by the language model (Phase 11) |

Example: `/api/v1/learning-path/E1001?target_role_id=R004&include_optional=false`

### How the path is built
1. **Gaps, scores and reasons** come from API 3, so the two APIs never disagree.
2. **Select:** for each gap skill (mandatory and largest first), climb from the current level to the required one. At each step, take a course the learner can start (it begins at or below their level at that point), preferring a course they are already enrolled in, then the one closing most of the gap, then the best API 3 score. A course raising several skills counts for all of them.
3. **Prerequisites:** a chosen course whose prerequisite is not yet satisfied pulls that prerequisite into the path (`purpose: prerequisite`).
4. **Order:** prerequisites, and lower courses on the same skill, always come first. Otherwise the API 3 order decides: mandatory gaps first, then score. A prerequisite takes the priority of the course that needs it, so it appears just before it.
5. **Never included:** completed and inactive courses. Courses in progress stay, with their `status`.

**Completed courses count as evidence.** If someone completed `C-PY-101` (Python 0→2) but their skill record still says 0, the path lets them start `C-PY-201` (from level 2), and a note suggests a skill re-assessment. The gap and match numbers still use the recorded levels, as in APIs 1–3. The synthetic data has many such records, as real LMS data often does.

### Response (200)

| Field | Meaning |
| --- | --- |
| `current_role`, `target_role`, `target_source` | As in API 1 |
| `current_skills` | Every skill the employee has, with `required_for_target` |
| `skill_gaps` | Each gap with `closed_by` (path courses that raise it) and `level_after_path` |
| `path` | The steps: `step`, course details, `purpose`, `status`, `raises` (skill from→to), `prerequisites`, `after_steps`, `ready_now`, `addresses_mandatory_gap`, `score` (API 3), `reason`, `cumulative_hours` |
| `progress` | `match_percentage` now, `projected_match_percentage` after the path, `skills_met` / `skills_required`, `completed_courses` relevant to the target, `in_progress_courses`, `total_steps`, `total_hours` |
| `next_action` | The first step that can be started now (or "Continue …" for a course already started) |
| `uncovered_skills`, `notes` | Gaps no available course fully closes; model, data and option notes |
| `explanation` | Only with `explain=true`: `text`, `provider` / `model`, the `facts` the model was given, `grounding_warnings`, `notes`, `duration_ms`. `null` otherwise |

### Example (E1001 → Data Engineer)

| Step | Course | Hours | After | Why |
| --- | --- | --- | --- | --- |
| 1 | C-SQL-201 SQL for Data Engineering | 21 | – | SQL 2→4, mandatory |
| 2 | C-PY-201 Python for Practitioners | 19 | – | Python 3→4, mandatory |
| 3 | C-AWS-101 AWS Cloud Foundations | 14 | – | AWS 1→2, mandatory |
| 4 | C-AWS-201 AWS for Data and Application Workloads | 19 | step 3 | AWS 2→3; needs C-AWS-101 |
| 5 | C-DOCKER-201 Docker in Production | 17 | – | Docker 2→3, optional |

Progress: match **62.5 %** now, **100 %** after 5 steps (90 hours). Next action: *"Enrol in C-SQL-201 'SQL for Data Engineering' (step 1, 21 h). …"*

Other cases:
- Target already met (`?target_role_id=R001`): empty path, "You already meet every requirement…".
- A requirement above every course in the catalogue (Advanced Excel level 4 for R003): listed in `uncovered_skills`, with the level the path reaches.
- No career goal: the current role is used, and a note says to pass `target_role_id`.

### Try it from PowerShell
```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/learning-path/E1001
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/learning-path/E1001?target_role_id=R009"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/learning-path/E1001?explain=true"
```

**The explanation (Phase 11).** With `explain=true`, the path is turned into short factual lines (first name, roles, gaps, steps, next action). The language model then writes a friendly paragraph from those lines only, and the answer is checked for course IDs and numbers that are not in the facts. Without a running model (`LLM_PROVIDER=auto`), a labelled fallback lists the facts instead. Check the model with `GET /api/v1/health/llm`. Details: [`LLM_RAG_GUIDE.md`](LLM_RAG_GUIDE.md).

### How it works inside
`app/api/v1/learning_path.py` (HTTP only) → `LearningPathService.build()` in `app/services/learning_path.py`, which reuses `TrainingRecommendationService` for gaps, scores and the shared prerequisite rule. The algorithm is explained in [`ML_MODEL_GUIDE.md`](ML_MODEL_GUIDE.md) section 6.

## API 5 – LMS AI assistant

`POST /api/v1/ai/chat`

Answers questions about skills, roles, courses, learning paths and the learning policies. Answers come from **LMS data** and **approved documents**, with sources, and the assistant says when it does not know.

### Request

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `question` | text, 2–1000 characters | – | The question |
| `employee_id` | `E` + 4 digits | none | Needed for questions about your own gaps, path and recommendations |
| `history` | list of `{role: user\|assistant, content}`, up to 20 | `[]` | Earlier turns; the last 6 are given to the model |

```json
{"question": "Why was C-AWS-201 recommended?", "employee_id": "E1001"}
```

### How a question is answered
1. **Understand** with simple, visible rules (returned as `intents`):

| Found in the question | Intent | Facts added |
| --- | --- | --- |
| "my", "I", "me" (or, with an `employee_id`, words like *recommended*, *next*, *gaps*, *path*) | `my_learning_path` | The learning path (API 4): gaps, steps, progress, next action. Toward the role named in the question, if any. "Why" questions also get each step's reason |
| A job role title or ID ("AI Engineer", "R007") | `role_requirements` | Mandatory and optional skills with levels |
| A skill name ("Python") | `skill_courses` | Courses that raise it (above your level when `employee_id` is given) |
| A course ID ("C-SQL-201") | `course_details` | Level, hours, skills, prerequisites, your status |
| – | `documents` | Passages from the document search, labelled `[S1]`, `[S2]` … |

2. **Retrieve** document passages. A passage is kept if its score is at least the minimum for the embedder (`RAG_MIN_SCORE`; default TF-IDF 0.08, Ollama 0.45) **and** at least half the best passage's score.
3. **Refuse** when there are no facts and no relevant passages: *"I don't have information about that…"* (`provider: none`, no model is called).
4. **Answer:** the language model writes the answer from the facts only and cites `[S1]` etc. A short follow-up ("And a second attempt?") is searched together with the previous question.
5. **Check:** `grounding_warnings` lists course IDs, numbers or `[S#]` citations that are not in the facts.

### Response (200)

| Field | Meaning |
| --- | --- |
| `answer` | The answer (from the fallback: the facts and passages as a labelled list) |
| `provider`, `model`, `is_fallback` | `ollama` + model, `fallback`, or `none` (nothing found) |
| `intents` | What the question was understood to need (table above) |
| `sources` | `label`, `source`, `title`, `section`, `page`, `score`, `excerpt` (≤ 300 characters) |
| `facts` | The LMS data given to the model |
| `grounding_warnings`, `notes`, `duration_ms` | Checks, explanations (for example, why the fallback was used), time taken |

### Examples (requirements' questions)

| Question | `employee_id` | Intents | Answer is based on |
| --- | --- | --- | --- |
| What skills do I need to become a Data Engineer? | E1001 | my_learning_path, documents | Path toward Data Engineer + role profile |
| Which courses should I complete next? | E1001 | my_learning_path, documents | Path steps and next action |
| Why was C-AWS-201 recommended? | E1001 | my_learning_path, course_details, documents | The step's reason (AWS 1 → 3, after C-AWS-101) |
| What are my current skill gaps? | E1001 | my_learning_path, documents | The gaps |
| Which skills are required for an AI Engineer? | – | role_requirements, documents | Python 4, LLM Applications 4, Prompt Engineering 3 (mandatory) |
| Explain my learning path. | E1001 | my_learning_path, documents | The path |
| What training should I complete to improve my Python skills? | E1001 | my_learning_path, skill_courses, documents | Python level 3; C-PY-201, C-PY-301 |
| How many learning hours do I have per year? | – | documents | [S1] faq.md, [S2] learning_policy.md: 40 hours |
| What is the capital of France? | – | – | "I don't have information about that…" |

### Try it from PowerShell
```powershell
$body = @{ question = "What are my current skill gaps?"; employee_id = "E1001" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/ai/chat -ContentType "application/json" -Body $body
python scripts/ask.py "Which skills are required for an AI Engineer?"     # the same, from the command line
python scripts/ask.py --employee E1001                                    # a conversation
```

## API 7 – Knowledge document ingestion

| Method and path | Purpose |
| --- | --- |
| `POST /api/v1/rag/ingest` | Upload a document (multipart form: `file`, optional `overwrite`) |
| `GET /api/v1/rag/documents` | List indexed documents with origin, pages, chunks, fingerprint, and skipped files |
| `DELETE /api/v1/rag/documents/{source}` | Delete an uploaded document |

### What happens on upload
1. **Name:** only the file name is kept; unsafe characters become `_` (`../../app/main.md` → `main.md`).
2. **Checks:** `.pdf`, `.docx`, `.txt`, `.csv` or `.md`; not empty; at most `RAG_MAX_UPLOAD_MB` (default 10).
3. **Conflicts:**
   - an approved base document (in `documents/`) can never be replaced or deleted through the API: 409 `DOCUMENT_IS_APPROVED`;
   - an uploaded name that already exists needs `overwrite=true` (a **document update**): 409 `DOCUMENT_EXISTS`;
   - the same content under another name: 409 `DUPLICATE_DOCUMENT` (**duplicate detection** by SHA-256).
4. **Text extraction** happens first: a damaged or scanned file is refused (422 `INVALID_DOCUMENT`) before anything is stored.
5. **Store and rebuild:** the file goes to `RAG_UPLOAD_DIR` (default `data/uploads/documents`, kept on the Docker data volume) and the index is rebuilt: clean → chunk → embed → FAISS. If the rebuild fails, the change is rolled back (503 `INDEX_BUILD_FAILED`).
6. The API reloads the index at once: the next question can use the new document.

**CSV files:** each row becomes a line such as `training: Kafka Essentials; provider: External Partner; hours: 12.`, so tables can be searched.

### Response (200, for upload and delete)

| Field | Meaning |
| --- | --- |
| `status` | `added`, `updated` or `deleted` |
| `source`, `title`, `pages`, `chunks`, `sha256` | The document and its fingerprint |
| `index` | `documents`, `chunks`, `embedder`, `embedding_model`, `backend`, `seconds` after the rebuild |
| `notes` | The rebuild summary and any skipped files |

### Try it from PowerShell 7
```powershell
"training,provider,hours`nKafka Essentials,External Partner,12" | Set-Content internal_trainings.csv
$admin = @{ "X-Admin-Key" = "<your ADMIN_API_KEY>" }
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/rag/ingest -Headers $admin -Form @{ file = Get-Item internal_trainings.csv }
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/rag/documents
Invoke-RestMethod -Method Delete -Uri http://127.0.0.1:8000/api/v1/rag/documents/internal_trainings.csv -Headers $admin
```
With Windows PowerShell 5.1 (no `-Form`), use the `curl.exe` built into Windows:
```powershell
curl.exe -H "X-Admin-Key: <key>" -F "file=@internal_trainings.csv" http://127.0.0.1:8000/api/v1/rag/ingest
curl.exe -H "X-Admin-Key: <key>" -F "file=@internal_trainings.csv" -F "overwrite=true" http://127.0.0.1:8000/api/v1/rag/ingest
```
In Swagger UI: **7. Knowledge Documents → POST /api/v1/rag/ingest → Try it out → Choose file**.

<<<<<<< HEAD
**Security (Phase 17):** uploading and deleting are for administrators (admin login or `X-Admin-Key`); listing needs only a login. Uploads are refused when the content does not match the extension or contains text that tries to instruct the assistant. RAG ingestion is separate from ML retraining (API 6) and does not change the language model.
=======
**Security:** Phase 17 restricts API 7 to administrators. RAG ingestion is separate from ML retraining (API 6) and does not change the language model.
>>>>>>> 3b18c7963333b5c28c29ad72afd8a9d2c7e5e314

## API 6 – ML model retraining

`POST /api/v1/ml/retrain` — **administrators only** · `GET /api/v1/ml/status` — open

Runs the controlled retraining workflow: validate the data → features → train → evaluate → compare with the current model → quality gate → register → promote if approved → MLflow. Details: [`ML_MODEL_GUIDE.md`](ML_MODEL_GUIDE.md) section 7.

### Authentication
<<<<<<< HEAD
Either log in as an administrator (`Authorization: Bearer <token>`, when `AUTH_ENABLED=true`) or send the administrator key in a header: `X-Admin-Key: <ADMIN_API_KEY>`. Set the key in `.env` and restart the server:
=======
Send the administrator key in a header: `X-Admin-Key: <ADMIN_API_KEY>`. Set the key in `.env` and restart the server:
>>>>>>> 3b18c7963333b5c28c29ad72afd8a9d2c7e5e314

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"     # copy the output into .env as ADMIN_API_KEY=...
```

| Situation | Response |
| --- | --- |
<<<<<<< HEAD
| Login off and no `ADMIN_API_KEY` on the server | 403 `ADMIN_ACTIONS_DISABLED` |
| Key wrong, or no key and no admin login | 401 `ADMIN_AUTH_REQUIRED` |
| Logged in as employee or manager | 403 `ADMIN_ONLY` |
| More than `RATE_LIMIT_ADMIN_PER_HOUR` attempts | 429 `RATE_LIMITED` |
| Correct key or admin login | 200 with the report |
=======
| No `ADMIN_API_KEY` on the server | 403 `ADMIN_ACTIONS_DISABLED` |
| Header missing or wrong | 401 `ADMIN_AUTH_REQUIRED` |
| Correct key | 200 with the report |
>>>>>>> 3b18c7963333b5c28c29ad72afd8a9d2c7e5e314

### Request

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `reason` | text, ≤ 500 characters | `""` | Kept in the retraining history |
| `promote` | bool | `true` | `false` registers the new version but keeps the current one |

### Response (200)

| Field | Meaning |
| --- | --- |
| `status` | `promoted`, `registered_not_promoted`, `rejected_by_quality_gate` or `rejected_invalid_data` |
| `gate_passed`, `quality_gate` | Each check: `minimum_quality`, `better_than_chance`, `no_regression`, with `passed` and a readable `detail` |
| `previous_version`, `new_version`, `current_version` | Before the run, saved by the run (`null` if stopped before training), in use after the run |
| `data_validation` | `errors`, `warnings`, the first `issues` |
| `training` | `rows` (total/train/test), the winning `algorithm`, the `cross_validation` table |
| `new_metrics`, `current_metrics` | The new model's test metrics, and the current model's on the **same** test rows |
| `mlflow` | `enabled`, `run_id`, `registered_version`, `tracking_uri` |
| `requested_by`, `reason`, `started_at`, `duration_seconds`, `notes` | Audit trail and explanations |

After `promoted`, API 3 uses the new model from the next request.

`GET /api/v1/ml/status` returns the `current_version`, every saved version (with `status` approved/rejected and test ROC AUC), the latest `recent_runs`, the quality-gate settings, the MLflow setting, and whether admin actions are enabled.

### Try it from PowerShell
```powershell
$headers = @{ "X-Admin-Key" = "<your ADMIN_API_KEY>" }
$body = @{ reason = "New training history" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/ml/retrain -Headers $headers -ContentType "application/json" -Body $body
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/ml/status
python scripts/retrain.py --reason "New training history"       # the same workflow from the command line
```
In Swagger UI: **6. ML Model Management → POST /api/v1/ml/retrain → Try it out**, and enter the key in the `x-admin-key` field.
