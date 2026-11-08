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
* **etiquetas livres** — as que escreves; as já usadas aparecem a sugerir.

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
          "swimming": "Pool Swimming", "strength": "Gym"}
VIRTUAL = {"cycling": "Virtual Cycling", "running": "Virtual Running"}
APP_TAG = "Perennia"

# os valores do FIT (sub_sport)
SUB_INDOOR_CYCLING, SUB_TREADMILL, SUB_VIRTUAL = 6, 1, 58


def type_label(key: str | None) -> str:
    for k, pt, en in WORKOUT_TYPES:
        if k == key:
            return tr(pt, en)
    return key or ""


def type_labels() -> list[str]:
    return [tr(pt, en) for _k, pt, en in WORKOUT_TYPES]


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
    """{"workout_type": chave|None, "session": [...], "custom": [...]} de uma sessão."""
    out = {"workout_type": None, "session": [], "custom": []}
    if not sid:
        return out
    ensure(db)
    for r in db.conn.execute("SELECT tag, kind FROM session_tags WHERE sport = ? AND"
                             " session_id = ? ORDER BY rowid", (sport, str(sid))):
        if r["kind"] == "workout_type":
            out["workout_type"] = r["tag"]
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
    """As etiquetas por mostrar/gravar: o tipo de treino (por extenso) + sessão + livres."""
    out = []
    if info.get("workout_type"):
        out.append(type_label(info["workout_type"]))
    out += list(info.get("session") or [])
    out += list(info.get("custom") or [])
    return out


def fit_text(info: dict, limit: int = 63) -> str:
    """O texto do .fit (cabe no campo de 64 bytes): `Perennia · Indoor Cycling · Limiar`."""
    text = " · ".join(labels(info))
    return text[:limit]


def defaults(db, sport: str, *, workout_id: str | None = None, has_route: bool = False,
             summary=None) -> dict:
    """As etiquetas de uma sessão que ainda ninguém editou: o tipo do treino (ou, numa
    sessão livre, o sugerido pelo esforço) e o tipo de sessão."""
    wtype = workout_type(db, sport, workout_id)
    if wtype is None:
        wtype = suggest_for(summary) if summary is not None else None
    return {"workout_type": wtype, "session": session_type_tags(sport, has_route),
            "custom": []}


def resolve(db, sport: str, sid: str, chosen: dict | None, *, workout_id: str | None = None,
            has_route: bool = False, summary=None) -> dict:
    """Fecha as etiquetas de uma sessão: as escolhidas na janela do fim, ou as de
    omissão; guarda-as e devolve-as (o .fit e o resumo usam o mesmo)."""
    info = dict(defaults(db, sport, workout_id=workout_id, has_route=has_route,
                         summary=summary))
    if chosen:
        for k in ("workout_type", "session", "custom"):
            if k in chosen and chosen[k] is not None:
                info[k] = chosen[k]
    save(db, sport, sid, info)
    return info
