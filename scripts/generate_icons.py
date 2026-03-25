#!/usr/bin/env python3
"""
Génère toutes les icônes pour l'application MCP IA :
- PNG 72/96/128/144/152/192/384/512 (PWA / Android)
- PNG 16/32/48/256 (Windows ICO)
- PNG 16/32/128/256/512/1024 (macOS ICNS)
- .ico (Windows)
- .icns (macOS)
"""

import os
import struct
import zlib
from pathlib import Path

# ── Dessin SVG inline converti en bitmap via Pillow ──────────────────────────

def make_icon_pil(size: int) -> "Image":
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fond dégradé simulé par un rectangle arrondi violet
    r = size // 6
    bg_color = (108, 99, 255, 255)   # #6c63ff
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=bg_color)

    # Cercle central blanc semi-transparent
    cx, cy = size // 2, size // 2
    cr = int(size * 0.28)
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=(255, 255, 255, 220))

    # Lettre "M" noire au centre
    try:
        font_size = max(8, int(size * 0.40))
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    text = "M"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - tw // 2 - bbox[0], cy - th // 2 - bbox[1]), text, font=font, fill=(108, 99, 255, 255))

    return img


# ── Chemins de sortie ─────────────────────────────────────────────────────────

BASE = Path(__file__).parent.parent
PWA_DIR  = BASE / "saas" / "frontend" / "icons"
DESK_DIR = BASE / "desktop" / "assets"

PWA_DIR.mkdir(parents=True, exist_ok=True)
DESK_DIR.mkdir(parents=True, exist_ok=True)

print("Génération des icônes PNG…")

# PWA / Android
pwa_sizes = [72, 96, 128, 144, 152, 192, 384, 512]
for s in pwa_sizes:
    img = make_icon_pil(s)
    out = PWA_DIR / f"icon-{s}x{s}.png"
    img.save(str(out), "PNG")
    print(f"  ✓ {out.relative_to(BASE)}")

# Desktop (various sizes needed for .ico and .icns source)
desk_sizes = [16, 32, 48, 128, 256, 512, 1024]
desk_pngs = {}
for s in desk_sizes:
    img = make_icon_pil(s)
    out = DESK_DIR / f"icon-{s}.png"
    img.save(str(out), "PNG")
    desk_pngs[s] = out
    print(f"  ✓ {out.relative_to(BASE)}")

# Main 512 icon used by electron-builder
main512 = DESK_DIR / "icon.png"
make_icon_pil(512).save(str(main512), "PNG")
print(f"  ✓ {main512.relative_to(BASE)}")


# ── Windows ICO ──────────────────────────────────────────────────────────────
print("\nGénération icon.ico (Windows)…")

from PIL import Image

ico_sizes = [16, 32, 48, 256]
ico_images = [make_icon_pil(s) for s in ico_sizes]
ico_path = DESK_DIR / "icon.ico"
ico_images[0].save(
    str(ico_path),
    format="ICO",
    sizes=[(s, s) for s in ico_sizes],
    append_images=ico_images[1:],
)
print(f"  ✓ {ico_path.relative_to(BASE)}")


# ── macOS ICNS ───────────────────────────────────────────────────────────────
# ICNS format: 4-byte type + 4-byte length + data
print("\nGénération icon.icns (macOS)…")

ICNS_TYPES = {
    16:   b"icp4",
    32:   b"icp5",
    64:   b"icp6",
    128:  b"ic07",
    256:  b"ic08",
    512:  b"ic09",
    1024: b"ic10",
}

import io

def png_bytes(size: int) -> bytes:
    img = make_icon_pil(size)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()

icns_sizes = [16, 32, 64, 128, 256, 512, 1024]
chunks = []
for s in icns_sizes:
    data = png_bytes(s)
    type_tag = ICNS_TYPES[s]
    length = 8 + len(data)  # type(4) + length(4) + data
    chunks.append(type_tag + struct.pack(">I", length) + data)

body = b"".join(chunks)
header = b"icns" + struct.pack(">I", 8 + len(body))

icns_path = DESK_DIR / "icon.icns"
icns_path.write_bytes(header + body)
print(f"  ✓ {icns_path.relative_to(BASE)}")


print("\n✅ Toutes les icônes ont été générées avec succès.")
