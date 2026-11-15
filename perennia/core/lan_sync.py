"""Sincronizar duas Perennia pela rede local (Wi-Fi): a **fonte** envia, o **destino** recebe.

Exemplo: o PC é a fonte e o Raspberry Pi o destino. No destino pões «Receber» (aparece um PIN de
uma vez só e o endereço); na fonte pões «Enviar», com o endereço e o PIN. A fonte manda uma cópia
(a mesma de um backup, só das componentes escolhidas) e o destino repõe-na, juntando ao que já
tem ou substituindo-o.

Segurança (tudo na biblioteca padrão, mais um certificado gerado na primeira vez):

* o canal é **TLS** (cifrado). O destino cria um certificado próprio na primeira vez
  (`<dados>/sync/`), que ninguém conhece de antemão; por isso a autenticação não se apoia nele
  mas no **PIN**: ambos provam que o sabem com um HMAC que inclui a **impressão digital do
  certificado** visto por cada um (quem se metesse no meio teria outro certificado e a prova
  falharia). O PIN nunca viaja nem é guardado;
* o PIN é aleatório, de uso único, de 8 dígitos por omissão, e caduca (`sync_pin_ttl_s`);
  depois de `sync_max_attempts` falhas o destino pára. O PIN é derivado com PBKDF2 para
  tornar os palpites lentos;
* só se aceitam ligações de endereços da rede local (`sync_lan_only`), com tempos limite, e o
  tamanho máximo do pacote (`sync_max_mb`) é verificado antes de ler;
* nunca se enviam credenciais (Strava, GarminDB) nem se aceitam: a componente «ligacoes» é
  sempre excluída. As Definições da máquina (`path_*`, `sync_*`) nunca são sobrepostas;
* o destino faz um backup de segurança antes de repor.

Limite a saber: o backup não tem data de alteração em cada registo. «Juntar» acrescenta o que
é novo e ignora o que é igual, mas um registo **alterado** na fonte aparece como novo (duplicado)
no destino; «Substituir» faz do destino uma cópia exata da fonte nas componentes enviadas
(o que só existia no destino perde-se, com a cópia de segurança). Para duas máquinas que
mudam as duas, usa-se «Juntar» e limpa-se à mão; o ideal é haver uma fonte de verdade.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import shutil
import socket
import ssl
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

from . import backup, options
from .db import Database
from .i18n import tr

PROTOCOL = 1
MAX_LINE = 16384
NEVER = ("ligacoes",)                       # componentes que nunca viajam
MACHINE_PREFIXES = ("path_", "sync_")       # definições da máquina: não se sobrepõem
# o que se sincroniza se nada for escolhido: os dados, não a máquina
DEFAULT_COMPONENTS = ("perfil", "rotas", "segmentos", "treinos", "ginasio", "inventario",
                      "sessoes", "analises", "desafios", "testes", "saude", "calendario",
                      "glossario")


class SyncError(Exception):
    """Falhou de uma forma que se explica ao utilizador."""


# ------------------------------------------------------------------ opções


def _opt(db: Database, key: str):
    return options.get(db, key)


def components(db: Database, chosen: list[str] | None = None) -> list[str]:
    """As componentes a sincronizar: as escolhidas, as da opção `sync_components`, ou as de
    omissão. Nunca inclui as credenciais."""
    keys = list(chosen or [])
    if not keys:
        text = str(_opt(db, "sync_components") or "")
        keys = [k.strip() for k in text.replace(";", ",").split(",") if k.strip()]
    if not keys:
        keys = list(DEFAULT_COMPONENTS)
    return [k for k in dict.fromkeys(keys) if k in backup.BY_KEY and k not in NEVER]


def mode_of(db: Database, chosen: str | None = None) -> str:
    m = (chosen or str(_opt(db, "sync_mode") or "merge")).lower()
    return "replace" if m in ("replace", "substituir") else "merge"


def sync_dir(data_dir: Path | str) -> Path:
    d = Path(data_dir) / "sync"
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


# --------------------------------------------------------------- certificado


def ensure_cert(data_dir: Path | str) -> tuple[Path, Path]:
    """O certificado e a chave do destino (criados na primeira vez; a chave só o dono lê)."""
    d = sync_dir(data_dir)
    cert, key = d / "cert.pem", d / "key.pem"
    if cert.is_file() and key.is_file():
        return cert, key
    try:
        _make_cert_cryptography(cert, key)
    except ImportError:
        _make_cert_openssl(cert, key)
    try:
        os.chmod(key, 0o600)
    except OSError:
        pass
    return cert, key


def _make_cert_cryptography(cert: Path, key: Path) -> None:
    import datetime as dt
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    k = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "perennia-sync")])
    now = dt.datetime.now(dt.timezone.utc)
    c = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
         .public_key(k.public_key()).serial_number(x509.random_serial_number())
         .not_valid_before(now - dt.timedelta(days=1))
         .not_valid_after(now + dt.timedelta(days=3650)).sign(k, hashes.SHA256()))
    key.write_bytes(k.private_bytes(serialization.Encoding.PEM,
                                    serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()))
    cert.write_bytes(c.public_bytes(serialization.Encoding.PEM))


def _make_cert_openssl(cert: Path, key: Path) -> None:
    exe = shutil.which("openssl")
    if not exe:
        raise SyncError(tr("falta a biblioteca «cryptography» (pip install cryptography) ou o "
                           "programa «openssl» para criar o certificado do destino",
                           "the 'cryptography' library (pip install cryptography) or the "
                           "'openssl' program is needed to create the receiver's certificate"))
    r = subprocess.run([exe, "req", "-x509", "-newkey", "ec", "-pkeyopt",
                        "ec_paramgen_curve:prime256v1", "-nodes", "-keyout", str(key), "-out",
                        str(cert), "-days", "3650", "-subj", "/CN=perennia-sync"],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not cert.is_file():
        raise SyncError(tr("não consegui criar o certificado: ", "could not create the "
                           "certificate: ") + (r.stderr or "")[-200:])


def fingerprint(der: bytes) -> str:
    return hashlib.sha256(der).hexdigest()


# ------------------------------------------------------------------ prova do PIN


def new_pin(digits: int = 8) -> str:
    digits = max(6, min(12, int(digits)))
    return "".join(secrets.choice("0123456789") for _ in range(digits))


def _mac(pin: str, role: str, nonce: str, fp: str, iterations: int) -> str:
    key = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(nonce),
                              max(1000, int(iterations)))
    return hmac.new(key, f"{PROTOCOL}|{role}|{nonce}|{fp}".encode("utf-8"),
                    hashlib.sha256).hexdigest()


def _send_line(sock, obj: dict) -> None:
    sock.sendall((json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8"))


def _read_line(sock) -> dict:
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(1)
        if not chunk:
            raise SyncError(tr("a ligação fechou", "the connection closed"))
        buf += chunk
        if len(buf) > MAX_LINE:
            raise SyncError(tr("mensagem demasiado grande", "message too large"))
    try:
        obj = json.loads(buf.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise SyncError(tr("mensagem inválida", "invalid message")) from None
    if not isinstance(obj, dict):
        raise SyncError(tr("mensagem inválida", "invalid message"))
    return obj


def local_addresses() -> list[str]:
    """Os endereços desta máquina na rede local (para dizer na outra «liga-te a …»). Não envia
    nada: só pergunta ao sistema por onde sairia um pacote."""
    out: list[str] = []
    for target in ("10.255.255.255", "192.168.255.255", "172.31.255.255"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.2)
            s.connect((target, 1))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127.") and ip not in out:
                out.append(ip)
        except OSError:
            continue
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if not ip.startswith("127.") and ip not in out:
                out.append(ip)
    except OSError:
        pass
    return out


def is_local(addr: str) -> bool:
    """Endereço da rede local (privado, link-local ou loopback)?"""
    try:
        ip = ipaddress.ip_address(addr.split("%")[0])
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


# ------------------------------------------------------------------ destino


class Receiver:
    """O destino: escuta, autentica com o PIN, recebe o pacote para um ficheiro e entrega-o
    (`result`). Repor é à parte (`apply`) para poder fazer-se na thread certa."""

    def __init__(self, db: Database, data_dir: Path | str, pin: str | None = None,
                 port: int | None = None, host: str = "0.0.0.0"):
        self.db, self.data_dir = db, Path(data_dir)
        self.pin = pin or new_pin(int(_opt(db, "sync_pin_digits")))
        self.port = int(port if port is not None else _opt(db, "sync_port"))
        self.host = host
        self.ttl = float(_opt(db, "sync_pin_ttl_s"))
        self.timeout = float(_opt(db, "sync_timeout_s"))
        self.max_bytes = int(_opt(db, "sync_max_mb")) * 1024 * 1024
        self.max_attempts = int(_opt(db, "sync_max_attempts"))
        self.iterations = int(_opt(db, "sync_kdf_iterations"))
        self.lan_only = bool(_opt(db, "sync_lan_only"))
        self.attempts = 0
        self.status = "idle"            # idle · waiting · receiving · received · failed · closed
        self.message = ""
        self.result: dict | None = None
        self.started = 0.0
        self._sock: socket.socket | None = None
        self._cancel = False
        cert, key = ensure_cert(self.data_dir)
        self._ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self._ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        self._ctx.load_cert_chain(str(cert), str(key))
        self.fingerprint = fingerprint(ssl.PEM_cert_to_DER_cert(cert.read_text()))

    # --- ciclo
    def open(self) -> int:
        """Começa a escutar; devolve a porta (útil com `port=0`)."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((self.host, self.port))
        except OSError as e:
            s.close()
            raise SyncError(tr("não consegui abrir a porta {p}: {e}", "could not open port "
                               "{p}: {e}", p=self.port, e=e)) from None
        s.listen(1)
        s.settimeout(0.5)
        self._sock = s
        self.port = s.getsockname()[1]
        self.started = time.monotonic()
        self.status = "waiting"
        return self.port

    def cancel(self) -> None:
        self._cancel = True

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self.status in ("waiting", "receiving"):
            self.status = "closed"

    def remaining(self) -> float:
        return max(0.0, self.ttl - (time.monotonic() - self.started))

    def wait(self) -> dict | None:
        """Espera por um envio válido (bloqueia). Devolve o resultado ou None se caducou, foi
        cancelado ou houve demasiadas falhas."""
        if self._sock is None:
            self.open()
        try:
            while not self._cancel:
                if self.remaining() <= 0:
                    self.status, self.message = "closed", tr("o PIN caducou", "the PIN expired")
                    return None
                if self.attempts >= self.max_attempts:
                    self.status = "failed"
                    self.message = tr("demasiadas tentativas falhadas: o destino fechou",
                                      "too many failed attempts: the receiver closed")
                    return None
                try:
                    conn, addr = self._sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    return None
                if self._serve(conn, addr[0]):
                    return self.result
            self.status, self.message = "closed", tr("cancelado", "cancelled")
            return None
        finally:
            self.close()

    # --- uma ligação
    def _serve(self, conn: socket.socket, addr: str) -> bool:
        tls = None
        try:
            if self.lan_only and not is_local(addr):
                conn.close()
                return False
            conn.settimeout(self.timeout)
            tls = self._ctx.wrap_socket(conn, server_side=True)
            nonce = secrets.token_hex(16)
            _send_line(tls, {"perennia_sync": PROTOCOL, "nonce": nonce})
            hello = _read_line(tls)
            expected = _mac(self.pin, "C", nonce, self.fingerprint, self.iterations)
            if not hmac.compare_digest(str(hello.get("mac", "")), expected):
                self.attempts += 1
                _send_line(tls, {"ok": False, "error": "pin"})
                return False
            self.status = "receiving"
            _send_line(tls, {"ok": True, "mac": _mac(self.pin, "S", nonce, self.fingerprint,
                                                     self.iterations)})
            head = _read_line(tls)
            size = int(head.get("bytes", -1))
            if size <= 0 or size > self.max_bytes:
                _send_line(tls, {"ok": False, "error": "size"})
                raise SyncError(tr("pacote com tamanho recusado ({n} bytes)",
                                   "package size refused ({n} bytes)", n=size))
            keys = [k for k in head.get("keys") or [] if k in backup.BY_KEY and k not in NEVER]
            mode = "replace" if head.get("mode") == "replace" else "merge"
            if not keys:
                _send_line(tls, {"ok": False, "error": "keys"})
                raise SyncError(tr("nenhuma componente válida", "no valid component"))
            dest = sync_dir(self.data_dir) / f"entrada-{int(time.time())}.zip"
            h = hashlib.sha256()
            got = 0
            with open(dest, "wb") as f:
                while got < size:
                    chunk = tls.recv(min(65536, size - got))
                    if not chunk:
                        raise SyncError(tr("a ligação fechou a meio", "the connection closed "
                                           "midway"))
                    f.write(chunk)
                    h.update(chunk)
                    got += len(chunk)
            if h.hexdigest() != head.get("sha256"):
                dest.unlink(missing_ok=True)
                _send_line(tls, {"ok": False, "error": "hash"})
                raise SyncError(tr("o pacote chegou estragado", "the package arrived corrupted"))
            self.result = {"path": str(dest), "keys": keys, "mode": mode, "bytes": got,
                           "from": addr, "name": str(head.get("name") or "")[:60]}
            self.status = "received"
            _send_line(tls, {"ok": True, "received": got})
            return True
        except (SyncError, OSError, ssl.SSLError, ValueError) as e:
            if self.status == "receiving":
                self.status = "waiting"
            self.message = str(e)[:200]
            return False
        finally:
            try:
                (tls or conn).close()
            except OSError:
                pass

    # --- repor
    def apply(self, progress: Callable[[str], None] | None = None) -> dict:
        """Repõe o pacote recebido (com backup de segurança antes). As definições da máquina
        (pastas, opções de sincronização) ficam como estavam."""
        if not self.result:
            raise SyncError(tr("nada recebido", "nothing received"))
        return apply_package(self.db, self.data_dir, self.result, progress)


def apply_package(db: Database, data_dir: Path | str, res: dict,
                  progress: Callable[[str], None] | None = None) -> dict:
    path = Path(res["path"])
    keep = {r[0]: r[1] for r in db.conn.execute("SELECT key, value FROM settings")
            if r[0].startswith(MACHINE_PREFIXES)}
    try:
        m = backup.inspect(path)
        keys = [k for k in res["keys"] if any(e["key"] == k for e in m["components"])]
        if not keys:
            raise SyncError(tr("o pacote não tem as componentes pedidas",
                               "the package lacks the requested components"))
        rep = backup.restore(db, Path(data_dir), path, keys, res["mode"], True, progress)
    except backup.BackupError as e:
        raise SyncError(str(e)) from None
    finally:
        for k, v in keep.items():
            db.conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (k, v))
        db.conn.commit()
        try:
            path.unlink()
        except OSError:
            pass
    return rep


# -------------------------------------------------------------------- fonte


def send(db: Database, data_dir: Path | str, host: str, pin: str, port: int | None = None,
         keys: list[str] | None = None, mode: str | None = None,
         progress: Callable[[str], None] | None = None) -> dict:
    """A fonte: junta as componentes num pacote e envia-o ao destino. Devolve
    {"bytes", "keys", "mode", "fingerprint"}."""
    host = (host or "").strip()
    if not host or not pin:
        raise SyncError(tr("falta o endereço ou o PIN", "the address or the PIN is missing"))
    if bool(_opt(db, "sync_lan_only")):
        try:
            addr = socket.gethostbyname(host)
        except OSError:
            raise SyncError(tr("não encontro «{h}» na rede", "cannot find '{h}' on the network",
                               h=host)) from None
        if not is_local(addr):
            raise SyncError(tr("«{h}» não é um endereço da rede local (opção «Só rede local»)",
                               "'{h}' is not a local network address ('Local network only')",
                               h=host))
    port = int(port if port is not None else _opt(db, "sync_port"))
    timeout = float(_opt(db, "sync_timeout_s"))
    iterations = int(_opt(db, "sync_kdf_iterations"))
    keys = components(db, keys)
    mode = mode_of(db, mode)
    tmpdir = Path(tempfile.mkdtemp(prefix="saida-", dir=str(sync_dir(data_dir))))
    try:
        if progress:
            progress(tr("a preparar o pacote…", "preparing the package…"))
        m = backup.export(db, Path(data_dir), tmpdir / "pacote.zip", keys, False)
        pack = Path(m["path"])
        size = pack.stat().st_size
        max_bytes = int(_opt(db, "sync_max_mb")) * 1024 * 1024
        if size > max_bytes:
            raise SyncError(tr("o pacote tem {a:.0f} MB e o máximo é {b:.0f} MB (opção "
                               "«Sincronização: tamanho máximo»)", "the package is {a:.0f} MB "
                               "and the maximum is {b:.0f} MB ('Sync: maximum size')",
                               a=size / 1048576, b=max_bytes / 1048576))
        h = hashlib.sha256()
        with open(pack, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE        # quem prova a identidade é o PIN (ver o topo)
        try:
            raw = socket.create_connection((host, port), timeout=timeout)
        except OSError as e:
            raise SyncError(tr("não consegui ligar a {h}:{p} ({e})", "could not connect to "
                               "{h}:{p} ({e})", h=host, p=port, e=e)) from None
        try:
            tls = ctx.wrap_socket(raw, server_hostname=host)
        except (ssl.SSLError, OSError) as e:
            raw.close()
            raise SyncError(tr("a ligação segura falhou ({e})", "the secure connection failed "
                               "({e})", e=e)) from None
        with tls:
            tls.settimeout(timeout)
            fp = fingerprint(tls.getpeercert(binary_form=True) or b"")
            hello = _read_line(tls)
            nonce = str(hello.get("nonce", ""))
            if hello.get("perennia_sync") != PROTOCOL or len(nonce) != 32:
                raise SyncError(tr("o outro lado não é uma Perennia compatível",
                                   "the other side is not a compatible Perennia"))
            _send_line(tls, {"mac": _mac(pin, "C", nonce, fp, iterations)})
            reply = _read_line(tls)
            if not reply.get("ok"):
                raise SyncError(tr("PIN recusado (ou o destino já fechou)",
                                   "PIN refused (or the receiver already closed)"))
            if not hmac.compare_digest(str(reply.get("mac", "")),
                                       _mac(pin, "S", nonce, fp, iterations)):
                raise SyncError(tr("o destino não provou conhecer o PIN: ligação recusada "
                                   "(alguém pode estar no meio)", "the receiver did not prove "
                                   "it knows the PIN: connection refused (someone may be in the "
                                   "middle)"))
            if progress:
                progress(tr("a enviar {mb:.1f} MB…", "sending {mb:.1f} MB…", mb=size / 1048576))
            _send_line(tls, {"keys": keys, "mode": mode, "bytes": size, "sha256": h.hexdigest(),
                             "name": socket.gethostname()})
            with open(pack, "rb") as f:
                while True:
                    block = f.read(65536)
                    if not block:
                        break
                    tls.sendall(block)
            done = _read_line(tls)
            if not done.get("ok"):
                raise SyncError(tr("o destino recusou o pacote ({e})", "the receiver refused "
                                   "the package ({e})", e=done.get("error", "?")))
        return {"bytes": size, "keys": keys, "mode": mode, "fingerprint": fp}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def report_text(rep: dict) -> str:
    return tr("Recebido e reposto ({m}): {r} registos, {f} ficheiros em {c} componentes. "
              "Cópia de segurança: {s}", "Received and restored ({m}): {r} rows, {f} files in "
              "{c} components. Safety copy: {s}", m=tr("juntar", "merge") if rep["mode"] ==
              "merge" else tr("substituir", "replace"), r=rep["rows"], f=rep["files"],
              c=len(rep["components"]), s=rep.get("safety") or "—")
