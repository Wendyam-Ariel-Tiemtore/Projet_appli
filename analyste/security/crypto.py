"""Chiffrement des données au repos (AES-256-GCM) avec clés de projet enveloppées par une clé maîtresse.

- Chaque projet possède sa propre clé de données, aléatoire, chiffrée (« enveloppée ») par la clé maîtresse.
- Les fichiers déposés et les résultats ne sont jamais écrits en clair sur le disque persistant.
- La suppression d'un projet détruit sa clé enveloppée : les fichiers résiduels deviennent illisibles
  (effacement cryptographique).
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"AA1"  # version du format de fichier chiffré
NONCE = 12


def new_key() -> bytes:
    return AESGCM.generate_key(bit_length=256)


def encrypt(key: bytes, data: bytes, aad: bytes = b"") -> bytes:
    nonce = os.urandom(NONCE)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, data, aad)


def decrypt(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    if not blob.startswith(MAGIC):
        raise ValueError("Format chiffré inconnu.")
    nonce = blob[len(MAGIC): len(MAGIC) + NONCE]
    return AESGCM(key).decrypt(nonce, blob[len(MAGIC) + NONCE:], aad)


def wrap_key(master: bytes, data_key: bytes, project_id: str) -> bytes:
    return encrypt(master, data_key, aad=f"cle:{project_id}".encode())


def unwrap_key(master: bytes, wrapped: bytes, project_id: str) -> bytes:
    return decrypt(master, wrapped, aad=f"cle:{project_id}".encode())


def write_encrypted(path: Path, key: bytes, data: bytes, aad: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{secrets.token_hex(4)}.tmp")
    tmp.write_bytes(encrypt(key, data, aad.encode()))
    tmp.chmod(0o600)
    tmp.replace(path)


def read_encrypted(path: Path, key: bytes, aad: str) -> bytes:
    return decrypt(key, path.read_bytes(), aad.encode())


def shred_dir(path: Path) -> None:
    """Supprime un répertoire après écrasement des fichiers (meilleur effort ; la vraie garantie est
    l'effacement cryptographique de la clé du projet)."""
    if not path.exists():
        return
    for f in sorted(path.rglob("*"), reverse=True):
        try:
            if f.is_file():
                size = f.stat().st_size
                with f.open("r+b") as fh:
                    fh.write(os.urandom(min(size, 1 << 20)))
                f.unlink()
            elif f.is_dir():
                f.rmdir()
        except OSError:
            continue
    try:
        path.rmdir()
    except OSError:
        pass
