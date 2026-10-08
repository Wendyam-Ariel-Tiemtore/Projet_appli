"""Fiabilité : Firth, séparation, bootstrap, témoin d'apprentissage, hypothèses et lecture en langage simple."""

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from analyste.stats import bivariate, fiabilite, hypotheses, models
from analyste.writing.lexique import LEXIQUE, lecture_simple, lexique_utilise, simplifier

EXPL = ["instruction", "milieu", "exposition_medias", "age"]


@pytest.fixture()
def sections(dataset, tmp_path):
    return {"bivarie": bivariate.bivariate(dataset, "contraception_moderne", EXPL, tmp_path),
            "multivarie": models.explain(dataset, "contraception_moderne", EXPL, tmp_path)}


# --- Firth --------------------------------------------------------------------------------------------------

def test_firth_egal_correction_de_haldane_sur_un_tableau_2x2():
    """Avec une seule variable binaire, l'estimateur de Firth revient à ajouter 0,5 à chaque case."""
    a, b, c, d = 12, 3, 5, 20  # exposés : 12 événements, 3 non ; non exposés : 5 et 20
    x = np.r_[np.ones(a + b), np.zeros(c + d)]
    y = np.r_[np.ones(a), np.zeros(b), np.ones(c), np.zeros(d)]
    X1 = sm.add_constant(pd.DataFrame({"x": x}))
    res = fiabilite.firth_logit(y, X1)
    attendu = np.log((a + 0.5) * (d + 0.5) / ((b + 0.5) * (c + 0.5)))
    assert res.converged
    assert abs(res.params["x"] - attendu) < 1e-6


def test_firth_donne_des_estimations_finies_en_cas_de_separation():
    rng = np.random.default_rng(1)
    x = rng.normal(size=120)
    g = (rng.random(120) < 0.15).astype(float)
    y = (x + rng.normal(scale=0.8, size=120) > 0).astype(float)
    y[g == 1] = 1.0  # séparation quasi complète : tous les membres du groupe g connaissent l'événement
    X = pd.DataFrame({"x": x, "g": g})
    fit = models.fit_simple("logistique", y, X)
    assert fit.methode == "firth"
    t = fit.table()
    assert np.isfinite(t["est"]).all() and np.isfinite(t["hi_e"]).all()
    assert 1 < float(t.loc[t.index.str.contains("g"), "est"].iloc[0]) < 1e4


def test_firth_proche_du_maximum_de_vraisemblance_sans_separation():
    rng = np.random.default_rng(3)
    x = rng.normal(size=2000)
    y = (rng.random(2000) < 1 / (1 + np.exp(-(0.3 + 0.8 * x)))).astype(float)
    X1 = sm.add_constant(pd.DataFrame({"x": x}))
    mle = sm.Logit(y, X1).fit(disp=0)
    assert not fiabilite.separation(mle, y)
    f = fiabilite.firth_logit(y, X1)
    assert np.max(np.abs(f.params.to_numpy() - mle.params.to_numpy())) < 0.01


# --- Bilan de fiabilité -------------------------------------------------------------------------------------

def test_bilan_de_fiabilite(dataset, sections):
    sec = fiabilite.bilan(dataset, sections, "contraception_moderne", None)
    assert sec is not None and sec.key == "fiabilite"
    noms = [c.nom for c in sec.extra["criteres"]]
    assert len(noms) >= 6 and len(set(noms)) == len(noms)
    assert sec.extra["globale"].split(",")[0] in {"élevée", "bonne", "satisfaisante", "à interpréter avec prudence"}
    assert any("Bilan de fiabilité" in t.title for t in sec.tables)
    for c in sec.extra["criteres"]:
        assert c.explication and c.etat


def test_bootstrap_optimisme_positif_et_auc_corrigee_plausible(dataset, sections):
    fit = sections["multivarie"].extra["fit"]
    r = fiabilite.bootstrap_logistique(sm.add_constant(fit.X, has_constant="add"), np.asarray(fit.y, dtype=float), B=60)
    assert 0.5 < r["auc_corrigee"] <= r["auc_apparente"] + 0.01 < 1.01


# --- Hypothèses ---------------------------------------------------------------------------------------------

def test_deviner_variable_et_sens(dataset):
    d = hypotheses.deviner("Le niveau d'instruction augmente l'utilisation de la contraception", dataset, EXPL,
                           "contraception_moderne")
    assert d == {"variable": "instruction", "sens": "positif"}
    d = hypotheses.deviner("Une phrase sans rapport avec les variables", dataset, EXPL, "contraception_moderne")
    assert d["variable"] is None


def test_verifier_hypotheses(dataset, sections):
    hyps = [{"texte": "L'instruction favorise l'utilisation", "variable": "instruction", "sens": "positif"},
            {"texte": "L'instruction réduit l'utilisation", "variable": "instruction", "sens": "negatif"},
            {"texte": "Une hypothèse non rattachée", "variable": None, "sens": "association"}]
    sec = hypotheses.verifier(hyps, dataset, sections, "contraception_moderne", None)
    v = [x.verdict for x in sec.extra["verdicts"]]
    assert v[0] in ("confirmée", "partiellement confirmée")
    assert v[1] == "infirmée"
    assert v[2] == "non vérifiable"
    assert any("Vérification des hypothèses" in t.title for t in sec.tables)


# --- Langage simple -----------------------------------------------------------------------------------------

def test_simplifier_retire_les_parentheses_techniques():
    s = simplifier("Les femmes instruites ont deux fois plus de chances (OR = 2,1 ; IC à 95 % : 1,4 à 3,0 ; "
                   "p < 0,001) d'utiliser la contraception.")
    assert s == "Les femmes instruites ont deux fois plus de chances d'utiliser la contraception."
    assert simplifier("Le milieu (urbain ou rural) compte.") == "Le milieu (urbain ou rural) compte."


def test_lexique_et_lecture_simple():
    notions = dict(lexique_utilise("Une régression logistique donne un rapport de cotes ; p < 0,05."))
    assert {"Régression logistique", "Rapport de cotes (OR)", "Probabilité critique (p)"} <= set(notions)
    assert all(d.endswith(".") for _, (_, d) in LEXIQUE.items())
    paras = lecture_simple(["A (p = 0,01)."], "bonne", 1500)
    assert "1 500" in paras[0] and "fiabilité bonne" in paras[-1]
    assert all("—" not in p and "–" not in p for p in paras)


def test_recherche_non_linearite_et_interaction():
    from analyste.stats.design import Term
    rng = np.random.default_rng(11)
    n = 3000
    age = rng.uniform(15, 49, n)
    a = (rng.random(n) < 0.5).astype(float)
    b = (rng.random(n) < 0.5).astype(float)
    eta = -0.5 - 0.004 * (age - 32) ** 2 + 0.2 * a + 0.2 * b + 1.2 * a * b
    y = (rng.random(n) < 1 / (1 + np.exp(-eta))).astype(float)
    X = pd.DataFrame({"age": age, "a": a, "b": b})
    termes = [Term("age", "Âge", "continue", ["age"]), Term("a", "A", "binaire", ["a"]),
              Term("b", "B", "binaire", ["b"])]
    res = fiabilite.explorer_specification(X, y, termes, True, {"a": 0.03, "b": 0.02, "age": 0.01})
    signif = {(o["type"], o["variables"]) for o in res if o["p_holm"] < 0.05}
    assert ("non-linéarité", ("age",)) in signif
    assert ("interaction", ("a", "b")) in signif
    # Sans effet omis : aucune détection
    y0 = (rng.random(n) < 1 / (1 + np.exp(-(0.02 * (age - 32) + 0.3 * a)))).astype(float)
    res0 = fiabilite.explorer_specification(X, y0, termes, True)
    assert all(o["p_holm"] >= 0.05 for o in res0)
