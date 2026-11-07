# data_science – step-by-step data pipeline scripts

**Filled in:** Phases 3, 4 and 8.

Numbered scripts you run in order to learn and check the data. Each has a beginner-friendly explanation at the top.

| Script | Phase |
| --- | --- |
| `01_read_csv.py` … `06_validate_duplicates.py` | 3 – read, inspect, schema, nulls, values, duplicates (**done**) |
| `07_clean_data.py`, `08_eda.py`, `15_data_quality_report.py` | 4 – clean, explore, report (**done**) |
| `09_feature_engineering.py` … `13_predict.py` | 8 – features, split, train, evaluate, predict (**done**) |
| `14_save_to_database.py` | 9 – load clean data into SQLite/MySQL |

`_common.py` holds shared helpers (imports, the `--data` option, printing). The checking logic itself lives in `app/data_processing/`, so the dashboard and API reuse exactly the same rules.

Run every script from the **project folder**, for example `python data_science/03_validate_schema.py --data data/raw/dirty`. A step-by-step guide is in `docs/DATA_PIPELINE_GUIDE.md`.
