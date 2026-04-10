"""Render document slides into image frames.

Renderer priority:
  1. Marp CLI  (npm install -g @marp-team/marp-cli)
  2. Playwright HTML (fallback)
  3. Pillow    (final fallback)
"""
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _ensure_marp() -> bool:
    """Return True if marp is available (install silently if not)."""
    if shutil.which("marp"):
        return True
    if not shutil.which("npm"):
        return False
    try:
        print("[render] Installing marp-cli (first run, ~10s)...")
        subprocess.run(
            ["npm", "install", "-g", "@marp-team/marp-cli", "--prefer-offline"],
            capture_output=True, timeout=120, check=True,
        )
        return bool(shutil.which("marp"))
    except Exception:
        return False


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
    """Try Marp → Playwright → Pillow, return result dict."""
    os.makedirs(output_dir, exist_ok=True)

    # 1. Marp CLI (auto-install if npm available)
    if _ensure_marp():
        try:
            return _render_marp(
                text_file, output_dir, width, height, fps, style, audio_file, secs_per_slide
            )
        except Exception as e:
            print(f"[render] Marp failed ({e}), trying Playwright...")

    # 2. Playwright
    try:
        return _render_playwright(
            text_file, output_dir, width, height, fps, style, audio_file, secs_per_slide
        )
    except Exception as e:
        print(f"[render] Playwright failed ({e}), using Pillow fallback...")

    # 3. Pillow
    return _render_pillow(
        text_file, output_dir, width, height, fps, style, audio_file, secs_per_slide
    )


# ---------------------------------------------------------------------------
# Marp renderer
# ---------------------------------------------------------------------------

def _render_marp(
    text_file, output_dir, width, height, fps, style, audio_file, secs_per_slide
) -> dict:
    """Use marp-cli to render each slide as PNG, then duplicate frames."""

    # Ensure input is valid Marp Markdown (inject frontmatter if missing)
    src = Path(text_file).read_text(encoding="utf-8")
    if not src.strip().startswith("---"):
        theme = _style_to_marp_theme(style)
        frontmatter = (
            f"---\nmarp: true\ntheme: {theme}\npaginate: true\n"
            "style: |\n  section {\n"
            "    font-family: 'PingFang SC', 'Microsoft YaHei', "
            "'Hiragino Sans GB', sans-serif;\n  }\n---\n\n"
        )
        marp_file = text_file + ".marp.md"
        Path(marp_file).write_text(frontmatter + src, encoding="utf-8")
    else:
        marp_file = text_file

    # Run marp --images png
    result = subprocess.run(
        [
            "marp",
            marp_file,
            "--images", "png",
            "--output", output_dir,
            "--allow-local-files",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"marp exited {result.returncode}: {result.stderr[:400]}")

    # Marp outputs: <output_dir>/<stem>.001.png, .002.png ...
    stem = Path(marp_file).stem
    slide_imgs = sorted(Path(output_dir).glob(f"{stem}.*.png"))
    if not slide_imgs:
        # Some marp versions output differently
        slide_imgs = sorted(Path(output_dir).glob("*.png"))

    if not slide_imgs:
        raise RuntimeError("Marp produced no PNG files")

    slide_count = len(slide_imgs)
    frames_per_slide = _calc_frames_per_slide(audio_file, slide_count, fps, secs_per_slide)

    # Rename/duplicate to frame_XXXXXX.png sequence
    frame_index = 0
    for img_path in slide_imgs:
        first_dst = Path(output_dir) / f"frame_{frame_index:06d}.png"
        shutil.copy2(img_path, first_dst)
        for i in range(1, frames_per_slide):
            shutil.copy2(first_dst, Path(output_dir) / f"frame_{frame_index + i:06d}.png")
        img_path.unlink()  # remove original marp output
        frame_index += frames_per_slide

    return {
        "frame_count": frame_index,
        "slide_count": slide_count,
        "output_dir": output_dir,
        "fps": fps,
        "renderer": "marp",
    }


def _style_to_marp_theme(style: str) -> str:
    mapping = {
        "default": "default",
        "dark": "gaia",
        "minimal": "uncover",
        "gradient": "gaia",
    }
    return mapping.get(style, "default")


# ---------------------------------------------------------------------------
# Playwright fallback renderer
# ---------------------------------------------------------------------------

SLIDE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ width: 1280px; height: 720px; overflow: hidden; }}
  body {{
    font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei',
                 'Noto Sans CJK SC', sans-serif;
    background: {bg};
    position: relative;
  }}
  .bar  {{ position: absolute; left: 56px; top: 50px; bottom: 50px; width: 6px; background: {accent}; border-radius: 3px; }}
  .bar2 {{ position: absolute; left: 68px; top: 50px; bottom: 50px; width: 6px; background: {gold};   border-radius: 3px; }}
  .tag  {{
    position: absolute; top: 52px; left: 96px;
    background: {accent}; color: {bg};
    font-size: 14px; font-weight: 700; padding: 4px 16px;
    border-radius: 3px; letter-spacing: 1.5px; white-space: nowrap;
  }}
  .title {{
    position: absolute; top: 100px; left: 96px; right: 72px;
    font-size: {title_size}px; font-weight: 700; color: {title_color};
    line-height: 1.35; word-break: break-all; overflow-wrap: break-word;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }}
  .divider {{ position: absolute; top: 196px; left: 96px; right: 72px; height: 1px; background: {accent}; opacity: 0.3; }}
  .body {{ position: absolute; top: 212px; left: 96px; right: 72px; bottom: 52px; overflow: hidden; }}
  .body ul {{ list-style: none; padding: 0; margin: 0; }}
  .body ul li {{
    display: flex; align-items: flex-start; gap: 12px;
    padding: 7px 0; border-bottom: 1px solid rgba(255,255,255,0.05);
    font-size: {body_size}px; color: {body_color}; line-height: 1.6;
    word-break: break-all; overflow-wrap: break-word;
  }}
  .body ul li:last-child {{ border-bottom: none; }}
  .body ul li .dot {{ flex-shrink: 0; width: 9px; height: 9px; border-radius: 2px; margin-top: 6px; }}
  .body ul li:nth-child(3n+1) .dot {{ background: {accent}; }}
  .body ul li:nth-child(3n+2) .dot {{ background: {gold}; }}
  .body ul li:nth-child(3n+0) .dot {{ background: {green}; }}
  .body ul li .text {{ flex: 1; min-width: 0; }}
  pre {{
    background: {code_bg}; color: {code_color};
    padding: 12px 16px; border-radius: 6px;
    font-size: {code_size}px; font-family: 'JetBrains Mono', 'Fira Code', monospace;
    line-height: 1.6; margin: 4px 0; word-break: break-all; white-space: pre-wrap;
  }}
  .num {{ position: absolute; right: 68px; bottom: 18px; font-size: 12px; color: {body_color}; opacity: 0.28; }}
</style>
</head>
<body>
  <div class="bar"></div><div class="bar2"></div>
  <div class="tag">{tag}</div>
  <div class="title">{title}</div>
  <div class="divider"></div>
  <div class="body">{body_html}</div>
  <div class="num">{slide_num} / {total_slides}</div>
</body>
</html>"""

STYLES = {
    "default": {"bg":"#0A0F2E","title_color":"#FFFFFF","body_color":"#AABBCC","accent":"#00B4D8","gold":"#FFD100","green":"#00E596","code_bg":"#0D1535","code_color":"#00E596","title_size":42,"body_size":23,"code_size":18},
    "dark":    {"bg":"#0D1117","title_color":"#F0F6FC","body_color":"#8B949E","accent":"#58A6FF","gold":"#F0A040","green":"#3FB950","code_bg":"#161B22","code_color":"#7EE787","title_size":42,"body_size":23,"code_size":18},
    "minimal": {"bg":"#FAFAFA","title_color":"#111111","body_color":"#444444","accent":"#2563EB","gold":"#D97706","green":"#059669","code_bg":"#F1F5F9","code_color":"#1E40AF","title_size":40,"body_size":22,"code_size":17},
    "gradient":{"bg":"#0F0C29","title_color":"#FFFFFF","body_color":"#CCCCDD","accent":"#E94560","gold":"#FFB700","green":"#06D6A0","code_bg":"rgba(255,255,255,0.08)","code_color":"#FFA07A","title_size":42,"body_size":23,"code_size":18},
}


def _render_playwright(
    text_file, output_dir, width, height, fps, style, audio_file, secs_per_slide
) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("playwright not found")

    slides = _parse_slides(text_file)
    s = STYLES.get(style, STYLES["default"])
    frames_per_slide = _calc_frames_per_slide(audio_file, len(slides), fps, secs_per_slide)

    frame_index = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        for idx, (title, body) in enumerate(slides):
            html = _build_html(title, body, idx + 1, len(slides), s)
            page.set_content(html, wait_until="domcontentloaded")
            first = os.path.join(output_dir, f"frame_{frame_index:06d}.png")
            page.screenshot(path=first, type="png")
            for i in range(1, frames_per_slide):
                shutil.copy2(first, os.path.join(output_dir, f"frame_{frame_index+i:06d}.png"))
            frame_index += frames_per_slide
        browser.close()

    return {"frame_count": frame_index, "slide_count": len(slides), "output_dir": output_dir, "fps": fps, "renderer": "playwright"}


# ---------------------------------------------------------------------------
# Pillow final fallback
# ---------------------------------------------------------------------------

def _render_pillow(
    text_file, output_dir, width, height, fps, style, audio_file, secs_per_slide
) -> dict:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise RuntimeError("Pillow not installed: pip install Pillow")

    slides = _parse_slides(text_file)
    s = STYLES.get(style, STYLES["default"])
    frames_per_slide = _calc_frames_per_slide(audio_file, len(slides), fps, secs_per_slide)

    font_title = font_body = None
    for fp in [
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        if os.path.exists(fp):
            try:
                font_title = ImageFont.truetype(fp, s["title_size"])
                font_body  = ImageFont.truetype(fp, s["body_size"])
                break
            except Exception:
                pass

    def h2rgb(h):
        if not h.startswith("#"): return (50, 50, 80)
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    import textwrap
    frame_index = 0
    for title, body in slides:
        img = Image.new("RGB", (width, height), h2rgb(s["bg"]))
        draw = ImageDraw.Draw(img)
        pad = 96
        draw.rectangle([56, 50, 62, height-50], fill=h2rgb(s["accent"]))
        draw.rectangle([68, 50, 74, height-50], fill=h2rgb(s["gold"]))
        draw.multiline_text((pad, 100), textwrap.fill(title, 36), font=font_title, fill=h2rgb(s["title_color"]))
        draw.line([(pad, 196), (width-72, 196)], fill=h2rgb(s["accent"]), width=1)
        y = 214
        colors = [h2rgb(s["accent"]), h2rgb(s["gold"]), h2rgb(s["green"])]
        for i, line in enumerate([l.strip().lstrip("-*•").strip() for l in body.splitlines() if l.strip()]):
            if y > height - 60: break
            draw.rectangle([pad, y+6, pad+9, y+15], fill=colors[i % 3])
            wrapped = textwrap.fill(line, 52)
            draw.multiline_text((pad+22, y), wrapped, font=font_body, fill=h2rgb(s["body_color"]), spacing=5)
            y += (wrapped.count("\n")+1) * (s["body_size"]+6) + 10
        fp = os.path.join(output_dir, f"frame_{frame_index:06d}.png")
        img.save(fp, "PNG")
        for i in range(1, frames_per_slide):
            shutil.copy2(fp, os.path.join(output_dir, f"frame_{frame_index+i:06d}.png"))
        frame_index += frames_per_slide

    return {"frame_count": frame_index, "slide_count": len(slides), "output_dir": output_dir, "fps": fps, "renderer": "pillow"}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _parse_slides(text_file: str) -> list[tuple[str, str]]:
    with open(text_file, encoding="utf-8") as f:
        content = f.read()

    # Strip Marp frontmatter
    content = re.sub(r"^---\s*\nmarp:.*?---\s*\n", "", content, flags=re.DOTALL)

    raw = [s.strip() for s in re.split(r"\n\s*---\s*\n", content) if s.strip()]
    if not raw:
        raw = [content.strip()]

    result = []
    for slide in raw:
        lines = slide.splitlines()
        title = lines[0].lstrip("#").strip() if lines else ""
        body  = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
        result.append((title, body))
    return result


def _build_html(title: str, body: str, slide_num: int, total: int, s: dict) -> str:
    import html as html_mod

    tag = "INTRO" if slide_num == 1 else ("SUMMARY" if slide_num == total else f"PART  {slide_num-1:02d}")

    code_blocks: dict[str, str] = {}
    def extract_code(m):
        key = f"\x00CODE{len(code_blocks)}\x00"
        code_blocks[key] = f"<pre>{html_mod.escape(m.group(1))}</pre>"
        return key

    body_clean = re.sub(r"```(?:\w+)?\n?(.*?)```", extract_code, body, flags=re.DOTALL)
    lines = [l.strip().lstrip("-*•").strip() for l in body_clean.splitlines() if l.strip()]

    items = ""
    for line in lines:
        if line in code_blocks:
            items += code_blocks[line]
        else:
            items += f'<li><span class="dot"></span><span class="text">{html_mod.escape(line)}</span></li>'

    body_html = f"<ul>{items}</ul>" if items else ""

    return SLIDE_TEMPLATE.format(
        **s,
        tag=tag,
        title=html_mod.escape(title),
        body_html=body_html,
        slide_num=slide_num,
        total_slides=total,
    )


def _get_audio_duration(audio_file: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_file],
            capture_output=True, text=True, timeout=10,
        )
        return float(r.stdout.strip())
    except Exception:
        return 30.0


def _calc_frames_per_slide(audio_file: Optional[str], slide_count: int, fps: int, secs_per_slide: int) -> int:
    if audio_file and os.path.exists(audio_file):
        duration = _get_audio_duration(audio_file)
        total_frames = math.ceil(duration * fps)
        return max(fps, total_frames // max(slide_count, 1))
    return secs_per_slide * fps
