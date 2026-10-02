"""Règles de style pour un français académique naturel, inspiré des usages des mémoires et rapports de stage
en statistique et en démographie (francophonie, Afrique de l'Ouest et France).

Principes appliqués à tout texte produit :
- aucun tiret long ni demi-cadratin comme ponctuation : on utilise la virgule, les deux-points ou les parenthèses ;
- les petits effectifs sont écrits en lettres suivis des chiffres entre parenthèses : « sept (07) variables » ;
- les variables sont désignées par un groupe nominal avec article (« le niveau d'instruction »), sans guillemets ;
  les guillemets sont réservés aux modalités (« Primaire ») ;
- des connecteurs variés et sobres (« En effet », « Par ailleurs », « Ainsi », « Cependant »…) ;
- la première personne du pluriel (« nous constatons que »).
"""

from __future__ import annotations

import re
import unicodedata

NBSP = " "

# ---------------------------------------------------------------------------
# Nombres en lettres (orthographe rectifiée de 1990 : traits d'union partout)
# ---------------------------------------------------------------------------

_UNITS = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze",
          "treize", "quatorze", "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf"]
_TENS = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def lettres(n: int, feminin: bool = False) -> str:
    """Nombre entier de 0 à 99 en toutes lettres."""
    if not 0 <= n <= 99:
        raise ValueError(n)
    if n < 20:
        w = _UNITS[n]
    elif n < 70:
        t, u = divmod(n, 10)
        w = _TENS[t] + ("" if u == 0 else "-et-un" if u == 1 else "-" + _UNITS[u])
    elif n < 80:
        u = n - 60
        w = "soixante-et-onze" if u == 11 else "soixante-" + _UNITS[u]
    else:
        u = n - 80
        w = "quatre-vingts" if u == 0 else "quatre-vingt-" + _UNITS[u]
    if feminin and (w == "un" or w.endswith("-un")):
        w = w[:-2] + "une"
    return w


def nombre(n: int, nom: str = "", feminin: bool | None = None) -> str:
    """« sept (07) variables » ; chiffres seuls au-delà de 99 (« 2 511 observations »)."""
    n = int(n)
    if feminin is None:
        feminin = bool(nom) and genre(nom) == "f"
    if 0 <= n <= 99:
        txt = f"{lettres(n, feminin)} ({n:02d})"
    else:
        txt = f"{n:,}".replace(",", NBSP)
    if nom:
        txt += " " + (nom if n > 1 or not nom.endswith("s") else nom[:-1])
    return txt


_ORD = {1: "premier", 2: "deuxième", 3: "troisième", 4: "quatrième", 5: "cinquième", 6: "sixième",
        7: "septième", 8: "huitième", 9: "neuvième", 10: "dixième"}


def ordinal(n: int, feminin: bool = False) -> str:
    """1 -> « premier » / « première » ; au-delà de 10 : « 11e »."""
    if n == 1:
        return "première" if feminin else "premier"
    return _ORD.get(n, f"{n}e")


# ---------------------------------------------------------------------------
# Articles et genre
# ---------------------------------------------------------------------------

FEMININ = {
    "activite", "aire", "annee", "appartenance", "attitude", "autonomie", "branche", "capacite", "categorie",
    "certification", "classe", "commune", "connaissance", "consommation", "consultation", "contraception",
    "couverture", "croyance", "date", "decision", "densite", "depense", "difficulte", "dimension", "distance",
    "duree", "ecole", "education", "efficience", "enquete", "entreprise", "epargne", "ethnie", "exposition",
    "famille", "fecondite", "femme", "filiere", "fille", "fonction", "formation", "frequence", "frontiere",
    "gouvernance", "grappe", "grossesse", "instruction", "intensite", "langue", "localite", "maladie", "marque",
    "mere", "methode", "migration", "mobilite", "moyenne", "mortalite", "nationalite", "naissance", "note",
    "occupation", "origine", "parite", "part", "participation", "pauvrete", "performance", "periode", "personne",
    "population", "possession", "pratique", "presence", "prevalence", "probabilite", "production", "profession",
    "proportion", "propriete", "province", "qualite", "religion", "region", "relation", "residence", "ressource",
    "richesse", "sante", "satisfaction", "situation", "source", "strate", "structure", "superficie", "surface",
    "survie", "taille", "tendance", "tranche", "union", "utilisation", "vaccination", "valeur", "variable", "ville",
    "zone", "cooperative", "agence", "unite", "cohorte", "vague", "mesure", "perception", "opinion",
    "scolarisation", "scolarite", "alphabetisation", "assurance", "allocation", "aide", "offre", "demande",
    "hauteur", "largeur", "longueur", "couleur", "chaleur", "douleur", "profondeur", "grandeur", "epaisseur",
}
MASCULIN = {"age", "acces", "indice", "milieu", "niveau", "nombre", "quintile", "revenu", "score", "sexe", "statut",
            "type", "groupe", "poids", "rang", "rendement", "chiffre", "secteur", "bassin", "departement", "village",
            "menage", "chef", "conjoint", "enfant", "taux", "ratio", "delai", "temps", "lieu", "mode", "usage",
            "emploi", "travail", "diplome", "cycle", "etat", "handicap", "imc", "effectif", "montant", "prix"}
FEMININE_ENDINGS = ("tion", "sion", "xion", "te", "ee", "ence", "ance", "ure", "ise", "ude", "ie", "elle", "ette",
                    "ine", "iere", "aille", "eille", "ouille", "ade", "ale", "ique")
PLURAL_UNITS_FEM = {"femmes", "filles", "meres", "cooperatives", "entreprises", "personnes", "familles", "communes",
                    "regions", "ecoles", "unites", "exploitations", "structures", "institutions", "agences"}


def _plain(word: str) -> str:
    w = unicodedata.normalize("NFKD", word.lower())
    return "".join(ch for ch in w if not unicodedata.combining(ch))


def genre(groupe: str) -> str:
    """'f' ou 'm' d'après le premier nom du groupe nominal (heuristique, modifiable par l'utilisateur)."""
    words = re.findall(r"[\wÀ-ÿ'’]+", groupe)
    if not words:
        return "m"
    w = _plain(words[0].split("'")[-1].split("’")[-1])
    if w.endswith("s") and w[:-1] in FEMININ | MASCULIN:
        w = w[:-1]
    if w in PLURAL_UNITS_FEM or w in FEMININ:
        return "f"
    if w in MASCULIN:
        return "m"
    return "f" if w.endswith(FEMININE_ENDINGS) and not w.endswith(("ste", "isme")) else "m"


def _starts_with_vowel(s: str) -> bool:
    p = _plain(s)
    return bool(p) and (p[0] in "aeiouy" or (p[0] == "h" and not p.startswith(("hau", "hie", "hon", "hor"))))


def _lower_first(label: str) -> str:
    first = label.split(" ")[0]
    if len(first) > 1 and (first.isupper() or any(ch.isupper() for ch in first[1:])):
        return label  # sigle ou nom propre (« IMC », « CSPS »)
    return label[:1].lower() + label[1:]


def avec_article(label: str) -> str:
    """« Niveau d'instruction » -> « le niveau d'instruction » ; « Âge » -> « l'âge »."""
    label = label.strip()
    if not label:
        return label
    low = _plain(label)
    if re.match(r"^(le|la|les|l'|l’|un|une|des|son|sa|ses|leur|leurs)\b", low):
        return _lower_first(label)
    txt = _lower_first(label)
    if _starts_with_vowel(label):
        return "l'" + txt
    first = _plain(re.findall(r"[\wÀ-ÿ]+", label)[0])
    if first.endswith(("s", "x")) and first not in MASCULIN | FEMININ and first not in ("poids", "acces", "taux",
                                                                                          "prix", "temps"):
        return "les " + txt
    return ("la " if genre(label) == "f" else "le ") + txt


def de(groupe: str) -> str:
    """Contraction avec « de » : « du niveau », « de la religion », « de l'âge », « des revenus »."""
    if groupe.startswith("le "):
        return "du " + groupe[3:]
    if groupe.startswith("les "):
        return "des " + groupe[4:]
    return "de " + groupe


def a(groupe: str) -> str:
    """Contraction avec « à » : « au niveau », « à la religion », « aux revenus »."""
    if groupe.startswith("le "):
        return "au " + groupe[3:]
    if groupe.startswith("les "):
        return "aux " + groupe[4:]
    return "à " + groupe


def sans_article(groupe: str) -> str:
    return re.sub(r"^(le |la |les |l'|l’)", "", groupe)


def majuscule(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def enumeration(items: list[str], conj: str = "et") -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" {conj} " + items[-1]


def guillemets(s: str) -> str:
    return f"« {s} »"


# ---------------------------------------------------------------------------
# Connecteurs (choix déterministe pour la reproductibilité)
# ---------------------------------------------------------------------------

AJOUT = ["Par ailleurs, ", "De même, ", "En outre, ", "Aussi, ", "De plus, "]
CONSTAT = ["Nous constatons que ", "Nous notons que ", "On observe que ", "Il ressort que "]


def connecteur(i: int, liste: list[str] = AJOUT) -> str:
    return "" if i == 0 else liste[(i - 1) % len(liste)]


# ---------------------------------------------------------------------------
# Nettoyage typographique
# ---------------------------------------------------------------------------

_DASH_SPACED = re.compile(r"\s+[—–]\s+")
_DASH_TIGHT = re.compile(r"(?<=\w)[—](?=\w)")


def nettoyer(texte: str) -> str:
    """Supprime les tirets longs et demi-cadratins de ponctuation, normalise les espaces."""
    if not texte:
        return texte
    out = []
    for phrase in re.split(r"(?<=[.!?])\s+", texte):
        n = len(_DASH_SPACED.findall(phrase))
        if n == 2:  # incise encadrée : parenthèses
            phrase = _DASH_SPACED.sub(" (", phrase, count=1)
            phrase = _DASH_SPACED.sub(") ", phrase, count=1)
        elif n == 1:
            phrase = _DASH_SPACED.sub(", " if ":" in phrase else " : ", phrase)
        elif n > 2:
            phrase = _DASH_SPACED.sub(", ", phrase)
        out.append(phrase)
    t = " ".join(out)
    t = _DASH_TIGHT.sub("-", t)
    t = t.replace("—", ", ").replace(" – ", " à ")
    t = re.sub(r"\s+,", ",", t)
    t = re.sub(r",\s*,", ",", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\(\s+", "(", t)
    t = re.sub(r"\s+\)", ")", t)
    return t.strip()


def titre(texte: str) -> str:
    """Titres : « Chapitre 1 — Cadre » devient « Chapitre 1 : Cadre »."""
    return re.sub(r"\s*[—–]\s*", " : ", texte).strip()
