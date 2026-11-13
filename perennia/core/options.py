"""As opções afináveis da Perennia (Definições → Avançado).

Cada valor que antes estava «escrito no código» (quanto tempo até a pausa automática, a
tolerância de um bloco de treino, o passo da carga, os limites da Análise AdHoc, os preços dos
tokens do agente…) é aqui uma `Opt`: a chave nas definições, o valor por omissão, os limites, o
passo das setas e o texto que as Definições mostram. **É a única fonte** dos valores por omissão:
os módulos que os usam leem-nos daqui (`get`), ou recebem-nos no arranque e depois de
guardar (`apply`: as opções com `binds` põem o valor na constante do módulo, que o código lê
sempre no momento de usar).

Tudo fica na tabela `settings` da base de dados local (nada de ficheiros à parte): o backup
leva-as com as «Definições» (e as de `strava_`, `garmin_` e `agent_` com as «Ligações»).
Nenhuma opção guarda segredos.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from .i18n import tr

INT, FLOAT, BOOL, CHOICE, TEXT = "int", "float", "bool", "choice", "text"


@dataclass(frozen=True)
class Opt:
    key: str
    group: str
    pt: str
    en: str
    kind: str
    default: Any
    lo: float | None = None
    hi: float | None = None
    step: float = 1
    choices: tuple = ()                  # (valor, pt, en) — só nas opções de escolha
    unit: str = ""
    hint_pt: str = ""
    hint_en: str = ""
    binds: tuple = ()                    # (módulo, constante) onde `apply` põe o valor

    @property
    def label(self) -> str:
        return tr(self.pt, self.en)

    @property
    def hint(self) -> str:
        return tr(self.hint_pt, self.hint_en)


# --------------------------------------------------------------------------- grupos

GROUPS: dict[str, tuple[str, str]] = {
    "sessions": ("Sessões e aparelhos", "Sessions and devices"),
    "workouts": ("Treinos e importação", "Workouts and import"),
    "links": ("Ligações externas", "External connections"),
    "adhoc": ("Análise AdHoc", "AdHoc analysis"),
    "agent": ("Agente de IA e tokens", "AI agent and tokens"),
    "health": ("Saúde e pressão arterial", "Health and blood pressure"),
    "coach": ("Treinador e Assistente de saúde", "Coach and Health assistant"),
    "data": ("Dados e backups", "Data and backups"),
}


def group_name(group: str) -> str:
    pt, en = GROUPS[group]
    return tr(pt, en)


def _o(key, group, pt, en, kind, default, **kw) -> Opt:
    return Opt(key, group, pt, en, kind, default, **kw)


OPTIONS: tuple[Opt, ...] = (
    # ------------------------------------------------------------ sessões e aparelhos
    _o("session_countdown_s", "sessions", "Contagem antes de começar", "Countdown before start",
       INT, 15, lo=0, hi=60, step=1, unit="s",
       hint_pt="segundos de contagem antes de qualquer sessão (0 = começa logo)",
       hint_en="seconds of countdown before any session (0 = starts at once)"),
    _o("auto_pause_after_s", "sessions", "Pausa automática ao fim de", "Auto-pause after",
       FLOAT, 3.0, lo=1.0, hi=30.0, step=0.5, unit="s",
       hint_pt="segundos sem pedalar até a sessão pausar (se a pausa automática estiver ligada)",
       hint_en="seconds without pedalling before the session pauses (if auto-pause is on)",
       binds=(("perennia.core.ride", "AUTO_PAUSE_AFTER_S"),)),
    _o("device_stale_after_s", "sessions", "Aparelho sem dados ao fim de",
       "Device silent after", FLOAT, 5.0, lo=2.0, hi=30.0, step=0.5, unit="s",
       hint_pt="segundos sem receber um valor até um sensor contar como perdido",
       hint_en="seconds without a reading before a sensor counts as lost",
       binds=(("perennia.io.hub", "STALE_AFTER_S"), ("perennia.io.rower", "STALE_AFTER_S"))),
    _o("ble_scan_s", "sessions", "Procura Bluetooth: duração", "Bluetooth scan: duration",
       FLOAT, 8.0, lo=3.0, hi=30.0, step=1.0, unit="s",
       hint_pt="quanto tempo a procura de aparelhos Bluetooth escuta (mais tempo encontra mais)",
       hint_en="how long the Bluetooth device scan listens (longer finds more)"),
    _o("ant_scan_s", "sessions", "Procura ANT+: duração", "ANT+ scan: duration",
       FLOAT, 12.0, lo=3.0, hi=60.0, step=1.0, unit="s",
       hint_pt="quanto tempo a procura de aparelhos ANT+ escuta (mais tempo encontra mais)",
       hint_en="how long the ANT+ device scan listens (longer finds more)"),
    _o("message_seconds", "sessions", "Duração dos avisos", "Notice duration", FLOAT, 6.0,
       lo=2.0, hi=20.0, step=0.5, unit="s",
       hint_pt="quanto tempo fica no topo a mensagem («Guardado», «Exportado»…)",
       hint_en="how long the message at the top stays («Saved», «Exported»…)"),
    _o("treadmill_start_speed_max_kmh", "sessions", "Passadeira: velocidade máxima à partida",
       "Treadmill: top start speed", FLOAT, 25.0, lo=8.0, hi=40.0, step=0.5, unit="km/h",
       hint_pt="o máximo que a lista de velocidades da passadeira oferece ao começar",
       hint_en="the highest speed the treadmill start list offers"),
    _o("strength_load_step_kg", "sessions", "Força: passo da carga", "Strength: load step",
       FLOAT, 2.5, lo=0.25, hi=20.0, step=0.25, unit="kg",
       hint_pt="quanto muda a carga de uma série com cada toque nas setas",
       hint_en="how much a set's load changes with each arrow press",
       binds=(("perennia.core.strength", "LOAD_STEP"),)),
    _o("strength_rpe_step", "sessions", "Força: passo do RPE", "Strength: RPE step", FLOAT, 0.5,
       lo=0.1, hi=1.0, step=0.1,
       hint_pt="quanto muda o RPE de uma série com cada toque nas setas",
       hint_en="how much a set's RPE changes with each arrow press",
       binds=(("perennia.core.strength", "RPE_STEP"),)),
    # ------------------------------------------------------------ treinos e importação
    _o("workout_tolerance_pct", "workouts", "Tolerância do alvo de potência",
       "Power target tolerance", FLOAT, 5.0, lo=1.0, hi=25.0, step=0.5, unit="%",
       hint_pt="± % do alvo que conta como «no alvo» durante um treino",
       hint_en="± % of the target that counts as «on target» during a workout",
       binds=(("perennia.core.workouts", "TOLERANCE_PCT"),)),
    _o("review_tolerance_pct", "workouts", "Tolerância na revisão da sessão",
       "Tolerance in the session review", FLOAT, 6.0, lo=1.0, hi=25.0, step=0.5, unit="%",
       hint_pt="± % do limiar, na revisão, quando o bloco não define outra",
       hint_en="± % of the threshold, in the review, when the block sets none",
       binds=(("perennia.core.session_review", "DEFAULT_TOL"),)),
    _o("export_freeride_pct", "workouts", "Exportar: potência do bloco «livre»",
       "Export: «free» block power", FLOAT, 50.0, lo=20.0, hi=100.0, step=5.0, unit="% FTP",
       hint_pt="os formatos .erg/.mrc não têm blocos livres: pedala-se a esta % do FTP",
       hint_en=".erg/.mrc have no free blocks: you ride at this % of FTP",
       binds=(("perennia.core.workout_export", "FREERIDE_PCT"),)),
    _o("gpx_resample_step_m", "workouts", "Rotas GPX: distância entre pontos",
       "GPX routes: spacing between points", FLOAT, 5.0, lo=1.0, hi=50.0, step=1.0, unit="m",
       hint_pt="as rotas importadas são reamostradas a esta distância (vale para as novas)",
       hint_en="imported routes are resampled at this spacing (applies to new ones)",
       binds=(("perennia.core.gpx", "RESAMPLE_STEP_M"),)),
    # ------------------------------------------------------------ ligações externas
    _o("strava_redirect_port", "links", "Strava: porta do retorno local", "Strava: local callback port",
       INT, 8723, lo=1024, hi=65535, step=1,
       hint_pt="a porta onde a Perennia espera o regresso do Strava (só nesta máquina)",
       hint_en="the port where Perennia waits for Strava to come back (this machine only)",
       binds=(("perennia.io.strava", "REDIRECT_PORT"),)),
    _o("garmin_sync_timeout_s", "links", "Garmin: tempo máximo de uma sincronização",
       "Garmin: sync time limit", INT, 3600, lo=60, hi=21600, step=60, unit="s",
       hint_pt="a sincronização é interrompida se demorar mais do que isto",
       hint_en="the sync is stopped if it takes longer than this",
       binds=(("perennia.core.garmin_sync", "SYNC_TIMEOUT_S"),)),
    # ------------------------------------------------------------ análise adhoc
    _o("adhoc_csv_sep", "adhoc", "CSV: separador de valores", "CSV: value separator", CHOICE, ";",
       choices=((";", "; (ponto e vírgula)", "; (semicolon)"), (",", ", (vírgula)", ", (comma)"),
                ("\t", "Tab", "Tab"), ("|", "| (barra)", "| (pipe)")),
       hint_pt="o que se propõe ao exportar (escolhe-se de novo em cada exportação)",
       hint_en="what is proposed when exporting (you can change it on each export)"),
    _o("adhoc_csv_decimal", "adhoc", "CSV: separador decimal", "CSV: decimal separator", CHOICE,
       ".", choices=((".", "«.» ponto", "«.» dot"), (",", "«,» vírgula", "«,» comma")),
       hint_pt="igual ao separador de valores não pode ser: usa-se o ponto",
       hint_en="it cannot equal the value separator: the dot is used then"),
    _o("adhoc_csv_bom", "adhoc", "CSV: UTF-8 com BOM", "CSV: UTF-8 with BOM", BOOL, True,
       hint_pt="o Excel abre bem os acentos", hint_en="Excel opens accents correctly"),
    _o("adhoc_export_dir", "adhoc", "CSV: pasta das exportações", "CSV: export folder", TEXT, "",
       hint_pt="vazio = a pasta «exports» dentro da pasta de dados",
       hint_en="empty = the «exports» folder inside the data folder"),
    _o("adhoc_max_categories", "adhoc", "Gráfico: categorias no eixo X", "Chart: X axis categories",
       INT, 15, lo=2, hi=120, step=1,
       hint_pt="as categorias a mais ficam agrupadas em «Outros»",
       hint_en="extra categories are grouped as «Other»"),
    _o("adhoc_max_series", "adhoc", "Gráfico: séries na legenda", "Chart: legend series", INT, 6,
       lo=1, hi=7, step=1,
       hint_pt="as séries a mais ficam agrupadas em «Outros»",
       hint_en="extra series are grouped as «Other»"),
    _o("adhoc_max_points", "adhoc", "Gráfico: pontos na dispersão", "Chart: scatter points", INT,
       400, lo=10, hi=2000, step=50,
       hint_pt="acima disto desenha-se uma amostra", hint_en="above this a sample is drawn"),
    _o("adhoc_bins", "adhoc", "Gráfico: classes do histograma", "Chart: histogram bins", INT, 10,
       lo=2, hi=40, step=1,
       hint_pt="quando o eixo X é um número, agrupa-se em classes",
       hint_en="when the X axis is a number, values are grouped in bins"),
    _o("adhoc_preview_rows", "adhoc", "Dataset: linhas da pré-visualização",
       "Dataset: preview rows", INT, 12, lo=1, hi=16, step=1,
       hint_pt="(o .csv leva sempre todas as linhas)", hint_en="(the .csv always has every row)"),
    _o("adhoc_max_filters", "adhoc", "Filtros por vista", "Filters per view", INT, 6, lo=1,
       hi=10, step=1),
    # ------------------------------------------------------------ agente de IA
    _o("agent_chars_per_token", "agent", "Caracteres por token (estimativa)",
       "Characters per token (estimate)", FLOAT, 3.5, lo=1.5, hi=8.0, step=0.1,
       hint_pt="serve só para estimar os tokens antes de enviar; em português e com JSON "
               "costuma ser ~3,5",
       hint_en="only used to estimate tokens before sending; for Portuguese and JSON it is "
               "usually ~3.5"),
    _o("agent_max_output_tokens", "agent", "Máximo de tokens da resposta",
       "Max response tokens", INT, 1024, lo=64, hi=8192, step=64,
       hint_pt="o limite que se pede ao fornecedor para a resposta",
       hint_en="the limit asked of the provider for the answer"),
    _o("agent_warn_tokens", "agent", "Avisar acima de (tokens)", "Warn above (tokens)", INT,
       8000, lo=500, hi=200000, step=500,
       hint_pt="um pedido maior do que isto mostra um aviso antes de enviar",
       hint_en="a request larger than this shows a warning before sending"),
    _o("agent_price_in_per_mtok", "agent", "Preço por milhão de tokens enviados",
       "Price per million input tokens", FLOAT, 0.0, lo=0.0, hi=1000.0, step=0.25,
       hint_pt="0 = não mostra o custo; vê o preço no site do fornecedor",
       hint_en="0 = no cost shown; see the price on the provider's site"),
    _o("agent_price_out_per_mtok", "agent", "Preço por milhão de tokens da resposta",
       "Price per million output tokens", FLOAT, 0.0, lo=0.0, hi=1000.0, step=0.25),
    _o("agent_currency", "agent", "Moeda do custo", "Cost currency", TEXT, "US$"),
    # ------------------------------------------------------------ saúde e pressão arterial
    _o("bp_daily_mode", "health", "Pressão arterial: média diária", "Blood pressure: daily mean",
       CHOICE, "periods",
       choices=(("periods", "média das médias dos períodos", "mean of the period means"),
                ("readings", "média de todas as medições", "mean of every reading")),
       hint_pt="«períodos»: manhã e noite pesam o mesmo, mesmo com números de medições diferentes",
       hint_en="'periods': morning and night weigh the same even with different reading counts"),
    _o("bp_discard_first", "health", "Pressão arterial: ignorar a 1.ª medição",
       "Blood pressure: skip the 1st reading", BOOL, False,
       hint_pt="em cada período com 3 ou mais medições, a primeira não conta para a média "
               "(costuma sair mais alta)",
       hint_en="in each period with 3 or more readings, the first is left out of the mean "
               "(it tends to be higher)"),
    _o("bp_high_sys", "health", "Pressão alta: máxima a partir de", "High pressure: systolic from",
       INT, 135, lo=110, hi=180, step=1, unit="mmHg",
       hint_pt="limiar para medições em casa (135/85 é o valor habitual das recomendações)",
       hint_en="threshold for home readings (135/85 is the usual guideline value)"),
    _o("bp_high_dia", "health", "Pressão alta: mínima a partir de",
       "High pressure: diastolic from", INT, 85, lo=60, hi=120, step=1, unit="mmHg"),
    _o("bp_low_sys", "health", "Pressão baixa: máxima abaixo de", "Low pressure: systolic below",
       INT, 90, lo=70, hi=110, step=1, unit="mmHg"),
    _o("bp_low_dia", "health", "Pressão baixa: mínima abaixo de", "Low pressure: diastolic below",
       INT, 60, lo=40, hi=80, step=1, unit="mmHg"),
    _o("bp_crisis_sys", "health", "Pressão muito alta: máxima a partir de",
       "Very high pressure: systolic from", INT, 180, lo=150, hi=220, step=1, unit="mmHg",
       hint_pt="acima disto a Perennia diz para repetires a medição e contactares um médico",
       hint_en="above this Perennia tells you to repeat the reading and contact a doctor"),
    _o("bp_crisis_dia", "health", "Pressão muito alta: mínima a partir de",
       "Very high pressure: diastolic from", INT, 110, lo=95, hi=140, step=1, unit="mmHg"),
    _o("bp_morning_until_h", "health", "Período «manhã» até às", "'Morning' period until",
       INT, 12, lo=6, hi=14, step=1, unit="h",
       hint_pt="a hora da medição sugere o período (podes sempre escolher outro)",
       hint_en="the reading time suggests the period (you can always pick another)"),
    _o("bp_afternoon_until_h", "health", "Período «tarde» até às", "'Afternoon' period until",
       INT, 19, lo=14, hi=22, step=1, unit="h"),
    _o("health_window_days", "health", "Assistente de saúde: período recente",
       "Health assistant: recent window", INT, 14, lo=3, hi=60, step=1, unit="d",
       hint_pt="os dias mais recentes, que se comparam com o período de base",
       hint_en="the most recent days, compared with the baseline window"),
    _o("health_baseline_days", "health", "Assistente de saúde: período de base",
       "Health assistant: baseline window", INT, 90, lo=14, hi=365, step=1, unit="d"),
    _o("health_sleep_min_h", "health", "Sono: mínimo desejável", "Sleep: desirable minimum",
       FLOAT, 7.0, lo=4.0, hi=10.0, step=0.25, unit="h"),
    _o("health_rhr_rise_bpm", "health", "FC em repouso: subida que merece aviso",
       "Resting HR: rise worth a warning", FLOAT, 5.0, lo=1.0, hi=20.0, step=0.5, unit="bpm",
       hint_pt="média recente acima da de base por este valor",
       hint_en="recent mean above the baseline by this much"),
    _o("health_hrv_drop_pct", "health", "HRV: descida que merece aviso",
       "HRV: drop worth a warning", FLOAT, 15.0, lo=3.0, hi=50.0, step=1.0, unit="%"),
    _o("health_alcohol_week_max", "health", "Bebidas alcoólicas: máximo por semana",
       "Alcoholic drinks: weekly maximum", FLOAT, 7.0, lo=0.0, hi=30.0, step=1.0),
    _o("health_weight_change_pct", "health", "Peso: variação que merece aviso",
       "Weight: change worth a warning", FLOAT, 2.0, lo=0.5, hi=10.0, step=0.5, unit="%",
       hint_pt="diferença entre a média recente e a de base",
       hint_en="difference between the recent and the baseline mean"),
    _o("health_min_days", "health", "Assistente de saúde: dias mínimos de registo",
       "Health assistant: minimum logged days", INT, 3, lo=1, hi=14, step=1, unit="d",
       hint_pt="com menos dias do que isto no período, não tira conclusões sobre a métrica",
       hint_en="with fewer days than this in the window, it draws no conclusion on the metric"),
    _o("health_streak_rest_days", "health", "Dias seguidos de treino que pedem descanso",
       "Training days in a row that call for rest", INT, 10, lo=3, hi=30, step=1, unit="d"),
    # ------------------------------------------------------------ treinador e assistente
    _o("advisor_coach_mode", "coach", "Treinador: aconselhamento", "Coach: advice from",
       CHOICE, "rules", choices=(("rules", "Regras da Perennia (offline, já funciona)", "Perennia rules (offline, works now)"), ("local", "LLM local (offline, por ligar)", "Local LLM (offline, not connected yet)"), ("online", "Agente online (por ligar)", "Online agent (not connected yet)")),
       hint_pt="as regras funcionam já, sem rede; o LLM local e o agente online ficam "
               "preparados (mostram o pedido e os tokens, sem enviar)",
       hint_en="the rules work now, offline; the local LLM and the online agent are prepared "
               "(they show the request and the tokens, without sending)"),
    _o("advisor_health_mode", "coach", "Assistente de saúde: aconselhamento",
       "Health assistant: advice from", CHOICE, "rules", choices=(("rules", "Regras da Perennia (offline, já funciona)", "Perennia rules (offline, works now)"), ("local", "LLM local (offline, por ligar)", "Local LLM (offline, not connected yet)"), ("online", "Agente online (por ligar)", "Online agent (not connected yet)"))),
    _o("advisor_online_provider", "coach", "Agente online: fornecedor", "Online agent: provider",
       CHOICE, "anthropic",
       choices=(("anthropic", "Claude (Anthropic)", "Claude (Anthropic)"),
                ("openai", "ChatGPT (OpenAI)", "ChatGPT (OpenAI)"),
                ("gemini", "Gemini (Google)", "Gemini (Google)"),
                ("other", "Outro (compatível com OpenAI)", "Other (OpenAI-compatible)")),
       hint_pt="a chave vem SEMPRE de uma variável de ambiente (ver RUN.md); nunca se escreve aqui",
       hint_en="the key ALWAYS comes from an environment variable (see RUN.md); never typed here"),
    _o("advisor_online_model", "coach", "Agente online: modelo", "Online agent: model", TEXT, "",
       hint_pt="o nome do modelo no fornecedor (vazio: o de omissão do fornecedor)",
       hint_en="the model name at the provider (empty: the provider's default)"),
    _o("advisor_local_url", "coach", "LLM local: endereço", "Local LLM: address", TEXT,
       "http://127.0.0.1:11434",
       hint_pt="onde o teu LLM local (Ollama, LM Studio, llama.cpp) escuta — só no teu computador",
       hint_en="where your local LLM (Ollama, LM Studio, llama.cpp) listens — your computer only"),
    _o("advisor_local_model", "coach", "LLM local: modelo", "Local LLM: model", TEXT, "",
       hint_pt="por exemplo «qwen2.5:7b» ou «llama3.1:8b»", hint_en="e.g. 'qwen2.5:7b' or 'llama3.1:8b'"),
    _o("advisor_local_context_tokens", "coach", "LLM local: janela de contexto",
       "Local LLM: context window", INT, 8192, lo=1024, hi=262144, step=1024, unit="tokens",
       hint_pt="um pedido maior do que isto não cabe no modelo local: a Perennia avisa",
       hint_en="a request larger than this does not fit the local model: Perennia warns"),
    _o("coach_live_feedback", "coach", "Construtor: feedback do Treinador ao vivo",
       "Builder: live coach feedback", BOOL, True,
       hint_pt="depois de pedires feedback uma vez, o veredicto atualiza-se enquanto editas",
       hint_en="after you ask for feedback once, the verdict updates while you edit"),
    _o("coach_ramp_max_per_week", "coach", "Subida máxima da forma (CTL) por semana",
       "Maximum fitness (CTL) rise per week", FLOAT, 5.0, lo=1.0, hi=12.0, step=0.5,
       hint_pt="acima disto o Treinador diz que a semana é carga a mais",
       hint_en="above this the coach says the week is too much load"),
    _o("coach_tired_tsb", "coach", "Forma (TSB) abaixo da qual se alivia",
       "Form (TSB) below which to ease off", FLOAT, -20.0, lo=-50.0, hi=0.0, step=1.0),
    _o("coach_overload_tsb", "coach", "Forma (TSB) abaixo da qual se descansa",
       "Form (TSB) below which to rest", FLOAT, -30.0, lo=-70.0, hi=-5.0, step=1.0),
    _o("coach_fresh_tsb", "coach", "Forma (TSB) acima da qual se está fresco",
       "Form (TSB) above which you are fresh", FLOAT, 5.0, lo=-5.0, hi=30.0, step=1.0),
    _o("coach_heavy_factor", "coach", "Treino pesado: vezes a carga habitual",
       "Heavy workout: times the usual load", FLOAT, 1.5, lo=1.1, hi=4.0, step=0.1,
       hint_pt="a carga de um treino a dividir pela carga típica das tuas sessões recentes",
       hint_en="a workout's load divided by the typical load of your recent sessions"),
    _o("coach_very_heavy_factor", "coach", "Treino pesado demais: vezes a carga habitual",
       "Too heavy a workout: times the usual load", FLOAT, 2.2, lo=1.2, hi=6.0, step=0.1),
    _o("coach_history_days", "coach", "Treinador: dias de histórico que conta",
       "Coach: days of history it weighs", INT, 42, lo=14, hi=180, step=1, unit="d"),
    _o("coach_taper_days", "coach", "Evento: dias de afinação antes", "Event: taper days before",
       INT, 7, lo=2, hi=21, step=1, unit="d"),
    _o("coach_plan_weeks_max", "coach", "Evento: semanas que vão para o calendário",
       "Event: weeks put on the calendar", INT, 16, lo=1, hi=52, step=1,
       hint_pt="o plano mais comprido do que isto só agenda as primeiras semanas",
       hint_en="a longer plan only schedules the first weeks"),
    _o("coach_weekday_minutes", "coach", "Disponibilidade por omissão: dia de semana",
       "Default availability: weekday", INT, 60, lo=0, hi=300, step=5, unit="min"),
    _o("coach_weekend_minutes", "coach", "Disponibilidade por omissão: dia de fim de semana",
       "Default availability: weekend day", INT, 180, lo=0, hi=600, step=10, unit="min"),
    _o("coach_carbs_g_per_h", "coach", "Evento: hidratos por hora", "Event: carbs per hour",
       INT, 60, lo=20, hi=120, step=5, unit="g",
       hint_pt="para esforços até à duração «evento longo»", hint_en="for efforts up to 'long event'"),
    _o("coach_carbs_long_g_per_h", "coach", "Evento longo: hidratos por hora",
       "Long event: carbs per hour", INT, 80, lo=30, hi=120, step=5, unit="g"),
    _o("coach_long_event_h", "coach", "Evento longo a partir de", "Long event from",
       FLOAT, 2.5, lo=1.0, hi=8.0, step=0.25, unit="h"),
    _o("coach_fluid_ml_per_h", "coach", "Evento: líquidos por hora", "Event: fluids per hour",
       INT, 600, lo=200, hi=1200, step=50, unit="ml"),
    _o("coach_weak_axis_score", "coach", "Longevidade: eixo fraco abaixo de",
       "Longevity: weak axis below", FLOAT, 50.0, lo=10.0, hi=90.0, step=5.0,
       hint_pt="os eixos do índice de longevidade abaixo desta nota entram no caminho proposto",
       hint_en="longevity index axes below this score enter the proposed path"),
    _o("coach_path_weeks", "coach", "Longevidade: duração de cada fase",
       "Longevity: length of each phase", INT, 4, lo=2, hi=12, step=1),
    _o("coach_long_share_pct", "coach", "Evento: treino longo necessário",
       "Event: long session needed", INT, 75, lo=40, hi=100, step=5, unit="%",
       hint_pt="a parte da duração do evento a que o teu treino mais longo deve chegar antes",
       hint_en="the share of the event duration your longest session should reach before"),
    _o("coach_early_start_h", "coach", "Evento: partida «cedo» antes das",
       "Event: 'early' start before", INT, 9, lo=5, hi=11, step=1, unit="h",
       hint_pt="antes desta hora, a refeição que conta é o jantar da véspera",
       hint_en="before this time, the meal that counts is the dinner the day before"),
    _o("coach_z5_max_min", "coach", "Treino: máximo em Z5 ou acima",
       "Workout: maximum in Z5 or above", INT, 30, lo=5, hi=90, step=5, unit="min",
       hint_pt="acima disto o Treinador avisa", hint_en="above this the coach warns"),
    _o("coach_z4_max_min", "coach", "Treino: máximo em Z4", "Workout: maximum in Z4",
       INT, 60, lo=10, hi=180, step=5, unit="min"),
    _o("coach_reps_week_soft_pct", "coach", "Força: progressão exigente (repetições)",
       "Strength: demanding progression (reps)", FLOAT, 6.0, lo=1.0, hi=20.0, step=0.5,
       unit="%",
       hint_pt="subida por semana acima da qual o objetivo passa de «realista» a «exigente»",
       hint_en="weekly rise above which the goal goes from 'realistic' to 'demanding'"),
    _o("coach_reps_week_hard_pct", "coach", "Força: progressão muito ambiciosa (repetições)",
       "Strength: very ambitious progression (reps)", FLOAT, 12.0, lo=2.0, hi=40.0, step=0.5,
       unit="%"),
    _o("coach_load_week_soft_pct", "coach", "Força: progressão exigente (kg)",
       "Strength: demanding progression (kg)", FLOAT, 2.5, lo=0.5, hi=10.0, step=0.5,
       unit="%"),
    _o("coach_load_week_hard_pct", "coach", "Força: progressão muito ambiciosa (kg)",
       "Strength: very ambitious progression (kg)", FLOAT, 5.0, lo=1.0, hi=20.0, step=0.5,
       unit="%"),
    _o("coach_reps_per_min_dense", "coach", "Força: ritmo muito denso",
       "Strength: very dense pace", INT, 30, lo=10, hi=80, step=1, unit="rep/min",
       hint_pt="repetições por minuto (num evento com limite de tempo) que já pedem aviso",
       hint_en="reps per minute (in a time-limited event) that already call for a warning"),
    _o("coach_reps_per_min_max", "coach", "Força: ritmo acima do possível",
       "Strength: pace beyond possible", INT, 45, lo=15, hi=120, step=1, unit="rep/min"),
    # ------------------------------------------------------------ dados e backups
    _o("backup_restore_max_mb", "data", "Backup: tamanho máximo ao repor",
       "Backup: maximum size on restore", INT, 4096, lo=64, hi=1048576, step=256, unit="MB",
       hint_pt="um backup que, descomprimido, passe disto é recusado (defesa contra ficheiros "
               "feitos para encher o disco)",
       hint_en="a backup that, uncompressed, exceeds this is refused (defence against files "
               "built to fill the disk)"),
)

BY_KEY: dict[str, Opt] = {o.key: o for o in OPTIONS}


# --------------------------------------------------------------------------- valores


def coerce(opt: Opt, value: Any) -> Any:
    """O valor dentro do tipo e dos limites da opção (um valor estragado volta ao de omissão)."""
    try:
        if opt.kind == BOOL:
            return bool(value)
        if opt.kind == CHOICE:
            ok = [c[0] for c in opt.choices]
            return value if value in ok else opt.default
        if opt.kind == TEXT:
            return str(value if value is not None else opt.default)[:200]
        v = float(value)
        if v != v:                                            # NaN
            return opt.default
        v = max(opt.lo, min(opt.hi, v)) if opt.lo is not None and opt.hi is not None else v
        return int(round(v)) if opt.kind == INT else float(v)
    except (TypeError, ValueError):
        return opt.default


def get(db, key: str) -> Any:
    """O valor atual de uma opção (por omissão, se nunca foi mexida)."""
    opt = BY_KEY[key]
    raw = db.get(key, opt.default) if db is not None else opt.default
    return coerce(opt, raw)


def defaults(prefix: str = "") -> dict[str, Any]:
    return {o.key: o.default for o in OPTIONS if o.key.startswith(prefix)}


def limits(prefix: str = "") -> dict[str, tuple[int, int]]:
    return {o.key: (int(o.lo), int(o.hi)) for o in OPTIONS
            if o.key.startswith(prefix) and o.lo is not None and o.hi is not None}


def stepped(opt: Opt, value: Any, steps: int) -> Any:
    """O valor depois de `steps` passos das setas (dentro dos limites; as escolhas dão a volta)."""
    if opt.kind == BOOL:
        return not bool(value)
    if opt.kind == CHOICE:
        ok = [c[0] for c in opt.choices]
        i = ok.index(value) if value in ok else 0
        return ok[(i + (1 if steps > 0 else -1)) % len(ok)]
    if opt.kind == TEXT:
        return value
    new = float(value) + opt.step * steps
    new = round(new / opt.step) * opt.step if opt.step else new      # sem restos de vírgula
    return coerce(opt, round(new, 6))


def choice_label(opt: Opt, value: Any) -> str:
    for v, pt, en in opt.choices:
        if v == value:
            return tr(pt, en)
    return str(value)


def shown(opt: Opt, value: Any) -> str:
    """O valor como as Definições o mostram."""
    if opt.kind == BOOL:
        return tr("ligado", "on") if value else tr("desligado", "off")
    if opt.kind == CHOICE:
        return choice_label(opt, value)
    if opt.kind == TEXT:
        return str(value) if str(value) else tr("(por omissão)", "(default)")
    text = f"{value:g}"
    return f"{text} {opt.unit}".strip()


def apply(db) -> None:
    """Põe os valores nas constantes dos módulos (arranque e depois de guardar as Definições)."""
    for opt in OPTIONS:
        if not opt.binds:
            continue
        value = get(db, opt.key)
        for module, name in opt.binds:
            try:
                setattr(importlib.import_module(module), name, value)
            except ImportError:
                pass
