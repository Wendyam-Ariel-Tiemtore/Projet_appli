"""En-têtes de sécurité HTTP, limitation de débit et validation des fichiers déposés."""

from __future__ import annotations

import io
import time
import zipfile
from collections import defaultdict, deque
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'; "
       "upgrade-insecure-requests")


class SecurityHeaders(BaseHTTPMiddleware):
    def __init__(self, app, https: bool):
        super().__init__(app)
        self.https = https

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        h = response.headers
        h["Content-Security-Policy"] = CSP if self.https else CSP.replace("; upgrade-insecure-requests", "")
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "same-origin"  # « no-referrer » rendrait l'en-tête Origin nul sur les POST
        h["Permissions-Policy"] = ("camera=(), microphone=(), geolocation=(), payment=(), usb=(), "
                                   "interest-cohort=(), browsing-topics=()")
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        h["Cross-Origin-Resource-Policy"] = "same-origin"
        h["X-Permitted-Cross-Domain-Policies"] = "none"
        if not request.url.path.startswith("/static/"):
            h["Cache-Control"] = "no-store, max-age=0"
            h["Pragma"] = "no-cache"
        if self.https:
            h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        if "server" in h:
            del h["server"]
        return response


class OriginCheck(BaseHTTPMiddleware):
    """Refuse les requêtes modifiantes dont l'origine déclarée n'est pas l'application elle-même."""

    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin") or request.headers.get("referer")
            host = request.headers.get("host", "")
            if origin:
                from urllib.parse import urlparse
                if origin == "null" or urlparse(origin).netloc != host:
                    return PlainTextResponse("Requête refusée : origine non autorisée.", status_code=403)
        return await call_next(request)


class LimiteCorps:
    """Refuse (413) toute requête dont le corps dépasse la limite, avant que le formulaire ne soit lu ou mis sur
    disque : l'en-tête Content-Length est contrôlé d'emblée, puis les octets réellement reçus."""

    PETIT = 8 * 1024 * 1024  # formulaires ordinaires (y compris la page des variables d'une grande base)

    def __init__(self, app, max_bytes: int, volumineux: tuple[str, ...] = ()):
        self.app, self.max_depot, self.volumineux = app, max_bytes, volumineux

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        limite = self.max_depot if scope.get("path") in self.volumineux else min(self.PETIT, self.max_depot)
        cl = dict(scope.get("headers") or []).get(b"content-length")
        if cl is not None:
            try:
                n = int(cl)
            except ValueError:
                n = limite + 1
            if n > limite:
                return await PlainTextResponse("Requête trop volumineuse.", status_code=413)(scope, receive, send)
        recu = 0

        async def receive_borne():
            nonlocal recu
            msg = await receive()
            if msg.get("type") == "http.request":
                recu += len(msg.get("body", b""))
                if recu > limite:
                    from starlette.exceptions import HTTPException
                    raise HTTPException(413, "Fichier trop volumineux.")
            return msg

        return await self.app(scope, receive_borne, send)


def cle_reseau(adresse: str) -> str:
    """Clé de limitation : adresse IPv4 entière, préfixe /64 pour IPv6 (un abonné dispose d'un /64 entier)."""
    import ipaddress
    try:
        ip = ipaddress.ip_address(adresse)
    except ValueError:
        return adresse[:64]
    if ip.version == 6:
        if ip.ipv4_mapped:
            return str(ip.ipv4_mapped)
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip)


class RateLimiter:
    """Fenêtre glissante en mémoire, par clé (adresse IP + catégorie)."""

    MAX_CLES = 50_000

    def __init__(self):
        self.hits: dict[str, deque] = defaultdict(deque)

    def _purger(self, q: deque, window_s: int, now: float) -> None:
        while q and now - q[0] > window_s:
            q.popleft()

    def allow(self, key: str, limit: int, window_s: int) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        self._purger(q, window_s, now)
        if len(q) >= limit:
            return False
        q.append(now)
        self._borner()
        return True

    def depasse(self, key: str, limit: int, window_s: int) -> bool:
        """Vrai si la clé a déjà atteint la limite, sans compter une occurrence de plus."""
        q = self.hits.get(key)
        if not q:
            return False
        self._purger(q, window_s, time.monotonic())
        return len(q) >= limit

    def noter(self, key: str) -> None:
        self.hits[key].append(time.monotonic())
        self._borner()

    def oublier(self, key: str) -> None:
        self.hits.pop(key, None)

    def _borner(self) -> None:
        # Borne mémoire : on évince les clés les plus anciennes plutôt que de tout effacer
        if len(self.hits) > self.MAX_CLES:
            for k in sorted(self.hits, key=lambda k: self.hits[k][-1] if self.hits[k] else 0)[: self.MAX_CLES // 10]:
                del self.hits[k]


# ---------------------------------------------------------------------------
# Fichiers déposés
# ---------------------------------------------------------------------------

ALLOWED = {".csv", ".tsv", ".txt", ".xlsx", ".sav", ".dta"}
MAX_UNZIPPED = 250 * 1024 * 1024
MAX_RATIO = 120


class UploadError(ValueError):
    pass


def safe_filename(name: str) -> str:
    base = Path(name or "donnees").name
    base = "".join(ch for ch in base if ch.isalnum() or ch in "._- ")[:100].strip() or "donnees"
    return base


def validate_upload(name: str, data: bytes, max_bytes: int) -> str:
    """Vérifie extension, taille et signature réelle du contenu ; renvoie le nom nettoyé."""
    fname = safe_filename(name)
    ext = Path(fname).suffix.lower()
    if ext not in ALLOWED:
        raise UploadError("Format non accepté. Formats acceptés : CSV, TSV, TXT, XLSX, SAV (SPSS), DTA (Stata).")
    if len(data) == 0:
        raise UploadError("Le fichier est vide.")
    if len(data) > max_bytes:
        raise UploadError(f"Le fichier dépasse la taille maximale autorisée ({max_bytes // (1024 * 1024)} Mo).")
    head = data[:16]
    if ext == ".xlsx":
        if not head.startswith(b"PK\x03\x04"):
            raise UploadError("Le fichier .xlsx n'est pas un classeur Excel valide.")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()
                if "[Content_Types].xml" not in names or not any(n.startswith("xl/") for n in names):
                    raise UploadError("Le fichier .xlsx n'est pas un classeur Excel valide.")
                total = sum(i.file_size for i in z.infolist())
                if total > MAX_UNZIPPED or total > MAX_RATIO * max(len(data), 1):
                    raise UploadError("Le classeur est anormalement compressé et a été refusé par précaution.")
                if any(n.lower().endswith((".bin", ".vba")) or "vbaproject" in n.lower() for n in names):
                    raise UploadError("Les classeurs contenant des macros ne sont pas acceptés.")
        except zipfile.BadZipFile as exc:
            raise UploadError("Le fichier .xlsx est corrompu.") from exc
    elif ext == ".sav":
        if not head.startswith((b"$FL2", b"$FL3")):
            raise UploadError("Le fichier .sav n'est pas un fichier SPSS valide.")
    elif ext == ".dta":
        if not (head.startswith(b"<stata_dta>") or head[:1] in (b"\x71", b"\x72", b"\x73", b"\x6e", b"\x6f")):
            raise UploadError("Le fichier .dta n'est pas un fichier Stata valide.")
    else:
        if b"\x00" in data[:65536]:
            raise UploadError("Le fichier texte contient des données binaires et a été refusé.")
        if head.startswith((b"PK\x03\x04", b"\x7fELF", b"MZ", b"%PDF")):
            raise UploadError("Le contenu ne correspond pas à un fichier texte délimité.")
    return fname
