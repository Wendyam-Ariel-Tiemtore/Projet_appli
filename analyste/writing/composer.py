"""Rédaction : assemble les résultats en document académique structuré selon le type demandé."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..stats import fmt, seuil
from ..stats.references import REFERENCES, bibliography
from ..stats.results import Figure, Section, Table
from . import guard
from .llm import LLMError, NoProvider, Provider
from .phrases import elision
from .style import a as contracte_a
from .style import de as contracte_de
from .style import nettoyer, nombre, ordinal, titre

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
    hypotheses_vars: list[dict] = field(default_factory=list)  # [{"variable": ..., "sens": positif|negatif|association}]
    keywords: list[str] = field(default_factory=list)
    english_abstract: bool = True
    style_sample: str = ""  # extrait rédigé par l'auteur, transmis au seul modèle de langage choisi
    presentation: dict = field(default_factory=dict)  # options de la présentation (writing/presentation.py)


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
    "Tu rédiges des passages de mémoires et de rapports d'étude en statistique sociale, démographie et santé "
    "publique, dans le style d'un étudiant de master francophone rigoureux (Afrique de l'Ouest, France). Règles "
    "impératives :\n"
    "1. N'utilise QUE les informations fournies (résultats, texte de l'auteur, résumés d'articles). N'invente aucun "
    "fait, aucun contexte, aucune statistique.\n"
    "2. N'écris AUCUN nombre qui ne figure pas tel quel dans les informations fournies. En cas de doute, n'écris pas "
    "de nombre.\n"
    "3. Ne cite QUE les références de la liste autorisée, au format auteur-date (Nom, année) ou (Nom et al., année). "
    "N'invente aucune référence.\n"
    "4. Les données sont observationnelles : parle d'association, jamais de cause, d'impact ou d'effet causal.\n"
    "5. Pas de titres, pas de listes à puces, pas de Markdown : des paragraphes séparés par une ligne vide.\n"
    "6. Ne commente pas ta tâche ; écris directement le texte demandé.\n"
    "Style attendu, qui doit être celui d'un mémoire écrit par une personne et non par un outil :\n"
    "- n'utilise JAMAIS de tiret long (—) ni de demi-cadratin (–) comme ponctuation ; emploie la virgule, les "
    "deux-points ou les parenthèses ;\n"
    "- écris à la première personne du pluriel (« nous constatons que », « nous notons », « nous pouvons donc dire "
    "que ») ou à la forme impersonnelle (« il ressort que », « il convient de préciser que ») ;\n"
    "- relie les phrases par des connecteurs sobres et variés : En effet, Par ailleurs, Ainsi, Aussi, Cependant, "
    "Néanmoins, En outre, De plus, Quant à, En ce qui concerne, Pour ce faire, En somme ;\n"
    "- désigne les variables par un groupe nominal avec article (« le niveau d'instruction »), sans guillemets ; "
    "réserve les guillemets français (« ») aux modalités ;\n"
    "- pour un rapport de cotes, écris « x fois plus de chances » s'il est supérieur à 1 et « y % moins de chances » "
    "s'il est inférieur à 1, toutes choses égales par ailleurs ;\n"
    "- phrases de longueur moyenne, ton factuel et mesuré ; pas d'emphase, pas de formules toutes faites.\n"
    "Expressions à proscrire : « crucial », « essentiel » employé comme intensif, « mettre en lumière », « souligner "
    "l'importance », « jouer un rôle clé », « s'inscrire dans », « dans un contexte où », « il est important de "
    "noter », « véritable », « levier », « paysage », « naviguer », « holistique », « en définitive », « force est "
    "de constater », les énumérations rhétoriques en trois termes et les phrases qui commencent par « Ainsi donc ».")

STYLE_UTILISATEUR = ("\n\nVoici un extrait rédigé par l'auteur lui-même. Imite sa grammaire, ses tournures et son "
                     "rythme (sans reprendre son contenu ni ses chiffres) :\n<<<\n{}\n>>>")


class Writer:
    def __init__(self, provider: Provider | None, allowed: guard.Allowed, log: list[str], style_sample: str = ""):
        self.provider = provider or NoProvider()
        self.allowed = allowed
        self.log = log
        sample = (style_sample or "").strip()[:2500]
        self.system = SYSTEM + (STYLE_UTILISATEUR.format(sample) if sample else "")

    @property
    def active(self) -> bool:
        return not isinstance(self.provider, NoProvider)

    def write(self, label: str, prompt: str, fallback: list[str], max_tokens: int = 1600) -> tuple[list[str], bool]:
        """Renvoie (paragraphes, rédigé_par_ia). Repli déterministe si la vérification échoue."""
        fallback = [nettoyer(p) for p in fallback]
        if not self.active:
            return fallback, False
        text = ""
        feedback = ""
        for attempt in range(2):
            try:
                text = self.provider.complete(self.system, prompt + (f"\n\nCorrections exigées :\n{feedback}"
                                                                      if feedback else ""), max_tokens)
            except LLMError as exc:
                self.log.append(f"{label} : {exc} Texte de repli utilisé.")
                return fallback, False
            text = guard.clean_markdown(text)
            text = "\n\n".join(nettoyer(p) for p in text.split("\n\n"))
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
            lit_digest: str, software: dict[str, str], style_sample: str = "") -> Document:
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
    w = Writer(provider, allowed, log, style_sample or spec.style_sample)

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
    intro_fb = _intro_fallback(spec, dt, sections)
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
                "fiabilite", "hypotheses", "litterature"):
        s = sections.get(key)
        if s:
            for n in s.method_notes:
                methods.append(Item("para", n))
    methods.append(Item("para",
                        f"Le seuil de signification retenu est de {seuil.texte()}. Les analyses ont été réalisées avec "
                        "Python "
                        + ", ".join(f"{k} {v}" for k, v in software.items())
                        + " (Seabold et Perktold, 2010 ; Virtanen et al., 2020), avec une graine aléatoire fixée à 42 "
                          "pour les procédures stochastiques."))
    methods.append(Item("heading", "Considérations éthiques et protection des données", 2))
    eth = "Les données ont été traitées localement, sans transfert vers un service tiers." + _privacy_text(privacy_log)
    methods.append(Item("para", eth))
    methods.append(Item("todo", TODO.format("avis éthique, consentement des participants, autorisations d'accès aux "
                                            "données")))

    # --- Résultats ---
    results: list[Item] = []
    order = [("qualite", "Qualité des données"), ("descriptif", "Caractéristiques de l'échantillon"),
             ("bivarie", "Facteurs associés : analyse bivariée"), ("multivarie", "Analyse explicative multivariée"),
             ("multiniveau", "Analyse multi-niveaux"), ("acp", "Analyse en composantes principales"),
             ("acm", "Analyse des correspondances multiples"), ("cah", "Typologie"), ("survie", "Analyse de survie"),
             ("fiabilite", "Fiabilité des résultats")]
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

    hyp_items = _section_items(sections["hypotheses"], "Vérification des hypothèses", dt) \
        if "hypotheses" in sections else []

    # --- Assemblage selon le type de document ---
    def paras(ps):
        return [Item("todo", p) if p.startswith("[À compléter") else Item("para", p) for p in ps]

    if dt == "article":
        items += [Item("heading", "Introduction", 1), *paras(intro)]
        items += _demote(lit_items, 1)
        items += [Item("heading", "Données et méthodes", 1), *methods]
        items += [Item("heading", "Résultats", 1), *_demote(results, 1), *_demote(hyp_items, 1)]
        items += [Item("heading", "Discussion", 1), *paras(discussion)]
        items += [Item("heading", "Conclusion", 1), *paras(conclusion)]
    elif dt == "memoire":
        items += [Item("heading", "Introduction générale", 1), *paras(intro)]
        chapitres = [("Cadre théorique et conceptuel",
                      [*_demote(lit_items, 1), Item("heading", "Cadre conceptuel et hypothèses", 2),
                       *(Item("bullets", items=spec.hypotheses) for _ in [0] if spec.hypotheses),
                       Item("todo", TODO.format("schéma du cadre conceptuel et définition des concepts"))]),
                     ("Méthodologie", methods),
                     ("Caractéristiques de la population étudiée",
                      [it for k in ("qualite", "descriptif") for it in _demote(chapters_res.get(k, []), 1)])]
        if "bivarie" in chapters_res:
            chapitres.append(("Facteurs associés", _demote(chapters_res["bivarie"], 1)))
        expl = [k for k in ("multivarie", "multiniveau", "acp", "acm", "cah", "survie", "fiabilite")
                if k in chapters_res]
        if expl:
            chapitres.append(("Analyse explicative et typologique",
                              [it for k in expl for it in _demote(chapters_res[k], 1)]))
        for i, (titre_chap, contenu) in enumerate(chapitres, start=1):
            items += [Item("heading", f"Chapitre {i} : {titre_chap}", 1), *contenu]
        items += hyp_items
        items += [Item("heading", "Discussion", 1), *paras(discussion)]
        items += [Item("heading", "Conclusion générale et recommandations", 1), *paras(conclusion)]
    elif dt == "rapport_stage":
        items += [Item("heading", "Introduction générale", 1), *paras(intro)]
        items += [Item("heading", "Première partie : Présentation de la structure d'accueil", 1),
                  Item("todo", TODO.format("historique, missions, organisation et service d'accueil")),
                  Item("todo", TODO.format("missions confiées et déroulement du stage"))]
        items += [Item("heading", "Deuxième partie : Cadre théorique", 1), *_demote(lit_items, 1)]
        items += [Item("heading", "Troisième partie : Données et méthodes", 1), *methods]
        items += [Item("heading", "Quatrième partie : Résultats et discussion", 1), *_demote(results, 1),
                  *_demote(hyp_items, 1), Item("heading", "Discussion", 2), *paras(discussion)]
        items += [Item("heading", "Apport du stage", 1),
                  Item("todo", TODO.format("compétences acquises, difficultés rencontrées, apports personnels"))]
        items += [Item("heading", "Conclusion", 1), *paras(conclusion)]
    elif dt == "note_synthese":
        items += [Item("heading", "Messages clés", 1), Item("bullets", items=key_results[:6] or [TODO.format("messages clés")])]
        items += [Item("heading", "Contexte et objectif", 1), *paras(intro[:2])]
        items += [Item("heading", "Principaux résultats", 1)]
        for k in ("descriptif", "multivarie", "multiniveau"):
            s = sections.get(k)
            if s and s.tables:
                items.append(Item("table", table=s.tables[0]))
        items += [Item("heading", "Méthode en bref", 1), *[i for i in methods if i.kind == "para"][:3]]
        items += [Item("heading", "Limites", 1), Item("bullets", items=limits)]
    else:  # rapport d'étude
        items += [Item("heading", "Résumé exécutif", 1), Item("bullets", items=key_results[:8] or [TODO.format("principaux résultats")])]
        items += [Item("heading", "Contexte et objectifs", 1), *paras(intro)]
        items += _demote(lit_items, 1)
        items += [Item("heading", "Méthodologie", 1), *methods]
        items += [Item("heading", "Résultats", 1), *_demote(results, 1), *_demote(hyp_items, 1)]
        items += [Item("heading", "Discussion", 1), *paras(discussion)]
        items += [Item("heading", "Conclusions et recommandations", 1), *paras(conclusion)]

    # --- Références ---
    keys = set()
    for s in sections.values():
        keys |= s.refs
    keys |= {"seabold2010", "virtanen2020"}
    refs = sorted(set(bibliography(keys)) | set(lit_refs), key=lambda x: _sort_key(x))
    from .lexique import lecture_simple, lexique_utilise
    fia = sections.get("fiabilite")
    clair = lecture_simple(key_results, fia.extra.get("globale") if fia else None, int(data_info.get("n", 0)),
                           data_info.get("unite") or "observations")
    corpus = " ".join([i.text for i in items if i.text] + [x for i in items for x in (i.items or [])]
                      + [f"{i.table.title} {i.table.note}" for i in items if i.table is not None])
    notions = lexique_utilise(corpus)
    annex = [Item("heading", "Annexe 1 : Lecture des résultats en langage simple", 1),
             Item("para", "Cette annexe s'adresse aux lecteurs qui ne sont pas familiers des méthodes statistiques."),
             *[Item("para", t) for t in clair]]
    if notions:
        annex += [Item("heading", "Annexe 2 : Lexique des notions employées", 1),
                  Item("bullets", items=[f"{t} : {d}" for t, d in notions])]
    k0 = sum(1 for i in annex if i.kind == "heading")
    annex += [Item("heading", f"Annexe {k0 + 1} : Paramètres de reproductibilité", 1),
             Item("para", "Les paramètres ci-dessous permettent de reproduire à l'identique l'ensemble des analyses."),
             Item("para", json.dumps(data_info.get("parameters", {}), ensure_ascii=False, indent=1)),
             Item("heading", f"Annexe {k0 + 2} : Journal de la rédaction assistée", 1),
             Item("bullets", items=log or ["Aucun modèle de langage n'a été utilisé : tous les textes sont produits "
                                           "par les règles de l'application."]),
             Item("heading", f"Annexe {k0 + 3} : Déclaration d'utilisation d'outils", 1),
             Item("para", "Les analyses statistiques, les tableaux, les figures et une partie des textes de ce "
                          "document ont été produits à l'aide de l'application « Analyste académique ». Les passages "
                          "marqués « À compléter par l'auteur » relèvent de la seule responsabilité de l'auteur. "
                          "Conformément aux règles d'intégrité académique, l'auteur vérifie chaque résultat, assume "
                          "l'interprétation finale et déclare l'usage de cet outil selon les exigences de son "
                          "institution.")]
    items = [_clean_item(i) for i in items]
    annex = [_clean_item(i) for i in annex]
    front["resume"] = [nettoyer(p) for p in front.get("resume", [])]
    return Document(spec=spec, items=items, references=refs, front=front, annex=annex, log=log)


def _clean_item(it: Item) -> Item:
    """Typographie finale : aucun tiret long ni demi-cadratin dans le texte ni dans les titres."""
    if it.kind == "heading":
        it.text = titre(it.text)
    elif it.kind in ("para", "todo"):
        if not it.text.lstrip().startswith("{"):  # paramètres JSON laissés tels quels
            it.text = nettoyer(it.text)
    elif it.kind == "bullets":
        it.items = [nettoyer(x) for x in it.items]
    if it.table is not None:
        it.table.title = titre(it.table.title)
        it.table.note = nettoyer(it.table.note)
    if it.figure is not None:
        it.figure.caption = titre(it.figure.caption)
    return it


def _privacy_text(privacy_log: list[str]) -> str:
    """Regroupe le journal de protection des identifiants en une ou deux phrases."""
    from .style import enumeration
    suppr = [m.group(1) for x in privacy_log if (m := re.search(r"« (.+?) », identifiant personnel, a été supprimée", x))]
    pseudo = [m.group(1) for x in privacy_log if (m := re.search(r"« (.+?) » a été pseudonymisée", x))]
    autres = [x for x in privacy_log if not re.search(r"supprimée avant toute analyse|a été pseudonymisée", x)]
    out = ""
    if len(suppr) == 1:
        out += f" La variable « {suppr[0]} », identifiant personnel, a été supprimée avant toute analyse."
    elif suppr:
        out += (" Les variables " + enumeration([f"« {v} »" for v in suppr]) + ", qui constituent des identifiants "
                "personnels, ont été supprimées avant toute analyse.")
    if len(pseudo) == 1:
        out += (f" La variable « {pseudo[0]} » a par ailleurs été pseudonymisée, chaque valeur étant remplacée par un "
                "code HMAC-SHA256.")
    elif pseudo:
        out += (" Les variables " + enumeration([f"« {v} »" for v in pseudo]) + " ont par ailleurs été "
                "pseudonymisées, chaque valeur étant remplacée par un code HMAC-SHA256.")
    return out + "".join(" " + x for x in autres)


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
    """Phrases de synthèse fournies par chaque module (résumé, discussion, conclusion)."""
    out = []
    for key in ("hypotheses", "descriptif", "multiniveau", "multivarie", "bivarie", "survie", "acp", "acm", "cah",
                "fiabilite"):
        s = sections.get(key)
        if s:
            out.extend(s.key_points)
    if "multiniveau" in sections and "multivarie" in sections:
        # les effets ajustés du modèle multi-niveaux priment : on évite de les répéter deux fois
        mv = set(sections["multivarie"].key_points)
        out = [p for p in out if p not in mv] + [p for p in out if p in mv][:1]
    return list(dict.fromkeys(out))[:12]


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
    """Chapitres (mémoire) ou parties (rapport de stage) effectivement présents dans le document."""
    if dt == "memoire":
        plan = ["le cadre théorique et conceptuel", "la méthodologie", "les caractéristiques de la population étudiée"]
        if "bivarie" in sections:
            plan.append("les facteurs associés")
        if any(k in sections for k in ("multivarie", "multiniveau", "acp", "acm", "cah", "survie")):
            plan.append("l'analyse explicative et typologique")
        return plan
    return {"article": ["la revue de la littérature", "les données et méthodes", "les résultats", "la discussion"],
            "rapport_stage": ["la structure d'accueil", "le cadre théorique", "les données et méthodes",
                              "les résultats et leur discussion"],
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
    debut = (f"Cette étude a pour objectif {elision('de', _lower_first(obj.rstrip('.')))}. " if spec.objectives else
             f"{obj.rstrip('.')}. ")
    meth_txt = ", ".join(meth[:-1]) + f" et {meth[-1]}" if len(meth) > 1 else meth[0]
    if key_results:
        res = "Les résultats montrent que " + _lower_first(res)
    return [debut + f"Elle porte sur {nombre(int(data_info.get('n', 0)), 'observations', True)} et mobilise "
            f"{meth_txt}. {res} " + TODO.format("conclusion et portée des résultats")]


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


def _intro_fallback(spec, dt, sections: dict | None = None) -> list[str]:
    sections = sections or {}
    out = []
    if spec.context:
        out += [p.strip() for p in spec.context.split("\n") if p.strip()]
    else:
        out.append(TODO.format("contexte et justification de l'étude"))
    out.append(TODO.format("état de la question : principaux travaux et lacune identifiée"))
    if spec.problematique:
        out.append("Dans ce contexte, la question centrale de ce travail est la suivante : "
                   f"{_lower_first(spec.problematique.rstrip('?. '))} ?")
    else:
        out.append(TODO.format("problématique"))
    if spec.objectives:
        out.append("L'objectif général de cette étude est " + elision("de", _lower_first(spec.objectives[0].rstrip(".")))
                   + "." + (" De manière spécifique, il s'agit " + " ; ".join(
                       elision("de", _lower_first(o.rstrip("."))) for o in spec.objectives[1:]) + "."
                       if len(spec.objectives) > 1 else ""))
    if spec.hypotheses:
        out.append("Pour atteindre ces objectifs, nous formulons les hypothèses suivantes : " + " ; ".join(
            f"(H{i + 1}) {_lower_first(h.rstrip('.'))}" for i, h in enumerate(spec.hypotheses)) + ".")
    plan = _plan(dt, sections)
    unite = {"memoire": "chapitres", "rapport_stage": "parties"}.get(dt, "sections")
    doc = {"memoire": "le présent mémoire", "rapport_stage": "le présent rapport", "article": "cet article",
           "note_synthese": "la présente note"}.get(dt, "le présent rapport")
    if dt in ("memoire", "rapport_stage"):
        fem = unite == "parties"
        verbes = ["porte sur", "présente", "est consacré" + ("e" if fem else "") + " à", "expose", "aborde", "traite de"]
        phrases = []
        for i, item in enumerate(plan):
            v = verbes[i % len(verbes)]
            if v.endswith(" à"):
                phr = f"{v[:-2]} {contracte_a(item)}"
            elif v.endswith(" de"):
                phr = f"{v[:-3]} {contracte_de(item)}"
            else:
                phr = f"{v} {item}"
            art = (f"la {ordinal(i + 1, True)}" if fem else f"le {ordinal(i + 1)}") if i else (
                "la première" if fem else "le premier")
            phrases.append(f"{art} {phr}")
        corps = phrases[0] if len(phrases) == 1 else ", ".join(phrases[:-1]) + f" et {phrases[-1]}"
        fin = ("Une discussion des résultats et une conclusion générale viennent enfin compléter ce travail."
               if dt == "memoire" else
               "Un bilan des apports du stage et une conclusion générale viennent enfin clore ce travail.")
        out.append(f"Pour ce faire, {doc} s'articule autour de {nombre(len(plan), unite, fem)}. {_cap(corps)}. {fin}")
    else:
        out.append(f"Pour ce faire, {doc} aborde successivement " + ", ".join(plan[:-1]) + f" et {plan[-1]}. "
                   "Une conclusion récapitule enfin les apports et les perspectives de ce travail.")
    return out


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _lower_first(s: str) -> str:
    from .style import _lower_first as lf
    return lf(s) if s else s


def _limits(sections: dict[str, Section], data_info: dict) -> list[str]:
    out = ["Les données sont observationnelles et, sauf dispositif longitudinal, transversales : les associations "
           "mises en évidence ne peuvent donc pas être interprétées comme des relations de cause à effet."]
    for s in sections.values():
        for w in s.warnings:
            out.append(w)
    m = sections.get("multivarie")
    if m and m.facts.get("modele.pct_exclus", 0) > 5:
        out.append(f"Par ailleurs, l'analyse multivariée porte sur les cas complets, ce qui exclut "
                   f"{fmt.num(m.facts['modele.pct_exclus'], 1)} % des observations et peut introduire un biais si les "
                   "valeurs manquantes ne sont pas aléatoires.")
    if data_info.get("weighted") is False:
        out.append("En outre, les estimations ne tiennent pas compte d'un éventuel plan de sondage complexe "
                   "(stratification, pondération), de sorte que les intervalles de confiance peuvent être "
                   "sous-estimés.")
    return out


def _discussion_fallback(key_results, limits, has_lit) -> list[str]:
    out = ["Au terme de nos analyses, plusieurs résultats méritent d'être soulignés. "
           + " ".join(_shorten(k) for k in key_results[:4])]
    out.append(TODO.format("mise en perspective de ces résultats avec la littérature : convergences, divergences et "
                           "explications possibles" + (" (voir les tableaux de synthèse de la revue de littérature)"
                                                       if has_lit else "")))
    out.append("Ce travail comporte toutefois certaines limites. " + " ".join(limits))
    out.append(TODO.format("implications pour la recherche et pour l'action"))
    return out


def _conclusion_fallback(spec, key_results) -> list[str]:
    q = spec.problematique.rstrip("?. ") if spec.problematique else None
    first = (f"Ce travail avait pour objectif de répondre à la question suivante : {q} ? " if q else "") + \
        "Au terme de nos analyses, des éléments de réponse se dégagent. " + \
        " ".join(_shorten(k) for k in key_results[:3])
    return [first, TODO.format("recommandations et perspectives de recherche")]
