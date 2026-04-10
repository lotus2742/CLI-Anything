"""Render document slides into image frames using Pillow."""
import math
import os
import re
import textwrap
from pathlib import Path
from typing import Optional

# Style presets
STYLES = {
    "default": {
        "bg": (245, 245, 250),
        "title_color": (30, 30, 80),
        "body_color": (50, 50, 60),
        "accent": (70, 130, 200),
        "title_size": 52,
        "body_size": 32,
        "padding": 80,
    },
    "dark": {
        "bg": (18, 18, 24),
        "title_color": (240, 240, 255),
        "body_color": (200, 200, 210),
        "accent": (100, 180, 255),
        "title_size": 52,
        "body_size": 32,
        "padding": 80,
    },
    "minimal": {
        "bg": (255, 255, 255),
        "title_color": (20, 20, 20),
        "body_color": (80, 80, 80),
        "accent": (0, 0, 0),
        "title_size": 48,
        "body_size": 30,
        "padding": 100,
    },
}


def render_frames(
    text_file: str,
    output_dir: str,
    width: int,
    height: int,
    fps: int,
    style: str,
) -> dict:
    """Render slides from a text file into per-slide image frames.

    Each slide gets `fps` identical frames (1 second of video per slide by default).
    The actual duration matches the TTS audio when merged with ffmpeg -shortest.

    Returns:
        dict with frame_count, slide_count, output_dir
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise RuntimeError("Pillow is required: pip install Pillow")

    with open(text_file, encoding="utf-8") as f:
        content = f.read()

    slides = [s.strip() for s in re.split(r"\n\s*---\s*\n", content) if s.strip()]
    if not slides:
        slides = [content.strip()]

    s = STYLES.get(style, STYLES["default"])
    os.makedirs(output_dir, exist_ok=True)

    # Try to load a decent font; fall back to default
    font_title: Optional[object] = None
    font_body: Optional[object] = None
    try:
        from PIL import ImageFont
        # Try common system fonts
        for font_path in [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]:
            if os.path.exists(font_path):
                font_title = ImageFont.truetype(font_path, s["title_size"])
                font_body = ImageFont.truetype(font_path, s["body_size"])
                break
    except Exception:
        pass

    frame_index = 0
    for slide_idx, slide_text in enumerate(slides):
        img = _render_slide(slide_text, width, height, s, font_title, font_body)
        # Write fps frames for each slide (placeholder timing; real timing = TTS length)
        for _ in range(fps):
            frame_path = os.path.join(output_dir, f"frame_{frame_index:06d}.png")
            img.save(frame_path, "PNG")
            frame_index += 1

    return {
        "frame_count": frame_index,
        "slide_count": len(slides),
        "output_dir": output_dir,
        "fps": fps,
    }


def _render_slide(text: str, width: int, height: int, s: dict, font_title, font_body):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), s["bg"])
    draw = ImageDraw.Draw(img)

    pad = s["padding"]
    usable_w = width - pad * 2

    # Split title (first line) from body
    lines = text.strip().splitlines()
    title_line = lines[0].lstrip("#").strip() if lines else ""
    body_lines = lines[1:] if len(lines) > 1 else []
    body_text = "\n".join(body_lines).strip()

    # Draw accent bar
    draw.rectangle([(pad, pad // 2), (pad + 6, height - pad // 2)], fill=s["accent"])

    y = pad

    # Title
    ft = font_title
    wrapped_title = textwrap.fill(title_line, width=max(1, usable_w // (s["title_size"] // 2)))
    draw.multiline_text((pad + 20, y), wrapped_title, font=ft, fill=s["title_color"], spacing=8)
    title_h = _text_height(draw, wrapped_title, ft, s["title_size"])
    y += title_h + 30

    # Divider
    draw.line([(pad + 20, y), (width - pad, y)], fill=s["accent"], width=2)
    y += 20

    # Body
    if body_text:
        fb = font_body
        wrapped_body = textwrap.fill(body_text, width=max(1, usable_w // (s["body_size"] // 2)))
        draw.multiline_text((pad + 20, y), wrapped_body, font=fb, fill=s["body_color"], spacing=10)

    # Slide number watermark
    num_font = font_body
    draw.text((width - pad, height - pad // 2), f"{text[:0]}", font=num_font, fill=s["body_color"])

    return img


def _text_height(draw, text: str, font, fallback_size: int) -> int:
    try:
        bbox = draw.multiline_textbbox((0, 0), text, font=font)
        return bbox[3] - bbox[1]
    except Exception:
        return fallback_size * (text.count("\n") + 1)
