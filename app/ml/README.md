# app/ml – machine learning engine

**Filled in:** Phase 8 (course-completion model). Phase 16 adds MLflow tracking and the retraining API.

| File | Purpose |
| --- | --- |
| `features.py` | `FeatureBuilder`: one row per finished enrolment with 11 features and the label `completed`. Only past enrolments count (no leakage) |
| `train.py` | Stratified 80/20 split, 5-fold cross-validation of Logistic Regression / Decision Tree / Random Forest, `run_training()` for the whole workflow |
| `evaluate.py` | Test metrics against an "always completes" baseline, confusion matrix, feature importance |
| `model_registry.py` | File-based registry in `models/`: versioned `.joblib` + `.json` model card, a pointer to the current version, rollback with `set_current()` |
| `predict.py` | `CompletionPredictor`: loads the current model and gives API 3 its `completion_probability` |

The data is synthetic, so the model demonstrates the method, not real-world accuracy. Every model card says `"synthetic_data": true`.
