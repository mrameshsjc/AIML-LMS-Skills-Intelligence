# app/database – database connection and tables

**Filled in:** Phase 9.

| Planned file | Purpose |
| --- | --- |
| `connection.py` | Engine and session from `DATABASE_URL` (SQLite by default, MySQL optional) |
| `models.py` | SQLAlchemy table classes (employees, skills, roles, courses, AI-owned tables) |

Schema changes are versioned with Alembic in the top-level `migrations/` folder.
