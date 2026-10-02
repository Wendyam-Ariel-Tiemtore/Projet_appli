"""Synthèse de la littérature : sélection, regroupement thématique, extraction et tableaux de synthèse."""

from __future__ import annotations

import math
import re
from datetime import date

import numpy as np
import pandas as pd

from ..stats import fmt
from ..stats.results import Section, Table
from ..writing.style import guillemets, nombre, ordinal
from .sources import Work

STOP = set("""a au aux avec ce ces dans de des du elle en et eux il je la le les leur lui ma mais me même mes moi
mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes toi ton tu un une vos votre vous
c d j l à m n s t y été être avoir est sont plus entre leurs cette selon ainsi chez dont lors via
the of and in to a is for on with by as an are this that from at be or which was were its their it these study
we our has have not using based between among than also more such can may two one new results analysis data
paper article research effect effects case role use""".split())

OBJ = re.compile(r"\b(aim|objective|purpose|this (study|paper|article)|we (examine|investigate|analy[sz]e|study|"
                 r"assess|explore)|objectif|cet article|cette étude|nous (examinons|analysons|étudions))\b", re.I)
METH = re.compile(r"\b(data|survey|sample|regression|model|method|qualitative|interview|panel|cohort|"
                  r"multilevel|logistic|données|enquête|échantillon|régression|modèle|méthode|entretiens)\b", re.I)
RES = re.compile(r"\b(result|find|found|show|suggest|indicate|reveal|associated|résultat|montre|révèle|"
                 r"suggère|indiquent|associé)", re.I)
LIM = re.compile(r"\b(limitation|limit|however|caution|cependant|toutefois|limite)", re.I)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 20]


def extract_rule_based(w: Work) -> dict:
    sents = _sentences(w.abstract)
    na = "non renseigné dans le résumé"
    if not sents:
        return {"objet": na, "methode": na, "resultats": na, "limites": na}

    def pick(rx, default=None):
        for s in sents:
            if rx.search(s):
                return s
        return default

    obj = pick(OBJ, sents[0])
    meth = pick(METH)
    res = None
    for s in reversed(sents):
        if RES.search(s):
            res = s
            break
    lim = pick(LIM)
    return {"objet": _short(obj) or na, "methode": _short(meth) or na, "resultats": _short(res) or na,
            "limites": _short(lim) or na}


def _short(s: str | None, n: int = 260) -> str | None:
    if not s:
        return None
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def rank(works: list[Work], keep: int = 30) -> list[Work]:
    """Ordre de pertinence de la base, pondéré par l'impact (citations) et la présence d'un résumé."""
    current = date.today().year
    scored = []
    n = len(works)
    for i, w in enumerate(works):
        rel = 1 - i / max(n, 1)
        age = max(1, current - (w.year or current) + 1)
        impact = math.log1p(w.cited_by / age)
        score = 0.6 * rel + 0.3 * min(impact / 4, 1) + 0.1 * (1 if w.abstract else 0)
        scored.append((score, w))
    scored.sort(key=lambda t: -t[0])
    return [w for _, w in scored[:keep]]


def themes(works: list[Work], k: int | None = None) -> tuple[list[int], list[str]]:
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer
    docs = [f"{w.title}. {w.title}. {w.abstract}" for w in works]
    if len(works) < 6:
        return [0] * len(works), ["Travaux identifiés"]
    k = k or max(2, min(5, len(works) // 6))
    vec = TfidfVectorizer(stop_words=list(STOP), max_df=0.8, min_df=1, ngram_range=(1, 2), max_features=3000,
                          token_pattern=r"(?u)\b[^\W\d_]{3,}\b")  # noqa: S106  # nosec B106 (motif regex, pas un secret)
    X = vec.fit_transform(docs)
    km = KMeans(k, n_init=10, random_state=42).fit(X)
    terms = np.array(vec.get_feature_names_out())
    names = []
    for c in range(k):
        top = terms[np.argsort(km.cluster_centers_[c])[::-1][:4]]
        names.append(", ".join(top))
    return list(km.labels_), names


def literature_section(works: list[Work], log: dict, topic: str, extractor=None, namer=None) -> Section:
    """Construit la section « Revue de la littérature ».

    extractor(work) -> dict | None : extraction assistée par un modèle de langage (facultative, vérifiée).
    namer(list[str]) -> list[str] : intitulés de thèmes reformulés (facultatif).
    """
    sec = Section(key="litterature", title="Revue de la littérature", level=2)
    sec.refs.add("priem2022")
    if not works:
        msg = log.get("erreur") or "aucun résultat"
        sec.warnings.append(f"La recherche bibliographique n'a pas abouti ({msg}). La revue de littérature est donc à "
                            "compléter par l'auteur.")
        sec.paragraphs.append("[À compléter par l'auteur : revue de la littérature.]")
        return sec
    selected = rank(works)
    labels, names = themes(selected)
    if namer:
        try:
            better = namer(names)
            if better and len(better) == len(names):
                names = better
        except Exception as exc:  # noqa: BLE001 - l'intitulé automatique est conservé
            sec.warnings.append(f"Les intitulés de thèmes n'ont pas pu être reformulés ({type(exc).__name__}).")
    for w in selected:
        ex = None
        if extractor:
            try:
                ex = extractor(w)
            except Exception:  # noqa: BLE001
                ex = None
        w.extracted = ex or extract_rule_based(w)
    sec.paragraphs.append(
        f"La recherche documentaire a été conduite le {_date_fr(log.get('date'))} dans la base bibliographique "
        f"ouverte {log.get('base')}, à partir des mots-clés {guillemets(str(log.get('requete')))}. Elle a renvoyé "
        f"{nombre(int(log.get('n_bruts') or 0), 'références', True)}. Après suppression des doublons et classement selon "
        f"la pertinence et l'impact, {nombre(len(selected), 'travaux')} ont été retenus, puis regroupés en "
        f"{nombre(len(names), 'ensembles')} thématiques par analyse lexicale de leurs titres et résumés. Il convient "
        "de préciser que les éléments des tableaux de synthèse sont tirés des résumés : ils doivent donc être vérifiés "
        "à la lecture des textes intégraux.")
    sec.facts.update({"litt.n_bruts": log.get("n_bruts"), "litt.n_retenus": len(selected), "litt.n_themes": len(names)})
    for t, name in enumerate(names):
        members = [w for w, lab in zip(selected, labels, strict=True) if lab == t]
        if not members:
            continue
        members.sort(key=lambda w: (w.year or 0))
        cites = " ; ".join(w.citation() for w in members[:8])
        yrs = [w.year for w in members if w.year]
        span = f"entre {min(yrs)} et {max(yrs)}" if yrs else ""
        verbe = "réunit" if t % 2 == 0 else "regroupe"
        sec.paragraphs.append(
            f"Le {ordinal(t + 1)} thème, intitulé {guillemets(name)}, {verbe} "
            f"{nombre(len(members), 'travaux') if len(members) > 1 else 'un (01) travail'} publié"
            f"{'s' if len(members) > 1 else ''} {span} ({cites}).".replace("  ", " ").replace(" (", " (", 1))
        rows = []
        for w in members:
            e = w.extracted
            rows.append({"Auteur(s), année": w.citation(), "Objet": e.get("objet", ""), "Méthode": e.get("methode", ""),
                         "Résultats principaux": e.get("resultats", ""), "Limites et perspectives": e.get("limites", "")})
        sec.tables.append(Table(title=f"Synthèse de la littérature, thème {t + 1} : {name}", data=pd.DataFrame(rows),
                                note="Éléments extraits des résumés des articles.",
                                source=f"Source : {log.get('base')}, recherche du {_date_fr(log.get('date'))}."))
    sec.paragraphs.append(
        "[À compléter par l'auteur : ce que la littérature établit, les controverses, et la lacune que la présente "
        "étude se propose de combler.]")
    sec.extra["works"] = selected
    sec.method_notes.append(
        f"La revue de la littérature s'appuie sur une recherche dans la base ouverte {log.get('base')} (Priem, Piwowar et "
        "Orr, 2022). Seuls les mots-clés du sujet ont été transmis à cette base.")
    return sec


def _date_fr(iso: str | None) -> str:
    if not iso:
        return "-"
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
            "novembre", "décembre"]
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} {mois[m - 1]} {y}"


def work_references(sec: Section) -> list[str]:
    return sorted((w.apa() for w in sec.extra.get("works", [])), key=str.lower)


__all__ = ["literature_section", "work_references", "extract_rule_based", "rank", "themes", "fmt"]
