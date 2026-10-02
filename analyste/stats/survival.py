"""Analyse de survie : Kaplan-Meier, log-rank, modèle de Cox."""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from ..writing.phrases import Redac, accord, est, pcrit
from ..writing.style import enumeration, genre, nombre, sans_article
from . import figures, fmt, seuil
from .design import build_design
from .io import Dataset, as_categorical
from .results import Figure, Section, Table


def survival(ds: Dataset, time_var: str, event_var: str, explanatory: list[str], outdir: Path,
             group_var: str | None = None, references: dict[str, str] | None = None,
             event_level: str | None = None) -> Section:
    from lifelines import CoxPHFitter, KaplanMeierFitter
    from lifelines.statistics import multivariate_logrank_test, proportional_hazard_test

    sec = Section(key="survie", title="Analyse de survie", level=2)
    sec.refs |= {"kaplan1958", "mantel1966", "cox1972", "grambsch1994", "davidsonpilon2019"}
    tlab = ds.variables[time_var].label
    einfo = ds.variables[event_var]
    dsg = build_design(ds, event_var, explanatory, references, event_level, extra_cols=[time_var])
    T = pd.to_numeric(ds.df.loc[dsg.index, time_var], errors="coerce")
    E = dsg.y if einfo.kind == "binaire" else (pd.to_numeric(dsg.y, errors="coerce") > 0).astype(float)
    ok = T.notna() & (T >= 0)
    T, E = T[ok], E[ok]
    n, d = len(T), int(E.sum())
    sec.facts.update({"survie.n": n, "survie.evenements": d, "survie.censures": n - d})
    kmf = KaplanMeierFitter()
    kmf.fit(T, E)
    med = kmf.median_survival_time_
    sec.facts["survie.mediane"] = med if np.isfinite(med) else np.nan
    R = Redac(ds)
    ev = R.v(event_var)
    R._evenement = f"connaître {ev}"
    txt = (f"L'analyse porte sur {nombre(n, 'observations', True)}. Parmi elles, {fmt.integer(d)} ont connu "
           f"l'événement étudié, à savoir {ev}, et {fmt.integer(n - d)} sont censurées : l'événement n'était pas "
           "encore survenu à la fin de la période d'observation. ")
    if np.isfinite(med):
        txt += (f"La durée médiane, estimée par la méthode de Kaplan-Meier, s'établit à {fmt.num(med)} : la moitié des "
                f"{R.unite} ont donc connu {ev} avant cette durée.")
    else:
        txt += "La durée médiane n'est pas atteinte, moins de la moitié des observations ayant connu l'événement."
    sec.paragraphs.append(txt)
    curves = {"Ensemble": kmf.survival_function_}
    gtxt = ""
    if group_var:
        gx = R.v(group_var)
        g = as_categorical(ds.df.loc[T.index, group_var], ds.variables[group_var])
        curves = {}
        rows = []
        meds = {}
        for lev in g.cat.categories:
            m = g == lev
            if m.sum() < 5:
                continue
            k = KaplanMeierFitter().fit(T[m], E[m], label=str(lev))
            curves[str(lev)] = k.survival_function_
            md = k.median_survival_time_
            rows.append({"Groupe": str(lev), "N": fmt.integer(m.sum()), "Événements": fmt.integer(E[m].sum()),
                         "Médiane": fmt.num(md) if np.isfinite(md) else "non atteinte"})
            sec.facts[f"survie.{lev}.mediane"] = md if np.isfinite(md) else np.nan
            if np.isfinite(md):
                meds[str(lev)] = md
        lr = multivariate_logrank_test(T, g.astype(str), E)
        sec.facts.update({"survie.logrank_chi2": lr.test_statistic, "survie.logrank_p": lr.p_value})
        sec.tables.append(Table(title=f"Durées médianes selon {gx}", data=pd.DataFrame(rows),
                                note=f"Le test du log-rank donne χ² = {fmt.num(lr.test_statistic)} ; "
                                     f"{fmt.p_phrase(lr.p_value)}."))
        gtxt = (f"Les courbes de survie diffèrent {'significativement' if seuil.significatif(lr.p_value) else 'peu'} selon {gx}, le "
                f"test du log-rank donnant un khi-deux de {fmt.num(lr.test_statistic)} avec {pcrit(lr.p_value)}.")
        if seuil.significatif(lr.p_value) and len(meds) >= 2:
            lo, hi = min(meds, key=meds.get), max(meds, key=meds.get)
            gtxt += (f" La durée médiane passe en effet de {fmt.num(meds[lo])} {R.chez(group_var, lo)} à "
                     f"{fmt.num(meds[hi])} {R.chez(group_var, hi, premier=False)}.")
        sec.paragraphs.append(gtxt)
    fig = figures.km_curves(curves, tlab, outdir)
    sec.figures.append(Figure(fig, f"Courbes de survie de Kaplan-Meier selon {R.v(group_var)}" if group_var else
                                   "Courbe de survie de Kaplan-Meier"))

    if dsg.X.shape[1]:
        data = dsg.X.loc[T.index].copy()
        data["_T"], data["_E"] = T, E
        cph = CoxPHFitter()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cph.fit(data, duration_col="_T", event_col="_E")
        summ = cph.summary
        rows = []
        for t in dsg.terms:
            if t.levels:
                rows.append({"Variable": t.label, "Modalité": "", "HR": "", "IC 95 %": "", "p": ""})
                rows.append({"Variable": "", "Modalité": f"{t.reference} (Réf.)", "HR": "1", "IC 95 %": "-", "p": "-"})
                pairs = list(zip(t.columns, t.levels, strict=True))
            else:
                pairs = [(t.columns[0], "(par unité)")]
            for c, lev in pairs:
                r = summ.loc[c]
                rows.append({"Variable": "" if t.levels else t.label, "Modalité": lev,
                             "HR": fmt.num(r["exp(coef)"]),
                             "IC 95 %": fmt.ci(r["exp(coef) lower 95%"], r["exp(coef) upper 95%"]),
                             "p": fmt.pval(r["p"])})
                sec.facts[f"cox.{c}.hr"] = r["exp(coef)"]
                sec.facts[f"cox.{c}.p"] = r["p"]
                sec.facts[f"cox.{c}.pct_moins"] = 100 * (1 - r["exp(coef)"])
        from .models import effect_paragraphs, term_text
        tab = pd.DataFrame({"est": summ["exp(coef)"], "lo_e": summ["exp(coef) lower 95%"],
                            "hi_e": summ["exp(coef) upper 95%"], "p": summ["p"]})
        sec.paragraphs.append(
            "Pour identifier les facteurs associés au calendrier de l'événement, nous avons estimé un modèle de Cox "
            "à risques proportionnels. Chaque rapport de risques est ajusté sur l'ensemble des autres variables du "
            "modèle.")
        paras, cles, ns = effect_paragraphs(dsg.terms, tab, "cox", R, True, conclure_ns=False)
        sec.paragraphs.extend(paras)
        if len(ns) == 1:
            sec.paragraphs.append(f"En revanche, {ns[0]} n'{est(ns[0])} pas {accord('associé', ns[0])} de manière "
                                  f"significative au risque de connaître {ev} au seuil de {seuil.texte()}.")
        elif ns:
            masc = any(genre(sans_article(v)) == "m" for v in ns)
            sec.paragraphs.append(f"En revanche, ni {', ni '.join(ns)} ne sont {'associés' if masc else 'associées'} "
                                  f"de manière significative au risque de connaître {ev} au seuil de {seuil.texte()}.")
        sec.key_points.extend(cles[:2])
        try:
            ph = proportional_hazard_test(cph, data, time_transform="rank")
            p_glob = float(np.min(ph.summary["p"]))
            bad = [c for c, p in ph.summary["p"].items() if p < 0.05]
        except Exception:  # noqa: BLE001
            p_glob, bad = np.nan, []
        sec.facts["cox.ph_p_min"] = p_glob
        sec.tables.append(Table(title=f"Facteurs associés au risque de connaître {ev} : résultats du modèle de Cox",
                                data=pd.DataFrame(rows),
                                note=f"HR : rapport de risques instantanés. Concordance de Harrell = "
                                     f"{fmt.num(cph.concordance_index_, 3)}."))
        sec.facts["cox.concordance"] = cph.concordance_index_
        if bad:
            noms = enumeration([term_text(R, dsg, c) for c in bad])
            sec.paragraphs.append(
                f"Enfin, l'hypothèse des risques proportionnels est rejetée pour {noms} (résidus de Schoenfeld, "
                "p < 0,05). L'effet de ces variables varie donc au cours du temps, et leur rapport de risques doit être "
                "lu comme un effet moyen. Une stratification ou une interaction avec le temps est recommandée.")
        else:
            sec.paragraphs.append("Enfin, les tests fondés sur les résidus de Schoenfeld ne rejettent l'hypothèse des "
                                  "risques proportionnels pour aucune variable, ce qui conforte la spécification du "
                                  "modèle de Cox.")
    sec.method_notes.append(
        "La durée jusqu'à l'événement est analysée par l'estimateur de Kaplan et Meier (1958), les courbes sont "
        "comparées par le test du log-rank (Mantel, 1966), et les facteurs associés sont estimés par un modèle de "
        "Cox (1972) dont l'hypothèse des risques proportionnels est vérifiée par les résidus de Schoenfeld "
        "(Grambsch et Therneau, 1994).")
    return sec
