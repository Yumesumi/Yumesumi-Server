#!/usr/bin/env python3
"""
梦澄服 · 静态资源管线

从项目根目录的「素材/」生成站点实际发布的资源：
  · assets/ 下的 WebP 世界图、品牌 Logo、favicon 与分享封面
  · index.html 中的星空粒子（确定性生成，占位标记之间整体替换）
  · assets/fonts/misans-subset.woff2（按页面实际用字做 MiSans 子集）

依赖：Pillow、fonttools、brotli
用法：python tools/build-assets.py
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps
from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "素材"
ASSETS = ROOT / "assets"
FONT_SOURCE = ROOT.parent / "Yumesumi-Center" / "MiSans" / "可变字体" / "MiSansVF.ttf"

STAR_START = "<!-- STARS_START -->"
STAR_END = "<!-- STARS_END -->"

# 素材 → 输出名。每张输出 1600 与 900 两档（Hero / 结尾额外保留 2560）。
IMAGES = {
    "images.png": "hero-night",
    "images_1.png": "world-underwater",
    "images_2.png": "world-mansion",
    "images_3.png": "world-sunrise",
    "images_5.png": "world-cloud-towers",
    "images_6.png": "world-night-flight",
    "images_7.png": "world-lava-mountain",
}


def ensure_dirs() -> None:
    (ASSETS / "brand").mkdir(parents=True, exist_ok=True)
    (ASSETS / "fonts").mkdir(parents=True, exist_ok=True)


def export_webp(source: Path, name: str) -> None:
    im = Image.open(source).convert("RGB")
    widths = [1600, 900]
    if name == "hero-night":
        widths = [2560, 1600]
    if name == "world-mansion":
        # 除画廊外还用作结尾整屏背景，额外保留一档 2560
        widths = [2560, 1600, 900]
    for width in widths:
        if width >= im.width:
            resized = im
        else:
            height = round(im.height * width / im.width)
            resized = im.resize((width, height), Image.Resampling.LANCZOS)
        out = ASSETS / f"{name}-{width}.webp"
        resized.save(out, "WEBP", quality=80, method=6)
        print(f"image {out.relative_to(ROOT)} {out.stat().st_size // 1024} KB")


def build_brand() -> None:
    logo = Image.open(SRC / "logo.png").convert("RGBA")
    bbox = logo.getchannel("A").getbbox()
    logo = logo.crop(bbox)
    logo = ImageOps.expand(logo, border=10, fill=(0, 0, 0, 0))
    logo.save(ASSETS / "brand" / "logo.png")
    print(f"brand logo.png {logo.size}")

    # 单字「梦」：只取上半部分，避开底部的 YUMESUMI 字标
    top = Image.open(SRC / "logo.png").convert("RGBA").crop((0, 0, 320, 225))
    top = top.crop(top.getchannel("A").getbbox())
    side = max(top.size)
    mark = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    mark.paste(top, ((side - top.width) // 2, (side - top.height) // 2), top)
    mark.save(ASSETS / "brand" / "mark.png")
    print(f"brand mark.png {mark.size}")

    for size, name in ((64, "favicon-64.png"), (180, "apple-touch-icon.png")):
        icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        padded = size - round(size * 0.16) * 2
        glyph = mark.copy()
        glyph.thumbnail((padded, padded), Image.Resampling.LANCZOS)
        icon.alpha_composite(glyph, ((size - glyph.width) // 2, (size - glyph.height) // 2))
        if name.startswith("apple"):
            bg = Image.new("RGBA", (size, size), (13, 11, 26, 255))
            icon = Image.alpha_composite(bg, icon)
        icon.save(ASSETS / "brand" / name)
        print(f"brand {name} {size}px")


def build_og_cover() -> None:
    im = Image.open(SRC / "images.png").convert("RGB")
    target_ratio = 1200 / 630
    crop_h = round(im.width / target_ratio)
    top = round((im.height - crop_h) * 0.42)
    cover = im.crop((0, top, im.width, top + crop_h)).resize(
        (1200, 630), Image.Resampling.LANCZOS
    )

    shade = Image.new("RGBA", cover.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shade)
    for y in range(630):
        alpha = round(150 - 80 * (y / 630))
        draw.line((0, y, 1200, y), fill=(5, 5, 12, alpha))
    cover = Image.alpha_composite(cover.convert("RGBA"), shade)

    glow = Image.new("RGBA", cover.size, (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse((260, 60, 940, 560), fill=(109, 79, 196, 40))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    cover = Image.alpha_composite(cover, glow)

    logo = Image.open(ASSETS / "brand" / "logo.png")
    logo.thumbnail((520, 520), Image.Resampling.LANCZOS)
    cover.alpha_composite(logo, ((1200 - logo.width) // 2, (630 - logo.height) // 2))

    out = ASSETS / "og-cover.jpg"
    cover.convert("RGB").save(out, "JPEG", quality=86, optimize=True)
    print(f"og-cover.jpg {out.stat().st_size // 1024} KB")


def build_stars() -> None:
    html_path = ROOT / "index.html"
    html = html_path.read_text(encoding="utf-8")

    rng = random.Random(20261029)
    eases = ["ease-in-out", "ease-out", "ease-in", "cubic-bezier(0.4, 0, 0.6, 1)"]
    spans: list[str] = []

    def particle(kind: str, size: tuple[float, float], peak: tuple[float, float]) -> str:
        x = rng.random() * 100
        y = rng.random() * 100
        s = rng.uniform(*size)
        duration = rng.uniform(6, 18) if kind == "is-star" else rng.uniform(10, 24)
        delay = -rng.uniform(0, 20)
        p = rng.uniform(*peak) * (1 - (s - size[0]) / (size[1] - size[0]) * 0.3)
        floor = p * rng.uniform(0.32, 0.52)
        ease = rng.choice(eases)
        dx = (rng.random() * 2 - 1) * rng.uniform(1.5, 7)
        dy = (rng.random() * 2 - 1) * rng.uniform(1.5, 7)
        ddur = rng.uniform(32, 80)
        ddelay = -rng.uniform(0, 80)
        style = (
            f"--x:{x:.2f}%;--y:{y:.2f}%;--size:{s:.2f}px;--dur:{duration:.2f}s;"
            f"--delay:{delay:.2f}s;--peak:{p:.3f};--floor:{floor:.3f};--ease:{ease};"
            f"--dx:{dx:.2f}vmin;--dy:{dy:.2f}vmin;--ddur:{ddur:.2f}s;--ddelay:{ddelay:.2f}s"
        )
        return f'        <span class="star {kind}" style="{style}"></span>'

    for _ in range(26):
        spans.append(particle("is-star", (7.0, 21.0), (0.32, 0.56)))
    for _ in range(28):
        spans.append(particle("is-dust", (1.2, 3.6), (0.16, 0.38)))

    block = "\n".join(spans)
    if STAR_START not in html or STAR_END not in html:
        raise SystemExit("index.html 缺少星空占位标记")
    prefix, rest = html.split(STAR_START, 1)
    _, suffix = rest.split(STAR_END, 1)
    html = f"{prefix}{STAR_START}\n{block}\n        {STAR_END}{suffix}"
    html_path.write_text(html, encoding="utf-8")
    print(f"stars {len(spans)}")


def build_font() -> None:
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    charset = sorted(set(html) | set("0123456789，。、；：？！“”‘’（）《》—…·～↗↓©"))
    charset = [c for c in charset if not c.isspace()]

    font = TTFont(FONT_SOURCE)
    options = Options()
    options.flavor = "woff2"
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.notdef_outline = True
    options.drop_tables += ["DSIG"]

    subsetter = Subsetter(options=options)
    subsetter.populate(text="".join(charset))
    subsetter.subset(font)

    out = ASSETS / "fonts" / "misans-subset.woff2"
    font.save(out)
    font.close()
    print(f"font misans-subset.woff2 {len(charset)} glyphs, {out.stat().st_size // 1024} KB")


def main() -> None:
    ensure_dirs()
    for source, name in IMAGES.items():
        export_webp(SRC / source, name)
    build_brand()
    build_og_cover()
    build_stars()
    build_font()


if __name__ == "__main__":
    main()
