"""Motor da sessão (req. 6, 7, 9, 11, 13, 14, 20, 21, 23, 24, 25).

Chamar `update(dt)` a cada frame; o motor corre a física, grava amostras a
1 Hz, cronometra subidas, acompanha fantasmas, segue o treino, envia
resistência ao trainer e emite eventos para o HUD mostrar.

Nada aqui sabe desenhar nem falar Bluetooth: recebe leituras por um objeto
com `.reading()` e manda comandos por um objeto com `.set_sim()` /
`.set_target_power()`. É isso que permite testá-lo sem hardware.
"""
from __future__ import annotations

import bisect
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from . import fit, naming, physics
from .boards import Board, LiveBoards
from .chase import Chase
from .climbs import signs_for
from .db import Athlete, Climb, Database, Lap, RideSummary, Sample
from .route_index import RouteIndex
from .workouts import WorkoutRunner

SAMPLE_INTERVAL_S = 1.0
FLUSH_EVERY = 5               # amostras: o máximo que se perde numa falha de energia
PHYSICS_STEP_S = 0.05        # 20 Hz
TRAINER_INTERVAL_S = 0.5     # 2 Hz
TRAINER_GRADE_EPSILON = 0.2  # só reenvia se mudou mais do que isto
SIGN_EVERY_M = 500.0
MOVING_POWER_W = 1
MOVING_SPEED_MPS = 0.1

# Pedalar = cadência acima de zero, ou potência acima disto quando não há
# sensor de cadência. Sem potência nem cadência, conta a velocidade do trainer.
PEDAL_POWER_W = 10
PEDAL_SPEED_MPS = 1.0
AUTO_PAUSE_AFTER_S = 3.0      # segundos sem pedalar até pausar
COAST_GRADE_PCT = -2.0        # a descer, deixar de pedalar não pausa…
COAST_SPEED_MPS = 2.0         # …enquanto a bicicleta ainda rola

# Estados da sessão, para o HUD
WAITING, RUNNING, PAUSED, AUTO_PAUSED = "waiting", "running", "paused", "auto_paused"


@dataclass
class Reading:
    """Leitura fundida dos sensores num instante."""
    power_w: int | None = None
    cadence_rpm: int | None = None
    hr_bpm: int | None = None
    speed_mps: float | None = None
    balance_left: float | None = None
    torque_nm: float | None = None
    # Eficácia do binário e suavidade da pedalada, em %, por perna. Vêm dos
    # pedais de duplo lado por ANT+ (página 0x13). Alguns medidores só dão a
    # suavidade combinada das duas pernas.
    te_left: float | None = None
    te_right: float | None = None
    ps_left: float | None = None
    ps_right: float | None = None
    ps_combined: float | None = None


def estimate_lthr(athlete: Athlete) -> int | None:
    """Limiar cardíaco para as zonas de FC. Sem ele definido, estima-se a
    partir da FC máxima (90 %) ou da idade (90 % de 220 − idade), para as
    zonas não ficarem em branco. Defini-lo nas Definições é mais certo."""
    if athlete.lthr:
        return athlete.lthr
    if athlete.max_hr:
        return int(round(athlete.max_hr * 0.9))
    if athlete.age:
        return int(round((220 - athlete.age) * 0.9))
    return None


# Os cinco valores de pedalada andam sempre juntos, da leitura ao .fit.
PEDAL_FIELDS = ("te_left", "te_right", "ps_left", "ps_right", "ps_combined")


@dataclass
class Event:
    kind: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class RideState:
    """Tudo o que o HUD e o registo de métricas precisam de ver."""
    t_s: float = 0.0
    dist_m: float = 0.0          # distância total da sessão
    pos_m: float = 0.0           # posição na rota (dá a volta ao chegar ao fim)
    loops: int = 0               # voltas completas à rota
    speed_mps: float = 0.0
    grade_pct: float = 0.0
    ele_m: float = 0.0
    ascent_m: float = 0.0
    power_w: int | None = None
    power_3s: int | None = None
    avg_power: float | None = None
    np_w: float | None = None
    balance_left: float | None = None      # instantâneo, % da perna esquerda
    balance_3s: float | None = None        # média de 3 s, para o HUD
    avg_balance: float | None = None       # média da sessão
    weight_kg: float | None = None         # do atleta, para os W/kg
    avg_torque: float | None = None
    power_zone_s: list = field(default_factory=lambda: [0.0] * 7)   # tempo em cada zona
    hr_zone_s: list = field(default_factory=lambda: [0.0] * 5)
    difficulty: float = 1.0                # sensação de declive, mudável a meio
    intensity: float = 1.0                 # alvo do treino ×, mudável a meio
    pedal: dict = field(default_factory=dict)      # último valor de cada PEDAL_FIELDS
    avg_pedal: dict = field(default_factory=dict)  # média da sessão
    cadence_rpm: int | None = None
    avg_cadence: float | None = None
    hr_bpm: int | None = None
    avg_hr: float | None = None
    avg_speed: float | None = None
    joules: float = 0.0
    tss: float | None = None
    ftp_w: int = 200
    lthr: int | None = None
    power_zone_bounds: list[float] = field(default_factory=list)
    hr_zone_bounds: list[float] = field(default_factory=list)
    target_power_w: int | None = None
    route: RouteIndex | None = None
    resistance_sent: float | None = None
    status: str = WAITING
    paused_s: float = 0.0


class Ghost:
    """Um esforço anterior, reproduzido por distância (req. 7).

    Guardamos (distância → tempo) e respondemos "em que segundo é que este
    esforço estava aqui", para calcular a diferença em tempo real.
    """

    def __init__(self, ride_id: str, label: str, samples: Sequence[Sample]):
        self.ride_id = ride_id
        self.label = label
        self._dist: list[float] = []
        self._time: list[float] = []
        for s in samples:
            # a distância tem de ser estritamente crescente para a busca
            if not self._dist or s.dist_m > self._dist[-1]:
                self._dist.append(s.dist_m)
                self._time.append(float(s.t_s))
        self.total_m = self._dist[-1] if self._dist else 0.0
        self.total_s = self._time[-1] if self._time else 0.0

    def time_at(self, dist_m: float) -> float | None:
        if not self._dist or dist_m > self.total_m:
            return None
        i = bisect.bisect_left(self._dist, dist_m)
        if i == 0:
            return self._time[0]
        if i >= len(self._dist):
            return self._time[-1]
        d0, d1 = self._dist[i - 1], self._dist[i]
        t0, t1 = self._time[i - 1], self._time[i]
        span = d1 - d0
        f = 0.0 if span <= 1e-9 else (dist_m - d0) / span
        return t0 + f * (t1 - t0)

    def dist_at(self, t_s: float) -> float:
        """Onde estaria o fantasma neste segundo — para o desenhar na estrada."""
        if not self._time:
            return 0.0
        i = bisect.bisect_left(self._time, t_s)
        if i == 0:
            return self._dist[0]
        if i >= len(self._time):
            return self._dist[-1]
        t0, t1 = self._time[i - 1], self._time[i]
        d0, d1 = self._dist[i - 1], self._dist[i]
        span = t1 - t0
        f = 0.0 if span <= 1e-9 else (t_s - t0) / span
        return d0 + f * (d1 - d0)


class _SectionTimer:
    """Cronómetro de um troço: subida detetada ou qualquer troço marcado."""

    def __init__(self, climb: Climb):
        self.climb = climb
        self.start_t: float = 0.0
        self.p_sum = 0.0
        self.p_n = 0
        self.hr_sum = 0.0
        self.hr_n = 0
        self.cad_sum = 0.0
        self.cad_n = 0
        self.bal_sum = 0.0
        self.bal_n = 0
        self.pending_signs: list[float] = []

    def observe(self, r: Reading) -> None:
        if r.power_w is not None:
            self.p_sum += r.power_w
            self.p_n += 1
        if r.hr_bpm is not None:
            self.hr_sum += r.hr_bpm
            self.hr_n += 1
        if r.cadence_rpm is not None:
            self.cad_sum += r.cadence_rpm
            self.cad_n += 1
        if r.balance_left is not None:
            self.bal_sum += r.balance_left
            self.bal_n += 1

    @property
    def avg_power(self) -> float | None:
        return self.p_sum / self.p_n if self.p_n else None

    @property
    def avg_balance(self) -> float | None:
        return self.bal_sum / self.bal_n if self.bal_n else None

    @property
    def avg_hr(self) -> float | None:
        return self.hr_sum / self.hr_n if self.hr_n else None

    @property
    def avg_cadence(self) -> float | None:
        return self.cad_sum / self.cad_n if self.cad_n else None


class RideEngine:
    def __init__(self, db: Database, athlete: Athlete, *,
                 route_id: str | None = None,
                 points: list | None = None,
                 climbs: Sequence[Climb] = (),
                 workout_runner: WorkoutRunner | None = None,
                 workout_id: str | None = None,
                 ghosts: Sequence[Ghost] = (),
                 kind: str = "route",
                 chase_level: str | None = None,
                 sensors: Any = None,
                 trainer: Any = None,
                 rides_dir: str | Path = "rides",
                 clock: Callable[[], float] = time.monotonic,
                 meta: dict | None = None,
                 resume: dict | None = None,
                 game: Any = None,
                 autolap: dict | None = None):
        """`meta`: o que o ecrã precisa para voltar a montar a sessão depois de
        uma falha (fantasmas, ERG, protocolo do teste de FTP); vai tal e qual
        para o ponto de recuperação. `resume`: um ponto de recuperação
        (`Database.checkpoint`) — retoma essa sessão em vez de abrir uma nova."""
        self.db = db
        self.athlete = athlete
        self.kind = kind
        self.route_id = route_id or None
        self.workout_id = workout_id or None
        self.sensors = sensors
        self.trainer = trainer
        self.ghosts = list(ghosts)
        self.workout = workout_runner
        self.rides_dir = Path(rides_dir)
        self._clock = clock

        self.difficulty = float(db.get("trainer_difficulty", 1.0))
        self.extra_resistance = float(db.get("extra_resistance_pct", 0.0))
        self.units = db.get("units", "metric")
        self.include_coords = bool(db.get("fit_include_coords", True))

        self.route = RouteIndex(points) if points else None
        self.climbs = list(climbs)
        self.events: list[Event] = []
        # segmentos do Strava na rota (só leitura; nunca vão para o agente)
        from . import segments as _segments
        try:
            segs = _segments.load(db, self.route_id) if self.route else []
        except Exception:
            segs = []
        self.strava = _segments.SegmentTracker(segs) if segs else None
        self.strava_results: list[dict] = []

        self.state = RideState(
            ftp_w=athlete.ftp_w, lthr=estimate_lthr(athlete), route=self.route,
            power_zone_bounds=list(db.get("power_zones_pct", [55, 75, 90, 105, 120, 150])),
            hr_zone_bounds=list(db.get("hr_zones_pct_lthr", [68, 83, 94, 105])),
        )
        if self.route:
            self.state.ele_m = self.route.ele_at(0.0)
            self.state.grade_pct = self.route.grade_at(0.0)
        self.state.weight_kg = athlete.weight_kg
        self.state.difficulty = self.difficulty
        self.state.power_zone_s = [0.0] * (len(self.state.power_zone_bounds) + 1)
        self.state.hr_zone_s = [0.0] * (len(self.state.hr_zone_bounds) + 1)
        # Traço de potência e FC ao longo da volta atual, para desenhar por cima
        # do perfil da rota (como no Zwift): (posição, potência 3 s, FC).
        self.trace: list[tuple[float, int | None, int | None]] = []
        self._torque_sum = 0.0
        self._torque_n = 0

        self.meta = dict(meta or {})
        from .sports import AutoLap
        if autolap is None:
            autolap = self.meta.get("autolap")
        self.autolap = AutoLap(autolap)
        if self.autolap.on:
            self.meta["autolap"] = self.autolap.as_dict()
        self.chase_level = chase_level
        self.game = game                 # modo Challenge (velo.core.games)
        self.game_result: dict | None = None
        if resume is not None:
            self.ride_id = resume["session_id"]
            self.start_unix = float(resume["config"].get("start_unix") or time.time())
        else:
            self.ride_id = db.begin_ride(
                route_id=route_id, workout_id=workout_id, kind=kind,
                mode="comparison" if ghosts else "alone",
                erg=bool(workout_runner and workout_runner.erg_enabled),
                athlete=athlete, difficulty=self.difficulty,
                extra=self.extra_resistance, preset=db.get("render_preset", "low"),
            )
            self.start_unix = time.time()
        self.recovered = resume is not None

        # estado interno
        self._t = 0.0
        self._moving_s = 0.0
        self._accum_sample = 0.0
        self._accum_trainer = 0.0
        self._accum_physics = 0.0
        self._last_grade_sent: float | None = None
        self._last_target_sent: int | None = None
        self._power_window: list[int] = []     # 3 s
        self._balance_window: list[float] = [] # 3 s
        self._power_series: list[float] = []   # 1 Hz, para NP e curva
        self._hr_sum = 0.0
        self._hr_n = 0
        self._cad_sum = 0.0
        self._cad_n = 0
        self._speed_sum = 0.0
        self._speed_n = 0
        self._power_sum = 0.0
        self._power_n = 0
        self._max_power = 0
        self._max_hr = 0
        self._bal_sum = 0.0
        self._bal_n = 0
        self._pedal_sum = {k: 0.0 for k in PEDAL_FIELDS}
        self._pedal_n = {k: 0 for k in PEDAL_FIELDS}
        self._pending: list[Sample] = []
        self._reading = Reading()
        self._last_sample_ele = self.state.ele_m

        # voltas
        self.lap_no = 1
        self._lap_start_t = 0.0
        self._lap_start_dist = 0.0
        self._lap_start_ele = self.state.ele_m
        self._lap_acc = _lap_accumulator()
        self.laps: list[Lap] = []

        # subidas
        self._next_climb = 0
        self._active: _SectionTimer | None = None
        self.climb_results: list[dict] = []

        # desafios em curso
        self._attempts: list[tuple[int, int, str, float]] = []  # (attempt, challenge, metric, target)
        for ch in db.challenges():
            row = db.ensure_attempt(ch["id"])
            self._attempts.append((row["id"], ch["id"], ch["metric"], ch["target"]))
        self._challenge_names = {c["id"]: c["name"] for c in db.challenges()}

        self.finished = False
        self.route_finished = False      # pelo menos uma volta completa
        # O relógio só arranca à primeira pedalada e para sozinho quando se
        # deixa de pedalar. A pausa manual (P ou botão) só sai com P ou botão.
        self.started = False
        self.manual_pause = False
        self.auto_pause = False
        self.auto_pause_enabled = bool(db.get("auto_pause", True))
        self._idle_s = 0.0
        self._paused_s = 0.0
        self._accum_wait_trainer = TRAINER_INTERVAL_S   # comanda já no 1.º frame
        self._loop_start_t = 0.0
        self._best_loop_s: float | None = None
        self._workout_done = False

        # modo fuga
        self.chase: Chase | None = None
        if chase_level:
            grade_at = None
            if self.route is not None:
                total = self.route.total_m
                grade_at = lambda d: self.route.grade_at(d % total)   # noqa: E731
            self.chase = Chase(chase_level, athlete.ftp_w, athlete.total_mass_kg,
                               athlete.cda, athlete.crr, grade_at=grade_at)
        self.chase_result: dict | None = None
        self.name = ""

        self.boards = LiveBoards(self)

        if resume is not None:
            self._restore(resume["state"])
            self.autolap.restore(self._t, self.state.dist_m)

        if self.trainer is not None:
            try:
                self.trainer.request_control()
                self.trainer.set_user_weight(athlete.weight_kg, athlete.bike_weight_kg)
            except Exception:
                pass

    # --------------------------------------------------------------- eventos

    def drain_events(self) -> list[Event]:
        out, self.events = self.events, []
        return out

    def _emit(self, kind: str, **data: Any) -> None:
        self.events.append(Event(kind, data))

    # ---------------------------------------------------------------- ciclo

    def update(self, dt: float) -> None:
        """Avança a sessão `dt` segundos de tempo real."""
        if self.finished or dt <= 0:
            return
        if self.sensors is not None:
            try:
                self._reading = self.sensors.reading() or Reading()
            except Exception:
                self._reading = Reading()

        r = self._reading
        if self.manual_pause:
            self._paused_s += dt
            self.state.status = PAUSED
            self.state.paused_s = self._paused_s
            return

        pedalling = self._is_pedalling(r)
        if not self.started:
            if not pedalling:
                self.state.status = WAITING
                self._prime_before_start(dt)
                return
            self.started = True
            self._emit("ride_started")

        if pedalling:
            self._idle_s = 0.0
            if self.auto_pause:
                self.auto_pause = False
                self._last_grade_sent = None
                self._last_target_sent = None
                self._emit("auto_resume")
        else:
            if self.auto_pause:
                self._paused_s += dt
                self.state.paused_s = self._paused_s
                self.state.power_w = r.power_w
                self.state.cadence_rpm = r.cadence_rpm
                self.state.hr_bpm = r.hr_bpm
                return
            self._idle_s += dt
            if self._should_auto_pause():
                self.auto_pause = True
                self.state.speed_mps = 0.0
                self.state.status = AUTO_PAUSED
                self._emit("auto_pause")
                return

        self.state.status = RUNNING
        self._t += dt
        self.state.power_w = r.power_w
        self.state.cadence_rpm = r.cadence_rpm
        self.state.hr_bpm = r.hr_bpm
        self.state.balance_left = r.balance_left

        # --- física a passo fixo, independente da taxa de frames
        self._accum_physics += dt
        while self._accum_physics >= PHYSICS_STEP_S:
            self._step_physics(PHYSICS_STEP_S)
            self._accum_physics -= PHYSICS_STEP_S

        # --- alvo do treino (ou do jogo)
        if self.workout is not None:
            self.state.target_power_w = self.workout.target_watts(self._t)
        elif self.game is not None:
            self.state.target_power_w = self.game.target_w

        # --- comando ao trainer
        self._accum_trainer += dt
        if self._accum_trainer >= TRAINER_INTERVAL_S:
            self._accum_trainer = 0.0
            self._command_trainer()

        # --- amostragem a 1 Hz
        self._accum_sample += dt
        while self._accum_sample >= SAMPLE_INTERVAL_S:
            self._accum_sample -= SAMPLE_INTERVAL_S
            self._take_sample()

        if self.autolap.due(self._t, self.state.dist_m):
            self.lap(self.autolap.mode)            # «time» ou «distance» no .fit
        self._track_sections()
        self._track_strava()
        self._track_ghosts()
        self.state.t_s = self._t

    # ------------------------------------------------------- pausas e arranque

    def _is_pedalling(self, r: Reading) -> bool:
        if r.cadence_rpm is not None:
            return r.cadence_rpm > 0
        if r.power_w is not None:
            return r.power_w >= PEDAL_POWER_W
        if r.speed_mps is not None:
            return r.speed_mps >= PEDAL_SPEED_MPS
        return False

    def _should_auto_pause(self) -> bool:
        if not self.auto_pause_enabled:
            return False
        if self.chase is not None and self.chase.active:
            # na fuga, parar de pedalar é deixar o pelotão chegar
            return False
        if self._idle_s < AUTO_PAUSE_AFTER_S:
            return False
        coasting = (self.state.grade_pct <= COAST_GRADE_PCT
                    and self.state.speed_mps > COAST_SPEED_MPS)
        return not coasting

    def _prime_before_start(self, dt: float) -> None:
        """Antes da 1.ª pedalada: trainer já com a resistência certa e o alvo
        do treino visível, mas o relógio parado."""
        r = self._reading
        self.state.power_w = r.power_w
        self.state.cadence_rpm = r.cadence_rpm
        self.state.hr_bpm = r.hr_bpm
        if self.workout is not None:
            self.state.target_power_w = self.workout.target_watts(0.0)
        elif self.game is not None:
            self.state.target_power_w = self.game.target_w
        self._accum_wait_trainer += dt
        if self._accum_wait_trainer >= TRAINER_INTERVAL_S:
            self._accum_wait_trainer = 0.0
            self._command_trainer()

    @property
    def paused(self) -> bool:
        """Pausada à mão ou automaticamente. Antes de arrancar não conta."""
        return self.manual_pause or self.auto_pause

    @property
    def loop_elapsed_s(self) -> float:
        return self._t - self._loop_start_t

    def active_climb(self) -> tuple[Climb, float] | None:
        """(subida, segundos desde o início dela) se estiver numa subida."""
        if self._active is None:
            return None
        return self._active.climb, self._t - self._active.start_t

    def live_board(self) -> Board:
        if self.game is not None:
            from . import games
            return self.game.board(games.history(self.db, self.game.key, 1))
        return self.boards.board()

    def _save_game(self) -> None:
        g = self.game
        if g is None or g.saved:
            return
        from . import games
        ranked = not self.recovered
        self.game_result = games.save_result(self.db, self.ride_id, g, ranked=ranked)
        self._emit("game_saved", **self.game_result)
        self.lap("game")

    def _step_physics(self, step: float) -> None:
        r = self._reading
        grade = self.state.grade_pct / 100.0

        if r.power_w is not None:
            self.state.speed_mps = physics.step_velocity(
                self.athlete.total_mass_kg, self.athlete.cda, self.athlete.crr,
                self.state.speed_mps, float(r.power_w), grade, step)
        elif r.speed_mps is not None:
            # trainer sem potência: aceita a velocidade que ele reporta
            self.state.speed_mps = r.speed_mps
        else:
            self.state.speed_mps = max(0.0, self.state.speed_mps - 1.5 * step)

        moving = (r.power_w or 0) >= MOVING_POWER_W or self.state.speed_mps > MOVING_SPEED_MPS
        if moving:
            self._moving_s += step

        prev_ele = self.state.ele_m
        self.state.dist_m += self.state.speed_mps * step
        if r.power_w:
            self.state.joules += r.power_w * step

        if self.chase is not None and self.chase.active:
            for kind, data in self.chase.step(step, self.state.dist_m):
                self._emit(kind, **data)
                if kind == "chase_caught":
                    self._save_chase(caught=True)

        if self.route is not None:
            # `dist_m` é a distância total da sessão; `pos_m` é onde estamos
            # na rota. Ao chegar ao fim, a rota dá a volta e a sessão continua
            # até o atleta a terminar — só o botão de parar termina.
            self.state.pos_m += self.state.speed_mps * step
            if self.state.pos_m >= self.route.total_m:
                self.state.pos_m -= self.route.total_m
                self._complete_loop()
            self.state.ele_m = self.route.ele_at(self.state.pos_m)
            self.state.grade_pct = self.route.grade_at(self.state.pos_m)
            climb = self.state.ele_m - prev_ele
            if 0 < climb < 50.0:        # o salto de volta ao início não conta
                self.state.ascent_m += climb

    def _complete_loop(self) -> None:
        """Fecha uma volta completa à rota (req. novo: a sessão não termina)."""
        loop_time = self._t - self._loop_start_t
        self.state.loops += 1
        self.route_finished = True
        if self._best_loop_s is None or loop_time < self._best_loop_s:
            self._best_loop_s = loop_time
        self._loop_start_t = self._t
        # as subidas voltam a contar do princípio
        if self._active is not None:
            self._close_section()
        self._next_climb = 0
        if self.strava is not None:
            self.strava.reset()
        self.trace = []                    # o traço recomeça com a volta à rota
        self._emit("route_loop", loops=self.state.loops, loop_time_s=loop_time,
                   best_loop_s=self._best_loop_s)
        self.lap("route_loop")

    def _command_trainer(self) -> None:
        if self.trainer is None:
            return
        erg = (self.workout is not None and self.workout.erg_enabled) or (
            self.game is not None and self.game.erg and not self.game.finished)
        try:
            if erg and self.state.target_power_w is not None:
                if self.state.target_power_w != self._last_target_sent:
                    self.trainer.set_target_power(int(self.state.target_power_w))
                    self._last_target_sent = int(self.state.target_power_w)
                self.state.resistance_sent = None
            else:
                g = physics.trainer_grade(self.state.grade_pct, self.difficulty,
                                          self.extra_resistance)
                if (self._last_grade_sent is None
                        or abs(g - self._last_grade_sent) > TRAINER_GRADE_EPSILON):
                    self.trainer.set_sim(g, self.athlete.crr, self.athlete.cda)
                    self._last_grade_sent = g
                self.state.resistance_sent = g
        except Exception as e:                       # o trainer caiu a meio
            self._emit("trainer_error", message=str(e))

    # ------------------------------------------------------------- amostras

    def _take_sample(self) -> None:
        r = self._reading
        t = int(self._t)

        if r.power_w is not None:
            self._power_window.append(r.power_w)
            if len(self._power_window) > 3:
                self._power_window.pop(0)
            self.state.power_3s = int(sum(self._power_window) / len(self._power_window))
            self._power_sum += r.power_w
            self._power_n += 1
            self._max_power = max(self._max_power, r.power_w)
        self._power_series.append(float(r.power_w or 0))

        if r.hr_bpm is not None:
            self._hr_sum += r.hr_bpm
            self._hr_n += 1
            self._max_hr = max(self._max_hr, r.hr_bpm)
        if r.cadence_rpm is not None:
            self._cad_sum += r.cadence_rpm
            self._cad_n += 1
        if r.balance_left is not None:
            self._bal_sum += r.balance_left
            self._bal_n += 1
            self._balance_window.append(r.balance_left)
            if len(self._balance_window) > 3:
                self._balance_window.pop(0)
        elif self._balance_window:
            self._balance_window.pop(0)          # sensor calado: deixa de mostrar
        self.state.balance_3s = (sum(self._balance_window) / len(self._balance_window)
                                 if self._balance_window else None)
        pedal = {k: getattr(r, k, None) for k in PEDAL_FIELDS}
        for k, v in pedal.items():
            if v is not None:
                self._pedal_sum[k] += v
                self._pedal_n[k] += 1
        self.state.pedal = pedal
        self.state.avg_pedal = self._pedal_avgs()
        self.state.avg_balance = self._bal_sum / self._bal_n if self._bal_n else None
        self._speed_sum += self.state.speed_mps
        self._speed_n += 1

        self.state.avg_power = self._power_sum / self._power_n if self._power_n else None
        self.state.avg_hr = self._hr_sum / self._hr_n if self._hr_n else None
        self.state.avg_cadence = self._cad_sum / self._cad_n if self._cad_n else None
        self.state.avg_speed = self._speed_sum / self._speed_n if self._speed_n else None
        self.state.np_w = physics.normalized_power(self._power_series)
        self.state.tss = physics.training_stress_score(
            self.state.np_w, self.athlete.ftp_w, int(self._moving_s)) or 0.0

        nm = physics.torque_nm(r.power_w, r.cadence_rpm)
        if nm is not None:
            self._torque_sum += nm
            self._torque_n += 1
            self.state.avg_torque = self._torque_sum / self._torque_n
        if r.power_w is not None:
            z = physics.zone_of(r.power_w, self.state.power_zone_bounds, self.athlete.ftp_w)
            self.state.power_zone_s[min(z, len(self.state.power_zone_s)) - 1] += \
                SAMPLE_INTERVAL_S
        if r.hr_bpm is not None and self.state.lthr:
            z = physics.zone_of(r.hr_bpm, self.state.hr_zone_bounds, self.state.lthr)
            self.state.hr_zone_s[min(z, len(self.state.hr_zone_s)) - 1] += SAMPLE_INTERVAL_S
        self.trace.append((self.state.pos_m, self.state.power_3s, r.hr_bpm))

        sample = Sample(
            t_s=t, dist_m=self.state.dist_m, speed_mps=self.state.speed_mps,
            power_w=r.power_w, cadence_rpm=r.cadence_rpm, hr_bpm=r.hr_bpm,
            balance_left=r.balance_left,
            torque_nm=physics.torque_nm(r.power_w, r.cadence_rpm),
            grade_pct=self.state.grade_pct, ele_m=self.state.ele_m,
            target_power_w=self.state.target_power_w,
            resistance_sent=self.state.resistance_sent, lap_no=self.lap_no,
            **pedal,
        )
        self._pending.append(sample)
        _lap_observe(self._lap_acc, sample)
        if self._active is not None:
            self._active.observe(r)
        if self.chase is not None:
            self.chase.observe_power(r.power_w)
        if self.workout is not None:
            if not self._workout_done and self._t >= self.workout.total_s:
                self._workout_done = True
                self._emit("workout_done")
            changed = self.workout.observe(self._t, r.power_w, r.hr_bpm, r.cadence_rpm)
            if changed is not None:
                step = self.workout.workout.steps[changed]
                self._emit("workout_step", idx=changed, total=len(self.workout.workout.steps),
                           cue=step.text_cue, target=self.state.target_power_w)

        if self.game is not None and not self.game.finished:
            for kind, data in self.game.tick(SAMPLE_INTERVAL_S, r.power_w):
                self._emit(kind, **data)
            self.state.target_power_w = self.game.target_w
            if self.game.finished:
                self._save_game()

        self._bump_challenges()

        if len(self._pending) >= FLUSH_EVERY:
            self.flush()

    def flush(self) -> None:
        """Grava as amostras pendentes e, com elas, o ponto de recuperação:
        os dois ficam sempre de acordo um com o outro."""
        if self._pending:
            self.db.append_samples(self.ride_id, self._pending)
            self._pending.clear()
        if not self.finished and self.started:
            self.checkpoint()

    # -------------------------------------------------------- recuperação

    def checkpoint(self) -> None:
        """Guarda o que não se consegue reconstruir a partir das amostras."""
        try:
            self.db.save_checkpoint(self.ride_id, "cycling", self._config(), self._snapshot())
        except Exception:
            pass                     # nunca deixar a gravação parar a sessão

    def _config(self) -> dict:
        return {"route_id": self.route_id, "workout_id": self.workout_id,
                "kind": self.kind, "chase_level": self.chase_level,
                "start_unix": self.start_unix, "meta": self.meta}

    def _snapshot(self) -> dict:
        st = self.state
        chase = None
        if self.chase is not None:
            chase = {k: v for k, v in vars(self.chase).items()
                     if isinstance(v, (int, float, bool)) and not k.startswith("__")}
        return {
            "t": self._t, "moving_s": self._moving_s, "paused_s": self._paused_s,
            "dist_m": st.dist_m, "pos_m": st.pos_m, "loops": st.loops,
            "ascent_m": st.ascent_m, "joules": st.joules, "speed_mps": st.speed_mps,
            "ele_m": st.ele_m, "lap_no": self.lap_no, "lap_start_t": self._lap_start_t,
            "lap_start_dist": self._lap_start_dist, "lap_start_ele": self._lap_start_ele,
            "loop_start_t": self._loop_start_t, "best_loop_s": self._best_loop_s,
            "route_finished": self.route_finished, "workout_done": self._workout_done,
            "difficulty": self.difficulty, "intensity": st.intensity,
            "last_sample_ele": self._last_sample_ele, "chase": chase,
            "chase_result": self.chase_result,
            "game": self.game.snapshot() if self.game is not None else None,
        }

    def _restore(self, snap: dict) -> None:
        """Volta a montar o estado: os escalares vêm do ponto de recuperação,
        as médias, zonas e voltas reconstroem-se a partir do que está gravado."""
        st = self.state
        self._t = float(snap.get("t", 0.0))
        self._moving_s = float(snap.get("moving_s", 0.0))
        self._paused_s = float(snap.get("paused_s", 0.0))
        st.paused_s = self._paused_s
        st.dist_m = float(snap.get("dist_m", 0.0))
        st.pos_m = float(snap.get("pos_m", 0.0))
        st.loops = int(snap.get("loops", 0))
        st.ascent_m = float(snap.get("ascent_m", 0.0))
        st.joules = float(snap.get("joules", 0.0))
        st.speed_mps = 0.0
        self.lap_no = int(snap.get("lap_no", 1))
        self._lap_start_t = float(snap.get("lap_start_t", 0.0))
        self._lap_start_dist = float(snap.get("lap_start_dist", 0.0))
        self._lap_start_ele = float(snap.get("lap_start_ele", st.ele_m))
        self._loop_start_t = float(snap.get("loop_start_t", 0.0))
        self._best_loop_s = snap.get("best_loop_s")
        self.route_finished = bool(snap.get("route_finished", False))
        self._workout_done = bool(snap.get("workout_done", False))
        self.difficulty = float(snap.get("difficulty", self.difficulty))
        st.difficulty = self.difficulty
        st.intensity = float(snap.get("intensity", 1.0))
        if self.workout is not None:
            self.workout.intensity = st.intensity
        if self.route is not None:
            st.ele_m = self.route.ele_at(st.pos_m)
            st.grade_pct = self.route.grade_at(st.pos_m)
        else:
            st.ele_m = float(snap.get("ele_m", 0.0))
        self._last_sample_ele = float(snap.get("last_sample_ele", st.ele_m))

        # subidas: a que estava a meio quando a aplicação caiu já não conta
        self._next_climb = 0
        for i, c in enumerate(self.climbs):
            if c.start_m <= st.pos_m:
                self._next_climb = i + 1
        self.climb_results = [
            {"name": r["name"], "category": r["category"], "elapsed_s": r["elapsed_s"],
             "avg_power_w": r["avg_power_w"], "avg_hr": r["avg_hr"],
             "avg_cadence": r["avg_cadence"], "avg_balance_left": r["avg_balance_left"],
             "rank": 0, "total": 0, "is_pr": False, "vam_mh": r["vam_mh"]}
            for r in self.db.conn.execute(
                "SELECT ce.*, c.name, c.category FROM climb_efforts ce"
                " JOIN climbs c ON c.id = ce.climb_id WHERE ce.ride_id = ?"
                " ORDER BY ce.start_t_s", (self.ride_id,))]

        # voltas já fechadas
        self.laps = []
        for r in self.db.laps(self.ride_id):
            keys = r.keys()
            self.laps.append(Lap(
                lap_no=r["lap_no"], trigger=r["trigger"], start_t_s=r["start_t_s"],
                end_t_s=r["end_t_s"], start_dist_m=r["start_dist_m"],
                end_dist_m=r["end_dist_m"], avg_power_w=r["avg_power_w"], np_w=r["np_w"],
                max_power_w=r["max_power_w"], avg_hr=r["avg_hr"], max_hr=r["max_hr"],
                avg_cadence=r["avg_cadence"], avg_speed_mps=r["avg_speed_mps"],
                ascent_m=r["ascent_m"] or 0.0, avg_balance_left=r["avg_balance_left"],
                pedal={k: r[f"avg_{k}"] for k in PEDAL_FIELDS if f"avg_{k}" in keys}))

        # médias, zonas, curva e volta em curso: repetir as amostras gravadas
        loop_dist0 = st.dist_m - st.pos_m
        for smp in self.db.samples(self.ride_id):
            self._replay(smp, loop_dist0)
        self.state.t_s = self._t
        st.np_w = physics.normalized_power(self._power_series)
        st.tss = physics.training_stress_score(st.np_w, self.athlete.ftp_w,
                                               int(self._moving_s)) or 0.0
        if self.workout is not None:
            self.workout.current_idx = -1

        # fuga: retoma onde estava, mas fica fora da classificação
        chase = snap.get("chase")
        if self.chase is not None and chase:
            for k, v in chase.items():
                if hasattr(self.chase, k):
                    setattr(self.chase, k, v)
            if self.chase.active and self.chase.clean:
                self.chase.clean = False
                self._emit("chase_unranked")
        self.chase_result = snap.get("chase_result")
        if self.game is not None and snap.get("game"):
            self.game.restore(snap["game"])     # retoma o jogo; fica fora do recorde

        # arranca já em pausa: volta a contar à primeira pedalada
        self.started = True
        self.auto_pause = True
        self._idle_s = AUTO_PAUSE_AFTER_S
        self.state.status = AUTO_PAUSED
        self._emit("recovered", t_s=self._t, dist_m=st.dist_m)

    def _replay(self, s: Sample, loop_dist0: float) -> None:
        """Uma amostra gravada passa pelos mesmos acumuladores que ao vivo."""
        st = self.state
        if s.power_w is not None:
            self._power_window.append(s.power_w)
            if len(self._power_window) > 3:
                self._power_window.pop(0)
            st.power_3s = int(sum(self._power_window) / len(self._power_window))
            self._power_sum += s.power_w
            self._power_n += 1
            self._max_power = max(self._max_power, s.power_w)
            z = physics.zone_of(s.power_w, st.power_zone_bounds, self.athlete.ftp_w)
            st.power_zone_s[min(z, len(st.power_zone_s)) - 1] += SAMPLE_INTERVAL_S
        self._power_series.append(float(s.power_w or 0))
        if s.hr_bpm is not None:
            self._hr_sum += s.hr_bpm
            self._hr_n += 1
            self._max_hr = max(self._max_hr, s.hr_bpm)
            if st.lthr:
                z = physics.zone_of(s.hr_bpm, st.hr_zone_bounds, st.lthr)
                st.hr_zone_s[min(z, len(st.hr_zone_s)) - 1] += SAMPLE_INTERVAL_S
        if s.cadence_rpm is not None:
            self._cad_sum += s.cadence_rpm
            self._cad_n += 1
        if s.balance_left is not None:
            self._bal_sum += s.balance_left
            self._bal_n += 1
        for k in PEDAL_FIELDS:
            v = getattr(s, k, None)
            if v is not None:
                self._pedal_sum[k] += v
                self._pedal_n[k] += 1
        self._speed_sum += s.speed_mps or 0.0
        self._speed_n += 1
        nm = physics.torque_nm(s.power_w, s.cadence_rpm)
        if nm is not None:
            self._torque_sum += nm
            self._torque_n += 1
            st.avg_torque = self._torque_sum / self._torque_n
        if s.lap_no == self.lap_no:
            _lap_observe(self._lap_acc, s)
        pos = s.dist_m - loop_dist0
        if pos >= 0:
            self.trace.append((pos, st.power_3s, s.hr_bpm))
        if self.workout is not None:
            self.workout.observe(float(s.t_s), s.power_w, s.hr_bpm, s.cadence_rpm)
        st.avg_power = self._power_sum / self._power_n if self._power_n else None
        st.avg_hr = self._hr_sum / self._hr_n if self._hr_n else None
        st.avg_cadence = self._cad_sum / self._cad_n if self._cad_n else None
        st.avg_speed = self._speed_sum / self._speed_n if self._speed_n else None
        st.avg_balance = self._bal_sum / self._bal_n if self._bal_n else None
        st.avg_pedal = self._pedal_avgs()

    # ----------------------------------------------------------- desafios

    def _bump_challenges(self) -> None:
        """Soma o progresso do último segundo a cada desafio activo (req. 20)."""
        if not self._attempts:
            return
        d_dist = self.state.speed_mps * SAMPLE_INTERVAL_S
        # A elevação anterior é guardada à parte: ler do buffer de amostras
        # perderia o incremento sempre que o buffer acabou de ser descarregado.
        d_asc = max(0.0, self.state.ele_m - self._last_sample_ele)
        self._last_sample_ele = self.state.ele_m
        still: list[tuple[int, int, str, float]] = []
        for attempt_id, ch_id, metric, target in self._attempts:
            add = {"distance_m": d_dist, "ascent_m": d_asc,
                   "time_s": SAMPLE_INTERVAL_S, "rides": 0.0}.get(metric, 0.0)
            if add <= 0:
                still.append((attempt_id, ch_id, metric, target))
                continue
            if self.db.bump_attempt(attempt_id, add, target, self.ride_id):
                self._emit("challenge_done", challenge_id=ch_id,
                           name=self._challenge_names.get(ch_id, ""))
            else:
                still.append((attempt_id, ch_id, metric, target))
        self._attempts = still

    # ------------------------------------------------------------- voltas

    def lap(self, trigger: str = "manual") -> Lap:
        """Fecha a volta atual e abre outra. Ligado à tecla L (req. 13)."""
        lap = _lap_finish(self._lap_acc, self.lap_no, trigger, self._lap_start_t,
                          self._t, self._lap_start_dist, self.state.dist_m,
                          max(0.0, self.state.ele_m - self._lap_start_ele))
        self.db.save_lap(self.ride_id, lap)
        self.laps.append(lap)
        zone = (physics.zone_of(lap.avg_power_w, self.state.power_zone_bounds,
                                self.athlete.ftp_w) if lap.avg_power_w else None)
        self._emit("lap", lap_no=lap.lap_no, trigger=trigger,
                   elapsed_s=lap.end_t_s - lap.start_t_s,
                   distance_m=lap.end_dist_m - lap.start_dist_m,
                   avg_power_w=lap.avg_power_w, avg_power_zone=zone,
                   avg_cadence=lap.avg_cadence, avg_hr=lap.avg_hr,
                   max_power_w=lap.max_power_w, ascent_m=lap.ascent_m)
        self.lap_no += 1
        self._lap_start_t = self._t
        self._lap_start_dist = self.state.dist_m
        self._lap_start_ele = self.state.ele_m
        self._lap_acc = _lap_accumulator()
        if not self.finished and trigger != "end":
            # a volta fechada já está na base: as amostras pendentes e o ponto
            # de recuperação acompanham, para o número da volta bater certo
            self.flush()
        return lap

    # ------------------------------------------------------------- subidas

    def _track_sections(self) -> None:
        """Abre e fecha subidas, e dispara as placas pelo caminho (req. 14)."""
        d = self.state.pos_m

        if self._active is None and self._next_climb < len(self.climbs):
            nxt = self.climbs[self._next_climb]
            if d >= nxt.start_m:
                self._active = _SectionTimer(nxt)
                self._active.start_t = self._t
                self._active.pending_signs = signs_for(nxt, SIGN_EVERY_M)
                self._emit("section_start", name=nxt.name, category=nxt.category,
                           length_m=nxt.length_m, gain_m=nxt.gain_m,
                           avg_grade_pct=nxt.avg_grade_pct,
                           start_m=nxt.start_m, end_m=nxt.end_m,
                           max_grade_pct=nxt.max_grade_pct)

        if self._active is not None:
            while self._active.pending_signs and d >= self._active.pending_signs[0]:
                self._active.pending_signs.pop(0)
                self._emit("section_sign", name=self._active.climb.name,
                           left_m=max(0.0, self._active.climb.end_m - d))
            if d >= self._active.climb.end_m:
                self._close_section()

    def _close_section(self) -> None:
        a = self._active
        if a is None:
            return
        self._active = None
        self._next_climb += 1
        elapsed = int(self._t - a.start_t)
        rank = total = 0
        is_pr = False
        if a.climb.id is not None:
            rank, total, is_pr = self.db.save_climb_effort(
                a.climb.id, self.ride_id, int(a.start_t), int(self._t),
                a.avg_power, a.avg_hr, a.avg_cadence, a.climb.gain_m,
                avg_balance=a.avg_balance)
        result = {
            "name": a.climb.name, "category": a.climb.category, "elapsed_s": elapsed,
            "avg_power_w": a.avg_power, "avg_hr": a.avg_hr,
            "avg_cadence": a.avg_cadence, "avg_balance_left": a.avg_balance,
            "rank": rank, "total": total, "is_pr": is_pr,
            "vam_mh": (a.climb.gain_m / elapsed * 3600.0) if elapsed > 0 else 0.0,
        }
        self.climb_results.append(result)
        self._emit("section_finish", **result)
        self.lap("climb")

    # ------------------------------------------------------ segmentos Strava

    def _track_strava(self) -> None:
        if self.strava is None:
            return
        from . import segments as _segments
        for kind, data in self.strava.observe(self.state.pos_m, self._t):
            if kind == "strava_end":
                elapsed = int(data["elapsed_s"])
                prev = data.get("local_best_s")
                data["local_pr"] = prev is None or elapsed < prev
                try:
                    _segments.save_effort(self.db, self.ride_id, data["id"], elapsed)
                except Exception:
                    pass
                self.strava_results.append(dict(data))
            self._emit(kind, **data)

    def active_segment(self) -> dict | None:
        if self.strava is None:
            return None
        return self.strava.current(self.state.pos_m, self._t)

    # ----------------------------------------------------------- fantasmas

    def _track_ghosts(self) -> None:
        # Em voltas seguintes o fantasma recomeça do princípio: compara-se o
        # tempo dentro da volta atual com o dele na mesma posição.
        mine = self._t - self._loop_start_t
        for g in self.ghosts:
            their_t = g.time_at(self.state.pos_m)
            if their_t is None:
                continue
            self._emit_ghost(g, mine - their_t)

    def _emit_ghost(self, g: Ghost, delta_s: float) -> None:
        # substitui o evento anterior do mesmo fantasma em vez de acumular
        for e in self.events:
            if e.kind == "ghost" and e.data.get("ride_id") == g.ride_id:
                e.data["delta_s"] = delta_s
                return
        self._emit("ghost", ride_id=g.ride_id, label=g.label, delta_s=delta_s,
                   dist_m=g.dist_at(self._t - self._loop_start_t))

    def ghost_positions(self) -> list[tuple[str, float, float]]:
        """(etiqueta, distância do fantasma, diferença em segundos) para desenhar."""
        out = []
        mine = self._t - self._loop_start_t
        for g in self.ghosts:
            their_t = g.time_at(self.state.pos_m)
            delta = (mine - their_t) if their_t is not None else 0.0
            out.append((g.label, g.dist_at(mine), delta))
        return out

    # ---------------------------------------------------------------- fim

    def _activity_file(self) -> tuple[Path, str]:
        """perennia_<data>_<ficheiro .gpx>, sem pisar uma sessão do mesmo dia."""
        source = route_name = workout_name = None
        if self.route_id:
            row = self.db.route(self.route_id)
            if row is not None:
                source, route_name = row["source_filename"], row["name"]
        if self.workout is not None:
            workout_name = self.workout.workout.name
        elif self.game is not None:
            workout_name = self.game.title
        base = naming.activity_name(self.start_unix, source_filename=source,
                                    route_name=route_name, kind=self.kind,
                                    workout_name=workout_name)
        self.rides_dir.mkdir(parents=True, exist_ok=True)
        return naming.unique_path(self.rides_dir, base)

    def _pedal_avgs(self) -> dict:
        return {k: (self._pedal_sum[k] / self._pedal_n[k] if self._pedal_n[k] else None)
                for k in PEDAL_FIELDS}

    def _save_chase(self, caught: bool, lap: bool = True) -> None:
        ch = self.chase
        if ch is None or ch.saved:
            return
        ch.saved = True
        rank, total, is_pr = self.db.save_chase_effort(
            self.ride_id, self.route_id, ch.level.id, ch.t_s, ch.distance_m,
            ch.avg_power_w, ch.watts, caught, ch.clean)
        self.chase_result = {
            "level": ch.level.id, "survived_s": ch.t_s, "distance_m": ch.distance_m,
            "avg_power_w": ch.avg_power_w, "final_chaser_w": ch.watts,
            "caught": caught, "clean": ch.clean, "rank": rank, "total": total,
            "is_pr": is_pr,
        }
        self._emit("chase_saved", **self.chase_result)
        if lap:
            self.lap("chase")

    def pause(self, confirming: bool = False) -> None:
        """Pausa manual. Só sai com `resume()` — pedalar não a desfaz.

        `confirming`: a pausa enquanto se pergunta «tem a certeza?» ao
        terminar. Não tira a fuga da classificação.
        """
        if self.manual_pause:
            return
        self.manual_pause = True
        self.state.status = PAUSED
        if (not confirming and self.chase is not None and self.chase.active
                and self.chase.clean):
            self.chase.clean = False
            self._emit("chase_unranked")
        if self.trainer is not None:
            try:
                self.trainer.set_sim(0.0, self.athlete.crr, self.athlete.cda)
            except Exception:
                pass

    def resume(self) -> None:
        self.manual_pause = False
        self._idle_s = 0.0
        self._last_target_sent = None
        self._last_grade_sent = None

    def resume_on_pedal(self) -> None:
        """Respondeu «não» a terminar: fica em pausa, e pedalar retoma."""
        self.manual_pause = False
        self.auto_pause = True
        self.state.status = AUTO_PAUSED
        self._idle_s = AUTO_PAUSE_AFTER_S
        self._last_target_sent = None
        self._last_grade_sent = None

    # ------------------------------------------------------ resistência a meio

    DIFFICULTY_STEP = 0.1
    INTENSITY_STEP = 0.05

    def adjust_resistance(self, steps: int) -> str:
        """+/− a meio da sessão. Em ERG muda a intensidade do treino (±5 %);
        em simulação muda a sensação de declive (±10 %). Devolve o modo."""
        erg = self.workout is not None and self.workout.erg_enabled
        if erg:
            self.state.intensity = round(max(0.5, min(1.5, self.state.intensity
                                                      + steps * self.INTENSITY_STEP)), 2)
            self.workout.intensity = self.state.intensity
            self._last_target_sent = None
            self._emit("resistance", mode="erg", value=self.state.intensity)
            return "erg"
        self.difficulty = round(max(0.0, min(1.5, self.difficulty
                                              + steps * self.DIFFICULTY_STEP)), 2)
        self.state.difficulty = self.difficulty
        self._last_grade_sent = None
        self._emit("resistance", mode="sim", value=self.difficulty)
        return "sim"

    def current_lap(self) -> dict:
        """A volta em curso, ao vivo: o que o painel das voltas mostra."""
        acc = self._lap_acc
        avg_p = acc["p_sum"] / acc["p_n"] if acc["p_n"] else None
        return {
            "lap_no": self.lap_no,
            "elapsed_s": self._t - self._lap_start_t,
            "distance_m": self.state.dist_m - self._lap_start_dist,
            "avg_power_w": avg_p,
            "avg_power_zone": (physics.zone_of(avg_p, self.state.power_zone_bounds,
                                               self.athlete.ftp_w) if avg_p else None),
            "avg_cadence": acc["cad_sum"] / acc["cad_n"] if acc["cad_n"] else None,
            "avg_hr": acc["hr_sum"] / acc["hr_n"] if acc["hr_n"] else None,
        }

    def summary(self) -> RideSummary:
        np_w = physics.normalized_power(self._power_series)
        moving = int(self._moving_s) or int(self._t)
        return RideSummary(
            elapsed_s=int(self._t), moving_s=moving,
            distance_m=self.state.dist_m, ascent_m=self.state.ascent_m,
            avg_power_w=self._power_sum / self._power_n if self._power_n else None,
            max_power_w=self._max_power or None, np_w=np_w,
            intensity_factor=(np_w / self.athlete.ftp_w) if np_w else None,
            tss=physics.training_stress_score(np_w, self.athlete.ftp_w, moving),
            work_kj=self.state.joules / 1000.0,
            avg_hr=self._hr_sum / self._hr_n if self._hr_n else None,
            max_hr=self._max_hr or None,
            avg_cadence=self._cad_sum / self._cad_n if self._cad_n else None,
            avg_speed_mps=self._speed_sum / self._speed_n if self._speed_n else 0.0,
            avg_balance_left=self._bal_sum / self._bal_n if self._bal_n else None,
            completed_route=self.route_finished,
            route_loops=self.state.loops,
            best_loop_s=int(self._best_loop_s) if self._best_loop_s else None,
            paused_s=int(self._paused_s),
            pedal=self._pedal_avgs(),
            power_curve=physics.power_curve(self._power_series),
        )

    def finish(self) -> dict[str, Any]:
        """Fecha a sessão: volta final, FIT, sumário e base de dados."""
        if self.finished:
            return {}
        if self._active is not None:
            self._close_section()
        if self.chase is not None and self.chase.active and self.started:
            # terminou antes de ser apanhado: a fuga conta até aqui
            self.chase.stop()
            self._save_chase(caught=False, lap=False)
        if self.game is not None and self.started and not self.game.saved:
            self.game.end()                      # terminou antes do fim do jogo
            self.game.saved = False
            from . import games
            self.game_result = games.save_result(self.db, self.ride_id, self.game,
                                                 ranked=not self.recovered)
        self.lap("end")
        self.flush()
        self.finished = True

        if self.trainer is not None:
            try:
                self.trainer.set_sim(0.0, self.athlete.crr, self.athlete.cda)
                self.trainer.release_control()
            except Exception:
                pass

        summary = self.summary()
        samples = self.db.samples(self.ride_id)
        fit_path, self.name = self._activity_file()
        coord_at = None
        if self.route is not None and self.include_coords:
            def coord_at(m: float):                       # noqa: E306
                p = self.route.point_at(m % self.route.total_m)
                return p.lat, p.lon, p.ele_m
        try:
            fit.write_activity(fit_path, self.athlete, samples, self.laps, summary,
                               start_unix=self.start_unix,
                               include_coords=self.include_coords, coord_at=coord_at,
                               name=self.name, virtual=True)
            fit_written: str | None = str(fit_path)
        except Exception as e:
            self._emit("fit_error", message=str(e))
            fit_written = None

        self.db.finish_ride(self.ride_id, summary, fit_written,
                            ghosts=[g.ride_id for g in self.ghosts])
        self.db.delete_checkpoint(self.ride_id)
        self.db.set_ride_name(self.ride_id, self.name)
        if self.workout is not None:
            self.db.save_step_results(self.ride_id, self.workout.results())

        return {
            "ride_id": self.ride_id, "name": self.name, "summary": summary,
            "fit_path": fit_written,
            "laps": self.laps, "climbs": self.climb_results,
            "strava": self.strava_results,
            "power_series": self._power_series, "chase": self.chase_result,
            "kind": self.kind, "route_id": self.route_id,
            "workout_id": self.workout_id, "game": self.game_result,
        }

    @property
    def lap_elapsed_s(self) -> float:
        return max(0.0, self._t - self._lap_start_t)

    def discard(self) -> None:
        """«Terminar sem guardar»: a sessão desaparece (nada de .fit nem estatísticas)."""
        self.abort()
        try:
            self.db.conn.execute("DELETE FROM rides WHERE id = ?", (self.ride_id,))
            self.db.conn.commit()
        except Exception:
            pass

    def abort(self) -> None:
        self.flush()
        self.finished = True
        if self.trainer is not None:
            try:
                self.trainer.set_sim(0.0, self.athlete.crr, self.athlete.cda)
                self.trainer.release_control()
            except Exception:
                pass
        self.db.abort_ride(self.ride_id)
        self.db.delete_checkpoint(self.ride_id)

    def suspend(self) -> None:
        """A aplicação vai fechar sem terminar a sessão (erro inesperado): grava
        tudo o que tem e deixa a sessão por terminar, para se retomar depois."""
        if self.finished:
            return
        try:
            self.flush()
            if self.started:
                self.checkpoint()
        except Exception:
            pass


# ------------------------------------------------------- acumuladores de volta


def _lap_accumulator() -> dict:
    return {"p_sum": 0.0, "p_n": 0, "p_max": 0, "hr_sum": 0.0, "hr_n": 0, "hr_max": 0,
            "cad_sum": 0.0, "cad_n": 0, "sp_sum": 0.0, "sp_n": 0, "bal_sum": 0.0,
            "bal_n": 0, "series": [],
            "pedal": {k: [0.0, 0] for k in PEDAL_FIELDS}}


def _lap_observe(acc: dict, s: Sample) -> None:
    if s.power_w is not None:
        acc["p_sum"] += s.power_w
        acc["p_n"] += 1
        acc["p_max"] = max(acc["p_max"], s.power_w)
    acc["series"].append(float(s.power_w or 0))
    if s.hr_bpm is not None:
        acc["hr_sum"] += s.hr_bpm
        acc["hr_n"] += 1
        acc["hr_max"] = max(acc["hr_max"], s.hr_bpm)
    if s.cadence_rpm is not None:
        acc["cad_sum"] += s.cadence_rpm
        acc["cad_n"] += 1
    acc["sp_sum"] += s.speed_mps or 0.0
    acc["sp_n"] += 1
    if s.balance_left is not None:
        acc["bal_sum"] += s.balance_left
        acc["bal_n"] += 1
    for k in PEDAL_FIELDS:
        v = getattr(s, k, None)
        if v is not None:
            acc["pedal"][k][0] += v
            acc["pedal"][k][1] += 1


def _lap_finish(acc: dict, lap_no: int, trigger: str, t0: float, t1: float,
                d0: float, d1: float, ascent: float) -> Lap:
    return Lap(
        lap_no=lap_no, trigger=trigger, start_t_s=int(t0), end_t_s=int(t1),
        start_dist_m=d0, end_dist_m=d1,
        avg_power_w=acc["p_sum"] / acc["p_n"] if acc["p_n"] else None,
        np_w=physics.normalized_power(acc["series"]),
        max_power_w=acc["p_max"] or None,
        avg_hr=acc["hr_sum"] / acc["hr_n"] if acc["hr_n"] else None,
        max_hr=acc["hr_max"] or None,
        avg_cadence=acc["cad_sum"] / acc["cad_n"] if acc["cad_n"] else None,
        avg_speed_mps=acc["sp_sum"] / acc["sp_n"] if acc["sp_n"] else None,
        ascent_m=ascent,
        avg_balance_left=acc["bal_sum"] / acc["bal_n"] if acc["bal_n"] else None,
        pedal={k: (tot / n if n else None) for k, (tot, n) in acc["pedal"].items()},
    )


def load_ghosts(db: Database, ride_ids: Sequence[str]) -> list[Ghost]:
    out = []
    for rid in ride_ids:
        row = db.conn.execute("SELECT started_at, elapsed_s FROM rides WHERE id = ?",
                              (rid,)).fetchone()
        samples = db.samples(rid)
        if not samples:
            continue
        label = (row["started_at"][:10] if row else rid[:8])
        out.append(Ghost(rid, label, samples))
    return out
