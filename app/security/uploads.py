"""
Checking that a file really is what its name says (Phase 17).

WHY
    The file name's extension is chosen by the uploader: "invoice.pdf" can be a
    Windows program. So the first bytes of the content (the "magic number") are
    checked against the extension:
        .pdf     starts with %PDF-
        .docx    is a ZIP archive (starts with PK) containing word/document.xml
        .txt/.md/.csv   valid UTF-8 text without NUL bytes (binary files contain them)
    Executable formats (Windows MZ, Linux ELF, macOS Mach-O, scripts with #!) are
    refused whatever their name.
"""

from __future__ import annotations

import io
import zipfile

EXECUTABLE_SIGNATURES = {
    b"MZ": "a Windows program",
    b"\x7fELF": "a Linux program",
    b"\xcf\xfa\xed\xfe": "a macOS program",
    b"#!": "a script",
}  # noqa: E501


def content_problem(suffix: str, content: bytes) -> str | None:
    """None if the content matches the extension, otherwise the reason it does not."""
    for signature, what in EXECUTABLE_SIGNATURES.items():
        if content.startswith(signature):
            return f"the file is {what}, not a document"
    if suffix == ".pdf":
        return (
            None
            if content.lstrip()[:5] == b"%PDF-"
            else "it is not a PDF file (the content does not start with %PDF-)"
        )  # noqa: E501
    if suffix == ".docx":
        if not content.startswith(b"PK"):
            return "it is not a Word .docx file (not a ZIP archive)"
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                return (
                    None
                    if "word/document.xml" in archive.namelist()
                    else "the ZIP archive is not a Word document"
                )
        except zipfile.BadZipFile:
            return "it is a damaged ZIP/Word file"
    if suffix in (".txt", ".md", ".csv"):
        if b"\x00" in content:
            return "it contains binary data, not text"
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return "it is not UTF-8 text (in Excel, save as 'CSV UTF-8')"
    return None
