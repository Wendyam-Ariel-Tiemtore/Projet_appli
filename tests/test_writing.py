"""La rédaction assistée ne peut introduire ni nombre ni référence absents des résultats."""

from analyste.writing import guard
from analyste.writing.composer import Writer
from analyste.writing.llm import Provider


class FauxModele(Provider):
    name = "factice"

    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.appels = 0

    def available(self):
        return True

    def complete(self, system, prompt, max_tokens=1800):
        self.appels += 1
        return self.reponses.pop(0)


def autorises():
    a = guard.Allowed()
    a.add_text("La part varie de 24,5 % à 54,4 % ; OR = 3,22 ; IC à 95 % [2,51 ; 4,14] ; 2 518 observations.")
    a.add_citation("Bougma et al., 2015")
    a.add_citation("Snijders et Bosker, 2012")
    return a


def test_nombre_invente_rejete_puis_repli():
    w = Writer(FauxModele(["Le taux atteint 61,7 % chez les femmes instruites, ce qui est remarquable. " * 2] * 2),
               autorises(), [])
    texte, ia = w.write("Discussion", "…", ["Texte de repli."])
    assert not ia and texte == ["Texte de repli."]
    assert "rejeté" in w.log[0]


def test_reference_inventee_rejetee():
    rep = ("L'instruction est associée à l'utilisation de la contraception (Dupont et al., 2019), comme l'ont "
           "montré d'autres travaux dans des contextes comparables, avec une cote de 3,22.")
    w = Writer(FauxModele([rep, rep]), autorises(), [])
    texte, ia = w.write("Discussion", "…", ["Repli."])
    assert not ia


def test_formulation_causale_rejetee():
    rep = ("L'instruction entraîne une hausse de l'utilisation de la contraception moderne, avec une cote de 3,22 "
           "fois plus élevée chez les femmes du secondaire.")
    w = Writer(FauxModele([rep, rep]), autorises(), [])
    assert w.write("Résumé", "…", ["Repli."])[1] is False


def test_texte_conforme_accepte_apres_correction():
    mauvais = "Le taux atteint 61,7 % chez les femmes instruites, ce qui mérite une discussion approfondie ici."
    bon = ("L'instruction est associée à une utilisation plus fréquente de la contraception moderne : la part "
           "passe de 24,5 % à 54,4 % (OR = 3,22), conformément à Bougma et al. (2015).")
    modele = FauxModele([mauvais, bon])
    w = Writer(modele, autorises(), [])
    texte, ia = w.write("Discussion", "…", ["Repli."])
    assert ia and texte == [bon] and modele.appels == 2


def test_arrondis_acceptes():
    a = autorises()
    assert guard.check("Environ 54 % et un OR de 3,2.", a).ok
    assert not guard.check("Environ 57 %.", a).ok


def test_sans_modele_aucun_appel():
    w = Writer(None, autorises(), [])
    assert w.write("x", "…", ["Repli."]) == (["Repli."], False)


def test_extraction_litterature_controlee():
    from analyste.literature.sources import Work
    from analyste.writing.assist import make_extractor, make_namer
    resume = ("This study examines the association between maternal education and modern contraceptive use among "
              "2 518 women in Burkina Faso using multilevel logistic regression. Educated women had higher odds "
              "of use (OR 3.2). However, the cross-sectional design limits causal interpretation of these results.")
    w = Work(key="w", title="Education and contraception", authors=["A. Auteur"], year=2020, venue="Revue",
             doi=None, abstract=resume, cited_by=0)
    ok = FauxModele(['{"objet": "Lien entre instruction et contraception moderne", "methode": "Régression '
                     'logistique multiniveau sur 2 518 femmes", "resultats": "Cote plus élevée chez les femmes '
                     'instruites (OR 3,2)", "limites": "Plan transversal"}'])
    ex = make_extractor(ok)(w)
    assert "2 518" in ex["methode"] and "3,2" in ex["resultats"]
    invente = FauxModele(['{"objet": "x", "methode": "Enquête auprès de 9 999 femmes", "resultats": "OR 7,5", '
                          '"limites": "aucune"}'])
    ex2 = make_extractor(invente)(w)
    assert "9 999" not in ex2["methode"] and "7,5" not in ex2["resultats"]
    noms = make_namer(FauxModele(['["Instruction et fécondité", "Thème 2020"]']))(["a, b", "c, d"])
    assert noms == ["Instruction et fécondité", "c, d"]
