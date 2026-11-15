"""O separador **Perfil** de cada desporto: como te posicionas (ver `core/profile.py`).

Ciclismo: o tipo de ciclista e os pontos por duração. Ginásio: o perfil de força, capacidade a
capacidade, com as deficiências e os planos que as tratam. Remo, corrida e natação:
velocidade contra resistência. As capacidades para a vida continuam no menu Longevidade.
"""
from __future__ import annotations

from perennia.core import options, profile
from perennia.core.i18n import tr
from perennia.core.units import hms
from perennia.ui.widgets import Item


def _pts(score: float | None) -> str:
    return f"{profile.bar(score)}  " + ("—" if score is None else f"{score:.0f}")


def _longevity_row(app) -> Item:
    def go() -> None:
        from perennia.ui.longevity_screens import LongevityMenu
        app.push(LongevityMenu(app))
    return Item(tr("Capacidades para a vida → Longevidade", "Capacities for life → Longevity"),
                detail=tr("o perfil daqui é o do desporto; aeróbia, força, VO2máx, mobilidade e "
                          "estabilidade para envelhecer bem estão no menu Longevidade",
                          "this profile is the sport's; aerobic, strength, VO2max, mobility and "
                          "stability for ageing well are in the Longevity menu"), action=go,
                data="longevity")


def profile_items(app, sport: str) -> list[Item]:
    p = profile.of(app.db, sport)
    if sport == "cycling":
        return _cycling(app, p)
    if sport == "gym":
        return _gym(app, p)
    return _endurance(app, p)


def _cycling(app, p: dict) -> list[Item]:
    rows = [Item(tr("Tipo de ciclista", "Rider type"), value=p["type_name"],
                 detail=p["type_text"] or tr(
                     "faltam esforços máximos para te classificar (ver abaixo)",
                     "maximal efforts are missing to classify you (see below)"),
                 data="type"),
            Item(tr("A tua curva de potência (0 = sem treino, 100 = classe mundial)",
                    "Your power curve (0 = untrained, 100 = world class)"), header=True)]
    for r in p["rows"]:
        if r["score"] is None:
            detail = tr("por medir: faz um esforço máximo desta duração com medidor de potência",
                        "not measured: do a maximal effort of this duration with a power "
                        "meter")
        else:
            detail = f"{r['wkg']:.2f} W/kg · {r['watts']:.0f} W · {r['level']}" + (
                f" · {r['date']}" if r["date"] else "") + (
                f" · {r['source']}" if r["source"] else "")
        rows.append(Item(r["name"], value=_pts(r["score"]), detail=detail,
                         data=("duration", r["key"])))
    if p["strongest"] and p["weakest"] and p["strongest"] is not p["weakest"]:
        rows.append(Item(tr("Ponto forte e ponto fraco", "Strong and weak point"), header=True))
        rows.append(Item(tr("Mais forte", "Strongest"), value=p["strongest"]["name"],
                         enabled=False))
        rows.append(Item(tr("Mais fraco", "Weakest"), value=p["weakest"]["name"],
                         detail=p["advice"], data="weakest"))
    ref = options.choice_label(options.BY_KEY["profile_reference"], p["reference"])
    rows.append(Item(tr("Como se calcula", "How it is computed"), header=True))
    rows.append(Item(tr("Melhores esforços dos últimos {n} dias, a dividir por {k:g} kg",
                        "Best efforts of the last {n} days, divided by {k:g} kg", n=p["days"],
                        k=p["weight_kg"]),
                     detail=tr("tabela de referência: {r} (aproximação da tabela de perfil de "
                               "potência de Coggan) · muda-se em Definições → Avançado → Perfil "
                               "por desporto", "reference table: {r} (an approximation of "
                               "Coggan's power profile table) · change it in Settings → "
                               "Advanced → Sport profile", r=ref), enabled=False))
    rows.append(_longevity_row(app))
    return rows


def _gym(app, p: dict) -> list[Item]:
    rows = [Item(tr("O teu perfil de força", "Your strength profile"), value="",
                 detail=p["summary"], data="summary"),
            Item(tr("Capacidades (0–100; 100 = bom nível, definido nas opções)",
                    "Capacities (0–100; 100 = good level, set in the options)"), header=True)]
    for d in p["dims"]:
        bits = []
        if d["measured"]:
            bits.append(tr("medido: ", "measured: ") + ", ".join(d["measured"]))
        bits.append(tr("treino: ", "training: ") + d["trained"])
        if not d["measured"]:
            bits.append(d["to_measure"])
        rows.append(Item(d["name"], value=_pts(d["score"]) + f"  {d['level']}",
                         detail=" · ".join(bits), data=("dim", d["key"])))
    if p["balance"]:
        rows.append(Item(tr("Equilíbrio", "Balance"), header=True))
        for b in p["balance"]:
            rows.append(Item(b[0].upper() + b[1:], enabled=False))
    if p["advice"]:
        rows.append(Item(tr("Onde tens mais deficiências — e o que fazer",
                            "Your biggest gaps — and what to do"), header=True))
        for a in p["advice"]:
            def go(key=a["plan"]) -> None:
                from perennia.ui.program_screens import ProgramDetail
                app.push(ProgramDetail(app, key))
            rows.append(Item(a["name"], value=tr("abrir o plano", "open the plan")
                             if a["plan"] else "", detail=a["text"],
                             action=go if a["plan"] else None, data=("advice", a["dim"])))
    w = int(options.get(app.db, "profile_measured_weight_pct"))
    rows.append(Item(tr("Como se calcula", "How it is computed"), header=True))
    rows.append(Item(tr("{s} dias com sessões nos últimos {n} dias; treino das últimas {w} "
                        "semanas", "{s} days with sessions in the last {n} days; training of "
                        "the last {w} weeks", s=p["sessions"], n=p["days"], w=p["weeks"]),
                     detail=tr("com medição: {a} % o que mediste, {b} % o que treinas; sem "
                               "medição: só o treino · os níveis estão em Definições → "
                               "Avançado → Perfil por desporto", "with a measurement: {a} % "
                               "what you measured, {b} % what you train; without: training "
                               "only · levels are in Settings → Advanced → Sport profile",
                               a=w, b=100 - w),
                     enabled=False))
    rows.append(_longevity_row(app))
    return rows


def _endurance(app, p: dict) -> list[Item]:
    units = app.db.get("units", "metric")
    rows = [Item(tr("Perfil", "Profile"), value=p["type_name"],
                 detail=p["type_text"] or tr(
                     "precisas de pelo menos uma sessão curta (< 20 min) e uma mais longa, com "
                     "distância, para te classificar", "you need at least one short session "
                     "(< 20 min) and a longer one, with distance, to be classified"),
                 data="type"),
            Item(tr("As tuas melhores sessões por duração", "Your best sessions by duration"),
                 header=True)]
    for r in p["rows"]:
        b = r["best"]
        if b is None:
            rows.append(Item(r["name"], value="—", enabled=False))
            continue
        kmh = b["speed"] * 3.6
        speed = f"{kmh:.1f} km/h" if units == "metric" else f"{kmh / 1.609344:.1f} mph"
        if p["sport"] in ("running", "swimming", "rowing"):
            per = 100 if p["sport"] == "swimming" else 500 if p["sport"] == "rowing" else 1000
            pace = per / b["speed"]
            label = {100: "/100 m", 500: "/500 m", 1000: "/km"}[per]
            speed = f"{int(pace // 60)}:{int(pace % 60):02d} {label}"
        rows.append(Item(r["name"], value=speed,
                         detail=f"{b['distance'] / 1000:.2f} km · {hms(b['seconds'])} · "
                                f"{b['date']}", enabled=False))
    rows.append(Item(tr("Como se calcula", "How it is computed"), header=True))
    rows.append(Item(tr("{s} sessões nos últimos {n} dias", "{s} sessions in the last {n} days",
                        s=p["sessions"], n=p["days"]),
                     detail=tr("compara a velocidade média da tua melhor sessão curta com a da "
                               "melhor longa; são sessões inteiras, não esforços máximos: é uma "
                               "leitura aproximada", "compares the average speed of your best "
                               "short session with the best long one; these are whole sessions, "
                               "not maximal efforts: an approximate reading"), enabled=False))
    rows.append(_longevity_row(app))
    return rows
