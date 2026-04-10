# cli-anything-doc2video

Convert documents (`.txt`, `.md`, `.pdf`) to narrated MP4 videos via CLI.

Part of the [CLI-Anything](https://github.com/HKUDS/CLI-Anything) ecosystem.
Closes #208.

## Install

```bash
pip install cli-anything-doc2video
# or from source:
pip install -e .
```

Prerequisites: Python 3.10+, `ffmpeg` in PATH.

## Quick Start

```bash
# One command: doc → video
cli-anything-doc2video process README.md -o output.mp4

# English voice
cli-anything-doc2video process doc.md -o output.mp4 --voice en-US-JennyNeural

# Dark theme
cli-anything-doc2video process doc.pdf -o output.mp4 --style dark

# JSON output (agent mode)
cli-anything-doc2video --json process doc.md -o output.mp4
```

## Pipeline

```
Document → parse → TTS (edge-tts) → render frames (Pillow) → merge (ffmpeg) → MP4
```

See [DOC2VIDEO.md](DOC2VIDEO.md) for architecture details and [SKILL.md](cli_anything/doc2video/skills/SKILL.md) for full command reference.

## Run Tests

```bash
pip install -e ".[dev]"
# Unit tests (no ffmpeg/network required)
python -m pytest cli_anything/doc2video/tests/test_core.py -v
```
