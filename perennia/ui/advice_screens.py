"""O ecrã onde o Treinador e o Assistente de saúde falam.

`AdviceScreen` mostra um `Advice` (veredicto, secções, perguntas, sessões propostas), com a
linha **Aconselhamento** em cima: Regras da Perennia (offline, já funciona), LLM local (offline)
ou Agente online. Nos dois últimos o ecrã mostra **quantos tokens o pedido gastaria** e deixa
ver tudo o que seria enviado (`AdvisorRequestScreen`), antes de qualquer chamada — que nesta
versão ainda não está ativa: enquanto isso, fica a leitura das regras.

`advice_rows` é a mesma apresentação em linhas, para os menus que mostram um conselho dentro
de um separador.
"""
from __future__ import annotations

from perennia.core import advisor
from perennia.core import agent as agent_mod
from perennia.core.advice import Advice
from perennia.core.i18n import tr
from perennia.ui.app import Screen
from perennia.ui.health_screens import AgentScreen, _excerpt
from perennia.ui.widgets import Dropdown, Item, wrap_lines

TONE_MARK = {"good": "✓", "warn": "!", "bad": "✗", "info": "·"}
MAX_LINES = 60                 # linhas por secção (um texto maior é cortado com reticências)
SCHEDULE_PREVIEW = 10
LABEL_SIZE = 14


def _n(v: int) -> str:
    return f"{v:,}".replace(",", " ")


def text_px(screen) -> float:
    w = screen.app.window.width
    try:
        w = screen._list_width(w)
    except Exception:
        w = w - 96
    return max(240.0, float(w) - 36.0)


def text_rows(screen, text: str, indent: int = 0) -> list[Item]:
    px = text_px(screen) - indent * 18
    return [Item(line, enabled=False, indent=indent)
            for line in wrap_lines(text, px, LABEL_SIZE, max_lines=MAX_LINES)]


def mode_row(screen, figure: str, on_change=None) -> Item:
    db = screen.app.db
    cur = advisor.mode(db, figure)
    modes = list(advisor.MODES)

    def pick(k: int) -> None:
        advisor.set_mode(db, figure, modes[k])
        if on_change is not None:
            on_change()
    return Item(tr("Aconselhamento", "Advice from"), value=advisor.mode_name(cur),
                detail=advisor.mode_detail(db, cur), data="cyc:advisor_mode",
                dropdown=Dropdown([advisor.mode_name(m) for m in modes], modes.index(cur), pick,
                                  title=tr("De onde vem o conselho?", "Where does the advice "
                                           "come from?")))


def llm_rows(screen, figure: str, advice: Advice, question: str = "") -> list[Item]:
    """Nos modos LLM local e online: os tokens do pedido e o que seria enviado."""
    db = screen.app.db
    m = advisor.mode(db, figure)
    if m == "rules":
        return []
    req = advisor.build_request(db, figure, advice, question)
    rep = advisor.report(db, req, m)
    st = advisor.status(db, m)
    rows = [Item(tr("LLM local — por ligar", "Local LLM — not connected yet") if m == "local"
                 else tr("Agente online — por ligar", "Online agent — not connected yet"),
                 header=True)]
    if m == "local":
        fit = tr("cabe na janela do modelo ({w})", "fits the model window ({w})",
                 w=_n(rep["window"])) if rep["fits"] else \
            tr("NÃO cabe na janela do modelo ({w}): desliga categorias", "does NOT fit the "
               "model window ({w}): turn categories off", w=_n(rep["window"]))
        rows.append(Item(tr("Tokens deste pedido", "Tokens in this request"),
                         value=f"≈ {_n(rep['total'])}", detail=fit + " · " + tr(
                             "sem custo: corre no teu computador", "no cost: runs on your "
                             "computer"), enabled=False))
        if not st["local"]:
            rows.append(Item(tr("Atenção", "Warning"),
                             detail=tr("o endereço «{u}» não é deste computador: isso já não "
                                       "seria offline", "the address '{u}' is not this "
                                       "computer: that would no longer be offline",
                                       u=st["url"]), enabled=False))
    else:
        cost = (f"{rep['currency']} {rep['max_cost']:.4f} " + tr("no máximo", "at most")
                if rep["priced"] else tr("põe os preços nas Definições → Avançado para ver o "
                                         "custo", "set the prices in Settings → Advanced to see "
                                         "the cost"))
        rows.append(Item(tr("Tokens deste pedido", "Tokens in this request"),
                         value=f"≈ {_n(rep['total'])}",
                         detail=tr("resposta até {m} · ", "reply up to {m} · ",
                                   m=_n(rep["max_output"])) + cost, enabled=False))
        rows.append(Item(tr("Dados partilhados", "Shared data"),
                         detail=tr("os factos deste pedido e as categorias autorizadas ({c}) "
                                   "· nada do Strava", "this request's facts and the allowed "
                                   "categories ({c}) · nothing from Strava",
                                   c=", ".join(sorted(agent_mod.allowed(db)))), enabled=False))
    rows.append(Item(tr("Ver o que seria enviado", "See what would be sent"),
                     detail=tr("o pedido inteiro, os tokens por partes e as categorias",
                               "the whole request, tokens by part and the categories"),
                     action=lambda: screen.app.push(AdvisorRequestScreen(
                         screen.app, figure, advice, question, m))))
    rows.append(Item(tr("Enquanto não está ligado, fica a leitura das regras da Perennia:",
                        "While it is not connected, here is the Perennia rules reading:"),
                     enabled=False))
    return rows


def advice_rows(screen, advice: Advice, schedule: bool = True) -> list[Item]:
    rows: list[Item] = []
    if advice.verdict:
        mark = TONE_MARK.get(advice.tone, "·")
        lines = wrap_lines(advice.verdict, text_px(screen) - 30, LABEL_SIZE, max_lines=4)
        for i, line in enumerate(lines):
            rows.append(Item((f"{mark}  " if i == 0 else "    ") + line,
                             data=("verdict", advice.tone)))
    for title, body in advice.sections:
        rows.append(Item(title, header=True))
        rows += text_rows(screen, body)
    if advice.questions:
        rows.append(Item(tr("Perguntas para ti", "Questions for you"), header=True))
        for q in advice.questions:
            rows += text_rows(screen, "? " + q)
    if schedule and advice.schedule:
        rows.append(Item(tr("Sessões propostas ({n})", "Proposed sessions ({n})",
                            n=len(advice.schedule)), header=True))
        for p in advice.schedule[:SCHEDULE_PREVIEW]:
            rows.append(Item(p.day.strftime("%d/%m") + "  " + p.title, enabled=False))
        if len(advice.schedule) > SCHEDULE_PREVIEW:
            rows.append(Item(tr("… e mais {n}", "… and {n} more",
                                n=len(advice.schedule) - SCHEDULE_PREVIEW), enabled=False))
    if advice.disclaimer:
        rows.append(Item("", header=True))
        rows += text_rows(screen, advice.disclaimer)
    return rows


class AdviceScreen(Screen):
    """Um conselho do Treinador (`figure="coach"`) ou do Assistente de saúde (`"health"`).

    `make()` devolve o `Advice` (refaz-se sempre que o ecrã se mostra); `extra(screen)` dá
    linhas para pôr por cima (uma pergunta com lista, por exemplo) e `actions(screen, advice)`
    os botões de baixo."""

    SEARCH = False
    AGENT = False

    def __init__(self, app, figure: str, make, *, extra=None, actions=None,
                 subtitle: str = ""):
        super().__init__(app)
        self.figure = figure
        self.make = make
        self.extra = extra
        self.actions = actions
        self.subtitle = subtitle
        self.question = ""
        self.advice: Advice | None = None

    def _ask(self) -> None:
        from perennia.ui.goal_popup import GoalPopup

        def save(text: str) -> None:
            self.question = " ".join((text or "").split())
        self.app.push(GoalPopup(self.app, tr("A tua pergunta", "Your question"),
                                tr("Segue com o pedido para o LLM (as regras não a leem)",
                                   "Goes with the request to the LLM (the rules do not read "
                                   "it)"), self.question, 400, save, multiline=True))

    def enter(self) -> None:
        a = self.app
        adv = self.advice = self.make()
        rows: list[Item] = [mode_row(self, self.figure)]
        if advisor.mode(a.db, self.figure) != "rules":
            rows.append(Item(tr("A tua pergunta", "Your question"),
                             value=_excerpt(self.question, 50) or "—",
                             detail=tr("Enter escreve · opcional", "Enter writes · optional"),
                             action=self._ask))
            rows += llm_rows(self, self.figure, adv, self.question)
        if self.extra is not None:
            rows += self.extra(self)
        rows += advice_rows(self, adv)
        if self.actions is not None:
            rows += self.actions(self, adv)
        self.chrome.set(advisor.figure_name(self.figure) + " · " + adv.title,
                        self.subtitle or advisor.mode_name(advisor.mode(a.db, self.figure)),
                        tr("↑↓ percorrer · Enter abre a lista ou a ação · Esc voltar",
                           "↑↓ scroll · Enter opens the list or the action · Esc back"))
        self.list.set_items(rows, keep_index=True)

    def agent_data(self) -> dict:
        return {} if self.advice is None else {"conselho": self.advice.as_text()}


class AdvisorRequestScreen(AgentScreen):
    """O pedido que seguiria para o LLM local ou para o agente online: os tokens (total e por
    partes), a janela do modelo local ou o custo do online, as categorias partilhadas (Enter
    liga/desliga) e o conteúdo, linha a linha. Nada é enviado nesta versão."""

    HEAD_KEYS = dict(AgentScreen.HEAD_KEYS, page=("O pedido e os factos",
                                                   "The request and the facts"))

    def __init__(self, app, figure: str, advice: Advice, question: str, mode: str):
        Screen.__init__(self, app)
        self.kind = "context"
        self.figure, self.advice, self.question, self.mode = figure, advice, question, mode
        self.source = None
        self.source_name = figure
        self._rebuild()

    def _rebuild(self) -> None:
        self.request = advisor.build_request(self.app.db, self.figure, self.advice,
                                             self.question)

    def enter(self) -> None:
        a = self.app
        rep = advisor.report(a.db, self.request, self.mode)
        st = advisor.status(a.db, self.mode)
        if self.mode == "local":
            head = tr("LLM local ({u}{m}): ainda não está ligado nesta versão. É isto que lhe "
                      "seria enviado — sem sair do teu computador:",
                      "Local LLM ({u}{m}): not connected in this version yet. This is what "
                      "would be sent — without leaving your computer:", u=st["url"],
                      m=" · " + st["model"] if st["model"] else "")
        else:
            head = tr("Agente online ({p}): ainda não está ligado nesta versão. É isto que "
                      "seria partilhado com o fornecedor:",
                      "Online agent ({p}): not connected in this version yet. This is what "
                      "would be shared with the provider:", p=st["provider_name"])
        items = [Item(head, enabled=False)]
        if self.mode == "local":
            rows = self._token_rows(dict(rep, priced=False))
            rows = [r for r in rows if r.label not in (tr("Custo estimado", "Estimated cost"),)]
            rows.append(Item(tr("Janela do modelo local", "Local model window"),
                             value=tr("{w} tokens", "{w} tokens", w=_n(rep["window"])),
                             detail=tr("cabe", "fits") if rep["fits"] else
                             tr("não cabe: desliga categorias abaixo", "does not fit: turn "
                                "categories off below"), enabled=False))
            rows.append(Item(tr("Custo", "Cost"), value=tr("nenhum", "none"),
                             detail=tr("corre no teu computador", "runs on your computer"),
                             enabled=False))
            items += rows
        else:
            items += self._token_rows(rep)
            items.append(Item(tr("Chave do fornecedor", "Provider key"),
                              value=tr("definida", "set") if st["has_key"]
                              else tr("em falta", "missing"),
                              detail=tr("variável de ambiente {e} (nunca se escreve na "
                                        "aplicação)", "environment variable {e} (never typed "
                                        "into the app)", e=st["env"]), enabled=False))
        share = agent_mod.allowed(a.db)
        items.append(Item(tr("— Categorias partilhadas (Enter liga/desliga) —",
                             "— Shared categories (Enter toggles) —"), enabled=False))
        for cat in agent_mod.CATEGORIES:
            items.append(Item(("✓ " if cat in share else "   ") + tr(*self.CATEGORY_NAMES[cat]),
                              detail=tr("nada do Strava, nunca", "never anything from Strava")
                              if cat == "training" else "",
                              action=lambda c=cat: self._toggle_category(c)))
        items.append(Item(tr("— O que seria enviado —", "— What would be sent —"),
                          enabled=False))
        items.append(Item(tr("Instruções", "Instructions"),
                          value=_excerpt(self.request["system"], 90), enabled=False))
        items.append(Item(tr("Pedido", "Request"),
                          value=_excerpt(self.request["instruction"], 90), enabled=False))
        for k, v in agent_mod.flatten(self.request["content"]):
            items.append(Item(k, value=_excerpt(v, 60), enabled=False))
        items.append(Item(tr("Voltar", "Back"), button=True, action=a.pop))
        items.append(Item(tr("Enviar", "Send"), button=True, primary=True, action=self._send,
                          enabled=bool(st["ready"])))
        self.chrome.set(advisor.figure_name(self.figure) + " · " + advisor.mode_name(self.mode),
                        tr("≈ {n} tokens · nada é enviado nesta versão",
                           "≈ {n} tokens · nothing is sent in this version",
                           n=_n(rep["total"])),
                        tr("↑↓ percorrer · Esc voltar", "↑↓ scroll · Esc back"))
        self.list.set_items(items, keep_index=True)
