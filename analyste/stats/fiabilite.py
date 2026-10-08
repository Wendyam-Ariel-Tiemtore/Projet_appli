"""Fiabilité des résultats : séparation (Firth), validation interne par bootstrap, comparaison avec un modèle
d'apprentissage automatique validé par validation croisée, et bilan de fiabilité lisible par tous.

Principes :
- la régression logistique pénalisée de Firth (1993) remplace l'estimation classique lorsque la séparation
  (quasi-)complète rend les coefficients infinis ou instables (Heinze et Schemper, 2002) ;
- la validation interne par bootstrap (Harrell, Lee et Mark, 1996 ; Steyerberg et al., 2001) mesure le
  sur-ajustement : l'aire sous la courbe ROC est corrigée de son optimisme ;
- un modèle de gradient boosting (Friedman, 2001), évalué par validation croisée, sert de témoin : s'il prédit
  nettement mieux que le modèle explicatif, des non-linéarités ou des interactions ont pu être omises.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from ..writing.phrases import Redac
from ..writing.style import enumeration, nombre
from . import fmt
from .results import Section, Table

SEED = 42


# ---------------------------------------------------------------------------
# Régression logistique pénalisée de Firth
# ---------------------------------------------------------------------------

class FirthResult:
    """Résultat au format attendu par models.Fit (params, bse, pvalues, conf_int, llf, fittedvalues…)."""

    def __init__(self, params, cov, X1: pd.DataFrame, y: np.ndarray, llf: float, converged: bool):
        names = list(X1.columns)
        self.params = pd.Series(params, index=names)
        self.cov = cov
        self.bse = pd.Series(np.sqrt(np.clip(np.diag(cov), 0, None)), index=names)
        z = self.params / self.bse.replace(0, np.nan)
        self.pvalues = pd.Series(2 * stats.norm.sf(np.abs(z)), index=names)
        eta = X1.to_numpy(dtype=float) @ params
        self.fittedvalues = pd.Series(1 / (1 + np.exp(-eta)), index=X1.index)
        self.llf = float(llf)
        ybar = float(np.clip(np.mean(y), 1e-12, 1 - 1e-12))
        self.llnull = float(len(y) * (ybar * np.log(ybar) + (1 - ybar) * np.log(1 - ybar)))
        self.nobs = float(len(y))
        self.df_model = float(len(params) - 1)
        self.aic = -2 * self.llf + 2 * len(params)
        self.converged = converged
        self.prsquared = 1 - self.llf / self.llnull if self.llnull else np.nan

    def conf_int(self, alpha: float = 0.05) -> pd.DataFrame:
        q = stats.norm.ppf(1 - alpha / 2)
        return pd.DataFrame({0: self.params - q * self.bse, 1: self.params + q * self.bse})


def firth_logit(y: np.ndarray, X1: pd.DataFrame, max_iter: int = 100, tol: float = 1e-8) -> FirthResult:
    """Maximum de la vraisemblance pénalisée par le prior de Jeffreys (Firth, 1993), avec demi-pas."""
    X = X1.to_numpy(dtype=float)
    y = np.asarray(y, dtype=float)
    b = np.zeros(X.shape[1])

    def penalisee(beta):
        eta = X @ beta
        p = 1 / (1 + np.exp(-eta))
        w = p * (1 - p)
        info = X.T @ (X * w[:, None])
        sign, logdet = np.linalg.slogdet(info)
        ll = np.sum(y * eta - np.logaddexp(0, eta))
        return ll + 0.5 * logdet if sign > 0 else -np.inf, ll, p, w, info

    lp, ll, p, w, info = penalisee(b)
    converged = False
    for _ in range(max_iter):
        inv = np.linalg.pinv(info)
        h = w * np.einsum("ij,jk,ik->i", X, inv, X)
        score = X.T @ (y - p + h * (0.5 - p))
        pas = inv @ score
        nouveau = b + pas
        lp_n, ll_n, p_n, w_n, info_n = penalisee(nouveau)
        k = 0
        while lp_n < lp - 1e-12 and k < 30:  # demi-pas tant que la vraisemblance pénalisée diminue
            pas /= 2
            nouveau = b + pas
            lp_n, ll_n, p_n, w_n, info_n = penalisee(nouveau)
            k += 1
        b, lp, ll, p, w, info = nouveau, lp_n, ll_n, p_n, w_n, info_n
        if np.max(np.abs(pas)) < tol:
            converged = True
            break
    return FirthResult(b, np.linalg.pinv(info), X1, y, ll, converged)


def separation(res, y: np.ndarray) -> bool:
    """Indice de séparation (quasi-)complète : coefficients ou erreurs types démesurés, probabilités 0 ou 1."""
    try:
        params, bse = np.asarray(res.params, dtype=float), np.asarray(res.bse, dtype=float)
    except Exception:  # noqa: BLE001
        return True
    if not np.all(np.isfinite(params)) or not np.all(np.isfinite(bse)):
        return True
    if np.max(np.abs(params[1:])) > 10 or np.max(bse[1:]) > 30:
        return True
    p = np.asarray(res.fittedvalues, dtype=float)
    if np.nanmin(p) < 0 or np.nanmax(p) > 1:  # Logit de statsmodels : prédicteur linéaire, pas probabilités
        p = 1 / (1 + np.exp(-np.clip(p, -700, 700)))
    return bool(np.mean((p < 1e-8) | (p > 1 - 1e-8)) > 0.02)


# ---------------------------------------------------------------------------
# Validation interne par bootstrap
# ---------------------------------------------------------------------------

def _auc(y: np.ndarray, p: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else np.nan


def _logit_rapide(X: np.ndarray, y: np.ndarray, iters: int = 25) -> np.ndarray:
    """IRLS minimal avec légère régularisation (stabilité des rééchantillons)."""
    b = np.zeros(X.shape[1])
    for _ in range(iters):
        eta = np.clip(X @ b, -30, 30)
        p = 1 / (1 + np.exp(-eta))
        w = np.clip(p * (1 - p), 1e-9, None)
        info = X.T @ (X * w[:, None]) + 1e-6 * np.eye(X.shape[1])
        pas = np.linalg.solve(info, X.T @ (y - p))
        b += pas
        if np.max(np.abs(pas)) < 1e-8:
            break
    return b


def bootstrap_logistique(X1: pd.DataFrame, y: np.ndarray, B: int = 200) -> dict:
    """AUC apparente, optimisme moyen, AUC corrigée et pente de calibration corrigée (méthode de Harrell)."""
    X = X1.to_numpy(dtype=float)
    y = np.asarray(y, dtype=float)
    rng = np.random.default_rng(SEED)
    b0 = _logit_rapide(X, y)
    auc_app = _auc(y, X @ b0)
    opt, pentes = [], []
    n = len(y)
    for _ in range(B):
        idx = rng.integers(0, n, n)
        if len(np.unique(y[idx])) < 2:
            continue
        bb = _logit_rapide(X[idx], y[idx])
        opt.append(_auc(y[idx], X[idx] @ bb) - _auc(y, X @ bb))
        lp = X @ bb
        lp_c = np.column_stack([np.ones(n), lp])
        pentes.append(_logit_rapide(lp_c, y)[1])
    o = float(np.mean(opt)) if opt else np.nan
    return {"auc_apparente": auc_app, "optimisme": o, "auc_corrigee": auc_app - o,
            "pente_calibration": float(np.mean(pentes)) if pentes else np.nan, "B": len(opt)}


def bootstrap_lineaire(X1: pd.DataFrame, y: np.ndarray, B: int = 200) -> dict:
    X = X1.to_numpy(dtype=float)
    y = np.asarray(y, dtype=float)
    rng = np.random.default_rng(SEED)

    def r2(Xa, ya, b):
        res = ya - Xa @ b
        return 1 - np.sum(res ** 2) / np.sum((ya - ya.mean()) ** 2)

    b0 = np.linalg.lstsq(X, y, rcond=None)[0]
    app = r2(X, y, b0)
    opt = []
    for _ in range(B):
        idx = rng.integers(0, len(y), len(y))
        bb = np.linalg.lstsq(X[idx], y[idx], rcond=None)[0]
        opt.append(r2(X[idx], y[idx], bb) - r2(X, y, bb))
    o = float(np.mean(opt))
    return {"r2_apparent": app, "optimisme": o, "r2_corrige": app - o, "B": B}


# ---------------------------------------------------------------------------
# Témoin d'apprentissage automatique
# ---------------------------------------------------------------------------

def comparer_apprentissage(X: pd.DataFrame, y: np.ndarray, termes, binaire: bool, plis: int = 5,
                           groupes_obs: np.ndarray | None = None) -> dict:
    """Validation croisée du modèle explicatif et d'un gradient boosting ; importance par permutation groupée.

    Si les observations sont regroupées (grappes), les blocs de validation respectent les grappes : sinon le
    modèle flexible reconnaîtrait les grappes à travers les variables contextuelles et serait avantagé à tort.
    """
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
    from sklearn.linear_model import LinearRegression, LogisticRegression
    from sklearn.metrics import r2_score
    from sklearn.model_selection import GroupKFold, KFold, StratifiedGroupKFold, StratifiedKFold

    Xn = X.to_numpy(dtype=float)
    y = np.asarray(y, dtype=float)
    rng = np.random.default_rng(SEED)
    groupe = groupes_obs is not None and len(np.unique(groupes_obs)) >= 2 * plis
    if groupe:
        cv = (StratifiedGroupKFold(plis, shuffle=True, random_state=SEED) if binaire else GroupKFold(plis))
    else:
        cv = (StratifiedKFold(plis, shuffle=True, random_state=SEED) if binaire else
              KFold(plis, shuffle=True, random_state=SEED))
    groupes = {t.variable: [X.columns.get_loc(c) for c in t.columns if c in X.columns] for t in termes}
    sc_ref, sc_ml = [], []
    imp = {v: [] for v in groupes}
    for tr, te in cv.split(Xn, y if binaire else None, groups=groupes_obs if groupe else None):
        if binaire:
            ref = LogisticRegression(C=1e6, max_iter=2000).fit(Xn[tr], y[tr])
            ml = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                                l2_regularization=1.0, random_state=SEED).fit(Xn[tr], y[tr])
            score = lambda m, A, yt=y[te]: _auc(yt, m.predict_proba(A)[:, 1])  # noqa: E731
        else:
            ref = LinearRegression().fit(Xn[tr], y[tr])
            ml = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                               l2_regularization=1.0, random_state=SEED).fit(Xn[tr], y[tr])
            score = lambda m, A, yt=y[te]: float(r2_score(yt, m.predict(A)))  # noqa: E731
        base = score(ml, Xn[te])
        sc_ref.append(score(ref, Xn[te]))
        sc_ml.append(base)
        for v, cols in groupes.items():
            if not cols:
                continue
            Xp = Xn[te].copy()
            perm = rng.permutation(len(te))
            Xp[:, cols] = Xp[perm][:, cols]
            imp[v].append(base - score(ml, Xp))
    importance = {v: float(np.mean(x)) for v, x in imp.items() if x}
    return {"mesure": "AUC" if binaire else "R²", "reference": float(np.mean(sc_ref)),
            "reference_et": float(np.std(sc_ref)), "apprentissage": float(np.mean(sc_ml)),
            "apprentissage_et": float(np.std(sc_ml)), "importance": importance, "plis": plis, "groupe": groupe}


# ---------------------------------------------------------------------------
# Recherche d'effets non linéaires et d'interactions
# ---------------------------------------------------------------------------

def _spline_restreinte(x: np.ndarray, noeuds: int = 4) -> np.ndarray:
    """Termes non linéaires d'une spline cubique restreinte (Harrell, 2015), noeuds aux quantiles usuels."""
    q = {3: [10, 50, 90], 4: [5, 35, 65, 95], 5: [5, 27.5, 50, 72.5, 95]}[noeuds]
    k = np.unique(np.percentile(x, q))
    if len(k) < 3:
        return np.empty((len(x), 0))
    t_k, t_k1 = k[-1], k[-2]
    echelle = (t_k - k[0]) ** 2 or 1.0
    cols = []
    for t in k[:-2]:
        c = (np.clip(x - t, 0, None) ** 3 - np.clip(x - t_k1, 0, None) ** 3 * (t_k - t) / (t_k - t_k1)
             + np.clip(x - t_k, 0, None) ** 3 * (t_k1 - t) / (t_k - t_k1))
        cols.append(c / echelle)
    return np.column_stack(cols)


def _log_vraisemblance(X: np.ndarray, y: np.ndarray, binaire: bool) -> float:
    import statsmodels.api as sm
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if binaire:
            return float(sm.GLM(y, X, family=sm.families.Binomial()).fit().llf)
        return float(sm.OLS(y, X).fit().llf)


def explorer_specification(X: pd.DataFrame, y: np.ndarray, termes, binaire: bool,
                           importance: dict[str, float] | None = None, max_paires: int = 6) -> list[dict]:
    """Tests du rapport de vraisemblance : non-linéarité des variables quantitatives (spline cubique restreinte)
    et interactions entre les variables les plus importantes. Probabilités critiques corrigées par Holm."""
    from statsmodels.stats.multitest import multipletests
    Xb = np.column_stack([np.ones(len(X)), X.to_numpy(dtype=float)])
    y = np.asarray(y, dtype=float)
    ll0 = _log_vraisemblance(Xb, y, binaire)
    cols = {t.variable: [X.columns.get_loc(c) for c in t.columns if c in X.columns] for t in termes}
    out: list[dict] = []
    for t in termes:
        c = cols.get(t.variable, [])
        if len(c) != 1 or t.kind not in ("continue", "comptage"):
            continue
        x = X.iloc[:, c[0]].to_numpy(dtype=float)
        if len(np.unique(x)) < 10:
            continue
        S = _spline_restreinte(x)
        if S.shape[1] == 0:
            continue
        try:
            ll1 = _log_vraisemblance(np.column_stack([Xb, S]), y, binaire)
        except Exception:  # noqa: BLE001, S112  # nosec B112 - test non estimable : ignoré
            continue
        lr = max(0.0, 2 * (ll1 - ll0))
        out.append({"type": "non-linéarité", "variables": (t.variable,), "chi2": lr, "ddl": S.shape[1],
                    "p": float(stats.chi2.sf(lr, S.shape[1]))})
    ordre = sorted(cols, key=lambda v: -(importance or {}).get(v, 0.0))
    candidats = [v for v in ordre if cols[v]][:4]
    paires = [(a, b) for i, a in enumerate(candidats) for b in candidats[i + 1:]][:max_paires]
    for a, b in paires:
        A, B = X.iloc[:, cols[a]].to_numpy(dtype=float), X.iloc[:, cols[b]].to_numpy(dtype=float)
        inter = np.column_stack([A[:, i] * B[:, j] for i in range(A.shape[1]) for j in range(B.shape[1])])
        inter = inter[:, inter.std(axis=0) > 0]
        if inter.shape[1] == 0 or inter.shape[1] > 12:
            continue
        try:
            ll1 = _log_vraisemblance(np.column_stack([Xb, inter]), y, binaire)
        except Exception:  # noqa: BLE001, S112  # nosec B112 - test non estimable : ignoré
            continue
        lr = max(0.0, 2 * (ll1 - ll0))
        out.append({"type": "interaction", "variables": (a, b), "chi2": lr, "ddl": inter.shape[1],
                    "p": float(stats.chi2.sf(lr, inter.shape[1]))})
    if out:
        p_holm = multipletests([o["p"] for o in out], method="holm")[1]
        for o, ph in zip(out, p_holm, strict=True):
            o["p_holm"] = float(ph)
    return out


# ---------------------------------------------------------------------------
# Bilan de fiabilité
# ---------------------------------------------------------------------------

OBJETS = {"Observations analysées": "la taille de l'échantillon analysé",
          "Observations exclues (valeurs manquantes)": "la part d'observations exclues pour valeurs manquantes",
          "Événements par paramètre estimé": "le nombre d'événements par paramètre estimé",
          "Multicolinéarité (VIF maximal)": "la multicolinéarité entre variables explicatives",
          "Séparation des données": "la séparation des données",
          "Ajustement (Hosmer-Lemeshow)": "l'ajustement du modèle",
          "Sur-ajustement (optimisme de l'AUC)": "le sur-ajustement du modèle",
          "Sur-ajustement (optimisme du R²)": "le sur-ajustement du modèle",
          "Écart avec un modèle d'apprentissage automatique": "l'écart avec le modèle d'apprentissage automatique",
          "Spécification (non-linéarités, interactions)": "la forme du modèle (effets non linéaires ou "
                                                          "interactions)",
          "Nombre de contextes (multi-niveaux)": "le nombre de contextes du modèle multi-niveaux"}


@dataclass
class Critere:
    nom: str
    valeur: str
    repere: str
    etat: str  # satisfaisant | à surveiller | insuffisant
    explication: str


def bilan(ds, sections: dict[str, Section], outcome: str | None, event: str | None,
          cluster: str | None = None) -> Section | None:
    """Section « Fiabilité des résultats » : validation interne, témoin d'apprentissage automatique et bilan."""
    mv = sections.get("multivarie")
    if mv is None or mv.extra.get("fit") is None:
        return None
    fit, dsg = mv.extra["fit"], mv.extra["design"]
    R = Redac(ds, outcome, event)
    sec = Section(key="fiabilite", title="Fiabilité des résultats", level=2)
    sec.refs |= {"harrell1996", "steyerberg2001", "friedman2001", "breiman2001", "pedregosa2011"}
    crit: list[Critere] = []
    f = mv.facts
    n = int(f.get("modele.n", dsg.n_used))
    crit.append(Critere("Observations analysées", fmt.integer(n), "au moins 100",
                        "satisfaisant" if n >= 200 else "à surveiller" if n >= 100 else "insuffisant",
                        "Plus l'échantillon est grand, plus les estimations sont précises."))
    pex = float(f.get("modele.pct_exclus", 0))
    crit.append(Critere("Observations exclues (valeurs manquantes)", f"{fmt.num(pex, 1)} %", "moins de 10 %",
                        "satisfaisant" if pex < 10 else "à surveiller" if pex < 25 else "insuffisant",
                        "Une forte exclusion peut biaiser les résultats si les données manquent de façon non "
                        "aléatoire."))
    binaire = fit.kind == "logistique"
    X1 = pd.concat([pd.Series(1.0, index=dsg.X.index, name="const"), dsg.X.astype(float)], axis=1)
    y = dsg.y.to_numpy(dtype=float)
    if binaire:
        epv = float(f.get("modele.epv", np.nan))
        crit.append(Critere("Événements par paramètre estimé", fmt.num(epv, 1), "au moins 10 (Peduzzi et al., 1996)",
                            "satisfaisant" if epv >= 10 else "à surveiller" if epv >= 5 else "insuffisant",
                            "Trop peu d'événements par coefficient rend les estimations instables."))
        sec.refs.add("peduzzi1996")
    vif = float(f.get("modele.vif_max", np.nan))
    if np.isfinite(vif):
        crit.append(Critere("Multicolinéarité (VIF maximal)", fmt.num(vif), "moins de 5",
                            "satisfaisant" if vif < 5 else "à surveiller" if vif < 10 else "insuffisant",
                            "Des variables trop liées entre elles brouillent la part de chacune."))
    if getattr(fit, "methode", "") == "firth":
        crit.append(Critere("Séparation des données", "détectée, corrigée", "absente", "à surveiller",
                            "Certaines modalités prédisent parfaitement l'événement ; la méthode de Firth a été "
                            "utilisée pour obtenir des estimations finies."))
    elif binaire:
        crit.append(Critere("Séparation des données", "absente", "absente", "satisfaisant",
                            "Aucune modalité ne prédit l'événement à elle seule."))
    if binaire and "modele.hl_p" in f:
        hl = float(f["modele.hl_p"])
        crit.append(Critere("Ajustement (Hosmer-Lemeshow)", fmt.pval(hl), "probabilité critique ≥ 0,05",
                            "satisfaisant" if hl >= 0.05 else "à surveiller",
                            "Compare les fréquences observées et prédites par le modèle."))

    # Validation interne
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            bt = bootstrap_logistique(X1, y) if binaire else bootstrap_lineaire(X1, y) \
                if fit.kind == "lineaire" else None
    except Exception:  # noqa: BLE001
        bt = None
    if bt:
        sec.facts.update({f"fiab.{k}": v for k, v in bt.items()})
        if binaire:
            opt = bt["optimisme"]
            crit.append(Critere("Sur-ajustement (optimisme de l'AUC)", fmt.num(opt, 3), "moins de 0,03",
                                "satisfaisant" if opt < 0.03 else "à surveiller" if opt < 0.06 else "insuffisant",
                                "Écart entre la performance sur les données d'estimation et sur de nouvelles "
                                "données simulées par rééchantillonnage."))
            auc_c = bt["auc_corrigee"]
            crit.append(Critere("Pouvoir discriminant (AUC corrigée)", fmt.num(auc_c, 3), "0,70 et plus : élevé",
                                "élevé" if auc_c >= 0.7 else "modeste" if auc_c >= 0.6 else "faible",
                                "Capacité du modèle à distinguer les deux groupes (0,5 correspond au hasard). Un "
                                "pouvoir modeste est fréquent en sciences sociales : il n'invalide pas les "
                                "associations, mais rappelle que d'autres facteurs non mesurés interviennent."))
            txt_bt = (f"La validation interne par bootstrap ({nombre(bt['B'], 'rééchantillonnages')}) donne une aire "
                      f"sous la courbe ROC corrigée de l'optimisme de {fmt.num(auc_c, 3)}, contre "
                      f"{fmt.num(bt['auc_apparente'], 3)} sur les données d'estimation. ")
            txt_bt += ("Cet écart très faible montre que le modèle n'est pas sur-ajusté : ses résultats devraient se "
                       "retrouver sur un autre échantillon de la même population." if opt < 0.03 else
                       "Cet écart signale un certain sur-ajustement : les associations les plus faibles doivent être "
                       "interprétées avec prudence.")
            txt_bt += (f" La pente de calibration corrigée s'établit à {fmt.num(bt['pente_calibration'], 2)} ; une "
                       "valeur proche de 1 indique des probabilités prédites bien calibrées.")
        else:
            opt = bt["optimisme"]
            crit.append(Critere("Sur-ajustement (optimisme du R²)", fmt.num(opt, 3), "moins de 0,03",
                                "satisfaisant" if opt < 0.03 else "à surveiller" if opt < 0.06 else "insuffisant",
                                "Écart entre la part de variance expliquée sur les données et sur des "
                                "rééchantillons."))
            txt_bt = (f"La validation interne par bootstrap ({nombre(bt['B'], 'rééchantillonnages')}) donne un R² "
                      f"corrigé de l'optimisme de {fmt.num(bt['r2_corrige'], 3)}, contre {fmt.num(bt['r2_apparent'], 3)} "
                      "sur les données d'estimation.")
        sec.paragraphs.append(txt_bt)

    # Témoin d'apprentissage automatique
    ml = None
    if fit.kind in ("logistique", "lineaire") and len(y) >= 100:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                grp = (ds.df.loc[dsg.X.index, cluster].astype(str).to_numpy()
                       if cluster and cluster in ds.df.columns else None)
                ml = comparer_apprentissage(dsg.X.astype(float), y, dsg.terms, binaire, groupes_obs=grp)
        except Exception:  # noqa: BLE001
            ml = None
    if ml:
        ecart = ml["apprentissage"] - ml["reference"]
        sec.facts.update({"fiab.ml_reference": ml["reference"], "fiab.ml_apprentissage": ml["apprentissage"],
                          "fiab.ml_ecart": ecart})
        crit.append(Critere("Écart avec un modèle d'apprentissage automatique",
                            f"{'+' if ecart >= 0 else ''}{fmt.num(ecart, 3)}", "moins de 0,03",
                            "satisfaisant" if ecart < 0.03 else "à surveiller" if ecart < 0.06 else "insuffisant",
                            "Si un modèle flexible prédit nettement mieux, des effets non linéaires ou des "
                            "interactions ont pu échapper au modèle."))
        top = sorted(ml["importance"].items(), key=lambda kv: -kv[1])
        top_noms = [R.v(v) for v, imp in top[:3] if imp > 0]
        mesure = ml["mesure"]
        txt = (f"Pour vérifier que le modèle ne passe pas à côté d'une structure plus complexe, nous l'avons comparé "
               f"à un modèle d'apprentissage automatique (gradient boosting), évalué comme lui par validation croisée "
               f"en {nombre(ml['plis'], 'blocs')}. Le modèle explicatif obtient un{'e' if mesure == 'AUC' else ''} "
               f"{mesure} moyen{'ne' if mesure == 'AUC' else ''} de {fmt.num(ml['reference'], 3)}, contre "
               f"{fmt.num(ml['apprentissage'], 3)} pour le modèle d'apprentissage automatique. ")
        txt += ("Le modèle explicatif fait donc au moins aussi bien : ses conclusions ne sont pas fragilisées par des "
                "effets non linéaires ou des interactions omises." if ecart <= 0 else
                "L'écart étant faible, le modèle explicatif capte l'essentiel de l'information contenue dans les "
                "variables : ses conclusions ne sont pas fragilisées par des effets non linéaires ou des interactions "
                "omises." if ecart < 0.03 else
                "L'écart est notable : des effets non linéaires ou des interactions entre variables pourraient exister. "
                "Il serait utile de les explorer, par exemple en introduisant des interactions ou des catégories plus "
                "fines.")
        if top_noms:
            txt += (f" Par ailleurs, les variables les plus utiles à la prédiction sont {enumeration(top_noms)}, ce qui "
                    "permet de recouper les résultats du modèle explicatif.")
        sec.paragraphs.append(txt)
        rows = [{"Modèle": "Modèle explicatif (" + ("logistique" if binaire else "linéaire") + ")",
                 f"{mesure} en validation croisée": f"{fmt.num(ml['reference'], 3)} (écart type {fmt.num(ml['reference_et'], 3)})"},
                {"Modèle": "Gradient boosting (apprentissage automatique)",
                 f"{mesure} en validation croisée": f"{fmt.num(ml['apprentissage'], 3)} (écart type {fmt.num(ml['apprentissage_et'], 3)})"}]
        sec.tables.append(Table(title="Comparaison du modèle explicatif avec un modèle d'apprentissage automatique",
                                data=pd.DataFrame(rows),
                                note=f"Validation croisée en {ml['plis']} blocs"
                     + (" formés de grappes entières" if ml.get("groupe") else "")
                     + f", graine aléatoire fixée à {SEED}. "
                                     "Le modèle d'apprentissage automatique sert de témoin : il n'est pas interprété."))
        imp_rows = [{"Variable": ds.variables[v].label if v in ds.variables else v,
                     "Perte de performance si la variable est brouillée": fmt.num(i, 3)} for v, i in top[:8]]
        if imp_rows:
            sec.tables.append(Table(title="Importance des variables dans le modèle d'apprentissage automatique",
                                    data=pd.DataFrame(imp_rows),
                                    note="Importance par permutation (Breiman, 2001) : baisse moyenne de la "
                                         f"performance ({mesure}) lorsque les valeurs de la variable sont mélangées."))

    # Recherche d'effets non linéaires et d'interactions
    try:
        spec_tests = explorer_specification(dsg.X.astype(float), y, dsg.terms, binaire,
                                            ml["importance"] if ml else None) if fit.kind in ("logistique",
                                                                                              "lineaire") else []
    except Exception:  # noqa: BLE001
        spec_tests = []
    if spec_tests:
        sec.refs |= {"harrell2015", "holm1979"}
        sec.extra["specification"] = spec_tests
        nomv = lambda v: ds.variables[v].label if v in ds.variables else v  # noqa: E731
        signif = [o for o in spec_tests if o["p_holm"] < 0.05]
        crit.append(Critere("Spécification (non-linéarités, interactions)",
                            f"{len(signif)} sur {len(spec_tests)} test{'s' if len(spec_tests) > 1 else ''}",
                            "aucun effet omis significatif",
                            "satisfaisant" if not signif else "à surveiller",
                            "Vérifie que le modèle ne néglige ni une relation courbe (par exemple un effet de "
                            "l'âge qui monte puis redescend) ni un effet qui dépend d'une autre caractéristique."))
        if signif:
            desc = []
            for o in signif:
                if o["type"] == "non-linéarité":
                    desc.append(f"un effet non linéaire de {R.v(o['variables'][0])}")
                else:
                    desc.append(f"une interaction entre {R.v(o['variables'][0])} et {R.v(o['variables'][1])}")
            txt = (f"La recherche systématique d'effets omis ({nombre(len(spec_tests), 'tests')} du rapport de "
                   "vraisemblance, probabilités critiques corrigées par la méthode de Holm) met en évidence "
                   f"{enumeration(desc)}. Il serait utile d'en tenir compte, par exemple en découpant la variable "
                   "quantitative en classes ou en introduisant le terme d'interaction correspondant, puis de "
                   "vérifier que les conclusions principales restent inchangées.")
        else:
            txt = (f"La recherche systématique d'effets omis ({nombre(len(spec_tests), 'tests')} du rapport de "
                   "vraisemblance portant sur les relations non linéaires des variables quantitatives et sur les "
                   "interactions entre les variables les plus importantes, probabilités critiques corrigées par la "
                   "méthode de Holm) ne met en évidence aucun effet significatif : la forme retenue pour le modèle "
                   "apparaît adéquate.")
        sec.paragraphs.append(txt)
        sec.tables.append(Table(
            title="Recherche d'effets non linéaires et d'interactions",
            data=pd.DataFrame([{"Effet testé": ("Non-linéarité de " + nomv(o["variables"][0])
                                                if o["type"] == "non-linéarité" else
                                                f"Interaction {nomv(o['variables'][0])} × {nomv(o['variables'][1])}"),
                                "Khi-deux (rapport de vraisemblance)": fmt.num(o["chi2"], 2), "ddl": str(o["ddl"]),
                                "p": fmt.pval(o["p"]), "p corrigée (Holm)": fmt.pval(o["p_holm"])}
                               for o in spec_tests]),
            note="Non-linéarité : spline cubique restreinte à quatre noeuds (Harrell, 2015). Interactions : paires "
                 "formées parmi les quatre variables les plus importantes. Chaque test compare le modèle principal "
                 "au même modèle augmenté du terme testé."))

    mn = sections.get("multiniveau")
    if mn is not None and "mn.contextes" in mn.facts:
        J = int(mn.facts["mn.contextes"])
        crit.append(Critere("Nombre de contextes (multi-niveaux)", fmt.integer(J), "au moins 30 (Maas et Hox, 2005)",
                            "satisfaisant" if J >= 30 else "à surveiller" if J >= 10 else "insuffisant",
                            "Il faut assez de contextes pour estimer la variance entre eux."))
        sec.refs.add("maas2005")

    # Appréciation globale
    nb_ins = sum(c.etat == "insuffisant" for c in crit)
    nb_sur = sum(c.etat == "à surveiller" for c in crit)
    if nb_ins:
        globale = "à interpréter avec prudence"
    elif nb_sur >= 2:
        globale = "satisfaisante, avec des points de vigilance"
    elif nb_sur == 1:
        globale = "bonne, avec un point de vigilance"
    else:
        globale = "élevée"
    sec.facts["fiab.nb_insuffisant"] = nb_ins
    sec.facts["fiab.nb_a_surveiller"] = nb_sur
    sec.extra["globale"] = globale
    sec.extra["criteres"] = crit
    vigilance = [OBJETS.get(c.nom, c.nom[:1].lower() + c.nom[1:]) for c in crit
                 if c.etat in ("à surveiller", "insuffisant")]
    chapeau = (f"Avant de conclure, nous avons évalué la fiabilité des résultats à l'aide de "
               f"{nombre(len(crit), 'critères')} présentés dans le tableau ci-dessous. Dans l'ensemble, la fiabilité "
               f"est jugée {globale}.")
    if vigilance:
        chapeau += f" Les points à surveiller concernent {enumeration(vigilance)}."
    sec.paragraphs.insert(0, chapeau)
    sec.tables.insert(0, Table(title="Bilan de fiabilité des résultats",
                               data=pd.DataFrame([{"Critère": c.nom, "Valeur": c.valeur, "Repère": c.repere,
                                                   "Appréciation": c.etat, "En clair": c.explication} for c in crit]),
                               note="Appréciation automatique selon des repères usuels de la littérature "
                                    "méthodologique ; elle ne remplace pas le jugement de l'auteur."))
    sec.key_points.append(f"Dans l'ensemble, la fiabilité des résultats est jugée {globale}.")
    sec.method_notes.append(
        "La fiabilité des résultats est appréciée par une validation interne par bootstrap (200 rééchantillonnages), "
        "qui corrige les indicateurs de performance de leur optimisme (Harrell, Lee et Mark, 1996 ; Steyerberg et "
        "al., 2001), et par la comparaison, en validation croisée, du modèle explicatif avec un modèle "
        "d'apprentissage automatique de type gradient boosting (Friedman, 2001 ; Pedregosa et al., 2011). Un bilan "
        "synthétise ces indicateurs et les repères usuels de taille d'échantillon, de multicolinéarité et "
        "d'ajustement.")
    return sec


__all__ = ["firth_logit", "separation", "bootstrap_logistique", "bootstrap_lineaire", "comparer_apprentissage",
           "bilan", "FirthResult"]
