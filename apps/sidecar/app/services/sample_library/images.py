"""Deterministic placeholder artwork for the sample library seeder.

Why this exists: a fresh Quillnight install's demo Books need cover art,
scene art, and character portraits so the Library/Canvas/Codex screens don't
look broken on first run. Those images must be **real PNG bytes on disk**
(via the existing `images_service.save_image(...)` write path), not
fabricated `Image` rows pointing at nonexistent files — no `<img>` consumer
in the frontend has an `onError` fallback, so a missing file renders a
broken-image glyph instead of gracefully degrading.

Determinism matters because the seeder must be re-runnable/reproducible: the
same `seed` string (typically a stable slug like a demo Book's UUID or a
demo character's name) always produces byte-identical PNG output. All
randomness is derived from a `hashlib.sha256` digest of the seed and fed
into a locally-seeded `random.Random` instance — never Python's randomized
per-process `hash()` and never the shared, unseeded `random` module state.

Visual style is a soft, abstract two-tone gradient (vertical or diagonal,
seed-derived hue) plus a handful of translucent circles/arcs for texture,
with optional centered label text. It's meant to sit comfortably next to
Quillnight's Day (cream `#FBF5E9`, warm amber/ink-blue) and Night (soft gray
`#1E1E24`, firefly-gold `#FFC94D` + cyan) themes without imitating either
exactly, and without attempting real illustration.
"""

from __future__ import annotations

import colorsys
import hashlib
import io
import math
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

RGB = tuple[int, int, int]


def _digest(seed: str) -> bytes:
    """Stable, process-independent hash of ``seed`` — the sole source of randomness."""
    return hashlib.sha256(seed.encode("utf-8")).digest()


def _hls_to_rgb(h: float, l: float, s: float) -> RGB:  # noqa: E741 - matches colorsys param name
    r, g, b = colorsys.hls_to_rgb(h % 1.0, min(max(l, 0.0), 1.0), min(max(s, 0.0), 1.0))
    return (round(r * 255), round(g * 255), round(b * 255))


def _gradient_colors(digest: bytes) -> tuple[RGB, RGB, float]:
    """Derive a two-tone (light, dark) color pair plus their average lightness."""
    hue = digest[1] / 255.0
    hue_shift = (digest[4] / 255.0) * 0.15
    light = _hls_to_rgb(hue, 0.78 + (digest[3] / 255.0) * 0.12, 0.35 + (digest[2] / 255.0) * 0.25)
    dark = _hls_to_rgb(
        hue + hue_shift, 0.25 + (digest[6] / 255.0) * 0.22, 0.45 + (digest[5] / 255.0) * 0.30
    )
    avg_lightness = (0.78 + 0.25) / 2.0
    return light, dark, avg_lightness


def _gradient_background(width: int, height: int, digest: bytes) -> Image.Image:
    """A smooth vertical/diagonal two-tone gradient, sized to (width, height)."""
    light, dark, _ = _gradient_colors(digest)

    # Angle is one of 0/45/90/135 degrees, chosen deterministically from the seed —
    # covers both the "vertical" and "diagonal" cases the spec asks for.
    angle = (digest[0] % 4) * 45

    diag = int(math.hypot(width, height)) + 2
    base = Image.linear_gradient("L").resize((diag, diag))
    if angle:
        base = base.rotate(angle, resample=Image.BICUBIC, expand=True)

    bw, bh = base.size
    left = (bw - width) // 2
    top = (bh - height) // 2
    cropped = base.crop((left, top, left + width, top + height))

    return ImageOps.colorize(cropped, black=dark, white=light).convert("RGBA")


def _shape_layer(width: int, height: int, digest: bytes) -> Image.Image:
    """A handful of soft, translucent circles/arcs for texture."""
    seed_int = int.from_bytes(digest[:8], "big")
    # Not cryptographic — this is deterministic decorative shape placement, seeded
    # locally from a sha256 digest so the same input seed always draws the same shapes.
    rng = random.Random(seed_int)  # noqa: S311

    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    short_side = min(width, height)
    num_shapes = 3 + digest[7] % 3  # 3..5
    for _ in range(num_shapes):
        radius = rng.randint(max(short_side // 10, 8), max(short_side // 3, 16))
        cx = rng.randint(0, width)
        cy = rng.randint(0, height)
        alpha = rng.randint(24, 70)
        tone = 255 if rng.random() < 0.75 else 0
        color = (tone, tone, tone, alpha)
        bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
        if rng.random() < 0.7:
            draw.ellipse(bbox, fill=color)
        else:
            start = rng.randint(0, 360)
            end = start + rng.randint(60, 180)
            draw.arc(bbox, start=start, end=end, fill=color, width=max(4, radius // 10))

    blur_radius = max(2.0, short_side * 0.015)
    return layer.filter(ImageFilter.GaussianBlur(radius=blur_radius))


def _label_text(label: str) -> str:
    """The label as-is if short, otherwise its first-two-word initials."""
    label = label.strip()
    if len(label) <= 3:
        return label.upper()
    words = label.split()
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return label[:2].upper()


def _draw_label(
    image: Image.Image, label: str, width: int, height: int, avg_lightness: float
) -> None:
    """Best-effort centered label text. A font failure must never raise."""
    try:
        text = _label_text(label)
        if not text:
            return

        font_size = max(24, min(width, height) // 6)
        try:
            font = ImageFont.load_default(size=font_size)
        except TypeError:
            # Older Pillow: load_default() takes no size argument.
            font = ImageFont.load_default()

        draw = ImageDraw.Draw(image)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        position = ((width - text_w) / 2 - bbox[0], (height - text_h) / 2 - bbox[1])

        fill = (30, 26, 20, 160) if avg_lightness > 0.5 else (245, 240, 230, 160)
        draw.text(position, text, font=font, fill=fill)
    except Exception:
        # Decorative only — never let a font/text issue break image generation.
        return


def generate_png(
    seed: str,
    *,
    width: int = 1024,
    height: int = 640,
    label: str | None = None,
) -> bytes:
    """Generate a deterministic abstract PNG for ``seed``, encoded as bytes.

    Same ``seed`` (and same ``width``/``height``/``label``) always produces
    byte-identical output. Never writes to disk — callers pass the returned
    bytes straight to ``images_service.save_image(...)``.
    """
    digest = _digest(seed)

    background = _gradient_background(width, height, digest)
    shapes = _shape_layer(width, height, digest)
    combined = Image.alpha_composite(background, shapes)

    if label:
        _, _, avg_lightness = _gradient_colors(digest)
        _draw_label(combined, label, width, height, avg_lightness)

    buffer = io.BytesIO()
    combined.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def generate_cover(seed: str, label: str | None = None) -> bytes:
    """Portrait-ish placeholder for a Book cover."""
    return generate_png(seed, width=800, height=1200, label=label)


def generate_scene_art(seed: str, label: str | None = None) -> bytes:
    """Landscape placeholder for canvas/scene reference art."""
    return generate_png(seed, width=1024, height=640, label=label)


def generate_portrait(seed: str, label: str | None = None) -> bytes:
    """Square placeholder for a Codex character portrait."""
    return generate_png(seed, width=512, height=512, label=label)
