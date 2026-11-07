"""«Métricas de evolução»: como o atleta está a mudar (as métricas de sessão
são as que se veem durante um treino). Três separadores:

* **Forma e fadiga** — CTL, ATL e TSB de hoje, como no TrainingPeaks/WKO,
  e o gráfico (Carga e prontidão);
* **Corrida** — eficiência, desacoplamento ritmo:FC, durabilidade, avisos da
  progressão da carga, previsões de prova e zonas de ritmo (80/20, Friel,
  Daniels);
* **Prontidão** — HRV, FC em repouso e sono face à linha de base.
"""
from __future__ import annotations

from datetime import date

from velo.core import evolution as ev
from velo.core import intensity as it
from velo.core import stats
from velo.core.i18n import t, tr
from velo.core.units import hms
from velo.ui.app import Screen
from velo.ui.widgets import Item


class EvolutionScreen(Screen):
    TABBED = True
    TAB_KEYS = ("form", "running", "readiness")

    def __init__(self, app, tab: int = 0):
        super().__init__(app)
        self.tab = tab
        if self.tabs is not None:
            self.tabs.select(tab)

    def tab_labels(self) -> list[str]:
        return [tr("Forma e fadiga", "Form and fatigue"), tr("Corrida", "Running"),
                tr("Prontidão", "Readiness")]

    def enter(self) -> None:
        k = self.TAB_KEYS[self.tab % 3]
        rows = getattr(self, f"_{k}")()
        self.chrome.set(tr("Métricas de evolução", "Progress metrics"),
                        tr("Como estás a mudar ao longo do tempo (as métricas de sessão são as "
                           "do ecrã do treino)", "How you change over time (session metrics "
                           "are the ones on the workout screen)"), self.footer())
        self.list.set_items(rows, keep_index=True)

    # --------------------------------------------------------- forma

    def _form(self) -> list[Item]:
        a = self.app
        series = stats.fitness(a.db, 43)
        rows = [Item(tr("Hoje (todos os desportos)", "Today (all sports)"), header=True)]
        if not series:
            rows.append(Item(tr("Ainda sem carga", "No load yet"), enabled=False))
        else:
            cur = series[-1]
            week = series[-8] if len(series) >= 8 else series[0]
            rows += [
                Item(tr("Fitness (CTL)", "Fitness (CTL)"), value=f"{cur['ctl']:.1f}",
                     detail=tr("média exponencial da carga a 42 dias", "42-day exponential "
                               "average of the load"), enabled=False),
                Item(tr("Fadiga (ATL)", "Fatigue (ATL)"), value=f"{cur['atl']:.1f}",
                     detail=tr("média exponencial a 7 dias", "7-day exponential average"),
                     enabled=False),
                Item(tr("Forma (TSB)", "Form (TSB)"), value=f"{cur['tsb']:+.1f}",
                     detail=tr("CTL − ATL de ontem (a forma com que entras hoje) · {s}",
                               "yesterday's CTL − ATL (the form you start today with) · {s}",
                               s=t(f"form.{stats.form_state(cur['tsb'])}")), enabled=False),
                Item(tr("Ramp (7 dias)", "Ramp (7 days)"), value=f"{cur['ctl'] - week['ctl']:+.1f}",
                     detail=tr("quanto o fitness subiu na última semana", "how much fitness "
                               "rose in the last week"), enabled=False),
                Item(tr("Gráfico de forma, fadiga e carga", "Form, fatigue and load chart"),
                     detail=tr("Enter abre (Carga e prontidão)", "Enter opens (Load and "
                               "readiness)"), action=self._chart)]
        rows += [Item(tr("Como se calcula", "How it is calculated"), header=True),
                 Item(tr("Igual ao TrainingPeaks e ao WKO (Coggan)",
                         "Same as TrainingPeaks and WKO (Coggan)"),
                      detail=tr("TSS/rTSS/sTSS por sessão; constantes de 42 e 7 dias; atividades "
                                "importadas sem duplicar",
                                "TSS/rTSS/sTSS per session; 42 and 7-day constants; imported "
                                "activities without duplicates; starting CTL/ATL in Settings → "
                                "Athlete"), enabled=False)]
        return rows

    def _chart(self) -> None:
        from velo.ui.load_screens import LoadReadinessScreen
        self.app.push(LoadReadinessScreen(self.app))

    # -------------------------------------------------------- corrida

    def _running(self) -> list[Item]:
        a = self.app
        rows: list[Item] = []
        tr_ = ev.running_trends(a.db)
        rows.append(Item(tr("Eficiência (últimos 90 dias)", "Efficiency (last 90 days)"),
                         header=True))
        ef = tr_["ef"]
        if ef:
            last = ef[-1][1]
            avg = sum(v for _d, v in ef) / len(ef)
            rows.append(Item(tr("Fator de eficiência (EF)", "Efficiency factor (EF)"),
                             value=f"{last:.2f}",
                             detail=tr("m/min por batimento · média {m:.2f} · mais alto é melhor",
                                       "m/min per beat · average {m:.2f} · higher is better",
                                       m=avg), enabled=False))
        dc = tr_["decoupling"]
        if dc:
            rows.append(Item(tr("Desacoplamento ritmo:FC", "Pace:HR decoupling"),
                             value=f"{dc[-1][1]:.1f} %",
                             detail=tr("a última corrida longa · abaixo de 5 % = base aeróbia "
                                       "sólida", "the last long run · under 5 % = solid "
                                       "aerobic base"), enabled=False))
        du = tr_["durability"]
        if du:
            rows.append(Item(tr("Durabilidade", "Durability"), value=f"{du[-1][1]:.1f} %",
                             detail=tr("quanto a eficiência caiu no último quarto (treinos ≥ "
                                       "75 min)", "how much efficiency fell in the last "
                                       "quarter (runs ≥ 75 min)"), enabled=False))
        if not (ef or dc or du):
            rows.append(Item(tr("Precisa de corridas com FC", "Needs runs with heart rate"),
                             enabled=False))
        rows.append(Item(tr("Progressão da carga", "Load progression"), header=True))
        warns = ev.load_warnings(a.db)
        for w in warns:
            rows.append(Item("⚠ " + w, enabled=False))
        if not warns:
            rows.append(Item(tr("Sem avisos: a carga está a subir com calma",
                                "No warnings: the load is rising calmly"), enabled=False))
        rows.append(Item(tr("Previsões de prova", "Race predictions"), header=True))
        pred = ev.predictions(a.db)
        if pred["basis"] is not None:
            b = pred["basis"]
            for name, _d, secs in pred["races"]:
                rows.append(Item(name, value=hms(secs),
                                 detail=tr("Riegel, a partir de {k} km em {t} ({d})",
                                           "Riegel, from {k} km in {t} ({d})",
                                           k=f"{b.distance_m / 1000:.1f}", t=hms(b.seconds),
                                           d=b.day.strftime("%d/%m")), enabled=False))
            if pred.get("tanda"):
                rows.append(Item(tr("Maratona (Tanda, pelo volume)", "Marathon (Tanda, by "
                                    "volume)"), value=hms(pred["tanda"]),
                                 detail=tr("{k} km por semana nas últimas 8 semanas",
                                           "{k} km a week over the last 8 weeks",
                                           k=f"{pred['weekly_km']:.0f}"), enabled=False))
        else:
            rows.append(Item(tr("Precisa de uma corrida de 3 km ou mais nos últimos 90 dias",
                                "Needs a run of 3 km or more in the last 90 days"),
                             enabled=False))
        ctx = it.Context.from_db(a.db, "running")
        vdot = None
        if pred["basis"] is not None:
            vdot = ev.daniels_vdot(pred["basis"].distance_m, pred["basis"].seconds)
        for method, zones in ev.pace_zones(ctx.run_pace_s, vdot).items():
            extra = f" · VDOT {vdot:.1f}" if method == "Daniels" and vdot else ""
            rows.append(Item(tr("Zonas de ritmo · {m}", "Pace zones · {m}", m=method) + extra,
                             header=True))
            for name, lo, hi in zones:
                rows.append(Item(name, value=ev.zone_text(lo, hi), enabled=False))
        return rows

    # ------------------------------------------------------ prontidão

    def _readiness(self) -> list[Item]:
        r = ev.readiness(self.app.db, date.today())
        rows = [Item(tr("Hoje", "Today"), header=True)]
        if r["state"] is None:
            rows.append(Item(tr("Sem dados de hoje", "No data for today"),
                             detail=tr("HRV, FC em repouso e sono (diário da Saúde, "
                                       "HRV4Training ou Garmin)", "HRV, resting HR and sleep "
                                       "(Health log, HRV4Training or Garmin)"), enabled=False))
        else:
            rows.append(Item(tr(*ev.READINESS_TEXT[r["state"]]), enabled=False))
            for line in r["lines"]:
                rows.append(Item(line, enabled=False))
        rows += [Item(tr("Regras", "Rules"), header=True),
                 Item(tr("HRV: média de 7 dias dentro do normal de 60 dias (± 0,5 desvio)",
                         "HRV: 7-day average within the 60-day normal (± 0.5 SD)"),
                      enabled=False),
                 Item(tr("FC em repouso: 5 bpm acima da linha de base é um sinal",
                         "Resting HR: 5 bpm above baseline is a sign"), enabled=False),
                 Item(tr("Sono: 1 h abaixo do costume é um sinal",
                         "Sleep: 1 h below usual is a sign"), enabled=False)]
        return rows
