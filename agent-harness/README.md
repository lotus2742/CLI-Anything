# cli-anything-doc2video

Convert documents (`.txt`, `.md`, `.pdf`, `.docx`) to narrated MP4 videos via CLI.

Part of the [CLI-Anything](https://github.com/HKUDS/CLI-Anything) ecosystem.
Closes #208.

## Install

```bash
# From source
git clone https://github.com/lotus2742/CLI-Anything.git
cd CLI-Anything/doc2video/agent-harness
pip install -e .
```

Prerequisites: Python 3.10+, `ffmpeg` in PATH, `npm` (Node.js).

> **Marp CLI** is auto-installed on first run — no manual setup needed.

## Quick Start

```bash
# One command: doc → video (default: deep-blue tech theme)
cli-anything-doc2video process README.md -o output.mp4

# Word document
cli-anything-doc2video process report.docx -o output.mp4

# Dark theme (GitHub style)
cli-anything-doc2video process doc.md -o output.mp4 --style dark

# Chinese voice
cli-anything-doc2video process doc.md -o output.mp4 --voice zh-CN-XiaoxiaoNeural

# No TTS (silent video)
cli-anything-doc2video process doc.md -o output.mp4 --no-tts

# JSON output (agent mode)
cli-anything-doc2video --json process doc.md -o output.mp4
```

## Pipeline

```
Document → parse → TTS (edge-tts) → render frames (Playwright HTML) → merge (ffmpeg) → MP4
                                            ↓ fallback
                                       Pillow (if Playwright unavailable)
```

## Supported Input Formats

| Format | Notes |
|--------|-------|
| `.md` / `.markdown` | Markdown |
| `.docx` / `.doc` | Word（via python-docx） |
| `.pdf` | PDF（via pypdf） |
| `.txt` | Plain text，支持 UTF-8 / GBK |

## Themes

| Theme | Style |
|-------|-------|
| `default` | 深蓝科技风，双色竖线，彩色要点列表（推荐）|
| `dark` | GitHub 暗色风 |
| `minimal` | 浅色商务风 |
| `gradient` | 深紫渐变，视觉最强 |

## Chinese Voices

| Voice ID | Style |
|----------|-------|
| `zh-CN-XiaoxiaoNeural` | 女声，温柔自然（默认）|
| `zh-CN-YunxiNeural` | 男声，沉稳清晰 |
| `zh-CN-XiaohanNeural` | 女声，干练 |
| `zh-CN-YunjianNeural` | 男声，有力 |

## Slide Pagination

Use `---` on its own line to split pages manually:

```markdown
# 第一页标题
要点一
要点二

---

# 第二页标题
要点三
要点四
```

If no `---` separators are present, the entire document becomes one slide.

## Use with Cursor Agent

Copy `.cursorrules` to your project root to let Cursor Agent automatically:
1. Read and summarize your document into 8–12 slides
2. Generate the video via `cli-anything-doc2video process`
3. Report the output path and estimated duration

```bash
cp .cursorrules /your/project/.cursorrules
```

Then tell Cursor Agent:
> "把这个文档做成视频，dark 主题"

## Sub-commands

```bash
cli-anything-doc2video parse   <file>               # Parse only
cli-anything-doc2video tts     <file> -o out.mp3    # TTS only
cli-anything-doc2video render  <file> --frames-dir /tmp/frames  # Render frames only
cli-anything-doc2video merge   --frames-dir /tmp/frames -o out.mp4  # Merge only
cli-anything-doc2video process <file> -o out.mp4    # Full pipeline
```

## Run Tests

```bash
pip install -e ".[dev]"
python -m pytest cli_anything/doc2video/tests/test_core.py -v
```

## Architecture

See [DOC2VIDEO.md](DOC2VIDEO.md) for full architecture details and [SKILL.md](cli_anything/doc2video/skills/SKILL.md) for complete command reference.
