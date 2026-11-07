# Dashboard Guide (Phase 15)

The Streamlit dashboard is the engine's user interface for the public demonstration: nine pages that cover every API, plus data upload and model management.

## 1. Run it

```powershell
pip install -r requirements.txt          # adds streamlit
streamlit run dashboard/Home.py           # from the project folder; opens http://localhost:8501
```

The dashboard does **not** need the API to be running: it uses the same services directly. Start uvicorn too if you also want Swagger. For the AI assistant and explanations, start Ollama; without it, a labelled fallback answers. Build the document index once with `python scripts/build_index.py`, or with **Rebuild now** on the Document management page.

With Docker: `docker compose up -d --build` starts the API (port 8000) and the dashboard (port 8501) from the same image, sharing the index, uploads and models.

## 2. The pages

| Page | What you can do | Behind it |
| --- | --- | --- |
| **Home** | Totals (100 employees, 13 roles, 42 skills, 80 courses), training completion (66.8 %), skill gaps toward career goals, the most often recommended courses | Skill analysis + recommendations for every employee with a goal |
| **Data upload** | Upload one of the 11 CSV files: dataset detection, preview, every issue with line numbers; save valid files to `data/uploads` | Phase 4 upload service |
| **Skills analysis** | Pick an employee and a target role: match %, gap score, a current-vs-required chart, current skills, suggestions | API 1 |
| **Role matching** | All roles ranked by match %; for one role, matching, missing and to-improve skills; similar roles | API 2 |
| **Recommendations** | Courses with skills, difficulty, hours, prerequisites (✓/✗), score; each with its reason and score parts | API 3 |
| **Learning path** | The courses in order, status, which step comes after which, course progress %, the next action; **Explain** asks the LLM | API 4 |
| **AI assistant** | Chat: answers with sources [S1]…, what was looked up ("understood as"), grounding warnings; example questions; conversation memory | API 5 |
| **Document management** *(admin)* | Index status, documents with origin and chunks, upload and ingest, delete uploads, rebuild the index | API 7 |
| **Model management** *(admin)* | Current version and test metrics vs baseline, the algorithm comparison, feature importance, versions with gate status, retraining runs, rollback, **controlled retraining** with the quality-gate result | API 6 workflow |

**The selected employee is remembered** across pages (sidebar), starting with E1001, the worked example from the requirements.

**Admin pages** show a notice: in Phase 15 every page is open; Phase 17 adds login and limits them to administrators.

## 3. How it is built

```
dashboard/
  Home.py, pages/N_Name.py   thin page scripts: widgets + layout
  components/data.py         service results -> tables (plain Python, unit-tested)
  components/ui.py           page setup, employee picker, error display
.streamlit/config.toml       theme colour, upload limit, no usage statistics
```

- **Same services as the API.** Pages get their services from `app.api.dependencies`, the same wiring FastAPI uses, so Swagger and the dashboard can never show different numbers. The requirement "the same service layer must be usable through FastAPI and the dashboard" is met literally.
- **No calculations in the dashboard.** `components/data.py` only reshapes results into DataFrames, for example "1 → 3" arrows and ✓/✗ prerequisites; it never computes a gap or a score itself.
- **How Streamlit works:** every click re-runs the page script from top to bottom. `st.session_state` keeps values between runs (the selected employee, the chat), and `@st.cache_data` keeps slow results (the Home summary, for 5 minutes).
- **Built-in charts only** (`st.bar_chart`, progress bars and columns): no extra charting library.

## 4. Testing the dashboard

| Test | What it checks | Runs |
| --- | --- | --- |
| `tests/unit/test_dashboard_data.py` | Every table helper against the known E1001 results | Everywhere |
| `tests/dashboard/test_pages.py` | Streamlit's **AppTest** runs each page headless: no errors, the right metrics (gap score 37.5, next action C-SQL-201), choosing another employee, a chat answer, the documents and model pages | With Streamlit installed (your PC, CI) |

```powershell
pytest tests/dashboard -v
```

AppTest runs a page script without a browser and lets the test read its metrics, select boxes and chat messages, change inputs and run it again.

## 5. Troubleshooting

| Problem | Fix |
| --- | --- |
| `ModuleNotFoundError: No module named 'app'` | Start Streamlit from the project folder: `streamlit run dashboard/Home.py` |
| `streamlit` is not recognised | `pip install -r requirements.txt` in the activated venv |
| The assistant answers "Fallback - no LLM" | Ollama is not running: see the sidebar note, or run `python scripts/check_llm.py` |
| Document management says "Not built" | Click **Rebuild now**, or run `python scripts/build_index.py` |
| A new model is not used by the API | The dashboard and the API are separate processes: restart uvicorn after retraining or rollback |
| Port 8501 is busy | `streamlit run dashboard/Home.py --server.port 8502` |
| The Home numbers look old | They are cached for 5 minutes: press **C** to clear the cache, then **R** to rerun |
