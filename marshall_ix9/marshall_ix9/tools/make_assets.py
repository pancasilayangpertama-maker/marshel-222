"""Draws the Marshall IX9 logo and writes assets/logo_*.png and assets/icon.ico.

The GitHub build runs this script by itself, so normally you never run it yourself.
To change the logo: edit this file, then   pip install "pillow<13" numpy   and   python tools/make_assets.py

The logo is a knob: brass ring, black face, 12 ticks, the pointer set to 9 (IX9), and the last tick
in red because "these go to eleven".
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "assets")
S = 2048  # working canvas; everything is drawn big and scaled down for smooth edges
C = S // 2

BRASS_HI, BRASS, BRASS_LO = (246, 221, 147), (214, 169, 74), (123, 98, 48)
CREAM, RED, LED_OFF = (239, 230, 210), (255, 68, 51), (62, 53, 42)

FONT_CANDIDATES = [
    "C:/Windows/Fonts/segoeuiz.ttf",  # Segoe UI Bold Italic
    "C:/Windows/Fonts/arialbi.ttf",   # Arial Bold Italic
    "/usr/share/fonts/truetype/google-fonts/Poppins-BoldItalic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
]


def gradient(size, stops, diagonal=True):
    """RGBA image with a linear gradient through `stops` = [(position 0..1, (r, g, b)), ...]."""
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    t = ((x + y) / (2 * size)) if diagonal else (y / size)
    out = np.zeros((size, size, 4), dtype=np.float32)
    out[..., 3] = 255
    positions = [p for p, _c in stops]
    for channel in range(3):
        out[..., channel] = np.interp(t, positions, [c[channel] for _p, c in stops])
    return Image.fromarray(out.astype(np.uint8))  # (S, S, 4) uint8 is read as RGBA


def disc_mask(radius, cx=C, cy=C):
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=255)
    return mask


def polar(angle_deg, radius):
    a = math.radians(angle_deg)  # clockwise from 12 o'clock
    return C + math.sin(a) * radius, C - math.cos(a) * radius


def thick_line(draw, p0, p1, width, fill):
    draw.line([p0, p1], fill=fill, width=width)
    r = width / 2
    for x, y in (p0, p1):
        draw.ellipse((x - r, y - r, x + r, y + r), fill=fill)


def load_font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    try:
        return ImageFont.load_default(size)
    except TypeError:  # old Pillow
        return ImageFont.load_default()


def draw_logo():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # soft brass glow behind the knob
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((C - 960, C - 960, C + 960, C + 960), fill=BRASS + (150,))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(70)))

    # brass ring (knob body)
    ring = gradient(S, [(0.0, BRASS_HI), (0.45, BRASS), (1.0, BRASS_LO)])
    ring.putalpha(disc_mask(940))
    img.alpha_composite(ring)

    # dark face with a thin brass rim
    face = gradient(S, [(0.0, (30, 26, 21)), (1.0, (10, 9, 8))])
    face.putalpha(disc_mask(790))
    img.alpha_composite(face)
    draw = ImageDraw.Draw(img)
    draw.ellipse((C - 790, C - 790, C + 790, C + 790), outline=BRASS_LO, width=12)
    draw.ellipse((C - 420, C - 420, C + 420, C + 420), outline=(44, 38, 31), width=10)

    # twelve ticks, 0 .. 11, lit up to 9
    level = 9
    for i in range(12):
        angle = -135 + 270 * i / 11
        color = RED if i == 11 else (BRASS if i <= level else LED_OFF)
        thick_line(draw, polar(angle, 615), polar(angle, 735), 38, color)

    # pointer on 9 and centre cap
    angle = -135 + 270 * level / 11
    thick_line(draw, polar(angle, 70), polar(angle, 540), 64, RED)
    thick_line(draw, polar(angle, 110), polar(angle, 500), 18, (255, 150, 130))
    draw.ellipse((C - 92, C - 92, C + 92, C + 92), fill=BRASS, outline=BRASS_LO, width=10)
    draw.ellipse((C - 40, C - 40, C + 40, C + 40), fill=BRASS_HI)

    # "IX9" in the free gap at the bottom of the dial
    font = load_font(300)
    text = "IX9"
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    tx, ty = C - (right + left) / 2, C + 330 - (bottom + top) / 2
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((tx + 8, ty + 12), text, font=font, fill=(0, 0, 0, 200))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)))
    ImageDraw.Draw(img).text((tx, ty), text, font=font, fill=CREAM)
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    master = draw_logo()
    sizes = (16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512)
    for size in sizes:
        if size >= 48:
            master.resize((size, size), Image.Resampling.LANCZOS).save(os.path.join(OUT, f"logo_{size}.png"), optimize=True)
    master.resize((1024, 1024), Image.Resampling.LANCZOS).save(os.path.join(OUT, "logo.png"), optimize=True)
    icon_base = master.resize((256, 256), Image.Resampling.LANCZOS)
    icon_base.save(os.path.join(OUT, "icon.ico"), sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    print("wrote", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    sys.exit(main())
