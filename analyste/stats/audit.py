"""Audit de qualité des données et protection des identifiants personnels."""

from __future__ import annotations

import hashlib
import hmac
import re

import numpy as np
import pandas as pd

from ..writing.phrases import Redac
from ..writing.style import de, enumeration, nombre
from . import fmt
from .io import Dataset
from .results import Section, Table

DIRECT_ID_NAMES = re.compile(
    r"(^|_)(nom|prenom|prénom|name|surname|firstname|lastname|email|e_?mail|courriel|tel|telephone|"
    r"téléphone|phone|mobile|portable|adresse|address|rue|cni|passeport|passport|nir|secu|"
    r"securite_sociale|iban|ip|ip_address|whatsapp)(_|$|\d)", re.IGNORECASE)
QUASI_ID_NAMES = re.compile(
    r"(^|_)(date_?naiss(ance)?|ddn|birth|dob|lat(itude)?|lon(gitude)?|gps|coord|code_?postal|zip|"
    r"quartier_exact|village_exact)(_|$)", re.IGNORECASE)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)
PHONE_RE = re.compile(r"^\+?[\d\s.\-()]{8,}$")


def detect_identifiers(ds: Dataset) -> dict[str, str]:
    """Renvoie {colonne: 'direct' | 'quasi'}."""
    found: dict[str, str] = {}
    for col in ds.df.columns:
        if DIRECT_ID_NAMES.search(col):
            found[col] = "direct"
            continue
        if QUASI_ID_NAMES.search(col):
            found[col] = "quasi"
            continue
        s = ds.df[col].dropna()
        if s.empty or pd.api.types.is_numeric_dtype(s):
            continue
        sample = s.astype(str).head(200)
        if (sample.str.match(EMAIL_RE).mean() > 0.5) or (
                sample.str.match(PHONE_RE).mean() > 0.8 and sample.str.count(r"\d").mean() >= 8):
            found[col] = "direct"
    return found


def pseudonymize(series: pd.Series, secret: bytes) -> pd.Series:
    """Remplace chaque valeur par un code HMAC-SHA256 tronqué, stable pour un même projet.

    Les codes conservent l'égalité entre valeurs (utile pour une variable de grappe) mais
    ne permettent pas de retrouver la valeur d'origine sans la clé du projet.
    """
    def _h(v):
        if pd.isna(v):
            return np.nan
        digest = hmac.new(secret, str(v).encode("utf-8"), hashlib.sha256).hexdigest()
        return f"P{digest[:10]}"
    return series.map(_h)


def apply_privacy(ds: Dataset, actions: dict[str, str], secret: bytes) -> list[str]:
    """Applique les actions {colonne: 'supprimer'|'pseudonymiser'|'conserver'} ; renvoie un journal."""
    log = []
    for col, action in actions.items():
        if col not in ds.df.columns:
            continue
        if action == "supprimer":
            ds.df = ds.df.drop(columns=[col])
            ds.variables.pop(col, None)
            log.append(f"La variable « {col} », identifiant personnel, a été supprimée avant toute analyse.")
        elif action == "pseudonymiser":
            ds.df[col] = pseudonymize(ds.df[col], secret)
            if col in ds.variables:
                ds.variables[col].categories = []
            log.append(f"La variable « {col} » a été pseudonymisée, chaque valeur étant remplacée par un code "
                       "HMAC-SHA256.")
    return log


def quality_section(ds: Dataset, used: list[str], outcome: str | None) -> Section:
    sec = Section(key="qualite", title="Qualité des données", level=2)
    df = ds.df
    n = len(df)
    rows = []
    flagged_missing = []
    for col in used:
        info = ds.variables[col]
        miss = df[col].isna().mean()
        note = []
        if miss > 0.05:
            note.append("manquants > 5 %")
            flagged_missing.append((col, miss))
        if info.kind in ("continue", "comptage"):
            x = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(x) >= 4:
                q1, q3 = np.percentile(x, [25, 75])
                iqr = q3 - q1
                ext = ((x < q1 - 3 * iqr) | (x > q3 + 3 * iqr)).sum()
                mod = ((x < q1 - 1.5 * iqr) | (x > q3 + 1.5 * iqr)).sum() - ext
                if ext:
                    note.append(f"{ext} valeur{'s' if ext > 1 else ''} extrême{'s' if ext > 1 else ''}")
                elif mod:
                    note.append(f"{mod} valeur{'s' if mod > 1 else ''} atypique{'s' if mod > 1 else ''}")
        elif info.kind in ("nominale", "binaire", "ordinale"):
            counts = df[col].value_counts()
            small = (counts < 5).sum()
            if small:
                note.append(f"{small} modalité{'s' if small > 1 else ''} d'effectif inférieur à 5")
        rows.append({"Variable": info.label if info.label != col else col, "Type": info.kind,
                     "Valides": fmt.integer(info.n_valid), "Manquants": fmt.pct(miss),
                     "Remarques": " ; ".join(note) or "-"})
    dup = int(df.duplicated().sum())
    sec.tables.append(Table(
        title="Qualité des variables retenues pour l'analyse",
        data=pd.DataFrame(rows),
        note=("Les valeurs atypiques sont repérées par la règle de Tukey : au-delà de 1,5 fois l'intervalle "
              "interquartile, et extrêmes au-delà de trois fois. Elles sont signalées mais ne sont pas supprimées.")))
    sec.refs |= {"tukey1977", "rubin1976"}
    R = Redac(ds)
    txt = (f"Avant toute analyse, nous avons vérifié la qualité des données. La base compte "
           f"{nombre(n, 'observations', True)}, et {nombre(len(used), 'variables')} sont retenues pour l'étude. ")
    if dup:
        txt += (f"Nous avons repéré {nombre(dup, 'lignes', True)} strictement "
                f"{'identiques' if dup > 1 else 'identique'} à une autre ; "
                f"{'elles sont conservées' if dup > 1 else 'elle est conservée'} mais "
                f"{'doivent' if dup > 1 else 'doit'} être vérifiée{'s' if dup > 1 else ''}. ")
    else:
        txt += "Aucune ligne dupliquée n'a été détectée. "
    if flagged_missing:
        lst = enumeration([f"{R.v(c)} ({fmt.pct(m)})" for c, m in flagged_missing[:6]])
        if len(flagged_missing) == 1:
            txt += f"Une seule variable présente plus de 5 % de valeurs manquantes : il s'agit {de(lst)}. "
        else:
            txt += f"Les variables présentant plus de 5 % de valeurs manquantes sont {lst}. "
        txt += ("Les analyses sont conduites sur les cas disponibles. Si l'absence de réponse n'est pas aléatoire, "
                "les estimations peuvent toutefois être biaisées (Rubin, 1976).")
    else:
        txt += "Par ailleurs, aucune variable retenue ne dépasse 5 % de valeurs manquantes."
    sec.paragraphs.append(txt)
    sec.facts.update({"qualite.n": n, "qualite.doublons": dup, "qualite.nb_variables": len(used)})

    if outcome and outcome in df.columns and flagged_missing:
        miss_rows = []
        y = df[outcome]
        for col, _ in flagged_missing:
            if col == outcome:
                continue
            m = df[col].isna()
            if pd.api.types.is_numeric_dtype(y) and ds.variables[outcome].kind in ("continue", "comptage"):
                from scipy import stats
                a, b = y[m].dropna(), y[~m].dropna()
                if len(a) >= 5 and len(b) >= 5:
                    p = stats.mannwhitneyu(a, b).pvalue
                    miss_rows.append((col, p))
            else:
                ct = pd.crosstab(m, y)
                if ct.shape[0] == 2 and ct.shape[1] >= 2:
                    from scipy import stats
                    p = stats.chi2_contingency(ct)[1]
                    miss_rows.append((col, p))
        bad = [R.v(c) for c, p in miss_rows if p < 0.05]
        if bad:
            sec.warnings.append(
                f"La présence de valeurs manquantes pour {enumeration(bad)} est associée à la variable dépendante. "
                "Le mécanisme de non-réponse n'est donc probablement pas complètement aléatoire (MCAR).")
    return sec
