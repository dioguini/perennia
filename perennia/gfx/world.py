"""Mundo 3D em primeira pessoa (req. 2, 3, 18).

A geometria da estrada vem do GPX: traçado, curvas e declives reais. O
cenário em volta é gerado por ruído determinístico semeado pela rota, por
isso é sempre igual na mesma estrada e não precisa de rede.

A malha é construída em troços de 250 m antes de a sessão começar (req. 3) e
só os troços dentro da distância de desenho são enviados ao GPU. É isso que
permite correr num Raspberry Pi no preset baixo.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from pyglet.gl import (GL_BLEND, GL_CULL_FACE, GL_DEPTH_TEST, GL_LEQUAL,
                       GL_ONE_MINUS_SRC_ALPHA, GL_SRC_ALPHA, GL_TRIANGLES,
                       glBlendFunc, glClearColor, glDepthFunc, glDisable,
                       glEnable)
from pyglet.graphics import Batch, Group
from pyglet.graphics.shader import Shader, ShaderProgram
from pyglet.math import Mat4, Vec3

CHUNK_LENGTH_M = 250.0
ROAD_HALF_WIDTH = 3.0
SHOULDER = 1.2
EYE_HEIGHT = 1.35

PRESETS = {
    "low":    {"draw_m": 600.0,  "terrain_bands": 2, "prop_every_m": 55.0, "skirt": 90.0},
    "medium": {"draw_m": 1500.0, "terrain_bands": 3, "prop_every_m": 32.0, "skirt": 180.0},
    "high":   {"draw_m": 3000.0, "terrain_bands": 4, "prop_every_m": 20.0, "skirt": 320.0},
}

_VERTEX_SRC = """#version 150 core
in vec3 position;
in vec3 normal;
in vec4 color;
out vec4 frag_color;
out float fog_depth;
uniform mat4 projection;
uniform mat4 view;
uniform vec3 sun;
void main() {
    vec4 eye = view * vec4(position, 1.0);
    gl_Position = projection * eye;
    float lambert = max(dot(normalize(normal), normalize(sun)), 0.0);
    float shade = 0.45 + 0.55 * lambert;
    frag_color = vec4(color.rgb * shade, color.a);
    fog_depth = -eye.z;
}
"""

_FRAGMENT_SRC = """#version 150 core
in vec4 frag_color;
in float fog_depth;
out vec4 final_color;
uniform vec3 fog_color;
uniform float fog_start;
uniform float fog_end;
void main() {
    float t = clamp((fog_depth - fog_start) / max(fog_end - fog_start, 1.0), 0.0, 1.0);
    final_color = vec4(mix(frag_color.rgb, fog_color, t), frag_color.a);
}
"""


def _hash01(*values: float) -> float:
    """Ruído determinístico em [0, 1). Semeado pelos argumentos."""
    h = 2166136261
    for v in values:
        bits = int(v * 1000.0) & 0xFFFFFFFF
        h = ((h ^ bits) * 16777619) & 0xFFFFFFFF
        h ^= h >> 13
    return (h & 0xFFFFFF) / float(0x1000000)


def _terrain_height(x: float, y: float, base: float, amplitude: float) -> float:
    """Relevo suave em volta da estrada, interpolando ruído numa grelha de 40 m."""
    cell = 40.0
    gx, gy = x / cell, y / cell
    ix, iy = math.floor(gx), math.floor(gy)
    fx, fy = gx - ix, gy - iy
    # suavização cúbica para não haver arestas entre células
    sx = fx * fx * (3.0 - 2.0 * fx)
    sy = fy * fy * (3.0 - 2.0 * fy)
    h00 = _hash01(ix, iy)
    h10 = _hash01(ix + 1, iy)
    h01 = _hash01(ix, iy + 1)
    h11 = _hash01(ix + 1, iy + 1)
    top = h00 + (h10 - h00) * sx
    bottom = h01 + (h11 - h01) * sx
    return base + (top + (bottom - top) * sy - 0.5) * amplitude


@dataclass
class Chunk:
    index: int
    start_m: float
    end_m: float
    group: Group
    vertex_lists: list = field(default_factory=list)


class World:
    """Constrói e desenha a estrada. Um `World` por sessão."""

    def __init__(self, points: list, preset: str = "low", seed: str = ""):
        self.points = points
        self.preset = preset if preset in PRESETS else "low"
        self.cfg = PRESETS[self.preset]
        self.seed = seed
        self.total_m = points[-1].dist_m if points else 0.0
        self.step_m = (points[1].dist_m - points[0].dist_m) if len(points) > 1 else 5.0

        self.program = ShaderProgram(Shader(_VERTEX_SRC, "vertex"),
                                     Shader(_FRAGMENT_SRC, "fragment"))
        self.batch = Batch()
        self.chunks: list[Chunk] = []
        self._built = 0
        self._chunk_count = max(1, int(math.ceil(self.total_m / CHUNK_LENGTH_M)))
        self.sky_top = (0.42, 0.62, 0.86)
        self.sky_bottom = (0.78, 0.86, 0.94)

    # ------------------------------------------------------------ construção

    @property
    def build_progress(self) -> float:
        return self._built / self._chunk_count if self._chunk_count else 1.0

    @property
    def ready(self) -> bool:
        return self._built >= self._chunk_count

    def build_step(self, budget: int = 2) -> None:
        """Constrói alguns troços. Chamado repetidamente no ecrã de preparação,
        para a barra de progresso andar em vez de a janela congelar."""
        for _ in range(budget):
            if self.ready:
                return
            self._build_chunk(self._built)
            self._built += 1

    def build_all(self) -> None:
        while not self.ready:
            self.build_step(8)

    def _index_at(self, dist_m: float) -> int:
        return max(0, min(len(self.points) - 1, int(dist_m / self.step_m)))

    def _normal_of(self, i: int) -> tuple[float, float]:
        """Perpendicular horizontal ao sentido da estrada, normalizada."""
        a = self.points[max(0, i - 1)]
        b = self.points[min(len(self.points) - 1, i + 1)]
        dx, dy = b.x_m - a.x_m, b.y_m - a.y_m
        length = math.hypot(dx, dy) or 1.0
        return dy / length, -dx / length

    def _build_chunk(self, index: int) -> None:
        start_m = index * CHUNK_LENGTH_M
        end_m = min(self.total_m, start_m + CHUNK_LENGTH_M)
        i0 = self._index_at(start_m)
        i1 = self._index_at(end_m)
        if i1 <= i0:
            i1 = min(len(self.points) - 1, i0 + 1)

        group = Group(order=0)
        chunk = Chunk(index, start_m, end_m, group)

        verts: list[float] = []
        normals: list[float] = []
        colors: list[float] = []
        indices: list[int] = []

        def quad(p1, p2, p3, p4, color, normal=(0.0, 1.0, 0.0)):
            base = len(verts) // 3
            for p in (p1, p2, p3, p4):
                verts.extend(p)
                normals.extend(normal)
                colors.extend(color)
            indices.extend([base, base + 1, base + 2, base, base + 2, base + 3])

        bands = self.cfg["terrain_bands"]
        skirt = self.cfg["skirt"]
        band_offsets = [ROAD_HALF_WIDTH + SHOULDER]
        for b in range(bands):
            band_offsets.append(band_offsets[-1] + skirt / bands)

        for i in range(i0, i1):
            a, b = self.points[i], self.points[i + 1]
            nax, nay = self._normal_of(i)
            nbx, nby = self._normal_of(i + 1)

            def edge(pt, nx, ny, offset, height=None):
                return (pt.x_m + nx * offset,
                        pt.ele_m if height is None else height,
                        pt.y_m + ny * offset)

            # alcatrão, com variação muito ligeira de tom para não parecer plástico
            shade = 0.17 + 0.02 * _hash01(i, 3)
            road = (shade, shade, shade + 0.01, 1.0)
            quad(edge(a, nax, nay, -ROAD_HALF_WIDTH), edge(a, nax, nay, ROAD_HALF_WIDTH),
                 edge(b, nbx, nby, ROAD_HALF_WIDTH), edge(b, nbx, nby, -ROAD_HALF_WIDTH),
                 road)

            # linha central descontínua
            if i % 4 < 2:
                quad(edge(a, nax, nay, -0.12), edge(a, nax, nay, 0.12),
                     edge(b, nbx, nby, 0.12), edge(b, nbx, nby, -0.12),
                     (0.85, 0.85, 0.80, 1.0))

            # bermas claras
            for side in (-1, 1):
                inner = side * ROAD_HALF_WIDTH
                outer = side * (ROAD_HALF_WIDTH + 0.18)
                quad(edge(a, nax, nay, inner), edge(a, nax, nay, outer),
                     edge(b, nbx, nby, outer), edge(b, nbx, nby, inner),
                     (0.80, 0.80, 0.76, 1.0))

                # terreno em faixas, cada vez mais larga e mais acidentada
                for band in range(bands):
                    o_in = side * band_offsets[band]
                    o_out = side * band_offsets[band + 1]
                    amp = 2.0 + band * 4.0
                    pa_in = edge(a, nax, nay, o_in)
                    pb_in = edge(b, nbx, nby, o_in)
                    pa_out = edge(a, nax, nay, o_out)
                    pb_out = edge(b, nbx, nby, o_out)
                    if band > 0:
                        pa_in = (pa_in[0], _terrain_height(pa_in[0], pa_in[2],
                                                           a.ele_m, amp * 0.5), pa_in[2])
                        pb_in = (pb_in[0], _terrain_height(pb_in[0], pb_in[2],
                                                           b.ele_m, amp * 0.5), pb_in[2])
                    pa_out = (pa_out[0], _terrain_height(pa_out[0], pa_out[2],
                                                         a.ele_m, amp), pa_out[2])
                    pb_out = (pb_out[0], _terrain_height(pb_out[0], pb_out[2],
                                                         b.ele_m, amp), pb_out[2])
                    green = 0.30 + 0.16 * _hash01(i, band, side)
                    quad(pa_in, pa_out, pb_out, pb_in,
                         (green * 0.55, green, green * 0.42, 1.0))

        # postes e árvores ao longo do troço
        every = self.cfg["prop_every_m"]
        d = start_m
        while d < end_m:
            i = self._index_at(d)
            p = self.points[i]
            nx, ny = self._normal_of(i)
            side = 1.0 if _hash01(d, 1) > 0.5 else -1.0
            offset = side * (ROAD_HALF_WIDTH + 2.0 + 6.0 * _hash01(d, 2))
            bx = p.x_m + nx * offset
            bz = p.y_m + ny * offset
            by = p.ele_m
            if _hash01(d, 5) > 0.35:
                self._add_tree(verts, normals, colors, indices, bx, by, bz, d)
            else:
                self._add_pole(verts, normals, colors, indices, bx, by, bz)
            d += every * (0.6 + 0.8 * _hash01(d, 7))

        if indices:
            vlist = self.program.vertex_list_indexed(
                len(verts) // 3, GL_TRIANGLES, indices, batch=self.batch, group=group,
                position=("f", verts), normal=("f", normals), color=("f", colors))
            chunk.vertex_lists.append(vlist)
        group.visible = False
        self.chunks.append(chunk)

    @staticmethod
    def _add_tree(verts, normals, colors, indices, x, y, z, seed) -> None:
        height = 4.0 + 4.0 * _hash01(seed, 11)
        radius = 1.0 + 1.4 * _hash01(seed, 13)
        trunk = (0.28, 0.20, 0.13, 1.0)
        leaf_t = 0.34 + 0.18 * _hash01(seed, 17)
        leaf = (leaf_t * 0.45, leaf_t, leaf_t * 0.35, 1.0)

        def box(cx, cy, cz, hw, hh, color):
            base = len(verts) // 3
            pts = [(cx - hw, cy, cz), (cx + hw, cy, cz), (cx + hw, cy + hh, cz),
                   (cx - hw, cy + hh, cz), (cx, cy, cz - hw), (cx, cy, cz + hw),
                   (cx, cy + hh, cz + hw), (cx, cy + hh, cz - hw)]
            for p in pts:
                verts.extend(p)
                normals.extend((0.0, 0.6, 0.8))
                colors.extend(color)
            indices.extend([base, base + 1, base + 2, base, base + 2, base + 3,
                            base + 4, base + 5, base + 6, base + 4, base + 6, base + 7])

        box(x, y, z, 0.18, height * 0.45, trunk)
        box(x, y + height * 0.35, z, radius, height * 0.65, leaf)

    @staticmethod
    def _add_pole(verts, normals, colors, indices, x, y, z) -> None:
        base = len(verts) // 3
        h = 7.0
        color = (0.45, 0.44, 0.42, 1.0)
        pts = [(x - 0.12, y, z), (x + 0.12, y, z), (x + 0.12, y + h, z), (x - 0.12, y + h, z),
               (x, y, z - 0.12), (x, y, z + 0.12), (x, y + h, z + 0.12), (x, y + h, z - 0.12)]
        for p in pts:
            verts.extend(p)
            normals.extend((0.0, 0.5, 0.9))
            colors.extend(color)
        indices.extend([base, base + 1, base + 2, base, base + 2, base + 3,
                        base + 4, base + 5, base + 6, base + 4, base + 6, base + 7])

    # -------------------------------------------------------------- desenho

    def camera(self, dist_m: float) -> tuple[Mat4, tuple[float, float, float]]:
        """Matriz de vista em primeira pessoa e a posição do olho."""
        i = self._index_at(dist_m)
        p = self.points[i]
        ahead = self.points[min(len(self.points) - 1, i + 4)]
        eye = (p.x_m, p.ele_m + EYE_HEIGHT, p.y_m)
        target = (ahead.x_m, ahead.ele_m + EYE_HEIGHT * 0.92, ahead.y_m)
        if abs(target[0] - eye[0]) < 1e-6 and abs(target[2] - eye[2]) < 1e-6:
            target = (eye[0], target[1], eye[2] - 10.0)
        return Mat4.look_at(Vec3(*eye), Vec3(*target), Vec3(0.0, 1.0, 0.0)), eye

    def visible_chunks(self, dist_m: float) -> None:
        """Mostra só o que cabe na distância de desenho do preset (req. 3)."""
        draw = self.cfg["draw_m"]
        lo = dist_m - CHUNK_LENGTH_M          # um troço atrás, para as curvas
        hi = dist_m + draw
        for c in self.chunks:
            c.group.visible = (c.end_m >= lo) and (c.start_m <= hi)

    def setup_gl(self) -> None:
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)
        # A malha é construída em dois sentidos (estrada e taludes), por isso
        # o corte de faces fica desligado — custa pouco e evita buracos.
        glDisable(GL_CULL_FACE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glClearColor(*self.sky_bottom, 1.0)

    def draw(self, window, dist_m: float) -> None:
        # o estado de GL é partilhado com os menus: repõe-se o nosso a cada frame
        self.setup_gl()
        draw_distance = self.cfg["draw_m"]
        view, _ = self.camera(dist_m)
        window.projection = Mat4.perspective_projection(
            window.aspect_ratio, z_near=0.4, z_far=draw_distance * 1.2, fov=68.0)
        window.view = view
        self.visible_chunks(dist_m)
        self.program.use()
        self.program["sun"] = Vec3(0.4, 0.85, 0.3)
        self.program["fog_color"] = Vec3(*self.sky_bottom)
        self.program["fog_start"] = draw_distance * 0.45
        self.program["fog_end"] = draw_distance
        self.batch.draw()
        self.program.stop()

    def delete(self) -> None:
        for c in self.chunks:
            for vl in c.vertex_lists:
                try:
                    vl.delete()
                except Exception:
                    pass
        self.chunks.clear()
