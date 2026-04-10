"""Document parser — supports .txt, .md, .pdf."""
import os
import re
from pathlib import Path


def parse_document(input_file: str, fmt: str = "slides") -> dict:
    """Parse a document file into structured text.

    Args:
        input_file: Path to input file (.txt / .md / .pdf)
        fmt: 'plain' returns raw text; 'slides' splits into sections by headings/pages

    Returns:
        dict with keys: slides (list[str]), content (str), slide_count (int)
    """
    ext = Path(input_file).suffix.lower()

    if ext == ".pdf":
        text = _parse_pdf(input_file)
    elif ext in (".md", ".markdown"):
        text = _parse_markdown(input_file)
    elif ext in (".docx", ".doc"):
        text = _parse_docx(input_file)
    else:
        # plain text — try utf-8 first, fall back to gbk
        try:
            with open(input_file, encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(input_file, encoding="gbk", errors="replace") as f:
                text = f.read()

    if fmt == "slides":
        slides = _split_slides(text)
    else:
        slides = [text]

    content = "\n\n---\n\n".join(slides)
    return {
        "slides": slides,
        "content": content,
        "slide_count": len(slides),
    }


def _parse_docx(path: str) -> str:
    try:
        from docx import Document
    except ImportError:
        raise RuntimeError("python-docx is required for .docx parsing: pip install python-docx")
    doc = Document(path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def _parse_pdf(path: str) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n---\n\n".join(pages)
    except ImportError:
        raise RuntimeError("pypdf is required for PDF parsing: pip install pypdf")


def _parse_markdown(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _split_slides(text: str) -> list[str]:
    """Split text into slides by headings (# / ##) or existing --- dividers."""
    # respect existing dividers first
    if "---" in text:
        parts = re.split(r"\n\s*---\s*\n", text)
        slides = [p.strip() for p in parts if p.strip()]
        if slides:
            return slides

    # split by markdown headings
    parts = re.split(r"(?=^#{1,2} )", text, flags=re.MULTILINE)
    slides = [p.strip() for p in parts if p.strip()]
    return slides if slides else [text.strip()]
