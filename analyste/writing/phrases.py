"""Formulations de rédaction partagées par les modules d'analyse (style des mémoires de statistique sociale)."""

from __future__ import annotations

from ..stats import fmt
from .style import a, avec_article, de, genre, guillemets, majuscule, sans_article

POSITIFS = ("oui", "yes", "1", "vrai", "true", "présent", "present")


def accord(adj: str, groupe: str) -> str:
    """Accorde un adjectif avec un groupe nominal : « élevé » -> « élevée », « élevés »."""
    plural = groupe.startswith(("les ", "des ", "aux "))
    fem = genre(sans_article(groupe)) == "f"
    out = adj
    if fem and not adj.endswith("e"):
        out += "e"
    if plural and not out.endswith(("s", "x")):
        out += "s"
    return out


def pronom(groupe: str) -> str:
    if groupe.startswith("les "):
        return "elles" if genre(groupe[4:]) == "f" else "ils"
    return "elle" if genre(sans_article(groupe)) == "f" else "il"


def est(groupe: str) -> str:
    return "sont" if groupe.startswith("les ") else "est"


def elision(mot: str, suivant: str) -> str:
    """« de » + « utiliser » -> « d'utiliser »."""
    from .style import _starts_with_vowel
    return mot[:-1] + "'" + suivant if mot in ("de", "que", "le", "la") and _starts_with_vowel(suivant) \
        else f"{mot} {suivant}"


class Redac:
    """Contexte de rédaction : unité d'observation, variable dépendante, événement modélisé."""

    def __init__(self, ds, outcome: str | None = None, event_level: str | None = None):
        r = getattr(ds, "redaction", {}) or {}
        self.ds = ds
        self.unite = (r.get("unite") or "individus").strip()
        self.fem = genre(self.unite) == "f"
        self.ceux = "celles" if self.fem else "ceux"
        self.outcome = outcome
        self.event = event_level
        self._evenement = (r.get("evenement") or "").strip()
        self._indicateur = (r.get("indicateur") or "").strip()

    # --- Variables -------------------------------------------------------
    def v(self, name: str) -> str:
        info = self.ds.variables.get(name)
        return info.prose if info else name

    def V(self, name: str) -> str:
        return majuscule(self.v(name))

    @property
    def y(self) -> str:
        return self.v(self.outcome) if self.outcome else "la variable dépendante"

    # --- Groupes définis par une modalité ---------------------------------
    def groupe(self, var: str, mod: str, premier: bool = True) -> str:
        """« les femmes dont le niveau d'instruction est « Aucun » » ou « celles dont il est « Primaire » »."""
        g = self.v(var)
        if premier:
            return f"les {self.unite} dont {g} {est(g)} {guillemets(mod)}"
        return f"{self.ceux} dont {pronom(g)} {est(g)} {guillemets(mod)}"

    def groupe_pron(self, var: str, mod: str) -> str:
        """« les femmes dont il est « Primaire » » (la variable vient d'être nommée)."""
        g = self.v(var)
        return f"les {self.unite} dont {pronom(g)} {est(g)} {guillemets(mod)}"

    def chez(self, var: str, mod: str, premier: bool = True) -> str:
        return "chez " + self.groupe(var, mod, premier)

    # --- Événement et indicateur (variable dépendante binaire) ------------
    def evenement(self) -> str:
        """Groupe verbal à l'infinitif : « utiliser la contraception moderne »."""
        if self._evenement:
            return self._evenement
        return f"avoir la modalité {guillemets(self.event or 'Oui')} pour {self.y}"

    def chances_de(self) -> str:
        return elision("de", self.evenement())

    def indicateur(self) -> str:
        """Groupe nominal : « la prévalence contraceptive moderne » (saisi par l'utilisateur) ou, à défaut,
        « la fréquence de l'utilisation de la contraception moderne »."""
        if self._indicateur:
            return self._indicateur
        if str(self.event or "Oui").strip().lower() in POSITIFS:
            return f"la fréquence {de(self.y)}"
        return f"la proportion {elision('de', self.unite)} dont {self.y} {est(self.y)} {guillemets(self.event)}"

    # --- Expressions statistiques -----------------------------------------
    @staticmethod
    def seuil(p: float) -> str:
        if p < 0.01:
            return "au seuil de 1 %"
        if p < 0.05:
            return "au seuil de 5 %"
        return "au seuil de 10 %"

    @staticmethod
    def chances(or_: float) -> str:
        """1,62 -> « 1,62 fois plus de chances » ; 0,74 -> « 26 % moins de chances »."""
        if or_ >= 1:
            return f"{fmt.num(or_)} fois plus de chances"
        return f"{fmt.num(100 * (1 - or_), 0)} % moins de chances"

    def titre_y(self) -> str:
        return a(self.y)

    def de_y(self) -> str:
        return de(self.y)


def pcrit(p: float, corrigee: bool = False) -> str:
    """« une probabilité critique inférieure à 0,001 » ou « une probabilité critique de 0,032 »."""
    pc = fmt.pval(p)
    q = "une probabilité critique corrigée" if corrigee else "une probabilité critique"
    if pc.startswith("<"):
        return f"{q} inférieure à {pc.lstrip('< ').strip()}"
    return f"{q} de {pc}"


def valeur(x: float, kind: str = "continue") -> str:
    """Entiers sans décimales pour les comptages (« 3 enfants »), deux décimales sinon."""
    try:
        if kind == "comptage" and float(x).is_integer():
            return fmt.integer(x)
    except (TypeError, ValueError):
        pass
    return fmt.num(x)


def libelle_texte(label: str, override: str | None = None) -> str:
    return (override or "").strip() or avec_article(label)
