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
