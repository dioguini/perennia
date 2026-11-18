"""Etiquetas das sessões e tipos de treino.

Cada sessão (e o seu .fit) leva etiquetas de três géneros:

* **tipo de sessão** — o que foi feito e onde: `Perennia`, `Indoor Cycling`,
  `Indoor Rowing`, `Indoor Running`… A corrida na passadeira não é virtual; só
  o é quando segue um .gpx (a rota é o «mundo» virtual) e, no ciclismo, a
  sessão com rota. As sessões sem rota são «indoor» à secura.
* **tipo de treino** — o esforço: recuperação, resistência aeróbia, tempo,
  limiar, VO2máx, anaeróbio, trabalho, aquecimento de prova… Um treino pode
  trazer o seu (escolhido no construtor); numa sessão livre sugere-se pelo
  esforço (o fator de intensidade, IF) e podes mudar no fim da sessão.
* **tipo de atividade** — automático, igual em todos os desportos: `Free Session` (sessão
  livre), `Workout` (um treino), `Challenge` + o nome do jogo (`Zone Hero`, `Regatta`…) ou
  `Test` + o nome do teste. Serve para ir buscar de uma vez todas as sessões de um tipo.
* **etiquetas livres** — as que escreves; as já usadas aparecem a sugerir. Um **treino** também
  as tem (escolhem-se no construtor) e as sessões desse treino herdam-nas.

**As etiquetas são sempre em inglês**, seja qual for o idioma da Perennia: assim as consultas
(`sessions_with`, filtros da Análise AdHoc) e os .fit dizem o mesmo em qualquer instalação.

O .fit guarda as etiquetas no nome do perfil desportivo (campo `name` da
mensagem `sport`), onde o Garmin Connect, o Strava e o TrainingPeaks as mostram.
"""
from __future__ import annotations

import math
import unicodedata

from .i18n import tr

# (chave, PT, EN) — a ordem é a da lista
WORKOUT_TYPES: tuple[tuple[str, str, str], ...] = (
    ("recovery", "Recuperação", "Recovery"),
    ("endurance", "Resistência aeróbia", "Aerobic endurance"),
    ("tempo", "Tempo", "Tempo"),
    ("threshold", "Limiar", "Threshold"),
    ("vo2max", "VO2máx", "VO2max"),
    ("anaerobic", "Anaeróbio / sprint", "Anaerobic / sprint"),
    ("work", "Trabalho", "Work"),
    ("race_warmup", "Aquecimento de prova", "Race warm-up"),
    ("race", "Prova", "Race"),
    ("test", "Teste", "Test"),
    ("technique", "Técnica", "Technique"),
    ("strength", "Força", "Strength"),
    ("mobility", "Mobilidade", "Mobility"),
)
TYPE_KEYS = tuple(k for k, _p, _e in WORKOUT_TYPES)

# etiquetas de «tipo de sessão» por desporto (a sua base, sem rota)
INDOOR = {"cycling": "Indoor Cycling", "rowing": "Indoor Rowing", "running": "Indoor Running",
          "swimming": "Pool Swimming", "strength": "Indoor Strength"}
VIRTUAL = {"cycling": "Virtual Cycling", "running": "Virtual Running"}
APP_TAG = "Perennia"

# os valores do FIT (sub_sport)
SUB_INDOOR_CYCLING, SUB_TREADMILL, SUB_VIRTUAL = 6, 1, 58


def type_label(key: str | None) -> str:
    """O nome da etiqueta de um tipo de treino — sempre em inglês (é uma etiqueta)."""
    for k, _pt, en in WORKOUT_TYPES:
        if k == key:
            return en
    return key or ""


def type_labels() -> list[str]:
    return [en for _k, _pt, en in WORKOUT_TYPES]


def type_key(label: str) -> str | None:
    """A chave de um tipo, pelo nome (PT ou EN) ou pela própria chave."""
    low = _fold(label)
    for k, pt, en in WORKOUT_TYPES:
        if low in (_fold(k), _fold(pt), _fold(en)):
            return k
    return None


def _fold(text: str) -> str:
    s = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in s if not unicodedata.combining(c)).casefold().strip()


# ------------------------------------------------------------------ tabelas


def ensure(db) -> None:
    db.conn.execute(
        "CREATE TABLE IF NOT EXISTS workout_types (sport TEXT NOT NULL, workout_id TEXT NOT"
        " NULL, wtype TEXT NOT NULL, PRIMARY KEY (sport, workout_id))")
    db.conn.execute(
        "CREATE TABLE IF NOT EXISTS session_tags (sport TEXT NOT NULL, session_id TEXT NOT"
        " NULL, tag TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'custom',"
        " PRIMARY KEY (sport, session_id, tag))")
    db.conn.execute(
        "CREATE TABLE IF NOT EXISTS tag_catalog (tag TEXT PRIMARY KEY, kind TEXT NOT NULL"
        " DEFAULT 'custom')")
    db.conn.execute(
        "CREATE TABLE IF NOT EXISTS workout_tags (sport TEXT NOT NULL, workout_id TEXT NOT"
        " NULL, tag TEXT NOT NULL, PRIMARY KEY (sport, workout_id, tag))")
    db.conn.execute("CREATE INDEX IF NOT EXISTS ix_session_tags_tag ON session_tags(tag)")
    db.conn.execute("CREATE INDEX IF NOT EXISTS ix_session_tags_sid ON session_tags(session_id)")
    db.conn.commit()


# ----------------------------------------------------------- tipo de treino


def workout_type(db, sport: str, wid: str | None) -> str | None:
    if not wid:
        return None
    ensure(db)
    r = db.conn.execute("SELECT wtype FROM workout_types WHERE sport = ? AND workout_id = ?",
                        (sport, str(wid))).fetchone()
    return r["wtype"] if r else None


def set_workout_type(db, sport: str, wid: str, wtype: str | None) -> None:
    ensure(db)
    if not wtype or wtype not in TYPE_KEYS:
        db.conn.execute("DELETE FROM workout_types WHERE sport = ? AND workout_id = ?",
                        (sport, str(wid)))
    else:
        db.conn.execute("INSERT OR REPLACE INTO workout_types (sport, workout_id, wtype)"
                        " VALUES (?, ?, ?)", (sport, str(wid), wtype))
    db.conn.commit()


# ------------------------------------------------------------- sugestão


def _get(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def effort_if(summary) -> float | None:
    """O fator de intensidade de uma sessão (1,0 = o esforço de uma hora no limiar).
    Pela potência normalizada e a FTP, se houver; senão pela carga (TSS = IF² × h × 100)."""
    ftp, np_ = _get(summary, "ftp_w"), _get(summary, "np_w") or _get(summary, "avg_power_w")
    if ftp and np_:
        return float(np_) / float(ftp)
    load = _get(summary, "tss") or _get(summary, "load")
    secs = _get(summary, "moving_s") or _get(summary, "elapsed_s") or 0
    if load and secs > 60:
        return math.sqrt(float(load) / (100.0 * secs / 3600.0))
    return None


def suggest_type(intensity: float | None, variability: float | None = None) -> str:
    """O tipo de treino pelo esforço (IF) e, se houver, a variabilidade (VI = NP/média):
    muito variável e forte são intervalos."""
    if intensity is None:
        return "endurance"
    if variability and variability >= 1.18 and intensity >= 0.75:
        return "vo2max" if intensity >= 1.0 else "work"
    if intensity < 0.55:
        return "recovery"
    if intensity < 0.76:
        return "endurance"
    if intensity < 0.88:
        return "tempo"
    if intensity < 1.0:
        return "threshold"
    if intensity < 1.15:
        return "vo2max"
    return "anaerobic"


def suggest_for(summary) -> str:
    np_, avg = _get(summary, "np_w"), _get(summary, "avg_power_w")
    vi = float(np_) / float(avg) if np_ and avg else None
    return suggest_type(effort_if(summary), vi)


# velocidade de referência (m/s) para converter um bloco por distância em tempo
_REF_SPEED = {"running": 2.8, "rowing": 3.85, "swimming": 0.9, "cycling": 8.0}


def block_seconds(b, sport: str = "cycling") -> float:
    """A duração de um bloco em segundos (os de distância convertem-se pela velocidade
    do bloco, se tiver, ou por uma de referência do desporto)."""
    dur = float(getattr(b, "dur", 0) or 0)
    if getattr(b, "dur_type", "time") != "distance":
        return dur
    extra = getattr(b, "extra", None) or {}
    v = (float(extra["speed_kmh"]) / 3.6) if extra.get("speed_kmh") else _REF_SPEED.get(sport, 3.0)
    return dur / v if v > 0 else 0.0


def suggest_for_blocks(blocks, sport: str = "cycling") -> str:
    """O tipo de um treino ainda por fazer, pelo esforço dos blocos (percentagem do
    limiar, lo/hi) ponderado pela duração. Serve ao construtor."""
    tot = acc = 0.0
    hi_time = 0.0
    for b in blocks:
        d = block_seconds(b, sport)
        lo = getattr(b, "lo", None)
        if d <= 0 or lo is None:
            continue
        hi = getattr(b, "hi", None)
        pct = (float(lo) + float(hi)) / 2 if hi else float(lo)
        tot += d
        acc += d * (pct / 100.0) ** 4              # a potência normalizada (4.ª potência)
        if pct >= 105:
            hi_time += d
    if tot <= 0:
        return "endurance"
    nf = (acc / tot) ** 0.25
    if hi_time / tot > 0.15 and nf >= 0.8:
        return "vo2max" if nf >= 1.0 else "work"
    return suggest_type(nf)


# --------------------------------------------------- tipo de atividade (automático)

FREE, WORKOUT, CHALLENGE, TEST = "Free Session", "Workout", "Challenge", "Test"
KINDS = ("free", "workout", "game", "chase", "test")
# o nome do jogo/teste como etiqueta (inglês, igual em todos os desportos)
GAME_NAMES = {"adaptive": "Adaptive Challenge", "zone_hero": "Zone Hero",
              "ladder": "Power Ladder", "warmup": "Warm-up", "elimination": "Elimination",
              "tug": "Tug of War", "regatta": "Regatta", "seg_pace": "Segment Pace",
              "seg_kom": "Segment KOM", "chase": "Chase", "surprise": "Surprise",
              "emom20": "EMOM 20 min", "tabata": "Tabata x3",
              "tread_pyramid": "Treadmill Pyramid", "row_pyramid": "Rowing Pyramid"}
TEST_NAMES = {"20min": "FTP 20 min", "ramp": "FTP Ramp", "8x8": "FTP 2x8 min",
              "sprint": "Sprint Test", "1min": "1 min Test", "5min": "5 min Test",
              "row_2000": "Row 2000 m", "row_500": "Row 500 m", "row_30min": "Row 30 min",
              "row_1min": "Row 1 min"}


def _title(key: str) -> str:
    return " ".join(w.capitalize() for w in str(key).replace("_", " ").replace(":", " ").split())


def kind_of(*, kind: str | None = None, workout_id: str | None = None,
            game_key: str | None = None, chase: bool = False,
            test: str | None = None) -> tuple[str, str | None]:
    """(tipo, nome) de uma sessão — o que cada motor sabe de si:
    `free` · `workout` · `game` (nome = o jogo) · `chase` · `test` (nome = o protocolo)."""
    if game_key:
        return "game", str(game_key)
    if chase or kind == "chase":
        return "chase", None
    if test or kind in ("ftp_test", "test"):
        return "test", test
    if workout_id or kind == "workout":
        return "workout", None
    return "free", None


def kind_tags(kind: str | None, name: str | None = None) -> list[str]:
    """As etiquetas do tipo de atividade: `Free Session` · `Workout` · `Challenge` + jogo ·
    `Test` + teste. Sempre em inglês."""
    if kind == "game":
        tags = [CHALLENGE]
        if name:
            tags.append(GAME_NAMES.get(name) or _title(name))
        return tags
    if kind == "chase":
        return [CHALLENGE, GAME_NAMES["chase"]]
    if kind == "test":
        tags = [TEST]
        label = TEST_NAMES.get(name or "")
        if label:
            tags.append(label)
        return tags
    if kind == "workout":
        return [WORKOUT]
    return [FREE]


# ----------------------------------------------------- etiquetas de um treino


def clean_tags(tags) -> list[str]:
    """Etiquetas limpas: sem espaços a mais, sem vazias nem repetidas (maiúsculas e
    acentos não contam), no máximo 32 letras cada."""
    out: list[str] = []
    seen: set[str] = set()
    for t in tags or []:
        c = " ".join(str(t).split())[:32]
        f = _fold(c)
        if c and f not in seen:
            seen.add(f)
            out.append(c)
    return out


def workout_tags(db, sport: str, wid: str | None) -> list[str]:
    """As etiquetas livres de um treino (as que escolheste no construtor)."""
    if not wid:
        return []
    ensure(db)
    return [r["tag"] for r in db.conn.execute(
        "SELECT tag FROM workout_tags WHERE sport = ? AND workout_id = ? ORDER BY rowid",
        (sport, str(wid)))]


def set_workout_tags(db, sport: str, wid: str, tags) -> list[str]:
    ensure(db)
    clean = clean_tags(tags)
    db.conn.execute("DELETE FROM workout_tags WHERE sport = ? AND workout_id = ?",
                    (sport, str(wid)))
    for t in clean:
        db.conn.execute("INSERT OR IGNORE INTO workout_tags (sport, workout_id, tag)"
                        " VALUES (?, ?, ?)", (sport, str(wid), t))
        db.conn.execute("INSERT OR IGNORE INTO tag_catalog (tag, kind) VALUES (?, 'custom')",
                        (t,))
    db.conn.commit()
    return clean


# ------------------------------------------------------- tipo de sessão


def session_type_tags(sport: str, has_route: bool = False) -> list[str]:
    """Perennia + onde foi: `Indoor Cycling`; com rota (.gpx), também `Virtual …`."""
    tags = [APP_TAG, INDOOR.get(sport, "Indoor")]
    if has_route and sport in VIRTUAL:
        tags.insert(1, VIRTUAL[sport])
    return tags


def sub_sport(sport: str, has_route: bool = False) -> int | None:
    """O sub_sport do FIT: «virtual» quando segue uma rota (ciclismo e corrida);
    senão, o indoor do desporto (rolo, passadeira…). None: o habitual do desporto."""
    if has_route and sport in VIRTUAL:
        return SUB_VIRTUAL
    if sport == "cycling":
        return SUB_INDOOR_CYCLING
    if sport == "running":
        return SUB_TREADMILL
    return None


def is_virtual(sport: str, has_route: bool) -> bool:
    return bool(has_route and sport in VIRTUAL)


# ------------------------------------------------------------ etiquetas livres


def known_tags(db) -> list[str]:
    """Todas as etiquetas já usadas (para sugerir ao escrever), sem repetidas."""
    ensure(db)
    seen: dict[str, str] = {}
    for tag in [APP_TAG, *INDOOR.values(), *VIRTUAL.values()]:
        seen.setdefault(_fold(tag), tag)
    for r in db.conn.execute("SELECT tag FROM tag_catalog ORDER BY tag"):
        seen.setdefault(_fold(r["tag"]), r["tag"])
    for r in db.conn.execute("SELECT DISTINCT tag FROM session_tags WHERE kind = 'custom'"
                             " ORDER BY tag"):
        seen.setdefault(_fold(r["tag"]), r["tag"])
    return list(seen.values())


def match(db, text: str, limit: int = 8) -> list[str]:
    """As etiquetas existentes que começam (ou contêm) o texto — a deteção automática."""
    low = _fold(text)
    if not low:
        return []
    allt = known_tags(db)
    first = [t for t in allt if _fold(t).startswith(low)]
    rest = [t for t in allt if low in _fold(t) and t not in first]
    return (first + rest)[:limit]


def normalize(db, text: str) -> str:
    """A etiqueta como já existe (mesma sem maiúsculas/acentos), ou a escrita limpa."""
    clean = " ".join((text or "").split())[:32]
    if not clean:
        return ""
    low = _fold(clean)
    for t in known_tags(db):
        if _fold(t) == low:
            return t
    return clean


# ------------------------------------------------------------------ sessões


def load(db, sport: str, sid: str | None) -> dict:
    """{"workout_type": chave|None, "activity": [...], "session": [...], "custom": [...]}
    de uma sessão (`activity`: Free Session, Challenge + jogo…; `session`: Perennia, Indoor …)."""
    out = {"workout_type": None, "activity": [], "session": [], "custom": []}
    if not sid:
        return out
    ensure(db)
    for r in db.conn.execute("SELECT tag, kind FROM session_tags WHERE sport = ? AND"
                             " session_id = ? ORDER BY rowid", (sport, str(sid))):
        if r["kind"] == "workout_type":
            out["workout_type"] = r["tag"]
        elif r["kind"] == "activity":
            out["activity"].append(r["tag"])
        elif r["kind"] == "session":
            out["session"].append(r["tag"])
        else:
            out["custom"].append(r["tag"])
    return out


def save(db, sport: str, sid: str, info: dict) -> None:
    ensure(db)
    db.conn.execute("DELETE FROM session_tags WHERE sport = ? AND session_id = ?",
                    (sport, str(sid)))
    rows = []
    if info.get("workout_type"):
        rows.append((info["workout_type"], "workout_type"))
    rows += [(t, "activity") for t in info.get("activity") or []]
    rows += [(t, "session") for t in info.get("session") or []]
    rows += [(t, "custom") for t in info.get("custom") or []]
    for tag, kind in rows:
        db.conn.execute("INSERT OR IGNORE INTO session_tags (sport, session_id, tag, kind)"
                        " VALUES (?, ?, ?, ?)", (sport, str(sid), tag, kind))
        if kind == "custom":
            db.conn.execute("INSERT OR IGNORE INTO tag_catalog (tag, kind) VALUES (?, 'custom')",
                            (tag,))
    db.conn.commit()


def labels(info: dict) -> list[str]:
    """As etiquetas por mostrar/gravar: o tipo de atividade, o tipo de treino (em inglês),
    o tipo de sessão e as livres."""
    out = list(info.get("activity") or [])
    if info.get("workout_type"):
        out.append(type_label(info["workout_type"]))
    out += list(info.get("session") or [])
    out += list(info.get("custom") or [])
    return out


def fit_text(info: dict, limit: int = 63) -> str:
    """O texto do .fit (cabe no campo de 64 bytes): `Free Session · Tempo · Indoor Cycling`.
    Entram etiquetas inteiras, por prioridade — o tipo de sessão, o tipo de treino, as tuas,
    onde foi e, por fim, `Perennia` (que é igual em todas); a que já não couber fica de fora."""
    lab = labels(info)
    session = list(info.get("session") or [])
    order = [t for t in lab if t not in session] + [t for t in session if t != APP_TAG] \
        + [t for t in session if t == APP_TAG]
    out = ""
    for tag in order:
        nxt = tag if not out else out + " · " + tag
        if len(nxt) > limit:
            if not out:
                out = tag[:limit]
            continue
        out = nxt
    return out


def defaults(db, sport: str, *, workout_id: str | None = None, has_route: bool = False,
             summary=None, activity: tuple[str, str | None] | None = None) -> dict:
    """As etiquetas de uma sessão que ainda ninguém editou: o tipo de atividade (`activity` =
    (tipo, nome) de `kind_of`; sem isso, treino ou sessão livre), o tipo do treino (ou, numa
    sessão livre, o sugerido pelo esforço), o tipo de sessão e as etiquetas do treino."""
    wtype = workout_type(db, sport, workout_id)
    if wtype is None:
        wtype = suggest_for(summary) if summary is not None else None
    kind, name = activity or kind_of(workout_id=workout_id)
    return {"workout_type": wtype, "activity": kind_tags(kind, name),
            "session": session_type_tags(sport, has_route),
            "custom": workout_tags(db, sport, workout_id)}


def resolve(db, sport: str, sid: str, chosen: dict | None, *, workout_id: str | None = None,
            has_route: bool = False, summary=None,
            activity: tuple[str, str | None] | None = None) -> dict:
    """Fecha as etiquetas de uma sessão: as escolhidas na janela do fim, ou as de
    omissão; guarda-as e devolve-as (o .fit e o resumo usam o mesmo)."""
    info = dict(defaults(db, sport, workout_id=workout_id, has_route=has_route,
                         summary=summary, activity=activity))
    auto = {"activity": list(info["activity"]), "session": list(info["session"])}
    if chosen:
        for k in ("workout_type", "activity", "session", "custom"):
            if k in chosen and chosen[k] is not None:
                info[k] = chosen[k]
    # o tipo de atividade, `Perennia` e o `Indoor …` do desporto estão SEMPRE lá
    for k, base in auto.items():
        info[k] = base + [x for x in info[k] if x not in base]
    fixed = set(info["activity"]) | set(info["session"])
    info["custom"] = [x for x in info["custom"] if x not in fixed]
    save(db, sport, sid, info)
    return info


# ------------------------------------------------- sessões antigas (uma vez e já)


def _missing(db, table: str, where: str = "status = 'completed'") -> str:
    return (f"{table} WHERE {where} AND id NOT IN (SELECT session_id FROM session_tags"
            f" WHERE kind = 'activity')")


def backfill(db) -> int:
    """Põe o tipo de atividade nas sessões que ainda não o têm (as de antes das etiquetas:
    o `kind`, o jogo e o treino ficaram guardados). Não mexe no que já tem. Devolve quantas."""
    ensure(db)
    have = {r[0] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    rows: list[tuple[str, str, tuple[str, str | None]]] = []

    def q(sql: str) -> list:
        try:
            return db.conn.execute(sql).fetchall()
        except Exception:
            return []

    if "rides" in have:
        games = {}
        if "game_results" in have:
            games = {r["ride_id"]: r["game"] for r in q(
                "SELECT ride_id, game FROM game_results WHERE ride_id IS NOT NULL")}
        tests = {}
        if "ftp_tests" in have:
            tests = {r["ride_id"]: r["protocol"] for r in q(
                "SELECT ride_id, protocol FROM ftp_tests WHERE ride_id IS NOT NULL")}
        for r in q("SELECT id, kind, workout_id FROM " + _missing(db, "rides")):
            rows.append(("cycling", r["id"], kind_of(
                kind=r["kind"], workout_id=r["workout_id"], game_key=games.get(r["id"])
                if r["kind"] == "game" else None, test=tests.get(r["id"]))))
    if "row_sessions" in have:
        for r in q("SELECT id, kind, workout_id, protocol, game FROM "
                   + _missing(db, "row_sessions")):
            rows.append(("rowing", r["id"], kind_of(
                kind=r["kind"], workout_id=r["workout_id"], game_key=r["game"],
                test=r["protocol"])))
    if "endurance_sessions" in have:
        for r in q("SELECT id, sport, workout_id FROM " + _missing(db, "endurance_sessions")):
            rows.append((r["sport"] or "running", r["id"], kind_of(workout_id=r["workout_id"])))
    if "strength_sessions" in have:
        for r in q("SELECT id, workout_id FROM " + _missing(db, "strength_sessions")):
            rows.append(("strength", r["id"], kind_of(workout_id=r["workout_id"])))
    for sport, sid, (kind, name) in rows:
        for tag in kind_tags(kind, name):
            db.conn.execute("INSERT OR IGNORE INTO session_tags (sport, session_id, tag, kind)"
                            " VALUES (?, ?, ?, 'activity')", (sport, str(sid), tag))
    if rows:
        db.conn.commit()
    return len(rows)


# ---------------------------------------------------------------- consultas


def split_tags(text) -> list[str]:
    """Uma lista escrita («Challenge, Zone Hero»), ou já em lista, em etiquetas limpas."""
    if isinstance(text, (list, tuple, set)):
        parts = list(text)
    else:
        parts = str(text or "").replace(";", ",").replace("|", ",").split(",")
    return clean_tags(parts)


def tags_by_session(db) -> dict[str, list[str]]:
    """{id da sessão: [etiquetas…]} — numa só consulta (a Análise AdHoc usa-o)."""
    ensure(db)
    out: dict[str, list[str]] = {}
    for r in db.conn.execute("SELECT session_id, tag FROM session_tags ORDER BY rowid"):
        out.setdefault(r["session_id"], []).append(r["tag"])
    return out


def tag_counts(db) -> list[tuple[str, int]]:
    """As etiquetas em uso nas sessões, com quantas sessões cada uma, da mais usada para a menos."""
    ensure(db)
    return [(r["tag"], r["n"]) for r in db.conn.execute(
        "SELECT tag, COUNT(DISTINCT session_id) AS n FROM session_tags GROUP BY tag"
        " ORDER BY n DESC, tag")]


def matches(have, wanted, mode: str = "all") -> bool:
    """`have` (etiquetas de uma sessão) cumpre `wanted`? `all`: tem todas · `any`: tem alguma ·
    `none`: não tem nenhuma. Maiúsculas e acentos não contam."""
    h = {_fold(t) for t in have or []}
    w = [_fold(t) for t in wanted or [] if _fold(t)]
    if not w:
        return True
    if mode == "any":
        return any(t in h for t in w)
    if mode == "none":
        return not any(t in h for t in w)
    return all(t in h for t in w)


def sessions_with(db, wanted, mode: str = "all") -> list[dict]:
    """As sessões (de todos os desportos) com uma ou mais etiquetas:
    [{"sport", "id", "tags": [...]}]. `mode`: all · any · none."""
    ensure(db)
    sports: dict[str, str] = {}
    by: dict[str, list[str]] = {}
    for r in db.conn.execute("SELECT sport, session_id, tag FROM session_tags ORDER BY rowid"):
        sports.setdefault(r["session_id"], r["sport"])
        by.setdefault(r["session_id"], []).append(r["tag"])
    return [{"sport": sports[sid], "id": sid, "tags": have}
            for sid, have in by.items() if matches(have, split_tags(wanted), mode)]


def workouts_with(db, wanted, mode: str = "all") -> list[dict]:
    """Os treinos com uma ou mais etiquetas (as livres e o tipo de treino):
    [{"sport", "id", "tags": [...]}]."""
    ensure(db)
    by: dict[tuple[str, str], list[str]] = {}
    for r in db.conn.execute("SELECT sport, workout_id, wtype FROM workout_types"):
        by.setdefault((r["sport"], r["workout_id"]), []).append(type_label(r["wtype"]))
    for r in db.conn.execute("SELECT sport, workout_id, tag FROM workout_tags ORDER BY rowid"):
        by.setdefault((r["sport"], r["workout_id"]), []).append(r["tag"])
    want = split_tags(wanted)
    return [{"sport": sp, "id": wid, "tags": have}
            for (sp, wid), have in by.items() if matches(have, want, mode)]


def activity_of(have) -> tuple[str, str]:
    """(tipo de sessão, jogo ou teste) de uma lista de etiquetas: `("Challenge", "Zone Hero")`,
    `("Free Session", "")`. Vazio se a sessão não tem o tipo (uma importada, por exemplo)."""
    have = list(have or [])
    for base in (CHALLENGE, TEST, WORKOUT, FREE):
        if base in have:
            names = set(GAME_NAMES.values()) | set(TEST_NAMES.values())
            return base, next((t for t in have if t in names), "") \
                if base in (CHALLENGE, TEST) else ""
    return "", ""
