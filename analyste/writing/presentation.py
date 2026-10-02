"""Plan d'une présentation orale (soutenance, communication, séminaire, restitution, atelier).

Le plan est construit à partir des résultats déjà calculés : aucune valeur n'est inventée. Les titres des
diapositives sont des phrases affirmatives tirées des résultats, les puces sont courtes, et les notes de l'orateur
reprennent les paragraphes rédigés dans le style des mémoires (voir writing/style.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ..stats import fmt, seuil
from ..stats.results import Section
from .phrases import Redac
from .style import a, de, enumeration, guillemets, majuscule, nettoyer, nombre, sans_article

# ---------------------------------------------------------------------------
# Options proposées à l'auteur
# ---------------------------------------------------------------------------

GENRES = {
    "soutenance": {"libelle": "Soutenance (mémoire, rapport de stage, thèse)", "duree": 20, "deroule": "classique",
                   "niveau": "detaille", "visuels": "mixte", "annexes": False,
                   "aide": "Démarche complète devant un jury : problématique, méthodologie, résultats, discussion."},
    "communication": {"libelle": "Communication scientifique (colloque, conférence)", "duree": 15,
                      "deroule": "classique", "niveau": "detaille", "visuels": "graphiques", "annexes": False,
                      "aide": "Format court centré sur la question, la méthode et les résultats principaux."},
    "seminaire": {"libelle": "Séminaire de recherche ou de laboratoire", "duree": 30, "deroule": "classique",
                  "niveau": "detaille", "visuels": "mixte", "annexes": True,
                  "aide": "Place plus large à la méthode et aux limites, pour nourrir la discussion."},
    "restitution": {"libelle": "Restitution professionnelle (décideurs, partenaires, bailleurs)", "duree": 15,
                    "deroule": "messages_cles", "niveau": "allege", "visuels": "graphiques", "annexes": True,
                    "aide": "Messages clés d'abord, résultats illustrés, détails techniques renvoyés en annexe."},
    "atelier": {"libelle": "Atelier de validation ou de formation", "duree": 45, "deroule": "classique",
                "niveau": "detaille", "visuels": "tableaux", "annexes": True,
                "aide": "Résultats commentés pas à pas, avec des questions pour la discussion."},
}
DUREES = (10, 15, 20, 30, 45)
DEROULES = {"classique": "Classique : contexte, méthodes, résultats", "messages_cles": "Messages clés d'abord"}
NIVEAUX = {"detaille": "Détaillé (tests, IC, probabilités)", "allege": "Allégé (chiffres essentiels)"}
VISUELS = {"graphiques": "Graphiques en priorité", "tableaux": "Tableaux en priorité", "mixte": "Graphiques et tableaux"}
THEMES = {"ardoise": "Ardoise et sarcelle", "foret": "Forêt et or", "terre": "Terre cuite et vert-de-gris",
          "nuit": "Bleu nuit et ambre"}
THEME_COULEURS = {
    "ardoise": {"fonce": "22303A", "primaire": "2F4858", "accent": "2A9D8F", "doux": "EDF2F4", "texte": "1F2A33",
                "attenue": "5E6B75", "accent_clair": "8FD3C9", "relief": "33475A"},
    "foret": {"fonce": "1C3326", "primaire": "2C5F2D", "accent": "B8892B", "doux": "EEF3EC", "texte": "1E2B22",
              "attenue": "5B6B5E", "accent_clair": "E3C27A", "relief": "2A4A36"},
    "terre": {"fonce": "3B2320", "primaire": "9C4434", "accent": "3E7C74", "doux": "F3EFEE", "texte": "2B1E1C",
              "attenue": "6D5D59", "accent_clair": "E8A898", "relief": "553330"},
    "nuit": {"fonce": "1B2250", "primaire": "26357A", "accent": "D9961A", "doux": "EEF0F8", "texte": "1A1F3A",
             "attenue": "5A6080", "accent_clair": "F2C76A", "relief": "28306A"},
}
FORMATS = ("16:9", "4:3")
CONTENUS = {"contexte": "Contexte et problématique", "objectifs": "Objectifs et hypothèses",
            "methodes": "Données et méthodes", "litterature": "Revue de littérature",
            "descriptif": "Caractéristiques de l'échantillon", "bivarie": "Analyse bivariée",
            "multivarie": "Analyse multivariée", "multiniveau": "Analyse multi-niveaux",
            "typologie": "Analyses factorielles et typologie", "survie": "Analyse de survie",
            "limites": "Limites", "recommandations": "Recommandations"}


@dataclass
class PresentationSpec:
    active: bool = False
    genre: str = "soutenance"
    duree: int = 20
    deroule: str = "classique"
    niveau: str = "detaille"
    visuels: str = "mixte"
    theme: str = "ardoise"
    format: str = "16:9"
    notes: bool = True
    annexes: bool = False
    contenus: list[str] = field(default_factory=lambda: list(CONTENUS))
    recommandations: list[str] = field(default_factory=list)
    contact: str = ""

    @classmethod
    def from_dict(cls, d: dict | None) -> PresentationSpec:
        d = dict(d or {})
        genre = d.get("genre") if d.get("genre") in GENRES else "soutenance"
        for k in ("duree", "deroule", "niveau", "visuels", "annexes"):  # valeurs par défaut propres au genre
            if d.get(k) in (None, ""):
                d[k] = GENRES[genre][k]
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        p = cls(**known)
        p.genre = genre
        p.duree = int(p.duree) if str(p.duree).isdigit() and int(p.duree) in DUREES else GENRES[p.genre]["duree"]
        p.deroule = p.deroule if p.deroule in DEROULES else GENRES[p.genre]["deroule"]
        p.niveau = p.niveau if p.niveau in NIVEAUX else GENRES[p.genre]["niveau"]
        p.visuels = p.visuels if p.visuels in VISUELS else GENRES[p.genre]["visuels"]
        p.theme = p.theme if p.theme in THEMES else "ardoise"
        p.format = p.format if p.format in FORMATS else "16:9"
        p.contenus = [c for c in p.contenus if c in CONTENUS]
        p.recommandations = [nettoyer(str(r).strip())[:300] for r in p.recommandations if str(r).strip()][:6]
        p.contact = nettoyer(str(p.contact).strip())[:120]
        return p


# ---------------------------------------------------------------------------
# Diapositives
# ---------------------------------------------------------------------------

@dataclass
class Diapo:
    kind: str  # titre | plan | messages | texte | cartes | chiffres | graphique | image | tableau | conclusion | fin
    titre: str = ""
    sous_titre: str = ""
    puces: list[str] = field(default_factory=list)
    encadre: str = ""  # texte mis en valeur à droite (question de recherche, lecture d'un résultat)
    chiffres: list[tuple[str, str]] = field(default_factory=list)  # (valeur, libellé)
    cartes: list[tuple[str, str]] = field(default_factory=list)  # (intitulé, texte)
    graphique: dict | None = None
    image: Path | None = None
    tableau: pd.DataFrame | None = None
    note_bas: str = ""
    notes: str = ""
    partie: str = ""
    priorite: int = 1  # 1 indispensable, 2 utile, 3 accessoire
    annexe: bool = False
    meta: dict = field(default_factory=dict)


@dataclass
class Plan:
    spec: PresentationSpec
    diapos: list[Diapo]
    titre: str
    pied: str


def _phrases(texte: str) -> list[str]:
    texte = nettoyer(re.sub(r"[ \t\r\n]+", " ", texte).strip())  # les espaces insécables sont conservées
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý«])", texte) if p.strip()]


def _court(texte: str, limite: int = 170) -> str:
    """Garde la première phrase, ou la coupe proprement à une virgule si elle est trop longue."""
    ph = _phrases(texte)
    if not ph:
        return ""
    s = ph[0]
    if len(s) <= limite:
        return s
    coupe, prof = -1, 0  # dernière virgule hors parenthèses et hors guillemets
    for i, ch in enumerate(s[:limite]):
        if ch in "(«":
            prof += 1
        elif ch in ")»":
            prof = max(0, prof - 1)
        elif ch == "," and prof == 0 and s[i + 1:i + 2] == " ":
            coupe = i
    return (s[:coupe] + ".") if coupe > limite // 2 else s


def _sans_point(s: str) -> str:
    return s.rstrip(" .")


def _sing(unite: str) -> str:
    return unite[:-1] if unite.endswith("s") and not unite.endswith("ss") else unite


def _paragraphe_de(sec: Section, motif: str) -> str:
    m = motif.lower()
    for p in sec.paragraphs:
        if m and m in p[:220].lower():
            return p
    return ""


ORAL = [("Les tableaux ci-dessous présentent", "Le tableau présenté ici résume"),
        ("Le tableau ci-dessous présente", "Le tableau présenté ici résume"),
        ("Les tableaux ci-dessous", "Les résultats présentés ici"), ("ci-dessous", "ci-contre"),
        ("ci-dessus", "précédemment")]


def _oral(texte: str) -> str:
    """Les paragraphes du document deviennent des notes d'orateur : pas de renvoi à des tableaux « ci-dessous »."""
    for a_, b_ in ORAL:
        texte = texte.replace(a_, b_)
    return texte


def _notes(*paras: str) -> str:
    return "\n\n".join(_oral(nettoyer(p)) for p in paras if p)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def planifier(pres: PresentationSpec, req, sections: dict[str, Section], data_info: dict, R: Redac,
              cfg, key_results: list[str], limites: list[str], figdir: Path | None = None) -> Plan:
    """Construit la liste des diapositives selon le genre, la durée, le déroulé et les contenus choisis."""
    detail = pres.niveau == "detaille"
    voulu = set(pres.contenus)
    out: list[Diapo] = []
    annexes: list[Diapo] = []
    titre_doc = nettoyer(req.title)
    sous = {"soutenance": {"memoire": "Soutenance de mémoire", "rapport_stage": "Soutenance de rapport de stage"}.get(
                req.doc_type, "Soutenance"),
            "communication": "Communication scientifique", "seminaire": "Séminaire de recherche",
            "restitution": "Restitution des résultats", "atelier": "Atelier de validation des résultats"}[pres.genre]

    # --- Titre ---
    accueil = {
        "soutenance": "Monsieur le Président du jury, Mesdames et Messieurs les membres du jury, chers invités, nous "
                      f"avons l'honneur de vous présenter les résultats de notre travail intitulé {guillemets(titre_doc)}.",
        "communication": f"Mesdames et Messieurs, nous vous présentons aujourd'hui les résultats d'une étude intitulée "
                         f"{guillemets(titre_doc)}.",
        "seminaire": f"Cette séance est consacrée à l'étude intitulée {guillemets(titre_doc)}. Nous présenterons la "
                     "démarche suivie, les principaux résultats et les questions qui restent ouvertes.",
        "restitution": "Mesdames et Messieurs, nous vous remercions de votre présence. Cette rencontre a pour objet "
                       f"de restituer les principaux résultats de l'étude intitulée {guillemets(titre_doc)}.",
        "atelier": f"Cet atelier a pour objet d'examiner ensemble les résultats de l'étude intitulée "
                   f"{guillemets(titre_doc)}, afin de les valider et de recueillir vos observations.",
    }[pres.genre]
    out.append(Diapo("titre", titre=titre_doc, sous_titre=sous, notes=accueil,
                     meta={"auteur": nettoyer(req.author), "direction": nettoyer(req.supervisor),
                           "institution": nettoyer(req.institution), "date": nettoyer(req.date_text)}))

    messages = [_court(k, 240) for k in (_messages(sections, R) or key_results[:4]) if k]
    if pres.deroule == "messages_cles" and messages:
        out.append(Diapo("messages", titre="Ce qu'il faut retenir", puces=messages[:4], partie="Messages clés",
                         notes=_notes("Avant d'entrer dans le détail, voici les principaux enseignements de l'étude.",
                                      *messages[:4])))

    # --- Contexte et problématique ---
    if "contexte" in voulu and (req.context or req.problematique):
        puces = []
        for par in [p for p in req.context.split("\n") if p.strip()]:
            puces += [_court(s, 200) for s in _phrases(par)][:2]
        out.append(Diapo("texte", titre="Contexte et justification", puces=puces[:4],
                         meta={"etiquette": "Question de recherche"},
                         encadre=(nettoyer(req.problematique.rstrip("?. ")) + " ?") if req.problematique else "",
                         partie="Contexte", notes=_notes(req.context, "La question qui guide ce travail est la "
                                                         f"suivante : {_minuscule(req.problematique.rstrip('?. '))} ?"
                                                         if req.problematique else "")))

    # --- Objectifs et hypothèses ---
    if "objectifs" in voulu and (req.objectives or req.hypotheses):
        cartes = []
        if req.objectives:
            cartes.append(("Objectif général", _sans_point(nettoyer(req.objectives[0]))))
            for i, o in enumerate(req.objectives[1:3], start=1):
                cartes.append((f"Objectif spécifique {i}", _sans_point(nettoyer(o))))
        hyp = [(f"Hypothèse {i}", _sans_point(nettoyer(h))) for i, h in enumerate(req.hypotheses[:3], start=1)]
        if len(cartes) + len(hyp) <= 4:
            out.append(Diapo("cartes", titre="Objectifs et hypothèses", cartes=cartes + hyp, partie="Objectifs",
                             notes=_notes(_objectifs_texte(req))))
        else:
            out.append(Diapo("cartes", titre="Objectifs de l'étude", cartes=cartes, partie="Objectifs",
                             notes=_notes(_objectifs_texte(req))))
            if hyp:
                out.append(Diapo("cartes", titre="Hypothèses de recherche", cartes=hyp, partie="Objectifs",
                                 priorite=2, notes=_notes("Nous avons formulé les hypothèses suivantes. "
                                                          + " ".join(f"{t} : {x}." for t, x in hyp))))

    # --- Littérature ---
    if "litterature" in voulu and "litterature" in sections:
        d = _diapo_litterature(sections["litterature"])
        if d:
            out.append(d)

    # --- Données et méthodes ---
    if "methodes" in voulu:
        out.append(_diapo_methodes(req, sections, data_info, R, cfg, detail))

    # --- Résultats ---
    if "descriptif" in voulu and "descriptif" in sections:
        d = _diapo_descriptif(sections["descriptif"], R, cfg)
        if d:
            out.append(d)
    if "bivarie" in voulu and "bivarie" in sections:
        out += _diapos_bivarie(sections["bivarie"], R, pres, detail)
    if "multivarie" in voulu and "multivarie" in sections:
        d, ann = _diapos_multivarie(sections["multivarie"], R, pres, detail, figdir)
        out += d
        annexes += ann
    if "multiniveau" in voulu and "multiniveau" in sections:
        out += _diapos_multiniveau(sections["multiniveau"], R, cfg, detail)
    if "typologie" in voulu and "cah" in sections:
        d = _diapo_typologie(sections["cah"], R)
        if d:
            out.append(d)
    if "survie" in voulu and "survie" in sections:
        d = _diapo_survie(sections["survie"], R, detail)
        if d:
            out.append(d)

    # --- Limites, conclusion, recommandations ---
    if "limites" in voulu and limites and pres.genre in ("soutenance", "seminaire", "atelier", "communication"):
        out.append(Diapo("texte", titre="Limites de l'étude", puces=[_court(x, 210) for x in limites[:3]],
                         encadre="Les associations mises en évidence ne sont pas des relations de cause à effet",
                         partie="Discussion", priorite=2, notes=_notes(*limites)))
    if pres.deroule == "classique" and messages:
        out.append(Diapo("conclusion", titre="Conclusion" if pres.genre != "restitution" else "Ce qu'il faut retenir",
                         puces=messages[:3], partie="Conclusion",
                         notes=_notes("Au terme de ce travail, plusieurs résultats méritent d'être retenus.",
                                      *messages[:3])))
    if "recommandations" in voulu and pres.recommandations:
        out.append(Diapo("cartes", titre="Recommandations",
                         cartes=[(f"Recommandation {i}", _sans_point(r))
                                 for i, r in enumerate(pres.recommandations[:4], start=1)],
                         partie="Recommandations",
                         notes=_notes("Au regard de ces résultats, nous formulons les recommandations suivantes. "
                                      + " ".join(f"{_sans_point(r)}." for r in pres.recommandations[:4]))))
    if pres.genre == "atelier":
        out.append(Diapo("texte", titre="Questions pour la discussion", partie="Discussion", priorite=2,
                         puces=["Les résultats correspondent-ils à ce que vous observez sur le terrain ?",
                                "Quels facteurs importants n'ont pas pu être pris en compte ?",
                                "Quelles priorités d'action se dégagent pour vous ?"],
                         encadre="Vos observations serviront à finaliser le rapport",
                         meta={"etiquette": "Objectif de l'échange"},
                         notes="Nous proposons à présent d'ouvrir la discussion autour de ces trois questions."))
    fin = {"soutenance": ("Merci de votre attention", "Nous restons à votre disposition pour vos questions, critiques "
                          "et suggestions"),
           "communication": ("Merci de votre attention", "Questions et échanges"),
           "seminaire": ("Merci de votre attention", "Place à la discussion"),
           "restitution": ("Merci de votre attention", "Questions et échanges"),
           "atelier": ("Merci de votre participation", "Vos observations sont les bienvenues")}[pres.genre]
    out.append(Diapo("fin", titre=fin[0], sous_titre=fin[1], meta={"contact": pres.contact},
                     notes=("Nous vous remercions de votre aimable attention et restons à votre disposition pour vos "
                            "questions, critiques et suggestions en vue de l'amélioration de ce travail."
                            if pres.genre == "soutenance" else
                            "Nous vous remercions de votre attention et restons à votre disposition pour vos "
                            "questions.")))

    out = _ajuster(out, pres)
    if pres.annexes:
        if "methodes" not in voulu:
            annexes.insert(0, _diapo_methodes(req, sections, data_info, R, cfg, True))
        for d in annexes:
            d.annexe = True
        if annexes:
            out += [Diapo("plan", titre="Annexes", puces=[d.titre for d in annexes], annexe=True)] + annexes
    _plan_et_notes(out, pres)
    pied = nettoyer(req.author or req.institution or "")
    return Plan(spec=pres, diapos=out, titre=titre_doc, pied=pied)


def _minuscule(s: str) -> str:
    from .style import _lower_first
    return _lower_first(nettoyer(s))


def _messages(sections: dict[str, Section], R: Redac) -> list[str]:
    """Trois ou quatre messages de conclusion : niveau du phénomène, facteurs retenus, effet le plus net, contexte."""
    out = []
    desc = sections.get("descriptif")
    if desc and desc.key_points:
        out.append(desc.key_points[0])
    mv = sections.get("multivarie")
    fit, dsg = (mv.extra.get("fit"), mv.extra.get("design")) if mv else (None, None)
    if fit is not None and dsg is not None:
        from ..stats.models import _level_clause
        tab = fit.table()
        noms, meilleur = [], None
        for t in dsg.terms:
            cols = [c for c in t.columns if c in tab.index and seuil.significatif(tab.loc[c, "p"])]
            if not cols:
                continue
            noms.append(R.v(t.variable))
            if t.levels and fit.kind == "logistique":
                for c in cols:
                    force = abs(np.log(max(float(tab.loc[c, "est"]), 1e-9)))
                    if meilleur is None or force > meilleur[0]:
                        meilleur = (force, t, c)
        if noms:
            from .style import genre
            if len(noms) == 1:
                fem = genre(sans_article(noms[0])) == "f"
                out.append(f"Après ajustement, seul{'e' if fem else ''} {noms[0]} reste "
                           f"{'associée' if fem else 'associé'} {a(R.y)}.")
            else:
                masc = any(genre(sans_article(n)) == "m" for n in noms)
                out.append(f"Après ajustement, {enumeration(noms)} restent {'associés' if masc else 'associées'} "
                           f"{a(R.y)}.")
        if meilleur is not None:
            _, t, c = meilleur
            lev = t.levels[t.columns.index(c)]
            out.append(majuscule("Toutes choses égales par ailleurs, " + _level_clause(
                "logistique", R, R.groupe(t.variable, lev), R.groupe(t.variable, t.reference, premier=False),
                tab.loc[c], "OR", court=True)))
    mn = sections.get("multiniveau")
    if mn and mn.key_points:
        out.append(mn.key_points[0])
    sv = sections.get("survie")
    if sv and sv.key_points and len(out) < 4:
        out.append(sv.key_points[0])
    if len(out) < 3:
        bv = sections.get("bivarie")
        if bv and bv.key_points:
            out.insert(1, bv.key_points[0])
    return list(dict.fromkeys(out))[:4]


def _objectifs_texte(req) -> str:
    txt = ""
    if req.objectives:
        txt = "L'objectif général de cette étude est " + _de_inf(req.objectives[0]) + "."
        if len(req.objectives) > 1:
            txt += " De manière spécifique, il s'agit " + " ; ".join(_de_inf(o) for o in req.objectives[1:]) + "."
    if req.hypotheses:
        txt += " Pour y parvenir, nous avons formulé les hypothèses suivantes : " + " ; ".join(
            _sans_point(h[:1].lower() + h[1:]) for h in req.hypotheses) + "."
    return txt.strip()


def _de_inf(s: str) -> str:
    from .phrases import elision
    from .style import _lower_first
    return elision("de", _lower_first(_sans_point(nettoyer(s))))


def _ajuster(diapos: list[Diapo], pres: PresentationSpec) -> list[Diapo]:
    """Respecte la durée : environ une minute et demie par diapositive, questions comprises."""
    budget = max(6, round(pres.duree / 1.5))
    while len(diapos) > budget:
        for prio in (3, 2):
            cand = [i for i, d in enumerate(diapos) if d.priorite == prio]
            if cand:
                del diapos[cand[-1]]
                break
        else:
            break
    if len(diapos) + 1 <= budget and len({d.partie for d in diapos if d.partie}) >= 4 and pres.duree >= 15:
        diapos.insert(1, Diapo("plan", titre="Plan de la présentation"))
    return diapos


def _plan_et_notes(diapos: list[Diapo], pres: PresentationSpec) -> None:
    parties = list(dict.fromkeys(d.partie for d in diapos if d.partie and not d.annexe))
    for d in diapos:
        if d.kind == "plan" and not d.annexe:
            d.puces = parties
            d.notes = (f"Notre présentation s'articule autour de {nombre(len(parties), 'points')} : "
                       + enumeration([p[:1].lower() + p[1:] for p in parties]) + ".")
        if not pres.notes:
            d.notes = ""


# ---------------------------------------------------------------------------
# Diapositives par analyse
# ---------------------------------------------------------------------------

def _diapo_litterature(sec: Section) -> Diapo | None:
    cartes = []
    for t in sec.tables:
        m = re.match(r"Synthèse de la littérature, thème (\d+) : (.+)", t.title)
        if m:
            n = len(t.data)
            cartes.append((f"Thème {m.group(1)}", f"{_sans_point(m.group(2))} : {nombre(n, 'travaux') if n > 1 else 'un travail'}"))
    if not cartes:
        return None
    return Diapo("cartes", titre="Ce que dit la littérature", cartes=cartes[:4], partie="Revue de littérature",
                 priorite=2, notes=_notes(*sec.paragraphs[:3]))


def _methodes_courtes(sections: dict[str, Section], cfg) -> list[str]:
    out = []
    if "descriptif" in sections:
        out.append("Statistiques descriptives, intervalles de confiance de Wilson")
    if "bivarie" in sections:
        corr = {"fdr_bh": "correction de Benjamini et Hochberg", "holm": "correction de Holm",
                "aucune": "sans correction des tests multiples"}.get(getattr(cfg, "correction", "fdr_bh"), "")
        out.append(f"Tests bivariés adaptés au type des variables, {corr}")
    if "multivarie" in sections and sections["multivarie"].extra.get("fit") is not None:
        from ..stats.models import MODEL_NAMES
        out.append(MODEL_NAMES.get(sections["multivarie"].extra["fit"].kind, "Modèle multivarié"))
    if "multiniveau" in sections:
        out.append("Modèles multi-niveaux à ordonnée aléatoire, démarche par étapes")
    if "acm" in sections or "acp" in sections or "cah" in sections:
        out.append("Analyses factorielles et classification ascendante hiérarchique")
    if "survie" in sections:
        out.append("Analyse de survie : Kaplan-Meier, log-rank et modèle de Cox")
    return out


def _diapo_methodes(req, sections, data_info, R: Redac, cfg, detail: bool) -> Diapo:
    chiffres = [(fmt.integer(data_info.get("n", 0)),
                 f"{R.unite} {'observées' if R.fem else 'observés'}" if R.unite.endswith("s") else "observations")]
    if cfg is not None and getattr(cfg, "explanatory", None):
        chiffres.append((str(len(cfg.explanatory)), "variables explicatives"))
    if "multiniveau" in sections:
        k = sections["multiniveau"].facts.get("mn.contextes")
        if k:
            chiffres.append((fmt.integer(k), "contextes de niveau 2"))
    chiffres.append((seuil.texte().replace(" ", " "), "seuil de signification"))
    puces = _methodes_courtes(sections, cfg)
    source = _court(req.data_description, 160) if req.data_description else ""
    notes = [data_info.get("description", "")]
    if req.data_description:
        notes.insert(0, req.data_description)
    for k in ("descriptif", "bivarie", "multivarie", "multiniveau", "survie"):
        if k in sections and sections[k].method_notes:
            notes.append(" ".join(_phrases(sections[k].method_notes[0])[:2]))
    return Diapo("chiffres", titre="Données et méthodes", chiffres=chiffres[:4], puces=puces[:5],
                 encadre=source, partie="Données et méthodes", notes=_notes(*notes))


def _diapo_descriptif(sec: Section, R: Redac, cfg) -> Diapo | None:
    chiffres = []
    titre = "Caractéristiques de l'échantillon"
    dep = next((p for p in sec.paragraphs if p.startswith("La variable dépendante")), "")
    if R.outcome and R.event:
        pct = sec.facts.get(f"{R.outcome}.{R.event}.pct")
        if pct is not None:
            chiffres.append((fmt.pct(pct / 100), majuscule(sans_article(R.indicateur()))))
            titre = f"{majuscule(R.indicateur())} s'établit à {fmt.pct(pct / 100)}"
    # Modalités dominantes des autres variables (les plus marquées)
    cand = []
    for key, val in sec.facts.items():
        m = re.match(r"(.+)\.(.+)\.pct$", key)
        if m and m.group(1) != R.outcome and m.group(1) in R.ds.variables:
            cand.append((val, m.group(1), m.group(2)))
    vus = set()
    for val, var, mod in sorted(cand, reverse=True):
        if var in vus or len(chiffres) >= 4 or val < 50:
            continue
        vus.add(var)
        chiffres.append((fmt.pct(val / 100), f"{majuscule(sans_article(R.v(var)))} : {mod}"))
    if not chiffres:
        return None
    return Diapo("chiffres", titre=titre, chiffres=chiffres, partie="Résultats",
                 note_bas="Pourcentages calculés sur les réponses renseignées.",
                 notes=_notes(dep, *[p for p in sec.paragraphs[1:4] if p != dep]))


def _diapos_bivarie(sec: Section, R: Redac, pres: PresentationSpec, detail: bool) -> list[Diapo]:
    tests = [t for t in sec.extra.get("tests", []) if not np.isnan(t.p)]
    sig = sorted([t for t in tests if seuil.significatif(t.p_fdr)], key=lambda t: t.p_fdr)
    out = []
    n_sig, n_tot = len(sig), len(tests)
    if n_sig == 0:
        titre = f"Aucun facteur n'est associé de manière significative {a(R.y)}"
    elif n_sig == 1:
        titre = f"Un seul facteur sur {nombre(n_tot)} est associé {a(R.y)}"
    else:
        titre = f"{majuscule(nombre(n_sig))} facteurs sur {nombre(n_tot)} sont associés {a(R.y)}"
    rows = []
    for t in sorted(tests, key=lambda t: t.p_fdr):
        row = {"Facteur": majuscule(sans_article(R.v(t.x))),
               "Association": ("significative" if seuil.significatif(t.p_fdr) else "non significative")}
        if detail:
            row["Test"] = t.test
            row["p corrigée"] = fmt.pval(t.p_fdr)
        row["Intensité"] = t.strength if seuil.significatif(t.p_fdr) else "-"
        rows.append(row)
    tab = pd.DataFrame(rows)
    out.append(Diapo("tableau", titre=titre, tableau=tab.head(9), partie="Résultats",
                     note_bas=("Tests choisis selon le type des variables ; probabilités corrigées pour les tests "
                               f"multiples. Seuil : {seuil.texte()}." if detail else
                               f"Associations bivariées, avant prise en compte des autres facteurs. Seuil : "
                               f"{seuil.texte()}."),
                     notes=_notes(*sec.paragraphs[:1], *[p for p in sec.paragraphs if p.startswith(("À l'inverse",
                                                                                                      "Ainsi"))])))
    # Une diapositive graphique par facteur, dans l'ordre d'importance
    nb = 0
    for t in sig:
        ct = t.details.get("crosstab")
        if ct is None or not R.event or R.event not in [str(c) for c in ct.columns]:
            continue
        stable = ct.sum(axis=1) >= 10
        rp = ct.div(ct.sum(axis=1), axis=0)
        col = rp.loc[stable, [c for c in rp.columns if str(c) == R.event][0]] * 100
        if len(col) < 2:
            continue
        x = R.v(t.x)
        vals = [float(v) for v in col.to_numpy()]
        cats = [str(c) for c in col.index]
        d = np.diff(vals)
        info = R.ds.variables[t.x]
        if info.kind == "ordinale" and len(vals) >= 3 and ((d > 0).all() or (d < 0).all()):
            verbe = "augmente" if (d > 0).all() else "diminue"
            titre_g = f"{majuscule(R.indicateur())} {verbe} avec {x}"
        else:
            titre_g = f"{majuscule(R.indicateur())} varie selon {x}"
        hi, lo = int(np.argmax(vals)), int(np.argmin(vals))
        puces = [f"{fmt.pct(vals[hi] / 100)} pour la modalité {guillemets(cats[hi])}",
                 f"{fmt.pct(vals[lo] / 100)} pour la modalité {guillemets(cats[lo])}",
                 f"Écart de {fmt.num(vals[hi] - vals[lo], 1)} points de pourcentage"]
        if detail:
            puces.append(f"{t.effect_label} = {fmt.num(t.effect)} ; {fmt.p_phrase(t.p_fdr)} (corrigée)")
        else:
            puces.append(f"Association d'intensité {t.strength}")
        ph = _paragraphe_de(sec, x)
        out.append(Diapo("graphique", titre=titre_g, puces=puces, partie="Résultats", priorite=2 if nb else 1,
                         graphique={"categories": cats, "valeurs": vals, "format": "pct",
                                    "serie": majuscule(sans_article(R.indicateur())), "surligne": hi,
                                    "axe": majuscule(sans_article(x))},
                         note_bas=f"{majuscule(sans_article(R.indicateur()))} selon {x} (%).",
                         notes=_notes(ph)))
        nb += 1
        if nb >= (3 if pres.duree >= 20 else 2):
            break
    return out


def _foret_diapo(fit, dsg, R: Redac, pres: PresentationSpec, figdir: Path | None) -> Path | None:
    """Graphique en forêt des seuls effets significatifs, à la taille d'une diapositive."""
    if figdir is None or not fit.exp_scale:
        return None
    from ..stats import figures
    tab = fit.table()
    rows = []
    for t in dsg.terms:
        for c in t.columns:
            if c in tab.index and seuil.significatif(tab.loc[c, "p"]):
                lev = t.levels[t.columns.index(c)] if t.levels else "par unité"
                rows.append({"terme": f"{majuscule(sans_article(R.v(t.variable)))} : {lev}", "est": tab.loc[c, "est"],
                             "lo": tab.loc[c, "lo_e"], "hi": tab.loc[c, "hi_e"]})
    if len(rows) < 2:
        return None
    coul = THEME_COULEURS.get(pres.theme, THEME_COULEURS["ardoise"])
    lab = {"logistique": "Rapport de cotes", "poisson": "Rapport de taux", "binomiale_negative": "Rapport de taux"}
    return figures.forest(pd.DataFrame(rows), lab.get(fit.kind, "Effet"), figdir, log_scale=True,
                          diapo={"couleur": "#" + coul["primaire"], "accent": "#" + coul["accent"],
                                 "largeur": 7.2 if pres.format == "16:9" else 5.6, "police": 13})


def _diapos_multivarie(sec: Section, R: Redac, pres: PresentationSpec, detail: bool, figdir: Path | None = None):
    fit, dsg = sec.extra.get("fit"), sec.extra.get("design")
    if fit is None or dsg is None:
        return [], []
    from ..stats.models import EFFECT
    tab = fit.table()
    eff = EFFECT.get(fit.kind, "β")
    rows, puces = [], []
    nsig = 0
    for t in dsg.terms:
        cols = [c for c in t.columns if c in tab.index]
        sig = [c for c in cols if seuil.significatif(tab.loc[c, "p"])]
        if sig:
            nsig += 1
        for c in cols:
            r = tab.loc[c]
            lev = t.levels[t.columns.index(c)] if t.levels else "par unité"
            if not seuil.significatif(r["p"]) and pres.niveau == "allege":
                continue
            row = {"Facteur": majuscule(sans_article(R.v(t.variable))), "Modalité": lev,
                   "Référence": t.reference or "-"}
            if fit.kind == "logistique" and not detail:
                row["Lecture"] = R.chances(float(r["est"])) if seuil.significatif(r["p"]) else "non significatif"
            else:
                row[eff] = fmt.num(r["est"])
                row["IC à 95 %"] = fmt.ci(r["lo_e"], r["hi_e"])
                row["p"] = fmt.pval(r["p"])
            rows.append(row)
        if sig and fit.kind == "logistique":
            best = min(sig, key=lambda c: tab.loc[c, "p"])
            lev = t.levels[t.columns.index(best)] if t.levels else None
            rb = tab.loc[best]
            if lev:
                puces.append(f"{majuscule(sans_article(R.v(t.variable)))} {guillemets(lev)} : "
                             f"{R.chances(float(rb['est']))} (réf. {guillemets(t.reference)})")
            else:
                puces.append(f"{majuscule(sans_article(R.v(t.variable)))} : rapport de {fmt.num(rb['est'], 3)} par unité")
    if nsig == 0:
        titre = f"Après ajustement, aucun facteur ne reste associé {a(R.y)}"
    elif nsig == 1:
        titre = f"Après ajustement, un seul facteur reste associé {a(R.y)}"
    else:
        titre = f"Après ajustement, {nombre(nsig)} facteurs restent associés {a(R.y)}"
    notes = _notes(*[p for p in sec.paragraphs if p.startswith(("Pour identifier", "Toutes choses", "De même",
                                                                  "Par ailleurs", "En ce qui concerne", "Quant"))][:5])
    tabdf = pd.DataFrame(rows)
    image = _foret_diapo(fit, dsg, R, pres, figdir) or (sec.figures[0].path if sec.figures else None)
    note = ("Modèle ajusté sur l'ensemble des variables ; " + {"OR": "OR : rapport de cotes", "IRR": "IRR : rapport de "
            "taux", "β": "β : coefficient"}.get(eff, eff) + f". Seuil : {seuil.texte()}.")
    out, ann = [], []
    usage_tableau = pres.visuels == "tableaux" or (pres.visuels == "mixte" and len(tabdf) <= 8) or image is None
    if usage_tableau and len(tabdf):
        out.append(Diapo("tableau", titre=titre, tableau=tabdf.head(9), partie="Résultats", note_bas=note, notes=notes,
                         puces=puces[:3]))
    elif image is not None:
        out.append(Diapo("image", titre=titre, image=image, puces=puces[:4], partie="Résultats", notes=notes,
                         note_bas=note))
        if len(tabdf):
            ann.append(Diapo("tableau", titre="Résultats détaillés du modèle multivarié", tableau=tabdf.head(10),
                             note_bas=note))
    if fit.kind == "logistique" and sec.tables:
        diag = next((t for t in sec.tables if t.title.startswith("Qualité d'ajustement")), None)
        if diag is not None:
            ann.append(Diapo("tableau", titre="Qualité d'ajustement du modèle", tableau=diag.data.head(8),
                             note_bas="Indicateurs détaillés dans la section consacrée aux méthodes du document."))
    return out, ann


def _diapos_multiniveau(sec: Section, R: Redac, cfg, detail: bool) -> list[Diapo]:
    f = sec.facts
    if "mn.M0.vpc" not in f:
        return []
    noms = {"M0": "Modèle vide", "M1": "Variables individuelles", "M2": "Variables contextuelles"}
    cats = [noms[m] for m in ("M0", "M1", "M2") if f"mn.{m}.vpc" in f]
    vals = [float(f[f"mn.{m}.vpc"]) for m in ("M0", "M1", "M2") if f"mn.{m}.vpc" in f]
    puces = [f"{fmt.num(vals[0], 1)} % de la variabilité se situe entre les contextes dans le modèle vide"]
    if "mn.M0.mor" in f:
        puces.append(f"Rapport de cotes médian : {fmt.num(f['mn.M0.mor'])}" if detail else
                     f"D'un contexte à l'autre, les chances varient en médiane d'un facteur {fmt.num(f['mn.M0.mor'], 1)}")
    if "mn.M1.variation_var_pct" in f:
        puces.append(f"Les caractéristiques individuelles réduisent la variance contextuelle de "
                     f"{fmt.num(f['mn.M1.variation_var_pct'], 1)} %")
    if "mn.M2.variation_var_pct" in f:
        puces.append(f"Au total, {fmt.num(f['mn.M2.variation_var_pct'], 1)} % de la variance contextuelle est "
                     "expliquée")
    titre = f"{fmt.num(vals[0], 1)} % de la variabilité {de(R.y)} se situe entre les contextes"
    notes = _notes(*[p for p in sec.paragraphs if p.startswith(("Le modèle vide", "L'introduction",
                                                                  "Les variables contextuelles"))])
    out = [Diapo("graphique", titre=titre, puces=puces[:4], partie="Résultats",
                 graphique={"categories": cats, "valeurs": vals, "format": "pct",
                            "serie": "Part de la variance entre contextes", "surligne": 0,
                            "axe": "Étape de modélisation"},
                 note_bas="Coefficient de partition de la variance (VPC) à chaque étape de la modélisation.",
                 notes=notes)]
    eff = [p for p in sec.paragraphs if p.startswith(("Dans le modèle complet", "Dans le modèle final",
                                                      "Au niveau contextuel"))]
    if eff:
        cles = [_court(k, 200) for k in sec.key_points[2:5]]
        ctx = next((p for p in eff if p.startswith("Au niveau contextuel")), "")
        encadre = ""
        if ctx.startswith("Au niveau contextuel, aucune"):
            encadre = f"Aucune variable contextuelle n'est associée de manière significative {a(R.y)}"
        elif ctx:
            encadre = _court(ctx, 180)
        if cles:
            out.append(Diapo("texte", titre="Facteurs individuels et contextuels dans le modèle complet",
                             puces=cles[:3], partie="Résultats", priorite=2, encadre=encadre,
                             meta={"etiquette": "Niveau contextuel"}, notes=_notes(*eff)))
    return out


def _diapo_typologie(sec: Section, R: Redac) -> Diapo | None:
    k = sec.facts.get("cah.k")
    tab = next((t for t in sec.tables if t.title == "Description des classes"), None)
    if not k or tab is None:
        return None
    cartes = []
    for _, row in tab.data.iterrows():
        feats = [x.replace(" = ", " : ") for x in str(row.iloc[-1]).split(" ; ")][:2]
        cartes.append((f"{row['Classe']} ({row['Part']})", " ; ".join(feats)))
    return Diapo("cartes", titre=f"La typologie distingue {nombre(int(k), 'profils')} de {R.unite}",
                 cartes=cartes[:4], partie="Résultats", priorite=2,
                 notes=_notes(*[p for p in sec.paragraphs if p.startswith(("La classification", "La classe"))]))


def _diapo_survie(sec: Section, R: Redac, detail: bool) -> Diapo | None:
    if not sec.figures:
        return None
    f = sec.facts
    puces = []
    if not np.isnan(f.get("survie.mediane", np.nan)):
        puces.append(f"Durée médiane : {fmt.num(f['survie.mediane'])}")
    if "survie.logrank_p" in f:
        puces.append(("Courbes significativement différentes" if seuil.significatif(f["survie.logrank_p"]) else
                      "Différences non significatives entre les courbes")
                     + (f" (log-rank : {fmt.p_phrase(f['survie.logrank_p'])})" if detail else ""))
    puces += [_court(k, 180) for k in sec.key_points[:2]]
    titre = sec.figures[0].caption
    m = re.match(r"Courbes de survie de Kaplan-Meier selon (.+)", titre)
    if m and "survie.logrank_p" in f and seuil.significatif(f["survie.logrank_p"]):
        titre = f"Le calendrier de l'événement diffère selon {m.group(1)}"
    return Diapo("image", titre=titre, image=sec.figures[0].path, puces=puces[:4], partie="Résultats", priorite=2,
                 note_bas="Estimateur de Kaplan-Meier.", notes=_notes(*sec.paragraphs[:4]))
