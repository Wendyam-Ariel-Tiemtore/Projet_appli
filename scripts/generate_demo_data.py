"""Génère un jeu de données fictif, de structure proche d'une enquête démographique et de santé.

Les données sont entièrement simulées (aucune personne réelle) : elles servent de démonstration et de
base aux tests automatisés. Les paramètres « vrais » sont connus, ce qui permet de vérifier que
l'application les retrouve.

Usage : python scripts/generate_demo_data.py examples/enquete_demo.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

TRUE = {
    "intercept": -1.6, "age_25_34": 0.4, "age_35_49": 0.1, "primaire": 0.7, "secondaire": 1.2,
    "quintile": 0.15, "medias": 0.35, "csps": 0.4, "sigma_u": 0.8,
}

PRENOMS = ["Awa", "Mariam", "Salimata", "Fatimata", "Aminata", "Rasmata", "Adjara", "Bintou", "Clarisse", "Odile"]
NOMS = ["Ouédraogo", "Sawadogo", "Compaoré", "Kaboré", "Traoré", "Zongo", "Ilboudo", "Kinda", "Bado", "Yaméogo"]


def simulate(n_clusters: int = 120, seed: int = 2026) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    regions = ["Centre", "Hauts-Bassins", "Nord", "Est", "Boucle du Mouhoun", "Sahel"]
    rows = []
    for j in range(n_clusters):
        region = regions[j % len(regions)]
        urbain = rng.random() < (0.55 if region in ("Centre", "Hauts-Bassins") else 0.2)
        csps = int(rng.random() < (0.85 if urbain else 0.45))
        u = rng.normal(0, TRUE["sigma_u"])
        u_imc = rng.normal(0, 1.2)
        size = int(rng.integers(12, 32))
        for _ in range(size):
            age = int(rng.integers(15, 50))
            p_instr = [0.35, 0.30, 0.35] if urbain else [0.70, 0.20, 0.10]
            instr = rng.choice(["Aucun", "Primaire", "Secondaire ou plus"], p=p_instr)
            q = int(np.clip(round(rng.normal(3.6 if urbain else 2.4, 1.1)), 1, 5))
            medias = int(rng.random() < (0.75 if urbain else 0.4) * (1.1 if instr != "Aucun" else 0.8))
            religion = rng.choice(["Musulmane", "Catholique", "Protestante", "Traditionnelle"],
                                  p=[0.6, 0.22, 0.1, 0.08])
            base_par = max(0.0, (age - 17) * 0.22) * (0.75 if instr == "Secondaire ou plus" else 1.0)
            parite = int(rng.poisson(base_par))
            lin = (TRUE["intercept"] + TRUE["age_25_34"] * (25 <= age <= 34) + TRUE["age_35_49"] * (age >= 35)
                   + TRUE["primaire"] * (instr == "Primaire") + TRUE["secondaire"] * (instr == "Secondaire ou plus")
                   + TRUE["quintile"] * (q - 3) + TRUE["medias"] * medias + TRUE["csps"] * csps + u)
            contra = int(rng.random() < 1 / (1 + np.exp(-lin)))
            imc = 21.5 + 0.06 * (age - 30) + 0.55 * (q - 3) + 0.9 * urbain + u_imc + rng.normal(0, 2.6)
            # Durée jusqu'à la première union (années depuis 12 ans), censurée à l'âge de l'enquête
            rate = 0.11 * (0.55 if instr == "Secondaire ou plus" else 1.0) * (0.8 if urbain else 1.0)
            t_union = rng.exponential(1 / rate)
            obs_time = age - 12
            union = int(t_union <= obs_time)
            rows.append({
                "id_femme": f"F{j:03d}{len(rows):05d}",
                "nom": rng.choice(NOMS), "prenom": rng.choice(PRENOMS),
                # Numéros volontairement non attribuables (préfixe 00) : aucune personne réelle
                "telephone": f"+226 00 00 {rng.integers(10, 99)} {rng.integers(10, 99)}",
                "grappe": f"G{j:03d}", "region": region, "milieu": "Urbain" if urbain else "Rural",
                "csps_village": "Oui" if csps else "Non",
                "age": age,
                "groupe_age": "15-24 ans" if age < 25 else ("25-34 ans" if age < 35 else "35-49 ans"),
                "instruction": instr, "quintile_bien_etre": q,
                "exposition_medias": "Oui" if medias else "Non", "religion": religion, "parite": parite,
                "contraception_moderne": "Oui" if contra else "Non",
                "imc": round(float(imc), 1),
                "duree_avant_union": round(float(min(t_union, obs_time)), 2), "premiere_union": union,
                "poids": round(float(rng.uniform(0.6, 1.6)), 4),
            })
    df = pd.DataFrame(rows)
    # Quelques valeurs manquantes réalistes
    miss = rng.random(len(df)) < 0.03
    df.loc[miss, "imc"] = np.nan
    df.loc[rng.random(len(df)) < 0.02, "exposition_medias"] = np.nan
    # Proportion de femmes instruites dans la grappe (variable contextuelle)
    df["prop_instruites_grappe"] = df.groupby("grappe")["instruction"].transform(
        lambda s: round(float((s != "Aucun").mean()), 3))
    return df


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "examples/enquete_demo.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    data = simulate()
    data.to_csv(out, index=False, sep=";", decimal=",")
    print(f"{len(data)} lignes écrites dans {out}")
