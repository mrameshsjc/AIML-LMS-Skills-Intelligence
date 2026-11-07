"""
End-to-end test over HTTP: the whole business flow through the real FastAPI app (Phase 14).

One employee's journey, the way the LMS will use the API later:
    1. health  2. skills analysis  3. role matching  4. recommendations
    5. learning path  6. assistant  7. upload a document  8. assistant uses it  9. delete it
Every response is checked against the earlier ones, so the APIs must agree.

conftest.py (tests/api) is not loaded here, so the model and LLM are switched
off by this file's fixture: the test is the same on every machine.

HOW TO RUN
    PS> pytest tests/integration/test_api_flow.py -v
"""

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import get_settings


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    folder = tmp_path_factory.mktemp("flow")
    patch = pytest.MonkeyPatch()
    for name, value in {
        "USE_COMPLETION_MODEL": "false",
        "LLM_PROVIDER": "fallback",
        "EMBEDDING_PROVIDER": "tfidf",
        "VECTOR_STORE_DIR": str(folder / "store"),
        "RAG_UPLOAD_DIR": str(folder / "uploads"),
        "DATA_SOURCE": "csv",
    }.items():
        patch.setenv(name, value)
    caches = [
        get_settings,
        dependencies.get_repository,
        dependencies.get_completion_predictor,
        dependencies.get_llm_provider,
        dependencies.get_knowledge_index,
    ]
    for cache in caches:
        cache.cache_clear()
    from app.main import app

    yield TestClient(app)
    patch.undo()
    for cache in caches:
        cache.cache_clear()


def test_full_journey_for_e1001(client):
    # 1. The service is up
    assert client.get("/api/v1/health").json()["status"] == "ok"

    # 2. Skills analysis (API 1): where does E1001 stand for their career goal?
    skills = client.post("/api/v1/skills/analyze", json={"employee_id": "E1001"}).json()
    assert skills["target_role"]["title"] == "Data Engineer" and skills["gap_score"] == 37.5
    gaps = {s["skill"] for s in skills["skills"] if s["gap"] > 0}

    # 3. Role matching (API 2): the same match % for the same role
    roles = client.post("/api/v1/roles/match", json={"employee_id": "E1001"}).json()
    assert roles["target"]["match_percentage"] == skills["match_percentage"]

    # 4. Recommendations (API 3): courses for exactly those gaps
    recs = client.post("/api/v1/trainings/recommend", json={"employee_id": "E1001", "max_results": 30}).json()
    assert recs["gap_score"] == skills["gap_score"]
    assert {s["skill"] for r in recs["recommendations"] for s in r["skills_covered"]} <= gaps
    scores = {r["course_id"]: r["score"] for r in recs["recommendations"]}

    # 5. Learning path (API 4): the same courses and scores, in an order that can be followed
    path = client.get("/api/v1/learning-path/E1001").json()
    assert path["progress"]["match_percentage"] == skills["match_percentage"]
    assert {g["skill"] for g in path["skill_gaps"]} == gaps
    for step in path["path"]:
        assert step["score"] == scores[step["course_id"]]
        assert all(before < step["step"] for before in step["after_steps"])
    first = path["path"][0]["course_id"]

    # 6. Assistant (API 5): repeats the path's next action, without documents yet
    answer = client.post(
        "/api/v1/ai/chat", json={"question": "Which course should I take next?", "employee_id": "E1001"}
    ).json()
    assert f"Next action: {path['next_action']}" in answer["facts"] and first in answer["answer"]
    assert any("No document index" in n for n in answer["notes"])

    # 7. Upload a document (API 7): this also builds the index
    uploaded = client.post(
        "/api/v1/rag/ingest",
        files={
            "file": ("internal_trainings.csv", b"training,hours\nKafka Essentials,12\nSpark Bootcamp,24\n")
        },
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["status"] == "added"

    # 8. The assistant finds it at once, with a source
    kafka = client.post(
        "/api/v1/ai/chat", json={"question": "How long is the Kafka Essentials training?"}
    ).json()
    assert kafka["sources"][0]["source"] == "internal_trainings.csv" and "hours: 12" in kafka["answer"]
    status = client.get("/api/v1/health/rag").json()
    assert status["ready"] and "internal_trainings.csv" in {d["source"] for d in status["documents"]}

    # 9. Delete it: gone from the index and from answers
    assert client.delete("/api/v1/rag/documents/internal_trainings.csv").json()["status"] == "deleted"
    again = client.post(
        "/api/v1/ai/chat", json={"question": "How long is the Kafka Essentials training?"}
    ).json()
    assert all(s["source"] != "internal_trainings.csv" for s in again["sources"])


@pytest.mark.parametrize("employee_id", ["E1003", "E1020", "E1050", "E1099"])
def test_apis_agree_for_other_employees(client, employee_id):
    skills = client.post("/api/v1/skills/analyze", json={"employee_id": employee_id}).json()
    roles = client.post(
        "/api/v1/roles/match",
        json={"employee_id": employee_id, "target_role_id": skills["target_role"]["role_id"]},
    ).json()
    path = client.get(f"/api/v1/learning-path/{employee_id}").json()
    assert (
        roles["target"]["match_percentage"]
        == skills["match_percentage"]
        == path["progress"]["match_percentage"]
    )
    assert path["target_role"] == skills["target_role"]
    if not path["uncovered_skills"]:
        assert path["progress"]["projected_match_percentage"] == 100.0
