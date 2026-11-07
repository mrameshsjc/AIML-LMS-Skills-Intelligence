# app/database – SQLite connection, migrations and tables

**Filled in:** Phase 9. Uses Python's built-in `sqlite3` (nothing to install).

| File | Purpose |
| --- | --- |
| `connection.py` | `connect(DATABASE_URL)`: a configured connection (foreign keys on, rows by column name). Only `sqlite:///` URLs in this version |
| `migrate.py` | Runs the numbered SQL files in `migrations/` that a database has not run yet (recorded in `schema_migrations`) |
| `migrations/0001_create_lms_tables.sql` | The 11 LMS tables, with primary keys, foreign keys, CHECK rules and indexes |
| `tables.py` | `save_datasets()` and `read_datasets()`: DataFrames ↔ tables, with identical types both ways |

Create the database with `python data_science/14_save_to_database.py`. The full explanation is in [`docs/DATABASE_GUIDE.md`](../../docs/DATABASE_GUIDE.md).
