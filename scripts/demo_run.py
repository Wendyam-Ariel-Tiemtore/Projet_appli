"""Exécute l'analyse complète sur le jeu de démonstration (sans interface web).

Usage : python scripts/demo_run.py [dossier_de_sortie] [type_de_document] [genre_de_presentation] [theme] [format]
Exemple : python scripts/demo_run.py sortie memoire soutenance ardoise 16:9
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analyste.config import Settings  # noqa: E402
from analyste.pipeline import AnalysisConfig, run  # noqa: E402
from analyste.stats.io import read_dataset  # noqa: E402
from analyste.writing.composer import RequestSpec  # noqa: E402

LABELS = {
    "contraception_moderne": "Utilisation de la contraception moderne", "groupe_age": "Groupe d'âge",
    "instruction": "Niveau d'instruction", "quintile_bien_etre": "Quintile de bien-être",
    "exposition_medias": "Exposition aux médias", "religion": "Religion", "parite": "Parité",
    "csps_village": "Présence d'un CSPS dans la localité", "milieu": "Milieu de résidence",
    "prop_instruites_grappe": "Proportion de femmes instruites dans la grappe", "grappe": "Grappe d'enquête",
    "duree_avant_union": "Durée avant la première union (années depuis 12 ans)", "premiere_union": "Première union",
    "age": "Âge", "imc": "Indice de masse corporelle",
}


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "sortie_demo")
    doc_type = sys.argv[2] if len(sys.argv) > 2 else "memoire"
    genre = sys.argv[3] if len(sys.argv) > 3 else ""  # soutenance, communication, seminaire, restitution, atelier
    theme = sys.argv[4] if len(sys.argv) > 4 else "ardoise"
    format_ = sys.argv[5] if len(sys.argv) > 5 else "16:9"
    data = ROOT / "examples" / "enquete_demo.csv"
    if not data.exists():
        from scripts.generate_demo_data import simulate  # type: ignore
        simulate().to_csv(data, index=False, sep=";", decimal=",")
    ds = read_dataset(data.read_bytes(), data.name, out)
    cfg = AnalysisConfig(
        outcome="contraception_moderne",
        explanatory=["groupe_age", "instruction", "quintile_bien_etre", "exposition_medias", "religion", "parite",
                     "csps_village", "milieu", "prop_instruites_grappe"],
        cluster="grappe", references={"groupe_age": "15-24 ans"},
        kinds={"instruction": "ordinale", "quintile_bien_etre": "ordinale"}, labels=LABELS,
        privacy_actions={"nom": "supprimer", "prenom": "supprimer", "telephone": "supprimer"},
        time_var="duree_avant_union", event_var="premiere_union", survival_group="instruction",
        textes={"prop_instruites_grappe": "la proportion de femmes instruites dans la grappe",
                "csps_village": "la présence d'un CSPS dans la localité"},
        redaction={"unite": "femmes", "evenement": "utiliser une méthode contraceptive moderne",
                   "indicateur": "la prévalence contraceptive moderne"})
    spec = RequestSpec(
        doc_type=doc_type,
        title="Facteurs individuels et contextuels de l'utilisation de la contraception moderne chez les femmes de "
              "15 à 49 ans",
        author="Nom de l'auteur", institution="Institution", supervisor="Nom du directeur", date_text="Octobre 2026",
        context="La faible utilisation de la contraception moderne demeure un enjeu majeur de santé reproductive.\n"
                "Les disparités entre milieux de résidence suggèrent l'existence d'effets de contexte.",
        problematique="Quels facteurs individuels et contextuels sont associés à l'utilisation de la contraception "
                      "moderne ?",
        objectives=["Identifier les facteurs individuels et contextuels associés à l'utilisation de la contraception "
                    "moderne", "Mesurer la part des disparités entre grappes attribuable aux effets de composition"],
        hypotheses=["Le niveau d'instruction de la femme est positivement associé à l'utilisation de la "
                    "contraception moderne", "La présence d'un centre de santé dans la localité est associée à une "
                    "utilisation plus élevée"],
        keywords=["contraception moderne", "analyse multiniveau", "effets de contexte", "Afrique de l'Ouest"],
        presentation={"active": bool(genre), "genre": genre or "soutenance", "theme": theme, "format": format_,
                      "recommandations": ["Renforcer l'offre de services de planification familiale en milieu rural",
                                          "Intégrer la sensibilisation à la contraception dans les programmes "
                                          "d'alphabétisation des femmes"]} if genre else {})
    res = run(ds, cfg, spec, out, Settings(), b"demonstration-cle-32-octets!!!!!",
              progress=lambda p, m: print(f"{p:3d} % {m}"))
    for k, v in res.items():
        print(k, v)


if __name__ == "__main__":
    main()
