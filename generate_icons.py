"""
Generate PWA icons (no emoji font needed — the heart is drawn as a vector).
Run once:  python generate_icons.py     (requires: pip install Pillow)
"""
import math
import os
from PIL import Image, ImageDraw


def _heart_points(cx, cy, scale):
    """Parametric heart curve, returned as a list of (x, y) image points."""
    pts = []
    steps = 200
    for i in range(steps + 1):
        t = (i / steps) * 2 * math.pi
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * scale, cy - y * scale))
    return pts


def make_icon(size, path):
    # Supersample for smooth edges, then downscale.
    ss = 4
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded-square background with a soft vertical pink→rose gradient
    top = (255, 107, 157)      # #FF6B9D
    bot = (201, 24, 74)        # #C9184A
    grad = Image.new("RGBA", (1, S))
    for y in range(S):
        f = y / (S - 1)
        grad.putpixel((0, y), (
            int(top[0] + (bot[0] - top[0]) * f),
            int(top[1] + (bot[1] - top[1]) * f),
            int(top[2] + (bot[2] - top[2]) * f),
            255,
        ))
    grad = grad.resize((S, S))

    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=S // 5, fill=255)
    img.paste(grad, (0, 0), mask)

    # White heart, slightly above center
    heart = _heart_points(S / 2, S * 0.46, S / 42)
    # subtle drop shadow
    shadow = [(x + S * 0.012, y + S * 0.012) for (x, y) in heart]
    draw.polygon(shadow, fill=(120, 10, 40, 90))
    draw.polygon(heart, fill=(255, 255, 255, 255))

    img = img.resize((size, size), Image.LANCZOS)
    img.save(path, "PNG")
    print(f"Created {path} ({size}x{size})")


os.makedirs("app/static/icons", exist_ok=True)
make_icon(192, "app/static/icons/icon-192.png")
make_icon(512, "app/static/icons/icon-512.png")
make_icon(180, "app/static/icons/apple-touch-icon.png")  # iOS home screen
print("Done! Icons saved to app/static/icons/")
