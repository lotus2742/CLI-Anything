# doc2video: Project-Specific Analysis & SOP

## Architecture Summary

doc2video is a pure-Python CLI tool that converts documents into narrated MP4 videos.
It chains four open-source components: a document parser, edge-tts for voiceover,
Pillow for frame rendering, and ffmpeg for final video assembly.

```
+-----------------------------------------------------------+
|                    doc2video CLI                           |
|  +--------+  +-------+  +--------+  +-------+            |
|  | parse  |  |  tts  |  | render |  | merge |            |
|  | (text/ |  |(edge- |  |(Pillow)|  |(ffmpeg|            |
|  |  md/   |  | tts)  |  |frames) |  |  mp4) |            |
|  |  pdf)  |  |       |  |        |  |       |            |
|  +---+----+  +---+---+  +---+----+  +---+---+            |
|      |            |          |           |                 |
|  +---+------------+----------+-----------+---+            |
|  |              process (full pipeline)      |            |
|  +-------------------------------------------+            |
+-----------------------------------------------------------+
```

## CLI Strategy: Pure Python Implementation

Unlike harnesses that wrap existing GUI apps, doc2video is itself the tool.
The harness IS the implementation — no subprocess delegation to a backend needed.

### Why pure Python?
- **edge-tts**: Free, no API key, supports 100+ voices, works offline-ish
- **Pillow**: Universal image generation, no system deps beyond libpng
- **ffmpeg**: System-level video assembly, battle-tested, universally available
- **pypdf**: PDF text extraction, pure Python

## Pipeline Detail

### Phase 1: parse
Reads `.txt`, `.md`, or `.pdf` and splits into slides by:
1. Existing `---` dividers (explicit slide breaks)
2. Markdown headings (`#`, `##`) — each heading starts a new slide
3. Falls back to single-slide if no structure detected

### Phase 2: tts
- Uses `edge-tts` (Microsoft Edge TTS, free)
- Strips markdown syntax before speech (headings, bold, links, code)
- Outputs `.mp3`
- Supports 100+ voices via `edge-tts --list-voices`

### Phase 3: render
- Renders each slide as a 1280×720 (default) PNG frame sequence
- Each slide gets `fps` identical frames (placeholder; real timing is controlled by TTS length via `-shortest` in ffmpeg)
- Three style presets: `default` (light), `dark`, `minimal`
- Falls back to PIL default font if no system font found

### Phase 4: merge
- `ffmpeg -framerate N -i frame_%06d.png -i audio.mp3 -shortest output.mp4`
- `-shortest` ensures video ends when audio ends — actual slide timing scales proportionally
- CRF quality: ultra=18, high=23, medium=28, low=32

## Frame Timing Model

The frame renderer writes `fps` frames per slide as placeholder timing.
The final video duration is determined by the TTS audio length (via `-shortest`).
This means all slides are equally weighted — the video fast-forwards/slow-downs through
slides to match the audio. For unequal timing, users should use `render` + `merge`
separately and provide a custom frame sequence.

## Testing Strategy

- **Unit tests** (`test_core.py`): Test parse logic, mock ffmpeg/Pillow absence
- **E2E tests** (`test_full_e2e.py`): Real pipeline with test fixtures

## Limitations

- Slide timing is uniform (equal time per slide); custom timing requires manual pipeline
- PDF parsing quality depends on document structure (scanned PDFs not supported)
- `edge-tts` requires network access (Microsoft's TTS service)
- Complex markdown (tables, code blocks) renders as plain text in speech

## Dependencies

| Package | Purpose | Required |
|---------|---------|---------|
| `edge-tts` | TTS voiceover | Yes (for audio) |
| `Pillow` | Frame rendering | Yes |
| `ffmpeg` | Video assembly | Yes (system) |
| `pypdf` | PDF parsing | Yes (for PDF input) |
| `click` | CLI framework | Yes |
| `prompt-toolkit` | REPL mode | Yes |
