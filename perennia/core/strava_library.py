"""A biblioteca de segmentos do Strava: ficam guardados **neste computador**, com o traçado, o
teu recorde e (com subscrição Strava) todos os teus esforços, para usares sem internet.

Entram por três vias, todas com internet **uma vez**:
* **por ID ou ligação** (`strava.com/segments/12345`), à mão, vários de uma vez;
* **os teus favoritos ⭐** do Strava;
* **a pesquisa por rota** (a «Atualizar do Strava» da rota): o que encontra fica também aqui.

Depois, **sem rede**, `link_route` liga à rota os segmentos da biblioteca que ela percorre no mesmo
sentido (e segue o traçado), e a Perennia conta-os no treino como os outros. Corre sozinho ao
importar um .gpx (opção `strava_auto_link`).

Só leitura e só dos teus dados. Pelo acordo da API do Strava, nada daqui vai para o agente de IA.
"""
from __future__ import annotations

import re
from typing import Callable

from . import options, segments
from .db import Database, now_iso
from .i18n import tr

_LINK_RE = re.compile(r"segments?/(\d{1,12})(?!\d)")
_NUM_RE = re.compile(r"^#?(\d{1,12})$")


class ImportReport(dict):
    """added, updated, efforts, failed [(id, msg)], remaining [ids], rate_limited,
    no_subscription, private_skipped."""

    def __init__(self):
        super().__init__(added=0, updated=0, efforts=0, failed=[], remaining=[],
                        rate_limited=False, no_subscription=False)

    def text(self) -> str:
        t = tr("{a} novos · {u} atualizados · {e} esforços", "{a} new · {u} updated · {e} efforts",
               a=self["added"], u=self["updated"], e=self["efforts"])
        if self["no_subscription"]:
            t += " · " + tr("sem subscrição Strava: só o PR", "no Strava subscription: PR only")
        if self["failed"]:
            t += " · " + tr("{n} falharam", "{n} failed", n=len(self["failed"]))
        if self["remaining"]:
            t += " · " + tr("faltam {n} (volta a importar)", "{n} left (import again)",
                            n=len(self["remaining"]))
        if self["rate_limited"]:
            t += " · " + tr("limite do Strava: tenta daqui a 15 min",
                            "Strava limit: try again in 15 min")
        return t


# ------------------------------------------------------------------ entrada


def parse_ids(text: str) -> list[int]:
    """Os IDs de segmentos num texto: ligações (`…/segments/12345`), números soltos, separados
    por espaços, vírgulas ou linhas. Sem repetidos, pela ordem em que aparecem."""
    out: list[int] = []
    for tok in re.split(r"[\s,;]+", text or ""):
        m = _LINK_RE.search(tok) or _NUM_RE.match(tok.strip())
        if m and int(m.group(1)) not in out:
            out.append(int(m.group(1)))
    return out


# ------------------------------------------------------------------ guardar


def save(db: Database, data: dict, origin: str = "id", starred: bool | None = None) -> bool:
    """Guarda (ou atualiza) um segmento a partir da resposta do Strava (`/segments/{id}` ou um
    resumo da pesquisa/favoritos). Devolve True se era novo. O que a resposta não traz
    (PR, traçado…) não apaga o que já havia."""
    segments.ensure(db)
    sid = int(data["id"])
    old = db.conn.execute("SELECT * FROM strava_library WHERE segment_id = ?", (sid,)).fetchone()
    stats = data.get("athlete_segment_stats") or {}
    s = data.get("start_latlng") or [None, None]
    e = data.get("end_latlng") or [None, None]
    poly = (data.get("map") or {}).get("polyline") or data.get("points") or data.get("polyline")
    row = {
        "name": data.get("name") or (old["name"] if old else str(sid)),
        "activity_type": (data.get("activity_type") or "").lower() or None,
        "distance_m": data.get("distance"),
        "avg_grade": data.get("average_grade", data.get("avg_grade")),
        "max_grade": data.get("maximum_grade"),
        "elev_gain_m": data.get("total_elevation_gain", data.get("elev_difference")),
        "climb_cat": data.get("climb_category"),
        "start_lat": s[0], "start_lon": s[1], "end_lat": e[0], "end_lon": e[1],
        "polyline": poly,
        "city": data.get("city"), "country": data.get("country"),
        "pr_s": stats.get("pr_elapsed_time"),
        "pr_date": (stats.get("pr_date") or "")[:10] or None,
        "effort_count": stats.get("effort_count"),
        "kom": (data.get("xoms") or {}).get("kom"),
    }
    if old is None:
        cols = ["segment_id", "origin", "starred", "private", "fetched_at"] + list(row)
        vals = [sid, origin, int(bool(starred)), int(bool(data.get("private"))), now_iso()] + \
            list(row.values())
        db.conn.execute(f"INSERT INTO strava_library({', '.join(cols)}) VALUES "
                        f"({', '.join('?' * len(cols))})", vals)
    else:
        sets, vals = [], []
        for k, v in row.items():
            if v is not None and v != "":
                sets.append(f"{k} = ?")
                vals.append(v)
        if origin in ("id", "starred") and old["origin"] == "route":
            sets.append("origin = ?")
            vals.append(origin)
        if starred is not None:
            sets.append("starred = ?")
            vals.append(int(bool(starred)))
        if "private" in data:
            sets.append("private = ?")
            vals.append(int(bool(data.get("private"))))
        if stats or data.get("map"):
            sets.append("fetched_at = ?")
            vals.append(now_iso())
        if sets:
            db.conn.execute(f"UPDATE strava_library SET {', '.join(sets)} WHERE segment_id = ?",
                            vals + [sid])
    db.conn.commit()
    return old is None


def save_efforts(db: Database, segment_id: int, items: list[dict]) -> int:
    """Os esforços (`/segment_efforts`) deste segmento; repetidos (mesmo id) não duplicam."""
    n = 0
    for e in items:
        try:
            eid = int(e["id"])
            elapsed = int(e["elapsed_time"])
        except (KeyError, TypeError, ValueError):
            continue
        cur = db.conn.execute(
            "INSERT OR REPLACE INTO strava_library_efforts(effort_id, segment_id, start_date,"
            " elapsed_s, moving_s, avg_watts, avg_hr, activity_id) VALUES (?,?,?,?,?,?,?,?)",
            (eid, int(segment_id), e.get("start_date_local") or e.get("start_date"), elapsed,
             e.get("moving_time"), e.get("average_watts"), e.get("average_heartrate"),
             (e.get("activity") or {}).get("id")))
        n += cur.rowcount
    db.conn.execute("UPDATE strava_library SET efforts_at = ? WHERE segment_id = ?",
                    (now_iso(), int(segment_id)))
    db.conn.commit()
    return n


# ------------------------------------------------------------------ importar


def _fetch_efforts(client, sid: int, limit: int) -> list[dict]:
    out: list[dict] = []
    page = 1
    while len(out) < limit:
        chunk = client.efforts(sid, page=page, per_page=200)
        if not chunk:
            break
        out += chunk
        if len(chunk) < 200:
            break
        page += 1
    return out[:limit]


def import_ids(db: Database, client, ids: list[int], *, origin: str = "id",
               starred: bool | None = None, efforts: bool | None = None,
               progress: Callable[[int, int], None] | None = None) -> ImportReport:
    """Vai ao Strava buscar cada segmento (o traçado, a distância, o teu PR) e, se puderes,
    os teus esforços. No máximo `strava_import_batch` por vez; o resto fica em `remaining`."""
    from ..io.strava import StravaError
    segments.ensure(db)
    rep = ImportReport()
    batch = int(options.get(db, "strava_import_batch"))
    want_efforts = options.get(db, "strava_import_efforts") if efforts is None else efforts
    cap = int(options.get(db, "strava_efforts_max"))
    todo = list(dict.fromkeys(int(i) for i in ids))
    for n, sid in enumerate(todo):
        if n >= batch:
            rep["remaining"] = todo[n:]
            break
        if progress:
            progress(n + 1, min(len(todo), batch))
        try:
            det = client.segment(sid)
            if not det or "id" not in det:
                raise StravaError(tr("não existe ou é privado", "does not exist or is private"))
        except StravaError as e:
            if e.status == 429:
                rep["rate_limited"] = True
                rep["remaining"] = todo[n:]
                break
            rep["failed"].append((sid, str(e)))
            continue
        rep["added" if save(db, det, origin, starred) else "updated"] += 1
        if want_efforts and not rep["no_subscription"]:
            try:
                rep["efforts"] += save_efforts(db, sid, _fetch_efforts(client, sid, cap))
            except StravaError as e:
                if e.status == 429:
                    rep["rate_limited"] = True
                    rep["remaining"] = todo[n + 1:]
                    break
                if e.status in (402, 403):
                    rep["no_subscription"] = True    # precisa de subscrição Strava
    return rep


def import_starred(db: Database, client, progress=None) -> ImportReport:
    """Os teus favoritos ⭐ do Strava (nomes e traçado), mais os esforços se puderes."""
    ids: list[int] = []
    page = 1
    while True:
        chunk = client.starred(page=page, per_page=200)
        ids += [int(x["id"]) for x in chunk if "id" in x]
        if len(chunk) < 200 or page >= 10:
            break
        page += 1
    return import_ids(db, client, ids, origin="starred", starred=True, progress=progress)


def refresh(db: Database, client, ids: list[int] | None = None, progress=None) -> ImportReport:
    """Atualiza o PR (e os esforços) de segmentos que já estão na biblioteca."""
    if ids is None:
        ids = [r["segment_id"] for r in db.conn.execute(
            "SELECT segment_id FROM strava_library ORDER BY COALESCE(fetched_at, '')")]
    return import_ids(db, client, ids, origin="id", progress=progress)


# ------------------------------------------------------------------ ler


def library(db: Database) -> list[dict]:
    """A biblioteca (A–Z), com quantos esforços e em quantas rotas está ligada."""
    segments.ensure(db)
    rows = db.conn.execute(
        "SELECT l.*, (SELECT COUNT(*) FROM strava_library_efforts e WHERE e.segment_id ="
        " l.segment_id) AS n_efforts, (SELECT COUNT(*) FROM strava_segments s WHERE s.segment_id"
        " = l.segment_id) AS n_routes FROM strava_library l ORDER BY lower(l.name)").fetchall()
    return [dict(r) for r in rows]


def get(db: Database, segment_id: int) -> dict | None:
    segments.ensure(db)
    r = db.conn.execute("SELECT * FROM strava_library WHERE segment_id = ?",
                        (int(segment_id),)).fetchone()
    return dict(r) if r else None


def library_efforts(db: Database, segment_id: int) -> list[dict]:
    segments.ensure(db)
    return [dict(r) for r in db.conn.execute(
        "SELECT * FROM strava_library_efforts WHERE segment_id = ? ORDER BY elapsed_s",
        (int(segment_id),))]


def delete(db: Database, segment_id: int) -> None:
    """Tira da biblioteca (e das rotas a que estava ligado, e os esforços importados). Os tempos
    que fizeste na Perennia ficam."""
    segments.ensure(db)
    sid = int(segment_id)
    for tbl in ("strava_library_efforts", "strava_segments"):
        db.conn.execute(f"DELETE FROM {tbl} WHERE segment_id = ?", (sid,))
    db.conn.execute("DELETE FROM strava_library WHERE segment_id = ?", (sid,))
    db.conn.commit()


# ------------------------------------------------------------------ ligar às rotas


def link_route(db: Database, route_id: str) -> dict:
    """Liga à rota os segmentos da biblioteca que ela percorre no mesmo sentido (sem rede).
    Os que já estavam ligados atualizam-se; os que a rota já não percorre ficam como estão
    (a pesquisa por rota é que refaz a lista). Devolve {checked, linked}."""
    segments.ensure(db)
    points = db.route_points(route_id)
    rep = {"checked": 0, "linked": 0}
    if not points:
        return rep
    lat0 = min(p.lat for p in points) - 0.01
    lat1 = max(p.lat for p in points) + 0.01
    lon0 = min(p.lon for p in points) - 0.01
    lon1 = max(p.lon for p in points) + 0.01
    rows = db.conn.execute(
        "SELECT * FROM strava_library WHERE start_lat BETWEEN ? AND ? AND start_lon BETWEEN ?"
        " AND ?", (lat0, lat1, lon0, lon1)).fetchall()      # só os de perto (barato, sem rede)
    for r in rows:
        rep["checked"] += 1
        seg = {"start_latlng": [r["start_lat"], r["start_lon"]],
               "end_latlng": [r["end_lat"], r["end_lon"]], "distance": r["distance_m"],
               "polyline": r["polyline"]}
        where = segments.match(points, seg)
        if not where:
            continue
        db.conn.execute(
            "INSERT OR REPLACE INTO strava_segments(route_id, segment_id, name, distance_m,"
            " avg_grade, climb_cat, start_m, end_m, pr_s, pr_date, effort_count, kom, fetched_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (route_id, r["segment_id"], r["name"], r["distance_m"], r["avg_grade"],
             r["climb_cat"], where[0], where[1], r["pr_s"], r["pr_date"], r["effort_count"],
             r["kom"], r["fetched_at"] or now_iso()))
        rep["linked"] += 1
    db.conn.commit()
    return rep


def link_all(db: Database) -> dict:
    """Refaz a ligação em todas as rotas (depois de importares segmentos novos)."""
    tot = {"routes": 0, "linked": 0}
    for r in db.routes():
        tot["routes"] += 1
        tot["linked"] += link_route(db, r["id"])["linked"]
    return tot


def auto_link(db: Database, route_id: str) -> int:
    """Chamado ao importar uma rota: liga a biblioteca se a opção estiver ligada. Nunca falha."""
    try:
        if not options.get(db, "strava_auto_link"):
            return 0
        return link_route(db, route_id)["linked"]
    except Exception:
        return 0
