"""TTS generation using edge-tts."""
import asyncio
import os


def generate_tts(text_file: str, output_path: str, voice: str, rate: str) -> dict:
    """Generate TTS audio from a text file.

    Args:
        text_file: Path to input text file
        output_path: Output audio file path (.mp3)
        voice: edge-tts voice name
        rate: Speech rate modifier, e.g. '+10%'

    Returns:
        dict with output_path and duration_hint
    """
    with open(text_file, encoding="utf-8") as f:
        text = f.read()

    # Remove markdown syntax for cleaner speech
    import re
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)  # headings
    text = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", text)           # bold/italic
    text = re.sub(r"`+(.+?)`+", r"\1", text)                      # code
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)               # links
    text = re.sub(r"\n\s*---\s*\n", "\n", text)                   # dividers
    text = text.strip()

    asyncio.run(_run_tts(text, output_path, voice, rate))

    size = os.path.getsize(output_path)
    return {
        "output_path": output_path,
        "voice": voice,
        "rate": rate,
        "file_size_bytes": size,
    }


async def _run_tts(text: str, output_path: str, voice: str, rate: str):
    try:
        import edge_tts
    except ImportError:
        raise RuntimeError("edge-tts is required: pip install edge-tts")

    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(output_path)
