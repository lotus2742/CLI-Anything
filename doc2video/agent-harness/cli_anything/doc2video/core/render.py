"""Render document slides into image frames using Playwright (HTML screenshot)."""
import math
import os
import re
import subprocess
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# HTML slide templates
# ---------------------------------------------------------------------------

SLIDE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=1280, height=720">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    width: 1280px;
    height: 720px;
    overflow: hidden;
    font-family: 'Inter', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
    background: {bg};
    color: {text_color};
    display: flex;
    align-items: center;
    justify-content: center;
  }}

  .slide {{
    width: 1140px;
    height: 640px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 60px 70px;
    position: relative;
  }}

  .accent-bar {{
    position: absolute;
    left: 0;
    top: 40px;
    bottom: 40px;
    width: 6px;
    background: {accent};
    border-radius: 3px;
  }}

  h1 {{
    font-size: {title_size}px;
    font-weight: 700;
    color: {title_color};
    line-height: 1.3;
    margin-bottom: 24px;
    padding-left: 28px;
  }}

  .divider {{
    height: 2px;
    background: {accent};
    margin-bottom: 28px;
    margin-left: 28px;
    opacity: 0.4;
  }}

  .body {{
    font-size: {body_size}px;
    font-weight: 400;
    color: {body_color};
    line-height: 1.8;
    padding-left: 28px;
    white-space: pre-wrap;
  }}

  .slide-num {{
    position: absolute;
    right: 0;
    bottom: -20px;
    font-size: 13px;
    color: {body_color};
    opacity: 0.35;
  }}

  /* code block */
  code {{
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
    background: {code_bg};
    color: {code_color};
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.9em;
  }}

  pre {{
    background: {code_bg};
    color: {code_color};
    padding: 20px 24px;
    border-radius: 8px;
    font-size: {code_size}px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    line-height: 1.6;
    overflow: hidden;
    margin-top: 8px;
  }}
</style>
</head>
<body>
  <div class="slide">
    <div class="accent-bar"></div>
    <h1>{title}</h1>
    <div class="divider"></div>
    <div class="body">{body}</div>
    <div class="slide-num">{slide_num} / {total_slides}</div>
  </div>
</body>
</html>"""

STYLES = {
    "default": {
        "bg": "#F5F5FA",
        "text_color": "#2D2D3A",
        "title_color": "#1E1E50",
        "body_color": "#3C3C4A",
        "accent": "#4682C8",
        "code_bg": "#E8EAF0",
        "code_color": "#1E3A5F",
        "title_size": 44,
        "body_size": 26,
        "code_size": 20,
    },
    "dark": {
        "bg": "#12121A",
        "text_color": "#E8E8F5",
        "title_color": "#F0F0FF",
        "body_color": "#C0C0D0",
        "accent": "#64B4FF",
        "code_bg": "#1E1E2E",
        "code_color": "#A8D8A8",
        "title_size": 44,
        "body_size": 26,
        "code_size": 20,
    },
    "minimal": {
        "bg": "#FFFFFF",
        "text_color": "#141414",
        "title_color": "#141414",
        "body_color": "#505050",
        "accent": "#000000",
        "code_bg": "#F4F4F4",
        "code_color": "#222222",
        "title_size": 42,
        "body_size": 25,
        "code_size": 19,
    },
    "gradient": {
        "bg": "linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)",
        "text_color": "#EAEAEA",
        "title_color": "#FFFFFF",
        "body_color": "#CCCCDD",
        "accent": "#E94560",
        "code_bg": "rgba(255,255,255,0.08)",
        "code_color": "#FFA07A",
        "title_size": 44,
        "body_size": 26,
        "code_size": 20,
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_frames(
    text_file: str,
    output_dir: str,
    width: int,
    height: int,
    fps: int,
    style: str,
    audio_file: Optional[str] = None,
    secs_per_slide: int = 5,
) -> dict:
    """Render slides using Playwright HTML screenshots.

    Falls back to Pillow if Playwright is unavailable.
    """
    try:
        return _render_playwright(
            text_file, output_dir, width, height, fps, style, audio_file, secs_per_slide
        )
    except Exception as e:
        if "playwright" in str(e).lower() or "not found" in str(e).lower():
            return _render_pillow(
                text_file, output_dir, width, height, fps, style, audio_file, secs_per_slide
            )
        raise


# ---------------------------------------------------------------------------
# Playwright renderer
# ---------------------------------------------------------------------------

def _render_playwright(
    text_file, output_dir, width, height, fps, style, audio_file, secs_per_slide
):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "playwright not found. Install: pip install playwright && playwright install chromium"
        )

    slides = _parse_slides(text_file)
    s = STYLES.get(style, STYLES["default"])
    os.makedirs(output_dir, exist_ok=True)

    frames_per_slide = _calc_frames_per_slide(
        audio_file, len(slides), fps, secs_per_slide
    )

    frame_index = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})

        for slide_idx, (title, body) in enumerate(slides):
            html = _build_html(title, body, slide_idx + 1, len(slides), s)
            page.set_content(html, wait_until="networkidle")

            png_bytes = page.screenshot(type="png")
            frame_path = os.path.join(output_dir, f"frame_{frame_index:06d}.png")
            with open(frame_path, "wb") as f:
                f.write(png_bytes)

            # Duplicate frame for duration
            for i in range(1, frames_per_slide):
                dup_path = os.path.join(output_dir, f"frame_{frame_index + i:06d}.png")
                import shutil
                shutil.copy2(frame_path, dup_path)

            frame_index += frames_per_slide

        browser.close()

    return {
        "frame_count": frame_index,
        "slide_count": len(slides),
        "output_dir": output_dir,
        "fps": fps,
        "renderer": "playwright",
    }


# ---------------------------------------------------------------------------
# Pillow fallback renderer
# ---------------------------------------------------------------------------

def _render_pillow(
    text_file, output_dir, width, height, fps, style, audio_file, secs_per_slide
):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise RuntimeError("Pillow is required: pip install Pillow")

    slides = _parse_slides(text_file)
    s = STYLES.get(style, STYLES["default"])
    os.makedirs(output_dir, exist_ok=True)

    frames_per_slide = _calc_frames_per_slide(
        audio_file, len(slides), fps, secs_per_slide
    )

    font_title = font_body = None
    try:
        cjk_font_paths = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        for fp in cjk_font_paths:
            if os.path.exists(fp):
                font_title = ImageFont.truetype(fp, s["title_size"])
                font_body = ImageFont.truetype(fp, s["body_size"])
                break
    except Exception:
        pass

    def hex_to_rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    frame_index = 0
    import shutil, textwrap
    for title, body in slides:
        bg = hex_to_rgb(s["bg"]) if s["bg"].startswith("#") else (245, 245, 250)
        title_c = hex_to_rgb(s["title_color"])
        body_c = hex_to_rgb(s["body_color"])
        accent_c = hex_to_rgb(s["accent"])

        img = Image.new("RGB", (width, height), bg)
        draw = ImageDraw.Draw(img)
        pad = 80
        draw.rectangle([(pad, pad // 2), (pad + 6, height - pad // 2)], fill=accent_c)
        draw.multiline_text((pad + 28, pad), title, font=font_title, fill=title_c)
        draw.line([(pad + 28, pad + 70), (width - pad, pad + 70)], fill=accent_c, width=2)
        if body:
            wrapped = textwrap.fill(body, width=60)
            draw.multiline_text((pad + 28, pad + 90), wrapped, font=font_body, fill=body_c, spacing=10)

        frame_path = os.path.join(output_dir, f"frame_{frame_index:06d}.png")
        img.save(frame_path, "PNG")
        for i in range(1, frames_per_slide):
            shutil.copy2(frame_path, os.path.join(output_dir, f"frame_{frame_index + i:06d}.png"))
        frame_index += frames_per_slide

    return {
        "frame_count": frame_index,
        "slide_count": len(slides),
        "output_dir": output_dir,
        "fps": fps,
        "renderer": "pillow-fallback",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_slides(text_file: str) -> list[tuple[str, str]]:
    with open(text_file, encoding="utf-8") as f:
        content = f.read()

    raw_slides = [s.strip() for s in re.split(r"\n\s*---\s*\n", content) if s.strip()]
    if not raw_slides:
        raw_slides = [content.strip()]

    result = []
    for slide in raw_slides:
        lines = slide.splitlines()
        title = lines[0].lstrip("#").strip() if lines else ""
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
        result.append((title, body))
    return result


def _build_html(title: str, body: str, slide_num: int, total: int, s: dict) -> str:
    import html as html_mod
    # Render code blocks
    body_html = re.sub(
        r"```(?:\w+)?\n(.*?)```",
        lambda m: f"<pre>{html_mod.escape(m.group(1))}</pre>",
        body,
        flags=re.DOTALL,
    )
    body_html = re.sub(r"`([^`]+)`", lambda m: f"<code>{html_mod.escape(m.group(1))}</code>", body_html)
    body_html = html_mod.escape(body_html).replace("&lt;pre&gt;", "<pre>").replace("&lt;/pre&gt;", "</pre>")
    # Re-allow pre/code tags we injected
    body_html = re.sub(r"&lt;(/?(?:pre|code)[^&]*)&gt;", r"<\1>", body_html)
    body_html = body_html.replace("\n", "<br>")

    return SLIDE_TEMPLATE.format(
        bg=s["bg"],
        text_color=s["text_color"],
        title_color=s["title_color"],
        body_color=s["body_color"],
        accent=s["accent"],
        code_bg=s["code_bg"],
        code_color=s["code_color"],
        title_size=s["title_size"],
        body_size=s["body_size"],
        code_size=s["code_size"],
        title=html_mod.escape(title),
        body=body_html,
        slide_num=slide_num,
        total_slides=total,
    )


def _get_audio_duration(audio_file: str) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_file,
            ],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 30.0


def _calc_frames_per_slide(
    audio_file: Optional[str], slide_count: int, fps: int, secs_per_slide: int
) -> int:
    if audio_file and os.path.exists(audio_file):
        duration = _get_audio_duration(audio_file)
        total_frames = math.ceil(duration * fps)
        return max(fps, total_frames // max(slide_count, 1))
    return secs_per_slide * fps
