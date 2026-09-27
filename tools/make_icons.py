"""Render PWA icons (192/512) with the brand mark, verify glyph support first.

Dev utility: needs Pillow and the FreeSerif font (Debian: fonts-freefont-ttf).
Writes into ../static/img/.
"""
from PIL import Image, ImageDraw, ImageFont
import hashlib, os

FONT = os.environ.get("ICON_FONT", "/usr/share/fonts/truetype/freefont/FreeSerif.ttf")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "img")

def mask_hash(font, ch):
    m = font.getmask(ch)
    return hashlib.md5(m.tobytes() if hasattr(m, "tobytes") else bytes(m)).hexdigest()

font = ImageFont.truetype(FONT, 64)
tofu = mask_hash(font, "\uFFFF")
mark = mask_hash(font, "से")
print("glyph ok?" , mark != tofu)

def make(size, path):
    im = Image.new("RGB", (size, size), "#1f6b47")
    d = ImageDraw.Draw(im)
    # subtle inner ring for depth (still flat, no gradients)
    r = int(size * 0.44)
    cx = cy = size // 2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline="#2a7d57", width=max(2, size // 48))
    fs = int(size * 0.52)
    f = ImageFont.truetype(FONT, fs)
    bbox = d.textbbox((0, 0), "से", font=f)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text((cx - w / 2 - bbox[0], cy - h / 2 - bbox[1]), "से", font=f, fill="#ffffff")
    im.save(path)
    print("saved", path, im.size)

make(512, os.path.join(OUT, "icon-512.png"))
make(192, os.path.join(OUT, "icon-192.png"))
