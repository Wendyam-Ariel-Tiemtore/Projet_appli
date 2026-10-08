"""Lexique des notions statistiques et lecture des résultats en langage simple.

Le lexique du document ne retient que les notions effectivement employées dans le texte. Les définitions sont
rédigées pour une personne qui n'a jamais suivi de cours de statistique.
"""

from __future__ import annotations

import re

# terme : (motifs déclencheurs, définition)
LEXIQUE: dict[str, tuple[tuple[str, ...], str]] = {
    "Variable dépendante": (("variable dépendante",),
                            "Le phénomène que l'on cherche à expliquer (par exemple l'utilisation de la contraception)."),
    "Variable explicative": (("variable explicative", "variables explicatives"),
                             "Une caractéristique dont on examine le lien avec le phénomène étudié (âge, instruction…)."),
    "Modalité de référence": (("modalité de référence", "réf."),
                              "Le groupe auquel les autres sont comparés ; son rapport de cotes vaut 1 par convention."),
    "Probabilité critique (p)": (("probabilité critique", "p <", "p ="),
                                 "Probabilité d'observer un écart au moins aussi grand si, en réalité, il n'existait "
                                 "aucun lien. Plus elle est petite, moins le résultat est dû au hasard."),
    "Seuil de signification": (("seuil de", "significati"),
                               "Limite (souvent 5 %) en dessous de laquelle la probabilité critique permet de conclure "
                               "qu'un lien est « significatif », c'est-à-dire peu probablement dû au hasard."),
    "Intervalle de confiance à 95 %": (("intervalle de confiance", "ic à 95"),
                                       "Fourchette dans laquelle se situe, avec une confiance de 95 %, la vraie valeur "
                                       "dans la population. Plus elle est étroite, plus l'estimation est précise."),
    "Toutes choses égales par ailleurs": (("toutes choses égales par ailleurs",),
                                          "En comparant des personnes qui se ressemblent sur toutes les autres "
                                          "caractéristiques prises en compte dans le modèle."),
    "Rapport de cotes (OR)": (("rapport de cotes", "fois plus de chances", "moins de chances", "or ="),
                              "Mesure de la force d'un lien. Un OR de 2 se lit « deux fois plus de chances », un OR de "
                              "0,7 « 30 % moins de chances », un OR de 1 « aucune différence »."),
    "Khi-deux": (("khi-deux", "χ²"),
                 "Test qui vérifie si deux caractéristiques qualitatives sont liées (par exemple le milieu de "
                 "résidence et l'utilisation d'un service)."),
    "V de Cramér": (("v de cramér",),
                    "Mesure de l'intensité d'un lien entre deux variables qualitatives, de 0 (aucun lien) à 1 "
                    "(lien parfait)."),
    "d de Somers": (("d de somers",),
                    "Mesure de l'intensité et du sens d'un lien entre deux variables ordonnées, de -1 à 1."),
    "Test t de Welch": (("t de welch",), "Test qui compare les moyennes de deux groupes."),
    "Test de Mann-Whitney": (("mann-whitney",),
                             "Test qui compare deux groupes sans supposer que les valeurs suivent une loi normale."),
    "Correction pour les tests multiples": (("benjamini", "holm"),
                                            "Ajustement des probabilités critiques quand on fait beaucoup de tests, "
                                            "pour éviter de conclure à tort à des liens dus au hasard."),
    "Régression logistique": (("régression logistique",),
                              "Modèle qui estime comment chaque caractéristique modifie les chances qu'un événement "
                              "se produise, en tenant compte de toutes les autres en même temps."),
    "Régression linéaire": (("régression linéaire",),
                            "Modèle qui estime de combien une valeur numérique varie avec chaque caractéristique, les "
                            "autres étant tenues constantes."),
    "Pseudo-R²": (("pseudo-r²",), "Indicateur de la part d'information expliquée par un modèle logistique."),
    "Aire sous la courbe ROC (AUC)": (("courbe roc", "auc"),
                                      "Capacité d'un modèle à distinguer deux groupes : 0,5 correspond au hasard, 1 "
                                      "à une distinction parfaite."),
    "Test de Hosmer et Lemeshow": (("hosmer",),
                                   "Test qui vérifie que les probabilités prédites par le modèle correspondent aux "
                                   "fréquences observées."),
    "Multicolinéarité (VIF)": (("multicolinéarité", "inflation de la variance"),
                               "Situation où des variables explicatives sont très liées entre elles, ce qui rend "
                               "leurs effets difficiles à séparer."),
    "Modèle multi-niveaux": (("multi-niveaux",),
                             "Modèle qui tient compte du fait que les personnes sont regroupées (villages, écoles, "
                             "grappes) et que le lieu de vie peut influencer chacune."),
    "Coefficient de partition de la variance (VPC)": (("partition de la variance", "vpc"),
                                                      "Part des différences entre personnes qui s'explique par le "
                                                      "lieu où elles vivent plutôt que par leurs caractéristiques "
                                                      "individuelles."),
    "Rapport de cotes médian (MOR)": (("rapport de cotes médian",),
                                      "Écart typique de chances entre deux personnes identiques vivant dans deux lieux "
                                      "différents."),
    "Effet de composition": (("effets de composition", "effet de composition"),
                             "Différence entre lieux due au fait qu'ils n'abritent pas les mêmes types de personnes."),
    "Bootstrap": (("bootstrap", "rééchantillonnage"),
                  "Technique qui refait l'analyse des centaines de fois sur des tirages de l'échantillon pour vérifier "
                  "la stabilité des résultats."),
    "Validation croisée": (("validation croisée",),
                           "Technique qui estime le modèle sur une partie des données et le teste sur l'autre, pour "
                           "mesurer sa performance sur des données nouvelles."),
    "Apprentissage automatique (gradient boosting)": (("apprentissage automatique", "gradient boosting"),
                                                      "Méthode de prédiction très flexible, utilisée ici comme témoin "
                                                      "pour vérifier que le modèle explicatif ne manque rien "
                                                      "d'important."),
    "Séparation et méthode de Firth": (("firth", "séparation"),
                                       "Quand un groupe connaît toujours (ou jamais) l'événement, le modèle classique "
                                       "échoue ; la méthode de Firth corrige ce problème."),
    "Courbe de Kaplan-Meier": (("kaplan",),
                               "Courbe qui montre, au fil du temps, la proportion de personnes n'ayant pas encore "
                               "connu l'événement étudié."),
    "Modèle de Cox et rapport de risques (HR)": (("modèle de cox", "hr ="),
                                                 "Modèle qui compare la rapidité avec laquelle l'événement survient "
                                                 "selon les caractéristiques. Un HR de 0,6 signifie un risque "
                                                 "instantané 40 % plus faible."),
    "Analyse des correspondances multiples (ACM)": (("correspondances multiples",),
                                                    "Méthode qui résume de nombreuses variables qualitatives en "
                                                    "quelques axes pour faire apparaître des profils."),
    "Analyse en composantes principales (ACP)": (("composantes principales",),
                                                 "Méthode qui résume de nombreuses variables numériques en quelques "
                                                 "composantes."),
    "Classification (typologie)": (("classification ascendante", "typologie"),
                                   "Méthode qui regroupe les personnes qui se ressemblent en classes homogènes."),
}


def lexique_utilise(texte: str) -> list[tuple[str, str]]:
    """Notions du lexique présentes dans le texte, dans l'ordre alphabétique."""
    bas = texte.lower()
    out = []
    for terme, (motifs, definition) in LEXIQUE.items():
        if any(m in bas for m in motifs):
            out.append((terme, definition))
    return sorted(out, key=lambda t: _cle(t[0]))


def _cle(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def lecture_simple(key_results: list[str], globale: str | None, n: int, unite: str = "observations") -> list[str]:
    """Paragraphes « en clair » : ce qui a été fait, ce qui en ressort, comment lire, quelle confiance accorder."""
    effectif = f"{n:,}".replace(",", "\u202f")
    out = [f"Cette étude s'appuie sur les données de {effectif} {unite}. Elle cherche à savoir quelles "
           "caractéristiques vont de pair avec le phénomène étudié, en comparant des personnes semblables sur les "
           "autres caractéristiques prises en compte."]
    if key_results:
        out.append("Voici ce qui en ressort : " + " ".join(simplifier(k) for k in key_results[:5]))
    out.append("Comment lire ces résultats ? « Deux fois plus de chances » signifie que, parmi des personnes qui se "
               "ressemblent sur tout le reste, celles du groupe concerné ont une cote (rapport entre la chance que "
               "l'événement survienne et celle qu'il ne survienne pas) deux fois plus élevée que celles du groupe de "
               "comparaison. Un résultat « significatif » est "
               "peu probablement dû au hasard ; il ne prouve pas pour autant que la caractéristique en est la cause.")
    if globale:
        out.append(f"Quelle confiance accorder à ces résultats ? Les contrôles automatiques jugent leur fiabilité "
                   f"{globale}. Le détail figure dans la section consacrée à la fiabilité des résultats.")
    return out


def simplifier(phrase: str) -> str:
    """Retire d'une phrase de résultat les parenthèses techniques (IC, OR, p, khi-deux)."""
    s = re.sub(r"\s*\((?:[^()]|\([^()]*\))*?(?:IC|OR|HR|p\s?[<=≤]|χ²|khi-deux)(?:[^()]|\([^()]*\))*\)", "", phrase)
    return re.sub(r"\s+([.,;:])", r"\1", re.sub(r"\s{2,}", " ", s)).strip()
