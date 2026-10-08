"""Exécution d'une analyse dans un processus séparé, borné en durée et en mémoire.

Une analyse très lourde (base volumineuse, rééchantillonnages) ne peut ainsi ni geler le serveur web ni épuiser sa
mémoire : au-delà des limites, le processus est arrêté et l'utilisateur reçoit un message clair, les autres
sessions n'étant pas affectées.
"""

from __future__ import annotations

import multiprocessing as mp
import queue
import time
from collections.abc import Callable


class DelaiDepasse(RuntimeError):
    pass


class MemoireDepassee(RuntimeError):
    pass


def _enfant(fonction, args: tuple, kwargs: dict, file, memoire_mo: int) -> None:
    try:
        import resource  # absent sous Windows : la limite de durée reste appliquée
        octets = memoire_mo * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (octets, octets))
    except (ImportError, ValueError, OSError):
        pass

    def progression(pct: int, msg: str) -> None:
        file.put(("progression", int(pct), str(msg)[:300]))

    try:
        res = fonction(*args, progress=progression, **kwargs)
        file.put(("resultat", res))
    except MemoryError:
        file.put(("erreur", MemoireDepassee("mémoire")))
    except BaseException as exc:  # noqa: BLE001 - transmis au parent
        try:
            file.put(("erreur", exc))
        except Exception:  # noqa: BLE001 - exception non sérialisable
            file.put(("erreur", RuntimeError(type(exc).__name__)))


def executer(fonction: Callable, args: tuple, kwargs: dict | None = None,
             progression: Callable[[int, str], None] | None = None, delai_s: float = 3600,
             memoire_mo: int = 4096):
    """Exécute fonction(*args, progress=..., **kwargs) dans un processus « spawn » ; renvoie son résultat."""
    ctx = mp.get_context("spawn")
    file = ctx.Queue()
    proc = ctx.Process(target=_enfant, args=(fonction, args, kwargs or {}, file, memoire_mo))
    proc.start()
    fin = time.monotonic() + delai_s
    try:
        while True:
            if time.monotonic() > fin:
                raise DelaiDepasse(f"{delai_s:.0f} s")
            try:
                msg = file.get(timeout=1.0)
            except queue.Empty:
                if not proc.is_alive():
                    if proc.exitcode in (-9, 137):
                        raise MemoireDepassee("processus arrêté") from None
                    raise RuntimeError(f"Processus d'analyse interrompu (code {proc.exitcode}).") from None
                continue
            if msg[0] == "progression":
                if progression is not None:
                    progression(msg[1], msg[2])
            elif msg[0] == "resultat":
                return msg[1]
            else:
                raise msg[1]
    finally:
        if proc.is_alive():
            proc.kill()
        proc.join(timeout=5)
        file.close()
