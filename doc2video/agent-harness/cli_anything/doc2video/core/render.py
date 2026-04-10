"""Render document slides into image frames using Playwright (HTML screenshot)."""
import math
import os
import re
import subprocess
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# HTML slide template — 严格约束布局，防溢出
# ---------------------------------------------------------------------------

SLIDE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  html, body {{
    width: 1280px;
    height: 720px;
    overflow: hidden;
  }}

  body {{
    font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei',
                 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', sans-serif;
    background: {bg};
    position: relative;
  }}

  /* ── 双色左侧竖线 ── */
  .bar {{
    position: absolute;
    left: 56px;
    top: 50px;
    bottom: 50px;
    width: 6px;
    background: {accent};
    border-radius: 3px;
  }}
  .bar2 {{
    position: absolute;
    left: 68px;
    top: 50px;
    bottom: 50px;
    width: 6px;
    background: {gold};
    border-radius: 3px;
  }}

  /* ── 标签 pill ── */
  .tag {{
    position: absolute;
    top: 52px;
    left: 96px;
    background: {accent};
    color: {bg};
    font-size: 14px;
    font-weight: 700;
    padding: 4px 16px;
    border-radius: 3px;
    letter-spacing: 1.5px;
    white-space: nowrap;
  }}

  /* ── 标题 ── */
  .title {{
    position: absolute;
    top: 100px;
    left: 96px;
    right: 72px;
    font-size: {title_size}px;
    font-weight: 700;
    color: {title_color};
    line-height: 1.35;
    word-break: break-all;
    overflow-wrap: break-word;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }}

  /* ── 分隔线 ── */
  .divider {{
    position: absolute;
    top: 196px;
    left: 96px;
    right: 72px;
    height: 1px;
    background: {accent};
    opacity: 0.3;
  }}

  /* ── 正文容器 ── */
  .body {{
    position: absolute;
    top: 216px;
    left: 96px;
    right: 72px;
    bottom: 56px;
    overflow: hidden;
  }}

  /* ── 列表样式 ── */
  .body ul {{
    list-style: none;
    padding: 0;
    margin: 0;
  }}

  .body ul li {{
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 9px 0;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    font-size: {body_size}px;
    color: {body_color};
    line-height: 1.65;
    word-break: break-all;
    overflow-wrap: break-word;
  }}

  .body ul li:last-child {{
    border-bottom: none;
  }}

  .body ul li .dot {{
    flex-shrink: 0;
    width: 10px;
    height: 10px;
    border-radius: 2px;
    margin-top: 7px;
  }}

  .body ul li:nth-child(3n+1) .dot {{ background: {accent}; }}
  .body ul li:nth-child(3n+2) .dot {{ background: {gold}; }}
  .body ul li:nth-child(3n+0) .dot {{ background: {green}; }}

  .body ul li .text {{
    flex: 1;
    min-width: 0;
  }}

  /* ── 代码块 ── */
  pre {{
    background: {code_bg};
    color: {code_color};
    padding: 14px 18px;
    border-radius: 6px;
    font-size: {code_size}px;
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code',
                 'Courier New', monospace;
    line-height: 1.6;
    margin: 6px 0;
    overflow: hidden;
    word-break: break-all;
    white-space: pre-wrap;
  }}

  code {{
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    background: {code_bg};
    color: {code_color};
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 0.88em;
  }}

  /* ── 页码 ── */
  .num {{
    position: absolute;
    right: 68px;
    bottom: 22px;
    font-size: 12px;
    color: {body_color};
    opacity: 0.28;
    letter-spacing: 1px;
  }}
</style>
</head>
<body>
  <div class="bar"></div>
  <div class="bar2"></div>
  <div class="tag">{tag}</div>
  <div class="title">{title}</div>
  <div class="divider"></div>
  <div class="body">{body_html}</div>
  <div class="num">{slide_num} / {total_slides}</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------

STYLES = {
    "default": {
        "bg": "#0A0F2E",
        "title_color": "#FFFFFF",
        "body_color": "#AABBCC",
        "accent": "#00B4D8",
        "gold": "#FFD100",
        "green": "#00E596",
        "card_bg": "#101840",
        "code_bg": "#0D1535",
        "code_color": "#00E596",
        "title_size": 42,
        "body_size": 23,
        "code_size": 18,
    },
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
        "title_size": 42,
        "body_size": 23,
        "code_size": 18,
    },
    "minimal": {
        "bg": "#FAFAFA",
        "title_color": "#111111",
        "body_color": "#444444",
        "accent": "#2563EB",
        "gold": "#D97706",
        "green": "#059669",
        "card_bg": "#EEF2FF",
        "code_bg": "#F1F5F9",
        "code_color": "#1E40AF",
        "title_size": 40,
        "body_size": 22,
        "code_size": 17,
    },
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
        "title_size": 42,
        "body_size": 23,
        "code_size": 18,
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
    try:
        return _render_playwright(
            text_file, output_dir, width, height, fps, style, audio_file, secs_per_slide
        )
    except Exception as e:
        if "playwright" in str(e).lower() or "not found" in str(e).lower() or "module" in str(e).lower():
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
        raise RuntimeError("playwright not found")

    slides = _parse_slides(text_file)
    s = STYLES.get(style, STYLES["default"])
    os.makedirs(output_dir, exist_ok=True)

    frames_per_slide = _calc_frames_per_slide(
        audio_file, len(slides), fps, secs_per_slide
    )

    frame_index = 0
    import shutil
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})

        for slide_idx, (title, body) in enumerate(slides):
            html = _build_html(title, body, slide_idx + 1, len(slides), s)
            page.set_content(html, wait_until="domcontentloaded")

            first_path = os.path.join(output_dir, f"frame_{frame_index:06d}.png")
            page.screenshot(path=first_path, type="png")

            for i in range(1, frames_per_slide):
                dup_path = os.path.join(output_dir, f"frame_{frame_index + i:06d}.png")
                shutil.copy2(first_path, dup_path)

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
        if not h.startswith("#"):
            return (50, 50, 80)
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    import shutil, textwrap
    frame_index = 0
    for title, body in slides:
        bg = hex_to_rgb(s["bg"])
        title_c = hex_to_rgb(s["title_color"])
        body_c = hex_to_rgb(s["body_color"])
        accent_c = hex_to_rgb(s["accent"])
        gold_c = hex_to_rgb(s["gold"])

        img = Image.new("RGB", (width, height), bg)
        draw = ImageDraw.Draw(img)
        pad = 96

        # Dual bars
        draw.rectangle([56, 50, 62, height - 50], fill=accent_c)
        draw.rectangle([68, 50, 74, height - 50], fill=gold_c)

        # Title (wrapped)
        wrapped_title = textwrap.fill(title, width=36)
        draw.multiline_text((pad, 100), wrapped_title, font=font_title, fill=title_c)
        draw.line([(pad, 196), (width - 72, 196)], fill=accent_c, width=1)

        # Body lines as bullets
        y = 216
        lines = [l.strip().lstrip("-*•").strip() for l in body.splitlines() if l.strip()]
        colors = [accent_c, gold_c, hex_to_rgb(s["green"])]
        for i, line in enumerate(lines):
            if y > height - 70:
                break
            draw.rectangle([pad, y + 6, pad + 9, y + 15], fill=colors[i % 3])
            wrapped = textwrap.fill(line, width=52)
            draw.multiline_text((pad + 22, y), wrapped, font=font_body, fill=body_c, spacing=6)
            line_h = (wrapped.count("\n") + 1) * (s["body_size"] + 6) + 12
            y += line_h

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

    if slide_num == 1:
        tag = "INTRO"
    elif slide_num == total:
        tag = "SUMMARY"
    else:
        tag = f"PART  {slide_num - 1:02d}"

    # Extract code blocks first
    code_blocks = {}
    def extract_code(m):
        key = f"\x00CODE{len(code_blocks)}\x00"
        code_blocks[key] = f"<pre>{html_mod.escape(m.group(1))}</pre>"
        return key

    body_clean = re.sub(r"```(?:\w+)?\n?(.*?)```", extract_code, body, flags=re.DOTALL)

    # Build list items from lines
    lines = [l.strip().lstrip("-*•").strip() for l in body_clean.splitlines() if l.strip()]
    items_html = ""
    for line in lines:
        if line.startswith("\x00CODE"):
            items_html += code_blocks.get(line, "")
        else:
            items_html += f'<li><span class="dot"></span><span class="text">{html_mod.escape(line)}</span></li>'

    body_html = f"<ul>{items_html}</ul>" if items_html else ""

    return SLIDE_TEMPLATE.format(
        bg=s["bg"],
        title_color=s["title_color"],
        body_color=s["body_color"],
        accent=s["accent"],
        gold=s["gold"],
        green=s["green"],
        code_bg=s["code_bg"],
        code_color=s["code_color"],
        title_size=s["title_size"],
        body_size=s["body_size"],
        code_size=s["code_size"],
        tag=tag,
        title=html_mod.escape(title),
        body_html=body_html,
        slide_num=slide_num,
        total_slides=total,
    )


def _get_audio_duration(audio_file: str) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             audio_file],
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
