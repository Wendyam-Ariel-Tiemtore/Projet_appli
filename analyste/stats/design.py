"""Construction des matrices de modélisation (indicatrices, modalités de référence, échantillon d'analyse)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .io import Dataset, as_categorical

POSITIVE = ("oui", "yes", "1", "vrai", "true", "présent", "present", "positif", "malade", "décédé", "decede")


@dataclass
class Term:
    variable: str
    label: str
    kind: str
    columns: list[str]  # colonnes de la matrice
    levels: list[str] = field(default_factory=list)  # modalités non de référence
    reference: str | None = None


@dataclass
class Design:
    y: pd.Series
    X: pd.DataFrame  # sans constante
    terms: list[Term]
    n_total: int
    n_used: int
    index: pd.Index
    event_level: str | None = None
    y_categories: list[str] = field(default_factory=list)


def event_level_for(categories: list[str], chosen: str | None = None) -> str:
    if chosen and chosen in categories:
        return chosen
    for c in categories:
        if c.strip().lower() in POSITIVE:
            return c
    return categories[-1]


NEGATIVE = ("non", "no", "0", "faux", "false", "absent", "négatif", "negatif", "aucun", "aucune", "jamais")


def default_reference(s: pd.Series, info) -> str:
    """Référence : modalité « négative » pour une binaire, première pour une ordinale, la plus fréquente sinon."""
    cats = [str(c) for c in s.cat.categories]
    if info.kind == "binaire":
        for c in cats:
            if c.strip().lower() in NEGATIVE:
                return c
    if info.kind in ("ordinale",):
        return cats[0]
    counts = s.value_counts()
    return str(counts.idxmax()) if len(counts) else cats[0]


def build_design(ds: Dataset, outcome: str, explanatory: list[str], references: dict[str, str] | None = None,
                 event_level: str | None = None, extra_cols: list[str] | None = None) -> Design:
    references = references or {}
    df = ds.df
    yinfo = ds.variables[outcome]
    cols = [outcome] + [c for c in explanatory if c != outcome] + (extra_cols or [])
    sub = df[cols].copy()
    n_total = len(sub)
    sub = sub.dropna()
    terms: list[Term] = []
    parts = []
    for c in explanatory:
        if c == outcome:
            continue
        info = ds.variables[c]
        if info.kind in ("binaire", "nominale", "ordinale"):
            s = as_categorical(sub[c], info).cat.remove_unused_categories()
            cats = [str(x) for x in s.cat.categories]
            if len(cats) < 2:
                continue
            ref = references.get(c) if references.get(c) in cats else default_reference(s, info)
            levels = [x for x in cats if x != ref]
            names = []
            for lev in levels:
                nm = f"{c}[{lev}]"
                parts.append(pd.Series((s.astype(str) == lev).astype(float), index=sub.index, name=nm))
                names.append(nm)
            terms.append(Term(c, info.label, info.kind, names, levels, ref))
        elif info.kind in ("continue", "comptage"):
            x = pd.to_numeric(sub[c], errors="coerce").astype(float)
            parts.append(x.rename(c))
            terms.append(Term(c, info.label, info.kind, [c]))
    X = pd.concat(parts, axis=1) if parts else pd.DataFrame(index=sub.index)
    # Retirer les indicatrices sans variation (modalité absente de l'échantillon d'analyse)
    const_cols = [c for c in X.columns if X[c].nunique() < 2]
    if const_cols:
        X = X.drop(columns=const_cols)
        for t in terms:
            keep = [(col, lev) for col, lev in zip(t.columns, t.levels or t.columns, strict=False)
                    if col not in const_cols]
            t.columns = [k for k, _ in keep]
            if t.levels:
                t.levels = [lv for _, lv in keep]
        terms = [t for t in terms if t.columns]

    ycats: list[str] = []
    ev = None
    if yinfo.kind == "binaire":
        ys = as_categorical(sub[outcome], yinfo)
        ycats = [str(x) for x in ys.cat.categories]
        ev = event_level_for(ycats, event_level)
        y = (ys.astype(str) == ev).astype(float)
    elif yinfo.kind in ("nominale", "ordinale"):
        ys = as_categorical(sub[outcome], yinfo).cat.remove_unused_categories()
        ycats = [str(x) for x in ys.cat.categories]
        y = ys
    else:
        y = pd.to_numeric(sub[outcome], errors="coerce").astype(float)
    return Design(y=y, X=X, terms=terms, n_total=n_total, n_used=len(sub), index=sub.index, event_level=ev,
                  y_categories=ycats)


def vif(X: pd.DataFrame) -> pd.Series:
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    if X.shape[1] < 2:
        return pd.Series(1.0, index=X.columns)
    Xc = np.column_stack([np.ones(len(X)), X.to_numpy(dtype=float)])
    out = {}
    for i, c in enumerate(X.columns, start=1):
        try:
            out[c] = float(variance_inflation_factor(Xc, i))
        except (np.linalg.LinAlgError, ZeroDivisionError):
            out[c] = np.inf
    return pd.Series(out)
