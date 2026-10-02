"""Analyse descriptive univariée."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from ..writing.phrases import Redac, pcrit, valeur
from ..writing.style import a, de, guillemets, majuscule
from . import figures, fmt
from .io import Dataset, as_categorical
from .results import Figure, Section, Table

OUVERTURES_QUAL = ["S'agissant {de}, ", "En ce qui concerne {x}, ", "Quant {a}, ", "Pour ce qui est {de}, ",
                   "Concernant {x}, "]


def wilson_ci(k: float, n: float, z: float = 1.959964) -> tuple[float, float]:
    if n <= 0:
        return (np.nan, np.nan)
    p = k / n
    den = 1 + z ** 2 / n
    centre = (p + z ** 2 / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z ** 2 / (4 * n ** 2)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def normality(x: np.ndarray) -> tuple[str, float, float]:
    """(nom du test, statistique, p) : Shapiro-Wilk jusqu'à 5 000 obs., D'Agostino-Pearson au-delà."""
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


def _ouverture(i: int, x: str) -> str:
    return OUVERTURES_QUAL[i % len(OUVERTURES_QUAL)].format(de=de(x), a=a(x), x=x)


def _qual_phrase(R: Redac, col: str, ranked: list[tuple], i: int) -> str:
    """Commentaire d'une variable qualitative : modalité dominante, seconde modalité, intervalle de confiance."""
    x = R.v(col)
    (cat, _, p, lo, hi) = ranked[0]
    ic = f"(IC à 95 % : {fmt.pct(lo)} à {fmt.pct(hi)})"
    statut = "majoritaire" if p > 0.5 else "la plus représentée"
    if i % 2 == 0:
        txt = (f"{_ouverture(i, x)}la modalité {guillemets(cat)} est {statut} : elle concerne {fmt.pct(p)} des "
               f"{R.unite} {ic}")
    else:
        txt = (f"{_ouverture(i, x)}{fmt.pct(p)} des {R.unite} relèvent de la modalité {guillemets(cat)} {ic}, ce qui "
               f"en fait la modalité {'majoritaire' if p > 0.5 else 'la plus fréquente'}")
    if len(ranked) >= 3:
        cat2, _, p2, _, _ = ranked[1]
        txt += f", suivie de la modalité {guillemets(cat2)} ({fmt.pct(p2)})"
    return majuscule(txt) + "."


def _quant_phrase(R: Redac, col: str, kind: str, m: dict, i: int, first_skew: bool) -> str:
    x = R.v(col)
    v = lambda key: valeur(m[key], kind)  # noqa: E731
    if i % 2 == 0:
        txt = (f"{majuscule(x)} présente une moyenne de {fmt.num(m['moyenne'])} avec un écart type de "
               f"{fmt.num(m['ecart_type'])}, pour une médiane de {v('mediane')}.")
    else:
        txt = (f"En moyenne, {x} s'établit à {fmt.num(m['moyenne'])}, avec un écart type de "
               f"{fmt.num(m['ecart_type'])} ; la médiane est de {v('mediane')}.")
    txt += (f" Le premier et le troisième quartiles valent respectivement {v('q1')} et {v('q3')}, et les valeurs "
            f"vont de {v('min')} à {v('max')}.")
    skew, tp, tname = m["asymetrie"], m["p_normalite"], m["test"]
    if not np.isnan(skew):
        if abs(skew) < 0.5:
            txt += " La distribution est à peu près symétrique"
        else:
            txt += (f" La distribution est étalée vers les valeurs {'élevées' if skew > 0 else 'faibles'}, avec une "
                    f"asymétrie de {fmt.num(skew)}")
        if not np.isnan(tp):
            if tp < 0.05:
                lien = ", même si" if abs(skew) < 0.5 else ", et"
                txt += (f"{lien} le test de {tname} conduit à rejeter l'hypothèse de normalité, avec "
                        f"{pcrit(tp)}.")
                if abs(skew) < 0.5 and m.get("n", 0) > 1000 and not m.get("taille_dite"):
                    txt += (" Ce rejet s'explique en partie par la taille de l'échantillon, ce test devenant sensible "
                            "au moindre écart à la normalité lorsque les effectifs sont élevés.")
            else:
                txt += (f", et le test de {tname} ne permet pas de rejeter l'hypothèse de normalité, avec "
                        f"{pcrit(tp)}.")
        else:
            txt += "."
        if abs(skew) >= 0.5 and not np.isnan(tp) and tp < 0.05 and first_skew:
            txt += (" Cette asymétrie justifie, dans la suite des analyses, le recours à des tests non paramétriques "
                    "lorsque les conditions d'application des tests paramétriques ne sont pas réunies.")
    return txt


def describe(ds: Dataset, variables: list[str], outdir: Path, weight: str | None = None,
             max_figures: int = 8, outcome: str | None = None) -> Section:
    sec = Section(key="descriptif", title="Analyse descriptive", level=2)
    df = ds.df
    w_all = pd.to_numeric(df[weight], errors="coerce") if weight else None
    quant_rows, qual_rows = [], []
    quant_txt, qual_txt = [], []
    n_fig = 0
    sec.refs |= {"wilson1927", "shapiro1965"}
    event = None
    if outcome and outcome in ds.variables and ds.variables[outcome].kind == "binaire":
        from .design import event_level_for
        event = event_level_for([str(c) for c in as_categorical(df[outcome], ds.variables[outcome]).cat.categories])
    R = Redac(ds, outcome, event)
    skew_said = size_said = False
    dep_txt = ""

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
                "Écart type": fmt.num(sd), "Médiane": fmt.num(med), "[Q1 ; Q3]": fmt.ci(q1, q3),
                "[Min ; Max]": fmt.ci(xv.min(), xv.max()), "Asymétrie": fmt.num(skew),
                "Normalité (p)": fmt.pval(tp)})
            sec.add_facts(col, {"n": len(xv), "moyenne": mean, "ecart_type": sd, "mediane": med, "q1": q1,
                                "q3": q3, "min": xv.min(), "max": xv.max(), "asymetrie": skew,
                                "aplatissement": kurt, "p_normalite": tp})
            m = {"moyenne": mean, "ecart_type": sd, "mediane": med, "q1": q1, "q3": q3, "min": xv.min(),
                 "max": xv.max(), "asymetrie": skew, "p_normalite": tp, "test": tname, "n": len(xv),
                 "taille_dite": size_said}
            asym = not np.isnan(skew) and abs(skew) >= 0.5 and not np.isnan(tp) and tp < 0.05
            entier = bool(np.all(np.mod(xv, 1) == 0))
            quant_txt.append(_quant_phrase(R, col, "comptage" if entier else info.kind, m, len(quant_txt),
                                           asym and not skew_said))
            skew_said = skew_said or asym
            size_said = size_said or (not asym and len(xv) > 1000 and not np.isnan(tp) and tp < 0.05)
            if n_fig < max_figures:
                p = figures.histogram(x, label, outdir)
                sec.figures.append(Figure(p, f"Distribution {de(R.v(col))}"))
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
            ranked = []
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
                ranked.append((str(cat), c, p, lo, hi))
            ranked.sort(key=lambda t: -t[1])
            if ranked and col == outcome and event is not None:
                ev = next((t for t in ranked if t[0] == str(event)), ranked[0])
                dep_txt = (f"La variable dépendante de l'étude est {R.y}. Sur l'ensemble des {R.unite} pour "
                           f"{'lesquelles' if R.fem else 'lesquels'} elle est renseignée, {R.indicateur()} s'établit "
                           f"à {fmt.pct(ev[2])}, avec un intervalle de confiance à 95 % allant de {fmt.pct(ev[3])} "
                           f"à {fmt.pct(ev[4])}.")
                sec.key_points.append(f"{majuscule(R.indicateur())} s'établit à {fmt.pct(ev[2])} dans l'échantillon.")
            elif ranked:
                qual_txt.append(_qual_phrase(R, col, ranked, len(qual_txt)))
            if n_fig < max_figures and len(counts) <= 15:
                p = figures.bar_categories(counts, label, outdir)
                sec.figures.append(Figure(p, f"Répartition des {R.unite} selon {R.v(col)}"))
                n_fig += 1

    intro = (f"Cette section décrit les {R.unite} de l'échantillon selon les variables retenues pour l'étude. "
             "Les tableaux ci-dessous présentent la répartition des variables qualitatives, avec l'intervalle de "
             "confiance à 95 % de chaque pourcentage, puis les principales statistiques des variables quantitatives.")
    if weight:
        intro += " Les pourcentages et les moyennes tiennent compte de la pondération."
    sec.paragraphs.append(intro)
    if dep_txt:
        sec.paragraphs.append(dep_txt)
    for i in range(0, len(qual_txt), 2):  # deux variables par paragraphe
        sec.paragraphs.append(" ".join(qual_txt[i:i + 2]))
    sec.paragraphs.extend(quant_txt)
    wnote = (" Les moyennes et pourcentages sont pondérés ; les effectifs sont non pondérés et les intervalles de "
             "confiance utilisent l'effectif efficace de Kish." if weight else "")
    if quant_rows:
        sec.tables.append(Table(
            title="Statistiques descriptives des variables quantitatives",
            data=pd.DataFrame(quant_rows),
            note=("Le test de Shapiro-Wilk (D'Agostino-Pearson au-delà de 5 000 observations) teste l'hypothèse nulle "
                  "de normalité ; une probabilité critique inférieure à 0,05 conduit à la rejeter." + wnote)))
    if qual_rows:
        sec.tables.append(Table(
            title=f"Répartition des {R.unite} selon les variables qualitatives",
            data=pd.DataFrame(qual_rows),
            note="Les intervalles de confiance à 95 % sont ceux de Wilson. Les pourcentages sont calculés sur les "
                 "réponses renseignées."
            + wnote))
    sec.method_notes.append(
        "Pour l'analyse descriptive, les variables qualitatives sont décrites par leurs effectifs et leurs "
        "pourcentages, assortis d'intervalles de confiance à 95 % de Wilson (1927). Ces intervalles sont plus "
        "fiables que l'approximation normale lorsque les effectifs sont faibles ou que les proportions sont proches "
        "de zéro ou de un. Les variables quantitatives, quant à elles, sont décrites par leur moyenne, leur écart "
        "type, leur médiane et leurs quartiles, et leur normalité est examinée par le test de Shapiro et Wilk "
        "(1965).")
    return sec
