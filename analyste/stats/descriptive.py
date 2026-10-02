"""Analyse descriptive univariée."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from . import figures, fmt
from .io import Dataset, as_categorical
from .results import Section, Table


def wilson_ci(k: float, n: float, z: float = 1.959964) -> tuple[float, float]:
    if n <= 0:
        return (np.nan, np.nan)
    p = k / n
    den = 1 + z ** 2 / n
    centre = (p + z ** 2 / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z ** 2 / (4 * n ** 2)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def normality(x: np.ndarray) -> tuple[str, float, float]:
    """(nom du test, statistique, p) — Shapiro-Wilk jusqu'à 5 000 obs., D'Agostino-Pearson au-delà."""
    x = x[np.isfinite(x)]
    if len(x) < 3 or np.ptp(x) == 0:
        return ("non calculable", np.nan, np.nan)
    if len(x) <= 5000:
        r = stats.shapiro(x)
        return ("Shapiro-Wilk", float(r.statistic), float(r.pvalue))
    r = stats.normaltest(x)
    return ("D'Agostino-Pearson", float(r.statistic), float(r.pvalue))


def _wmean_sd(x: np.ndarray, w: np.ndarray) -> tuple[float, float]:
    m = np.average(x, weights=w)
    v = np.average((x - m) ** 2, weights=w) * (w.sum() / (w.sum() - 1)) if w.sum() > 1 else np.nan
    return float(m), float(np.sqrt(v))


def describe(ds: Dataset, variables: list[str], outdir: Path, weight: str | None = None,
             max_figures: int = 8) -> Section:
    sec = Section(key="descriptif", title="Analyse descriptive", level=2)
    df = ds.df
    w_all = pd.to_numeric(df[weight], errors="coerce") if weight else None
    quant_rows, qual_rows = [], []
    n_fig = 0
    sec.refs |= {"wilson1927", "shapiro1965"}

    for col in variables:
        info = ds.variables[col]
        label = info.label
        if info.kind in ("continue", "comptage"):
            x = pd.to_numeric(df[col], errors="coerce")
            mask = x.notna()
            xv = x[mask].to_numpy(dtype=float)
            if len(xv) == 0:
                continue
            if weight:
                wv = w_all[mask].fillna(0).to_numpy(dtype=float)
                mean, sd = _wmean_sd(xv, wv)
            else:
                mean, sd = float(np.mean(xv)), float(np.std(xv, ddof=1)) if len(xv) > 1 else np.nan
            q1, med, q3 = np.percentile(xv, [25, 50, 75])
            skew = float(stats.skew(xv)) if len(xv) > 2 else np.nan
            kurt = float(stats.kurtosis(xv)) if len(xv) > 3 else np.nan
            tname, _, tp = normality(xv)
            quant_rows.append({
                "Variable": label, "N": fmt.integer(len(xv)), "Moyenne": fmt.num(mean),
                "Écart type": fmt.num(sd), "Médiane": fmt.num(med), "Q1 – Q3": f"{fmt.num(q1)} – {fmt.num(q3)}",
                "Min – Max": f"{fmt.num(xv.min())} – {fmt.num(xv.max())}", "Asymétrie": fmt.num(skew),
                "Normalité (p)": fmt.pval(tp)})
            sec.add_facts(col, {"n": len(xv), "moyenne": mean, "ecart_type": sd, "mediane": med, "q1": q1,
                                "q3": q3, "min": xv.min(), "max": xv.max(), "asymetrie": skew,
                                "aplatissement": kurt, "p_normalite": tp})
            shape = ""
            if not np.isnan(skew):
                if abs(skew) < 0.5:
                    shape = "une distribution à peu près symétrique"
                elif skew > 0:
                    shape = "une distribution étalée vers les valeurs élevées (asymétrie positive)"
                else:
                    shape = "une distribution étalée vers les valeurs faibles (asymétrie négative)"
            norm_txt = ("la normalité est rejetée" if tp < 0.05 else "la normalité n'est pas rejetée") \
                if not np.isnan(tp) else ""
            sec.paragraphs.append(
                f"« {label} » a une moyenne de {fmt.num(mean)} (écart type {fmt.num(sd)}) et une médiane de "
                f"{fmt.num(med)}, la moitié centrale des observations se situant entre {fmt.num(q1)} et "
                f"{fmt.num(q3)}. Elle présente {shape}"
                + (f" ; {norm_txt} ({tname}, {fmt.p_phrase(tp)})." if norm_txt else "."))
            if n_fig < max_figures:
                p = figures.histogram(x, label, outdir)
                from .results import Figure
                sec.figures.append(Figure(p, f"Distribution de « {label} »"))
                n_fig += 1
        elif info.kind in ("binaire", "nominale", "ordinale"):
            s = as_categorical(df[col], info)
            if weight:
                ww = w_all.fillna(0)
                counts = ww.groupby(s, observed=False).sum()
                raw_counts = s.value_counts(sort=False)
                wnn = ww[s.notna()]
                n_eff = (wnn.sum() ** 2) / (wnn ** 2).sum() if (wnn ** 2).sum() > 0 else 0
            else:
                counts = s.value_counts(sort=False)
                raw_counts = counts
                n_eff = counts.sum()
            total = counts.sum()
            top = None
            first = True
            for cat, c in counts.items():
                p = c / total if total else np.nan
                lo, hi = wilson_ci(p * n_eff, n_eff)
                qual_rows.append({"Variable": label if first else "", "Modalité": str(cat),
                                  "Effectif": fmt.integer(raw_counts[cat]),
                                  "Pourcentage": fmt.pct(p), "IC 95 %": f"[{fmt.pct(lo)} ; {fmt.pct(hi)}]"})
                first = False
                sec.facts[f"{col}.{cat}.pct"] = 100 * p
                sec.facts[f"{col}.{cat}.n"] = int(raw_counts[cat])
                if top is None or c > top[1]:
                    top = (cat, c, p, lo, hi)
            if top:
                sec.paragraphs.append(
                    f"Pour « {label} », la modalité la plus fréquente est « {top[0]} », qui regroupe "
                    f"{fmt.pct(top[2])} des observations renseignées (IC à 95 % : {fmt.pct(top[3])} à "
                    f"{fmt.pct(top[4])}).")
            if n_fig < max_figures and len(counts) <= 15:
                from .results import Figure
                p = figures.bar_categories(counts, label, outdir)
                sec.figures.append(Figure(p, f"Répartition de « {label} »"))
                n_fig += 1

    wnote = (" Les moyennes et pourcentages sont pondérés ; les effectifs sont non pondérés et les intervalles de "
             "confiance utilisent l'effectif efficace de Kish." if weight else "")
    if quant_rows:
        sec.tables.append(Table(
            title="Statistiques descriptives des variables quantitatives",
            data=pd.DataFrame(quant_rows),
            note=("Normalité : test de Shapiro-Wilk (D'Agostino-Pearson au-delà de 5 000 observations) ; "
                  "une probabilité inférieure à 0,05 conduit à rejeter l'hypothèse de normalité." + wnote)))
    if qual_rows:
        sec.tables.append(Table(
            title="Répartition des variables qualitatives",
            data=pd.DataFrame(qual_rows),
            note="Intervalles de confiance à 95 % de Wilson. Pourcentages calculés sur les réponses renseignées."
            + wnote))
    sec.method_notes.append(
        "Les variables qualitatives sont décrites par leurs effectifs et pourcentages, assortis d'intervalles de "
        "confiance à 95 % de Wilson (1927), plus fiables que l'approximation normale pour les petits effectifs "
        "et les proportions extrêmes. Les variables quantitatives sont décrites par leur moyenne, écart type, "
        "médiane et quartiles ; leur normalité est examinée par le test de Shapiro et Wilk (1965).")
    return sec
