# API Documentation

The engine exposes seven business endpoints under `/api/v1`. They are stable contracts: the models, data source and LLM behind them can change without changing these requests and responses.

| # | Method and path | Status |
| --- | --- | --- |
| – | `GET /api/v1/health` | Live (Phase 1) |
| 1 | `POST /api/v1/skills/analyze` | **Live (Phase 5)** |
| 2 | `POST /api/v1/roles/match` | **Live (Phase 6)** |
| 3 | `POST /api/v1/trainings/recommend` | Phase 7 |
| 4 | `GET /api/v1/learning-path/{employee_id}` | Phase 10 |
| 5 | `POST /api/v1/ai/chat` | Phase 13 |
| 6 | `POST /api/v1/ml/retrain` | Phase 16 |
| 7 | `POST /api/v1/rag/ingest` | Phase 13 |

**Try it:** start the server with `uvicorn app.main:app --reload` and open **http://127.0.0.1:8000/docs**. Every endpoint has a description, request examples, response examples and error examples there.

Authentication arrives in Phase 17. Until then, all endpoints are open and serve synthetic data only.

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
