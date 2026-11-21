#!/usr/bin/env python3
"""Desenha o ícone da aplicação (o do executável do Windows e o da janela).

    python tools/make_app_icon.py

Cria perennia/assets/app_icon.png (256×256) e packaging/perennia.ico (16 a 256 px). Precisa do
Pillow só para gerar; o projeto traz os ficheiros já feitos.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
S = 1024                       # desenha grande e reduz: arestas suaves
BG_TOP, BG_BOTTOM = (22, 33, 52), (12, 18, 30)
ACCENT = (64, 196, 160)        # o verde da Perennia (perene)
INK = (236, 240, 246)


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # fundo: quadrado arredondado com um degradê vertical
    bg = Image.new("RGBA", (S, S))
    px = bg.load()
    for y in range(S):
        t = y / (S - 1)
        c = tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)) + (255,)
        for x in range(S):
            px[x, y] = c
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.22), fill=255)
    img.paste(bg, (0, 0), mask)
    d = ImageDraw.Draw(img)
    # a roda: um anel
    cx = cy = S // 2
    r_out, r_in = int(S * 0.36), int(S * 0.29)
    d.ellipse((cx - r_out, cy - r_out, cx + r_out, cy + r_out), fill=INK)
    d.ellipse((cx - r_in, cy - r_in, cx + r_in, cy + r_in), fill=(16, 25, 41, 255))
    # a subida: uma linha a subir, a atravessar a roda (a perene a crescer)
    pts = [(int(S * 0.24), int(S * 0.66)), (int(S * 0.42), int(S * 0.52)),
           (int(S * 0.53), int(S * 0.60)), (int(S * 0.76), int(S * 0.32))]
    d.line(pts, fill=ACCENT, width=int(S * 0.075), joint="curve")
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x - S * 0.0375, y - S * 0.0375, x + S * 0.0375, y + S * 0.0375), fill=ACCENT)
    return img


def main() -> None:
    img = draw()
    png = ROOT / "perennia" / "assets" / "app_icon.png"
    img.resize((256, 256), Image.LANCZOS).save(png)
    ico = ROOT / "packaging" / "perennia.ico"
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.resize((256, 256), Image.LANCZOS).save(ico, format="ICO", sizes=sizes)
    print(png)
    print(ico)


if __name__ == "__main__":
    main()
