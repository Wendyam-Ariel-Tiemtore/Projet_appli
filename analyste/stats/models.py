"""Modélisation explicative à un niveau : linéaire, logistique (binaire, multinomiale, ordonnée), comptage."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

from ..writing.phrases import Redac, accord, elision, est, pcrit
from ..writing.style import a, de, enumeration, genre, guillemets, majuscule, nombre, sans_article
from . import figures, fmt
from .design import Design, build_design, vif
from .io import Dataset
from .results import Figure, Section, Table

MODEL_NAMES = {
    "lineaire": "Régression linéaire (moindres carrés ordinaires)",
    "logistique": "Régression logistique binaire",
    "multinomiale": "Régression logistique multinomiale",
    "ordonnee": "Régression logistique ordonnée (cotes proportionnelles)",
    "poisson": "Régression de Poisson",
    "binomiale_negative": "Régression binomiale négative",
}
EFFECT = {"lineaire": "β", "logistique": "OR", "multinomiale": "RRR", "ordonnee": "OR",
          "poisson": "IRR", "binomiale_negative": "IRR", "cox": "HR"}


def model_kind(outcome_kind: str) -> str:
    return {"binaire": "logistique", "nominale": "multinomiale", "ordinale": "ordonnee",
            "comptage": "poisson", "continue": "lineaire"}.get(outcome_kind, "lineaire")


# ---------------------------------------------------------------------------
# Ajustement
# ---------------------------------------------------------------------------

class Fit:
    """Résultat homogène : estimations sur l'échelle de lecture (OR, IRR, β)."""

    def __init__(self, kind: str, res, X: pd.DataFrame, y, exp_scale: bool, cluster_used: bool):
        self.kind, self.res, self.X, self.y = kind, res, X, y
        self.exp_scale, self.cluster_used = exp_scale, cluster_used

    def table(self) -> pd.DataFrame:
        params, ci, p = self.res.params, self.res.conf_int(), self.res.pvalues
        if isinstance(params, pd.Series):
            out = pd.DataFrame({"coef": params, "lo": ci.iloc[:, 0], "hi": ci.iloc[:, 1], "p": p})
        else:  # pragma: no cover - multinomial géré séparément
            raise TypeError
        if self.exp_scale:
            out[["est", "lo_e", "hi_e"]] = np.exp(out[["coef", "lo", "hi"]])
        else:
            out[["est", "lo_e", "hi_e"]] = out[["coef", "lo", "hi"]]
        return out


def _cov_kwargs(cluster: pd.Series | None, default: str):
    if cluster is not None:
        codes = pd.factorize(cluster)[0]
        return {"cov_type": "cluster", "cov_kwds": {"groups": codes}}
    return {"cov_type": default} if default else {}


def fit_simple(kind: str, y, X: pd.DataFrame, cluster: pd.Series | None = None) -> Fit:
    X1 = sm.add_constant(X, has_constant="add")
    if kind == "lineaire":
        res = sm.OLS(y, X1).fit(**_cov_kwargs(cluster, "HC3"))
        return Fit(kind, res, X, y, False, cluster is not None)
    if kind == "logistique":
        res = sm.GLM(y, X1, family=sm.families.Binomial()).fit(**_cov_kwargs(cluster, "nonrobust"))
        return Fit(kind, res, X, y, True, cluster is not None)
    if kind in ("poisson", "binomiale_negative"):
        if kind == "poisson":
            res = sm.GLM(y, X1, family=sm.families.Poisson()).fit(**_cov_kwargs(cluster, "nonrobust"))
        else:
            res = sm.NegativeBinomial(y, X1).fit(disp=0, maxiter=300, **_cov_kwargs(cluster, "nonrobust"))
        return Fit(kind, res, X, y, True, cluster is not None)
    raise ValueError(kind)


def overdispersion_test(y: np.ndarray, mu: np.ndarray) -> tuple[float, float]:
    """Test de Cameron et Trivedi (1990) : régression auxiliaire sans constante."""
    aux_y = ((y - mu) ** 2 - y) / mu
    r = sm.OLS(aux_y, mu).fit()
    return float(r.params[0]), float(r.pvalues[0])


def hosmer_lemeshow(y: np.ndarray, p: np.ndarray, g: int = 10) -> tuple[float, int, float]:
    order = np.argsort(p)
    y, p = y[order], p[order]
    groups = np.array_split(np.arange(len(p)), g)
    chi = 0.0
    for idx in groups:
        if len(idx) == 0:
            continue
        o1, e1 = y[idx].sum(), p[idx].sum()
        o0, e0 = len(idx) - o1, len(idx) - e1
        if e1 > 0:
            chi += (o1 - e1) ** 2 / e1
        if e0 > 0:
            chi += (o0 - e0) ** 2 / e0
    dof = g - 2
    return float(chi), dof, float(stats.chi2.sf(chi, dof))


def brant_test(y_codes: np.ndarray, X: pd.DataFrame) -> tuple[float, int, float]:
    """Test de Brant (1990) de l'hypothèse des cotes proportionnelles (test global de Wald)."""
    J = int(y_codes.max()) + 1
    X1 = np.column_stack([np.ones(len(X)), X.to_numpy(dtype=float)])
    k = X.shape[1]
    betas, pis, infos = [], [], []
    for j in range(J - 1):
        yj = (y_codes > j).astype(float)
        if yj.min() == yj.max():
            return np.nan, 0, np.nan
        r = sm.Logit(yj, X1).fit(disp=0, maxiter=200)
        b = r.params
        pi = 1 / (1 + np.exp(-(X1 @ b)))
        betas.append(b[1:])
        pis.append(pi)
        infos.append(np.linalg.pinv(X1.T @ (X1 * (pi * (1 - pi))[:, None])))
    m = J - 1
    V = np.zeros((m * k, m * k))
    for j in range(m):
        for l_ in range(j, m):
            w = pis[l_] * (1 - pis[j])  # Cov(1{y>j}, 1{y>l}) pour j <= l
            cross = infos[j] @ (X1.T @ (X1 * w[:, None])) @ infos[l_]
            block = cross[1:, 1:]
            V[j * k:(j + 1) * k, l_ * k:(l_ + 1) * k] = block
            V[l_ * k:(l_ + 1) * k, j * k:(j + 1) * k] = block.T
    B = np.concatenate(betas)
    D = np.zeros(((m - 1) * k, m * k))
    for j in range(m - 1):
        D[j * k:(j + 1) * k, 0:k] = np.eye(k)
        D[j * k:(j + 1) * k, (j + 1) * k:(j + 2) * k] = -np.eye(k)
    DB = D @ B
    W = float(DB @ np.linalg.pinv(D @ V @ D.T) @ DB)
    dof = (m - 1) * k
    return W, dof, float(stats.chi2.sf(W, dof))


# ---------------------------------------------------------------------------
# Analyse explicative complète
# ---------------------------------------------------------------------------

def explain(ds: Dataset, outcome: str, explanatory: list[str], outdir: Path,
            references: dict[str, str] | None = None, event_level: str | None = None,
            blocks: list[list[str]] | None = None, cluster: str | None = None) -> Section:
    yinfo = ds.variables[outcome]
    kind = model_kind(yinfo.kind)
    sec = Section(key="multivarie", title="Analyse explicative multivariée", level=2)
    extra = [cluster] if cluster and cluster not in explanatory else []
    dsg = build_design(ds, outcome, explanatory, references, event_level, extra_cols=extra)
    if dsg.X.shape[1] == 0 or dsg.n_used < 20:
        sec.warnings.append("L'effectif ou le nombre de variables est insuffisant pour estimer un modèle multivarié.")
        return sec
    R = Redac(ds, outcome, dsg.event_level)
    clus = ds.df.loc[dsg.index, cluster] if cluster else None
    excluded = dsg.n_total - dsg.n_used
    sec.facts.update({"modele.n": dsg.n_used, "modele.n_exclus": excluded,
                      "modele.pct_exclus": 100 * excluded / dsg.n_total})
    if excluded / dsg.n_total > 0.10:
        sec.warnings.append(
            f"Au total, {fmt.pct(excluded / dsg.n_total)} des observations sont exclues du modèle en raison de valeurs "
            "manquantes sur au moins une variable (analyse en cas complets).")

    if kind == "multinomiale":
        return _explain_multinomial(ds, dsg, sec, outdir, R)
    if kind == "ordonnee":
        return _explain_ordinal(ds, dsg, sec, outdir, R)

    y = dsg.y.to_numpy(dtype=float)
    notes = []
    if kind == "poisson":
        pois = fit_simple("poisson", y, dsg.X)
        alpha_od, p_od = overdispersion_test(y, pois.res.fittedvalues.to_numpy())
        sec.facts.update({"modele.surdispersion_alpha": alpha_od, "modele.surdispersion_p": p_od})
        if p_od < 0.05 and alpha_od > 0:
            kind = "binomiale_negative"
            notes.append(f"Le test de Cameron et Trivedi (1990) met en évidence une surdispersion, avec {pcrit(p_od)}. "
                         "Nous avons donc retenu le modèle binomial négatif plutôt que le modèle de Poisson.")
        else:
            notes.append(f"Le test de Cameron et Trivedi (1990) ne met pas en évidence de surdispersion, avec "
                         f"{pcrit(p_od)}. Le modèle de Poisson est donc conservé.")
        sec.refs.add("cameron1990")

    full = fit_simple(kind, y, dsg.X, clus)
    eff = EFFECT[kind]

    # Modèles emboîtés (blocs) ou bruts / ajustés
    if blocks:
        cumulative, models = [], []
        for b in blocks:
            cumulative += [c for c in b if c in [t.variable for t in dsg.terms]]
            cols = [col for t in dsg.terms if t.variable in cumulative for col in t.columns]
            models.append(fit_simple(kind, y, dsg.X[cols], clus))
        tab = _multi_model_table(dsg, models, eff, kind)
        sec.tables.append(Table(title=f"Facteurs associés {a(R.y)} : modèles emboîtés ({_nom(kind)})"
                                + (f", modalité modélisée {guillemets(dsg.event_level)}" if dsg.event_level else ""),
                                data=tab, note=_effect_note(kind, dsg) + " " + fmt.STARS_NOTE))
        full = models[-1]
    else:
        crude = {}
        for t in dsg.terms:
            f1 = fit_simple(kind, y, dsg.X[t.columns], clus)
            crude.update(f1.table().to_dict("index"))
        tab = _crude_adjusted_table(dsg, crude, full.table().to_dict("index"), eff, kind)
        sec.tables.append(Table(
            title=f"Facteurs associés {a(R.y)} : résultats de la {_nom(kind)}"
                  + (f" (modalité modélisée : {guillemets(dsg.event_level)})" if dsg.event_level else ""),
            data=tab, note=_effect_note(kind, dsg)))

    # Diagnostics
    diag_rows, diag_facts, diag_text = _diagnostics(kind, full, dsg, y, R)
    sec.tables.append(Table(title="Qualité d'ajustement et diagnostics du modèle", data=pd.DataFrame(diag_rows),
                            note="L'interprétation de chaque indicateur est précisée dans la section consacrée aux "
                                 "méthodes."))
    sec.facts.update(diag_facts)
    sec.refs |= _model_refs(kind)

    # Graphique en forêt
    ft = full.table()
    ft = ft.drop(index="const", errors="ignore")
    rows = [{"terme": _term_label(dsg, c), "est": r["est"], "lo": r["lo_e"], "hi": r["hi_e"]} for c, r in ft.iterrows()]
    if rows:
        p = figures.forest(pd.DataFrame(rows), {"OR": "Rapport de cotes", "IRR": "Rapport de taux d'incidence",
                                                  "β": "Coefficient"}.get(eff, eff), outdir,
                           log_scale=full.exp_scale)
        long_ = {"OR": "rapports de cotes", "IRR": "rapports de taux d'incidence", "β": "coefficients"}.get(eff, eff)
        sec.figures.append(Figure(p, f"Facteurs associés {a(R.y)} : {long_} ajustés et intervalles de confiance à "
                                     "95 %"))

    # Texte
    sec.paragraphs.append(_intro_sentence(kind, dsg, R))
    sec.paragraphs.extend(notes)
    sec.paragraphs.extend(diag_text)
    effets, cles = _effect_sentences(dsg, full, kind, R)
    sec.paragraphs.extend(effets)
    sec.key_points.extend(cles)
    if not blocks:
        sec.paragraphs.extend(_crude_vs_adjusted(dsg, crude, full, R))
    for c, r in ft.iterrows():
        sec.facts[f"mod.{c}.est"] = r["est"]
        sec.facts[f"mod.{c}.ic_bas"] = r["lo_e"]
        sec.facts[f"mod.{c}.ic_haut"] = r["hi_e"]
        sec.facts[f"mod.{c}.p"] = r["p"]
        if full.exp_scale:
            sec.facts[f"mod.{c}.pct_variation"] = 100 * (r["est"] - 1)
            sec.facts[f"mod.{c}.pct_variation_abs"] = abs(100 * (r["est"] - 1))
    sec.method_notes.append(_method_note(kind, clus is not None, dsg))
    sec.extra["fit"] = full
    sec.extra["design"] = dsg
    return sec


def _term_label(dsg: Design, col: str) -> str:
    for t in dsg.terms:
        if col in t.columns:
            if t.levels:
                lev = t.levels[t.columns.index(col)]
                return f"{t.label} : {lev}"
            return t.label
    return col


def _effect_note(kind: str, dsg: Design) -> str:
    base = {
        "logistique": "OR : rapport de cotes ; un OR supérieur à 1 indique une cote plus élevée que la modalité de "
                      "référence (Réf.), un OR inférieur à 1 une cote plus faible.",
        "lineaire": "β : variation moyenne de la variable dépendante associée à la modalité (par rapport à la "
                    "référence) ou à une unité supplémentaire de la variable ; erreurs types robustes HC3.",
        "poisson": "IRR : rapport de taux d'incidence.",
        "binomiale_negative": "IRR : rapport de taux d'incidence (modèle binomial négatif NB2).",
    }.get(kind, "")
    return (base + " Association brute : modèle ne contenant que la variable ; association ajustée : modèle "
            "complet, toutes choses égales par ailleurs. Réf. : modalité de référence. IC : intervalle de confiance "
            "à 95 %.")


def _crude_adjusted_table(dsg: Design, crude: dict, adj: dict, eff: str, kind: str) -> pd.DataFrame:
    rows = []
    for t in dsg.terms:
        if t.levels:
            rows.append({"Variable": t.label, "Modalité": "", f"{eff} brut": "", "IC 95 % (brut)": "", "p (brut)": "",
                         f"{eff} ajusté": "", "IC 95 % (ajusté)": "", "p (ajusté)": ""})
            rows.append({"Variable": "", "Modalité": f"{t.reference} (Réf.)", f"{eff} brut": "1" if eff != "β" else "0",
                         "IC 95 % (brut)": "-", "p (brut)": "-", f"{eff} ajusté": "1" if eff != "β" else "0",
                         "IC 95 % (ajusté)": "-", "p (ajusté)": "-"})
            for col, lev in zip(t.columns, t.levels, strict=True):
                rows.append(_ca_row("", lev, crude.get(col), adj.get(col), eff))
        else:
            rows.append(_ca_row(t.label, "(par unité)", crude.get(t.columns[0]), adj.get(t.columns[0]), eff))
    return pd.DataFrame(rows)


def _ca_row(var: str, mod: str, c: dict | None, a: dict | None, eff: str) -> dict:
    def three(d):
        if not d:
            return "-", "-", "-"
        return fmt.num(d["est"]), fmt.ci(d["lo_e"], d["hi_e"]), fmt.pval(d["p"])
    cb, cci, cp = three(c)
    ab, aci, ap = three(a)
    return {"Variable": var, "Modalité": mod, f"{eff} brut": cb, "IC 95 % (brut)": cci, "p (brut)": cp,
            f"{eff} ajusté": ab, "IC 95 % (ajusté)": aci, "p (ajusté)": ap}


def _multi_model_table(dsg: Design, models: list[Fit], eff: str, kind: str) -> pd.DataFrame:
    tabs = [m.table() for m in models]
    names = [f"Modèle {i + 1}" for i in range(len(models))]
    rows = [dict({"Variable": "Constante", "Modalité": ""},
                 **{nm: f"{fmt.num(tb.loc['const', 'est'])}{fmt.stars(tb.loc['const', 'p'])}" if "const" in tb.index
                    else "" for nm, tb in zip(names, tabs, strict=True)})]
    for t in dsg.terms:
        if t.levels:
            rows.append(dict({"Variable": t.label, "Modalité": ""}, **{nm: "" for nm in names}))
            rows.append(dict({"Variable": "", "Modalité": f"{t.reference}"},
                             **{nm: ("Réf." if t.columns[0] in tb.index else "") for nm, tb in
                                zip(names, tabs, strict=True)}))
            for col, lev in zip(t.columns, t.levels, strict=True):
                rows.append(dict({"Variable": "", "Modalité": lev},
                                 **{nm: (f"{fmt.num(tb.loc[col, 'est'])}{fmt.stars(tb.loc[col, 'p'])}"
                                         if col in tb.index else "") for nm, tb in zip(names, tabs, strict=True)}))
        else:
            col = t.columns[0]
            rows.append(dict({"Variable": t.label, "Modalité": "(par unité)"},
                             **{nm: (f"{fmt.num(tb.loc[col, 'est'])}{fmt.stars(tb.loc[col, 'p'])}"
                                     if col in tb.index else "") for nm, tb in zip(names, tabs, strict=True)}))
    fit_row = {"Variable": "N", "Modalité": ""}
    fit_row.update({nm: fmt.integer(m.res.nobs) for nm, m in zip(names, models, strict=True)})
    rows.append(fit_row)
    crit = {"Variable": "AIC", "Modalité": ""}
    crit.update({nm: fmt.num(m.res.aic, 1) for nm, m in zip(names, models, strict=True)})
    rows.append(crit)
    return pd.DataFrame(rows)


def _nom(kind: str) -> str:
    n = MODEL_NAMES[kind]
    return n[0].lower() + n[1:]


def _term_text(R: Redac, dsg: Design, col: str) -> str:
    for t in dsg.terms:
        if col in t.columns:
            if t.levels:
                return f"la modalité {guillemets(t.levels[t.columns.index(col)])} {de(R.v(t.variable))}"
            return R.v(t.variable)
    return col


def _diagnostics(kind: str, fit: Fit, dsg: Design, y: np.ndarray, R: Redac):
    res = fit.res
    rows, facts, text = [], {}, []
    k = dsg.X.shape[1]
    v = vif(dsg.X)
    vmax = float(v.replace(np.inf, np.nan).max()) if len(v) else np.nan
    rows.append({"Indicateur": "Observations utilisées", "Valeur": fmt.integer(res.nobs), "Lecture": ""})
    if kind == "lineaire":
        from statsmodels.stats.diagnostic import het_breuschpagan, linear_reset
        ols_plain = sm.OLS(y, sm.add_constant(dsg.X, has_constant="add")).fit()
        bp = het_breuschpagan(ols_plain.resid, ols_plain.model.exog)
        try:
            reset = linear_reset(ols_plain, power=2, use_f=True)
            reset_p = float(reset.pvalue)
        except Exception:  # noqa: BLE001
            reset_p = np.nan
        resid = ols_plain.resid
        _, _, norm_p = ("", 0, stats.shapiro(resid).pvalue) if len(resid) <= 5000 else \
            ("", 0, stats.normaltest(resid).pvalue)
        cook = ols_plain.get_influence().cooks_distance[0]
        facts.update({"modele.r2": res.rsquared, "modele.r2_ajuste": res.rsquared_adj, "modele.f": res.fvalue,
                      "modele.p_f": res.f_pvalue, "modele.bp_p": bp[1], "modele.reset_p": reset_p,
                      "modele.normalite_residus_p": norm_p, "modele.vif_max": vmax,
                      "modele.cook_max": float(np.max(cook))})
        rows += [
            {"Indicateur": "R² / R² ajusté", "Valeur": f"{fmt.num(res.rsquared, 3)} / {fmt.num(res.rsquared_adj, 3)}",
             "Lecture": "part de la variance expliquée"},
            {"Indicateur": "Test F global", "Valeur": f"F = {fmt.num(res.fvalue)} ; {fmt.p_phrase(res.f_pvalue)}",
             "Lecture": "au moins un coefficient non nul" if res.f_pvalue < 0.05 else "modèle non significatif"},
            {"Indicateur": "Breusch-Pagan (hétéroscédasticité)", "Valeur": fmt.p_phrase(bp[1]),
             "Lecture": "hétéroscédasticité : erreurs types robustes indispensables" if bp[1] < 0.05 else
             "pas d'hétéroscédasticité détectée"},
            {"Indicateur": "RESET de Ramsey (spécification)", "Valeur": fmt.p_phrase(reset_p),
             "Lecture": "forme fonctionnelle à revoir (non-linéarités ?)" if reset_p < 0.05 else
             "pas de défaut de spécification détecté"},
            {"Indicateur": "Normalité des résidus", "Valeur": fmt.p_phrase(norm_p),
             "Lecture": "résidus non normaux : inférence fondée sur les erreurs robustes et la taille d'échantillon"
             if norm_p < 0.05 else "normalité non rejetée"},
            {"Indicateur": "Distance de Cook maximale", "Valeur": fmt.num(float(np.max(cook)), 3),
             "Lecture": "observation(s) influente(s) à examiner" if np.max(cook) > 1 else "aucune observation très "
                                                                                        "influente"},
        ]
        glob = ("Il est globalement significatif" if res.f_pvalue < 0.05 else "Il n'est cependant pas globalement "
                "significatif")
        txt = (f"Le modèle explique {fmt.pct(res.rsquared)} de la variance {de(R.y)}, avec un R² ajusté de "
               f"{fmt.num(res.rsquared_adj, 3)}. {glob}, la statistique F valant {fmt.num(res.fvalue)} avec "
               f"{pcrit(res.f_pvalue)}.")
        if bp[1] < 0.05:
            txt += (" Le test de Breusch et Pagan révèle par ailleurs une hétéroscédasticité des résidus, ce qui "
                    "justifie le recours à des erreurs types robustes.")
        text.append(txt)
    elif kind == "logistique":
        llf, lln = res.llf, res.llnull
        lr = 2 * (llf - lln)
        lr_p = float(stats.chi2.sf(lr, k))
        mcf = 1 - llf / lln
        n = res.nobs
        cs = 1 - np.exp(2 * (lln - llf) / n)
        nag = cs / (1 - np.exp(2 * lln / n))
        pr = res.fittedvalues.to_numpy() if hasattr(res.fittedvalues, "to_numpy") else res.fittedvalues
        hl, hl_df, hl_p = hosmer_lemeshow(y, np.asarray(pr))
        from sklearn.metrics import roc_auc_score
        auc = float(roc_auc_score(y, pr))
        events = min(y.sum(), len(y) - y.sum())
        epv = events / max(k, 1)
        facts.update({"modele.lr_chi2": lr, "modele.lr_ddl": k, "modele.lr_p": lr_p, "modele.mcfadden": mcf,
                      "modele.nagelkerke": nag, "modele.hl_chi2": hl, "modele.hl_p": hl_p, "modele.auc": auc,
                      "modele.epv": epv, "modele.vif_max": vmax, "modele.aic": res.aic})
        rows += [
            {"Indicateur": "Rapport de vraisemblance", "Valeur": f"χ²({k}) = {fmt.num(lr)} ; {fmt.p_phrase(lr_p)}",
             "Lecture": "le modèle améliore significativement le modèle nul" if lr_p < 0.05 else
             "le modèle n'améliore pas le modèle nul"},
            {"Indicateur": "Pseudo-R² de McFadden / Nagelkerke",
             "Valeur": f"{fmt.num(mcf, 3)} / {fmt.num(nag, 3)}", "Lecture": "à comparer entre modèles concurrents"},
            {"Indicateur": "Hosmer-Lemeshow", "Valeur": f"χ²({hl_df}) = {fmt.num(hl)} ; {fmt.p_phrase(hl_p)}",
             "Lecture": "ajustement satisfaisant" if hl_p >= 0.05 else "écart entre fréquences observées et prédites"},
            {"Indicateur": "Aire sous la courbe ROC", "Valeur": fmt.num(auc, 3),
             "Lecture": _auc_label(auc)},
            {"Indicateur": "Événements par paramètre", "Valeur": fmt.num(epv, 1),
             "Lecture": "suffisant (≥ 10)" if epv >= 10 else "insuffisant : estimations fragiles"},
        ]
        if lr_p < 0.05:
            txt = (f"Le modèle est globalement significatif : le test du rapport de vraisemblance donne un khi-deux de "
                   f"{fmt.num(lr)} pour {nombre(k, 'degrés')} de liberté, avec {pcrit(lr_p)}.")
        else:
            txt = (f"Le modèle n'est pas globalement significatif : le test du rapport de vraisemblance donne un "
                   f"khi-deux de {fmt.num(lr)} pour {nombre(k, 'degrés')} de liberté, avec {pcrit(lr_p)}.")
        txt += (f" Le pseudo-R² de Nagelkerke s'établit à {fmt.num(nag, 3)} et l'aire sous la courbe ROC à "
                f"{fmt.num(auc, 3)}, ce qui traduit un pouvoir discriminant {_auc_label(auc)}.")
        if hl_p >= 0.05:
            txt += (f" Par ailleurs, le test de Hosmer et Lemeshow ne met pas en évidence de défaut d'ajustement, avec "
                    f"{pcrit(hl_p)}.")
        else:
            txt += (f" Le test de Hosmer et Lemeshow signale toutefois un écart entre les fréquences observées et "
                    f"prédites, avec {pcrit(hl_p)}.")
        text.append(txt)
        if epv < 10:
            text.append(f"Avec {fmt.num(epv, 1)} événements par paramètre estimé, en deçà du repère de dix (10), les "
                        "estimations doivent être interprétées avec prudence.")
    else:  # poisson / binomiale négative
        llf = res.llf
        facts.update({"modele.aic": res.aic, "modele.vif_max": vmax})
        rows.append({"Indicateur": "Log-vraisemblance / AIC", "Valeur": f"{fmt.num(llf, 1)} / {fmt.num(res.aic, 1)}",
                     "Lecture": ""})
        if kind == "binomiale_negative":
            alpha = float(res.params.get("alpha", np.nan))
            facts["modele.alpha_nb"] = alpha
            rows.append({"Indicateur": "Paramètre de dispersion α", "Valeur": fmt.num(alpha, 3),
                         "Lecture": "surdispersion prise en compte"})
    rows.append({"Indicateur": "VIF maximal", "Valeur": fmt.num(vmax),
                 "Lecture": "multicolinéarité forte" if vmax > 10 else "multicolinéarité à surveiller" if vmax > 5
                 else "pas de multicolinéarité préoccupante"})
    if vmax > 5:
        worst = v.idxmax()
        text.append(f"Le facteur d'inflation de la variance atteint {fmt.num(vmax)} pour {_term_text(R, dsg, worst)} : "
                    "les coefficients des variables corrélées entre elles sont donc estimés avec moins de précision.")
    return rows, facts, text


def _auc_label(auc: float) -> str:
    if auc < 0.6:
        return "faible"
    if auc < 0.7:
        return "modeste"
    if auc < 0.8:
        return "acceptable"
    if auc < 0.9:
        return "bon"
    return "excellent"


def _intro_sentence(kind: str, dsg: Design, R: Redac) -> str:
    txt = (f"Pour identifier les facteurs associés {a(R.y)}, nous avons eu recours à une {_nom(kind)}. Le modèle "
           f"porte sur {nombre(dsg.n_used, 'observations', True)} complètes et intègre "
           f"{nombre(len(dsg.terms), 'variables', True)} explicatives.")
    if dsg.event_level:
        if R._evenement:
            txt += f" Il estime les chances {elision('de', R.evenement())} selon les caractéristiques des {R.unite}."
        else:
            txt += f" La modalité modélisée est {guillemets(dsg.event_level)}."
    txt += (" Les résultats présentés sont ajustés : chaque association s'entend toutes choses égales par ailleurs, "
            "c'est-à-dire à niveau identique des autres variables du modèle.")
    return txt


OUVERTURES = ["Toutes choses égales par ailleurs, ", "De même, ", "Par ailleurs, ", "En ce qui concerne {x}, ",
              "Quant {a}, ", "En outre, "]


def _ic(r, digits: int = 2) -> str:
    return f"IC à 95 % : {fmt.ci(r['lo_e'], r['hi_e'], digits)}"


def _effect_sentences(dsg: Design, fit: Fit, kind: str, R: Redac) -> tuple[list[str], list[str]]:
    out, cles, _ = effect_paragraphs(dsg.terms, fit.table(), kind, R, fit.exp_scale)
    return out, cles


def term_text(R: Redac, dsg: Design, col: str) -> str:
    return _term_text(R, dsg, col)


def effect_paragraphs(terms, tab: pd.DataFrame, kind: str, R: Redac, exp_scale: bool,
                      ouvertures: list[str] | None = None,
                      conclure_ns: bool = True) -> tuple[list[str], list[str], list[str]]:
    """Un paragraphe par variable significative, regroupant ses modalités ; phrases de synthèse en second.

    `tab` contient les colonnes est, lo_e, hi_e et p, indexées par les colonnes de la matrice du modèle."""
    ouvertures = ouvertures or OUVERTURES
    out, cles, ns = [], [], []
    k = 0
    eff = EFFECT[kind]
    for t in terms:
        cols = [c for c in t.columns if c in tab.index]
        if not cols:
            continue
        sig = [c for c in cols if tab.loc[c, "p"] < 0.05]
        if not sig:
            ns.append(R.v(t.variable))
            continue
        x = R.v(t.variable)
        modele = ouvertures[k] if k < len(ouvertures) else OUVERTURES[1 + (k - 1) % (len(OUVERTURES) - 1)]
        ouv = modele.format(x=x, a=a(x))
        pron = "{x}" in modele or "{a}" in modele
        k += 1
        if t.levels:
            phr = []
            first = sig[0]
            lev = t.levels[t.columns.index(first)]
            r = tab.loc[first]
            sujet = R.groupe_pron(t.variable, lev) if pron else R.groupe(t.variable, lev)
            ref = R.groupe(t.variable, t.reference, premier=False)
            phr.append(majuscule(ouv + _level_clause(kind, R, sujet, ref, r, eff)))
            best = min(sig, key=lambda c: tab.loc[c, "p"])
            rb = tab.loc[best]
            cles.append((float(rb["p"]), majuscule("Toutes choses égales par ailleurs, " + _level_clause(
                kind, R, R.groupe(t.variable, t.levels[t.columns.index(best)]), ref, rb, eff, court=True))))
            base = 1 if exp_scale else 0
            meme = []
            for c in sig[1:]:
                lev2 = t.levels[t.columns.index(c)]
                r2 = tab.loc[c]
                autre = f"{R.ceux} dont {_pron(x)} {est(x)} {guillemets(lev2)}"
                if kind in ("logistique", "cox") and (r2["est"] >= base) == (r["est"] >= base):
                    meme.append(f"{fmt.num(r2['est'])} pour {autre} ({_ic(r2)} ; {fmt.p_phrase(r2['p'])})")
                else:
                    phr.append(majuscule(_level_clause(kind, R, autre, "", r2, eff, quant=True)))
            if len(meme) == 1:
                phr.insert(1, f"Ce rapport atteint {meme[0]}.")
            elif meme:
                phr.insert(1, "Ce rapport s'établit à " + ", à ".join(meme[:-1]) + f" et à {meme[-1]}.")
            nsig = [c for c in cols if c not in sig]
            if nsig:
                mods = enumeration([guillemets(t.levels[t.columns.index(c)]) for c in nsig])
                phr.append(f"En revanche, la différence avec la modalité de référence n'est pas significative pour "
                           f"{'la modalité' if len(nsig) == 1 else 'les modalités'} {mods}.")
            if t.kind == "ordinale" and len(cols) >= 2 and not nsig:
                vals = [tab.loc[c, "est"] for c in cols]
                if all(v > base for v in vals) and all(np.diff(vals) > 0):
                    phr.append(_monotone(kind, R, x, "augmentent"))
                elif all(v < base for v in vals) and all(np.diff(vals) < 0):
                    phr.append(_monotone(kind, R, x, "diminuent"))
            out.append(" ".join(phr))
        else:
            c = cols[0]
            r = tab.loc[c]
            out.append(majuscule(ouv + _continuous_clause(kind, R, x, r)))
            cles.append((float(r["p"]), "Toutes choses égales par ailleurs, " + _continuous_clause(kind, R, x, r,
                                                                                                     court=True)))
    if ns and conclure_ns:
        if len(ns) == 1:
            out.append(f"En revanche, après ajustement, {ns[0]} n'{est(ns[0])} pas {accord('associé', ns[0])} de "
                       f"manière significative {a(R.y)} au seuil de 5 %.")
        else:
            masc = any(genre(sans_article(v)) == "m" for v in ns)
            out.append(f"En revanche, après ajustement, ni {', ni '.join(ns)} ne sont "
                       f"{'associés' if masc else 'associées'} de manière significative {a(R.y)} au seuil de 5 %.")
    cles.sort(key=lambda t: t[0])
    return out, [c for _, c in cles[:4]], ns


def _pron(groupe: str) -> str:
    from ..writing.phrases import pronom
    return pronom(groupe)


def _level_clause(kind: str, R: Redac, sujet: str, ref: str, r, eff: str, court: bool = False,
                  quant: bool = False) -> str:
    """Proposition décrivant l'effet d'une modalité par rapport à la référence."""
    est_txt = f" ({eff} = {fmt.num(r['est'])} ; {_ic(r)} ; {fmt.p_phrase(r['p'])})" if not court else ""
    que = f" que {ref}" if ref else ""
    if kind == "logistique":
        verbe = "ont" if sujet.startswith(("les ", "celles", "ceux")) else "a"
        if quant:
            verbe = f"{verbe} quant à {'elles' if R.fem else 'eux'}"
        return f"{sujet} {verbe} {R.chances(r['est'])} {elision('de', R.evenement())}{que}{est_txt}."
    if kind == "cox":
        verbe = "ont" if sujet.startswith(("les ", "celles", "ceux")) else "a"
        if quant:
            verbe = f"{verbe} quant à {'elles' if R.fem else 'eux'}"
        risque = f"un risque instantané {elision('de', R.evenement())}"
        if r["est"] >= 1:
            return f"{sujet} {verbe} {risque} {fmt.num(r['est'])} fois plus élevé{que}{est_txt}."
        return (f"{sujet} {verbe} {risque} inférieur de {fmt.num(100 * (1 - r['est']), 0)} %"
                f"{(' à celui de ' + ref) if ref else ''}{est_txt}.")
    if kind == "lineaire":
        sens = accord("supérieur" if r["est"] > 0 else "inférieur", R.y)
        ref_txt = f" par rapport à {ref}" if ref else ""
        return (f"{R.y} est en moyenne {sens} de {fmt.num(abs(r['est']))} chez {sujet}{ref_txt}{est_txt}.")
    # comptage : rapport de taux
    if r["est"] >= 1:
        return (f"{R.y} est en moyenne {fmt.num(r['est'])} fois plus {accord('élevé', R.y)} chez {sujet}"
                f"{(' que chez ' + ref) if ref else ''}{est_txt}.")
    return (f"{R.y} est en moyenne inférieur{'e' if genre(sans_article(R.y)) == 'f' else ''} de "
            f"{fmt.num(100 * (1 - r['est']), 0)} % chez {sujet}{(' par rapport à ' + ref) if ref else ''}{est_txt}.")


def _continuous_clause(kind: str, R: Redac, x: str, r, court: bool = False) -> str:
    unite = f"une augmentation d'une unité {de(x)}"
    est_txt = "" if court else f" ({_ic(r, 3)} ; {fmt.p_phrase(r['p'])})"
    if kind == "logistique":
        if r["est"] >= 1:
            return (f"{unite} multiplie les chances {elision('de', R.evenement())} par {fmt.num(r['est'], 3)}"
                    f"{est_txt}.")
        return (f"{unite} réduit les chances {elision('de', R.evenement())} de {fmt.num(100 * (1 - r['est']), 1)} %"
                f"{est_txt}.")
    if kind == "cox":
        risque = f"le risque instantané {elision('de', R.evenement())}"
        if r["est"] >= 1:
            return f"{unite} multiplie {risque} par {fmt.num(r['est'], 3)}{est_txt}."
        return f"{unite} réduit {risque} de {fmt.num(100 * (1 - r['est']), 1)} %{est_txt}."
    if kind == "lineaire":
        sens = "hausse" if r["est"] > 0 else "baisse"
        return f"{unite} s'accompagne d'une {sens} moyenne de {fmt.num(abs(r['est']), 3)} {de(R.y)}{est_txt}."
    return f"{unite} multiplie la valeur attendue {de(R.y)} par {fmt.num(r['est'], 3)}{est_txt}."


def _monotone(kind: str, R: Redac, x: str, sens: str) -> str:
    if kind == "cox":
        return (f"Nous pouvons donc dire que le risque {elision('de', R.evenement())} "
                f"{'augmente' if sens == 'augmentent' else 'diminue'} avec {x}.")
    if kind == "logistique":
        return f"Nous pouvons donc dire que les chances {elision('de', R.evenement())} {sens} avec {x}."
    return f"Nous pouvons donc dire que {R.y} {'augmente' if sens == 'augmentent' else 'diminue'} avec {x}."


def _crude_vs_adjusted(dsg: Design, crude: dict, fit: Fit, R: Redac) -> list[str]:
    adj = fit.table()
    lost, gained = [], []
    for t in dsg.terms:
        c_sig = any(crude.get(c, {}).get("p", 1) < 0.05 for c in t.columns)
        a_sig = any(c in adj.index and adj.loc[c, "p"] < 0.05 for c in t.columns)
        if c_sig and not a_sig:
            lost.append(R.v(t.variable))
        elif a_sig and not c_sig:
            gained.append(R.v(t.variable))
    out = []
    if len(lost) == 1:
        out.append(f"Il convient de noter que l'association brute observée pour {lost[0]} n'est plus significative "
                   "après ajustement. Elle reflétait vraisemblablement, au moins en partie, des différences de "
                   "composition selon les autres variables du modèle (effet de structure ou de confusion).")
    elif lost:
        out.append(f"Il convient de noter que les associations brutes observées pour {enumeration(lost)} ne sont plus "
                   "significatives après ajustement. Elles reflétaient vraisemblablement, au moins en partie, des "
                   "différences de composition selon les autres variables du modèle (effet de structure ou de "
                   "confusion).")
    if len(gained) == 1:
        g = gained[0]
        out.append(f"À l'inverse, {g} ne devient {accord('significatif', g).replace('significatife', 'significative')} "
                   f"qu'après ajustement : son association {a(R.y)} était masquée par d'autres facteurs (effet de "
                   "suppression).")
    elif gained:
        out.append(f"À l'inverse, {enumeration(gained)} ne deviennent significatives qu'après ajustement : leur "
                   f"association {a(R.y)} était masquée par d'autres facteurs (effet de suppression).")
    return out


def _model_refs(kind: str) -> set[str]:
    return {
        "lineaire": {"mackinnon1985", "breusch1979", "ramsey1969", "seabold2010"},
        "logistique": {"hosmer2013", "mcfadden1974", "nagelkerke1991", "kleinbaum2010", "seabold2010"},
        "poisson": {"cameron1990", "seabold2010"},
        "binomiale_negative": {"cameron1990", "seabold2010"},
    }.get(kind, {"seabold2010"})


def _method_note(kind: str, clustered: bool, dsg: Design) -> str:
    base = {
        "lineaire": "La variable dépendante quantitative est modélisée par régression linéaire estimée par les moindres "
                    "carrés ordinaires, avec des erreurs types robustes à l'hétéroscédasticité de type HC3 (MacKinnon "
                    "et White, 1985). L'hétéroscédasticité est examinée par le test de Breusch et Pagan (1979) et la "
                    "spécification par le test RESET de Ramsey (1969).",
        "logistique": "La variable dépendante dichotomique est modélisée par régression logistique (Hosmer, Lemeshow "
                      "et Sturdivant, 2013) estimée par le maximum de vraisemblance. Les coefficients sont présentés "
                      "sous forme de rapports de cotes (OR). L'ajustement est apprécié par le test du rapport de "
                      "vraisemblance, les pseudo-R² de McFadden (1974) et de Nagelkerke (1991), le test de Hosmer et "
                      "Lemeshow et l'aire sous la courbe ROC.",
        "poisson": "La variable de comptage est modélisée par une régression de Poisson ; la surdispersion est testée "
                   "selon Cameron et Trivedi (1990).",
        "binomiale_negative": "La variable de comptage, surdispersée selon le test de Cameron et Trivedi (1990), est "
                              "modélisée par une régression binomiale négative (NB2).",
    }[kind]
    if kind == "logistique":
        base += (" Pour la lecture des résultats, nous suivons l'usage courant en démographie : un rapport de cotes "
                 "supérieur à 1 est lu comme un nombre de fois plus de chances, et un rapport inférieur à 1 comme un "
                 "pourcentage de chances en moins, égal à (1 - OR) × 100. Il s'agit de rapports de cotes et non de "
                 "rapports de probabilités, les deux étant proches lorsque l'événement est peu fréquent.")
    base += (" Chaque variable est d'abord introduite seule (association brute), puis l'ensemble est estimé "
             "conjointement (association ajustée). La multicolinéarité est contrôlée par le facteur d'inflation de la "
             "variance (VIF). Les modalités de référence sont les modalités les plus fréquentes, ou la première "
             "modalité pour les variables ordinales, sauf choix contraire de l'auteur. L'analyse porte sur les cas "
             f"complets, soit {fmt.integer(dsg.n_used)} observations sur {fmt.integer(dsg.n_total)}.")
    if clustered:
        base += (" Les erreurs types sont robustes à la corrélation intra-grappe, les observations d'une même grappe "
                 "n'étant pas indépendantes.")
    return base


# ---------------------------------------------------------------------------
# Multinomiale et ordonnée
# ---------------------------------------------------------------------------

def _explain_multinomial(ds: Dataset, dsg: Design, sec: Section, outdir: Path, R: Redac) -> Section:
    cats = dsg.y_categories
    counts = dsg.y.value_counts()
    ref = str(counts.idxmax())
    order = [ref] + [c for c in cats if c != ref]
    codes = pd.Categorical(dsg.y.astype(str), categories=order).codes
    X1 = sm.add_constant(dsg.X, has_constant="add")
    res = sm.MNLogit(codes, X1).fit(disp=0, maxiter=500, method="bfgs")
    params, pv = res.params, res.pvalues
    se = res.bse
    rows, phrases = [], []
    for t in dsg.terms:
        if t.levels:
            rows.append(dict({"Variable": t.label, "Modalité": ""}, **{f"{c} vs {ref}": "" for c in order[1:]}))
            rows.append(dict({"Variable": "", "Modalité": f"{t.reference} (Réf.)"}, **{f"{c} vs {ref}": "1" for c in
                                                                                     order[1:]}))
            for col, lev in zip(t.columns, t.levels, strict=True):
                row = {"Variable": "", "Modalité": lev}
                for j, c in enumerate(order[1:]):
                    b, s, p = params.loc[col, j], se.loc[col, j], pv.loc[col, j]
                    row[f"{c} vs {ref}"] = (f"{fmt.num(np.exp(b))} {fmt.ci(np.exp(b - 1.96 * s), np.exp(b + 1.96 * s))}"
                                            f"{fmt.stars(p)}")
                    sec.facts[f"mnl.{col}.{c}.rrr"] = float(np.exp(b))
                    sec.facts[f"mnl.{col}.{c}.p"] = float(p)
                    if p < 0.05 and len(phrases) < 8:
                        phrases.append(
                            f"{R.groupe(t.variable, lev)} ont {R.chances(float(np.exp(b)))} d'être dans la modalité "
                            f"{guillemets(c)} plutôt que dans la modalité {guillemets(ref)} que "
                            f"{R.groupe(t.variable, t.reference, premier=False)} (RRR = {fmt.num(np.exp(b))} ; "
                            f"{fmt.p_phrase(p)}).")
                rows.append(row)
        else:
            col = t.columns[0]
            row = {"Variable": t.label, "Modalité": "(par unité)"}
            for j, c in enumerate(order[1:]):
                b, s, p = params.loc[col, j], se.loc[col, j], pv.loc[col, j]
                row[f"{c} vs {ref}"] = f"{fmt.num(np.exp(b), 3)} {fmt.ci(np.exp(b - 1.96 * s), np.exp(b + 1.96 * s), 3)}" \
                                       f"{fmt.stars(p)}"
                sec.facts[f"mnl.{col}.{c}.rrr"] = float(np.exp(b))
            rows.append(row)
    sec.tables.append(Table(title=f"Facteurs associés {a(R.y)} : résultats de la régression logistique multinomiale "
                                  f"(référence : {guillemets(ref)})",
                            data=pd.DataFrame(rows),
                            note="RRR : rapport de risques relatifs [IC à 95 %], par rapport à la modalité de "
                                 "référence de la variable dépendante. " + fmt.STARS_NOTE))
    lr = 2 * (res.llf - res.llnull)
    dfm = res.df_model
    lr_p = float(stats.chi2.sf(lr, dfm))
    sec.facts.update({"modele.lr_chi2": lr, "modele.lr_p": lr_p, "modele.mcfadden": res.prsquared})
    sec.paragraphs.append(
        f"La variable dépendante comptant plus de deux modalités non ordonnées, nous avons eu recours à une régression "
        f"logistique multinomiale. Le modèle compare chaque modalité {de(R.y)} à la modalité la plus fréquente, "
        f"{guillemets(ref)}, et porte sur {nombre(dsg.n_used, 'observations', True)} complètes. Il "
        + ("améliore significativement" if lr_p < 0.05 else "n'améliore pas significativement")
        + f" le modèle sans variable explicative, avec un khi-deux de {fmt.num(lr)} pour "
        f"{nombre(int(dfm), 'degrés')} de liberté et {pcrit(lr_p)} ; le pseudo-R² de McFadden s'établit à "
        f"{fmt.num(res.prsquared, 3)}. Il convient de rappeler que ce modèle suppose l'indépendance des alternatives "
        "non pertinentes : le rapport de risques entre deux modalités ne dépend pas des autres modalités.")
    for i, ph in enumerate(phrases):
        sec.paragraphs.append(majuscule(("Toutes choses égales par ailleurs, " if i == 0 else
                                         ["Par ailleurs, ", "De même, ", "En outre, "][(i - 1) % 3]) + ph))
    sec.refs |= {"agresti2013", "mcfadden1974", "seabold2010"}
    sec.method_notes.append(
        "La variable dépendante nominale à plus de deux modalités est modélisée par régression logistique multinomiale ; "
        "les coefficients sont exprimés en rapports de risques relatifs (RRR) par rapport à la modalité de référence.")
    return sec


def _explain_ordinal(ds: Dataset, dsg: Design, sec: Section, outdir: Path, R: Redac) -> Section:
    from statsmodels.miscmodels.ordinal_model import OrderedModel
    codes = dsg.y.cat.codes.to_numpy()
    mod = OrderedModel(codes, dsg.X.astype(float), distr="logit")
    res = mod.fit(method="bfgs", disp=0, maxiter=1000)
    ci = res.conf_int()
    rows, phrases = [], []
    for t in dsg.terms:
        if t.levels:
            rows.append({"Variable": t.label, "Modalité": "", "OR": "", "IC 95 %": "", "p": ""})
            rows.append({"Variable": "", "Modalité": f"{t.reference} (Réf.)", "OR": "1", "IC 95 %": "-", "p": "-"})
            names = list(zip(t.columns, t.levels, strict=True))
        else:
            names = [(t.columns[0], "(par unité)")]
        for col, lev in names:
            b = res.params[col]
            rows.append({"Variable": "" if t.levels else t.label, "Modalité": lev, "OR": fmt.num(np.exp(b)),
                         "IC 95 %": fmt.ci(np.exp(ci.loc[col, 0]), np.exp(ci.loc[col, 1])),
                         "p": fmt.pval(res.pvalues[col])})
            sec.facts[f"ord.{col}.or"] = float(np.exp(b))
            sec.facts[f"ord.{col}.p"] = float(res.pvalues[col])
            if res.pvalues[col] < 0.05:
                ic = f"IC à 95 % : {fmt.ci(np.exp(ci.loc[col, 0]), np.exp(ci.loc[col, 1]))}"
                orv = float(np.exp(b))
                if t.levels:
                    phrases.append(
                        f"{R.groupe(t.variable, lev)} ont {R.chances(orv)} de se situer dans les modalités supérieures "
                        f"{de(R.y)} que {R.groupe(t.variable, t.reference, premier=False)} (OR = {fmt.num(orv)} ; "
                        f"{ic} ; {fmt.p_phrase(res.pvalues[col])}).")
                else:
                    verbe = (f"multiplie par {fmt.num(orv, 3)}" if orv >= 1 else
                             f"réduit de {fmt.num(100 * (1 - orv), 1)} %")
                    phrases.append(
                        f"une augmentation d'une unité {de(R.v(t.variable))} {verbe} les chances de se situer dans les "
                        f"modalités supérieures {de(R.y)} ({ic} ; {fmt.p_phrase(res.pvalues[col])}).")
    sec.paragraphs.append(
        f"La variable dépendante étant ordinale, nous avons eu recours à une régression logistique ordonnée à cotes "
        f"proportionnelles. Le modèle porte sur {nombre(dsg.n_used, 'observations', True)} complètes, et les "
        "résultats présentés s'entendent toutes choses égales par ailleurs.")
    for i, ph in enumerate(phrases):
        sec.paragraphs.append(majuscule(("Toutes choses égales par ailleurs, " if i == 0 else
                                         ["Par ailleurs, ", "De même, ", "En outre, "][(i - 1) % 3]) + ph))
    sec.tables.append(Table(title=f"Facteurs associés {a(R.y)} : résultats de la régression logistique ordonnée",
                            data=pd.DataFrame(rows),
                            note="OR : rapport de cotes cumulées ; un OR supérieur à 1 indique une propension plus "
                                 "élevée à se situer dans les modalités supérieures de la variable dépendante."))
    try:
        w, dof, p_b = brant_test(codes, dsg.X)
    except Exception:  # noqa: BLE001
        w, dof, p_b = np.nan, 0, np.nan
    sec.facts.update({"modele.brant_chi2": w, "modele.brant_p": p_b})
    if not np.isnan(p_b):
        sec.paragraphs.insert(1,
            "Le test de Brant (1990) "
            + ("ne rejette pas" if p_b >= 0.05 else "rejette")
            + f" l'hypothèse des cotes proportionnelles, avec un khi-deux de {fmt.num(w)} pour "
            f"{nombre(int(dof), 'degrés')} de liberté et {pcrit(p_b)}"
            + (". Le modèle ordonné est donc adapté." if p_b >= 0.05 else
               ". L'effet de certaines variables varie donc selon le seuil considéré : un modèle multinomial ou à "
               "cotes partiellement proportionnelles serait plus approprié, et les résultats sont à lire comme des "
               "effets moyens."))
    sec.refs |= {"mccullagh1980", "brant1990", "agresti2013", "seabold2010"}
    sec.method_notes.append(
        "La variable dépendante ordinale est modélisée par une régression logistique ordonnée à cotes proportionnelles "
        "(McCullagh, 1980) ; l'hypothèse de proportionnalité est testée par le test de Brant (1990).")
    return sec
