"""Vérification des hypothèses de l'auteur à partir des résultats bivariés et ajustés.

Chaque hypothèse porte sur une variable explicative et un sens attendu :
- « positif » : la modalité supérieure (ou la présence, ou une valeur plus élevée) va de pair avec une valeur plus
  élevée de la variable dépendante (ou des chances plus élevées de l'événement) ;
- « negatif » : l'inverse ;
- « association » : une association est attendue sans sens précis.

Verdicts possibles : confirmée, partiellement confirmée, non confirmée, infirmée (association significative de
sens contraire), non vérifiable (variable absente des analyses). Le verdict repose d'abord sur le modèle ajusté
(multi-niveaux s'il existe, sinon multivarié), l'analyse bivariée servant de complément.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..writing.phrases import Redac, accord, est
from ..writing.style import a, guillemets, majuscule, nombre, ordinal
from . import seuil
from .design import POSITIVE
from .results import Section, Table

SENS = {"positif": "positif", "negatif": "négatif", "association": "association sans sens précisé"}
MOTS_POSITIFS = ("positivement", "augmente", "accroit", "accroît", "favorise", "plus eleve", "plus élevé",
                 "plus elevee", "plus élevée", "davantage", "renforce", "ameliore", "améliore", "hausse")
MOTS_NEGATIFS = ("negativement", "négativement", "diminue", "reduit", "réduit", "moins", "baisse", "freine",
                 "defavorise", "défavorise", "limite", "entrave")
VIDES = {"les", "des", "une", "dans", "avec", "pour", "par", "sur", "est", "sont", "plus", "moins", "que", "qui",
         "aux", "son", "ses", "leur", "leurs", "associe", "associee", "associes", "associees", "positivement",
         "negativement", "variable", "niveau", "chez", "entre", "elle", "ils", "elles", "cette", "ces"}


def _plat(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _mots(s: str) -> set[str]:
    return {m for m in re.findall(r"[a-z0-9]+", _plat(s)) if len(m) > 2 and m not in VIDES}


def deviner(texte: str, ds, candidats: list[str], exclure: str | None = None) -> dict:
    """Propose la variable et le sens d'une hypothèse rédigée librement (l'auteur peut corriger)."""
    t = _plat(texte)
    mots = _mots(texte)
    meilleur, score = None, 0.0
    for v in candidats:
        if v == exclure or v not in ds.variables:
            continue
        info = ds.variables[v]
        cible = _mots(" ".join([info.label, info.texte or "", v.replace("_", " ")]))
        if not cible:
            continue
        commun = len(cible & mots)
        sc = commun / len(cible) + 0.01 * commun
        if sc > score:
            meilleur, score = v, sc
    sens = "association"
    if any(m in t for m in map(_plat, MOTS_NEGATIFS)):
        sens = "negatif"
    if any(m in t for m in map(_plat, MOTS_POSITIFS)):
        sens = "positif"
    return {"variable": meilleur if score >= 0.34 else None, "sens": sens}


@dataclass
class Verdict:
    numero: int
    texte: str
    variable: str | None
    sens: str
    bivarie: str = "-"
    ajuste: str = "-"
    verdict: str = "non vérifiable"
    explication: str = ""
    details: dict = field(default_factory=dict)


def _sens_terme(t, tab: pd.DataFrame, info) -> tuple[int, bool, list[str]]:
    """(sens de l'effet : +1, -1 ou 0 si mixte/indéterminé ; significatif ; modalités significatives)."""
    base_col = "coef"
    cols = [c for c in t.columns if c in tab.index]
    sig = [c for c in cols if seuil.significatif(tab.loc[c, "p"])]
    if not sig:
        return 0, False, []
    if not t.levels:  # variable quantitative
        return int(np.sign(tab.loc[sig[0], base_col])), True, ["par unité"]
    cats = [str(c) for c in (info.categories or [])]
    signes = []
    for c in sig:
        lev = t.levels[t.columns.index(c)]
        signe = np.sign(tab.loc[c, base_col])
        if info.kind == "binaire":
            # « positif » s'entend pour la modalité de présence (Oui, 1) ou la dernière modalité
            positive = next((x for x in cats if x.strip().lower() in POSITIVE), cats[-1] if cats else lev)
            signe = signe if lev == positive else -signe
        elif info.kind == "ordinale" and lev in cats and t.reference in cats:
            signe = signe if cats.index(lev) > cats.index(t.reference) else -signe
        else:
            signe = 0  # variable nominale : pas de sens défini
        signes.append(int(signe))
    labs = [t.levels[t.columns.index(c)] for c in sig]
    if signes and all(s > 0 for s in signes):
        return 1, True, labs
    if signes and all(s < 0 for s in signes):
        return -1, True, labs
    return 0, True, labs


def _sens_bivarie(r, info, R: Redac, y_binaire: bool) -> int:
    """Sens de l'association brute quand il est lisible (variable ordinale, binaire ou quantitative)."""
    if "crosstab" in r.details and y_binaire and R.event:
        ct = r.details["crosstab"]
        col = [c for c in ct.columns if str(c) == R.event]
        if not col:
            return 0
        pct = ct[col[0]] / ct.sum(axis=1)
        cats = [str(c) for c in ct.index]
        if info.kind == "binaire":
            positive = next((x for x in cats if x.strip().lower() in POSITIVE), cats[-1])
            autre = next(x for x in cats if x != positive)
            return int(np.sign(pct[[c for c in ct.index if str(c) == positive][0]]
                               - pct[[c for c in ct.index if str(c) == autre][0]]))
        if info.kind == "ordinale" and len(cats) >= 2:
            return int(np.sign(pct.iloc[-1] - pct.iloc[0]))
        return 0
    if "groupes" in r.details and y_binaire and R.event:
        g = r.details["groupes"]
        cle = "moyenne" if r.details.get("parametrique") else "mediane"
        autres = [k for k in g if k != R.event]
        if R.event in g and autres:
            return int(np.sign(g[R.event][cle] - g[autres[0]][cle]))
        return 0
    if r.effect_label in ("r de Pearson", "ρ de Spearman", "d de Somers"):
        return int(np.sign(r.effect))
    return 0


def verifier(hypotheses: list[dict], ds, sections: dict[str, Section], outcome: str | None,
             event: str | None) -> Section | None:
    """Section « Vérification des hypothèses » ; None si aucune hypothèse n'est rattachée à une variable."""
    hyps = [h for h in hypotheses if str(h.get("texte", "")).strip()]
    if not hyps or not outcome:
        return None
    R = Redac(ds, outcome, event)
    y_bin = ds.variables[outcome].kind == "binaire"
    tests = {r.x: r for r in (sections.get("bivarie").extra.get("tests", []) if sections.get("bivarie") else [])}
    modele, nom_modele = None, ""
    mn = sections.get("multiniveau")
    if mn is not None and mn.extra.get("final") is not None and mn.extra.get("design") is not None:
        nom, f = mn.extra["final"]
        modele, dsg, nom_modele = f.wald(), mn.extra["design"], f"modèle multi-niveaux {nom}"
    mv = sections.get("multivarie")
    if modele is None and mv is not None and mv.extra.get("fit") is not None:
        modele, dsg, nom_modele = mv.extra["fit"].table(), mv.extra["design"], "modèle multivarié"
    termes = {t.variable: t for t in dsg.terms} if modele is not None else {}

    verdicts: list[Verdict] = []
    for i, h in enumerate(hyps, start=1):
        v = h.get("variable") or None
        sens = h.get("sens") if h.get("sens") in SENS else "association"
        vd = Verdict(i, str(h["texte"]).strip().rstrip("."), v, sens)
        if not v or v not in ds.variables or (v not in tests and v not in termes):
            vd.explication = ("Cette hypothèse n'a pas pu être vérifiée, car elle n'est rattachée à aucune variable "
                              "explicative retenue dans les analyses.")
            verdicts.append(vd)
            continue
        info = ds.variables[v]
        attendu = {"positif": 1, "negatif": -1}.get(sens, 0)
        if info.kind == "nominale" and attendu:
            attendu = 0  # le sens n'a pas de signification pour une variable nominale
            vd.details["nominale"] = True
        # Analyse bivariée
        r = tests.get(v)
        b_sig = bool(r is not None and seuil.significatif(r.p_fdr))
        b_sens = _sens_bivarie(r, info, R, y_bin) if b_sig else 0
        if r is not None:
            vd.bivarie = ("significative" if b_sig else "non significative") + (
                {1: ", sens positif", -1: ", sens négatif"}.get(b_sens, "") if b_sig else "")
        # Analyse ajustée
        a_sig, a_sens, mods = False, 0, []
        if v in termes:
            a_sens, a_sig, mods = _sens_terme(termes[v], modele, info)
            vd.ajuste = ("significative" if a_sig else "non significative") + (
                {1: ", sens positif", -1: ", sens négatif"}.get(a_sens, "") if a_sig else "")
        vd.details.update({"bivarie_sig": b_sig, "ajuste_sig": a_sig, "modalites": mods})
        # Verdict
        x = R.v(v)
        ref = a_sig if v in termes else b_sig
        sens_ref = a_sens if v in termes else b_sens
        if ref and attendu and sens_ref == -attendu:
            vd.verdict = "infirmée"
            vd.explication = (f"L'association entre {x} et {R.y} est significative, mais elle va dans le sens "
                              "contraire de celui attendu.")
        elif ref and (not attendu or sens_ref == attendu):
            partiel = info.kind in ("ordinale", "nominale") and termes.get(v) is not None and \
                len(mods) < len(termes[v].levels)
            vd.verdict = "partiellement confirmée" if partiel else "confirmée"
            if v in termes:
                vd.explication = ("L'association est significative " + ("en analyse bivariée comme " if b_sig else "")
                                  + f"après ajustement sur les autres variables ({nom_modele})")
                if attendu:
                    vd.explication += ", et elle va dans le sens attendu"
                if partiel:
                    vd.explication += (", mais seulement pour " + (f"la modalité {guillemets(mods[0])}" if len(mods) == 1
                                       else "les modalités " + ", ".join(guillemets(m) for m in mods)))
                vd.explication += "."
            else:
                vd.explication = "L'association est significative en analyse bivariée" + (
                    " et va dans le sens attendu." if attendu else ".")
        elif ref and attendu and sens_ref == 0:
            vd.verdict = "partiellement confirmée"
            vd.explication = ("L'association est significative, mais son sens varie selon les modalités et ne "
                              "correspond donc pas entièrement au sens attendu.")
        elif b_sig and v in termes and not a_sig:
            vd.verdict = "partiellement confirmée"
            vd.explication = ("L'association observée en analyse bivariée ne résiste pas à l'ajustement sur les "
                              "autres variables : elle s'explique, au moins en partie, par celles-ci.")
        else:
            vd.verdict = "non confirmée"
            vd.explication = (f"{majuscule(x)} n'{est(x)} pas {accord('associé', x)} de manière significative "
                              f"{a(R.y)} au seuil de {seuil.texte()}.")
        if vd.details.get("nominale") and sens != "association":
            vd.explication += (" Le sens attendu ne peut pas être vérifié pour une variable nominale : seule "
                               "l'existence d'une association est examinée.")
        verdicts.append(vd)

    sec = Section(key="hypotheses", title="Vérification des hypothèses", level=2)
    n = len(verdicts)
    conf = sum(v.verdict == "confirmée" for v in verdicts)
    part = sum(v.verdict == "partiellement confirmée" for v in verdicts)
    intro = (f"Le tableau ci-dessous confronte les {nombre(n, 'hypothèses')} formulées au départ aux résultats obtenus. "
             if n > 1 else "Le tableau ci-dessous confronte l'hypothèse formulée au départ aux résultats obtenus. ")
    intro += ("Une hypothèse est jugée confirmée lorsque l'association attendue est significative après ajustement "
              "sur les autres variables et va dans le sens prévu ; elle est partiellement confirmée lorsque "
              "l'association n'est significative qu'en analyse bivariée ou pour une partie des modalités.")
    sec.paragraphs.append(intro)
    from ..writing.style import _lower_first
    for v in verdicts:
        debut = (f"La {ordinal(v.numero, True)} hypothèse (H{v.numero}) stipulait que "
                 f"{_lower_first(v.texte)}.")
        if v.verdict == "non vérifiable":
            sec.paragraphs.append(f"{debut} {v.explication}")
        else:
            sec.paragraphs.append(f"{debut} Elle est {v.verdict}. En effet, {_lower_first(v.explication)}")
    rows = [{"Hypothèse": f"H{v.numero} : {v.texte}", "Variable": ds.variables[v.variable].label if v.variable
             and v.variable in ds.variables else "-", "Sens attendu": SENS[v.sens], "Analyse bivariée": v.bivarie,
             "Analyse ajustée": v.ajuste, "Verdict": v.verdict} for v in verdicts]
    sec.tables.append(Table(title="Vérification des hypothèses de recherche", data=pd.DataFrame(rows),
                            note=f"Seuil de signification : {seuil.texte()}. Analyse ajustée : {nom_modele or 'non disponible'}."))
    resume = f"Sur les {nombre(n, 'hypothèses')} de départ, {nombre(conf, feminin=True)} " + (
        "est confirmée" if conf <= 1 else "sont confirmées")
    if part:
        resume += f" et {nombre(part, feminin=True)} {'l’est' if part == 1 else 'le sont'} partiellement"
    sec.key_points.append((resume + ".").replace("’", "'") if n > 1 else
                          f"L'hypothèse de départ est {verdicts[0].verdict}.")
    sec.extra["verdicts"] = verdicts
    sec.method_notes.append(
        "Les hypothèses de recherche sont vérifiées de manière systématique : pour chacune, l'association entre la "
        "variable concernée et la variable dépendante est examinée en analyse bivariée puis après ajustement, et "
        "son sens est comparé au sens attendu. Pour une variable ordinale, le sens s'apprécie par rapport à la "
        "modalité de référence ; pour une variable nominale, seule l'existence d'une association est examinée.")
    return sec
