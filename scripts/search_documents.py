"""
Search the knowledge index from the command line (Phase 12).

Shows the chunks the AI assistant would read for a question, with their
source, section, page and similarity score (1.0 = same meaning, 0 = unrelated).
This is the "retrieval" in Retrieval-Augmented Generation; Phase 13 gives
these chunks to the language model to write the answer.

HOW TO RUN (from the project folder)
    PS> python scripts/search_documents.py "How many times can I retake a course?"
    PS> python scripts/search_documents.py "certification fee" -k 2
"""

import argparse
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.llm.base import LLMUnavailableError  # noqa: E402
from app.rag.factory import load_index  # noqa: E402
from app.rag.index import IndexNotReadyError  # noqa: E402

parser = argparse.ArgumentParser(description="Search the knowledge documents.")
parser.add_argument("question")
parser.add_argument("-k", type=int, default=None, help="number of results (default: RAG_TOP_K)")
args = parser.parse_args()

settings = get_settings()
try:
    index = load_index(settings)
    results = index.search(args.question, args.k or settings.rag_top_k)
except (IndexNotReadyError, LLMUnavailableError) as error:
    sys.exit(str(error))

info = index.manifest["embedder"]
manifest = index.manifest
print(f"Index: {manifest['chunk_count']} chunks, {info['name']} ({info['model']}), {manifest['backend']}")
print(f"Question: {args.question}\n")
if not results:
    print("No matching passage found.")
for rank, r in enumerate(results, start=1):
    print(f"{rank}. score {r.score:.3f}  {r.citation}")
    print(textwrap.indent(textwrap.fill(r.text, 100), "     "), "\n")
