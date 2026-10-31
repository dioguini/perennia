#!/usr/bin/env python3
"""Desenha os ícones da aplicação (PNG, 64×64, claros sobre transparente).

    python tools/make_icons.py

Desenha a 256 px e reduz para 64, o que dá arestas suaves. Precisa do Pillow
só para gerar; a aplicação usa os PNG já feitos, que vêm no projeto.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

S = 256
OUT = 64
INK = (236, 240, 246, 255)
CLEAR = (0, 0, 0, 0)
DEST = Path(__file__).resolve().parents[1] / "velo" / "assets" / "icons"


def canvas():
    img = Image.new("RGBA", (S, S), CLEAR)
    return img, ImageDraw.Draw(img)


def line(d, pts, w=22):
    d.line(pts, fill=INK, width=w, joint="curve")
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=INK)


def ring(d, cx, cy, r, w=20):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=INK, width=w)


def disc(d, cx, cy, r, fill=INK):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)


def arc(d, cx, cy, r, a0, a1, w=22):
    d.arc((cx - r, cy - r, cx + r, cy + r), a0, a1, fill=INK, width=w)


def arrow_head(d, x, y, angle_deg, size=46):
    a = math.radians(angle_deg)
    tip = (x + size * math.cos(a), y + size * math.sin(a))
    left = (x + size * 0.8 * math.cos(a + 2.4), y + size * 0.8 * math.sin(a + 2.4))
    right = (x + size * 0.8 * math.cos(a - 2.4), y + size * 0.8 * math.sin(a - 2.4))
    d.polygon([tip, left, right], fill=INK)


def save(img, name):
    DEST.mkdir(parents=True, exist_ok=True)
    img.resize((OUT, OUT), Image.LANCZOS).save(DEST / f"{name}.png")


# ------------------------------------------------------------------ métricas

def power():
    img, d = canvas()
    d.polygon([(150, 8), (52, 142), (118, 142), (92, 248), (204, 104), (138, 104),
               (176, 8)], fill=INK)
    save(img, "power")


def heart():
    img, d = canvas()
    disc(d, 84, 92, 58)
    disc(d, 172, 92, 58)
    d.polygon([(30, 118), (226, 118), (128, 232)], fill=INK)
    save(img, "heart")


def cadence():
    img, d = canvas()
    arc(d, 128, 128, 92, 40, 320, 24)
    a = math.radians(40)
    arrow_head(d, 128 + 92 * math.cos(a), 128 + 92 * math.sin(a), 40 + 100)
    disc(d, 128, 128, 22)
    line(d, [(128, 128), (180, 168)], 18)
    save(img, "cadence")


def speed():
    img, d = canvas()
    arc(d, 128, 160, 104, 180, 360, 24)
    for k in range(5):
        a = math.radians(180 + k * 45)
        x0, y0 = 128 + 72 * math.cos(a), 160 + 72 * math.sin(a)
        x1, y1 = 128 + 90 * math.cos(a), 160 + 90 * math.sin(a)
        d.line([(x0, y0), (x1, y1)], fill=INK, width=12)
    line(d, [(128, 160), (186, 96)], 20)
    disc(d, 128, 160, 22)
    save(img, "speed")


def distance():
    img, d = canvas()
    line(d, [(40, 128), (216, 128)], 20)
    arrow_head(d, 216, 128, 0, 50)
    arrow_head(d, 40, 128, 180, 50)
    for x in (88, 128, 168):
        d.line([(x, 100), (x, 156)], fill=INK, width=12)
    save(img, "distance")


def mountain():
    img, d = canvas()
    d.polygon([(8, 222), (96, 64), (138, 136), (170, 96), (248, 222)], fill=INK)
    d.polygon([(96, 64), (118, 104), (102, 96), (88, 110), (78, 96)], fill=CLEAR)
    save(img, "mountain")


def grade():
    img, d = canvas()
    d.polygon([(18, 222), (238, 222), (238, 62)], fill=INK)
    d.polygon([(110, 196), (210, 196), (210, 124)], fill=CLEAR)
    save(img, "grade")


def clock():
    img, d = canvas()
    ring(d, 128, 136, 100, 22)
    line(d, [(128, 136), (128, 76)], 20)
    line(d, [(128, 136), (172, 160)], 20)
    d.rectangle((108, 12, 148, 32), fill=INK)
    save(img, "clock")


def flag():
    img, d = canvas()
    line(d, [(50, 30), (50, 240)], 20)
    cell = 34
    for r in range(4):
        for c in range(5):
            if (r + c) % 2 == 0:
                x, y = 60 + c * cell, 34 + r * cell
                d.rectangle((x, y, x + cell, y + cell), fill=INK)
    d.rectangle((60, 34, 60 + 5 * cell, 34 + 4 * cell), outline=INK, width=8)
    save(img, "flag")


def balance():
    img, d = canvas()
    line(d, [(128, 40), (128, 214)], 18)
    line(d, [(44, 74), (212, 74)], 18)
    d.rectangle((84, 210, 172, 230), fill=INK)
    for cx in (60, 196):
        line(d, [(cx, 74), (cx - 34, 150)], 8)
        line(d, [(cx, 74), (cx + 34, 150)], 8)
        d.chord((cx - 44, 110, cx + 44, 190), 0, 180, fill=INK)
    save(img, "balance")


def wrench():
    img, d = canvas()
    line(d, [(64, 200), (160, 104)], 40)
    disc(d, 176, 82, 56)
    disc(d, 196, 62, 30, CLEAR)
    d.polygon([(196, 20), (240, 64), (214, 90), (170, 46)], fill=CLEAR)
    disc(d, 64, 200, 12, CLEAR)
    save(img, "wrench")


def zones():
    img, d = canvas()
    for i, h in enumerate((50, 85, 120, 160, 200)):
        x = 22 + i * 44
        d.rounded_rectangle((x, 232 - h, x + 32, 232), 6, fill=INK)
    save(img, "zones")


def flame():
    img, d = canvas()
    d.ellipse((58, 102, 198, 242), fill=INK)
    d.polygon([(62, 168), (120, 8), (150, 80), (176, 46), (194, 168)], fill=INK)
    d.ellipse((98, 160, 158, 232), fill=CLEAR)
    save(img, "flame")


def battery():
    img, d = canvas()
    d.rounded_rectangle((20, 70, 216, 186), 16, outline=INK, width=18)
    d.rectangle((216, 104, 240, 152), fill=INK)
    d.rectangle((46, 96, 150, 160), fill=INK)
    save(img, "battery")


def loops():
    img, d = canvas()
    arc(d, 128, 128, 88, 200, 340, 22)
    arc(d, 128, 128, 88, 20, 160, 22)
    a = math.radians(340)
    arrow_head(d, 128 + 88 * math.cos(a), 128 + 88 * math.sin(a), 70)
    a = math.radians(160)
    arrow_head(d, 128 + 88 * math.cos(a), 128 + 88 * math.sin(a), 250)
    save(img, "loops")


def target():
    img, d = canvas()
    ring(d, 128, 128, 104, 18)
    ring(d, 128, 128, 64, 18)
    disc(d, 128, 128, 24)
    save(img, "target")


def weight():
    img, d = canvas()
    line(d, [(40, 128), (216, 128)], 18)
    for x0 in (44, 186):
        d.rounded_rectangle((x0, 72, x0 + 26, 184), 6, fill=INK)
    for x0 in (14, 216):
        d.rounded_rectangle((x0, 96, x0 + 26, 160), 6, fill=INK)
    save(img, "weight")


def wave():
    img, d = canvas()
    pts = [(x, 128 - 62 * math.sin((x - 20) / 216 * 2 * math.pi)) for x in range(20, 237, 6)]
    line(d, pts, 22)
    save(img, "wave")


def gear():
    img, d = canvas()
    for k in range(8):
        a = k * math.pi / 4
        cx, cy = 128 + 92 * math.cos(a), 128 + 92 * math.sin(a)
        pts = []
        for dx, dy in ((-20, -22), (20, -22), (20, 22), (-20, 22)):
            pts.append((cx + dx * math.cos(a) - dy * math.sin(a),
                        cy + dx * math.sin(a) + dy * math.cos(a)))
        d.polygon(pts, fill=INK)
    disc(d, 128, 128, 86)
    disc(d, 128, 128, 36, CLEAR)
    save(img, "gear")


# -------------------------------------------------------------------- menus

def bike():
    img, d = canvas()
    ring(d, 62, 170, 52, 16)
    ring(d, 194, 170, 52, 16)
    line(d, [(62, 170), (108, 100), (176, 100), (194, 170)], 14)
    line(d, [(108, 100), (128, 170), (62, 170)], 14)
    line(d, [(128, 170), (176, 100)], 14)
    line(d, [(108, 100), (98, 68)], 14)
    line(d, [(80, 64), (118, 64)], 16)
    line(d, [(176, 100), (170, 66), (196, 60)], 14)
    save(img, "bike")


def runner():
    img, d = canvas()
    disc(d, 158, 42, 26)
    line(d, [(148, 76), (122, 148)], 22)
    line(d, [(144, 90), (186, 118), (206, 104)], 16)
    line(d, [(144, 90), (100, 104), (80, 132)], 16)
    line(d, [(122, 148), (168, 184), (154, 238)], 18)
    line(d, [(122, 148), (92, 198), (44, 204)], 18)
    save(img, "runner")


def rower():
    img, d = canvas()
    d.chord((8, 150, 248, 250), 0, 180, fill=INK)
    disc(d, 96, 62, 24)
    line(d, [(100, 90), (80, 160)], 22)
    line(d, [(96, 104), (150, 120)], 16)
    line(d, [(80, 160), (138, 150), (156, 180)], 16)
    line(d, [(120, 92), (240, 236)], 12)
    save(img, "rower")


def stats():
    img, d = canvas()
    line(d, [(28, 24), (28, 228), (236, 228)], 16)
    for i, h in enumerate((70, 120, 90, 170)):
        x = 56 + i * 46
        d.rounded_rectangle((x, 214 - h, x + 32, 214), 5, fill=INK)
    save(img, "stats")


def devices():
    img, d = canvas()
    disc(d, 128, 206, 20)
    for r in (60, 110, 160):
        arc(d, 128, 206, r, 225, 315, 20)
    save(img, "devices")


def trophy():
    img, d = canvas()
    d.polygon([(64, 30), (192, 30), (176, 120), (80, 120)], fill=INK)
    d.chord((64, 60, 192, 160), 0, 180, fill=INK)
    arc(d, 64, 76, 34, 90, 270, 14)
    arc(d, 192, 76, 34, 270, 450, 14)
    d.rectangle((116, 156, 140, 196), fill=INK)
    d.rounded_rectangle((70, 196, 186, 226), 6, fill=INK)
    save(img, "trophy")


def stopwatch():
    img, d = canvas()
    ring(d, 128, 146, 92, 20)
    d.rectangle((110, 20, 146, 44), fill=INK)
    line(d, [(128, 44), (128, 56)], 16)
    line(d, [(128, 146), (166, 104)], 18)
    save(img, "stopwatch")


def chevrons():
    img, d = canvas()
    for x in (40, 120):
        line(d, [(x, 46), (x + 70, 128), (x, 210)], 28)
    save(img, "chase")


def road():
    img, d = canvas()
    d.polygon([(96, 20), (160, 20), (240, 236), (16, 236)], fill=INK)
    for y0 in (40, 104, 168):
        d.rectangle((122, y0, 134, y0 + 36), fill=CLEAR)
    save(img, "road")


def back():
    img, d = canvas()
    line(d, [(220, 128), (60, 128)], 26)
    line(d, [(122, 58), (52, 128), (122, 198)], 26)
    save(img, "back")


def quit_icon():
    img, d = canvas()
    arc(d, 128, 136, 92, 300, 600, 22)
    line(d, [(128, 30), (128, 128)], 22)
    save(img, "quit")


def calendar():
    img, d = canvas()
    d.rounded_rectangle((24, 44, 232, 232), 18, outline=INK, width=18)
    d.rectangle((24, 44, 232, 92), fill=INK)
    for x in (72, 184):
        line(d, [(x, 20), (x, 60)], 18)
    for r in range(3):
        for c in range(4):
            x, y = 50 + c * 44, 112 + r * 38
            d.rectangle((x, y, x + 24, y + 22), fill=INK)
    save(img, "calendar")


def dumbbell():
    """Força: um haltere na horizontal."""
    img, d = canvas()
    line(d, [(80, 128), (176, 128)], 22)
    for x0, x1 in ((58, 86), (170, 198)):          # discos grandes, por dentro
        d.rounded_rectangle((x0, 60, x1, 196), 10, fill=INK)
    for x0, x1 in ((28, 52), (204, 228)):          # discos pequenos, por fora
        d.rounded_rectangle((x0, 86, x1, 170), 8, fill=INK)
    save(img, "dumbbell")


def pulse():
    """Forma / fitness: uma linha de ECG a subir."""
    img, d = canvas()
    line(d, [(18, 150), (78, 150), (102, 92), (132, 206), (160, 60), (186, 150),
             (238, 150)], 20)
    save(img, "pulse")


def export_icon():
    """Exportar: seta a sair de uma caixa."""
    img, d = canvas()
    d.rounded_rectangle((36, 100, 220, 232), 16, outline=INK, width=18)
    line(d, [(128, 170), (128, 40)], 22)
    arrow_head(d, 128, 52, -90, 56)
    save(img, "export")


def recover():
    """Recuperar: seta circular."""
    img, d = canvas()
    arc(d, 128, 136, 84, 200, 500, 22)
    arrow_head(d, 60, 92, -60, 54)
    save(img, "recover")


def swimmer():
    """Natação: cabeça e braço por cima de duas ondas."""
    img, d = canvas()
    disc(d, 70, 96, 24)
    line(d, [(96, 112), (150, 96), (196, 66)], 18)
    line(d, [(100, 118), (176, 130)], 18)
    for y in (172, 214):
        pts = [(x, y + 12 * math.sin(x / 22.0)) for x in range(18, 240, 6)]
        d.line(pts, fill=INK, width=14, joint="curve")
    save(img, "swimmer")


def box():
    """Inventário: uma caixa aberta."""
    img, d = canvas()
    d.polygon([(36, 104), (128, 132), (220, 104), (220, 206), (128, 236), (36, 206)],
              outline=INK, width=18)
    line(d, [(128, 132), (128, 236)], 16)
    line(d, [(36, 104), (78, 52), (172, 52), (220, 104)], 16)
    save(img, "box")


def checklist():
    """Lista de exercícios: três linhas com marcas."""
    img, d = canvas()
    for i, y in enumerate((60, 128, 196)):
        line(d, [(34, y), (52, y + 18), (80, y - 14)], 14)
        line(d, [(112, y), (226, y)], 18)
    save(img, "checklist")


def kettlebell():
    """Ginásio: um kettlebell."""
    img, d = canvas()
    arc(d, 128, 92, 54, 180, 360, 22)
    line(d, [(74, 92), (82, 128)], 22)
    line(d, [(182, 92), (174, 128)], 22)
    disc(d, 128, 172, 68)
    d.rectangle((84, 226, 172, 240), fill=INK)
    save(img, "kettlebell")


def power_button():
    """Ligar/desligar."""
    img, d = canvas()
    arc(d, 128, 140, 86, 300, 600, 22)
    line(d, [(128, 30), (128, 128)], 22)
    save(img, "power_button")


ALL = [power, heart, cadence, speed, distance, mountain, grade, clock, flag, balance,
       wrench, zones, flame, battery, loops, target, weight, wave, gear, bike, runner,
       rower, stats, devices, trophy, stopwatch, chevrons, road, back, quit_icon,
       calendar, dumbbell, pulse, export_icon, recover, swimmer, box, checklist,
       kettlebell, power_button]

if __name__ == "__main__":
    for fn in ALL:
        fn()
    print(f"{len(ALL)} ícones em {DEST}")
