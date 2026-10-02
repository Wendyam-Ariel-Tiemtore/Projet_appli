"""Analyse bivariée : choix automatique du test selon le niveau de mesure et les conditions d'application."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

from ..writing.phrases import Redac, accord, est, pcrit, pronom
from ..writing.style import a as a_
from ..writing.style import de, enumeration, genre, guillemets, majuscule, nombre, sans_article
from . import figures, fmt
from .io import Dataset, as_categorical
from .results import Figure, Section, Table

CAT_KINDS = ("binaire", "nominale", "ordinale")
NUM_KINDS = ("continue", "comptage")
RNG_SEED = 42


# ---------------------------------------------------------------------------
# Qualificatifs d'intensité (repères de la synthèse des coefficients, ISSP ; Cohen, 1988)
# ---------------------------------------------------------------------------

def strength_cramer(v: float) -> str:
    v = abs(v)
    for thr, lab in ((0.05, "absente"), (0.10, "très faible"), (0.20, "faible"), (0.40, "modérée"),
                     (0.80, "forte")):
        if v < thr:
            return lab
    return "très forte"


strength_somers = strength_cramer


def strength_r(r: float) -> str:
    r = abs(r)
    if r == 0:
        return "absente"
    for thr, lab in ((0.20, "très faible"), (0.40, "faible"), (0.60, "modérée"), (0.90, "forte")):
        if r < thr:
            return lab
    return "très forte"


def strength_d(d: float) -> str:
    d = abs(d)
    return "négligeable" if d < 0.2 else "faible" if d < 0.5 else "moyenne" if d < 0.8 else "forte"


def strength_eta(e: float) -> str:
    return "négligeable" if e < 0.01 else "faible" if e < 0.06 else "moyenne" if e < 0.14 else "forte"


def strength_rb(r: float) -> str:
    r = abs(r)
    return "négligeable" if r < 0.1 else "faible" if r < 0.3 else "moyenne" if r < 0.5 else "forte"


# ---------------------------------------------------------------------------
# Tests élémentaires
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    x: str
    test: str
    stat_label: str
    stat: float
    df: float | None
    p: float
    effect_label: str
    effect: float
    effect_ci: tuple[float, float] | None
    strength: str
    n: int
    reliability: str = "bonne"
    details: dict = field(default_factory=dict)
    posthoc: pd.DataFrame | None = None
    p_fdr: float = np.nan
    refs: set[str] = field(default_factory=set)
    justification: str = ""


def _monte_carlo_chi2(x_codes: np.ndarray, y_codes: np.ndarray, observed: float, b: int) -> float:
    rng = np.random.default_rng(RNG_SEED)
    kx, ky = x_codes.max() + 1, y_codes.max() + 1
    count = 0
    n = len(x_codes)
    row = np.bincount(x_codes, minlength=kx)
    col = np.bincount(y_codes, minlength=ky)
    expected = np.outer(row, col) / n
    for _ in range(b):
        perm = rng.permutation(y_codes)
        tab = np.zeros((kx, ky))
        np.add.at(tab, (x_codes, perm), 1)
        with np.errstate(divide="ignore", invalid="ignore"):
            chi = np.nansum((tab - expected) ** 2 / expected)
        if chi >= observed - 1e-12:
            count += 1
    return (count + 1) / (b + 1)


def cat_cat(x: pd.Series, y: pd.Series, x_ordinal: bool, y_ordinal: bool) -> TestResult:
    d = pd.DataFrame({"x": x, "y": y}).dropna()
    d["x"] = d["x"].cat.remove_unused_categories()
    d["y"] = d["y"].cat.remove_unused_categories()
    ct = pd.crosstab(d["x"], d["y"])
    n = int(ct.to_numpy().sum())
    r, c = ct.shape
    if r < 2 or c < 2:
        return TestResult(x.name, "non calculable", "", np.nan, None, np.nan, "", np.nan, None, "", n,
                          reliability="une seule modalité observée")
    chi2, p_chi, dof, expected = stats.chi2_contingency(ct, correction=False)
    share_low = float((expected < 5).mean())
    min_exp = float(expected.min())
    v = float(np.sqrt(chi2 / (n * (min(r, c) - 1))))
    refs = {"cramer1946", "cochran1954"}
    res = TestResult(x.name, "Khi-deux de Pearson", "χ²", float(chi2), float(dof), float(p_chi), "V de Cramér", v,
                     None, strength_cramer(v), n, refs=refs,
                     justification="effectifs attendus conformes à la règle de Cochran")
    res.details = {"part_attendus_inf5": share_low, "attendu_min": min_exp}

    if r == 2 and c == 2:
        table = ct.to_numpy()
        orr, p_f = stats.fisher_exact(table)
        lo, hi = _or_ci(table)
        res.details.update({"or": orr, "or_lo": lo, "or_hi": hi})
        if min_exp < 5:
            res.test, res.stat_label, res.stat, res.df, res.p = "Exact de Fisher", "", np.nan, None, float(p_f)
            res.justification = "tableau 2 × 2 avec un effectif attendu inférieur à 5"
            res.refs |= {"fisher1922"}
    elif share_low > 0.2 or min_exp < 1:
        b = int(min(10000, max(1000, 2e7 / max(n, 1))))
        xc = d["x"].cat.codes.to_numpy()
        yc = d["y"].cat.codes.to_numpy()
        res.p = _monte_carlo_chi2(xc, yc, chi2, b)
        res.test = "Khi-deux (p par Monte-Carlo)"
        res.reliability = "faible (cellules creuses)"
        res.justification = (f"{fmt.pct(share_low, 0)} des effectifs attendus sont inférieurs à 5 : probabilité "
                             f"critique estimée par {fmt.integer(b)} permutations")
        res.details["mc_tirages"] = b

    if x_ordinal and y_ordinal:
        sd = stats.somersd(d["x"].cat.codes.to_numpy(), d["y"].cat.codes.to_numpy())
        res.effect_label, res.effect = "d de Somers", float(sd.statistic)
        res.strength = strength_somers(sd.statistic)
        res.p = float(sd.pvalue)
        res.test = "d de Somers (tendance ordinale)"
        res.stat_label, res.stat, res.df = "", np.nan, None
        res.justification = "deux variables ordinales : test de la tendance et mesure orientée"
        res.details["p_khi2"] = float(p_chi)
        res.refs |= {"somers1962"}
    res.details["crosstab"] = ct
    return res


def _or_ci(t: np.ndarray) -> tuple[float, float]:
    a, b, c, d = (t + 0.5).ravel() if (t == 0).any() else t.ravel()
    lor = np.log((a * d) / (b * c))
    se = np.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    return float(np.exp(lor - 1.96 * se)), float(np.exp(lor + 1.96 * se))


def _group_ok(v: np.ndarray) -> bool:
    if len(v) < 3:
        return False
    sk = stats.skew(v) if np.ptp(v) > 0 else 0
    if len(v) >= 30:
        return abs(sk) <= 1
    if np.ptp(v) == 0:
        return False
    return stats.shapiro(v).pvalue >= 0.05


def welch_anova(groups: list[np.ndarray]) -> tuple[float, float, float, float]:
    k = len(groups)
    n = np.array([len(g) for g in groups], dtype=float)
    m = np.array([g.mean() for g in groups])
    v = np.array([g.var(ddof=1) for g in groups])
    w = n / v
    mw = (w * m).sum() / w.sum()
    a = (w * (m - mw) ** 2).sum() / (k - 1)
    tmp = ((1 - w / w.sum()) ** 2 / (n - 1)).sum()
    b = 1 + 2 * (k - 2) / (k ** 2 - 1) * tmp
    f = a / b
    df1, df2 = k - 1, (k ** 2 - 1) / (3 * tmp)
    p = stats.f.sf(f, df1, df2)
    return float(f), float(df1), float(df2), float(p)


def games_howell(groups: dict[str, np.ndarray]) -> pd.DataFrame:
    rows = []
    keys = list(groups)
    k = len(keys)
    for a, b in combinations(keys, 2):
        ga, gb = groups[a], groups[b]
        na, nb = len(ga), len(gb)
        va, vb = ga.var(ddof=1), gb.var(ddof=1)
        diff = ga.mean() - gb.mean()
        se = np.sqrt(va / na + vb / nb)
        dfw = (va / na + vb / nb) ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
        q = abs(diff) / se * np.sqrt(2)
        p = float(stats.studentized_range.sf(q, k, dfw))
        rows.append({"Comparaison": f"{a} / {b}", "Différence": diff, "p ajustée": min(p, 1.0)})
    return pd.DataFrame(rows)


def dunn_holm(groups: dict[str, np.ndarray]) -> pd.DataFrame:
    keys = list(groups)
    allv = np.concatenate([groups[k] for k in keys])
    ranks = stats.rankdata(allv)
    n = len(allv)
    idx, mean_rank = 0, {}
    sizes = {}
    for k in keys:
        nk = len(groups[k])
        mean_rank[k] = ranks[idx: idx + nk].mean()
        sizes[k] = nk
        idx += nk
    _, counts = np.unique(allv, return_counts=True)
    tie = (counts ** 3 - counts).sum() / (12 * (n - 1))
    rows, ps = [], []
    for a, b in combinations(keys, 2):
        se = np.sqrt((n * (n + 1) / 12 - tie) * (1 / sizes[a] + 1 / sizes[b]))
        z = (mean_rank[a] - mean_rank[b]) / se
        p = 2 * stats.norm.sf(abs(z))
        rows.append({"Comparaison": f"{a} / {b}", "Différence": mean_rank[a] - mean_rank[b]})
        ps.append(p)
    adj = multipletests(ps, method="holm")[1] if ps else []
    out = pd.DataFrame(rows)
    out["p ajustée"] = adj
    return out


def tukey_kramer(groups: dict[str, np.ndarray]) -> pd.DataFrame:
    from statsmodels.stats.multicomp import pairwise_tukeyhsd
    vals = np.concatenate(list(groups.values()))
    labs = np.concatenate([[k] * len(v) for k, v in groups.items()])
    res = pairwise_tukeyhsd(vals, labs)
    tab = pd.DataFrame(res.summary().data[1:], columns=res.summary().data[0])
    return pd.DataFrame({"Comparaison": tab["group1"].astype(str) + " / " + tab["group2"].astype(str),
                         "Différence": tab["meandiff"].astype(float), "p ajustée": tab["p-adj"].astype(float)})


def num_by_group(values: pd.Series, groups: pd.Series, var_name: str) -> TestResult:
    d = pd.DataFrame({"v": pd.to_numeric(values, errors="coerce"), "g": groups}).dropna()
    d["g"] = d["g"].cat.remove_unused_categories()
    gdict = {str(k): grp["v"].to_numpy(dtype=float) for k, grp in d.groupby("g", observed=True)}
    gdict = {k: v for k, v in gdict.items() if len(v) > 0}
    n = int(len(d))
    k = len(gdict)
    if k < 2:
        return TestResult(var_name, "non calculable", "", np.nan, None, np.nan, "", np.nan, None, "", n,
                          reliability="un seul groupe observé")
    ok = all(_group_ok(v) for v in gdict.values())
    arrays = list(gdict.values())
    desc = {kk: {"n": len(v), "moyenne": float(v.mean()), "ecart_type": float(v.std(ddof=1)) if len(v) > 1 else np.nan,
                 "mediane": float(np.median(v)), "q1": float(np.percentile(v, 25)),
                 "q3": float(np.percentile(v, 75))} for kk, v in gdict.items()}
    if k == 2:
        a, b = arrays
        if ok:
            r = stats.ttest_ind(a, b, equal_var=False)
            sp = np.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / (len(a) + len(b) - 2))
            dval = (a.mean() - b.mean()) / sp if sp > 0 else np.nan
            se = np.sqrt((len(a) + len(b)) / (len(a) * len(b)) + dval ** 2 / (2 * (len(a) + len(b))))
            res = TestResult(var_name, "t de Welch", "t", float(r.statistic), float(r.df), float(r.pvalue),
                             "d de Cohen", float(dval), (dval - 1.96 * se, dval + 1.96 * se), strength_d(dval), n,
                             refs={"welch1947", "cohen1988"},
                             justification="distributions compatibles avec la normalité (ou effectifs ≥ 30 sans "
                                           "asymétrie marquée) ; variances non supposées égales")
        else:
            r = stats.mannwhitneyu(a, b, alternative="two-sided")
            rb = 1 - 2 * r.statistic / (len(a) * len(b))
            res = TestResult(var_name, "U de Mann-Whitney", "U", float(r.statistic), None, float(r.pvalue),
                             "Corrélation bisériale de rang", float(-rb), None, strength_rb(rb), n,
                             refs={"mann1947"},
                             justification="normalité non vérifiée dans au moins un groupe de petit effectif ou "
                                           "asymétrie marquée")
    else:
        lev = stats.levene(*arrays, center="median")
        if ok and lev.pvalue >= 0.05:
            f, p = stats.f_oneway(*arrays)
            allv = np.concatenate(arrays)
            ssb = sum(len(g) * (g.mean() - allv.mean()) ** 2 for g in arrays)
            sst = ((allv - allv.mean()) ** 2).sum()
            ssw = sst - ssb
            msw = ssw / (len(allv) - k)
            eta2 = ssb / sst if sst > 0 else np.nan
            omega2 = (ssb - (k - 1) * msw) / (sst + msw) if sst > 0 else np.nan
            res = TestResult(var_name, "ANOVA à un facteur", "F", float(f), float(k - 1), float(p), "ω²",
                             float(max(omega2, 0)), None, strength_eta(max(omega2, 0)), n,
                             refs={"levene1960", "kramer1956"},
                             justification="normalité et homogénéité des variances (Levene) vérifiées")
            res.details["eta2"] = float(eta2)
            res.details["df2"] = float(len(allv) - k)
            if p < 0.05:
                res.posthoc = tukey_kramer(gdict)
                res.details["posthoc_nom"] = "Tukey-Kramer"
        elif ok:
            f, df1, df2, p = welch_anova(arrays)
            allv = np.concatenate(arrays)
            omega2 = (df1 * (f - 1)) / (df1 * (f - 1) + len(allv))
            res = TestResult(var_name, "ANOVA de Welch", "F", f, df1, p, "ω²", float(max(omega2, 0)), None,
                             strength_eta(max(omega2, 0)), n, refs={"levene1960", "welch1947", "games1976"},
                             justification="normalité vérifiée mais variances hétérogènes (Levene)")
            res.details["df2"] = df2
            if p < 0.05:
                res.posthoc = games_howell(gdict)
                res.details["posthoc_nom"] = "Games-Howell"
        else:
            h, p = stats.kruskal(*arrays)
            eps2 = h / ((n ** 2 - 1) / (n + 1))
            res = TestResult(var_name, "Kruskal-Wallis", "H", float(h), float(k - 1), float(p), "ε²", float(eps2),
                             None, strength_eta(eps2), n, refs={"kruskal1952", "dunn1964", "holm1979",
                                                                "tomczak2014"},
                             justification="normalité non vérifiée dans au moins un groupe")
            if p < 0.05:
                res.posthoc = dunn_holm(gdict)
                res.details["posthoc_nom"] = "Dunn (ajustement de Holm)"
        res.details["levene_p"] = float(lev.pvalue)
    res.details["groupes"] = desc
    res.details["parametrique"] = ok
    return res


def num_num(x: pd.Series, y: pd.Series) -> TestResult:
    d = pd.DataFrame({"x": pd.to_numeric(x, errors="coerce"), "y": pd.to_numeric(y, errors="coerce")}).dropna()
    n = len(d)
    if n < 4 or d["x"].std() == 0 or d["y"].std() == 0:
        return TestResult(x.name, "non calculable", "", np.nan, None, np.nan, "", np.nan, None, "", n,
                          reliability="effectif ou variance insuffisants")
    pr = stats.pearsonr(d["x"], d["y"])
    sr = stats.spearmanr(d["x"], d["y"])
    ok = _group_ok(d["x"].to_numpy()) and _group_ok(d["y"].to_numpy())
    if ok:
        r, p, name = float(pr.statistic), float(pr.pvalue), "r de Pearson"
        just = "distributions compatibles avec la normalité"
    else:
        r, p, name = float(sr.statistic), float(sr.pvalue), "ρ de Spearman"
        just = "normalité non vérifiée ou asymétrie marquée : corrélation de rang"
    z = np.arctanh(np.clip(r, -0.999999, 0.999999))
    se = 1 / np.sqrt(n - 3) if n > 3 else np.nan
    ci = (float(np.tanh(z - 1.96 * se)), float(np.tanh(z + 1.96 * se)))
    res = TestResult(x.name, name, name.split(" ")[0], r, float(n - 2), p, name, r, ci, strength_r(r), n,
                     refs={"spearman1904"} if not ok else set(), justification=just)
    res.details = {"pearson": float(pr.statistic), "p_pearson": float(pr.pvalue), "spearman": float(sr.statistic),
                   "p_spearman": float(sr.pvalue)}
    return res


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def bivariate(ds: Dataset, outcome: str, explanatory: list[str], outdir: Path, max_figures: int = 6) -> Section:
    sec = Section(key="bivarie", title="Analyse bivariée : facteurs associés", level=2)
    yinfo = ds.variables[outcome]
    ylab = yinfo.label
    df = ds.df
    results: list[TestResult] = []
    y_cat = yinfo.kind in CAT_KINDS
    ys = as_categorical(df[outcome], yinfo) if y_cat else pd.to_numeric(df[outcome], errors="coerce")
    from .design import event_level_for as _evl
    R = Redac(ds, outcome, _evl([str(c) for c in ys.cat.categories]) if yinfo.kind == "binaire" else None)

    for col in explanatory:
        if col == outcome:
            continue
        info = ds.variables[col]
        if info.kind in CAT_KINDS:
            xs = as_categorical(df[col], info).rename(col)
            if y_cat:
                # d de Somers : deux ordinales, ou une ordinale et une dichotomique ordonnable (synthèse ISSP)
                x_ord = info.kind == "ordinale" or (info.kind == "binaire" and yinfo.kind == "ordinale")
                y_ord = yinfo.kind == "ordinale" or (yinfo.kind == "binaire" and info.kind == "ordinale")
                r = cat_cat(xs, ys, x_ord, y_ord)
            else:
                r = num_by_group(ys, xs, col)
        elif info.kind in NUM_KINDS:
            xs = pd.to_numeric(df[col], errors="coerce").rename(col)
            r = num_by_group(xs, ys, col) if y_cat else num_num(xs, ys)
        else:
            continue
        r.x = col
        results.append(r)

    valid = [r for r in results if not np.isnan(r.p)]
    if valid:
        adj = multipletests([r.p for r in valid], method="fdr_bh")[1]
        for r, pa in zip(valid, adj, strict=True):
            r.p_fdr = float(pa)
    sec.refs |= {"benjamini1995", "wasserstein2016"}
    for r in results:
        sec.refs |= r.refs

    # --- Tableaux synthétiques ---
    abbrev = {"V de Cramér": "V", "d de Somers": "dS", "d de Cohen": "d", "Corrélation bisériale de rang": "rb",
              "ω²": "ω²", "ε²": "ε²", "r de Pearson": "r", "ρ de Spearman": "ρ"}
    legend = ("Mesures d'association : V, V de Cramér ; dS, d de Somers ; d, d de Cohen ; rb, corrélation bisériale "
              "de rang ; ω², oméga carré ; ε², epsilon carré ; r, Pearson ; ρ, Spearman. p (FDR) : probabilité "
              "critique corrigée par la procédure de Benjamini et Hochberg pour l'ensemble des variables testées.")

    def assoc(r):
        return f"{abbrev.get(r.effect_label, r.effect_label)} = {fmt.num(r.effect)}" if r.effect_label else "-"

    if y_cat:
        cats = [str(c) for c in ys.cat.categories]
        binary = yinfo.kind == "binaire"
        from .design import event_level_for
        ev = event_level_for(cats) if binary else None
        show = [ev] if binary else cats
        rows = []
        for r in [r for r in results if "crosstab" in r.details or r.test == "non calculable"]:
            info = ds.variables[r.x]
            head = {"Variable": info.label, "Modalité": "", "N": fmt.integer(r.n)}
            head.update({(f"% « {c} »"): "" for c in show})
            head.update({"Test": r.test, "p": fmt.pval(r.p), "p (FDR)": fmt.pval(r.p_fdr), "Association": assoc(r)})
            rows.append(head)
            ct = r.details.get("crosstab")
            if ct is None:
                continue
            rp = ct.div(ct.sum(axis=1), axis=0)
            for mod in ct.index:
                row = {"Variable": "", "Modalité": str(mod), "N": fmt.integer(ct.loc[mod].sum())}
                for c in show:
                    row[f"% « {c} »"] = fmt.pct(rp.loc[mod, c]) if c in rp.columns else "-"
                row.update({"Test": "", "p": "", "p (FDR)": "", "Association": ""})
                rows.append(row)
        if rows:
            sec.tables.append(Table(
                title=f"Association entre {R.y} et les variables explicatives qualitatives",
                data=pd.DataFrame(rows),
                note=(f"Les pourcentages sont calculés en ligne : il s'agit de la part de la modalité « {ev} » "
                      f"{R.de_y()} dans chaque groupe. " if binary else
                      f"Les pourcentages sont calculés en ligne : il s'agit de la répartition {R.de_y()} dans chaque "
                      "groupe. ")
                + legend))
        qrows = []
        for r in [r for r in results if "groupes" in r.details]:
            info = ds.variables[r.x]
            row = {"Variable": info.label, "N": fmt.integer(r.n)}
            for c in cats:
                g = r.details["groupes"].get(c)
                row[f"« {c} »"] = ("-" if not g else f"{fmt.num(g['moyenne'])} ({fmt.num(g['ecart_type'])})"
                                   if r.details.get("parametrique") else
                                   f"{fmt.num(g['mediane'])} [{fmt.num(g['q1'])} ; {fmt.num(g['q3'])}]")
            row.update({"Test": r.test, "p": fmt.pval(r.p), "p (FDR)": fmt.pval(r.p_fdr), "Association": assoc(r)})
            qrows.append(row)
        if qrows:
            sec.tables.append(Table(
                title=f"Comparaison des variables explicatives quantitatives selon {R.y}",
                data=pd.DataFrame(qrows),
                note=f"Les colonnes correspondent aux modalités {R.de_y()}. Les cellules donnent la moyenne (écart "
                     "type) si le test est paramétrique, la médiane [Q1 ; Q3] sinon. " + legend))
    else:
        rows = []
        for r in results:
            info = ds.variables[r.x]
            if "groupes" in r.details:
                rows.append({"Variable": info.label, "Modalité": "", "N": fmt.integer(r.n), "Moyenne (é.-t.)": "",
                             "Médiane [Q1 ; Q3]": "", "Test": r.test, "p": fmt.pval(r.p), "p (FDR)": fmt.pval(r.p_fdr),
                             "Taille d'effet": assoc(r)})
                for mod, g in r.details["groupes"].items():
                    rows.append({"Variable": "", "Modalité": mod, "N": fmt.integer(g["n"]),
                                 "Moyenne (é.-t.)": f"{fmt.num(g['moyenne'])} ({fmt.num(g['ecart_type'])})",
                                 "Médiane [Q1 ; Q3]": f"{fmt.num(g['mediane'])} [{fmt.num(g['q1'])} ; {fmt.num(g['q3'])}]",
                                 "Test": "", "p": "", "p (FDR)": "", "Taille d'effet": ""})
            else:
                ci = f" {fmt.ci(*r.effect_ci)}" if r.effect_ci else ""
                rows.append({"Variable": info.label, "Modalité": "(corrélation)", "N": fmt.integer(r.n),
                             "Moyenne (é.-t.)": "", "Médiane [Q1 ; Q3]": "", "Test": r.test, "p": fmt.pval(r.p),
                             "p (FDR)": fmt.pval(r.p_fdr), "Taille d'effet": f"{assoc(r)}{ci}"})
        sec.tables.append(Table(title=f"Association entre {R.y} et les variables explicatives", data=pd.DataFrame(rows),
                                note=f"Moyennes et médianes {R.de_y()} selon chaque modalité. " + legend))

    # --- Tableau des justifications ---
    just_rows = [{"Variable": ds.variables[r.x].label, "Test retenu": r.test, "Justification": r.justification,
                  "Fiabilité": r.reliability} for r in results]
    sec.tables.append(Table(title="Choix des tests bivariés et conditions d'application",
                            data=pd.DataFrame(just_rows),
                            note="Le test est choisi selon les règles exposées dans la section consacrée aux "
                                 "méthodes ; la fiabilité est jugée faible lorsque plus de 20 % des effectifs "
                                 "attendus sont inférieurs à cinq."))

    # --- Post-hoc ---
    for r in results:
        if r.posthoc is not None and r.p_fdr < 0.05:
            ph = r.posthoc.copy()
            ph["Différence"] = ph["Différence"].map(fmt.num)
            ph["p ajustée"] = ph["p ajustée"].map(fmt.pval)
            sec.tables.append(Table(
                title=f"Comparaisons deux à deux {de(R.y if not y_cat else R.v(r.x))} "
                      f"({r.details.get('posthoc_nom')})",
                data=ph,
                note=("Différence de moyennes (Tukey-Kramer, Games-Howell) ou de rangs moyens (Dunn). "
                      "Probabilités ajustées pour les comparaisons multiples.")))

    # --- Texte ---
    tested = len(valid)
    sig = [r for r in valid if r.p_fdr < 0.05]
    sig_raw_only = [r for r in valid if r.p < 0.05 <= r.p_fdr]
    intro = (f"Les tableaux ci-dessous présentent les associations testées entre {R.y} et chacune des variables "
             f"explicatives. Sur les {nombre(tested, 'variables')} testées, ")
    if not sig:
        intro += "aucune ne ressort de manière significative au seuil de 5 % "
    elif len(sig) == 1:
        intro += "une seule ressort de manière significative au seuil de 5 % "
    else:
        intro += f"{nombre(len(sig), feminin=True)} ressortent de manière significative au seuil de 5 % "
    intro += "après correction pour les tests multiples (procédure de Benjamini et Hochberg, 1995)"
    if sig_raw_only:
        noms = enumeration([R.v(r.x) for r in sig_raw_only])
        if len(sig_raw_only) == 1:
            intro += f", et une (01) autre, {noms}, ne l'est qu'avant cette correction"
        else:
            intro += f", et {nombre(len(sig_raw_only), feminin=True)} autres ({noms}) ne le sont qu'avant cette correction"
    intro += (". Il convient de préciser que ces associations sont brutes : elles ne tiennent pas compte de l'influence "
              "des autres facteurs, ce qui fera l'objet de l'analyse multivariée.")
    sec.paragraphs.append(intro)
    sec.facts.update({"bivarie.nb_testees": tested, "bivarie.nb_significatives": len(sig),
                      "bivarie.nb_sig_avant_correction": len(sig) + len(sig_raw_only)})
    k = 0
    for r in sorted(valid, key=lambda t: t.p):
        txt = _sentence(r, R, yinfo, y_cat, k, len(sig))
        if txt:
            sec.paragraphs.append(txt)
            k += 1
        pref = f"biv.{r.x}"
        sec.facts.update({f"{pref}.p": r.p, f"{pref}.p_fdr": r.p_fdr, f"{pref}.effet": r.effect,
                          f"{pref}.stat": r.stat, f"{pref}.n": r.n})
        if r.df is not None:
            sec.facts[f"{pref}.ddl"] = r.df
        if r.effect_ci:
            sec.facts[f"{pref}.ic_bas"], sec.facts[f"{pref}.ic_haut"] = r.effect_ci
        if "crosstab" in r.details:
            ct = r.details["crosstab"]
            rp = ct.div(ct.sum(axis=1), axis=0) * 100
            for mod in rp.index:
                for c in rp.columns:
                    sec.facts[f"{pref}.{mod}.{c}.pct"] = float(rp.loc[mod, c])
        if "groupes" in r.details:
            for g, v in r.details["groupes"].items():
                for kk in ("moyenne", "mediane", "ecart_type", "n"):
                    sec.facts[f"{pref}.{g}.{kk}"] = v[kk]
        if "or" in r.details:
            sec.facts.update({f"{pref}.or": r.details["or"], f"{pref}.or_lo": r.details["or_lo"],
                              f"{pref}.or_hi": r.details["or_hi"]})
    if sig:
        top = enumeration([R.v(r.x) for r in sorted(sig, key=lambda t: t.p)[:3]])
        sec.key_points.append(
            f"L'analyse bivariée met en évidence une association significative entre {R.y} et "
            f"{nombre(len(sig), feminin=True)} des {nombre(tested, 'variables')} testées, notamment {top}.")
    ns = [R.v(r.x) for r in valid if r.p_fdr >= 0.05]
    if len(ns) == 1:
        sec.paragraphs.append(f"{'À l’inverse' if sig else 'Ainsi'}, {ns[0]} n'{est(ns[0])} pas "
                              f"{accord('associé', ns[0])} de manière significative {a_(R.y)}.".replace("’", "'"))
    elif ns:
        masc = any(genre(sans_article(v)) == "m" for v in ns)
        sec.paragraphs.append(f"{'À l’inverse' if sig else 'Ainsi'}, ni {', ni '.join(ns)} ne sont "
                              f"{'associés' if masc else 'associées'} de manière significative {a_(R.y)}."
                              .replace("’", "'"))

    # --- Figures ---
    nfig = 0
    for r in sorted(sig, key=lambda t: t.p):
        if nfig >= max_figures:
            break
        info = ds.variables[r.x]
        if "crosstab" in r.details:
            ct = r.details["crosstab"]
            rp = ct.div(ct.sum(axis=1), axis=0) * 100
            p = figures.stacked_by_group(rp, info.label, ylab, outdir)
            sec.figures.append(Figure(p, f"Répartition {de(R.y)} selon {R.v(r.x)}"))
        elif y_cat:
            p = figures.box_by_group(pd.to_numeric(df[r.x], errors="coerce"), ys, info.label, ylab, outdir)
            sec.figures.append(Figure(p, f"Distribution {de(R.v(r.x))} selon {R.y}"))
        elif info.kind in CAT_KINDS:
            p = figures.box_by_group(ys, as_categorical(df[r.x], info), ylab, info.label, outdir)
            sec.figures.append(Figure(p, f"Distribution {de(R.y)} selon {R.v(r.x)}"))
        else:
            p = figures.scatter(df[r.x], ys, info.label, ylab, outdir)
            sec.figures.append(Figure(p, f"Relation entre {R.v(r.x)} et {R.y}"))
        nfig += 1

    sec.method_notes.append(
        "Les associations bivariées sont évaluées par un test choisi selon le niveau de mesure des deux variables "
        "et la vérification de ses conditions d'application. Pour deux variables qualitatives : khi-deux de "
        "Pearson lorsque la règle de Cochran (1954) est respectée, test exact de Fisher (1922) pour un tableau "
        "2 × 2 à effectifs attendus faibles, probabilité critique par permutations de Monte-Carlo sinon ; "
        "l'intensité est mesurée par le V de Cramér (1946), ou par le d de Somers (1962) pour deux variables "
        "ordinales. Pour une variable quantitative et une variable qualitative : t de Welch (1947) ou U de "
        "Mann-Whitney (1947) pour deux groupes ; ANOVA, ANOVA de Welch ou test de Kruskal-Wallis (1952) au-delà, "
        "selon la normalité dans chaque groupe et l'homogénéité des variances (Levene, 1960), suivis de "
        "comparaisons deux à deux ajustées. Pour deux variables quantitatives : corrélation de Pearson ou de "
        "Spearman (1904). Chaque test est accompagné d'une taille d'effet. La multiplicité des tests est "
        "contrôlée par la procédure de Benjamini et Hochberg (1995).")
    sec.extra["tests"] = results
    return sec


MESURES = {"V de Cramér": "un V de Cramér", "d de Somers": "un d de Somers", "d de Cohen": "un d de Cohen",
           "Corrélation bisériale de rang": "une corrélation bisériale de rang", "ω²": "un ω²", "ε²": "un ε²",
           "r de Pearson": "un coefficient de corrélation de Pearson",
           "ρ de Spearman": "un coefficient de corrélation de Spearman"}


def _stats_txt(r: TestResult) -> str:
    """« avec un V de Cramér de 0,15 et une probabilité critique corrigée inférieure à 0,001 (χ² = 57,00 ; ddl = 1) »."""
    txt = "avec "
    if r.effect_label and not np.isnan(r.effect):
        txt += f"{MESURES.get(r.effect_label, 'un ' + r.effect_label)} de {fmt.num(r.effect)} et "
    txt += pcrit(r.p_fdr, corrigee=True)
    if r.stat_label and not np.isnan(r.stat):
        stat = f"{r.stat_label} = {fmt.num(r.stat)}"
        if r.df is not None:
            stat += f" ; ddl = {fmt.num(r.df, 0) if float(r.df).is_integer() else fmt.num(r.df, 1)}"
        txt += f" ({stat})"
    return txt


def _intensite(strength: str, k: int) -> str:
    faible = strength in ("faible", "très faible", "négligeable")
    if k % 3 == 0:
        return f"L'intensité de cette association {'reste' if faible else 'est'} {strength}."
    if k % 3 == 1:
        return f"Il s'agit {'toutefois ' if faible else ''}d'une association d'intensité {strength}."
    return f"Cette association est d'intensité {strength}."


def _sentence(r: TestResult, R, yinfo, y_cat: bool, k: int, total: int = 0) -> str:
    """Commentaire d'une association significative, dans le style des mémoires de statistique sociale."""
    if not r.p_fdr < 0.05:
        return ""
    x = R.v(r.x)
    st = _stats_txt(r)
    ass = accord("associé", x)
    if k == 0:
        head = f"{majuscule(x)} {est(x)} {ass} de manière significative {a_(R.y)}, {st}."
    elif total >= 3 and k == total - 1:
        head = f"Enfin, {x} {est(x)} {ass} de manière significative {a_(R.y)}, {st}."
    else:
        modeles = [
            f"Par ailleurs, l'association entre {x} et {R.y} est également significative, {st}.",
            f"{majuscule(x)} ressort aussi comme un facteur significativement associé {a_(R.y)}, "
            f"{st}.",
            f"Il en va de même pour {x}, {st}.",
            f"Nous notons également une association significative entre {x} et {R.y}, {st}.",
            f"De plus, {x} {est(x)} {accord('lié', x)} de manière significative {a_(R.y)}, {st}.",
        ]
        head = modeles[(k - 1) % len(modeles)]
    head += " " + _intensite(r.strength, k)
    xinfo = R.ds.variables[r.x]
    if "crosstab" in r.details:
        ct = r.details["crosstab"]
        rp = ct.div(ct.sum(axis=1), axis=0)
        from .design import event_level_for
        binary = yinfo.kind == "binaire"
        target = event_level_for([str(c) for c in rp.columns]) if binary else \
            rp.columns[int(np.argmax(rp.var().to_numpy()))]
        stable = ct.sum(axis=1) >= 10  # pas de proportion calculée sur moins de 10 observations dans le texte
        if stable.sum() >= 2:
            col = rp.loc[stable, target]
            hi, lo = str(col.idxmax()), str(col.idxmin())
            quoi = R.indicateur() if binary else f"la part de la modalité {guillemets(str(target))} {de(R.y)}"
            if k % 2 == 0:
                head += (f" En effet, {quoi} passe de {fmt.pct(col[lo])} {R.chez(r.x, lo)} à {fmt.pct(col[hi])} "
                         f"{R.chez(r.x, hi, premier=False)}.")
            else:
                head += (f" {majuscule(quoi)} s'établit à {fmt.pct(col[hi])} {R.chez(r.x, hi)}, contre "
                         f"{fmt.pct(col[lo])} {R.chez(r.x, lo, premier=False)}.")
            if xinfo.kind == "ordinale" and stable.all() and len(col) >= 3:
                d = np.diff(col.to_numpy())
                if (d > 0).all() or (d < 0).all():
                    if k % 2 == 0:
                        sens = "augmente" if (d > 0).all() else "diminue"
                        head += f" Nous pouvons donc dire que {quoi} {sens} avec {x}."
                    else:
                        sens = "croît" if (d > 0).all() else "décroît"
                        head += f" Ainsi, {quoi} {sens} régulièrement avec {x}."
        if "or" in r.details and r.test == "Exact de Fisher":
            head += (f" Le rapport de cotes s'établit à {fmt.num(r.details['or'])}, avec un intervalle de confiance à "
                     f"95 % de {fmt.ci(r.details['or_lo'], r.details['or_hi'])}.")
    elif "groupes" in r.details:
        g = r.details["groupes"]
        key = "moyenne" if r.details.get("parametrique") else "mediane"
        mot = "La moyenne" if key == "moyenne" else "La médiane"
        hi = max(g, key=lambda kk: g[kk][key])
        lo = min(g, key=lambda kk: g[kk][key])
        if y_cat:
            pr = pronom(R.y)
            lorsque = "lorsqu'" + pr if pr[0] in "ei" else "lorsque " + pr
            head += (f" {mot} {de(x)} s'établit à {fmt.num(g[hi][key])} lorsque {R.y} {est(R.y)} "
                     f"{guillemets(hi)}, contre {fmt.num(g[lo][key])} {lorsque} {est(R.y)} {guillemets(lo)}.")
        else:
            head += (f" {mot} {de(R.y)} s'établit à {fmt.num(g[hi][key])} {R.chez(r.x, hi)}, contre "
                     f"{fmt.num(g[lo][key])} {R.chez(r.x, lo, premier=False)}.")
    elif r.effect_label:
        adj = accord("élevé", R.y)
        if r.effect > 0:
            head += f" Ainsi, plus {x} {est(x)} {accord('élevé', x)}, plus {R.y} tend à être {adj}."
        else:
            head += f" Ainsi, plus {x} {est(x)} {accord('élevé', x)}, moins {R.y} tend à être {adj}."
    return head
