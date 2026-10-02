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


class RateLimiter:
    """Fenêtre glissante en mémoire, par clé (adresse IP + catégorie)."""

    def __init__(self):
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_s: int) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > window_s:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        if len(self.hits) > 50_000:  # borne mémoire
            self.hits.clear()
        return True


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
