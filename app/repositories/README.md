# app/repositories – where data is read

**Filled in:** Phase 5 (CSV) and Phase 9 (SQLite).

| File | Purpose |
| --- | --- |
| `base.py` | `LmsRepository`: the interface (abstract class) the services depend on |
| `csv_repository.py` | Reads the CSV files in `DATA_DIR` once into memory (default data source) |
| `sqlite_repository.py` | Answers the same questions with SQL from the database at `DATABASE_URL` (`DATA_SOURCE=database`) |

Tests prove both repositories give identical answers. Why it matters: swapping the data source (for example, the real LMS database later) means adding one new repository, not rewriting the business logic.
