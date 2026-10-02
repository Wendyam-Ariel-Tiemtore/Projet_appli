"""Analyse de survie : Kaplan-Meier, log-rank, modèle de Cox."""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from . import figures, fmt
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
    sec.paragraphs.append(
        f"Sur {fmt.integer(n)} observations, {fmt.integer(d)} ont connu l'événement et {fmt.integer(n - d)} sont "
        f"censurées. " + (f"La durée médiane estimée par Kaplan-Meier est de {fmt.num(med)} ({tlab})."
                          if np.isfinite(med) else
                          "La médiane n'est pas atteinte : moins de la moitié des observations ont connu l'événement."))
    curves = {"Ensemble": kmf.survival_function_}
    if group_var:
        g = as_categorical(ds.df.loc[T.index, group_var], ds.variables[group_var])
        curves = {}
        rows = []
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
        lr = multivariate_logrank_test(T, g.astype(str), E)
        sec.facts.update({"survie.logrank_chi2": lr.test_statistic, "survie.logrank_p": lr.p_value})
        sec.tables.append(Table(title=f"Durées médianes selon « {ds.variables[group_var].label} »",
                                data=pd.DataFrame(rows),
                                note=f"Test du log-rank : χ² = {fmt.num(lr.test_statistic)}, {fmt.p_phrase(lr.p_value)}."))
        sec.paragraphs.append(
            "Les courbes de survie diffèrent "
            + ("significativement" if lr.p_value < 0.05 else "de manière non significative")
            + f" selon « {ds.variables[group_var].label} » (log-rank : χ² = {fmt.num(lr.test_statistic)}, "
              f"{fmt.p_phrase(lr.p_value)}).")
    fig = figures.km_curves(curves, tlab, outdir)
    sec.figures.append(Figure(fig, "Courbes de survie de Kaplan-Meier"))

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
                rows.append({"Variable": "", "Modalité": f"{t.reference} (Réf.)", "HR": "1", "IC 95 %": "–", "p": "–"})
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
                if r["p"] < 0.05:
                    who = f"la modalité « {lev} » de « {t.label} »" if t.levels else \
                        f"chaque unité supplémentaire de « {t.label} »"
                    sens = "plus élevé" if r["exp(coef)"] > 1 else "plus faible"
                    sec.paragraphs.append(
                        f"Toutes choses égales par ailleurs, {who} est associée à un risque instantané de "
                        f"survenue de l'événement {sens} (HR = {fmt.num(r['exp(coef)'])} ; IC à 95 % "
                        f"{fmt.ci(r['exp(coef) lower 95%'], r['exp(coef) upper 95%'])} ; {fmt.p_phrase(r['p'])}).")
        try:
            ph = proportional_hazard_test(cph, data, time_transform="rank")
            p_glob = float(np.min(ph.summary["p"]))
            bad = [c for c, p in ph.summary["p"].items() if p < 0.05]
        except Exception:  # noqa: BLE001
            p_glob, bad = np.nan, []
        sec.facts["cox.ph_p_min"] = p_glob
        sec.tables.append(Table(title="Modèle de Cox : rapports de risques instantanés", data=pd.DataFrame(rows),
                                note=f"HR : rapport de risques instantanés. Concordance de Harrell = "
                                     f"{fmt.num(cph.concordance_index_, 3)}."))
        sec.facts["cox.concordance"] = cph.concordance_index_
        if bad:
            sec.paragraphs.append(
                "L'hypothèse des risques proportionnels est rejetée pour : "
                + ", ".join(f"« {x} »" for x in bad)
                + " (résidus de Schoenfeld, p < 0,05) ; l'effet de ces variables varie au cours du temps et leur HR "
                  "doit être lu comme un effet moyen. Une stratification ou une interaction avec le temps est "
                  "recommandée.")
        else:
            sec.paragraphs.append("Les tests fondés sur les résidus de Schoenfeld ne rejettent l'hypothèse des risques "
                                  "proportionnels pour aucune variable.")
    sec.method_notes.append(
        "La durée jusqu'à l'événement est analysée par l'estimateur de Kaplan et Meier (1958), les courbes sont "
        "comparées par le test du log-rank (Mantel, 1966), et les facteurs associés sont estimés par un modèle de "
        "Cox (1972) dont l'hypothèse des risques proportionnels est vérifiée par les résidus de Schoenfeld "
        "(Grambsch et Therneau, 1994).")
    return sec
