"""
Clean text and split documents into chunks (Phase 12).

WHY CHUNKS?
    A search should return the PARAGRAPH that answers a question, not a whole
    20-page document: the language model can only read a limited amount, and
    a precise passage gives a precise answer and citation. So each document is
    cut into pieces of about RAG_CHUNK_SIZE characters (default 800, roughly
    150 words).

HOW
    1. Clean       normalise line endings and spaces; re-join words that a PDF
                   split across lines ("assess-\\nment" -> "assessment").
    2. Sections    Markdown headings ("## 4. Completing courses") and numbered
                   PDF headings start a new section. Every chunk remembers its
                   section path, e.g. "Learning and Development Policy > 4. Completing courses".
    3. Pack        paragraphs are added to a chunk until the next one would
                   make it too long. A very long paragraph is split at sentence ends.
    4. Overlap     the last RAG_CHUNK_OVERLAP characters (whole sentences) of
                   a chunk are repeated at the start of the next one in the same
                   section, so a fact cut at a boundary is still found whole.

    The section path is also put at the top of the text that is embedded, so
    "How many attempts?" finds the chunk under "4. Completing courses" even if
    the paragraph itself never says "course".

WHY CHARACTERS AND NOT TOKENS?
    Counting characters needs no tokenizer and is easy to reason about.
    800 characters stays well within any embedding model's input limit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.rag.document_loader import Document

HEADING_MD = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
HEADING_NUMBERED = re.compile(r"^\d+(\.\d+)*\.?\s+[A-Z][^.!?]{2,70}$")  # "3. How much is reimbursed"
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str  # "<source>#<n>"
    source: str
    title: str
    section: str
    page: int | None
    text: str

    @property
    def text_for_embedding(self) -> str:
        return f"{self.section}\n\n{self.text}" if self.section else self.text


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # word split across lines by a PDF
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _blocks(document: Document):
    """Yield (page, section path, paragraph) for every paragraph in the document."""
    path: list[tuple[int, str]] = []  # [(level, heading), ...]
    for page in document.pages:
        text = clean_text(page.text)
        is_pdf = page.number is not None
        # PDFs break lines inside paragraphs: a line ending a sentence (or a heading) ends a paragraph.
        raw = text.split("\n\n") if not is_pdf else _pdf_paragraphs(text)
        for para in raw:
            para = para.strip()
            if not para:
                continue
            md = HEADING_MD.match(para) if "\n" not in para else None
            if md or (is_pdf and HEADING_NUMBERED.match(para)):
                level, heading = (len(md.group(1)), md.group(2)) if md else (2, para)
                path = [(lvl, h) for lvl, h in path if lvl < level] + [(level, heading.strip("*_ "))]
                continue
            headings = [h for _, h in path]
            if not headings or headings[0] != document.title:  # e.g. PDFs: the title is not a heading
                headings.insert(0, document.title)
            section = " > ".join(headings)
            yield page.number, section, " ".join(para.split("\n")) if is_pdf else para


def _pdf_paragraphs(text: str) -> list[str]:
    paragraphs, current = [], []
    for line in text.split("\n"):
        if HEADING_NUMBERED.match(line):
            if current:
                paragraphs.append("\n".join(current))
            paragraphs.append(line)
            current = []
            continue
        current.append(line)
        if line.rstrip().endswith((".", ":", "!", "?")):
            paragraphs.append("\n".join(current))
            current = []
    if current:
        paragraphs.append("\n".join(current))
    return paragraphs


def _split_long(paragraph: str, size: int) -> list[str]:
    if len(paragraph) <= size:
        return [paragraph]
    parts, current = [], ""
    for sentence in SENTENCE_END.split(paragraph):
        if current and len(current) + 1 + len(sentence) > size:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    return [p[i : i + size] for p in parts for i in range(0, len(p), size)]  # a single huge sentence


def _tail(text: str, overlap: int) -> str:
    """The last whole sentences of text, at most `overlap` characters."""
    if overlap <= 0:
        return ""
    tail = ""
    for sentence in reversed(SENTENCE_END.split(text)):
        if len(tail) + len(sentence) + 1 > overlap:
            break
        tail = f"{sentence} {tail}".strip()
    return tail


def chunk_document(document: Document, size: int = 800, overlap: int = 120) -> list[Chunk]:
    chunks: list[Chunk] = []
    current: list[str] = []
    key: tuple[int | None, str] | None = None  # (page, section) of the chunk being filled

    def flush():
        if current:
            n = len(chunks)
            page, section = key
            chunks.append(
                Chunk(
                    f"{document.source}#{n}",
                    document.source,
                    document.title,
                    section,
                    page,
                    "\n\n".join(current),
                )
            )

    for page, section, paragraph in _blocks(document):
        for piece in _split_long(paragraph, size):
            if key != (page, section):  # new section or page: start a new chunk, no overlap across sections
                flush()
                current, key = [], (page, section)
            elif current and len("\n\n".join([*current, piece])) > size:
                tail = _tail("\n\n".join(current), overlap)
                flush()
                current = [tail] if tail and tail != piece else []
            current.append(piece)
    flush()
    return chunks
