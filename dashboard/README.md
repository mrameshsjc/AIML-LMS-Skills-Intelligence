# dashboard – Streamlit user interface

**Filled in:** Phase 15. Run from the project folder: `streamlit run dashboard/Home.py` → http://localhost:8501

The dashboard calls the same `app/services` as the API (through `app.api.dependencies`), so its numbers always match Swagger. It does not need the API to be running.

| File | Shows |
| --- | --- |
| `Home.py` | Totals, training completion, skill-gap summary, recommendation statistics |
| `pages/1_Data_Upload.py` | Check an LMS CSV file: detection, preview, issues; save valid files |
| `pages/2_Skills_Analysis.py` | One employee's skills, a target role's requirements, gaps, match % (API 1) |
| `pages/3_Role_Matching.py` | Roles ranked by match %; matching, missing and to-improve skills; similar roles (API 2) |
| `pages/4_Recommendations.py` | Courses with skills, difficulty, prerequisites, score parts and reasons (API 3) |
| `pages/5_Learning_Path.py` | Ordered courses, status, progress %, next action, LLM explanation (API 4) |
| `pages/6_AI_Assistant.py` | Chat with sources, intents and grounding warnings (API 5) |
| `pages/7_Document_Management.py` | Index status, upload/ingest, delete, rebuild (API 7) – admin |
| `pages/8_Model_Management.py` | Model versions, metrics, comparison, feature importance, rollback, retraining – admin |
| `components/data.py` | Plain functions that turn service results into tables (unit-tested, no Streamlit) |
| `components/ui.py` | Page setup, employee picker (remembered across pages), error display |

Guide: [`docs/DASHBOARD_GUIDE.md`](../docs/DASHBOARD_GUIDE.md).
