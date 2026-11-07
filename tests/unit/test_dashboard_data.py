"""
Tests for the dashboard's data helpers (Phase 15). No Streamlit needed: the
helpers only reshape service results, so they are tested like any function.

HOW TO RUN
    PS> pytest tests/unit/test_dashboard_data.py -v
"""

import pytest

from app.ml.model_registry import current_version, list_cards, save_model
from app.repositories.csv_repository import CsvLmsRepository
from app.services.chat_service import ChatService
from app.services.learning_path import LearningPathService
from app.services.role_matching import RoleMatchingService
from app.services.skill_analysis import SkillAnalysisService
from app.services.training_recommendation import TrainingRecommendationService
from dashboard.components import data


@pytest.fixture(scope="module")
def repo():
    return CsvLmsRepository()


def test_choices(repo):
    employees = data.employee_choices(repo)
    assert len(employees) == 100
    assert next(iter(employees)).startswith("E1001 – ") and "(Software Developer)" in next(iter(employees))
    roles = data.role_choices(repo)
    assert roles["Data Engineer (R004)"] == "R004" and list(roles) == sorted(roles)


def test_home_stats(repo):
    stats = data.home_stats(repo)
    assert (stats.employees, stats.roles, stats.skills, stats.active_courses) == (100, 13, 42, 80)
    assert sum(stats.training_status.values()) > 0 and stats.completion_rate == 66.8
    assert stats.employees_with_goal == 63 and 0 < stats.average_gap_score < 100
    assert list(stats.top_gap_skills.columns) == ["Skill", "Employees with a gap", "Of which mandatory"]
    assert stats.top_gap_skills["Employees with a gap"].is_monotonic_decreasing
    assert stats.top_recommended["Times recommended first"].sum() <= stats.employees_with_goal


def test_skills_tables_match_api1(repo):
    result = SkillAnalysisService(repo).analyze("E1001")
    table = data.skills_table(result)
    assert table["Skill"].tolist()[:2] == ["AWS", "SQL"] and table.loc[0, "Status"] == "Below required"
    assert table["Gap"].sum() == 6
    chart = data.level_chart_data(result)
    assert chart.loc["SQL"].tolist() == [2, 4]
    assert "Python" in data.profile_table(result)["Skill"].tolist()


def test_role_tables(repo):
    result = RoleMatchingService(repo).match("E1001")
    table = data.role_matches_table(result)
    assert table.loc[0, "Role"] == "Software Developer" and table.loc[0, "Note"] == "current role"
    breakdown = data.role_skill_breakdown(result.target)
    assert breakdown["Matching skills"] == ["Machine Learning (level 2 of 2)"]
    assert "SQL (2 → 4)" in breakdown["Skills to improve"] and breakdown["Missing skills"] == []


def test_recommendations_table(repo):
    table = data.recommendations_table(TrainingRecommendationService(repo).recommend("E1001"))
    first = table.iloc[0]
    assert (first["Course"], first["Skills"], first["Prerequisites"]) == (
        "C-SQL-201",
        "SQL 2→4",
        "C-SQL-101 ✓",
    )


def test_path_table_and_progress(repo):
    path = LearningPathService(repo).build("E1001")
    table = data.path_table(path)
    assert table["Course"].tolist() == ["C-SQL-201", "C-PY-201", "C-AWS-101", "C-AWS-201", "C-DOCKER-201"]
    assert table.loc[3, "After step"] == "3" and not table.loc[3, "Can start now"]
    assert table.loc[4, "Why"] == "optional gap"
    assert data.course_progress(path) == (2, 7, 28.6)  # 2 relevant courses done, 5 to go


def test_sources_table(repo, tmp_path):
    from app.rag.embeddings import TfidfEmbedder
    from app.rag.index import KnowledgeIndex, build_index
    from app.rag.vector_store import NumpyVectorStore

    build_index("documents", tmp_path / "default", TfidfEmbedder(), NumpyVectorStore)
    index = KnowledgeIndex.load(tmp_path / "default")
    answer = ChatService(repo, _Model(), lambda: index, lambda i: 0.08).ask(
        "How many learning hours do I get?"
    )
    table = data.sources_table(answer)
    assert table.loc[0, "Source"] == "S1" and table.loc[0, "Document"] == "faq.md"


class _Model:
    name, model = "fake", "fake"

    def generate(self, request):
        from app.llm.base import LLMResult

        return LLMResult("ok", "fake", "fake")


def test_documents_table():
    assert data.documents_table(None).empty
    manifest = {"documents": [{"source": "a.md", "title": "A", "pages": 1, "chunks": 2, "sha256": "f" * 64}]}
    row = data.documents_table(manifest).iloc[0]
    assert row["Origin"] == "base" and row["Fingerprint"] == "f" * 12


def test_model_tables(tmp_path):
    card = {
        "algorithm": "logistic_regression",
        "trained_at": "2026-11-08T00:00:00+00:00",
        "test_metrics": {"roc_auc": 0.69, "accuracy": 0.68, "baseline_accuracy": 0.66},
        "cross_validation": [{"model": "logistic_regression", "cv_roc_auc": 0.64, "cv_roc_auc_std": 0.03}],
    }
    save_model({"fake": "pipeline"}, card, tmp_path)
    save_model({"fake": "pipeline"}, {**card, "algorithm": "random_forest"}, tmp_path)
    cards, current = list_cards(tmp_path), current_version(tmp_path)
    assert [c["version"] for c in cards] == [1, 2] and current == 2
    table = data.model_versions_table(cards, current)
    assert table["Version"].tolist() == [2, 1] and table["Current"].tolist() == [True, False]
    comparison = data.model_comparison_table(cards[0])
    assert list(comparison.columns)[:2] == ["Algorithm", "CV ROC AUC"]
    assert current_version(tmp_path / "nothing") is None and list_cards(tmp_path / "nothing") == []
