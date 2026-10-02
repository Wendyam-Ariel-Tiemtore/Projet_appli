"""Analyse multi-niveaux (deux niveaux) : modèles linéaire et logistique à effets aléatoires.

Démarche par étapes (Soura, 2POP2302 ; Snijders et Bosker, 2012) :
M0 modèle vide -> M1 variables individuelles -> M2 variables contextuelles -> M3 pente aléatoire (linéaire).

La logistique à ordonnée aléatoire est estimée par maximum de vraisemblance avec une quadrature de
Gauss-Hermite adaptative (Pinheiro et Bates, 1995), implémentée ici et validée par simulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import optimize, stats
from scipy.special import expit, logsumexp

from ..writing.phrases import Redac, accord, elision, est, pcrit
from ..writing.style import a, de, enumeration, genre, guillemets, nombre, sans_article
from . import figures, fmt
from .design import Design, build_design
from .io import Dataset
from .models import effect_paragraphs
from .results import Figure, Section, Table

PI2_3 = np.pi ** 2 / 3


# ---------------------------------------------------------------------------
# Logistique à ordonnée aléatoire par quadrature de Gauss-Hermite adaptative
# ---------------------------------------------------------------------------

@dataclass
class GLMMResult:
    beta: np.ndarray
    se: np.ndarray
    names: list[str]
    sigma2: float
    sigma2_se: float
    llf: float
    llf_glm: float
    n: int
    n_groups: int
    u_hat: np.ndarray
    u_se: np.ndarray
    converged: bool

    @property
    def lr_var(self) -> tuple[float, float]:
        lr = max(0.0, 2 * (self.llf - self.llf_glm))
        return lr, 0.5 * stats.chi2.sf(lr, 1)  # mélange 50:50 (Self et Liang, 1987)

    @property
    def vpc(self) -> float:
        return self.sigma2 / (self.sigma2 + PI2_3)

    @property
    def mor(self) -> float:
        return float(np.exp(np.sqrt(2 * self.sigma2) * stats.norm.ppf(0.75)))

    def wald(self) -> pd.DataFrame:
        z = self.beta / self.se
        p = 2 * stats.norm.sf(np.abs(z))
        return pd.DataFrame({"coef": self.beta, "se": self.se, "z": z, "p": p,
                             "est": np.exp(self.beta), "lo_e": np.exp(self.beta - 1.96 * self.se),
                             "hi_e": np.exp(self.beta + 1.96 * self.se)}, index=self.names)

    @property
    def aic(self) -> float:
        return -2 * self.llf + 2 * (len(self.beta) + 1)


class RandomInterceptLogit:
    def __init__(self, y: np.ndarray, X: np.ndarray, groups: np.ndarray, n_quad: int = 15):
        self.y = np.asarray(y, dtype=float)
        self.X = np.asarray(X, dtype=float)
        self.g = np.asarray(groups, dtype=int)
        self.J = int(self.g.max()) + 1
        self.z, self.w = np.polynomial.hermite.hermgauss(n_quad)
        self.logw = np.log(self.w) + self.z ** 2

    def _mode(self, eta: np.ndarray, s2: float):
        u = np.zeros(self.J)
        for _ in range(50):
            p = expit(eta + u[self.g])
            grad = np.bincount(self.g, self.y - p, self.J) - u / s2
            hess = -np.bincount(self.g, p * (1 - p), self.J) - 1 / s2
            step = grad / hess
            u -= step
            if np.max(np.abs(step)) < 1e-10:
                break
        p = expit(eta + u[self.g])
        hess = -np.bincount(self.g, p * (1 - p), self.J) - 1 / s2
        return u, 1 / np.sqrt(-hess)

    def _cluster_logf(self, eta: np.ndarray, u: np.ndarray, s2: float) -> np.ndarray:
        lin = eta + u[self.g]
        ll = self.y * lin - np.logaddexp(0, lin)
        return np.bincount(self.g, ll, self.J) - u ** 2 / (2 * s2) - 0.5 * np.log(2 * np.pi * s2)

    def loglik(self, theta: np.ndarray) -> float:
        beta, log_s = theta[:-1], theta[-1]
        s2 = float(np.exp(2 * log_s))
        eta = self.X @ beta
        mode, scale = self._mode(eta, s2)
        vals = np.empty((len(self.z), self.J))
        for k, zk in enumerate(self.z):
            u = mode + np.sqrt(2) * scale * zk
            vals[k] = self.logw[k] + self._cluster_logf(eta, u, s2)
        return float(np.sum(np.log(np.sqrt(2) * scale) + logsumexp(vals, axis=0)))

    def fit(self, names: list[str]) -> GLMMResult:
        glm = sm.GLM(self.y, self.X, family=sm.families.Binomial()).fit()
        start = np.concatenate([glm.params, [np.log(0.7)]])
        obj = lambda th: -self.loglik(th)  # noqa: E731
        opt = optimize.minimize(obj, start, method="BFGS", options={"gtol": 1e-6, "maxiter": 500})
        theta = opt.x
        # Si la variance tend vers zéro, la quadrature reste stable grâce au paramétrage en log(σ)
        H = _num_hessian(obj, theta)
        try:
            cov = np.linalg.inv(H)
        except np.linalg.LinAlgError:
            cov = np.linalg.pinv(H)
        se_all = np.sqrt(np.clip(np.diag(cov), 0, None))
        s2 = float(np.exp(2 * theta[-1]))
        s2_se = float(2 * s2 * se_all[-1])  # méthode delta
        u, uscale = self._mode(self.X @ theta[:-1], s2)
        return GLMMResult(beta=theta[:-1], se=se_all[:-1], names=names, sigma2=s2, sigma2_se=s2_se,
                          llf=-float(opt.fun), llf_glm=float(glm.llf), n=len(self.y), n_groups=self.J,
                          u_hat=u, u_se=uscale, converged=bool(opt.success or opt.status == 2))


def _num_hessian(f, x: np.ndarray) -> np.ndarray:
    k = len(x)
    h = 1e-4 * np.maximum(1.0, np.abs(x))
    H = np.zeros((k, k))
    f0 = f(x)
    for i in range(k):
        ei = np.zeros(k)
        ei[i] = h[i]
        H[i, i] = (f(x + ei) - 2 * f0 + f(x - ei)) / h[i] ** 2
        for j in range(i + 1, k):
            ej = np.zeros(k)
            ej[j] = h[j]
            H[i, j] = H[j, i] = (f(x + ei + ej) - f(x + ei - ej) - f(x - ei + ej) + f(x - ei - ej)) / (4 * h[i] * h[j])
    return H


# ---------------------------------------------------------------------------
# Linéaire mixte
# ---------------------------------------------------------------------------

@dataclass
class LMMResult:
    res: object
    names: list[str]
    sigma2_u: float
    sigma2_e: float
    llf: float
    llf_ols: float
    n: int
    n_groups: int
    slope_var: float | None = None
    slope_cov: float | None = None
    r2_m: float = np.nan
    r2_c: float = np.nan

    @property
    def lr_var(self) -> tuple[float, float]:
        lr = max(0.0, 2 * (self.llf - self.llf_ols))
        return lr, 0.5 * stats.chi2.sf(lr, 1)

    @property
    def icc(self) -> float:
        return self.sigma2_u / (self.sigma2_u + self.sigma2_e)

    def wald(self) -> pd.DataFrame:
        fe = np.asarray(self.res.fe_params, dtype=float)
        se = np.asarray(self.res.bse_fe, dtype=float)
        z = fe / se
        p = 2 * stats.norm.sf(np.abs(z))
        return pd.DataFrame({"coef": fe, "se": se, "z": z, "p": p, "est": fe, "lo_e": fe - 1.96 * se,
                             "hi_e": fe + 1.96 * se}, index=self.names)

    @property
    def aic(self) -> float:
        k = len(self.names) + 2 + (2 if self.slope_var is not None else 0)
        return -2 * self.llf + 2 * k


def fit_lmm(y: np.ndarray, X: np.ndarray, groups: np.ndarray, names: list[str],
            slope: np.ndarray | None = None) -> LMMResult:
    exog_re = None
    if slope is not None:
        exog_re = np.column_stack([np.ones(len(y)), slope])
    mod = sm.MixedLM(y, X, groups=groups, exog_re=exog_re)
    res = None
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for method in ("lbfgs", "bfgs", "powell", "nm"):
            try:
                cand = mod.fit(reml=False, method=method, maxiter=2000)
            except (np.linalg.LinAlgError, ValueError):
                continue
            if np.isfinite(cand.llf) and (res is None or cand.llf > res.llf + 1e-8):
                res = cand
    if res is None:
        raise RuntimeError("Le modèle linéaire mixte n'a pas convergé.")
    cov_re = np.asarray(res.cov_re, dtype=float)
    s2u = float(cov_re[0, 0])
    s2e = float(res.scale)
    ols = sm.OLS(y, X).fit()
    out = LMMResult(res=res, names=names, sigma2_u=s2u, sigma2_e=s2e, llf=float(res.llf), llf_ols=float(ols.llf),
                    n=len(y), n_groups=len(np.unique(groups)))
    if slope is not None:
        out.slope_var = float(cov_re[1, 1])
        out.slope_cov = float(cov_re[0, 1])
    var_f = float(np.var(X @ np.asarray(res.fe_params, dtype=float)))
    tot = var_f + s2u + s2e
    out.r2_m, out.r2_c = var_f / tot, (var_f + s2u) / tot
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def contextual_variables(df: pd.DataFrame, cluster: str, variables: list[str]) -> list[str]:
    """Variables constantes à l'intérieur de chaque contexte (niveau 2)."""
    out = []
    g = df[cluster]
    for v in variables:
        nun = df.groupby(g, observed=True)[v].nunique(dropna=True)
        if len(nun) and (nun <= 1).all():
            out.append(v)
    return out


def multilevel(ds: Dataset, outcome: str, explanatory: list[str], cluster: str, outdir: Path,
               level2: list[str] | None = None, references: dict[str, str] | None = None,
               event_level: str | None = None, random_slope: str | None = None) -> Section:
    yinfo = ds.variables[outcome]
    sec = Section(key="multiniveau", title="Analyse multi-niveaux : effets de composition et effets de contexte",
                  level=2)
    sec.refs |= {"snijders2012", "goldstein2011", "raudenbush2002", "self1987"}
    if yinfo.kind not in ("binaire", "continue"):
        sec.warnings.append("L'analyse multi-niveaux est proposée pour une variable dépendante binaire ou continue "
                            "dans cette version.")
        return sec
    lvl2 = level2 if level2 is not None else contextual_variables(ds.df, cluster, explanatory)
    lvl1 = [v for v in explanatory if v not in lvl2 and v != cluster]
    dsg = build_design(ds, outcome, lvl1 + lvl2, references, event_level, extra_cols=[cluster])
    # Centrage des variables quantitatives sur la moyenne générale : la constante et la variance de
    # l'ordonnée à l'origine se rapportent alors à un individu « moyen » (Snijders et Bosker, 2012).
    centred, centred_vars = [], []
    for t in dsg.terms:
        if not t.levels:
            c = t.columns[0]
            dsg.X[c] = dsg.X[c] - dsg.X[c].mean()
            centred.append(t.label)
            centred_vars.append(t.variable)
    groups_raw = ds.df.loc[dsg.index, cluster]
    gcodes, guniq = pd.factorize(groups_raw)
    J = len(guniq)
    sizes = np.bincount(gcodes)
    sec.facts.update({"mn.n": dsg.n_used, "mn.contextes": J, "mn.taille_moyenne": float(sizes.mean()),
                      "mn.taille_min": int(sizes.min()), "mn.taille_max": int(sizes.max())})
    if J < 10 or sizes.mean() < 5:
        sec.warnings.append(
            f"Avec {nombre(J, 'contextes')} et {fmt.num(sizes.mean(), 1)} individus par contexte en moyenne, les "
            "variances contextuelles sont estimées avec une faible précision. Les repères usuels sont d'au moins dix "
            "(10) contextes, idéalement trente (30) ou plus, et de cinq (05) individus par contexte.")
    if J < 3:
        return sec

    cols1 = [c for t in dsg.terms if t.variable in lvl1 for c in t.columns]
    cols2 = [c for t in dsg.terms if t.variable in lvl2 for c in t.columns]
    stages = [("M0", []), ("M1", cols1)]
    if cols2:
        stages.append(("M2", cols1 + cols2))
    y = dsg.y.to_numpy(dtype=float)
    binary = yinfo.kind == "binaire"
    fits = []
    for name, cols in stages:
        Xs = np.column_stack([np.ones(len(y))] + [dsg.X[c].to_numpy(dtype=float) for c in cols])
        names = ["const"] + cols
        if binary:
            f = RandomInterceptLogit(y, Xs, gcodes).fit(names)
        else:
            f = fit_lmm(y, Xs, gcodes, names)
        fits.append((name, cols, f))

    slope_fit = None
    if random_slope and not binary:
        sc = [c for t in dsg.terms if t.variable == random_slope for c in t.columns]
        if len(sc) == 1:
            last_cols = fits[-1][1]
            Xs = np.column_stack([np.ones(len(y))] + [dsg.X[c].to_numpy(dtype=float) for c in last_cols])
            try:
                slope_fit = fit_lmm(y, Xs, gcodes, ["const"] + last_cols, slope=dsg.X[sc[0]].to_numpy(dtype=float))
                fits.append(("M3", last_cols, slope_fit))
            except Exception:  # noqa: BLE001
                sec.warnings.append("Le modèle à pente aléatoire n'a pas convergé ; il n'est pas présenté.")

    # --- Tableau des effets fixes ---
    rows = []
    rows.append(dict({"Caractéristique": "Constante"},
                     **{nm: _cell(f.wald(), "const") for nm, _, f in fits}))
    for block, cols in (("Facteurs individuels (niveau 1)", cols1), ("Facteurs contextuels (niveau 2)", cols2)):
        if not cols:
            continue
        rows.append(dict({"Caractéristique": block}, **{nm: "" for nm, _, _ in fits}))
        for t in dsg.terms:
            if not any(c in cols for c in t.columns):
                continue
            if t.levels:
                rows.append(dict({"Caractéristique": t.label}, **{nm: "" for nm, _, _ in fits}))
                rows.append(dict({"Caractéristique": f"   {t.reference}"},
                                 **{nm: ("Réf." if t.columns[0] in fc else "") for nm, fc, _ in fits}))
                for c, lev in zip(t.columns, t.levels, strict=True):
                    rows.append(dict({"Caractéristique": f"   {lev}"},
                                     **{nm: (_cell(f.wald(), c) if c in fc else "") for nm, fc, f in fits}))
            else:
                c = t.columns[0]
                rows.append(dict({"Caractéristique": f"{t.label} (par unité)"},
                                 **{nm: (_cell(f.wald(), c) if c in fc else "") for nm, fc, f in fits}))
    rows.append(dict({"Caractéristique": "Variance contextuelle (σ²ᵤ)"},
                     **{nm: f"{fmt.num(_s2u(f), 3)}{fmt.stars(f.lr_var[1])}" for nm, _, f in fits}))
    if slope_fit is not None:
        rows.append(dict({"Caractéristique": f"Variance de la pente : {ds.variables[random_slope].label}"},
                         **{nm: (fmt.num(f.slope_var, 5) if nm == "M3" else "") for nm, _, f in fits}))
    rows.append(dict({"Caractéristique": "Log-vraisemblance"}, **{nm: fmt.num(f.llf, 1) for nm, _, f in fits}))
    rows.append(dict({"Caractéristique": "AIC"}, **{nm: fmt.num(f.aic, 1) for nm, _, f in fits}))
    R = Redac(ds, outcome, dsg.event_level)
    ctx_txt = R.v(cluster)
    sec.tables.append(Table(
        title=f"Facteurs individuels et contextuels associés {a(R.y)} : modèles multi-niveaux"
              + (f" (modalité modélisée : {guillemets(dsg.event_level)})" if binary else ""),
        data=pd.DataFrame(rows),
        note=(("OR : rapports de cotes. " if binary else "β : coefficients. ")
              + f"Le modèle porte sur {fmt.integer(dsg.n_used)} individus répartis dans {fmt.integer(J)} contextes, "
              f"définis par {ctx_txt}. Les effets fixes sont testés par le test de Wald, et la variance contextuelle "
              "par le rapport de vraisemblance contre le modèle sans effet aléatoire (mélange à parts égales de "
              "lois du khi-deux). " + fmt.STARS_NOTE)))

    # --- Décomposition de la variance ---
    base = _s2u(fits[0][2])
    vrows = []
    for nm, _, f in fits:
        if nm == "M3":  # variance de l'ordonnée à l'origine non comparable en présence d'une pente aléatoire
            continue
        s2u = _s2u(f)
        lvl1_var = PI2_3 if binary else f.sigma2_e
        vpc = s2u / (s2u + lvl1_var)
        change = (base - s2u) / base * 100 if base > 0 else np.nan
        row = {"Indice": nm, "Variance individuelle": fmt.num(lvl1_var, 3), "Variance contextuelle": fmt.num(s2u, 3),
               "Variance totale": fmt.num(s2u + lvl1_var, 3),
               "Variation de la variance contextuelle (%)": "-" if nm == "M0" else fmt.num(change, 1),
               "VPC (%)": fmt.num(100 * vpc, 1)}
        if binary:
            row["Rapport de cotes médian"] = fmt.num(f.mor)
        else:
            row["R² marginal / conditionnel"] = f"{fmt.num(f.r2_m, 3)} / {fmt.num(f.r2_c, 3)}"
        vrows.append(row)
        sec.facts.update({f"mn.{nm}.var_ctx": s2u, f"mn.{nm}.vpc": 100 * vpc, f"mn.{nm}.var_tot": s2u + lvl1_var,
                          f"mn.{nm}.var_ind": lvl1_var, f"mn.{nm}.lr": f.lr_var[0], f"mn.{nm}.lr_p": f.lr_var[1],
                          f"mn.{nm}.llf": f.llf, f"mn.{nm}.aic": f.aic})
        if nm != "M0":
            sec.facts[f"mn.{nm}.variation_var_pct"] = change
        if binary:
            sec.facts[f"mn.{nm}.mor"] = f.mor
    sec.tables.append(Table(
        title="Décomposition de la variance et part attribuable aux contextes",
        data=pd.DataFrame(vrows),
        note=("VPC : coefficient de partition de la variance, c'est-à-dire la part de la variance totale située "
              "entre contextes. "
              + ("En logistique, la variance individuelle est fixée à π²/3, soit environ 3,29 (approche de la variable "
                 "latente). Le rapport de cotes médian (MOR) exprime l'hétérogénéité contextuelle sur l'échelle des "
                 "rapports de cotes (Merlo et al., 2006)." if binary else
                 "R² marginal : part expliquée par les effets fixes ; conditionnel : par les effets fixes et "
                 "aléatoires (Nakagawa et Schielzeth, 2013)."))))
    if binary:
        sec.refs |= {"merlo2006", "larsen2005", "pinheiro1995"}
    else:
        sec.refs |= {"nakagawa2013", "seabold2010"}

    # --- Texte (démarche par étapes : modèle vide, composition, contexte) ---
    f0 = fits[0][2]
    lr0, p0 = f0.lr_var
    s0 = _s2u(f0)
    vpc0 = s0 / (s0 + (PI2_3 if binary else f0.sigma2_e))
    sec.paragraphs.append(
        f"Les {R.unite} de l'échantillon étant regroupés dans {nombre(J, 'contextes')}, définis par {ctx_txt}, nous "
        "avons estimé une série de modèles multi-niveaux selon une démarche par étapes. Le modèle vide (M0) mesure "
        "d'abord la variabilité entre contextes ; les caractéristiques individuelles (M1) puis contextuelles (M2) sont "
        "ensuite introduites, en suivant l'évolution de la variance contextuelle.".replace(
            "regroupés", "regroupées" if R.fem else "regroupés"))
    txt = (f"Le modèle vide montre que {R.y} "
           + ("varie significativement" if p0 < 0.05 else "ne varie pas significativement")
           + f" d'un contexte à l'autre. La variance contextuelle s'établit en effet à {fmt.num(s0, 3)}, et le test du "
             f"rapport de vraisemblance donne une statistique de {fmt.num(lr0)} avec {pcrit(p0)}. Le coefficient de "
             f"partition de la variance indique que {fmt.num(100 * vpc0, 1)} % de la variabilité du phénomène se "
             f"situe entre les contextes, et {fmt.num(100 - 100 * vpc0, 1)} % entre les {R.unite} d'un même contexte.")
    if binary:
        txt += (f" Par ailleurs, le rapport de cotes médian vaut {fmt.num(f0.mor)} : si l'on compare deux "
                f"{R.unite} de même profil tirés au hasard dans deux contextes différents, celui du contexte le plus "
                f"favorable a, en médiane, des chances {fmt.num(f0.mor)} fois plus élevées "
                f"{elision('de', R.evenement())}.")
        if R.fem:
            txt = txt.replace("tirés au hasard", "tirées au hasard").replace("celui du contexte", "celle du contexte")
    sec.paragraphs.append(txt)
    sec.key_points.append(
        f"Le modèle vide montre que {fmt.num(100 * vpc0, 1)} % de la variabilité {de(R.y)} se situe entre les "
        "contextes.")
    if p0 >= 0.05:
        sec.paragraphs.append("La variance contextuelle n'étant pas significative, le recours à un modèle "
                              "multi-niveaux apporte peu par rapport à un modèle à un seul niveau. Les résultats "
                              "suivants sont donc présentés à titre de vérification.")
    if len(fits) > 1:
        f1 = fits[1][2]
        s1 = _s2u(f1)
        ch1 = (s0 - s1) / s0 * 100 if s0 > 0 else np.nan
        txt = ("L'introduction des caractéristiques individuelles (M1) "
               + (f"réduit la variance contextuelle de {fmt.num(ch1, 1)} %" if ch1 >= 0 else
                  f"augmente la variance contextuelle de {fmt.num(-ch1, 1)} %")
               + f", qui passe de {fmt.num(s0, 3)} à {fmt.num(s1, 3)}.")
        if ch1 > 0:
            txt += (" Cette part des différences entre contextes tient donc à des effets de composition : les contextes "
                    f"diffèrent d'abord par les caractéristiques des {R.unite} qui y vivent.")
        if f1.lr_var[1] < 0.05:
            txt += (f" Néanmoins, la variance contextuelle reste significative, avec {pcrit(f1.lr_var[1])}, ce qui "
                    "signale l'existence d'autres facteurs de différenciation entre contextes, observés ou non.")
        else:
            txt += f" La variance contextuelle n'est alors plus significative, avec {pcrit(f1.lr_var[1])}."
        sec.paragraphs.append(txt)
        if binary and ch1 < 0:
            sec.paragraphs.append(
                "Il convient de préciser qu'en régression logistique, l'ajout de variables individuelles peut augmenter "
                "la variance contextuelle par simple effet d'échelle de la variable latente (Snijders et Bosker, "
                "2012). Cette hausse ne traduit donc pas nécessairement un accroissement des écarts entre contextes.")
    if cols2 and len(fits) > 2:
        f1, f2 = fits[1][2], fits[2][2]
        s1, s2 = _s2u(f1), _s2u(f2)
        ch2 = (s1 - s2) / s1 * 100 if s1 > 0 else np.nan
        tot = (s0 - s2) / s0 * 100 if s0 > 0 else np.nan
        sec.paragraphs.append(
            f"Les variables contextuelles (M2) expliquent quant à elles {fmt.num(ch2, 1)} % de la variance contextuelle "
            f"qui subsistait après contrôle des effets de composition. Au total, {fmt.num(tot, 1)} % de la variance "
            f"contextuelle initiale est expliquée. La variance résiduelle, qui s'établit à {fmt.num(s2, 3)}, "
            + ("demeure significative : d'autres facteurs contextuels non observés contribuent donc aux différences "
               "entre contextes." if f2.lr_var[1] < 0.05 else "n'est plus significative."))
        sec.key_points.append(
            f"Les effets de composition et de contexte expliquent ensemble {fmt.num(tot, 1)} % de la variance "
            "contextuelle initiale.")
    final_name, final_cols, final = fits[2] if len(fits) > 2 and fits[2][0] == "M2" else fits[-1] \
        if fits[-1][0] != "M3" else fits[-2]
    tab = final.wald()
    kind = "logistique" if binary else "lineaire"
    t1 = [t for t in dsg.terms if any(c in cols1 for c in t.columns)]
    t2 = [t for t in dsg.terms if any(c in cols2 for c in t.columns)]
    nom = "complet" if final_name == "M2" else "final"
    ouv1 = [f"Dans le modèle {nom} ({final_name}), au niveau individuel et toutes choses égales par ailleurs, ",
            "De même, ", "Par ailleurs, ", "En ce qui concerne {x}, ", "Quant {a}, ", "En outre, "]
    paras1, cles1, ns1 = effect_paragraphs(t1, tab, kind, R, binary, ouv1, conclure_ns=False)
    sec.paragraphs.extend(paras1)
    sec.key_points.extend(cles1[:2])
    if t2:
        ouv2 = ["Au niveau contextuel, toutes choses égales par ailleurs, ", "De même, ", "Par ailleurs, "]
        paras2, cles2, ns2 = effect_paragraphs(t2, tab, kind, R, binary, ouv2, conclure_ns=False)
        sec.paragraphs.extend(paras2)
        sec.key_points.extend(cles2[:2])
        if not paras2:
            sec.paragraphs.append(f"Au niveau contextuel, aucune des variables introduites ({enumeration(ns2)}) "
                                  f"n'est associée de manière significative {a(R.y)} au seuil de 5 %, toutes choses "
                                  "égales par ailleurs.")
            ns2 = []
    else:
        ns2 = []
    ns = ns1 + ns2
    if ns:
        if len(ns) == 1:
            sec.paragraphs.append(f"En revanche, {ns[0]} n'{est(ns[0])} pas {accord('associé', ns[0])} de manière "
                                  f"significative {a(R.y)} dans ce modèle.")
        else:
            masc = any(genre(sans_article(v)) == "m" for v in ns)
            sec.paragraphs.append(f"En revanche, ni {', ni '.join(ns)} ne sont {'associés' if masc else 'associées'} "
                                  f"de manière significative {a(R.y)} dans ce modèle.")
    for t in dsg.terms:
        for c in t.columns:
            if c not in tab.index or tab.loc[c, "p"] >= 0.05:
                continue
            r = tab.loc[c]
            sec.facts[f"mn.{final_name}.{c}.est"] = r["est"]
            sec.facts[f"mn.{final_name}.{c}.ic_bas"] = r["lo_e"]
            sec.facts[f"mn.{final_name}.{c}.ic_haut"] = r["hi_e"]
            sec.facts[f"mn.{final_name}.{c}.p"] = r["p"]
            if binary:
                sec.facts[f"mn.{final_name}.{c}.facteur"] = r["est"] if r["est"] >= 1 else 1 / r["est"]
                sec.facts[f"mn.{final_name}.{c}.pct_moins"] = 100 * (1 - r["est"])
    if slope_fit is not None:
        lr = 2 * (slope_fit.llf - fits[-2][2].llf)
        p = 0.5 * stats.chi2.sf(lr, 1) + 0.5 * stats.chi2.sf(lr, 2)
        sec.paragraphs.append(
            f"L'introduction d'une pente aléatoire pour {R.v(random_slope)} (M3) "
            + ("améliore significativement" if p < 0.05 else "n'améliore pas significativement")
            + f" l'ajustement, le rapport de vraisemblance valant {fmt.num(lr)} avec {pcrit(p)}. L'association de "
              f"cette variable avec {R.y} "
            + ("varie donc d'un contexte à l'autre." if p < 0.05 else "peut donc être considérée comme identique dans "
                                                                       "tous les contextes."))
        sec.facts.update({"mn.M3.lr_pente": lr, "mn.M3.p_pente": p, "mn.M3.var_pente": slope_fit.slope_var,
                          "mn.M3.cov_pente": slope_fit.slope_cov})

    # --- Graphique en chenille ---
    if binary:
        u = pd.DataFrame({"est": final.u_hat, "se": final.u_se})
    else:
        re_ = final.res.random_effects
        u = pd.DataFrame({"est": [float(np.asarray(v)[0]) for v in re_.values()],
                          "se": np.sqrt(final.sigma2_u * 0 + np.nan_to_num(_lmm_re_se(final)))})
    p = figures.caterpillar(u, outdir, f"Contextes ({ds.variables[cluster].label})")
    sec.figures.append(Figure(p, f"Effets aléatoires des contextes estimés dans le modèle {final_name} et intervalles "
                                 "de confiance à 95 %"))
    n_extreme = int(((u["est"] - 1.96 * u["se"]) > 0).sum() + ((u["est"] + 1.96 * u["se"]) < 0).sum())
    sec.facts["mn.contextes_extremes"] = n_extreme
    if n_extreme == 0:
        sec.paragraphs.append("L'examen des effets aléatoires montre qu'aucun contexte ne se distingue "
                              "significativement de la moyenne, l'intervalle de confiance de chaque effet aléatoire "
                              "incluant zéro.")
    else:
        sec.paragraphs.append(
            f"L'examen des effets aléatoires montre que "
            f"{nombre(n_extreme, 'contextes') if n_extreme > 1 else 'un (01) contexte'} sur {fmt.integer(J)} "
            f"{'se distinguent' if n_extreme > 1 else 'se distingue'} significativement de la moyenne, l'intervalle de "
            f"confiance de l'effet aléatoire excluant zéro. {'Ils constituent' if n_extreme > 1 else 'Il constitue'} "
            "des terrains privilégiés pour une étude approfondie.")
    sec.paragraphs.append(
        "Ces résultats doivent être lus en gardant à l'esprit deux écueils. Le premier est l'inférence écologique "
        "fallacieuse, qui consisterait à lire au niveau individuel une relation observée entre contextes. Le second "
        "est l'erreur atomiste, qui consisterait à ignorer l'influence des normes et des ressources du milieu de vie "
        "sur les comportements individuels.")

    sec.method_notes.append(
        f"Pour tenir compte de la structure hiérarchique des données ({fmt.integer(dsg.n_used)} individus dans {J} "
        f"contextes), des modèles multi-niveaux à deux niveaux sont estimés selon une démarche par étapes : un modèle "
        f"vide (M0) pour mesurer la variabilité entre contextes, puis l'introduction des variables individuelles (M1) "
        f"et contextuelles (M2) en suivant l'évolution de la variance contextuelle (Snijders et Bosker, 2012 ; "
        f"Goldstein, 2011). "
        + ("Les modèles logistiques à ordonnée aléatoire sont estimés par le maximum de vraisemblance avec une "
           "quadrature de Gauss-Hermite adaptative à 15 points (Pinheiro et Bates, 1995). La variance individuelle est "
           "fixée à π²/3 pour le calcul du coefficient de partition de la variance, et l'hétérogénéité contextuelle "
           "est aussi exprimée par le rapport de cotes médian (Merlo et al., 2006). "
           if binary else
           "Les modèles linéaires mixtes sont estimés par le maximum de vraisemblance. ")
        + "Les effets fixes sont testés par le test de Wald et la variance contextuelle par le test du rapport de "
          "vraisemblance, avec une loi de référence corrigée pour la valeur frontière (Self et Liang, 1987). "
        + ("Les variables contextuelles sont celles qui sont constantes au sein de chaque contexte. "
           if level2 is None else "")
        + ("Les variables quantitatives (" + enumeration([R.v(c) for c in centred_vars]) + ") sont centrées sur leur "
           "moyenne générale, de sorte que la constante et la variance contextuelle se rapportent à un individu de "
           "valeurs moyennes." if centred else ""))
    sec.extra["fits"] = fits
    return sec


def _lmm_re_se(f: LMMResult) -> np.ndarray:
    # Écart type conditionnel de l'effet aléatoire (approximation sans incertitude des effets fixes)
    sizes = pd.Series(f.res.model.groups).value_counts().reindex(list(f.res.random_effects.keys())).to_numpy()
    return np.sqrt(1 / (1 / f.sigma2_u + sizes / f.sigma2_e)) if f.sigma2_u > 0 else np.zeros(len(sizes))


def _s2u(f) -> float:
    return f.sigma2 if isinstance(f, GLMMResult) else f.sigma2_u


def _cell(tab: pd.DataFrame, c: str) -> str:
    if c not in tab.index:
        return ""
    return f"{fmt.num(tab.loc[c, 'est'], 3)}{fmt.stars(tab.loc[c, 'p'])}"


def _lab(dsg: Design, col: str) -> str:
    for t in dsg.terms:
        if col in t.columns:
            return f"{t.label} : {t.levels[t.columns.index(col)]}" if t.levels else t.label
    return col
