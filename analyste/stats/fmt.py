"""Mise en forme des nombres selon les usages typographiques français."""

from __future__ import annotations

import math

NBSP = " "  # espace fine insécable, séparateur de milliers


def num(x, digits: int = 2) -> str:
    """Nombre décimal à la française : 1 234,57."""
    if x is None:
        return "-"
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return str(x)
    if math.isnan(xf):
        return "-"
    if math.isinf(xf):
        return "∞" if xf > 0 else "-∞"
    s = f"{xf:,.{digits}f}"
    s = s.replace(",", "\x00").replace(".", ",").replace("\x00", NBSP)
    if s.startswith("-") and float(xf) == 0:
        s = s[1:]
    return s


def integer(x) -> str:
    if x is None:
        return "-"
    try:
        return num(int(round(float(x))), 0)
    except (TypeError, ValueError):
        return str(x)


def pct(x, digits: int = 1) -> str:
    """Pourcentage à partir d'une proportion (0,253 -> 25,3 %)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    return f"{num(100 * float(x), digits)}{NBSP}%"


def pval(p) -> str:
    """Probabilité critique : « < 0,001 » sous le seuil d'affichage."""
    if p is None:
        return "-"
    try:
        pf = float(p)
    except (TypeError, ValueError):
        return str(p)
    if math.isnan(pf):
        return "-"
    if pf < 0.001:
        return "< 0,001"
    return num(pf, 3)


def stars(p) -> str:
    """Seuils usuels en sciences sociales : *** 1 %, ** 5 %, * 10 %."""
    if p is None:
        return ""
    try:
        pf = float(p)
    except (TypeError, ValueError):
        return ""
    if math.isnan(pf):
        return ""
    if pf < 0.01:
        return "***"
    if pf < 0.05:
        return "**"
    if pf < 0.10:
        return "*"
    return "ns"


STARS_NOTE = ("*** p < 0,01 ; ** p < 0,05 ; * p < 0,10 ; ns : non significatif au seuil de 10 %.")


def ci(lo, hi, digits: int = 2) -> str:
    return f"[{num(lo, digits)} ; {num(hi, digits)}]"


def p_phrase(p) -> str:
    """Formulation pour le texte : « p < 0,001 » ou « p = 0,032 »."""
    s = pval(p)
    return f"p {s}" if s.startswith("<") else f"p = {s}"
