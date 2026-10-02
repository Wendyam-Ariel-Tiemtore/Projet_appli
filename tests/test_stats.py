"""Validation des procédures statistiques, y compris sur données simulées à paramètres connus."""

import numpy as np
import pandas as pd
from scipy import stats

from analyste.stats import bivariate, descriptive, models, multilevel, multivariate
from analyste.stats.io import infer_variable


def test_wilson():
    lo, hi = descriptive.wilson_ci(0, 10)
    assert lo == 0 and 0.27 < hi < 0.28  # valeur de référence : 0,2775
    lo, hi = descriptive.wilson_ci(50, 100)
    assert abs(lo - 0.4038) < 1e-3 and abs(hi - 0.5962) < 1e-3


def test_choix_fisher_petits_effectifs():
    x = pd.Series(pd.Categorical(["a"] * 6 + ["b"] * 6), name="x")
    y = pd.Series(pd.Categorical(["o", "o", "o", "o", "o", "n", "n", "n", "n", "n", "n", "o"]))
    r = bivariate.cat_cat(x, y, False, False)
    assert r.test == "Exact de Fisher"
    assert abs(r.p - stats.fisher_exact(pd.crosstab(x, y))[1]) < 1e-12


def test_choix_welch_ou_mann_whitney():
    rng = np.random.default_rng(1)
    g = pd.Series(pd.Categorical(["a"] * 60 + ["b"] * 60))
    normal = pd.Series(np.r_[rng.normal(0, 1, 60), rng.normal(0.5, 2, 60)])
    assert bivariate.num_by_group(normal, g, "v").test == "t de Welch"
    asym = pd.Series(np.r_[rng.exponential(1, 15) ** 3, rng.exponential(2, 15) ** 3])
    g2 = pd.Series(pd.Categorical(["a"] * 15 + ["b"] * 15))
    assert bivariate.num_by_group(asym, g2, "v").test == "U de Mann-Whitney"


def test_welch_anova_reference():
    rng = np.random.default_rng(3)
    groups = [rng.normal(0, 1, 30), rng.normal(0.3, 2, 40), rng.normal(0.8, 3, 50)]
    f, df1, df2, p = bivariate.welch_anova(groups)
    from statsmodels.stats.oneway import anova_oneway
    ref = anova_oneway(groups, use_var="unequal")
    assert abs(f - ref.statistic) < 1e-8 and abs(p - ref.pvalue) < 1e-8


def test_bivarie_fdr(dataset, tmp_path):
    sec = bivariate.bivariate(dataset, "contraception_moderne",
                              ["instruction", "milieu", "religion", "age", "parite"], tmp_path)
    tests = sec.extra["tests"]
    assert all(t.p_fdr >= t.p - 1e-12 for t in tests)
    assert any(t.test.startswith("d de Somers") for t in tests)
    assert sec.facts["bivarie.nb_testees"] == 5


def test_logistique_coherente_avec_statsmodels(dataset, tmp_path):
    sec = models.explain(dataset, "contraception_moderne", ["instruction", "milieu", "age"], tmp_path)
    fit = sec.extra["fit"]
    tab = fit.table()
    assert (tab["lo_e"] <= tab["est"]).all() and (tab["est"] <= tab["hi_e"]).all()
    assert 0 < sec.facts["modele.nagelkerke"] < 1
    assert 0.5 < sec.facts["modele.auc"] < 1


def test_brant_cotes_proportionnelles_respectees():
    rng = np.random.default_rng(5)
    n = 3000
    x = rng.normal(size=n)
    lat = 0.8 * x + rng.logistic(size=n)
    y = np.digitize(lat, [-1, 0.5, 2])
    w, dof, p = models.brant_test(y, pd.DataFrame({"x": x}))
    assert dof == 2 and p > 0.01


def test_glmm_logistique_retrouve_les_parametres():
    """Logistique multi-niveaux par quadrature adaptative : paramètres simulés retrouvés."""
    rng = np.random.default_rng(11)
    J, m = 150, 25
    g = np.repeat(np.arange(J), m)
    u = rng.normal(0, 0.9, J)
    x = rng.normal(size=J * m)
    z = np.repeat(rng.binomial(1, 0.5, J), m)
    eta = -0.5 + 0.8 * x + 0.6 * z + u[g]
    y = rng.binomial(1, 1 / (1 + np.exp(-eta)))
    X = np.column_stack([np.ones(len(y)), x, z])
    res = multilevel.RandomInterceptLogit(y, X, g).fit(["const", "x", "z"])
    assert abs(res.beta[1] - 0.8) < 3 * res.se[1]
    assert abs(res.beta[2] - 0.6) < 3 * res.se[2]
    assert 0.5 < res.sigma2 < 1.2  # vraie valeur 0,81
    lr, p = res.lr_var
    assert p < 1e-6
    assert 0 < res.vpc < 1 and res.mor > 1


def test_glmm_variance_nulle_detectee():
    rng = np.random.default_rng(12)
    J, m = 80, 20
    g = np.repeat(np.arange(J), m)
    x = rng.normal(size=J * m)
    y = rng.binomial(1, 1 / (1 + np.exp(-(0.2 + 0.5 * x))))
    res = multilevel.RandomInterceptLogit(y, np.column_stack([np.ones(len(y)), x]), g).fit(["const", "x"])
    assert res.sigma2 < 0.15
    assert res.lr_var[1] > 0.01


def test_multiniveau_lineaire(dataset, tmp_path):
    dataset.df["q"] = dataset.df["quintile_bien_etre"].astype(float)
    dataset.variables["q"] = infer_variable(dataset.df["q"], "q", "quintile")
    dataset.variables["q"].kind = "continue"
    sec = multilevel.multilevel(dataset, "imc", ["age", "q", "milieu"], "grappe", tmp_path)
    assert sec.facts["mn.M0.lr_p"] < 0.001
    assert sec.facts["mn.M2.var_ctx"] < sec.facts["mn.M0.var_ctx"]
    assert 0 < sec.facts["mn.M0.vpc"] < 100


def test_acp_diagnostics(tmp_path):
    from analyste.stats.io import Dataset
    rng = np.random.default_rng(2)
    f = rng.normal(size=500)
    df = pd.DataFrame({f"v{i}": f + rng.normal(scale=0.6, size=500) for i in range(5)})
    ds = Dataset(df=df, variables={c: infer_variable(df[c], c, c) for c in df}, source_format="csv")
    sec = multivariate.pca(ds, list(df.columns), tmp_path)
    assert sec.facts["acp.kmo"] > 0.8 and sec.facts["acp.retenues"] == 1
    noise = pd.DataFrame(rng.normal(size=(500, 5)), columns=[f"n{i}" for i in range(5)])
    ds2 = Dataset(df=noise, variables={c: infer_variable(noise[c], c, c) for c in noise}, source_format="csv")
    sec2 = multivariate.pca(ds2, list(noise.columns), tmp_path)
    assert sec2.facts["acp.retenues"] == 0  # pas de structure : résultat rapporté, pas d'interprétation


def test_cronbach():
    rng = np.random.default_rng(4)
    t = rng.normal(size=400)
    items = pd.DataFrame({f"i{k}": t + rng.normal(scale=0.5, size=400) for k in range(4)})
    assert multivariate.cronbach_alpha(items) > 0.85
