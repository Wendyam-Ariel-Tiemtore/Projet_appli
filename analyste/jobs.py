"""Stockage chiffré des projets et exécution des analyses en arrière-plan."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from .db import Database, Project, User, utcnow
from .security import crypto
from .stats.io import Dataset, read_dataset

log = logging.getLogger("analyste")


class ProjectStore:
    def __init__(self, db: Database, settings, master_key: bytes):
        self.db = db
        self.settings = settings
        self.master = master_key
        self.root = Path(settings.data_dir) / "projets"
        self.root.mkdir(parents=True, exist_ok=True)
        self.root.chmod(0o700)
        self.pool = ThreadPoolExecutor(max_workers=max(1, settings.worker_threads), thread_name_prefix="analyse")
        self.lock = threading.Lock()

    # --- Clés et chiffrement --------------------------------------------
    def _key(self, p: Project) -> bytes:
        return crypto.unwrap_key(self.master, p.wrapped_key, p.id)

    def enc(self, p: Project, value) -> bytes:
        return crypto.encrypt(self._key(p), json.dumps(value, ensure_ascii=False).encode(), p.id.encode())

    def dec(self, p: Project, blob: bytes | None, default=None):
        if not blob:
            return default
        return json.loads(crypto.decrypt(self._key(p), blob, p.id.encode()))

    def pseudo_secret(self, p: Project) -> bytes:
        return hashlib.sha256(self._key(p) + b"pseudonymisation").digest()

    def name(self, p: Project) -> str:
        return self.dec(p, p.name_enc, "Projet")

    def filename(self, p: Project) -> str:
        return self.dec(p, p.filename_enc, "donnees")

    # --- Cycle de vie ----------------------------------------------------
    def create(self, owner_id: int, name: str, filename: str, raw: bytes) -> str:
        pid = uuid.uuid4().hex
        key = crypto.new_key()
        wrapped = crypto.wrap_key(self.master, key, pid)
        d = self.root / pid
        d.mkdir(mode=0o700)
        crypto.write_encrypted(d / "source.enc", key, raw, f"{pid}:source")
        with self.db.session() as s:
            p = Project(id=pid, owner_id=owner_id, wrapped_key=wrapped, name_enc=b"", filename_enc=b"")
            p.name_enc = crypto.encrypt(key, json.dumps(name).encode(), pid.encode())
            p.filename_enc = crypto.encrypt(key, json.dumps(filename).encode(), pid.encode())
            s.add(p)
            s.commit()
        return pid

    def get(self, pid: str, user: User) -> Project | None:
        if not pid or len(pid) != 32 or not all(c in "0123456789abcdef" for c in pid):
            return None
        with self.db.session() as s:
            p = s.get(Project, pid)
            if p is None or p.owner_id != user.id:  # cloisonnement strict, y compris pour l'administrateur
                return None
            return p

    def list(self, user: User) -> list[Project]:
        with self.db.session() as s:
            return list(s.scalars(select(Project).where(Project.owner_id == user.id)
                                  .order_by(Project.created_at.desc())).all())

    def update(self, pid: str, **fields) -> None:
        with self.db.session() as s:
            p = s.get(Project, pid)
            if p is None:
                return
            for k, v in fields.items():
                setattr(p, k, v)
            p.updated_at = utcnow()
            s.commit()

    def load_dataset(self, p: Project) -> Dataset:
        raw = crypto.read_encrypted(self.root / p.id / "source.enc", self._key(p), f"{p.id}:source")
        with tempfile.TemporaryDirectory(prefix="aa_") as tmp:
            return read_dataset(raw, self.filename(p), Path(tmp))

    def delete(self, pid: str) -> None:
        with self.db.session() as s:
            p = s.get(Project, pid)
            if p is not None:
                s.delete(p)  # destruction de la clé enveloppée : effacement cryptographique
                s.commit()
        crypto.shred_dir(self.root / pid)

    def purge_expired(self) -> int:
        limit = utcnow() - timedelta(days=self.settings.retention_days)
        with self.db.session() as s:
            old = [p.id for p in s.scalars(select(Project).where(Project.updated_at < limit)).all()]
        for pid in old:
            self.delete(pid)
            self.db.audit("purge_automatique", project_id=pid)
        # Répertoires orphelins (projet supprimé de la base mais fichiers restants)
        with self.db.session() as s:
            known = {pid for (pid,) in s.execute(select(Project.id)).all()}
        for d in self.root.iterdir():
            if d.is_dir() and d.name not in known:
                crypto.shred_dir(d)
        return len(old)

    # --- Résultats -------------------------------------------------------
    def results(self, p: Project) -> dict:
        return self.dec(p, p.results_enc, {"fichiers": [], "journal": []})

    def read_result(self, p: Project, name: str) -> bytes | None:
        for r in self.results(p)["fichiers"]:
            if r["stockage"] == name:
                return crypto.read_encrypted(self.root / p.id / "resultats" / name, self._key(p), f"{p.id}:{name}")
        return None

    # --- Exécution -------------------------------------------------------
    def submit(self, pid: str, user_id: int, provider_factory) -> None:
        self.update(pid, status="en_cours", progress=1, message="Analyse en file d'attente")
        self.pool.submit(self._run, pid, user_id, provider_factory)

    def _run(self, pid: str, user_id: int, provider_factory) -> None:
        from .pipeline import AnalysisConfig, run
        from .writing.composer import RequestSpec
        with self.db.session() as s:
            p = s.get(Project, pid)
        if p is None:
            return
        tmp = Path(tempfile.mkdtemp(prefix="aa_run_"))
        try:
            key = self._key(p)
            cfg = AnalysisConfig.from_dict(self.dec(p, p.config_enc, {}))
            spec = RequestSpec(**self.dec(p, p.spec_enc, {}))
            ds = self.load_dataset(p)
            provider = provider_factory(cfg)

            def progress(pct: int, msg: str) -> None:
                self.update(pid, progress=int(pct), message=msg[:300])

            out = run(ds, cfg, spec, tmp / "sortie", self.settings, self.pseudo_secret(p), progress, provider)
            res_dir = self.root / pid / "resultats"
            if res_dir.exists():
                crypto.shred_dir(res_dir)
            res_dir.mkdir(parents=True, mode=0o700)
            files = []
            labels = {"docx": "Document Word", "pptx": "Présentation (PowerPoint)", "xlsx": "Tableaux (Excel)",
                      "zip": "Dossier complet (ZIP)", "params": "Paramètres de reproductibilité (JSON)"}
            for kind in ("docx", "pptx", "xlsx", "zip", "params"):
                if kind not in out:
                    continue
                path: Path = out[kind]
                stor = f"{kind}.enc"
                crypto.write_encrypted(res_dir / stor, key, path.read_bytes(), f"{pid}:{stor}")
                files.append({"type": kind, "nom": path.name, "libelle": labels[kind], "stockage": stor,
                              "taille": path.stat().st_size})
            self.update(pid, status="termine", progress=100, message="Analyse terminée",
                        results_enc=self.enc(p, {"fichiers": files, "journal": out.get("log", []),
                                                 "retenir": out.get("retenir", {})}))
            self.db.audit("analyse_terminee", user_id=user_id, project_id=pid)
        except Exception as exc:  # noqa: BLE001
            log.error("Échec de l'analyse %s : %s", pid, type(exc).__name__)
            log.debug("%s", traceback.format_exc())
            self.update(pid, status="erreur", message=_user_message(exc))
            self.db.audit("analyse_echec", user_id=user_id, project_id=pid, detail=type(exc).__name__)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def _user_message(exc: Exception) -> str:
    from .stats.io import DataReadError
    if isinstance(exc, DataReadError):
        return str(exc)
    return ("L'analyse a échoué. Vérifiez le typage des variables (une variable qualitative déclarée comme continue, "
            "par exemple) et les effectifs par modalité, puis relancez.")
