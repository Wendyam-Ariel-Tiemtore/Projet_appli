"""Authentification : mots de passe Argon2id, sessions côté serveur, jetons CSRF, verrouillage."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import delete, select

from ..db import Database, SessionRow, User, utcnow

# Paramètres Argon2id proches des recommandations OWASP (mémoire 64 Mio, 3 passes)
HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)
COOKIE = "aa_session"
USERNAME_RE = re.compile(r"^[a-zA-Z0-9._\-]{3,32}$")
COMMON = {"motdepasse123", "password1234", "azerty123456", "123456789012", "qwerty123456", "administrateur",
          "000000000000", "111111111111", "motdepasse1234", "bonjour12345", "soleil123456"}
DUMMY_HASH = HASHER.hash("valeur-factice-pour-temps-constant")


def password_problems(password: str, username: str = "") -> list[str]:
    errs = []
    if len(password) < 12:
        errs.append("au moins 12 caractères")
    if len(password) > 256:
        errs.append("au plus 256 caractères")
    classes = sum(bool(re.search(p, password)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^\w\s]"))
    if classes < 3:
        errs.append("au moins trois types de caractères parmi minuscules, majuscules, chiffres et symboles")
    if password.lower() in COMMON or (username and username.lower() in password.lower()):
        errs.append("ni mot de passe courant ni identifiant inclus")
    return errs


def hash_password(password: str) -> str:
    return HASHER.hash(password)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Auth:
    def __init__(self, db: Database, settings):
        self.db = db
        self.settings = settings

    # --- Comptes ---------------------------------------------------------
    def create_user(self, username: str, password: str, is_admin: bool = False) -> User:
        with self.db.session() as s:
            u = User(username=username, password_hash=hash_password(password), is_admin=is_admin)
            s.add(u)
            s.commit()
            return u

    def authenticate(self, username: str, password: str) -> tuple[User | None, str]:
        with self.db.session() as s:
            u = s.scalar(select(User).where(User.username == username))
            now = utcnow()
            if u is None:
                try:  # temps constant : ne pas révéler l'existence du compte
                    HASHER.verify(DUMMY_HASH, password)
                except (VerifyMismatchError, VerificationError, InvalidHashError):
                    pass
                return None, "Identifiant ou mot de passe incorrect."
            if u.locked_until and u.locked_until > now:
                return None, ("Compte temporairement verrouillé après plusieurs échecs. Réessayez dans "
                              f"{self.settings.login_lock_minutes} minutes.")
            try:
                HASHER.verify(u.password_hash, password)
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                u.failed_attempts += 1
                if u.failed_attempts >= self.settings.login_max_attempts:
                    u.locked_until = now + timedelta(minutes=self.settings.login_lock_minutes)
                    u.failed_attempts = 0
                s.commit()
                return None, "Identifiant ou mot de passe incorrect."
            if HASHER.check_needs_rehash(u.password_hash):
                u.password_hash = hash_password(password)
            u.failed_attempts = 0
            u.locked_until = None
            s.commit()
            return u, ""

    def change_password(self, user_id: int, old: str, new: str) -> str:
        with self.db.session() as s:
            u = s.get(User, user_id)
            try:
                HASHER.verify(u.password_hash, old)
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                return "Mot de passe actuel incorrect."
            probs = password_problems(new, u.username)
            if probs:
                return "Le nouveau mot de passe doit comporter " + ", ".join(probs) + "."
            u.password_hash = hash_password(new)
            s.execute(delete(SessionRow).where(SessionRow.user_id == user_id))  # déconnexion partout
            s.commit()
        return ""

    # --- Sessions --------------------------------------------------------
    def open_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        with self.db.session() as s:
            s.add(SessionRow(token_hash=_token_hash(token), user_id=user_id, csrf=secrets.token_urlsafe(32)))
            s.commit()
        return token

    def resolve(self, token: str | None) -> tuple[User, SessionRow] | None:
        if not token or len(token) > 100:
            return None
        now = utcnow()
        with self.db.session() as s:
            row = s.scalar(select(SessionRow).where(SessionRow.token_hash == _token_hash(token)))
            if row is None:
                return None
            idle = timedelta(minutes=self.settings.session_idle_minutes)
            absolute = timedelta(hours=self.settings.session_max_hours)
            if now - row.last_seen > idle or now - row.created_at > absolute:
                s.delete(row)
                s.commit()
                return None
            row.last_seen = now
            user = s.get(User, row.user_id)
            s.commit()
            if user is None:
                return None
            return user, row

    def close_session(self, token: str | None) -> None:
        if not token:
            return
        with self.db.session() as s:
            s.execute(delete(SessionRow).where(SessionRow.token_hash == _token_hash(token)))
            s.commit()

    def purge_sessions(self) -> None:
        limit = utcnow() - timedelta(hours=self.settings.session_max_hours)
        with self.db.session() as s:
            s.execute(delete(SessionRow).where(SessionRow.created_at < limit))
            s.commit()


def csrf_ok(expected: str, received: str | None) -> bool:
    return bool(received) and hmac.compare_digest(expected, received)
