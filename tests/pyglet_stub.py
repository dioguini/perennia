"""Uma pyglet falsa, para poder correr a interface sem placa gráfica.

Não desenha nada: substitui as janelas, etiquetas, formas e o programa de
shaders por objetos que apenas registam o que lhes foi pedido. Isto não
valida a API da pyglet verdadeira — valida o nosso código: nomes errados,
atributos que não existem, ecrãs que rebentam ao abrir, contas que dão
divisão por zero. É nesse tipo de erro que se gasta a primeira hora de
quem instala a aplicação.

Instala-se chamando `install()` antes de importar `velo.ui` ou `velo.gfx`.
"""
from __future__ import annotations

import sys
import types

created: dict[str, list] = {"labels": [], "rects": [], "lines": [], "vlists": [],
                            "sprites": []}
calls: list[tuple[str, tuple]] = []


def reset() -> None:
    for key in created:
        created[key].clear()
    calls.clear()


class _Recorder:
    """Devolve funções que não fazem nada e registam a chamada."""

    def __init__(self, prefix: str = ""):
        self._prefix = prefix

    def __getattr__(self, name: str):
        if name.isupper():          # constantes do OpenGL
            return len(name)
        def fn(*args, **kwargs):
            calls.append((self._prefix + name, args))
            return None
        return fn


class Label:
    """Imita a API da pyglet 2.1: aceita `weight`, recusa `bold`."""

    def __init__(self, text="", font_name=None, font_size=12, weight="normal",
                 color=(255, 255, 255, 255), x=0, y=0, anchor_x="left",
                 anchor_y="baseline", batch=None, group=None, multiline=False,
                 width=None, **kw):
        if "bold" in kw:
            raise TypeError("Label.__init__() got an unexpected keyword argument 'bold'")
        if kw:
            raise TypeError(f"argumentos desconhecidos: {sorted(kw)}")
        self.text = text
        self.font_name = font_name
        self.font_size = font_size
        self.weight = weight
        self.bold = weight == "bold"
        self.color = color
        self.x, self.y = x, y
        self.anchor_x, self.anchor_y = anchor_x, anchor_y
        self.batch = batch
        created["labels"].append(self)

    def draw(self) -> None:
        calls.append(("Label.draw", (self.text,)))

    def delete(self) -> None:
        pass


class Rectangle:
    def __init__(self, x=0, y=0, width=1, height=1, color=(255, 255, 255),
                 batch=None, group=None, **kw):
        self.x, self.y = x, y
        self.width, self.height = width, height
        self.color = color
        self.opacity = 255
        self.batch = batch
        created["rects"].append(self)

    def draw(self) -> None:
        calls.append(("Rectangle.draw", (self.x, self.y)))

    def delete(self) -> None:
        pass


class Line:
    """A pyglet verdadeira chamou a espessura `width` (2.0) e `thickness` (2.1).

    Aqui aceitamos as duas, mas o nosso código tem de passar uma delas e
    sobreviver a um TypeError na outra — é isso que o widget faz.
    """

    def __init__(self, x=0, y=0, x2=0, y2=0, thickness=None, width=None,
                 color=(255, 255, 255), batch=None, group=None, **kw):
        if thickness is None and width is None:
            raise TypeError("falta a espessura")
        self.x, self.y, self.x2, self.y2 = x, y, x2, y2
        self.thickness = thickness if thickness is not None else width
        self.color = color
        self.batch = batch
        self.opacity = 255
        created["lines"].append(self)

    def draw(self) -> None:
        pass

    def delete(self) -> None:
        pass


class _Image:
    def __init__(self, path=""):
        self.path = path
        self.width = self.height = 64


class Sprite:
    def __init__(self, img, x=0, y=0, batch=None, group=None, **kw):
        self.image, self.x, self.y, self.batch = img, x, y, batch
        self.scale = 1.0
        self.opacity = 255
        self.visible = True
        created.setdefault("sprites", []).append(self)

    @property
    def width(self):
        return self.image.width * self.scale

    @property
    def height(self):
        return self.image.height * self.scale

    def update(self, x=None, y=None, scale=None, **kw):
        if x is not None:
            self.x = x
        if y is not None:
            self.y = y
        if scale is not None:
            self.scale = scale

    def draw(self) -> None:
        pass

    def delete(self) -> None:
        pass


class Batch:
    def __init__(self):
        self.drawn = 0

    def draw(self) -> None:
        self.drawn += 1
        calls.append(("Batch.draw", ()))


class Group:
    def __init__(self, order=0, parent=None):
        self.order = order
        self.visible = True


class _VertexList:
    def __init__(self, count: int):
        self.count = count
        self.deleted = False
        created["vlists"].append(self)

    def delete(self) -> None:
        self.deleted = True


class Shader:
    def __init__(self, source: str, kind: str):
        if kind not in ("vertex", "fragment"):
            raise ValueError(f"tipo de shader inválido: {kind}")
        if "void main" not in source:
            raise ValueError("shader sem main()")
        self.source = source
        self.kind = kind


class ShaderProgram:
    def __init__(self, *shaders):
        self.shaders = shaders
        self.uniforms: dict = {}
        self.in_use = False

    def use(self) -> None:
        self.in_use = True

    def stop(self) -> None:
        self.in_use = False

    def __setitem__(self, name: str, value) -> None:
        self.uniforms[name] = value

    def vertex_list_indexed(self, count, mode, indices, batch=None, group=None,
                            **data):
        # Verifica a coerência que a pyglet verdadeira também exigiria.
        for name, (fmt, values) in data.items():
            if len(values) % count != 0:
                raise ValueError(
                    f"atributo {name}: {len(values)} valores não divide por "
                    f"{count} vértices")
        if indices and max(indices) >= count:
            raise ValueError(
                f"índice {max(indices)} fora do alcance de {count} vértices")
        return _VertexList(count)


class Window:
    def __init__(self, width=800, height=600, caption="", resizable=False,
                 fullscreen=False, **kw):
        self.width, self.height = width, height
        self.caption = caption
        self.fullscreen = fullscreen
        self.projection = None
        self.view = None
        self.handlers: list[dict] = []
        self.cleared = 0
        self.screen = types.SimpleNamespace(width=2560, height=1440)
        if fullscreen:
            self._saved = (width, height)
            self.width, self.height = self.screen.width, self.screen.height

    @property
    def aspect_ratio(self) -> float:
        return self.width / max(self.height, 1)

    def clear(self) -> None:
        self.cleared += 1

    def push_handlers(self, **handlers) -> None:
        self.handlers.append(handlers)

    def set_fullscreen(self, value: bool) -> None:
        self.fullscreen = value
        if value:
            self._saved = (self.width, self.height)
            self.width, self.height = self.screen.width, self.screen.height
        elif hasattr(self, "_saved"):
            self.width, self.height = self._saved

    def set_size(self, width: int, height: int) -> None:
        if self.fullscreen:
            raise RuntimeError("set_size em ecrã inteiro")    # a pyglet real ignora
        self.width, self.height = width, height

    def set_minimum_size(self, width: int, height: int) -> None:
        self.minimum_size = (width, height)

    def close(self) -> None:
        pass


class FPSDisplay:
    def __init__(self, window):
        self.window = window

    def draw(self) -> None:
        pass


class Mat4(tuple):
    def __new__(cls, values=None):
        return super().__new__(cls, values or [0.0] * 16)

    @classmethod
    def perspective_projection(cls, aspect, z_near=0.1, z_far=1000.0, fov=60.0):
        if aspect <= 0:
            raise ValueError("razão de aspeto inválida")
        if z_near <= 0 or z_far <= z_near:
            raise ValueError(f"planos inválidos: {z_near} .. {z_far}")
        return cls()

    @classmethod
    def orthogonal_projection(cls, left, right, bottom, top, z_near, z_far):
        if right == left or top == bottom:
            raise ValueError("projeção ortogonal degenerada")
        return cls()

    @classmethod
    def look_at(cls, eye, target, up):
        if tuple(eye) == tuple(target):
            raise ValueError("câmara a olhar para o próprio olho")
        return cls()


class Vec3(tuple):
    def __new__(cls, x=0.0, y=0.0, z=0.0):
        return super().__new__(cls, (x, y, z))

    @property
    def x(self):
        return self[0]

    @property
    def y(self):
        return self[1]

    @property
    def z(self):
        return self[2]


class _Clock:
    def __init__(self):
        self.intervals: list = []
        self.once: list = []

    def schedule_interval(self, fn, interval) -> None:
        self.intervals.append((fn, interval))

    def schedule_once(self, fn, delay) -> None:
        self.once.append((fn, delay))

    def unschedule(self, fn) -> None:
        self.intervals = [x for x in self.intervals if x[0] is not fn]


class _Key:
    """Códigos de tecla. Os valores não importam, só terem de ser distintos."""
    UP, DOWN, LEFT, RIGHT = 1, 2, 3, 4
    ENTER, RETURN, SPACE, ESCAPE = 5, 6, 7, 8
    A, B, C, D, E, F, G, H, I, J, K, L = range(20, 32)
    M, N, O, P, Q, R, S, T, U, V, W, X, Y, Z = range(32, 46)
    DELETE, BACKSPACE, TAB = 50, 51, 52
    F1, F2, F3, F4, F5, F6, F7, F8, F9, F10, F11, F12 = range(60, 72)
    MOD_SHIFT, MOD_CTRL, MOD_ALT = 1, 2, 4
    PLUS, EQUAL, MINUS, NUM_ADD, NUM_SUBTRACT = 80, 81, 82, 83, 84
    BRACKETLEFT, BRACKETRIGHT, HOME, END, TAB2 = 85, 86, 87, 88, 89
    PAGEUP, PAGEDOWN, PERIOD, COMMA = 90, 91, 92, 93


def install() -> types.ModuleType:
    """Põe a pyglet falsa em sys.modules. Idempotente: se já lá estiver, devolve
    a mesma (vários ficheiros de teste instalam-na; os módulos da aplicação já
    importados têm de continuar a ver o mesmo objeto)."""
    existing = sys.modules.get("pyglet")
    if existing is not None and getattr(existing, "version", "") == "0.0-stub":
        return existing
    pyglet = types.ModuleType("pyglet")
    pyglet.version = "0.0-stub"

    gl = types.ModuleType("pyglet.gl")
    recorder = _Recorder("gl.")
    for name in ("glEnable", "glDisable", "glDepthFunc", "glBlendFunc",
                 "glClearColor", "glViewport", "glClear"):
        setattr(gl, name, getattr(recorder, name))
    for name in ("GL_DEPTH_TEST", "GL_CULL_FACE", "GL_BLEND", "GL_LEQUAL",
                 "GL_TRIANGLES", "GL_SRC_ALPHA", "GL_ONE_MINUS_SRC_ALPHA",
                 "GL_LINES", "GL_COLOR_BUFFER_BIT", "GL_DEPTH_BUFFER_BIT"):
        setattr(gl, name, len(name))

    shader_mod = types.ModuleType("pyglet.graphics.shader")
    shader_mod.Shader = Shader
    shader_mod.ShaderProgram = ShaderProgram

    graphics = types.ModuleType("pyglet.graphics")
    graphics.Batch = Batch
    graphics.Group = Group
    graphics.shader = shader_mod

    class Config:
        def __init__(self, **kw):
            self.kw = kw
    gl.Config = Config

    shapes = types.ModuleType("pyglet.shapes")
    shapes.Rectangle = Rectangle
    shapes.Line = Line
    shapes.Circle = Rectangle
    shapes.BorderedRectangle = Rectangle

    text = types.ModuleType("pyglet.text")
    text.Label = Label

    math_mod = types.ModuleType("pyglet.math")
    math_mod.Mat4 = Mat4
    math_mod.Vec3 = Vec3

    key_mod = types.ModuleType("pyglet.window.key")
    for name in dir(_Key):
        if not name.startswith("_"):
            setattr(key_mod, name, getattr(_Key, name))

    window_mod = types.ModuleType("pyglet.window")
    window_mod.Window = Window
    window_mod.FPSDisplay = FPSDisplay
    window_mod.key = key_mod

    clock = _Clock()
    clock_mod = types.ModuleType("pyglet.clock")
    clock_mod.schedule_interval = clock.schedule_interval
    clock_mod.schedule_once = clock.schedule_once
    clock_mod.unschedule = clock.unschedule
    clock_mod._clock = clock

    app_mod = types.ModuleType("pyglet.app")
    app_mod.run = lambda *a, **k: calls.append(("app.run", ()))
    app_mod.exit = lambda *a, **k: calls.append(("app.exit", ()))

    pyglet.gl = gl
    pyglet.graphics = graphics
    pyglet.shapes = shapes

    image_mod = types.ModuleType("pyglet.image")

    def _load(path, *a, **k):
        import os
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        return _Image(path)
    image_mod.load = _load
    sprite_mod = types.ModuleType("pyglet.sprite")
    sprite_mod.Sprite = Sprite
    pyglet.image = image_mod
    pyglet.sprite = sprite_mod
    pyglet.text = text
    pyglet.math = math_mod
    pyglet.window = window_mod
    pyglet.clock = clock_mod
    pyglet.app = app_mod

    for name, module in (("pyglet", pyglet), ("pyglet.gl", gl),
                         ("pyglet.graphics", graphics),
                         ("pyglet.graphics.shader", shader_mod),
                         ("pyglet.shapes", shapes), ("pyglet.text", text),
                         ("pyglet.math", math_mod), ("pyglet.window", window_mod),
                         ("pyglet.window.key", key_mod),
                         ("pyglet.clock", clock_mod), ("pyglet.app", app_mod),
                         ("pyglet.image", image_mod), ("pyglet.sprite", sprite_mod)):
        sys.modules[name] = module
    return pyglet
