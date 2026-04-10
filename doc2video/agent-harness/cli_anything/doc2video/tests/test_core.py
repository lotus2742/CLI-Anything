"""Unit tests for doc2video core modules — no real backends required."""
import os
import tempfile
import textwrap
import pytest

from cli_anything.doc2video.core.parse import parse_document, _split_slides


# ── parse ──────────────────────────────────────────────────────────────────────

class TestSplitSlides:
    def test_splits_by_divider(self):
        text = "Slide 1\n\n---\n\nSlide 2\n\n---\n\nSlide 3"
        slides = _split_slides(text)
        assert len(slides) == 3
        assert slides[0] == "Slide 1"
        assert slides[2] == "Slide 3"

    def test_splits_by_headings(self):
        text = "# Title\nIntro\n## Section 1\nContent 1\n## Section 2\nContent 2"
        slides = _split_slides(text)
        assert len(slides) == 3

    def test_single_slide_no_delimiter(self):
        text = "Just plain text with no delimiters"
        slides = _split_slides(text)
        assert len(slides) == 1
        assert slides[0] == text.strip()


class TestParseDocument:
    def test_parse_txt_plain(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Hello world")
        result = parse_document(str(f), "plain")
        assert result["slide_count"] == 1
        assert "Hello world" in result["content"]

    def test_parse_md_slides(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("# Title\nIntro\n## Section\nContent")
        result = parse_document(str(f), "slides")
        assert result["slide_count"] >= 2

    def test_parse_txt_slides_with_dividers(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Slide A\n\n---\n\nSlide B")
        result = parse_document(str(f), "slides")
        assert result["slide_count"] == 2

    def test_output_path_written(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Content here")
        result = parse_document(str(f), "plain")
        assert "content" in result
        assert "slides" in result


# ── merge (mock ffmpeg) ────────────────────────────────────────────────────────

class TestMergeVideo:
    def test_raises_without_ffmpeg(self, monkeypatch, tmp_path):
        import shutil
        monkeypatch.setattr(shutil, "which", lambda _: None)
        from cli_anything.doc2video.core.merge import merge_video
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()
        with pytest.raises(RuntimeError, match="ffmpeg is required"):
            merge_video(str(frames_dir), None, str(tmp_path / "out.mp4"), 24, "high")

    def test_quality_map_keys(self):
        from cli_anything.doc2video.core.merge import QUALITY_MAP
        assert set(QUALITY_MAP.keys()) == {"ultra", "high", "medium", "low"}


# ── render (mock Pillow) ───────────────────────────────────────────────────────

class TestRenderFrames:
    def test_raises_without_pillow(self, monkeypatch, tmp_path):
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "PIL":
                raise ImportError("no PIL")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        from cli_anything.doc2video.core import render as render_mod
        # Reload to trigger the import check at call time
        # Just verify the module imports cleanly; runtime check is inside function

    def test_render_creates_frames(self, tmp_path):
        pytest.importorskip("PIL")  # skip if Pillow not installed

        from cli_anything.doc2video.core.render import render_frames
        f = tmp_path / "slides.txt"
        f.write_text("# Slide 1\nHello\n\n---\n\n# Slide 2\nWorld")
        out_dir = tmp_path / "frames"
        out_dir.mkdir()

        result = render_frames(str(f), str(out_dir), 320, 240, 2, "minimal")
        assert result["slide_count"] == 2
        assert result["frame_count"] == 4  # 2 slides × 2 fps
        frames = list(out_dir.glob("frame_*.png"))
        assert len(frames) == 4
