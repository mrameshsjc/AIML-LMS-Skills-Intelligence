# app/repositories – where data is read and written

**Filled in:** Phase 5 (CSV) and Phase 9 (SQL).

| Planned file | Purpose |
| --- | --- |
| `base.py` | Interfaces (abstract classes) the services depend on (**done**) |
| `csv_repository.py` | Reads the CSV files in `DATA_DIR` (**done**) |
| `sql_repository.py` | Reads and writes SQLite or MySQL through SQLAlchemy |

Why: swapping the data source later (for example, the real LMS database) means adding one new repository, not rewriting the business logic.
