"""Feedback automático do treino do(s) dia(s) anterior(es), no diário de saúde.

Para cada sessão concluída nos dias anteriores ao do diário junta-se: o que foi (a frase da
sessão), o veredito da análise offline (a mesma do fim da sessão, com o feedback que deste, se
houver) e o que isso pede à recuperação (sono, hidratação…). Sem rede nem IA."""
from __future__ import annotations

from datetime import date, timedelta

from . import calendar_view as cv
from . import feedback as fbm
from . import options
from .i18n import tr


def days_back(db) -> int:
    return int(options.get(db, "health_feedback_days"))


def enabled(db) -> bool:
    return bool(options.get(db, "health_day_feedback"))


def _recovery_hint(sport: str, load: float | None, rpe, pain) -> str:
    hard = (rpe is not None and rpe >= 8) or (load or 0) >= 100
    if pain is not None and pain >= 4:
        return tr("Dores a vigiar: se o diário de hoje mostrar sono curto, alivia.",
                  "Pain to watch: if today's log shows short sleep, ease off.")
    if hard:
        return tr("Sessão exigente: dá prioridade ao sono, à hidratação e às proteínas hoje.",
                  "Demanding session: prioritise sleep, hydration and protein today.")
    return ""


def for_day(db, day: date) -> list[dict]:
    """As sessões dos `health_feedback_days` dias antes de `day`, com o resumo de cada uma."""
    if not enabled(db):
        return []
    d1 = day - timedelta(days=1)
    d0 = day - timedelta(days=days_back(db))
    out = []
    for e in cv.sessions_between(db, d0, d1):
        sess = fbm.load_session(db, e.kind, e.id)
        if sess is None:
            continue
        fb = fbm.get(db, e.kind, e.id) or {}
        try:
            res = fbm.analyse(db, sess, fb)
        except Exception:
            res = {}
        out.append({"day": e.day.isoformat(), "kind": e.kind, "id": e.id, "sport": sess.sport,
                    "title": e.title, "text": fbm.session_text(sess),
                    "verdict": res.get("verdict") or "", "useful": res.get("useful"),
                    "has_feedback": bool(fb),
                    "hint": _recovery_hint(sess.sport, sess.load, fb.get("rpe"),
                                           fb.get("pain"))})
    return out
