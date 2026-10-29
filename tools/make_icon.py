"""Genera assets/isla_avisos.ico con el dibujo de la isla (multi-tamano).

Solo necesita Pillow. Se dibuja a 4x y se reduce para que quede suave.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    print("Falta Pillow. Instalalo con:  pip install pillow")
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "assets" / "isla_avisos.ico"

SIZES = [256, 128, 64, 48, 32, 24, 16]
SUPERSAMPLE = 4

ISLAND_FILL = (18, 18, 20, 255)
ISLAND_BORDER = (255, 255, 255, 48)
DOT_FILL = (255, 69, 58, 255)


def render(size: int) -> Image.Image:
    """Dibuja la isla a `size` px (con supersampling)."""
    n = size * SUPERSAMPLE
    image = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Pastilla (isla) redondeada.
    x0, y0, x1, y1 = 0.03 * n, 0.27 * n, 0.97 * n, 0.73 * n
    radius = 0.31 * n
    draw.rounded_rectangle(
        [x0, y0, x1, y1],
        radius=radius,
        fill=ISLAND_FILL,
        outline=ISLAND_BORDER,
        width=max(1, int(0.012 * n)),
    )

    # Punto de estado.
    dot_r = 0.072 * n
    cx, cy = 0.235 * n, 0.50 * n
    draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=DOT_FILL)

    # Dos barras que sugieren el texto del aviso.
    bar_x = 0.385 * n
    bar_h = 0.055 * n
    draw.rounded_rectangle(
        [bar_x, 0.415 * n, bar_x + 0.40 * n, 0.415 * n + bar_h],
        radius=bar_h / 2, fill=(255, 255, 255, 225),
    )
    draw.rounded_rectangle(
        [bar_x, 0.525 * n, bar_x + 0.27 * n, 0.525 * n + bar_h],
        radius=bar_h / 2, fill=(255, 255, 255, 140),
    )

    return image.resize((size, size), Image.LANCZOS)


def build(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    base = render(SIZES[0])
    try:
        base.save(output, format="ICO",
                  sizes=[(s, s) for s in SIZES],
                  append_images=[render(s) for s in SIZES[1:]])
    except TypeError:
        # Pillow antiguo: deja que redimensione el mismo dibujo.
        base.save(output, format="ICO", sizes=[(s, s) for s in SIZES])
    return output


def main() -> int:
    target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_OUTPUT
    build(target)
    print(f"Icono creado: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
