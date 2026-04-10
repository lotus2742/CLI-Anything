"""Render document slides into image frames.

Renderer priority:
  1. Marp CLI  (npm install -g @marp-team/marp-cli)
  2. Pillow    (vlog-maker quality fallback)
"""
import math
import os
import random
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
    """Try Marp → Pillow, return result dict."""
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

    # 2. Pillow (vlog-maker quality renderer)
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

    if not src.strip().startswith("---"):
        # No frontmatter: inject one using style → theme mapping
        theme = _style_to_marp_theme(style)
        frontmatter = (
            f"---\nmarp: true\ntheme: {theme}\npaginate: true\n"
            "style: |\n  section {\n"
            "    font-family: 'PingFang SC', 'Microsoft YaHei', "
            "'Hiragino Sans GB', sans-serif;\n  }\n---\n\n"
        )
        content = frontmatter + src
    elif style != "default":
        # LLM already wrote frontmatter; only override theme if user explicitly
        # passed --style (i.e., style is not the default "default")
        theme = _style_to_marp_theme(style)
        content = re.sub(
            r"(^---\n.*?theme:\s*)\S+",
            lambda m: m.group(1) + theme,
            src,
            count=1,
            flags=re.DOTALL,
        )
    else:
        # LLM wrote frontmatter, no --style override → respect LLM's choice
        content = src

    # If the input is already a .marp.md and we didn't modify content, reuse it
    src_path = Path(text_file)
    if src_path.name.endswith(".marp.md") and content == src:
        marp_file = str(src_path)
    else:
        # Strip all extensions to get the stem, then write .marp.md
        stem = src_path.name
        for suffix in (".marp.md", ".md", ".txt"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        marp_file = str(src_path.parent / (stem + ".marp.md"))
        Path(marp_file).write_text(content, encoding="utf-8")

    # Marp --output is a file *prefix*, not a directory.
    # e.g. --output /tmp/frames/slide  → /tmp/frames/slide.001, slide.002 ...
    marp_prefix = os.path.join(output_dir, "slide")
    result = subprocess.run(
        [
            marp_bin,
            marp_file,
            "--images", "png",
            "--output", marp_prefix,
            "--allow-local-files",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"marp exited {result.returncode}: {result.stderr[:400]}")

    # Marp outputs: slide.001, slide.002 ... (no .png extension in some versions)
    slide_imgs = sorted(
        p for p in Path(output_dir).iterdir()
        if re.match(r"slide\.\d+", p.name)
    )

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
# vlog-maker quality Pillow renderer
# ---------------------------------------------------------------------------

# ---- 画布尺寸 & 安全区 ----
_W, _H = 1280, 720
_SAFE_BOTTOM = _H - 144  # 576，字幕安全区

# ---- 配色（与 vlog-maker 完全一致）----
_BG          = (8, 4, 20)
_BG2         = (18, 10, 40)
_CARD        = (22, 14, 50)
_CARD_BORDER = (60, 30, 100)
_PURPLE_L    = (200, 120, 255)
_PURPLE_M    = (150, 80, 220)
_CYAN        = (100, 220, 255)
_PINK        = (255, 80, 180)
_WHITE       = (240, 235, 255)
_DIM         = (120, 100, 160)
_GOLD        = (255, 209, 0)
_GREEN       = (0, 229, 150)
_ORANGE      = (255, 107, 53)
_RED         = (255, 60, 60)

# ---- 光晕参数（严格对齐 vlog-maker 规范）----
_STANDARD_GLOW_POS = [
    (-600, -550,  400,  450,  (20,  60, 220)),
    (_W-400, -550, _W+600, 450, (180,  0, 200)),
    (-500, _H-450, 300,  _H+550, (10,  40, 160)),
    (_W-300, _H-450, _W+500, _H+550, (160, 0, 160)),
]
_STANDARD_GLOW_ALPHA  = 0.65
_STANDARD_BLUR_RADIUS = 150

# ---- 字体路径（只用 wqy-zenhei，禁止 microhei）----
_FONT_PATHS = [
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
]

_FONT_PATH_CACHE: Optional[str] = None


def _find_font() -> Optional[str]:
    """搜索 wqy-zenhei 字体路径，禁止 microhei。"""
    global _FONT_PATH_CACHE
    if _FONT_PATH_CACHE is not None:
        return _FONT_PATH_CACHE
    for p in _FONT_PATHS:
        if os.path.exists(p):
            _FONT_PATH_CACHE = p
            return p
    # 通过 fc-list 搜索，只接受 zenhei
    try:
        r = subprocess.run(["fc-list"], capture_output=True, text=True, timeout=10)
        for line in r.stdout.split("\n"):
            lline = line.lower()
            if "zenhei" in lline and "microhei" not in lline:
                _FONT_PATH_CACHE = line.split(":")[0].strip()
                return _FONT_PATH_CACHE
    except Exception:
        pass
    return None


def _load_font(size: int):
    """加载 wqy-zenhei 字体，fallback default。"""
    from PIL import ImageFont
    fp = _find_font()
    if fp:
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _draw_tag(draw, x: int, y: int, text: str, color: tuple, font_size: int = 18) -> int:
    """绘制带背景色的标签 pill，返回宽度。"""
    font = _load_font(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad_x, pad_y = 12, 6
    draw.rectangle([x, y, x + tw + pad_x * 2, y + th + pad_y * 2], fill=color, outline=color)
    draw.text((x + pad_x, y + pad_y), text, fill=_BG, font=font)
    return tw + pad_x * 2


def _make_base_purple(accent_color=None, glow_pos=None,
                      glow_alpha=_STANDARD_GLOW_ALPHA,
                      blur_radius=_STANDARD_BLUR_RADIUS):
    """生成极深紫黑背景（网格线 + 装饰角线 + 粒子 + 光晕）。"""
    from PIL import Image, ImageDraw, ImageFilter
    if accent_color is None:
        accent_color = _PURPLE_L
    random.seed(42)
    img = Image.new('RGB', (_W, _H), _BG)
    draw = ImageDraw.Draw(img)
    # 网格线
    for x in range(0, _W, 60):
        draw.line([(x, 0), (x, _H)], fill=(25, 15, 50), width=1)
    for y in range(0, _H, 60):
        draw.line([(0, y), (_W, y)], fill=(25, 15, 50), width=1)
    c = accent_color
    # 装饰角线
    draw.line([(0, 40), (120, 40)], fill=c, width=1)
    draw.line([(120, 40), (120, 0)], fill=c, width=1)
    draw.rectangle([116, 36, 124, 44], fill=c)
    draw.line([(40, 0), (40, 80)], fill=c, width=1)
    draw.rectangle([36, 76, 44, 84], fill=c)
    draw.line([(_W, _H-40), (_W-120, _H-40)], fill=c, width=1)
    draw.line([(_W-120, _H-40), (_W-120, _H)], fill=c, width=1)
    draw.rectangle([_W-124, _H-44, _W-116, _H-36], fill=c)
    draw.line([(_W-40, _H), (_W-40, _H-80)], fill=c, width=1)
    draw.rectangle([_W-44, _H-84, _W-36, _H-76], fill=c)
    draw.line([(_W, 60), (_W-80, 60)], fill=c, width=1)
    draw.rectangle([_W-84, 56, _W-76, 64], fill=c)
    draw.line([(0, _H-60), (80, _H-60)], fill=c, width=1)
    draw.rectangle([76, _H-64, 84, _H-56], fill=c)
    # 粒子
    for _ in range(60):
        px, py = random.randint(0, _W), random.randint(0, _H)
        rv = random.choice([1, 1, 1, 2])
        a = random.randint(40, 120)
        col = tuple(min(255, int(ch * a // 255)) for ch in c)
        draw.ellipse([px-rv, py-rv, px+rv, py+rv], fill=col)
    # 光晕
    effective_glow = glow_pos if glow_pos is not None else _STANDARD_GLOW_POS
    glow_img = Image.new('RGB', (_W, _H), (0, 0, 0))
    gdraw = ImageDraw.Draw(glow_img)
    for x1, y1, x2, y2, gc in effective_glow:
        gdraw.ellipse([x1, y1, x2, y2], fill=gc)
    glow_img = glow_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    img = Image.blend(img, glow_img, alpha=glow_alpha)
    return img


def _wrap_text(text: str, max_chars: int) -> list[str]:
    """简单按字符数换行（兼容中英文混排）。"""
    import textwrap
    return textwrap.wrap(text, max_chars) or [text]


def _draw_bullet_list(draw, items: list[str], x: int, y: int, max_y: int,
                      accent_color: tuple, font_size: int = 20) -> int:
    """绘制 bullet list，返回最终 y 坐标。每项超出安全区则截断。"""
    font = _load_font(font_size)
    line_h = font_size + 10
    for item in items:
        if y + line_h > max_y:
            break
        # 小色块 bullet
        draw.rectangle([x, y + 6, x + 8, y + 14], fill=accent_color)
        # 处理长文本换行
        for j, wrapped_line in enumerate(_wrap_text(item, 52)):
            if y + line_h > max_y:
                break
            draw.text((x + 20, y), wrapped_line, fill=_WHITE, font=font)
            y += line_h
        y += 4  # 条目间距
    return y


# ---- 布局实现 ----

def _layout_cover(img, title: str, body: str, slide_index: int, total_slides: int):
    """layout_0：封面型 - 大标题居中 + 副标题。"""
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)

    # 顶部装饰条
    draw.rectangle([0, 0, _W, 4], fill=_CYAN)

    # 大标题居中
    font_big = _load_font(54)
    font_sub = _load_font(28)
    font_small = _load_font(20)

    # 标题换行处理
    title_lines = _wrap_text(title, 28)
    title_y = 160
    for line in title_lines:
        bbox = draw.textbbox((0, 0), line, font=font_big)
        tw = bbox[2] - bbox[0]
        draw.text((_W // 2 - tw // 2, title_y), line, fill=_CYAN, font=font_big)
        title_y += 70

    # 分隔线
    draw.line([(200, title_y + 10), (_W - 200, title_y + 10)], fill=_CARD_BORDER, width=1)

    # 副标题
    if body:
        sub_lines = body.splitlines()
        sub_text = sub_lines[0].lstrip("-*•").strip() if sub_lines else ""
        if sub_text:
            bbox = draw.textbbox((0, 0), sub_text, font=font_sub)
            tw = bbox[2] - bbox[0]
            sub_y = title_y + 30
            if sub_y + 40 <= _SAFE_BOTTOM:
                draw.text((_W // 2 - tw // 2, sub_y), sub_text, fill=_WHITE, font=font_sub)

    # 底部标签（取 body 里的其他条目）
    if body:
        tag_lines = [l.lstrip("-*•").strip() for l in body.splitlines() if l.strip()][1:5]
        colors = [_CYAN, _PURPLE_L, _GOLD, _GREEN]
        tag_y = _SAFE_BOTTOM - 70
        if tag_lines and tag_y > title_y + 80:
            tag_x = 200
            for tag, color in zip(tag_lines, colors):
                if tag_x + 200 > _W - 200:
                    break
                w_ = _draw_tag(draw, tag_x, tag_y, tag, color, font_size=18)
                tag_x += w_ + 14

    # 幻灯片编号
    num_text = f"01 / {total_slides:02d}"
    draw.text((_W - 120, _SAFE_BOTTOM - 30), num_text, fill=_DIM, font=font_small)


def _layout_standard(img, title: str, body: str, slide_index: int, total_slides: int,
                      accent_color: tuple = None):
    """layout_1：标准内容 - 顶部标题 + 左色条 + bullet list。"""
    from PIL import ImageDraw
    if accent_color is None:
        # 颜色轮换：CYAN/PURPLE_L/GOLD/GREEN
        palette = [_CYAN, _PURPLE_L, _GOLD, _GREEN]
        accent_color = palette[slide_index % len(palette)]

    draw = ImageDraw.Draw(img)

    # 顶部装饰条
    draw.rectangle([0, 0, _W, 4], fill=accent_color)

    # 标题区卡片
    title_card_top = 30
    title_card_bot = 120
    draw.rectangle([60, title_card_top, _W - 60, title_card_bot],
                   fill=_CARD, outline=accent_color, width=1)
    draw.rectangle([60, title_card_top, 66, title_card_bot], fill=accent_color)

    font_title = _load_font(36)
    font_body = _load_font(20)
    title_lines = _wrap_text(title, 40)
    ty = title_card_top + (title_card_bot - title_card_top) // 2 - 20
    for line in title_lines[:2]:
        draw.text((84, ty), line, fill=accent_color, font=font_title)
        ty += 42

    # 幻灯片编号标签
    num_text = f"{slide_index + 1:02d} / {total_slides:02d}"
    draw.text((_W - 110, title_card_top + 10), num_text, fill=_DIM, font=_load_font(18))

    # 内容区
    content_top = title_card_bot + 16
    items = [l.lstrip("-*•").strip() for l in body.splitlines() if l.strip()]

    if not items:
        return

    # 判断是否分两栏（条目 > 5 时分栏）
    if len(items) > 5:
        mid = len(items) // 2
        left_items = items[:mid]
        right_items = items[mid:]
        mid_x = _W // 2 - 10

        # 左栏
        draw.rectangle([60, content_top, mid_x - 5, _SAFE_BOTTOM - 10],
                        fill=_CARD, outline=_CARD_BORDER, width=1)
        draw.rectangle([60, content_top, 65, _SAFE_BOTTOM - 10], fill=accent_color)
        _draw_bullet_list(draw, left_items, 80, content_top + 14,
                          _SAFE_BOTTOM - 10, accent_color)

        # 右栏
        draw.rectangle([mid_x + 5, content_top, _W - 60, _SAFE_BOTTOM - 10],
                        fill=_CARD, outline=_CARD_BORDER, width=1)
        draw.rectangle([mid_x + 5, content_top, mid_x + 10, _SAFE_BOTTOM - 10],
                        fill=accent_color)
        _draw_bullet_list(draw, right_items, mid_x + 25, content_top + 14,
                          _SAFE_BOTTOM - 10, accent_color)
    else:
        # 单栏
        draw.rectangle([60, content_top, _W - 60, _SAFE_BOTTOM - 10],
                        fill=_CARD, outline=_CARD_BORDER, width=1)
        draw.rectangle([60, content_top, 65, _SAFE_BOTTOM - 10], fill=accent_color)
        _draw_bullet_list(draw, items, 80, content_top + 18,
                          _SAFE_BOTTOM - 10, accent_color, font_size=22)


def _layout_compare(img, title: str, body: str, slide_index: int, total_slides: int):
    """layout_2：对比型 - 左右两栏（检测 title 含 vs/对比/区别）。"""
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, _W, 4], fill=_PURPLE_L)

    # 标题
    font_title = _load_font(36)
    font_body = _load_font(20)
    draw.text((60, 30), title, fill=_WHITE, font=font_title)
    draw.line([(60, 82), (_W - 60, 82)], fill=_CARD_BORDER, width=1)

    # 中轴分隔
    mid_x = _W // 2
    draw.line([(mid_x, 100), (mid_x, _SAFE_BOTTOM - 20)], fill=_CARD_BORDER, width=2)
    draw.text((mid_x - 20, _SAFE_BOTTOM - 50), "VS", fill=_DIM, font=_load_font(22))

    # 拆分条目：前半 → 左，后半 → 右
    items = [l.lstrip("-*•").strip() for l in body.splitlines() if l.strip()]
    if not items:
        return
    mid = max(1, len(items) // 2)
    left_items = items[:mid]
    right_items = items[mid:]

    # 左栏（PINK 色）
    lx1, ly1, lx2, ly2 = 60, 98, mid_x - 20, _SAFE_BOTTOM - 20
    draw.rectangle([lx1, ly1, lx2, ly2], fill=(30, 8, 20), outline=_PINK, width=1)
    draw.rectangle([lx1, ly1, lx1 + 5, ly2], fill=_PINK)
    for i, item in enumerate(left_items):
        iy = ly1 + 16 + i * 46
        if iy + 30 > ly2:
            break
        draw.rectangle([lx1 + 20, iy + 8, lx1 + 28, iy + 16], fill=_PINK)
        draw.text((lx1 + 38, iy), item, fill=_WHITE, font=font_body)

    # 右栏（GREEN 色）
    rx1, ry1, rx2, ry2 = mid_x + 20, 98, _W - 60, _SAFE_BOTTOM - 20
    draw.rectangle([rx1, ry1, rx2, ry2], fill=(8, 30, 20), outline=_GREEN, width=1)
    draw.rectangle([rx1, ry1, rx1 + 5, ry2], fill=_GREEN)
    for i, item in enumerate(right_items):
        iy = ry1 + 16 + i * 46
        if iy + 30 > ry2:
            break
        draw.rectangle([rx1 + 20, iy + 8, rx1 + 28, iy + 16], fill=_GREEN)
        draw.text((rx1 + 38, iy), item, fill=_WHITE, font=font_body)


def _layout_ending(img, title: str, body: str, slide_index: int, total_slides: int):
    """layout_3：结尾型 - 标题 + bullet list + 进度条装饰。"""
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, _W, 4], fill=_CYAN)
    _draw_tag(draw, 60, 30, "SUMMARY", _GREEN, 18)

    # 大标题
    font_title = _load_font(46)
    font_body = _load_font(20)
    draw.text((60, 80), title, fill=_GOLD, font=font_title)
    draw.line([(60, 142), (_W - 60, 142)], fill=_CARD_BORDER, width=1)

    # 内容
    items = [l.lstrip("-*•").strip() for l in body.splitlines() if l.strip()]
    y = 158
    for item in items:
        if y + 30 > _SAFE_BOTTOM - 100:
            break
        draw.ellipse([64, y + 7, 74, y + 17], fill=_CYAN)
        for wrapped_line in _wrap_text(item, 52):
            if y + 30 > _SAFE_BOTTOM - 100:
                break
            draw.text((86, y), wrapped_line, fill=_WHITE, font=font_body)
            y += 30
        y += 6

    # 进度条
    pb_y = _SAFE_BOTTOM - 95
    progress_pct = (slide_index + 1) / max(total_slides, 1)
    draw.text((60, pb_y - 28), "课程进度", fill=_DIM, font=_load_font(18))
    draw.rectangle([60, pb_y, _W - 60, pb_y + 20], fill=(30, 20, 60), outline=_CARD_BORDER, width=1)
    progress_w = int((_W - 120) * progress_pct)
    if progress_w > 0:
        draw.rectangle([60, pb_y, 60 + progress_w, pb_y + 20], fill=_CYAN)
    nx = 60 + progress_w
    draw.ellipse([nx - 8, pb_y - 8, nx + 8, pb_y + 28], fill=_GOLD)
    draw.text((nx + 14, pb_y - 2), f"P{slide_index + 1}", fill=_GOLD, font=_load_font(16))


def _detect_layout(title: str, slide_index: int) -> str:
    """根据 slide 内容自动决策布局类型。"""
    title_lower = title.lower()
    if slide_index == 0:
        return "cover"
    if any(kw in title_lower for kw in ["vs", "对比", "区别", "versus", "比较"]):
        return "compare"
    if any(kw in title for kw in ["总结", "小结", "回顾", "结尾", "预告", "结束", "recap", "summary"]):
        return "ending"
    return "standard"


def _render_pillow(
    text_file, output_dir, width, height, fps, style, audio_file, secs_per_slide
) -> dict:
    """vlog-maker 同款 Pillow 渲染器（替换原有简陋 fallback）。"""
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
    except ImportError:
        raise RuntimeError("Pillow not installed: pip install Pillow")

    slides = _parse_slides(text_file)
    total_slides = len(slides)

    # 计算每个 slide 的帧数
    frames_per_slide = _calc_frames_per_slide(audio_file, total_slides, fps, secs_per_slide)

    # 获取音频时长（用于帧数校验）
    audio_duration = None
    if audio_file and os.path.exists(audio_file):
        audio_duration = _get_audio_duration(audio_file)

    # 强调色轮换（跳过封面和特殊布局）
    accent_palette = [_CYAN, _PURPLE_L, _GOLD, _GREEN, _ORANGE, _PINK]

    frame_index = 0
    for slide_idx, (title, body) in enumerate(slides):
        # 决策布局
        layout = _detect_layout(title, slide_idx)

        # 选择强调色（封面用 CYAN，对比用 PURPLE_L，结尾用 CYAN，其他轮换）
        if layout == "cover":
            accent = _CYAN
        elif layout == "compare":
            accent = _PURPLE_L
        elif layout == "ending":
            accent = _CYAN
        else:
            accent = accent_palette[slide_idx % len(accent_palette)]

        # 生成基底背景
        img = _make_base_purple(accent_color=accent)

        # 叠加布局
        if layout == "cover":
            _layout_cover(img, title, body, slide_idx, total_slides)
        elif layout == "compare":
            _layout_compare(img, title, body, slide_idx, total_slides)
        elif layout == "ending":
            _layout_ending(img, title, body, slide_idx, total_slides)
        else:
            _layout_standard(img, title, body, slide_idx, total_slides, accent_color=accent)

        # 如果 width/height 与标准 1280x720 不同，resize
        if width != _W or height != _H:
            from PIL import Image as PilImage
            img = img.resize((width, height), PilImage.LANCZOS)

        # 保存首帧
        first_fp = os.path.join(output_dir, f"frame_{frame_index:06d}.png")
        img.save(first_fp, "PNG")

        # 帧数校验：actual_frames >= ceil(duration * fps)
        actual_frames = frames_per_slide
        if audio_duration is not None:
            # 每个 slide 分配的最小帧数
            min_frames = math.ceil(audio_duration / total_slides * fps)
            actual_frames = max(frames_per_slide, min_frames)

        # 复制帧（用最后一帧补齐）
        for i in range(1, actual_frames):
            shutil.copy2(first_fp, os.path.join(output_dir, f"frame_{frame_index + i:06d}.png"))

        frame_index += actual_frames

    return {
        "frame_count": frame_index,
        "slide_count": total_slides,
        "output_dir": output_dir,
        "fps": fps,
        "renderer": "pillow",
    }


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
