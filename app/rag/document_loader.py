"""
Load knowledge documents as text (Phase 12).

SUPPORTED FILES
    .md / .txt   read as UTF-8 text
    .pdf         text of each page, with its page number (pypdf)
    .docx        Word: a .docx file is a ZIP of XML files; the text is in
                 word/document.xml, so Python's built-in zipfile is enough.
                 Headings (style "Heading 1", "Title") become Markdown "#"
                 lines, so chunking can use them as section titles.
    .csv         each row becomes one sentence-like line, "column: value; ...",
                 so a table (e.g. a list of internal trainings) can be searched
                 (Phase 13). The first row must hold the column names.

    Other files are skipped and reported. Scanned PDFs (images of text) have
    no text to extract; they would need OCR, which is out of scope.

WHY KEEP PAGE NUMBERS
    Answers cite their source. "certification_reimbursement_policy.pdf, page 2"
    lets a reader check the claim in seconds.
"""

from __future__ import annotations

import csv
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

SUPPORTED = {".md", ".txt", ".pdf", ".docx", ".csv"}
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass(frozen=True)
class Page:
    text: str
    number: int | None = None  # page number for PDFs, None for other files


@dataclass(frozen=True)
class Document:
    source: str  # file name, shown as the citation
    title: str
    pages: list[Page]


class DocumentError(ValueError):
    """A file cannot be read as a document."""


def load_document(path: str | Path) -> Document:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise DocumentError(
            f"{path.name}: unsupported file type '{suffix}' (use .md, .txt, .pdf, .docx or .csv)."
        )
    try:
        if suffix in (".md", ".txt"):
            pages = [Page(path.read_text(encoding="utf-8"))]
        elif suffix == ".pdf":
            pages = _pdf_pages(path)
        elif suffix == ".csv":
            pages = [Page(_csv_text(path))]
        else:
            pages = [Page(_docx_text(path))]
    except UnicodeDecodeError as error:
        raise DocumentError(f"{path.name}: not UTF-8 text. Save it as UTF-8.") from error
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as error:
        raise DocumentError(f"{path.name}: not a valid Word (.docx) file.") from error
    pages = [p for p in pages if p.text.strip()]
    if not pages:
        raise DocumentError(f"{path.name}: no text found (a scanned PDF needs OCR).")
    return Document(path.name, _title(pages[0].text, path), pages)


def load_folder(
    folder: str | Path, skip: tuple[str, ...] = ("README.md",)
) -> tuple[list[Document], list[str]]:
    """All supported documents in a folder (sorted by name), and warnings for files that were skipped."""
    documents, warnings = [], []
    for path in sorted(Path(folder).iterdir()):
        if not path.is_file() or path.name in skip or path.name.startswith("."):
            continue
        try:
            documents.append(load_document(path))
        except DocumentError as error:
            warnings.append(str(error))
    return documents, warnings


def _pdf_pages(path: Path) -> list[Page]:
    from pypdf import PdfReader  # imported here: only needed when there is a PDF
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(path)
        return [Page(page.extract_text() or "", number) for number, page in enumerate(reader.pages, start=1)]
    except PdfReadError as error:
        raise DocumentError(f"{path.name}: not a valid PDF ({error}).") from error


def _csv_text(path: Path) -> str:
    with path.open(encoding="utf-8-sig", newline="") as f:  # utf-8-sig: Excel's "CSV UTF-8" adds a BOM
        rows = list(csv.reader(f))
    if len(rows) < 2:
        return ""
    header = [h.strip() for h in rows[0]]
    title = path.stem.replace("_", " ").title()
    lines = [f"# {title}"]
    for row in rows[1:]:
        cells = [f"{h}: {v.strip()}" for h, v in zip(header, row, strict=False) if v.strip()]
        if cells:
            lines.append("; ".join(cells) + ".")
    return "\n\n".join(lines)


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    lines = []
    for paragraph in root.iter(f"{_W}p"):
        text = "".join(t.text or "" for t in paragraph.iter(f"{_W}t")).strip()
        if not text:
            continue
        style = paragraph.find(f"{_W}pPr/{_W}pStyle")
        name = style.get(f"{_W}val", "") if style is not None else ""
        if name == "Title":
            text = f"# {text}"
        elif match := re.fullmatch(r"Heading(\d)", name):
            text = f"{'#' * (int(match.group(1)) + 1)} {text}"
        lines.append(text)
    return "\n\n".join(lines)


def _title(first_page: str, path: Path) -> str:
    for line in first_page.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:120]
    return path.stem.replace("_", " ").title()
