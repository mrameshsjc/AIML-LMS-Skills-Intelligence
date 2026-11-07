"""
Shared set-up for the API tests.

The API tests must give the same answers on every machine, whether or not
someone has trained a completion model locally (models/ is not in Git) or has
Ollama running. So the model is switched off and the LLM is set to the no-LLM
fallback here, BEFORE the app is imported. Tests that need a model
(test_trainings_api.py) provide one explicitly.
"""

import os

os.environ["USE_COMPLETION_MODEL"] = "false"
os.environ["LLM_PROVIDER"] = "fallback"
