"""Structures de résultats partagées par tous les modules d'analyse."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class Table:
    title: str
    data: pd.DataFrame  # cellules déjà formatées (chaînes)
    note: str = ""
    source: str = "Source : données de l'utilisateur, calculs de l'auteur."
    number: int | None = None  # attribué à l'assemblage du document


@dataclass
class Figure:
    path: Path
    caption: str
    source: str = "Source : données de l'utilisateur, calculs de l'auteur."
    number: int | None = None


@dataclass
class Section:
    """Bloc de résultats autonome : tableaux, figures, texte, faits chiffrés."""

    key: str
    title: str
    paragraphs: list[str] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    figures: list[Figure] = field(default_factory=list)
    method_notes: list[str] = field(default_factory=list)  # pour la section Méthodes
    warnings: list[str] = field(default_factory=list)
    refs: set[str] = field(default_factory=set)
    facts: dict[str, Any] = field(default_factory=dict)  # nombres autorisés pour la rédaction assistée
    level: int = 2
    key_points: list[str] = field(default_factory=list)  # phrases de synthèse (résumé, discussion, conclusion)
    extra: dict[str, Any] = field(default_factory=dict)  # objets internes (non publiés)

    def add_facts(self, prefix: str, values: dict[str, Any]) -> None:
        for k, v in values.items():
            self.facts[f"{prefix}.{k}"] = v


@dataclass
class AnalysisBundle:
    """Ensemble des résultats d'une demande."""

    sections: list[Section] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    data_summary: dict[str, Any] = field(default_factory=dict)

    def all_refs(self) -> set[str]:
        out: set[str] = set()
        for s in self.sections:
            out |= s.refs
        return out

    def all_facts(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for s in self.sections:
            out.update(s.facts)
        return out
