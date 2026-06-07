"""
Run once to generate PWA icons:  python generate_icons.py
Requires: pip install Pillow
"""
from PIL import Image, ImageDraw, ImageFont
import os

def make_icon(size, path):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Pink rounded-square background
    r = size // 6
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r,
                            fill="#FF6B9D")

    # Draw two overlapping hearts using text emoji
    font_size = int(size * 0.52)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    text = "💕"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2, (size - th) / 2 - size * 0.04),
              text, font=font, embedded_color=True)

    img.save(path, "PNG")
    print(f"Created {path} ({size}x{size})")

os.makedirs("app/static/icons", exist_ok=True)
make_icon(192, "app/static/icons/icon-192.png")
make_icon(512, "app/static/icons/icon-512.png")
print("Done! Icons saved to app/static/icons/")
