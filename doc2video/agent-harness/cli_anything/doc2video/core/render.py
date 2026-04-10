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
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    width: 1280px;
    height: 720px;
    overflow: hidden;
    font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif;
    background: {bg};
    position: relative;
  }}

  /* 双色左侧竖线（vlog-maker 风格） */
  .bar-blue {{
    position: absolute;
    left: 60px; top: 60px; bottom: 60px;
    width: 8px;
    background: {accent};
    border-radius: 4px;
  }}
  .bar-gold {{
    position: absolute;
    left: 76px; top: 60px; bottom: 60px;
    width: 8px;
    background: {gold};
    border-radius: 4px;
  }}

  /* 标签 pill */
  .tag {{
    position: absolute;
    top: 60px; left: 104px;
    background: {accent};
    color: {bg};
    font-size: 15px;
    font-weight: 700;
    padding: 5px 18px;
    border-radius: 4px;
    letter-spacing: 1px;
  }}

  /* 标题区 */
  .title {{
    position: absolute;
    top: 108px; left: 104px; right: 80px;
    font-size: {title_size}px;
    font-weight: 700;
    color: {title_color};
    line-height: 1.3;
  }}

  /* 分隔线 */
  .divider {{
    position: absolute;
    top: 210px; left: 104px; right: 80px;
    height: 2px;
    background: {accent};
    opacity: 0.25;
  }}

  /* 正文 */
  .body {{
    position: absolute;
    top: 234px; left: 104px; right: 80px; bottom: 80px;
    font-size: {body_size}px;
    color: {body_color};
    line-height: 1.9;
    overflow: hidden;
  }}

  /* 要点列表 */
  .body ul {{
    list-style: none;
    padding: 0;
  }}
  .body ul li {{
    padding: 8px 0 8px 28px;
    position: relative;
    border-bottom: 1px solid rgba(255,255,255,0.05);
  }}
  .body ul li::before {{
    content: '';
    position: absolute;
    left: 0; top: 50%;
    transform: translateY(-50%);
    width: 10px; height: 10px;
    background: {accent};
    border-radius: 2px;
  }}
  .body ul li:nth-child(2n)::before {{ background: {gold}; }}
  .body ul li:nth-child(3n)::before {{ background: {green}; }}

  /* 高亮卡片 */
  .highlight {{
    background: {card_bg};
    border-left: 5px solid {gold};
    padding: 16px 20px;
    border-radius: 0 8px 8px 0;
    margin-top: 12px;
    font-size: {body_size}px;
    color: {gold};
    font-weight: 600;
  }}

  /* 代码块 */
  pre {{
    background: {code_bg};
    color: {code_color};
    padding: 16px 20px;
    border-radius: 8px;
    font-size: {code_size}px;
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
    line-height: 1.6;
    margin-top: 8px;
    overflow: hidden;
  }}
  code {{
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    background: {code_bg};
    color: {code_color};
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 0.88em;
  }}

  /* 页码 */
  .slide-num {{
    position: absolute;
    right: 72px; bottom: 28px;
    font-size: 13px;
    color: {body_color};
    opacity: 0.3;
    letter-spacing: 1px;
  }}
</style>
</head>
<body>
  <div class="bar-blue"></div>
  <div class="bar-gold"></div>
  <div class="tag">{tag}</div>
  <div class="title">{title}</div>
  <div class="divider"></div>
  <div class="body">{body}</div>
  <div class="slide-num">{slide_num} / {total_slides}</div>
</body>
</html>"""

STYLES = {
    # vlog-maker 同款：深蓝科技风（默认）
    "default": {
        "bg": "#0A0F2E",
        "title_color": "#FFFFFF",
        "body_color": "#AABBCC",
        "accent": "#00B4D8",
        "gold": "#FFD100",
        "green": "#00E596",
        "card_bg": "#101840",
        "code_bg": "#101840",
        "code_color": "#00E596",
        "title_size": 44,
        "body_size": 24,
        "code_size": 19,
    },
    # 深色极简
    "dark": {
        "bg": "#0D1117",
        "title_color": "#F0F6FC",
        "body_color": "#8B949E",
        "accent": "#58A6FF",
        "gold": "#F0A040",
        "green": "#3FB950",
        "card_bg": "#161B22",
        "code_bg": "#161B22",
        "code_color": "#7EE787",
        "title_size": 44,
        "body_size": 24,
        "code_size": 19,
    },
    # 浅色商务
    "minimal": {
        "bg": "#FAFAFA",
        "title_color": "#111111",
        "body_color": "#555555",
        "accent": "#2563EB",
        "gold": "#D97706",
        "green": "#059669",
        "card_bg": "#EEF2FF",
        "code_bg": "#F1F5F9",
        "code_color": "#1E40AF",
        "title_size": 42,
        "body_size": 24,
        "code_size": 19,
    },
    # 深色渐变（视觉最强）
    "gradient": {
        "bg": "#0F0C29",
        "title_color": "#FFFFFF",
        "body_color": "#CCCCDD",
        "accent": "#E94560",
        "gold": "#FFB700",
        "green": "#06D6A0",
        "card_bg": "rgba(255,255,255,0.06)",
        "code_bg": "rgba(255,255,255,0.08)",
        "code_color": "#FFA07A",
        "title_size": 44,
        "body_size": 24,
        "code_size": 19,
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

    # Tag: PART 01 / 02 ... or INTRO / SUMMARY
    if slide_num == 1:
        tag = "INTRO"
    elif slide_num == total:
        tag = "SUMMARY"
    else:
        tag = f"PART  {slide_num - 1:02d}"

    # Code blocks → <pre>
    body_processed = re.sub(
        r"```(?:\w+)?\n(.*?)```",
        lambda m: f"\x00PRE\x00{html_mod.escape(m.group(1))}\x00/PRE\x00",
        body,
        flags=re.DOTALL,
    )

    # Split into lines, build list items or plain paragraphs
    lines = body_processed.splitlines()
    has_bullets = any(l.strip().startswith(("-", "*", "•")) for l in lines if l.strip())

    if has_bullets:
        items = []
        for line in lines:
            line = line.strip().lstrip("-*•").strip()
            if line:
                items.append(f"<li>{html_mod.escape(line)}</li>")
        body_html = "<ul>" + "".join(items) + "</ul>"
    else:
        # Auto-convert non-empty lines to bullet list
        items = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith("\x00PRE\x00"):
                items.append(f"<li>{html_mod.escape(line)}</li>")
            elif line.startswith("\x00PRE\x00"):
                code = line.replace("\x00PRE\x00", "").replace("\x00/PRE\x00", "")
                items.append(f"<pre>{code}</pre>")
        body_html = "<ul>" + "".join(items) + "</ul>" if items else ""

    # Restore pre blocks
    body_html = body_html.replace("\x00PRE\x00", "<pre>").replace("\x00/PRE\x00", "</pre>")

    return SLIDE_TEMPLATE.format(
        bg=s["bg"],
        title_color=s["title_color"],
        body_color=s["body_color"],
        accent=s["accent"],
        gold=s["gold"],
        green=s["green"],
        card_bg=s["card_bg"],
        code_bg=s["code_bg"],
        code_color=s["code_color"],
        title_size=s["title_size"],
        body_size=s["body_size"],
        code_size=s["code_size"],
        tag=tag,
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
