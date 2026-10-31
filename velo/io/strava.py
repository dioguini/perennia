"""Strava: autorização (OAuth) e os pedidos que a Perennia usa.

Só leitura e só dos teus dados: os segmentos que cruzam uma rota
(`/segments/explore`) e, de cada um, o teu recorde pessoal
(`/segments/{id}` → `athlete_segment_stats`). A classificação completa
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

import json
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
SCOPE = "read,activity:read"


class StravaError(RuntimeError):
    pass


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
        return str(self.db.get("strava_client_id", "") or "")

    @property
    def client_secret(self) -> str:
        return str(self.db.get("strava_client_secret", "") or "")

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

    def auth_url(self) -> str:
        return AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": self.client_id, "response_type": "code",
            "redirect_uri": self.redirect_uri(), "approval_prompt": "auto", "scope": SCOPE})

    def disconnect(self) -> None:
        self.db.set("strava_tokens", {})

    # ------------------------------------------------------------ chaves

    def exchange(self, code: str) -> dict:
        status, body = self.http("POST", TOKEN_URL, {
            "client_id": self.client_id, "client_secret": self.client_secret,
            "code": code, "grant_type": "authorization_code"})
        if status != 200 or not body or "access_token" not in body:
            raise StravaError(f"o Strava recusou a autorização ({status})")
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
            raise StravaError("limite de pedidos do Strava atingido; tenta daqui a 15 min")
        if status != 200:
            raise StravaError(f"pedido ao Strava falhou ({status})")
        return body

    # ---------------------------------------------------------- segmentos

    def explore(self, bounds: tuple[float, float, float, float],
                activity: str = "riding") -> list[dict]:
        body = self.get("/segments/explore", {
            "bounds": ",".join(f"{v:.6f}" for v in bounds), "activity_type": activity})
        return list((body or {}).get("segments") or [])

    def segment(self, segment_id: int) -> dict:
        return self.get(f"/segments/{int(segment_id)}") or {}


def authorize_interactive(client: StravaClient, open_browser: Callable = webbrowser.open,
                          timeout: float = 180.0) -> bool:
    """Abre o browser no Strava e espera pelo código em http://localhost:8723."""
    result: dict = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):                                  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result["code"] = (q.get("code") or [None])[0]
            result["error"] = (q.get("error") or [None])[0]
            ok = bool(result["code"])
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = ("Perennia: Strava ligado. Podes fechar esta janela." if ok else
                   "Perennia: o Strava não deu autorização.")
            self.wfile.write(f"<html><body><h2>{msg}</h2></body></html>".encode())
            done.set()

        def log_message(self, *a):                         # sem ruído na consola
            pass

    server = HTTPServer(("127.0.0.1", REDIRECT_PORT), Handler)
    server.timeout = 1.0
    open_browser(client.auth_url())
    t0 = time.time()
    try:
        while not done.is_set() and time.time() - t0 < timeout:
            server.handle_request()
    finally:
        server.server_close()
    if not result.get("code"):
        return False
    client.exchange(result["code"])
    return True
