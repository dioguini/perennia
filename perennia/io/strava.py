"""Strava: autorização (OAuth) e os pedidos que a Perennia usa.

Só leitura e só dos teus dados: os segmentos que cruzam uma rota
(`/segments/explore`), os teus favoritos (`/segments/starred`), um segmento por ID e, de cada um,
o teu recorde pessoal (`/segments/{id}` → `athlete_segment_stats`) e, com subscrição Strava, os
teus esforços (`/segment_efforts`). A classificação completa
(top 15) deixou de estar disponível na API do Strava em 2020.

Pelo acordo da API do Strava, estes dados não podem ir para sistemas de IA:
o agente da Perennia nunca os recebe.

Para usar:
1. Em https://www.strava.com/settings/api cria uma aplicação («Perennia»),
   com o domínio de autorização (Authorization Callback Domain) `localhost`.
2. Copia o Client ID e o Client Secret para o ecrã do Strava na Perennia.
3. «Autorizar no browser»: abre a página do Strava; ao aceitar, o Strava
   devolve um código a este computador (porta 8723) e a Perennia troca-o
   pelas chaves de acesso, que se renovam sozinhas.
"""
from __future__ import annotations

import html
import json
import os
import secrets
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable

AUTH_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
API = "https://www.strava.com/api/v3"
REDIRECT_PORT = 8723
SCOPE = "read,read_all,activity:read"      # read_all: o teu PR e os segmentos privados
# Em vez de gravar as chaves na base de dados, podem vir do ambiente (não ficam em disco):
ENV_CLIENT_ID = "PERENNIA_STRAVA_CLIENT_ID"
ENV_CLIENT_SECRET = "PERENNIA_STRAVA_CLIENT_SECRET"
# O Client Secret escrito nas Definições fica só em memória enquanto a Perennia está aberta
# (ronda 37): não vai para a base de dados, a não ser que a opção «strava_secret_in_db» o peça.
SESSION_SECRET: dict[str, str] = {}


class StravaError(RuntimeError):
    def __init__(self, message: str = "", status: int | None = None):
        super().__init__(message)
        self.status = status               # o código HTTP do Strava, quando o houve


def default_http(method: str, url: str, params: dict | None = None,
                 headers: dict | None = None, timeout: float = 20.0) -> tuple[int, Any]:
    data = None
    if method == "GET" and params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    elif params:
        data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode() or "null")
        except Exception:
            body = None
        return e.code, body


class StravaClient:
    def __init__(self, db, http: Callable | None = None, clock: Callable = time.time):
        self.db = db
        self.http = http or default_http
        self.clock = clock

    # ------------------------------------------------------------ estado

    @property
    def client_id(self) -> str:
        return os.environ.get(ENV_CLIENT_ID) or str(self.db.get("strava_client_id", "") or "")

    @property
    def client_secret(self) -> str:
        return (os.environ.get(ENV_CLIENT_SECRET) or SESSION_SECRET.get("secret")
                or str(self.db.get("strava_client_secret", "") or ""))

    @property
    def secret_from_env(self) -> bool:
        """True quando o Client Secret vem da variável de ambiente (e não da base de dados)."""
        return bool(os.environ.get(ENV_CLIENT_SECRET))

    @property
    def tokens(self) -> dict:
        return self.db.get("strava_tokens", {}) or {}

    @property
    def connected(self) -> bool:
        return bool(self.tokens.get("refresh_token"))

    @property
    def athlete_name(self) -> str:
        a = self.tokens.get("athlete") or {}
        return " ".join(x for x in (a.get("firstname"), a.get("lastname")) if x)

    def redirect_uri(self) -> str:
        return f"http://localhost:{REDIRECT_PORT}/exchange"

    def auth_url(self, state: str | None = None) -> str:
        q = {"client_id": self.client_id, "response_type": "code",
             "redirect_uri": self.redirect_uri(), "approval_prompt": "auto", "scope": SCOPE}
        if state:
            q["state"] = state                     # volta igual: prova que o pedido foi nosso
        return AUTH_URL + "?" + urllib.parse.urlencode(q)

    def disconnect(self) -> None:
        self.db.set("strava_tokens", {})

    # ------------------------------------------------------------ chaves

    @property
    def scope(self) -> str:
        """As permissões que o Strava deu na última autorização («» se não se sabe)."""
        return str(self.tokens.get("scope") or "")

    @property
    def needs_reauth(self) -> bool:
        """Ligado, mas sem a permissão `read_all` (o PR e os esforços podem faltar): autorizar
        de novo resolve."""
        return self.connected and "read_all" not in self.scope.replace("%2C", ",").split(",")

    def exchange(self, code: str, scope: str | None = None) -> dict:
        status, body = self.http("POST", TOKEN_URL, {
            "client_id": self.client_id, "client_secret": self.client_secret,
            "code": code, "grant_type": "authorization_code"})
        if status != 200 or not body or "access_token" not in body:
            raise StravaError(f"o Strava recusou a autorização ({status})")
        if scope:
            cur = self.tokens
            cur["scope"] = scope
            self.db.set("strava_tokens", cur)
        self._save_tokens(body)
        return body

    def _save_tokens(self, body: dict) -> None:
        cur = self.tokens
        cur.update({k: body[k] for k in ("access_token", "refresh_token", "expires_at")
                    if k in body})
        if body.get("athlete"):
            cur["athlete"] = {k: body["athlete"].get(k) for k in ("id", "firstname", "lastname")}
        self.db.set("strava_tokens", cur)

    def access_token(self) -> str:
        tok = self.tokens
        if not tok.get("refresh_token"):
            raise StravaError("o Strava não está autorizado")
        if float(tok.get("expires_at") or 0) < self.clock() + 60:
            status, body = self.http("POST", TOKEN_URL, {
                "client_id": self.client_id, "client_secret": self.client_secret,
                "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"})
            if status != 200 or not body or "access_token" not in body:
                raise StravaError(f"não foi possível renovar o acesso ({status})")
            self._save_tokens(body)
            tok = self.tokens
        return tok["access_token"]

    def get(self, path: str, params: dict | None = None) -> Any:
        status, body = self.http("GET", API + path, params,
                                 {"Authorization": f"Bearer {self.access_token()}"})
        if status == 429:
            raise StravaError("limite de pedidos do Strava atingido; tenta daqui a 15 min", 429)
        if status != 200:
            raise StravaError(f"pedido ao Strava falhou ({status})", status)
        return body

    # ---------------------------------------------------------- segmentos

    def explore(self, bounds: tuple[float, float, float, float],
                activity: str = "riding") -> list[dict]:
        try:
            body = self.get("/segments/explore", {
                "bounds": ",".join(f"{v:.6f}" for v in bounds), "activity_type": activity})
        except StravaError as e:
            if e.status in (401, 403):
                raise StravaError(
                    f"{e} — a tua app do Strava pode não ter acesso à pesquisa por rota; "
                    "importa os segmentos por ID ou pelos favoritos (menu Segmentos)",
                    e.status) from e
            raise
        return list((body or {}).get("segments") or [])

    def segment(self, segment_id: int) -> dict:
        return self.get(f"/segments/{int(segment_id)}") or {}

    def starred(self, page: int = 1, per_page: int = 200) -> list[dict]:
        """Os segmentos que marcaste com ⭐ no Strava (resumos)."""
        return list(self.get("/segments/starred", {"page": page, "per_page": per_page}) or [])

    def efforts(self, segment_id: int, page: int = 1, per_page: int = 200) -> list[dict]:
        """Os teus esforços num segmento (precisa de subscrição Strava)."""
        return list(self.get("/segment_efforts", {
            "segment_id": int(segment_id), "page": page, "per_page": per_page}) or [])


def authorize_interactive(client: StravaClient, open_browser: Callable = webbrowser.open,
                          timeout: float = 180.0) -> bool:
    """Abre o browser no Strava e espera pelo código em http://localhost:8723.

    O servidor só escuta neste computador (127.0.0.1), só aceita `/exchange` e só aceita o
    código se vier com o `state` aleatório que esta chamada gerou (senão, qualquer página
    aberta no browser podia entregar à Perennia um código que não é teu)."""
    result: dict = {}
    done = threading.Event()
    state = secrets.token_urlsafe(24)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):                                  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/exchange":
                self.send_error(404)
                return
            q = urllib.parse.parse_qs(parsed.query)
            if not secrets.compare_digest((q.get("state") or [""])[0], state):
                self.send_error(400, "state invalido")
                return
            result["code"] = (q.get("code") or [None])[0]
            result["scope"] = (q.get("scope") or [""])[0]
            result["error"] = (q.get("error") or [None])[0]
            ok = bool(result["code"])
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = ("Perennia: Strava ligado. Podes fechar esta janela." if ok else
                   "Perennia: o Strava não deu autorização.")
            self.wfile.write(
                f"<html><body><h2>{html.escape(msg)}</h2></body></html>".encode())
            done.set()

        def log_message(self, *a):                         # sem ruído na consola
            pass

    server = HTTPServer(("127.0.0.1", REDIRECT_PORT), Handler)
    server.timeout = 1.0
    open_browser(client.auth_url(state))
    t0 = time.time()
    try:
        while not done.is_set() and time.time() - t0 < timeout:
            server.handle_request()
    finally:
        server.server_close()
    if not result.get("code"):
        return False
    client.exchange(result["code"], result.get("scope") or None)
    return True
