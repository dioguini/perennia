"""A análise de uma sessão já feita, de qualquer desporto: que tipo de sessão
foi, se cada bloco do treino foi cumprido, e as séries para os gráficos
(com os blocos por baixo, para se perceber os dados).

Lê o que o feedback já sabe ler (`feedback.load_session` e `prescribed`):
as amostras de segundo a segundo em % do limiar e o treino prescrito.
"""
from __future__ import annotations

from . import feedback as fbm
from . import intensity as it
from .i18n import tr
from .units import hms

# um bloco conta como cumprido com esta parte do tempo dentro do alvo
DONE, PARTIAL = 0.75, 0.45
DEFAULT_TOL = 6.0            # ± % do limiar, quando o bloco não diz outra coisa


# ------------------------------------------------------------- tipo de sessão


def session_type(db, sess: fbm.Session) -> str:
    """«Treino: Sweet spot 3×12 · Potência · ERG», «Sessão livre · rota X»…"""
    from . import workout_meta as wm
    kind = None
    extra = ""
    if sess.kind == "ride":
        r = db.conn.execute("SELECT kind, route_id FROM rides WHERE id = ?",
                            (sess.id,)).fetchone()
        kind = r["kind"] if r is not None else None
        if r is not None and r["route_id"]:
            route = db.route(r["route_id"])
            extra = route["name"] if route else ""
    elif sess.kind == "row":
        r = db.conn.execute("SELECT kind, protocol, game FROM row_sessions WHERE id = ?",
                            (sess.id,)).fetchone()
        kind = r["kind"] if r is not None else None
        if r is not None and kind == "test":
            extra = r["protocol"] or ""
    brief = fbm.prescribed(db, sess)
    if sess.workout_id and brief is not None:
        label = wm.label(db, sess.sport, sess.workout_id, "power") if sess.sport != "gym" else ""
        return tr("Treino: {n}", "Workout: {n}", n=brief.title) + (f" · {label}" if label else "")
    if kind == "ftp_test":
        return tr("Teste de FTP", "FTP test")
    if kind == "test":
        return tr("Teste", "Test") + (f" · {extra}" if extra else "")
    if kind in ("chase",):
        return tr("Challenge · fuga", "Challenge · breakaway")
    if kind in ("game",):
        return tr("Challenge · jogo", "Challenge · game")
    if sess.sport == "gym":
        return tr("Treino livre de ginásio", "Free gym session")
    return tr("Sessão livre", "Free session") + (f" · {extra}" if extra else "")


# --------------------------------------------------------- blocos no tempo


def _step_laps(db, sess: fbm.Session) -> list[tuple[float, float]]:
    """As voltas que fecharam no fim de cada bloco (a volta automática por bloco)."""
    if sess.kind == "ride":
        rows = db.conn.execute("SELECT start_t_s AS a, end_t_s AS b FROM laps WHERE ride_id = ?"
                               " AND trigger = 'workout_step' ORDER BY lap_no",
                               (sess.id,)).fetchall()
    elif sess.kind == "row":
        rows = db.conn.execute("SELECT start_t AS a, end_t AS b FROM row_laps WHERE"
                               " session_id = ? AND trigger = 'workout_step' ORDER BY lap_no",
                               (sess.id,)).fetchall()
    elif sess.kind == "endurance":
        rows = db.conn.execute("SELECT start_t AS a, end_t AS b FROM endurance_laps WHERE"
                               " session_id = ? AND trigger = 'workout_step' ORDER BY lap_no",
                               (sess.id,)).fetchall()
    else:
        return []
    return [(float(r["a"] or 0), float(r["b"] or 0)) for r in rows]


def block_windows(db, sess: fbm.Session, brief) -> list[tuple[float, float]]:
    """(início, fim) de cada bloco em segundos de sessão. Pelas voltas de cada
    bloco quando existem (os blocos por distância só assim batem certo);
    senão, pela duração prevista de cada um."""
    raw = list(brief.raw_blocks) if brief else []
    laps = _step_laps(db, sess)
    out: list[tuple[float, float]] = []
    t = 0.0
    for i, b in enumerate(raw):
        if i < len(laps) and laps[i][1] > laps[i][0]:
            a, z = laps[i]
        else:
            a, z = t, t + float(b.seconds or 0)
        out.append((a, z))
        t = z
    return out


# ----------------------------------------------------------- cumprimento


def _tol(db, sess: fbm.Session, i: int) -> float:
    from . import workout_meta as wm
    try:
        blocks = wm.get(db, sess.sport, sess.workout_id).get("blocks") or []
        v = (blocks[i] or {}).get("tol") if i < len(blocks) else None
    except Exception:
        v = None
    return float(v) if v else DEFAULT_TOL


def block_compliance(db, sess: fbm.Session) -> list[dict]:
    """Um dicionário por bloco do treino: o alvo, o feito (média), a parte do
    tempo dentro do alvo e o veredicto (cumprido · em parte · não cumprido ·
    não feito · livre)."""
    brief = fbm.prescribed(db, sess)
    if brief is None or sess.sport == "gym":
        return []
    wins = block_windows(db, sess, brief)
    ctx = it.Context.from_db(db, sess.sport)
    if sess.ftp_w:
        ctx.ftp_w = ctx.row_ftp_w = int(sess.ftp_w)
    mode = "power" if sess.sport in ("cycling", "rowing") else "pace"
    vals = [(t, p, h) for t, p, _raw, h in sess.samples]
    end_t = max((t for t, *_ in vals), default=0)
    out = []
    for i, (b, (a, z)) in enumerate(zip(brief.raw_blocks, wins)):
        inside = [(p, h) for t, p, h in vals if a <= t < z]
        pcts = [p for p, _h in inside if p is not None]
        hrs = [h for _p, h in inside if h]
        avg = sum(pcts) / len(pcts) if pcts else None
        row = {"i": i, "name": b.name, "target": b.target, "kind": b.kind,
               "start": a, "end": z, "seconds": z - a, "lo": b.lo, "hi": b.hi,
               "avg_pct": avg, "avg_hr": sum(hrs) / len(hrs) if hrs else None,
               "done": None, "in_target": None}
        if a >= end_t or not inside:
            row["verdict"] = "skipped"
        elif b.lo is None:
            row["verdict"] = "free"
        else:
            tol = _tol(db, sess, i)
            lo, hi = sorted((b.lo, b.hi if b.hi is not None else b.lo))
            lo, hi = lo - tol, hi + tol
            if b.kind in ("warmup", "cooldown", "rest"):
                lo, hi = lo - 10, hi + 10          # nos blocos leves, mais folga
            # média de 5 s, para não penalizar as oscilações de cada pedalada
            win: list[float] = []
            ok = n = 0
            for p in pcts:
                win.append(p)
                if len(win) > 5:
                    win.pop(0)
                m = sum(win) / len(win)
                n += 1
                ok += 1 if lo <= m <= hi else 0
            frac = ok / n if n else 0.0
            row["in_target"] = frac
            covered = min(1.0, (min(z, end_t) - a) / max(1.0, z - a))
            row["done"] = covered
            if covered < 0.9:
                row["verdict"] = "short"
            else:
                row["verdict"] = ("ok" if frac >= DONE else "partial" if frac >= PARTIAL
                                  else "miss")
        if avg is not None:
            row["avg_text"] = ctx.text(mode, avg) if mode == "power" else ctx.short(mode, avg)
        else:
            row["avg_text"] = "—"
        out.append(row)
    return out


VERDICTS = {"ok": ("✓ cumprido", "✓ done"), "partial": ("~ em parte", "~ partly"),
            "miss": ("✗ não cumprido", "✗ missed"), "short": ("✗ não acabado", "✗ unfinished"),
            "skipped": ("— não feito", "— not done"), "free": ("✓ livre", "✓ free")}


def verdict_text(v: str) -> str:
    return tr(*VERDICTS.get(v, ("", "")))


def summary(rows: list[dict]) -> str:
    graded = [r for r in rows if r["verdict"] in ("ok", "partial", "miss", "short")]
    if not graded:
        return ""
    ok = sum(1 for r in graded if r["verdict"] == "ok")
    return tr("{a} de {b} blocos cumpridos", "{a} of {b} blocks done", a=ok, b=len(graded))


# ------------------------------------------------------------- gráficos


def series(db, sess: fbm.Session) -> dict:
    """As séries de segundo a segundo para o gráfico: {nome: (valores, cor,
    unidade)} — a primeira é a principal (a do alvo) — e `t` (segundos)."""
    out: dict = {"t": [], "lines": []}
    if sess.kind == "ride":
        rows = db.conn.execute("SELECT t_s, power_w, hr_bpm, cadence_rpm FROM ride_samples"
                               " WHERE ride_id = ? ORDER BY t_s", (sess.id,)).fetchall()
        out["t"] = [r[0] for r in rows]
        out["lines"] = [(tr("Potência (W)", "Power (W)"), [r[1] or 0 for r in rows],
                         (108, 170, 220)),
                        (tr("FC (bpm)", "HR (bpm)"), [r[2] or 0 for r in rows], (214, 54, 128)),
                        (tr("Cadência (rpm)", "Cadence (rpm)"), [r[3] or 0 for r in rows],
                         (120, 200, 150))]
    elif sess.kind == "row":
        rows = db.conn.execute("SELECT t_s, power_w, hr_bpm, spm FROM row_samples"
                               " WHERE session_id = ? ORDER BY t_s", (sess.id,)).fetchall()
        out["t"] = [r[0] for r in rows]
        out["lines"] = [(tr("Potência (W)", "Power (W)"), [r[1] or 0 for r in rows],
                         (108, 170, 220)),
                        (tr("FC (bpm)", "HR (bpm)"), [r[2] or 0 for r in rows], (214, 54, 128)),
                        (tr("Voga (spm)", "Rate (spm)"), [r[3] or 0 for r in rows],
                         (120, 200, 150))]
    elif sess.kind == "endurance":
        cols = {c["name"] for c in db.conn.execute("PRAGMA table_info(endurance_samples)")}
        inc = ", incline_pct" if "incline_pct" in cols else ", NULL"
        rows = db.conn.execute("SELECT t_s, speed_mps, hr_bpm" + inc + " FROM endurance_samples"
                               " WHERE session_id = ? ORDER BY t_s", (sess.id,)).fetchall()
        out["t"] = [r[0] for r in rows]
        out["lines"] = [(tr("Velocidade (km/h)", "Speed (km/h)"),
                         [(r[1] or 0) * 3.6 for r in rows], (108, 170, 220)),
                        (tr("FC (bpm)", "HR (bpm)"), [r[2] or 0 for r in rows], (214, 54, 128))]
        if any(r[3] for r in rows):             # a inclinação escolhida na passadeira
            out["lines"].append((tr("Inclinação (%)", "Incline (%)"),
                                 [r[3] or 0 for r in rows], (120, 200, 150)))
    elif sess.kind == "strength":
        out["t"] = [t for t, *_x in sess.samples]
        out["lines"] = [(tr("FC (bpm)", "HR (bpm)"), [h or 0 for *_x, h in sess.samples],
                         (214, 54, 128))]
    return out


def target_line(db, sess: fbm.Session, t: list[float]) -> list[float] | None:
    """O alvo de cada segundo, na unidade da série principal (W ou km/h)."""
    brief = fbm.prescribed(db, sess)
    if brief is None or not t or sess.sport == "gym":
        return None
    wins = block_windows(db, sess, brief)
    ctx = it.Context.from_db(db, sess.sport)
    out = []
    for x in t:
        val = 0.0
        for b, (a, z) in zip(brief.raw_blocks, wins):
            if a <= x < z and b.lo is not None:
                frac = (x - a) / max(1.0, z - a)
                hi = b.hi if b.hi is not None else b.lo
                pct = b.lo + (hi - b.lo) * frac
                if sess.sport in ("cycling", "rowing"):
                    ftp = sess.ftp_w or (ctx.row_ftp_w if sess.sport == "rowing" else ctx.ftp_w)
                    val = pct / 100.0 * ftp
                else:
                    val = ctx.speed_mps(pct) * 3.6
                break
        out.append(val)
    return out


def duration_text(seconds: float) -> str:
    return hms(max(0.0, seconds))
