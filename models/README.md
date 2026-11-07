# models – trained model files

**Filled in:** Phase 8. Generated files, **not committed to Git** (only this README is).

Create a model with `python data_science/11_train_model.py` (after scripts 09 and 10). Every run adds a new version:

| File | What it is |
| --- | --- |
| `completion_model_v1.joblib`, `_v2.joblib`, … | The trained scikit-learn pipeline (preprocessing + model) |
| `completion_model_v1.json`, … | Its model card: algorithm, date, features, cross-validation and test metrics, `synthetic_data: true` |
| `completion_model.json` | Pointer to the version the API uses |

Roll back: `python -c "from app.ml.model_registry import set_current; set_current(1)"`, then restart the API.
No model? API 3 still works and shares the 15 % completion weight among its other score parts.
From Phase 16, MLflow tracks the runs and only approved models are promoted.
