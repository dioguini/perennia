"""O GPX Conversor, no construtor de treinos manuais (ciclismo e corrida).

Escolhe-se um percurso (.gpx), a fórmula e a precisão, e os blocos do treino são
gerados a partir do perfil: o nível do rolo ou a inclinação (e a velocidade) da
passadeira em cada troço. Ver `perennia.core.gpx_convert` para as fórmulas."""
from __future__ import annotations

from perennia.core import gpx_convert as gc
from perennia.core import workout_meta as wm
from perennia.core.i18n import tr
from perennia.ui.app import PopupMixin
from perennia.ui.session_setup import GpxPickerPopup, RoutePickerPopup
from perennia.ui.sport_screens import EditScreen
from perennia.ui.widgets import Item


class GpxConverter(PopupMixin, EditScreen):
    W, H = 920, 700
    SEARCH = False
    AGENT = False
    DATE_FIELDS: tuple = ()

    def __init__(self, app, builder):
        super().__init__(app)
        self.builder = builder
        self.sport = builder.sport
        lim = wm.device_limits(app.db)
        ath = app.db.athlete()
        self.p = gc.Params(
            sport=self.sport, formula="direct" if self.sport == "running" else "linear",
            incline_step=lim["treadmill_incline_step"], max_incline=lim["treadmill_max_incline"],
            max_kmh=lim["treadmill_max_kmh"], weight_kg=ath.weight_kg or 75.0,
            cda=getattr(ath, "cda", 0.32) or 0.32, crr=getattr(ath, "crr", 0.004) or 0.004,
            ftp_w=ath.ftp_w or 200)
        if self.sport == "running":
            self.p.speed_kmh = min(self.p.max_kmh, 10.0)
        self.route_id: str | None = None
        self.route_name = ""
        self.points: list = []
        self.back_button = None
        self._init_popup()

    # ----------------------------------------------------------- rota

    def formulas(self) -> tuple[str, ...]:
        return gc.RUN_FORMULAS if self.sport == "running" else gc.BIKE_FORMULAS

    def choose_route(self) -> None:
        def new() -> None:
            self.app.push(GpxPickerPopup(self.app, on_pick=self.set_route))
        self.app.push(RoutePickerPopup(self.app, self.set_route, optional=False,
                                       current=self.route_id, on_new=new))

    def set_route(self, route_id: str | None) -> None:
        if not route_id:
            return
        row = self.app.db.route(route_id)
        self.route_id = route_id
        self.route_name = row["name"] if row else ""
        self.points = self.app.db.route_points(route_id)
        self.enter()

    def secs(self) -> list:
        return gc.sections(self.points, self.p) if self.points else []

    # ----------------------------------------------------------- campos

    def cycle(self, field: str, step: int) -> None:
        p = self.p
        if field == "formula":
            fs = self.formulas()
            p.formula = fs[(fs.index(p.formula) + step) % len(fs)] if p.formula in fs else fs[0]
        elif field == "window":
            p.window_m = gc.WINDOWS_M[(gc.WINDOWS_M.index(p.window_m) + step)
                                      % len(gc.WINDOWS_M)] if p.window_m in gc.WINDOWS_M \
                else gc.WINDOWS_M[1]
        elif field == "seg":
            p.seg_m = gc.SEGMENTS_M[(gc.SEGMENTS_M.index(p.seg_m) + step)
                                    % len(gc.SEGMENTS_M)] if p.seg_m in gc.SEGMENTS_M \
                else gc.SEGMENTS_M[1]
        elif field == "speed_mode":
            p.speed_mode = gc.SPEED_MODES[(gc.SPEED_MODES.index(p.speed_mode) + step)
                                          % len(gc.SPEED_MODES)]

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        p = self.p
        if field == "speed":
            p.speed_kmh = max(4.0, min(p.max_kmh, round(p.speed_kmh + steps * (1.0 if big
                                                                                 else 0.5), 1)))
        elif field == "flat":
            p.flat_pct = max(40.0, min(110.0, p.flat_pct + steps * (5 if big else 1)))
        elif field == "gain":
            p.gain = max(0.0, min(15.0, round(p.gain + steps * (1.0 if big else 0.5), 1)))

    def num_set(self, field: str, value: float | None) -> None:
        if value is None:
            return
        p = self.p
        if field == "speed":
            p.speed_kmh = max(4.0, min(p.max_kmh, float(value)))
        elif field == "flat":
            p.flat_pct = max(40.0, min(110.0, float(value)))
        elif field == "gain":
            p.gain = max(0.0, min(15.0, float(value)))

    # ----------------------------------------------------------- lista

    def enter(self) -> None:
        p = self.p
        rows = [Item(tr("Percurso (.gpx)", "Route (.gpx)"),
                     value=self.route_name or tr("escolher…", "pick…"),
                     detail=tr("Enter escolhe uma rota ou carrega um .gpx novo",
                               "Enter picks a route or loads a new .gpx"),
                     action=self.choose_route),
                Item(tr("Fórmula", "Formula"), value=tr(*gc.NAMES[p.formula]), data="cyc:formula",
                     detail=self._formula_help()),
                Item(tr("Média móvel da altitude", "Altitude moving average"),
                     value=f"{p.window_m} m", data="cyc:window",
                     detail=tr("alisa o ruído do GPS · maior = menos subidas falsas",
                               "smooths GPS noise · larger = fewer false climbs")),
                Item(tr("Troço mínimo", "Shortest section"), value=f"{p.seg_m} m",
                     data="cyc:seg",
                     detail=tr("menor = mais fiel ao terreno, mas mexes no aparelho mais vezes",
                               "shorter = truer to the terrain, but you adjust the device "
                               "more often"))]
        if self.sport == "running":
            rows.append(Item(tr("Velocidade", "Speed"),
                             value=tr(*gc.NAMES[p.speed_mode]), data="cyc:speed_mode",
                             detail=tr("Livre: a que quiseres (o bloco acaba na distância) · "
                                       "Constante: a mesma em todo o lado · Esforço constante "
                                       "(sugerido): abranda a subir e acelera a descer",
                                       "Free: whatever you like (the block ends at the "
                                       "distance) · Constant: the same everywhere · Constant "
                                       "effort (suggested): slows on climbs, speeds up on "
                                       "descents")))
            if p.speed_mode != "free":
                rows.append(Item(tr("Velocidade na plana", "Flat speed"),
                                 value=f"{p.speed_kmh:.1f} km/h", data="num:speed",
                                 detail=tr("máx. da passadeira {m:.1f} km/h (Definições)",
                                           "treadmill top {m:.1f} km/h (Settings)",
                                           m=p.max_kmh)))
        else:
            rows += [Item(tr("Intensidade na plana", "Flat intensity"),
                          value=f"{p.flat_pct:.0f} % FTP ≈ {p.flat_pct * p.ftp_w / 100:.0f} W",
                          data="num:flat"),
                     Item(tr("Ganho por 1 % de inclinação", "Gain per 1 % grade"),
                          value=f"+{p.gain:g} % FTP", data="num:gain",
                          detail=tr("só na fórmula linear", "linear formula only"))]
        secs = self.secs()
        if secs:
            s = gc.summary(self.points, secs)
            sub = tr("{k:.1f} km · ↑ {a:.0f} m · {n} blocos · {c} mudanças · inclinação máx. "
                     "{g:.1f} %", "{k:.1f} km · ↑ {a:.0f} m · {n} blocks · {c} changes · max "
                     "grade {g:.1f} %", k=s["km"], a=s["ascent_m"], n=s["blocks"],
                     c=s["changes"], g=s["max_grade"])
        else:
            sub = tr("Escolhe um percurso para ver o treino que daí sai",
                     "Pick a route to see the workout it makes")
        rows.append(Item(tr("Resultado", "Result"), value=sub, enabled=False))
        rows += [Item(tr("Cancelar", "Cancel"), button=True, action=self.app.pop),
                 Item(tr("Converter e aplicar", "Convert and apply"), button=True, primary=True,
                      enabled=bool(secs), action=self.apply)]
        self.chrome.set(tr("GPX Conversor", "GPX Converter"),
                        tr("Do percurso para os níveis do {d}", "From the route to the {d}'s "
                           "levels", d=tr("rolo", "trainer") if self.sport == "cycling"
                           else tr("passadeira", "treadmill")), "")
        self.list.set_items(rows, keep_index=True)

    def _formula_help(self) -> str:
        return {
            "direct": tr("inclinação da passadeira = inclinação do troço (descidas a 0 %)",
                         "treadmill incline = the section's grade (descents at 0 %)"),
            "calibrated": tr("como a direta, menos 1 % (compensa a falta de ar na passadeira)",
                             "like direct, minus 1 % (makes up for the missing air resistance)"),
            "effort": tr("inclinação + velocidade que mantém o esforço (custo de Minetti)",
                         "incline + a speed that keeps effort constant (Minetti cost)"),
            "linear": tr("nível = % FTP plana + ganho × inclinação",
                         "level = flat % FTP + gain × grade"),
            "physics": tr("a potência para a mesma velocidade, pela física da bicicleta",
                          "the power for the same speed, from bike physics"),
        }.get(self.p.formula, "")

    # ----------------------------------------------------------- aplicar

    def apply(self) -> None:
        secs = self.secs()
        if not secs:
            return
        b = self.builder
        ctx = b.ctx
        blocks = gc.to_blocks(secs, self.p, lambda pace_s: ctx.pct_from("pace", pace_s))
        if self.sport == "cycling" and "level" in b.modes:
            b.mode = "level"
            b.tab = b.modes.index("level")
        elif self.sport == "running" and "pace" in b.modes:
            b.mode = "pace"
            b.tab = b.modes.index("pace")
        b.blocks = blocks
        b.sel = 0
        if self.route_name and (not b.name.strip() or b.name.strip() in (
                tr("Novo treino", "New workout"), tr("Treino", "Workout"))):
            b.name = self.route_name
        b.dirty = True
        self.app.pop()
        if b.tabs is not None:
            b.tabs.select(b.tab)
        b.on_tab()
        b.enter()
        self.app.message(tr("{n} blocos criados a partir de «{r}»", "{n} blocks made from "
                            "“{r}”", n=len(blocks), r=self.route_name))
