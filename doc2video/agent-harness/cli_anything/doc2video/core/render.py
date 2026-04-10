"""Render document slides into image frames.

Renderer priority:
  1. Marp CLI  (npm install -g @marp-team/marp-cli)
  2. Pillow    (fallback)
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

def _find_marp() -> Optional[str]:
    """Return marp executable path, or None if not found."""
    # 1. Already in PATH
    p = shutil.which("marp")
    if p:
        return p

    # 2. Look in npm global prefix bin directory (works with all npm versions)
    try:
        r = subprocess.run(
            ["npm", "prefix", "-g"], capture_output=True, text=True, timeout=10
        )
        npm_prefix = r.stdout.strip()
        if npm_prefix:
            candidate = os.path.join(npm_prefix, "bin", "marp")
            if os.path.isfile(candidate):
                return candidate
    except Exception:
        pass

    # 3. Common macOS/Linux paths
    for candidate in [
        os.path.expanduser("~/.npm-global/bin/marp"),
        "/usr/local/bin/marp",
        "/opt/homebrew/bin/marp",
        "/opt/homebrew/opt/node/bin/marp",
    ]:
        if os.path.isfile(candidate):
            return candidate

    return None


def _ensure_marp() -> Optional[str]:
    """Return marp path if available, auto-install if npm present."""
    p = _find_marp()
    if p:
        return p
    if not shutil.which("npm"):
        return None
    try:
        print("[render] Installing marp-cli (first run, ~10s)...")
        subprocess.run(
            ["npm", "install", "-g", "@marp-team/marp-cli", "--prefer-offline"],
            capture_output=True, timeout=120, check=True,
        )
        return _find_marp()
    except Exception:
        return None


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
    marp_bin = _ensure_marp()
    if marp_bin:
        try:
            return _render_marp(
                text_file, output_dir, width, height, fps, style, audio_file, secs_per_slide,
                marp_bin=marp_bin,
            )
        except Exception as e:
            print(f"[render] Marp failed ({e}), falling back to Pillow...")

    # 2. Pillow
    return _render_pillow(
        text_file, output_dir, width, height, fps, style, audio_file, secs_per_slide
    )


# ---------------------------------------------------------------------------
# Marp renderer
# ---------------------------------------------------------------------------

def _render_marp(
    text_file, output_dir, width, height, fps, style, audio_file, secs_per_slide,
    marp_bin: str = "marp",
) -> dict:
    """Use marp-cli to render each slide as PNG, then duplicate frames."""

    # Marp requires .md extension — always write to a temp .md file
    src = Path(text_file).read_text(encoding="utf-8")
    theme = _style_to_marp_theme(style)
    if not src.strip().startswith("---"):
        frontmatter = (
            f"---\nmarp: true\ntheme: {theme}\npaginate: true\n"
            "style: |\n  section {\n"
            "    font-family: 'PingFang SC', 'Microsoft YaHei', "
            "'Hiragino Sans GB', sans-serif;\n  }\n---\n\n"
        )
        content = frontmatter + src
    else:
        content = src

    marp_file = str(Path(text_file).with_suffix("")) + ".marp.md"
    Path(marp_file).write_text(content, encoding="utf-8")

    # Run marp --images png
    result = subprocess.run(
        [
            marp_bin,
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
# Pillow fallback renderer
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
