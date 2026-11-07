"""
Tests for the knowledge documents and search (Phase 12). No Ollama needed:
Ollama embeddings are tested against the fake server in conftest.py, and
FAISS tests run only when faiss-cpu is installed.

HOW TO RUN
    PS> pytest tests/unit/test_rag.py -v
"""

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

from app.core.config import Settings
from app.llm.base import LLMUnavailableError
from app.rag.chunking import Chunk, chunk_document, clean_text
from app.rag.document_loader import Document, DocumentError, Page, load_document, load_folder
from app.rag.embeddings import OllamaEmbedder, TfidfEmbedder, normalise
from app.rag.factory import choose_embedder
from app.rag.index import IndexNotReadyError, KnowledgeIndex, build_index, index_folder, read_manifest
from app.rag.vector_store import FaissVectorStore, NumpyVectorStore, choose_backend, faiss_installed
from app.repositories.csv_repository import CsvLmsRepository
from tests.unit.conftest import EMBED_DIM, closed_port_url

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "documents"


@pytest.fixture(scope="module")
def tfidf_index(tmp_path_factory) -> KnowledgeIndex:
    target = tmp_path_factory.mktemp("store") / "default"
    build_index(DOCS, target, TfidfEmbedder(), NumpyVectorStore)
    return KnowledgeIndex.load(target)


# --- Loading documents ------------------------------------------------------------------


def test_sample_documents_load():
    documents, warnings = load_folder(DOCS)
    sources = {d.source for d in documents}
    assert warnings == [] and "README.md" not in sources
    assert {
        "learning_policy.md",
        "certification_reimbursement_policy.pdf",
        "mentoring_programme.docx",
    } <= sources


def test_pdf_keeps_page_numbers():
    pdf = load_document(DOCS / "certification_reimbursement_policy.pdf")
    assert [p.number for p in pdf.pages] == [1, 2] and pdf.title == "Certification Reimbursement Policy"
    assert "300 euros" in pdf.pages[1].text


def test_docx_headings_become_markdown():
    docx = load_document(DOCS / "mentoring_programme.docx")
    assert docx.title == "Mentoring Programme"
    assert "## How to find a mentor" in docx.pages[0].text


def test_bad_files_are_reported(tmp_path):
    (tmp_path / "notes.xlsx").write_bytes(b"x")
    (tmp_path / "empty.md").write_text("   ")
    (tmp_path / "broken.docx").write_bytes(b"not a zip")
    (tmp_path / "latin1.txt").write_bytes("caf\xe9".encode("latin-1"))
    (tmp_path / "good.md").write_text("# Good\n\nSome text.")
    documents, warnings = load_folder(tmp_path)
    assert [d.source for d in documents] == ["good.md"]
    assert len(warnings) == 4
    assert any("unsupported" in w for w in warnings) and any("UTF-8" in w for w in warnings)
    with pytest.raises(DocumentError, match="no text"):
        load_document(tmp_path / "empty.md")


def test_docx_without_document_xml(tmp_path):
    with zipfile.ZipFile(tmp_path / "odd.docx", "w") as z:
        z.writestr("other.xml", "<x/>")
    with pytest.raises(DocumentError, match="Word"):
        load_document(tmp_path / "odd.docx")


def test_generated_documents_match_the_data():
    """If this fails, the LMS data changed: run python scripts/generate_documents.py."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import generate_documents as gen

    repo = CsvLmsRepository()
    assert (DOCS / "course_catalogue.md").read_text(encoding="utf-8") == gen.course_catalogue(repo)
    assert (DOCS / "job_role_profiles.md").read_text(encoding="utf-8") == gen.job_role_profiles(repo)


# --- Cleaning and chunking ----------------------------------------------------------------


def test_clean_text():
    assert clean_text("re-\nassessment  is\r\n\n\n\ndone ") == "reassessment is\n\ndone"


def _long_doc() -> Document:
    sentences = " ".join(f"Sentence number {i} explains one rule of the policy." for i in range(60))
    return Document(
        "long.md", "Long", [Page(f"# Long\n\n## Rules\n\n{sentences}\n\n## Other\n\nShort section.")]
    )


def test_chunks_respect_size_sections_and_overlap():
    chunks = chunk_document(_long_doc(), size=400, overlap=120)
    rules = [c for c in chunks if c.section == "Long > Rules"]
    assert len(rules) >= 5
    assert all(len(c.text) <= 400 + 120 for c in chunks)
    for previous, current in zip(
        rules, rules[1:], strict=False
    ):  # each chunk starts with the end of the last
        assert current.text.split(". ")[0] in previous.text
    other = [c for c in chunks if c.section == "Long > Other"]
    assert [c.text for c in other] == ["Short section."]  # no overlap carried across sections
    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_no_overlap_when_disabled():
    chunks = chunk_document(_long_doc(), size=400, overlap=0)
    rules = [c.text for c in chunks if c.section == "Long > Rules"]
    assert "".join(rules).count("Sentence number 10 ") == 1


def test_sample_chunks_have_sections_and_pages():
    pdf = chunk_document(load_document(DOCS / "certification_reimbursement_policy.pdf"))
    reimbursed = next(c for c in pdf if "300 euros" in c.text)
    assert reimbursed.page == 2 and reimbursed.section.endswith("3. How much is reimbursed")
    policy = chunk_document(load_document(DOCS / "learning_policy.md"))
    attempts = next(c for c in policy if "up to 5 times" in c.text)
    assert attempts.section == "Learning and Development Policy > 4. Completing courses"
    assert attempts.text_for_embedding.startswith(attempts.section)


# --- Embeddings -------------------------------------------------------------------------------


def test_tfidf_vectors_are_normalised_and_reloadable(tmp_path):
    embedder = TfidfEmbedder()
    texts = ["learning hours per year", "certification exam fee", "mentor meetings"]
    embedder.fit(texts)
    vectors = embedder.embed_documents(texts)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0)
    embedder.save(tmp_path)
    again = TfidfEmbedder.load(tmp_path).embed_query("exam fee")
    assert np.allclose(again, embedder.embed_query("exam fee")) and int(np.argmax(vectors @ again)) == 1


def test_normalise_keeps_zero_vectors_at_zero():
    assert np.allclose(normalise(np.array([[3.0, 4.0], [0.0, 0.0]])), [[0.6, 0.8], [0.0, 0.0]])


def test_ollama_embedder_batches_and_uses_nomic_prefixes(fake_ollama):
    embedder = OllamaEmbedder(fake_ollama.url, "nomic-embed-text")
    vectors = embedder.embed_documents([f"text {i}" for i in range(40)])
    assert vectors.shape == (40, EMBED_DIM)
    assert [len(r["input"]) for r in fake_ollama.requests] == [32, 8]  # two batches
    assert fake_ollama.requests[0]["input"][0] == "search_document: text 0"
    embedder.embed_query("hours")
    assert fake_ollama.requests[-1]["input"] == ["search_query: hours"]


def test_ollama_embedder_errors(fake_ollama):
    with pytest.raises(LLMUnavailableError, match="ollama pull mxbai-embed-large"):
        OllamaEmbedder(fake_ollama.url, "mxbai-embed-large").embed_query("x")
    with pytest.raises(LLMUnavailableError, match="Is it running"):
        OllamaEmbedder(closed_port_url()).embed_query("x")
    assert OllamaEmbedder(fake_ollama.url).available()[0] is True
    assert OllamaEmbedder(closed_port_url()).available()[0] is False


def test_choose_embedder_follows_the_setting(fake_ollama):
    embedder, _ = choose_embedder(Settings(embedding_provider="tfidf"))
    assert isinstance(embedder, TfidfEmbedder)
    down = Settings(embedding_provider="auto", ollama_base_url=closed_port_url())
    embedder, notes = choose_embedder(down)
    assert isinstance(embedder, TfidfEmbedder) and "ollama pull nomic-embed-text" in notes[0]
    up = Settings(embedding_provider="auto", ollama_base_url=fake_ollama.url)
    assert isinstance(choose_embedder(up)[0], OllamaEmbedder)
    with pytest.raises(RuntimeError, match="EMBEDDING_PROVIDER=ollama"):
        choose_embedder(Settings(embedding_provider="ollama", ollama_base_url=closed_port_url()))


# --- Vector stores ------------------------------------------------------------------------------


def _random_vectors(n=50, dim=16, seed=0) -> np.ndarray:
    return normalise(np.random.default_rng(seed).normal(size=(n, dim)))


def test_numpy_store_finds_the_exact_nearest(tmp_path):
    vectors = _random_vectors()
    store = NumpyVectorStore()
    store.build(vectors)
    query = vectors[7]
    hits = store.search(query, 5)
    assert hits[0][0] == 7 and hits[0][1] == pytest.approx(1.0, abs=1e-5)
    assert [i for i, _ in hits] == list(np.argsort(-(vectors @ query))[:5])
    store.save(tmp_path)
    assert NumpyVectorStore.load(tmp_path).search(query, 5) == hits
    assert len(store.search(query, 500)) == 50 and NumpyVectorStore().search(query, 3) == []


@pytest.mark.skipif(not faiss_installed(), reason="faiss-cpu is not installed")
def test_faiss_gives_the_same_results_as_numpy(tmp_path):
    vectors = _random_vectors()
    exact, fast = NumpyVectorStore(), FaissVectorStore()
    exact.build(vectors)
    fast.build(vectors)
    for q in vectors[:5]:
        assert [i for i, _ in fast.search(q, 5)] == [i for i, _ in exact.search(q, 5)]
    fast.save(tmp_path)
    assert [i for i, _ in FaissVectorStore.load(tmp_path).search(vectors[0], 3)][0] == 0


def test_choose_backend():
    assert choose_backend("numpy") is NumpyVectorStore
    assert choose_backend("auto") is (FaissVectorStore if faiss_installed() else NumpyVectorStore)
    if not faiss_installed():
        with pytest.raises(RuntimeError, match="pip install faiss-cpu"):
            choose_backend("faiss")


# --- Building and searching the index --------------------------------------------------------------


def test_manifest_describes_the_index(tfidf_index):
    m = tfidf_index.manifest
    assert m["embedder"]["name"] == "tfidf" and m["backend"] == "numpy"
    assert m["chunk_count"] == len(tfidf_index.chunks) == sum(d["chunks"] for d in m["documents"])
    assert all(len(d["sha256"]) == 64 for d in m["documents"])


@pytest.mark.parametrize(
    "question, expected_source",
    [
        ("How many learning hours do I get per year?", "faq.md"),
        ("How many times can I attempt a course?", "learning_policy.md"),
        ("Who can be my mentor?", "mentoring_programme.docx"),
        ("Do I need approval to enrol in a course?", "learning_policy.md"),
        ("Which skills does a Data Engineer need?", "job_role_profiles.md"),
        ("How much of the certification fee is reimbursed?", "certification_reimbursement_policy.pdf"),
    ],
)
def test_search_finds_the_right_document(tfidf_index, question, expected_source):
    results = tfidf_index.search(question, 3)
    assert expected_source in [r.source for r in results]
    assert results == sorted(results, key=lambda r: -r.score)


def test_search_result_citation(tfidf_index):
    hit = next(r for r in tfidf_index.search("certification fee reimbursed 300 euros", 5) if r.page == 2)
    assert hit.citation.startswith("certification_reimbursement_policy.pdf, page 2 (")


def test_unrelated_question_returns_nothing(tfidf_index):
    assert tfidf_index.search("zebra quantum violin", 3) == [] and tfidf_index.search("  ", 3) == []


def test_rebuild_replaces_the_index_in_one_step(tmp_path):
    target = tmp_path / "default"
    build_index(DOCS, target, TfidfEmbedder(), NumpyVectorStore)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "only.md").write_text("# Only\n\nOne small document.")
    report = build_index(docs, target, TfidfEmbedder(), NumpyVectorStore)
    assert report.documents == 1 and read_manifest(target)["documents"][0]["source"] == "only.md"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["default", "docs"]  # no temporary folders left


class BrokenEmbedder(TfidfEmbedder):
    def embed_documents(self, texts):
        raise LLMUnavailableError("embedding failed")


def test_failed_build_keeps_the_old_index(tmp_path):
    target = tmp_path / "default"
    build_index(DOCS, target, TfidfEmbedder(), NumpyVectorStore)
    before = read_manifest(target)
    with pytest.raises(LLMUnavailableError):
        build_index(DOCS, target, BrokenEmbedder(), NumpyVectorStore)
    assert read_manifest(target) == before


def test_empty_documents_folder(tmp_path):
    with pytest.raises(IndexNotReadyError, match="No documents"):
        build_index(tmp_path, tmp_path / "default", TfidfEmbedder(), NumpyVectorStore)


def test_index_built_with_ollama_embeddings(fake_ollama, tmp_path):
    target = tmp_path / "default"
    embedder = OllamaEmbedder(fake_ollama.url)
    build_index(DOCS, target, embedder, NumpyVectorStore)
    index = KnowledgeIndex.load(target, embedder)
    assert index.manifest["embedder"] == {
        "name": "ollama",
        "model": "nomic-embed-text",
        "dimensions": EMBED_DIM,
    }
    assert "mentoring_programme.docx" in [r.source for r in index.search("mentor mentee meetings", 3)]
    with pytest.raises(IndexNotReadyError, match="OLLAMA_EMBED_MODEL=nomic-embed-text"):
        KnowledgeIndex.load(target, OllamaEmbedder(fake_ollama.url, "other-model"))
    with pytest.raises(IndexNotReadyError):
        KnowledgeIndex.load(target)  # no Ollama embedder given


def test_missing_index(tmp_path):
    with pytest.raises(IndexNotReadyError, match="build_index.py"):
        KnowledgeIndex.load(tmp_path / "default")


def test_tenant_folders():
    assert index_folder("vector_store", "acme-1").name == "acme-1"
    with pytest.raises(ValueError):
        index_folder("vector_store", "../other")


def test_chunk_round_trip_through_json():
    chunk = Chunk("a.md#0", "a.md", "A", "A > B", None, "text")
    assert Chunk(**json.loads(json.dumps(chunk.__dict__))) == chunk


# --- Scripts ---------------------------------------------------------------------------------------


def _run(script: str, *args: str, store: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "VECTOR_STORE_DIR": str(store), "OLLAMA_BASE_URL": closed_port_url()}
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.mark.slow
def test_build_and_search_scripts(tmp_path):
    built = _run("build_index.py", store=tmp_path)
    assert built.returncode == 0, built.stderr
    assert "Using TF-IDF instead" in built.stdout and "Indexed 8 documents" in built.stdout
    found = _run("search_documents.py", "Who can be my mentor?", "-k", "2", store=tmp_path)
    assert found.returncode == 0, found.stderr
    assert "1. score" in found.stdout and "mentoring_programme.docx" in found.stdout


@pytest.mark.slow
def test_search_script_without_an_index(tmp_path):
    result = _run("search_documents.py", "anything", store=tmp_path)
    assert result.returncode == 1 and "build_index.py" in result.stderr


# --- Phase 13 additions ------------------------------------------------------------------------------


def test_csv_with_only_a_header_has_no_text(tmp_path):
    (tmp_path / "empty.csv").write_text("training,hours\n")
    with pytest.raises(DocumentError, match="no text"):
        load_document(tmp_path / "empty.csv")


def test_csv_with_excel_bom(tmp_path):
    (tmp_path / "list.csv").write_bytes("﻿training,hours\nKafka,12\n".encode())
    text = load_document(tmp_path / "list.csv").pages[0].text
    assert "training: Kafka; hours: 12." in text


def test_build_with_uploads_skips_name_clashes_and_duplicates(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "faq.md").write_text("# Another FAQ\n\nDifferent text.")  # same name as a base document
    (uploads / "copy_of_policy.md").write_bytes((DOCS / "learning_policy.md").read_bytes())  # same content
    (uploads / "extra.md").write_text("# Extra\n\nA genuinely new document.")
    report = build_index(DOCS, tmp_path / "default", TfidfEmbedder(), NumpyVectorStore, upload_dir=uploads)
    docs = {d["source"]: d["origin"] for d in read_manifest(tmp_path / "default")["documents"]}
    assert docs["extra.md"] == "uploaded" and docs["faq.md"] == "base" and "copy_of_policy.md" not in docs
    assert any("already indexed" in w for w in report.warnings)
    assert any("same content as learning_policy.md" in w for w in report.warnings)
