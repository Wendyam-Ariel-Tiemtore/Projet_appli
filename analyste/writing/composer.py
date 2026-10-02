"""Rédaction : assemble les résultats en document académique structuré selon le type demandé."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..stats import fmt
from ..stats.references import REFERENCES, bibliography
from ..stats.results import Figure, Section, Table
from . import guard
from .llm import LLMError, NoProvider, Provider

DOC_TYPES = {
    "article": "Article scientifique",
    "memoire": "Mémoire",
    "rapport_stage": "Rapport de stage",
    "rapport_etude": "Rapport d'étude",
    "note_synthese": "Note de synthèse",
}

TODO = "[À compléter par l'auteur : {}]"


@dataclass
class RequestSpec:
    doc_type: str = "rapport_etude"
    title: str = "Titre de l'étude"
    author: str = ""
    institution: str = ""
    supervisor: str = ""
    date_text: str = ""
    context: str = ""
    data_description: str = ""
    problematique: str = ""
    objectives: list[str] = field(default_factory=list)
    hypotheses: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    english_abstract: bool = True


@dataclass
class Item:
    kind: str  # heading | para | todo | table | figure | pagebreak | toc | bullets
    text: str = ""
    level: int = 1
    table: Table | None = None
    figure: Figure | None = None
    items: list[str] = field(default_factory=list)


@dataclass
class Document:
    spec: RequestSpec
    items: list[Item]
    references: list[str]
    front: dict
    annex: list[Item]
    log: list[str]


SYSTEM = (
    "Tu es un rédacteur scientifique francophone expérimenté en statistique sociale, démographie et santé publique. "
    "Tu rédiges en français académique soutenu, précis et sobre, à la première personne du pluriel de modestie ou "
    "à la forme impersonnelle. Règles impératives :\n"
    "1. N'utilise QUE les informations fournies (résultats, texte de l'auteur, résumés d'articles). N'invente aucun "
    "fait, aucun contexte, aucune statistique.\n"
    "2. N'écris AUCUN nombre qui ne figure pas tel quel dans les informations fournies. En cas de doute, n'écris pas "
    "de nombre.\n"
    "3. Ne cite QUE les références de la liste autorisée, au format auteur-date (Nom, année) ou (Nom et al., année). "
    "N'invente aucune référence.\n"
    "4. Les données sont observationnelles : parle d'association, jamais de cause, d'impact ou d'effet causal.\n"
    "5. Pas de titres, pas de listes à puces, pas de Markdown : des paragraphes séparés par une ligne vide.\n"
    "6. Ne commente pas ta tâche ; écris directement le texte demandé.")


class Writer:
    def __init__(self, provider: Provider | None, allowed: guard.Allowed, log: list[str]):
        self.provider = provider or NoProvider()
        self.allowed = allowed
        self.log = log

    @property
    def active(self) -> bool:
        return not isinstance(self.provider, NoProvider)

    def write(self, label: str, prompt: str, fallback: list[str], max_tokens: int = 1600) -> tuple[list[str], bool]:
        """Renvoie (paragraphes, rédigé_par_ia). Repli déterministe si la vérification échoue."""
        if not self.active:
            return fallback, False
        text = ""
        feedback = ""
        for attempt in range(2):
            try:
                text = self.provider.complete(SYSTEM, prompt + (f"\n\nCorrections exigées :\n{feedback}" if feedback
                                                                  else ""), max_tokens)
            except LLMError as exc:
                self.log.append(f"{label} : {exc} Texte de repli utilisé.")
                return fallback, False
            text = guard.clean_markdown(text)
            chk = guard.check(text, self.allowed)
            if chk.ok and len(text) > 80:
                self.log.append(f"{label} : rédigé par le modèle ({self.provider.name}), vérification réussie"
                                + (" après correction." if attempt else "."))
                return [p.strip() for p in text.split("\n\n") if p.strip()], True
            feedback = chk.feedback() or "Texte trop court."
        self.log.append(f"{label} : la vérification automatique a rejeté le texte du modèle ({feedback[:200]}). "
                        "Texte de repli utilisé.")
        return fallback, False


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def compose(spec: RequestSpec, sections: dict[str, Section], data_info: dict, variables_table: Table,
            privacy_log: list[str], provider: Provider | None, lit_refs: list[str], lit_citations: list[str],
            lit_digest: str, software: dict[str, str]) -> Document:
    log: list[str] = []
    allowed = guard.Allowed()
    for s in sections.values():
        for p in s.paragraphs + s.method_notes + s.warnings:
            allowed.add_text(p)
        for t in s.tables:
            allowed.add_text(t.data.to_string() + " " + t.note)
        for v in s.facts.values():
            allowed.add_value(v)
    for txt in (spec.context, spec.problematique, spec.data_description, " ".join(spec.objectives),
                " ".join(spec.hypotheses), spec.title, lit_digest):
        allowed.add_text(txt or "")
        allowed.add_citations_from_text(txt or "")
    for v in data_info.values():
        allowed.add_value(v)
    for r in REFERENCES.values():
        allowed.add_citation(r.citation)
    for c in lit_citations:
        allowed.add_citation(c)
    w = Writer(provider, allowed, log)

    key_results = _key_results(sections)
    refs_list = "\n".join(sorted(set(lit_citations))) or "(aucune référence bibliographique externe)"
    results_digest = "\n".join(key_results)
    author_text = _author_block(spec)

    items: list[Item] = []
    dt = spec.doc_type
    front: dict = {}

    # --- Résumé ---
    abstract_fb = _abstract_fallback(spec, sections, data_info, key_results)
    abstract, _ = w.write(
        "Résumé",
        f"Rédige le résumé (180 à 250 mots, un seul paragraphe) d'un document de type « {DOC_TYPES[dt]} » intitulé "
        f"« {spec.title} », structuré en contexte, objectif, données et méthodes, principaux résultats, conclusion.\n\n"
        f"{author_text}\n\nPrincipaux résultats (seuls nombres autorisés) :\n{results_digest}\n\n"
        f"Données : {data_info.get('description', '')}",
        abstract_fb, 700)
    front["resume"] = abstract
    front["mots_cles"] = spec.keywords
    if spec.english_abstract and w.active:
        en, ok = w.write(
            "Abstract",
            "Translate the following French abstract into academic English. Keep every number exactly as written "
            "(using the same decimal comma) and do not add any information.\n\n" + "\n\n".join(abstract),
            [], 700)
        front["abstract"] = en if ok else []

    # --- Introduction ---
    intro_fb = _intro_fallback(spec, dt)
    intro, _ = w.write(
        "Introduction",
        f"Rédige l'introduction générale (4 à 6 paragraphes) de ce {DOC_TYPES[dt].lower()} : contexte et "
        f"justification, état de la question en t'appuyant sur les références autorisées, problématique, objectifs, "
        f"hypothèses, puis annonce du plan.\n\n{author_text}\n\nRéférences autorisées et ce qu'elles disent :\n"
        f"{lit_digest or refs_list}\n\nPlan du document : {', '.join(_plan(dt, sections))}.",
        intro_fb, 1800)

    # --- Méthodes ---
    methods: list[Item] = []
    methods.append(Item("heading", "Source et nature des données", 2))
    methods.append(Item("para", spec.data_description) if spec.data_description else
                   Item("todo", TODO.format("source des données, population, mode de collecte, période, "
                                            "plan d'échantillonnage")))
    methods.append(Item("para", data_info.get("description", "")))
    methods.append(Item("heading", "Variables de l'étude", 2))
    methods.append(Item("table", table=variables_table))
    methods.append(Item("heading", "Méthodes d'analyse statistique", 2))
    for key in ("qualite", "descriptif", "bivarie", "multivarie", "multiniveau", "acp", "acm", "cah", "survie",
                "litterature"):
        s = sections.get(key)
        if s:
            for n in s.method_notes:
                methods.append(Item("para", n))
    methods.append(Item("para",
                        "Le seuil de significativité retenu est de 5 %. Les analyses ont été réalisées avec Python "
                        + ", ".join(f"{k} {v}" for k, v in software.items())
                        + " (Seabold et Perktold, 2010 ; Virtanen et al., 2020), avec une graine aléatoire fixée à 42 "
                          "pour les procédures stochastiques."))
    methods.append(Item("heading", "Considérations éthiques et protection des données", 2))
    eth = ("Les données ont été traitées localement, sans transfert vers un service tiers. "
           + " ".join(privacy_log) if privacy_log else
           "Les données ont été traitées localement, sans transfert vers un service tiers.")
    methods.append(Item("para", eth))
    methods.append(Item("todo", TODO.format("avis éthique, consentement des participants, autorisations d'accès aux "
                                            "données")))

    # --- Résultats ---
    results: list[Item] = []
    order = [("qualite", "Qualité des données"), ("descriptif", "Caractéristiques de l'échantillon"),
             ("bivarie", "Facteurs associés : analyse bivariée"), ("multivarie", "Analyse explicative multivariée"),
             ("multiniveau", "Analyse multi-niveaux"), ("acp", "Analyse en composantes principales"),
             ("acm", "Analyse des correspondances multiples"), ("cah", "Typologie"), ("survie", "Analyse de survie")]
    chapters_res: dict[str, list[Item]] = {}
    for key, title in order:
        s = sections.get(key)
        if not s:
            continue
        block = _section_items(s, title, dt)
        chapters_res[key] = block
        results.extend(block)

    # --- Discussion et conclusion ---
    limits = _limits(sections, data_info)
    disc_fb = _discussion_fallback(key_results, limits, bool(lit_citations))
    discussion, _ = w.write(
        "Discussion",
        "Rédige la discussion (5 à 7 paragraphes) : rappel synthétique des principaux résultats, mise en perspective "
        "avec les travaux de la liste autorisée (convergences et divergences, explications plausibles en termes "
        "d'association), forces et limites de l'étude, implications pour la recherche et l'action publique.\n\n"
        f"{author_text}\n\nPrincipaux résultats :\n{results_digest}\n\nLimites identifiées :\n" + "\n".join(limits)
        + f"\n\nRéférences autorisées et ce qu'elles disent :\n{lit_digest or refs_list}",
        disc_fb, 2200)
    concl_fb = _conclusion_fallback(spec, key_results)
    conclusion, _ = w.write(
        "Conclusion",
        "Rédige la conclusion générale (2 à 3 paragraphes) : réponse à la problématique, principaux apports, "
        "recommandations prudentes et perspectives de recherche.\n\n"
        f"{author_text}\n\nPrincipaux résultats :\n{results_digest}", concl_fb, 1000)

    # --- Revue de littérature ---
    lit_items = _section_items(sections["litterature"], "Revue de la littérature", dt) if "litterature" in sections \
        else [Item("heading", "Revue de la littérature", 1), Item("todo", TODO.format("revue de la littérature"))]

    # --- Assemblage selon le type de document ---
    def paras(ps):
        return [Item("todo", p) if p.startswith("[À compléter") else Item("para", p) for p in ps]

    if dt == "article":
        items += [Item("heading", "Introduction", 1), *paras(intro)]
        items += _demote(lit_items, 1)
        items += [Item("heading", "Données et méthodes", 1), *methods]
        items += [Item("heading", "Résultats", 1), *_demote(results, 1)]
        items += [Item("heading", "Discussion", 1), *paras(discussion)]
        items += [Item("heading", "Conclusion", 1), *paras(conclusion)]
    elif dt == "memoire":
        items += [Item("heading", "Introduction générale", 1), *paras(intro)]
        items += [Item("heading", "Chapitre 1 — Cadre théorique et conceptuel", 1), *_demote(lit_items, 1),
                  Item("heading", "Cadre conceptuel et hypothèses", 2),
                  *(Item("bullets", items=spec.hypotheses) for _ in [0] if spec.hypotheses),
                  Item("todo", TODO.format("schéma du cadre conceptuel et définition des concepts"))]
        items += [Item("heading", "Chapitre 2 — Méthodologie", 1), *methods]
        items += [Item("heading", "Chapitre 3 — Caractéristiques de la population étudiée", 1)]
        for k in ("qualite", "descriptif"):
            items += _demote(chapters_res.get(k, []), 1)
        items += [Item("heading", "Chapitre 4 — Facteurs associés", 1)]
        items += _demote(chapters_res.get("bivarie", []), 1)
        expl = [k for k in ("multivarie", "multiniveau", "acp", "acm", "cah", "survie") if k in chapters_res]
        if expl:
            items += [Item("heading", "Chapitre 5 — Analyse explicative et typologique", 1)]
            for k in expl:
                items += _demote(chapters_res[k], 1)
        items += [Item("heading", "Discussion", 1), *paras(discussion)]
        items += [Item("heading", "Conclusion générale et recommandations", 1), *paras(conclusion)]
    elif dt == "rapport_stage":
        items += [Item("heading", "Introduction générale", 1), *paras(intro)]
        items += [Item("heading", "Première partie — Présentation de la structure d'accueil", 1),
                  Item("todo", TODO.format("historique, missions, organisation et service d'accueil")),
                  Item("todo", TODO.format("missions confiées et déroulement du stage"))]
        items += [Item("heading", "Deuxième partie — Cadre théorique", 1), *_demote(lit_items, 1)]
        items += [Item("heading", "Troisième partie — Données et méthodes", 1), *methods]
        items += [Item("heading", "Quatrième partie — Résultats et discussion", 1), *_demote(results, 1),
                  Item("heading", "Discussion", 2), *paras(discussion)]
        items += [Item("heading", "Apport du stage", 1),
                  Item("todo", TODO.format("compétences acquises, difficultés rencontrées, apports personnels"))]
        items += [Item("heading", "Conclusion", 1), *paras(conclusion)]
    elif dt == "note_synthese":
        items += [Item("heading", "Messages clés", 1), Item("bullets", items=key_results[:6] or ["–"])]
        items += [Item("heading", "Contexte et objectif", 1), *paras(intro[:2])]
        items += [Item("heading", "Principaux résultats", 1)]
        for k in ("descriptif", "multivarie", "multiniveau"):
            s = sections.get(k)
            if s and s.tables:
                items.append(Item("table", table=s.tables[0]))
        items += [Item("heading", "Méthode en bref", 1), *[i for i in methods if i.kind == "para"][:3]]
        items += [Item("heading", "Limites", 1), Item("bullets", items=limits)]
    else:  # rapport d'étude
        items += [Item("heading", "Résumé exécutif", 1), Item("bullets", items=key_results[:8] or ["–"])]
        items += [Item("heading", "Contexte et objectifs", 1), *paras(intro)]
        items += _demote(lit_items, 1)
        items += [Item("heading", "Méthodologie", 1), *methods]
        items += [Item("heading", "Résultats", 1), *_demote(results, 1)]
        items += [Item("heading", "Discussion", 1), *paras(discussion)]
        items += [Item("heading", "Conclusions et recommandations", 1), *paras(conclusion)]

    # --- Références ---
    keys = set()
    for s in sections.values():
        keys |= s.refs
    keys |= {"seabold2010", "virtanen2020"}
    refs = sorted(set(bibliography(keys)) | set(lit_refs), key=lambda x: _sort_key(x))
    annex = [Item("heading", "Annexe — Paramètres de reproductibilité", 1),
             Item("para", "Les paramètres ci-dessous permettent de reproduire à l'identique l'ensemble des analyses."),
             Item("para", json.dumps(data_info.get("parameters", {}), ensure_ascii=False, indent=1)),
             Item("heading", "Annexe — Journal de la rédaction assistée", 1),
             Item("bullets", items=log or ["Aucun modèle de langage n'a été utilisé : tous les textes sont produits "
                                           "par les règles de l'application."]),
             Item("heading", "Annexe — Déclaration d'utilisation d'outils", 1),
             Item("para", "Les analyses statistiques, les tableaux, les figures et une partie des textes de ce "
                          "document ont été produits à l'aide de l'application « Analyste académique ». Les passages "
                          "marqués « À compléter par l'auteur » relèvent de la seule responsabilité de l'auteur. "
                          "Conformément aux règles d'intégrité académique, l'auteur vérifie chaque résultat, assume "
                          "l'interprétation finale et déclare l'usage de cet outil selon les exigences de son "
                          "institution.")]
    return Document(spec=spec, items=items, references=refs, front=front, annex=annex, log=log)


def _sort_key(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def _demote(items: list[Item], by: int) -> list[Item]:
    out = []
    for it in items:
        if it.kind == "heading":
            out.append(Item("heading", it.text, min(it.level + by, 4)))
        else:
            out.append(it)
    return out


def _section_items(s: Section, title: str, dt: str) -> list[Item]:
    out = [Item("heading", title, 1)]
    paras = list(s.paragraphs)
    # Paragraphe introductif, puis tableaux et figures, puis interprétation
    if paras:
        out.append(Item("para", paras[0]) if not paras[0].startswith("[À") else Item("todo", paras[0]))
    for w in s.warnings:
        out.append(Item("para", "Avertissement : " + w))
    tables = s.tables if dt != "note_synthese" else s.tables[:1]
    for t in tables:
        out.append(Item("table", table=t))
    for f in s.figures[: (2 if dt == "article" else 6)]:
        out.append(Item("figure", figure=f))
    for p in paras[1:]:
        out.append(Item("todo", p) if p.startswith("[À") else Item("para", p))
    return out


def _key_results(sections: dict[str, Section]) -> list[str]:
    out = []
    for key in ("multiniveau", "multivarie", "bivarie", "survie", "acp", "cah"):
        s = sections.get(key)
        if not s:
            continue
        for p in s.paragraphs:
            if ("Toutes choses égales" in p or "Dans le modèle" in p or "Le modèle vide" in p
                    or "L'association entre" in p or "La composante" in p or "classes" in p):
                out.append(p)
        if len(out) >= 10:
            break
    return out[:12]


def _author_block(spec: RequestSpec) -> str:
    parts = [f"Titre : {spec.title}"]
    if spec.context:
        parts.append(f"Contexte fourni par l'auteur : {spec.context}")
    if spec.problematique:
        parts.append(f"Problématique : {spec.problematique}")
    if spec.objectives:
        parts.append("Objectifs : " + " ; ".join(spec.objectives))
    if spec.hypotheses:
        parts.append("Hypothèses : " + " ; ".join(spec.hypotheses))
    return "\n".join(parts)


def _plan(dt: str, sections: dict) -> list[str]:
    return {"article": ["la revue de la littérature", "les données et méthodes", "les résultats", "la discussion"],
            "memoire": ["le cadre théorique", "la méthodologie", "les caractéristiques de la population étudiée",
                        "les facteurs associés", "l'analyse explicative", "la discussion"],
            "rapport_stage": ["la structure d'accueil", "le cadre théorique", "les données et méthodes",
                              "les résultats et leur discussion", "l'apport du stage"],
            }.get(dt, ["le contexte", "la méthodologie", "les résultats", "la discussion"])


def _abstract_fallback(spec, sections, data_info, key_results) -> list[str]:
    meth = ["des analyses descriptives", "des tests bivariés avec correction pour les tests multiples"]
    if "multivarie" in sections:
        meth.append("une modélisation multivariée")
    if "multiniveau" in sections:
        meth.append("des modèles multi-niveaux")
    if "acp" in sections or "acm" in sections:
        meth.append("des analyses factorielles")
    if "survie" in sections:
        meth.append("une analyse de survie")
    obj = spec.objectives[0] if spec.objectives else (spec.problematique or TODO.format("objectif de l'étude"))
    res = " ".join(_shorten(k) for k in key_results[:3]) or TODO.format("principaux résultats")
    return [f"Objectif. {obj.rstrip('.')}. Données et méthodes. L'étude porte sur "
            f"{fmt.integer(data_info.get('n', 0))} observations ; elle mobilise " + ", ".join(meth[:-1])
            + (f" et {meth[-1]}" if len(meth) > 1 else meth[0]) + f". Résultats. {res} Conclusion. "
            + TODO.format("conclusion et portée des résultats")]


def _shorten(p: str, limit: int = 340) -> str:
    """Garde les phrases entières tenant dans la limite (au moins la première)."""
    p = re.sub(r"\s*\(([^()]*IC à 95 %[^()]*)\)", "", p)
    sents = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-ÝL«])", p)
    out = sents[0]
    for s_ in sents[1:]:
        if len(out) + len(s_) + 1 > limit:
            break
        out += " " + s_
    return out


def _intro_fallback(spec, dt) -> list[str]:
    out = []
    if spec.context:
        out += [p.strip() for p in spec.context.split("\n") if p.strip()]
    else:
        out.append(TODO.format("contexte et justification de l'étude"))
    out.append(TODO.format("état de la question : principaux travaux et lacune identifiée"))
    if spec.problematique:
        out.append(f"Dans ce contexte, la question centrale de ce travail est la suivante : {spec.problematique.rstrip('?. ')} ?")
    else:
        out.append(TODO.format("problématique"))
    if spec.objectives:
        out.append("L'objectif général est de " + _lower_first(spec.objectives[0].rstrip(".")) + "."
                   + (" De manière spécifique, il s'agit de " + " ; ".join(_lower_first(o.rstrip(".")) for o in
                                                                          spec.objectives[1:]) + "."
                      if len(spec.objectives) > 1 else ""))
    if spec.hypotheses:
        out.append("Les hypothèses testées sont les suivantes : " + " ; ".join(
            f"(H{i + 1}) {_lower_first(h.rstrip('.'))}" for i, h in enumerate(spec.hypotheses)) + ".")
    plan = _plan(dt, {})
    out.append("Le document présente successivement " + ", ".join(plan[:-1]) + f" et {plan[-1]} ; une conclusion "
               "récapitule les apports et les perspectives de ce travail.")
    return out


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s else s


def _limits(sections: dict[str, Section], data_info: dict) -> list[str]:
    out = ["Les données sont observationnelles et, sauf dispositif longitudinal, transversales : les associations "
           "mises en évidence ne peuvent pas être interprétées comme des relations de cause à effet."]
    for s in sections.values():
        for w in s.warnings:
            out.append(w)
    m = sections.get("multivarie")
    if m and m.facts.get("modele.pct_exclus", 0) > 5:
        out.append(f"L'analyse multivariée porte sur les cas complets, ce qui exclut "
                   f"{fmt.num(m.facts['modele.pct_exclus'], 1)} % des observations et peut introduire un biais si les "
                   "valeurs manquantes ne sont pas aléatoires.")
    if data_info.get("weighted") is False:
        out.append("Les estimations ne tiennent pas compte d'un éventuel plan de sondage complexe (stratification, "
                   "pondération) : les intervalles de confiance peuvent être sous-estimés.")
    return out


def _discussion_fallback(key_results, limits, has_lit) -> list[str]:
    out = ["Les principaux résultats de cette étude peuvent être résumés comme suit. "
           + " ".join(_shorten(k) for k in key_results[:4])]
    out.append(TODO.format("mise en perspective de ces résultats avec la littérature : convergences, divergences et "
                           "explications possibles" + (" (voir les tableaux de synthèse de la revue de littérature)"
                                                       if has_lit else "")))
    out.append("Plusieurs limites doivent être soulignées. " + " ".join(limits))
    out.append(TODO.format("implications pour la recherche et pour l'action"))
    return out


def _conclusion_fallback(spec, key_results) -> list[str]:
    q = spec.problematique.rstrip("?. ") if spec.problematique else None
    first = (f"Ce travail visait à répondre à la question suivante : {q} ? " if q else "") + \
        "Les analyses conduites apportent les éléments de réponse suivants. " + \
        " ".join(_shorten(k) for k in key_results[:3])
    return [first, TODO.format("recommandations et perspectives de recherche")]
