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


def _strip_marp_frontmatter(text: str) -> str:
    """Remove Marp YAML frontmatter (--- ... ---) including style/CSS blocks."""
    # Match opening --- block at the very start of the file
    match = re.match(r"^---\s*\n.*?^---\s*\n", text, flags=re.DOTALL | re.MULTILINE)
    if match:
        return text[match.end():]
    return text


def _slide_to_tts(slide_text: str) -> str:
    """Convert a single slide's markdown to clean TTS-friendly text.

    Removes:
    - HTML comments (<!-- _class: lead -->)
    - Marp/markdown directives
    - Markdown formatting (**, __, `, ##, -, *, ▸)
    - Inline code and code blocks
    - Extra blank lines
    """
    t = slide_text

    # Remove HTML comments (<!-- ... -->)
    t = re.sub(r"<!--.*?-->", "", t, flags=re.DOTALL)

    # Remove fenced code blocks (``` ... ```)
    t = re.sub(r"```[\s\S]*?```", "", t)

    # Remove inline code (`...`)
    t = re.sub(r"`[^`]+`", lambda m: m.group(0).strip("`"), t)

    # Remove markdown heading markers
    t = re.sub(r"^#{1,6}\s+", "", t, flags=re.MULTILINE)

    # Remove bold/italic markers
    t = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", t)
    t = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", t)

    # Remove bullet markers (-, *, ▸, •)
    t = re.sub(r"^[\s]*[-*▸•]\s+", "", t, flags=re.MULTILINE)

    # Remove markdown links [text](url) → text
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)

    # Collapse multiple blank lines
    t = re.sub(r"\n{3,}", "\n\n", t)

    return t.strip()


def _split_slides(text: str) -> list[str]:
    """Split Marp markdown into per-slide TTS scripts.

    1. Strip frontmatter (including CSS style block)
    2. Split on Marp slide dividers (--- on its own line)
    3. Clean each slide for TTS output
    """
    # Strip YAML frontmatter first (contains CSS — must not be read aloud)
    text = _strip_marp_frontmatter(text)

    # Split on slide dividers
    if re.search(r"\n\s*---\s*\n", text):
        parts = re.split(r"\n\s*---\s*\n", text)
    else:
        # Fallback: split by headings
        parts = re.split(r"(?=^#{1,2} )", text, flags=re.MULTILINE)

    slides = []
    for part in parts:
        cleaned = _slide_to_tts(part)
        if cleaned:
            slides.append(cleaned)

    return slides if slides else [_slide_to_tts(text)]
