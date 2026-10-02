"""Garde-fous de la rédaction assistée : aucun nombre ni aucune référence absents des résultats."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

NUM_RE = re.compile(r"(?<![\w.,])[-−]?\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?(?![\w])|(?<![\w.,])[-−]?\d+(?:[.,]\d+)?(?![\w])")
NAME = r"[A-ZÀ-Ý][\w'’\-]+(?:\s(?:de|van|von|der|da|du|le|la)\s[A-ZÀ-Ý][\w'’\-]+)?"
YEAR = r"(?:19|20)\d{2}[a-z]?"
PAREN_PIECE = re.compile(rf"^\s*(?:voir\s+|cf\.\s+)?({NAME})(?:\s+et\s+al\.|(?:,\s*{NAME})*(?:,?\s+et\s+{NAME})?)?,\s*({YEAR})")
NARRATIVE = re.compile(rf"({NAME})(?:\s+et\s+al\.|(?:,\s*{NAME})*(?:,?\s+et\s+{NAME})?)?\s+\(({YEAR})\)")
PAREN = re.compile(r"\(([^()]*?(?:19|20)\d{2}[^()]*?)\)")
CAUSAL_RE = re.compile(r"\b(cause[nts]?|causé|causal|provoqu\w*|entraîn\w*|engendr\w*|détermin(e|ent|é)\b|"
                       r"impact\w*|effet (de|du|des) .{1,40} sur)\b", re.IGNORECASE)


def _to_float(tok: str) -> float | None:
    t = tok.replace(" ", "").replace(" ", "").replace(" ", "").replace("−", "-").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def numbers_in(text: str) -> list[tuple[str, float, int]]:
    out = []
    for m in NUM_RE.finditer(text):
        tok = m.group(0)
        v = _to_float(tok)
        if v is None:
            continue
        dec = len(re.split(r"[.,]", tok)[1]) if re.search(r"[.,]\d+$", tok) else 0
        out.append((tok, v, dec))
    return out


@dataclass
class Allowed:
    values: set[float] = field(default_factory=set)
    citations: set[tuple[str, str]] = field(default_factory=set)  # (nom normalisé, année)

    def add_text(self, text: str) -> None:
        for _, v, _ in numbers_in(text):
            self.values.add(v)

    def add_value(self, v) -> None:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return
        if f == f:  # pas NaN
            self.values.add(f)
            for d in range(0, 4):
                self.values.add(round(f, d))

    def add_citations_from_text(self, text: str) -> None:
        for n, y in citations_in(text):
            self.citations.add((_norm(n), y[:4]))
            self.values.add(float(y[:4]))

    def add_citation(self, short: str) -> None:
        """short : « Nom, 2015 », « Nom et Nom, 2015 » ou « Nom et al., 2015 »."""
        m = re.match(r"\s*(.+?),\s*((?:19|20)\d{2})", short)
        if m:
            first = m.group(1).split(" et ")[0].split(",")[0].strip()
            self.citations.add((_norm(first), m.group(2)))
            self.values.add(float(m.group(2)))

    def number_ok(self, v: float, dec: int) -> bool:
        if dec == 0 and abs(v) <= 10 and float(v).is_integer():
            return True
        if (1900 <= v <= 2100) and float(v).is_integer():
            return v in self.values
        for a in self.values:
            if dec >= 1 and abs(round(a, dec) - v) < 10 ** (-dec) / 2 + 1e-12:
                return True
            if dec == 0 and (a == v or (abs(a) >= 10 and round(a) == v)):
                return True
        return False


def citations_in(text: str) -> list[tuple[str, str]]:
    """Citations auteur-date, entre parenthèses ou narratives : [(premier auteur, année)]."""
    found = []
    for m in PAREN.finditer(text):
        for piece in m.group(1).split(";"):
            pm = PAREN_PIECE.match(piece)
            if pm:
                found.append((pm.group(1), pm.group(2)))
    for m in NARRATIVE.finditer(text):
        found.append((m.group(1), m.group(2)))
    return found


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


@dataclass
class Check:
    ok: bool
    bad_numbers: list[str]
    bad_citations: list[str]
    causal: list[str]

    def feedback(self) -> str:
        parts = []
        if self.bad_numbers:
            parts.append("Nombres absents des résultats fournis (à supprimer) : " + ", ".join(self.bad_numbers[:15]))
        if self.bad_citations:
            parts.append("Références absentes de la liste autorisée (à supprimer) : " + "; ".join(self.bad_citations[:10]))
        if self.causal:
            parts.append("Formulations causales à remplacer par des formulations d'association : "
                         + ", ".join(sorted(set(self.causal))[:10]))
        return "\n".join(parts)


def check(text: str, allowed: Allowed, causal_ok: bool = False) -> Check:
    bad = [tok for tok, v, dec in numbers_in(text) if not allowed.number_ok(v, dec)]
    bad_c = [f"{n} ({y})" for n, y in citations_in(text) if (_norm(n), y[:4]) not in allowed.citations]
    causal = [] if causal_ok else [m.group(0) for m in CAUSAL_RE.finditer(text)]
    return Check(ok=not bad and not bad_c and not causal, bad_numbers=bad, bad_citations=bad_c, causal=causal)


def clean_markdown(text: str) -> str:
    """Retire titres et listes Markdown ; conserve des paragraphes séparés."""
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            continue
        s = re.sub(r"^[-*•]\s+", "", s)
        s = s.replace("**", "")
        lines.append(s)
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()
