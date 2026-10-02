"""Seuil de signification choisi par l'auteur (1 %, 5 % ou 10 %) pour la lecture des associations et des effets.

Les tests de conditions d'application (normalité, homogénéité des variances, ajustement du modèle, cotes
proportionnelles) restent au seuil conventionnel de 5 % : ils ne servent pas à conclure sur les hypothèses de
l'étude. La valeur est portée par une variable de contexte, propre à chaque analyse en cours d'exécution.
"""

from __future__ import annotations

from contextvars import ContextVar

SEUILS = (0.01, 0.05, 0.10)
_ALPHA: ContextVar[float] = ContextVar("seuil_signification", default=0.05)


def alpha() -> float:
    return _ALPHA.get()


def definir(valeur: float | None):
    """Fixe le seuil pour l'analyse en cours ; renvoie le jeton à passer à `retablir`."""
    v = float(valeur) if valeur is not None else 0.05
    if not any(abs(v - s) < 1e-9 for s in SEUILS):
        v = 0.05
    return _ALPHA.set(v)


def retablir(jeton) -> None:
    _ALPHA.reset(jeton)


def texte() -> str:
    """« 5 % », « 1 % » ou « 10 % »."""
    return f"{alpha() * 100:.0f} %"


def significatif(p: float) -> bool:
    try:
        return float(p) < alpha()
    except (TypeError, ValueError):
        return False
