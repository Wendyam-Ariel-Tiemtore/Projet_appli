"""Configuration par variables d'environnement (préfixe ANALYSTE_) ou fichier .env."""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANALYSTE_", env_file=".env", extra="ignore")

    # Stockage
    data_dir: Path = Path("./donnees")
    # Clé maîtresse de chiffrement (32 octets, base64 urlsafe) : générée au premier lancement si absente
    master_key_file: Path = Path("./donnees/secrets/cle_maitresse")
    session_secret_file: Path = Path("./donnees/secrets/secret_session")

    # Réseau et sécurité
    allowed_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])
    https: bool = True  # cookies « Secure » et HSTS (désactiver uniquement pour un test sans proxy TLS)
    max_upload_mb: int = 50
    session_idle_minutes: int = 30
    session_max_hours: int = 8
    retention_days: int = 7  # purge automatique des projets
    registration_open: bool = False  # au-delà du premier compte (administrateur)
    setup_token: str = ""  # si renseigné, exigé pour créer le compte administrateur (recommandé sur un serveur)
    login_max_attempts: int = 5
    login_lock_minutes: int = 15

    # Rédaction assistée
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:14b-instruct"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    allow_external_llm: bool = True  # l'administrateur peut interdire tout appel externe

    # Littérature
    allow_literature: bool = True
    openalex_api_key: str = ""
    openalex_mailto: str = ""

    # Calcul
    worker_threads: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()


def ensure_secret_file(path: Path, nbytes: int = 32) -> bytes:
    """Lit ou crée un secret aléatoire stocké avec des permissions restrictives (0600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    if path.exists():
        data = path.read_bytes()
        if len(data) >= nbytes:
            return data[:nbytes]
    data = secrets.token_bytes(nbytes)
    path.write_bytes(data)
    path.chmod(0o600)
    return data
