# data – datasets (synthetic only)

| Folder | Holds | In Git? |
| --- | --- | --- |
| `sample/` | The 11 synthetic CSV files (Phase 2 – **done**). Column-by-column guide: `docs/DATA_DICTIONARY.md` | Yes |
| `raw/` | Files as uploaded, before cleaning | No |
| `processed/` | Cleaned files from `07_clean_data.py`, plus `cleaning_log.csv` and `rejected_rows.csv` | No |
| `uploads/` | Files uploaded through the dashboard or API; `uploads/documents/` holds documents added with API 7 (Phase 13) | No |

The SQLite database file (`lms_ai.db`) is also created here from Phase 9 and is not committed.

**No real employee data may be stored in this project.**
