"""O separador «Treinar» de cada desporto, sempre pela mesma ordem —
Sessão de treino · Challenge · Desafios (e depois os Testes) — e o modo
Challenge da corrida, da natação e do ginásio.

O Challenge do ciclismo (fuga, desafio adaptativo, jogos) e o do remo
(Regata e jogos) já existiam; aqui juntam-se:

* corrida e natação: provas contra o relógio («5 km contra o relógio»,
  «30 min: o mais longe possível», escadas de ritmo), com a tua tabela de
  melhores resultados em cada uma;
* ginásio: treino surpresa de cada modalidade e formatos de Conditioning
  (EMOM, Tabata, pirâmide), que correm na sessão por voltas.
"""
from __future__ import annotations

from velo.core import boards
from velo.core import endurance as en
from velo.core import sports as sp
from velo.core.i18n import t, tr
from velo.core.units import hms
from velo.ui.app import ChallengeScreen, Screen
from velo.ui.widgets import Item

S = en.Step
# (chave, nome PT, nome EN, descrição PT, descrição EN, passos, mede)
# «mede»: "time" — ganha o menor tempo; "distance" — ganha a maior distância
ENDURANCE_CHALLENGES = {
    "running": (
        ("run_5k", "5 km contra o relógio", "5 km time trial",
         "5 km no máximo. A tabela guarda os teus melhores tempos.",
         "5 km all out. The table keeps your best times.",
         [S("active", "distance", 5000, None, None, "5 km no máximo")], "time"),
        ("run_10k", "10 km contra o relógio", "10 km time trial",
         "10 km a ritmo de prova.", "10 km at race pace.",
         [S("active", "distance", 10000, None, None, "10 km a ritmo de prova")], "time"),
        ("run_hour", "1 hora: o mais longe possível", "1 hour: as far as you can",
         "60 minutos; conta a distância.", "60 minutes; distance counts.",
         [S("active", "time", 3600, None, None, "O mais longe possível")], "distance"),
        ("run_ladder", "Escada de ritmo", "Pace ladder",
         "7 × 1 km, cada um mais rápido (80 % → 110 % do limiar).",
         "7 × 1 km, each faster (80 % → 110 % of threshold).",
         [S("active", "distance", 1000, p, p + 2, f"Degrau {i + 1}")
          for i, p in enumerate(range(80, 111, 5))], "time"),
    ),
    "swimming": (
        ("swim_400", "400 m contra o relógio", "400 m time trial",
         "400 m no máximo, ritmo constante.", "400 m all out, even pace.",
         [S("active", "distance", 400, None, None, "400 m no máximo")], "time"),
        ("swim_1500", "1500 m contra o relógio", "1500 m time trial",
         "1500 m sem parar.", "1500 m non-stop.",
         [S("active", "distance", 1500, None, None, "1500 m sem parar")], "time"),
        ("swim_30min", "30 min: o mais longe possível", "30 min: as far as you can",
         "30 minutos sem parar; conta a distância.", "30 minutes non-stop; distance counts.",
         [S("active", "time", 1800, None, None, "O mais longe possível")], "distance"),
        ("swim_pyramid", "Pirâmide 100-200-300-200-100", "Pyramid 100-200-300-200-100",
         "900 m em pirâmide, 20 s de descanso entre séries.",
         "900 m pyramid, 20 s rest between sets.",
         [x for i, d in enumerate((100, 200, 300, 200, 100))
          for x in ((S("active", "distance", d, 92, 96, f"{d} m"),) +
                    ((S("rest", "time", 20, 40, 45, "Descanso"),) if i < 4 else ()))], "time"),
    ),
}

# formatos de Conditioning (voltas da sessão por voltas)
GYM_FORMATS = (
    ("emom20", "EMOM 20 min", "EMOM 20 min",
     "20 minutos: 40 s a trabalhar e 20 s a descansar, em cada minuto.",
     "20 minutes: 40 s work and 20 s rest every minute.",
     [x for _ in range(20) for x in ({"kind": "cardio", "seconds": 40},
                                     {"kind": "rest", "seconds": 20})]),
    ("tabata", "Tabata × 3", "Tabata × 3",
     "3 blocos de 8 × (20 s a fundo + 10 s), 1 min entre blocos.",
     "3 blocks of 8 × (20 s all out + 10 s), 1 min between blocks.",
     [x for b in range(3) for x in (
         [y for _ in range(8) for y in ({"kind": "cardio", "seconds": 20},
                                        {"kind": "rest", "seconds": 10})]
         + ([{"kind": "rest", "seconds": 60}] if b < 2 else []))]),
    ("tread_pyramid", "Pirâmide na passadeira", "Treadmill pyramid",
     "1-2-3-4-3-2-1 min forte na passadeira, 1 min de descanso entre cada.",
     "1-2-3-4-3-2-1 min hard on the treadmill, 1 min rest in between.",
     [x for i, m in enumerate((1, 2, 3, 4, 3, 2, 1))
      for x in ([{"kind": "treadmill", "seconds": m * 60}]
                + ([{"kind": "rest", "seconds": 60}] if i < 6 else []))]),
    ("row_pyramid", "Pirâmide no remo", "Rowing pyramid",
     "250-500-750-500-250 m de remo (em tempo: 1-2-3-2-1 min), 1 min entre cada.",
     "250-500-750-500-250 m of rowing (by time: 1-2-3-2-1 min), 1 min in between.",
     [x for i, m in enumerate((1, 2, 3, 2, 1))
      for x in ([{"kind": "rowing", "seconds": m * 60}]
                + ([{"kind": "rest", "seconds": 60}] if i < 4 else []))]),
)


# ============================================================ separador Treinar


def train_items(app, sport: str, session: Item, tests: bool = True) -> list[Item]:
    """Sessão de treino · Challenge · Desafios · Testes — igual em todos."""
    a = app
    from velo.ui import app as app_mod
    challenge = Item(t("menu.challenge"), detail=challenge_detail(sport),
                     action=lambda: a.push(challenge_menu(a, sport)), data="chase")
    n = len(a.db.challenges(sport))
    desafios = Item(t("menu.challenges"),
                    value=tr("{n} em curso", "{n} active", n=n) if n else "",
                    detail=tr("Objetivos acumulados, com data limite se quiseres",
                              "Cumulative goals, with a deadline if you like"),
                    action=lambda: a.push(ChallengeScreen(a, sport)), data="challenges")
    items = [session, challenge, desafios]
    if tests:
        test_sport = "longevity" if sport == "gym" else sport
        items.append(Item(t("menu.tests"), detail=t("menu.tests_detail"),
                          action=lambda: a.push(app_mod._extra_health().TestsMenu(
                              a, test_sport)), data="ftp"))
    return items


def challenge_detail(sport: str) -> str:
    return {"cycling": t("menu.challenge_detail"),
            "rowing": tr("Desafio adaptativo, jogos e a Regata contra bots",
                         "Adaptive challenge, games and the Regatta vs bots"),
            "running": tr("Provas contra o relógio e escadas de ritmo",
                          "Time trials and pace ladders"),
            "swimming": tr("Provas contra o relógio e pirâmides",
                           "Time trials and pyramids"),
            "gym": tr("Treino surpresa, EMOM, Tabata e pirâmides",
                      "Surprise workout, EMOM, Tabata and pyramids")}.get(sport, "")


def challenge_menu(app, sport: str):
    if sport == "cycling":
        from velo.ui.sport_screens import ChallengeMenu
        return ChallengeMenu(app)
    if sport == "rowing":
        from velo.ui.rowing_screens import RowChallengeMenu
        return RowChallengeMenu(app)
    if sport == "gym":
        return GymChallengeMenu(app)
    return EnduranceChallengeMenu(app, sport)


# ======================================================== corrida e natação


def ensure_endurance(db, sport: str) -> dict[str, str]:
    """Cria (uma vez) os treinos das provas; devolve {chave: id do treino}."""
    ids = dict(db.get("challenge_workouts", {}) or {})
    changed = False
    for i, (key_, pt, en_, dpt, den, steps, _m) in enumerate(ENDURANCE_CHALLENGES.get(sport, ())):
        wid = ids.get(key_)
        if wid and en.workout(db, wid) is not None:
            continue
        ids[key_] = en.save_workout(db, None, sport, tr(pt, en_), tr(dpt, den), steps,
                                    mode="pace", builtin=en.CHALLENGE, sort=i)
        changed = True
    if changed:
        db.set("challenge_workouts", ids)
    return ids


def results(db, wid: str, measure: str, limit: int = 10) -> list[dict]:
    """As melhores tentativas de uma prova (sessões concluídas desse treino)."""
    en.ensure(db)
    order = "COALESCE(moving_s, elapsed_s) ASC" if measure == "time" else "distance_m DESC"
    return [dict(r) for r in db.conn.execute(
        "SELECT * FROM endurance_sessions WHERE status='completed' AND workout_id = ?"
        f" ORDER BY {order} LIMIT ?", (wid, limit))]


def result_text(r: dict, measure: str) -> str:
    if measure == "time":
        return hms(r.get("moving_s") or r.get("elapsed_s") or 0)
    d = r.get("distance_m") or 0
    return f"{d / 1000:.2f} km" if d >= 1000 else f"{d:.0f} m"


class EnduranceChallengeMenu(Screen):
    """Challenge da corrida e da natação: provas, com a tabela de cada uma."""

    HAS_BOARD = True

    def __init__(self, app, sport: str):
        super().__init__(app)
        self.sport = sport

    def _spec(self, key_: str):
        return next(c for c in ENDURANCE_CHALLENGES[self.sport] if c[0] == key_)

    def side_board(self):
        item = self.list.selected
        if item is None or not isinstance(item.data, tuple):
            return boards.Board(t("menu.challenge"), empty=t("board.empty"))
        key_, wid = item.data
        spec = self._spec(key_)
        rows = [boards.Row(i, result_text(r, spec[6]), str(r["started_at"])[:10])
                for i, r in enumerate(results(self.app.db, wid, spec[6], boards.MAX_ROWS), 1)]
        return boards.Board(tr(spec[1], spec[2]), rows,
                            tr("os teus melhores", "your best"),
                            empty=tr("Ainda sem tentativas.", "No attempts yet."))

    def enter(self) -> None:
        a = self.app
        ids = ensure_endurance(a.db, self.sport)
        items = []
        for key_, pt, en_, dpt, den, _steps, measure in ENDURANCE_CHALLENGES[self.sport]:
            wid = ids[key_]
            best = results(a.db, wid, measure, 1)
            items.append(Item(tr(pt, en_), value=result_text(best[0], measure) if best else "—",
                              detail=tr(dpt, den),
                              action=lambda w=wid: self._start(w), data=(key_, wid)))
        self.chrome.set(f"{t('menu.challenge')} · {sp.name(self.sport)}",
                        tr("Contra o relógio e contra ti mesmo",
                           "Against the clock and against yourself"), self.footer())
        self.list.set_items(items, keep_index=True)

    def _start(self, wid: str) -> None:
        from velo.ui.endurance_screens import start
        start(self.app, self.sport, wid)


# ================================================================== ginásio


class GymChallengeMenu(Screen):
    """Challenge do ginásio: treino surpresa de cada modalidade e formatos de
    Conditioning, que correm na sessão por voltas."""

    def enter(self) -> None:
        from velo.core import gym
        from velo.ui import gym_screens as gs
        a = self.app
        items = []
        for m in gym.modalities():
            if m.laps:
                continue
            items.append(Item(tr("Surpresa · {m}", "Surprise · {m}", m=m.name),
                              detail=tr("Exercícios à sorte, só com o teu material",
                                        "Random exercises, only with your equipment"),
                              action=lambda k=m.key: a.push(gs.SurpriseScreen(a, k))))
        for key_, pt, en_, dpt, den, plan in GYM_FORMATS:
            from velo.core import laps_session as ls
            items.append(Item(tr(pt, en_), value=f"≈ {hms(ls.plan_seconds(plan))}",
                              detail=tr(dpt, den),
                              action=lambda p=plan: gs.start_laps(a, "conditioning",
                                                                  [dict(x) for x in p])))
        self.chrome.set(f"{t('menu.challenge')} · {sp.name('gym')}",
                        tr("Para quando te apetece ser surpreendido",
                           "For when you want to be surprised"), self.footer())
        self.list.set_items(items, keep_index=True)


class GymSessionPicker(Screen):
    """«Sessão de treino» do ginásio: escolhe a modalidade."""

    def enter(self) -> None:
        from velo.core import gym
        from velo.core import laps_session as ls
        from velo.ui import gym_screens as gs
        a = self.app
        items = []
        for m in gym.modalities():
            n = len(gym.workouts(a.db, m.key)) if not m.laps else len(ls.plans(a.db, m.key))
            items.append(Item(m.name, value=tr("{n} treinos", "{n} workouts", n=n) if n else "",
                              detail=m.desc, action=lambda k=m.key: a.push(
                                  gs.ModalityScreen(a, k)), data=("modality", m.key)))
        self.chrome.set(tr("Sessão de treino", "Training session") + " · " + sp.name("gym"),
                        tr("Escolhe a modalidade", "Pick the modality"), self.footer())
        self.list.set_items(items, keep_index=True)
