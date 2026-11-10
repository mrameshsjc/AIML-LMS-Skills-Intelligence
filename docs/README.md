# Documentation

Everything about the LMS Skills Intelligence Engine. New here? Start with the **overview**, then try the **live demo walkthrough**.

| Live dashboard | Live API / Swagger |
| --- | --- |
| https://lms-skills-intelligence.streamlit.app | https://lms-skills-api.onrender.com/docs |

## Start here

| Guide | What it covers |
| --- | --- |
| [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) | The problem, what the engine does, methods, technology, risks, future work |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Diagrams: system context, layers, request flow, RAG, ML lifecycle, data model, security, deployment |
| [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md) | A 15-minute guided tour of the live system |
| [screenshots/](screenshots/README.md) | Screenshots of every step |
| [ACCEPTANCE_CHECKLIST.md](ACCEPTANCE_CHECKLIST.md) | Every acceptance criterion with its evidence; deliverables map |

## Using the engine

| Guide | What it covers |
| --- | --- |
| [API_DOCUMENTATION.md](API_DOCUMENTATION.md) | The seven APIs and supporting endpoints, with examples; [api_contract.json](api_contract.json) is the saved contract |
| [DASHBOARD_GUIDE.md](DASHBOARD_GUIDE.md) | The Streamlit dashboard, page by page |

## Data and AI

| Guide | What it covers |
| --- | --- |
| [DATA_DICTIONARY.md](DATA_DICTIONARY.md) | The eleven synthetic datasets, columns and rules |
| [DATA_PIPELINE_GUIDE.md](DATA_PIPELINE_GUIDE.md) | Generation, validation and loading scripts |
| [DATABASE_GUIDE.md](DATABASE_GUIDE.md) | SQLite schema, migrations, CSV/SQLite parity |
| [MYSQL_CONFIGURATION_GUIDE.md](MYSQL_CONFIGURATION_GUIDE.md) | MySQL setup for the LMS integration |
| [ML_MODEL_GUIDE.md](ML_MODEL_GUIDE.md) | Gap formula, role matching, hybrid recommendations, completion model, retraining, MLflow |
| [LLM_RAG_GUIDE.md](LLM_RAG_GUIDE.md) | Ollama / hosted LLM, fallback, guardrails, document index, RAG assistant |

## Security, running and delivery

| Guide | What it covers |
| --- | --- |
| [SECURITY_GUIDE.md](SECURITY_GUIDE.md) | Login, roles, rate limits, audit log, prompt injection, uploads |
| [SNYK_SECURITY_GUIDE.md](SNYK_SECURITY_GUIDE.md) | Dependency and container scanning, the `.snyk` policy |
| [DOCKER_GUIDE.md](DOCKER_GUIDE.md) | Build, run, volumes, hardening |
| [KUBERNETES_GUIDE.md](KUBERNETES_GUIDE.md) | Minikube, manifests, scaling, rollout |
| [JENKINS_CICD_GUIDE.md](JENKINS_CICD_GUIDE.md) | Jenkins pipeline and GitHub Actions |
| [PUBLIC_DEPLOYMENT_GUIDE.md](PUBLIC_DEPLOYMENT_GUIDE.md) | Streamlit Community Cloud + Render, secrets, demo reset |
| [TESTING_GUIDE.md](TESTING_GUIDE.md) | Test layers and how to run them |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common problems and fixes |
