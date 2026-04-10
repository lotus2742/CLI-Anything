---
name: cli-anything-doc2video
description: >
  Convert documents (text, PDF, Markdown) to narrated MP4 videos.
  Pipeline: parse → TTS voiceover (edge-tts) → render slides → ffmpeg merge.
  Free TTS included. Supports multiple voices and languages.
triggers:
  - "doc to video"
  - "document to video"
  - "convert document to video"
  - "generate video from document"
  - "narrated video"
  - "doc2video"
---

# cli-anything-doc2video

Convert documents to narrated MP4 videos. Supports `.txt`, `.md`, `.pdf` input.

## Installation

```bash
pip install cli-anything-doc2video
```

Prerequisites:
- Python 3.10+
- `ffmpeg` installed and available in PATH
- `edge-tts` (installed automatically)
- `Pillow`, `pypdf` (installed automatically)

## Usage

### One-shot: full pipeline

```bash
# Convert a markdown doc to video (Chinese voice)
cli-anything-doc2video process README.md -o output.mp4

# English voice
cli-anything-doc2video process doc.md -o output.mp4 --voice en-US-JennyNeural

# Dark theme, high quality
cli-anything-doc2video process doc.pdf -o output.mp4 --style dark --quality ultra

# Silent video (no TTS)
cli-anything-doc2video process doc.md -o output.mp4 --no-tts

# JSON output (for agent consumption)
cli-anything-doc2video --json process doc.md -o output.mp4
```

### Step by step

```bash
# 1. Parse document
cli-anything-doc2video parse doc.md -o slides.txt

# 2. Generate TTS audio
cli-anything-doc2video tts slides.txt -o audio.mp3 --voice zh-CN-XiaoxiaoNeural

# 3. Render frames
cli-anything-doc2video render slides.txt --output-dir frames/ --style default

# 4. Merge into video
cli-anything-doc2video merge frames/ audio.mp3 -o output.mp4

# Interactive REPL
cli-anything-doc2video
```

## Command Reference

### process — Full pipeline (recommended)

```
process <input> -o <output.mp4>
  [--voice VOICE]     TTS voice name (default: zh-CN-XiaoxiaoNeural)
  [--rate RATE]       Speech rate, e.g. +10% (default: +0%)
  [--style STYLE]     Slide style: default | dark | minimal (default: default)
  [--fps FPS]         Frames per second (default: 24)
  [--quality LEVEL]   ultra | high | medium | low (default: high)
  [--no-tts]          Skip TTS, produce silent video
```

### parse — Parse document into slides

```
parse <input> [-o output.txt] [--format plain|slides]
```

### tts — Generate voiceover

```
tts <text_file> -o <output.mp3> [--voice VOICE] [--rate RATE]
```

### render — Render slide frames

```
render <text_file> --output-dir DIR [--width W] [--height H] [--fps N] [--style STYLE]
```

### merge — Merge frames + audio

```
merge <frames_dir> <audio_file> -o <output.mp4> [--fps N] [--quality LEVEL]
```

## Slide Styles

| Name | Background | Best for |
|------|-----------|---------|
| `default` | Light gray | General docs |
| `dark` | Dark navy | Tech content |
| `minimal` | White | Clean presentations |

## Popular TTS Voices

| Voice | Language |
|-------|---------|
| `zh-CN-XiaoxiaoNeural` | Chinese (default) |
| `zh-CN-YunxiNeural` | Chinese (male) |
| `en-US-JennyNeural` | English |
| `en-US-GuyNeural` | English (male) |
| `ja-JP-NanamiNeural` | Japanese |

Run `edge-tts --list-voices` to see all available voices.

## JSON Output

All commands support `--json` for machine-readable output:

```bash
cli-anything-doc2video --json process doc.md -o output.mp4
# {"output_path": "/path/to/output.mp4", "file_size_bytes": 4096000, ...}
```
