"""Lecture sécurisée des fichiers de données et typage des variables.

Formats acceptés : CSV/TSV/TXT délimités, Excel (.xlsx), SPSS (.sav), Stata (.dta).
Aucun format exécutable ou sérialisé (pickle, .RData) n'est accepté.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

KINDS = ("identifiant", "binaire", "nominale", "ordinale", "continue", "comptage", "date", "texte")

ID_NAME = re.compile(r"(^|_)(id|ident|identifiant|code|matricule|num(ero)?|siren|siret|uuid|key|cle)(_|$)",
                     re.IGNORECASE)
MAX_CATEGORIES = 12
ORDINAL_NAME = re.compile(r"(quintile|quartile|decile|décile|niveau|echelle|échelle|satisfaction|likert|degre|"
                          r"degré|rang|classe_age|frequence|fréquence|accord)", re.IGNORECASE)
COUNT_NAME = re.compile(r"(^|_)(nb|nombre|n|parite|parité|enfants|effectif|count|freq_)", re.IGNORECASE)


class DataReadError(ValueError):
    """Erreur de lecture présentée telle quelle à l'utilisateur (aucune donnée sensible)."""


@dataclass
class VariableInfo:
    name: str
    label: str
    kind: str
    n_valid: int
    n_missing: int
    n_unique: int
    categories: list[str] = field(default_factory=list)  # ordre des modalités
    ordered: bool = False
    suggested_role: str = "explicative"  # explicative | ignorer
    reason: str = ""
    texte: str = ""  # groupe nominal employé dans la rédaction (« le niveau d'instruction »)

    @property
    def prose(self) -> str:
        from ..writing.style import avec_article
        return self.texte or avec_article(self.label)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Dataset:
    df: pd.DataFrame
    variables: dict[str, VariableInfo]
    source_format: str
    # Formulations de rédaction : unité d'observation, événement (infinitif), indicateur (groupe nominal)
    redaction: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise DataReadError("Encodage du fichier texte non reconnu.")


# Bornes de lecture : un fichier de quelques kilo-octets ne doit pas pouvoir épuiser la mémoire du serveur.
MAX_COLONNES = 2000
MAX_LIGNES = 1_000_000
MAX_CELLULES = 25_000_000


def _verifier_forme(lignes: int, colonnes: int) -> None:
    if colonnes > MAX_COLONNES:
        raise DataReadError(f"Le tableau compte plus de {MAX_COLONNES} colonnes. Conservez uniquement les variables "
                            "utiles à l'analyse avant de le déposer.")
    if lignes > MAX_LIGNES:
        raise DataReadError(f"Le tableau compte plus de {MAX_LIGNES:,} lignes.".replace(",", "\u202f"))
    if lignes * max(colonnes, 1) > MAX_CELLULES:
        raise DataReadError("Le tableau est trop volumineux (lignes × colonnes). Conservez uniquement les variables "
                            "utiles à l'analyse avant de le déposer.")


def _read_delimited(raw: bytes) -> pd.DataFrame:
    text = _decode(raw)
    sample = text[:20000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        sep = dialect.delimiter
    except csv.Error:
        sep = ";" if sample.count(";") > sample.count(",") else ","
    # Contrôle de la forme avant toute lecture complète
    entete = text[: text.find("\n") if "\n" in text else len(text)]
    ncol = entete.count(sep) + 1
    nlig = text.count("\n")
    _verifier_forme(nlig, ncol)
    # Virgule décimale probable si séparateur « ; » et nombres du type 12,5
    decimal = "," if sep != "," and re.search(r"\d,\d", sample) else "."
    df = None
    for moteur in ("c", "python"):
        try:
            df = pd.read_csv(io.StringIO(text), sep=sep, decimal=decimal, engine=moteur, skipinitialspace=True,
                             nrows=MAX_LIGNES + 1, low_memory=False) if moteur == "c" else \
                pd.read_csv(io.StringIO(text), sep=sep, decimal=decimal, engine=moteur, skipinitialspace=True,
                            nrows=MAX_LIGNES + 1)
            break
        except Exception as exc:  # noqa: BLE001 - message générique, sans contenu
            if moteur == "python":
                raise DataReadError("Le fichier texte n'a pas pu être lu comme un tableau délimité.") from exc
    _verifier_forme(len(df), df.shape[1])
    return df


def _read_excel(raw: bytes) -> pd.DataFrame:
    """Lecture en flux de la première feuille, bornée en lignes et en colonnes (pas de matrice creuse géante)."""
    import openpyxl

    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise DataReadError("Le classeur Excel n'a pas pu être lu (première feuille).") from exc
    try:
        ws = wb.worksheets[0]
        lignes: list[list] = []
        largeur, vides = 0, 0
        for row in ws.iter_rows(values_only=True):
            if len(row) > MAX_COLONNES and any(v is not None for v in row[MAX_COLONNES:]):
                _verifier_forme(0, len(row))
            row = row[:MAX_COLONNES]
            if all(v is None for v in row):
                vides += 1
                if vides > 10_000:  # longues plages vides : fin utile de la feuille
                    break
                continue
            vides = 0
            dernier = max(i for i, v in enumerate(row) if v is not None) + 1
            largeur = max(largeur, dernier)
            lignes.append(list(row))
            if len(lignes) > MAX_LIGNES or len(lignes) * largeur > MAX_CELLULES:
                _verifier_forme(len(lignes), largeur)
    except DataReadError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise DataReadError("Le classeur Excel n'a pas pu être lu (première feuille).") from exc
    finally:
        wb.close()
    if not lignes:
        raise DataReadError("La première feuille du classeur est vide.")
    entete = [("" if v is None else str(v)) for v in lignes[0][:largeur]]
    entete += [""] * (largeur - len(entete))
    noms = [h if h.strip() else f"Unnamed: {i}" for i, h in enumerate(entete)]
    corps = [(r[:largeur] + [None] * (largeur - len(r[:largeur]))) for r in lignes[1:]]
    return pd.DataFrame(corps, columns=noms)


def _read_stat(raw: bytes, suffix: str, workdir: Path):
    import pyreadstat

    tmp = workdir / f"lecture{suffix}"
    tmp.write_bytes(raw)
    try:
        lire = pyreadstat.read_sav if suffix == ".sav" else pyreadstat.read_dta
        _, entete = lire(str(tmp), metadataonly=True)
        _verifier_forme(int(entete.number_rows or 0), int(entete.number_columns or 0))
    except DataReadError:
        tmp.unlink(missing_ok=True)
        raise
    except Exception as exc:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        raise DataReadError("Le fichier SPSS/Stata n'a pas pu être lu.") from exc
    try:
        if suffix == ".sav":
            df, meta = pyreadstat.read_sav(str(tmp), apply_value_formats=False)
        else:
            df, meta = pyreadstat.read_dta(str(tmp), apply_value_formats=False)
    except Exception as exc:  # noqa: BLE001
        raise DataReadError("Le fichier SPSS/Stata n'a pas pu être lu.") from exc
    finally:
        tmp.unlink(missing_ok=True)
    return df, meta


def read_dataset(raw: bytes, filename: str, workdir: Path) -> Dataset:
    suffix = Path(filename).suffix.lower()
    labels: dict[str, str] = {}
    value_labels: dict[str, dict] = {}
    measures: dict[str, str] = {}
    if suffix in (".csv", ".tsv", ".txt"):
        df = _read_delimited(raw)
    elif suffix == ".xlsx":
        df = _read_excel(raw)
    elif suffix in (".sav", ".dta"):
        df, meta = _read_stat(raw, suffix, workdir)
        labels = dict(zip(meta.column_names, meta.column_labels or [], strict=False))
        for col, lblset in (meta.variable_to_label or {}).items():
            value_labels[col] = meta.value_labels.get(lblset, {})
        measures = dict(getattr(meta, "variable_measure", {}) or {})
    else:
        raise DataReadError("Format non pris en charge. Formats acceptés : CSV, TSV, TXT, XLSX, SAV, DTA.")

    df = _clean_frame(df)
    if df.shape[0] < 5 or df.shape[1] < 1:
        raise DataReadError("Le tableau doit compter au moins 5 lignes et 1 colonne.")

    # Application des étiquettes de valeurs SPSS/Stata en conservant l'ordre des codes
    ordered_cols: set[str] = set()
    for col, mapping in value_labels.items():
        if col in df.columns and mapping:
            codes = sorted(mapping)
            cats = [str(mapping[c]) for c in codes]
            series = df[col].map(lambda v, m=mapping: m.get(v, v) if pd.notna(v) else np.nan)
            extra = [str(v) for v in pd.unique(series.dropna()) if str(v) not in cats]
            is_ord = measures.get(col) == "ordinal"
            df[col] = pd.Categorical(series.astype("object").where(series.isna(), series.astype(str)),
                                     categories=cats + extra, ordered=is_ord)
            if is_ord:
                ordered_cols.add(col)

    variables = {c: infer_variable(df[c], c, labels.get(c) or c, c in ordered_cols) for c in df.columns}
    return Dataset(df=df, variables=variables, source_format=suffix.lstrip("."))


def _clean_name(name: str, used: set[str]) -> str:
    s = unicodedata.normalize("NFKC", str(name)).strip()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^\w\-]", "", s) or "variable"
    if s[0].isdigit():
        s = f"v_{s}"
    base, k = s[:60], 2
    while s in used:
        s = f"{base}_{k}"
        k += 1
    used.add(s)
    return s


def _clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
    used: set[str] = set()
    df.columns = [_clean_name(c, used) for c in df.columns]
    for c in df.columns:
        if df[c].dtype == object or pd.api.types.is_string_dtype(df[c].dtype):
            s = df[c].astype("string").str.strip()
            s = s.replace({"": pd.NA, "NA": pd.NA, "N/A": pd.NA, "na": pd.NA, "NaN": pd.NA, ".": pd.NA,
                           "NSP": pd.NA, "nsp": pd.NA})
            # Conversion numérique si au moins 95 % des valeurs non manquantes s'y prêtent
            conv = pd.to_numeric(s.str.replace(NBSP_CHARS, "", regex=True).str.replace(",", ".", regex=False),
                                 errors="coerce")
            nn = s.notna().sum()
            if nn and conv.notna().sum() / nn >= 0.95:
                df[c] = conv
            else:
                df[c] = s.astype(object).where(s.notna(), np.nan)
    return df.reset_index(drop=True)


NBSP_CHARS = r"[\s  ]"


# ---------------------------------------------------------------------------
# Typage
# ---------------------------------------------------------------------------

def infer_variable(s: pd.Series, name: str, label: str, ordered: bool = False) -> VariableInfo:
    n = len(s)
    valid = s.dropna()
    n_valid, n_missing = int(valid.shape[0]), int(n - valid.shape[0])
    n_unique = int(valid.nunique())
    info = VariableInfo(name=name, label=label, kind="nominale", n_valid=n_valid, n_missing=n_missing,
                        n_unique=n_unique)

    if n_valid == 0:
        info.kind, info.suggested_role, info.reason = "nominale", "ignorer", "aucune valeur renseignée"
        return info

    if isinstance(s.dtype, pd.CategoricalDtype):
        info.categories = [str(c) for c in s.cat.categories if (valid == c).any()]
        info.ordered = bool(s.cat.ordered) or ordered
        info.kind = "binaire" if n_unique == 2 else ("ordinale" if info.ordered else "nominale")
        return info

    if pd.api.types.is_datetime64_any_dtype(s):
        info.kind, info.suggested_role, info.reason = "date", "ignorer", "variable de date"
        return info

    is_num = pd.api.types.is_numeric_dtype(s)
    unique_ratio = n_unique / max(n_valid, 1)

    if ID_NAME.search(name) and unique_ratio > 0.5:
        info.kind, info.suggested_role, info.reason = "identifiant", "ignorer", "nom d'identifiant"
        return info
    if unique_ratio > 0.95 and n_valid >= 20 and (not is_num or _all_integers(valid)):
        info.kind, info.suggested_role, info.reason = "identifiant", "ignorer", "valeurs presque toutes uniques"
        return info

    if n_unique == 1:
        info.kind, info.suggested_role, info.reason = "nominale", "ignorer", "variable constante"
        info.categories = [str(valid.iloc[0])]
        return info

    if n_unique == 2:
        info.kind = "binaire"
        info.categories = _sorted_categories(valid)
        return info

    if not is_num:
        if unique_ratio > 0.5 and n_unique > MAX_CATEGORIES * 3:
            info.kind, info.suggested_role, info.reason = "texte", "ignorer", "texte libre"
        else:
            info.kind = "nominale"
            info.categories = _sorted_categories(valid)
            if n_unique > MAX_CATEGORIES * 3:
                info.suggested_role = "ignorer"
                info.reason = "très nombreuses modalités : variable de regroupement possible (grappe, école…)"
            elif n_unique > MAX_CATEGORIES:
                info.reason = "nombreuses modalités : envisager un regroupement"
        return info

    if _all_integers(valid):
        if n_unique <= MAX_CATEGORIES and valid.min() >= 0 and valid.max() <= 20:
            info.categories = _sorted_categories(valid)
            if ORDINAL_NAME.search(name):
                info.kind, info.ordered = "ordinale", True
                info.reason = "ordre présumé d'après le nom : à vérifier"
            else:
                info.kind = "nominale"
                info.reason = ("entiers peu nombreux : vérifier s'il s'agit de codes, d'une échelle ordinale "
                               "ou d'un comptage")
            return info
        if valid.min() >= 0 and ((valid == 0).any() or COUNT_NAME.search(name)):
            info.kind = "comptage"
            return info
    info.kind = "continue"
    return info


def _all_integers(valid: pd.Series) -> bool:
    try:
        arr = valid.to_numpy(dtype=float)
    except (TypeError, ValueError):
        return False
    return bool(np.all(np.isfinite(arr)) and np.all(np.mod(arr, 1) == 0))


def _sorted_categories(valid: pd.Series) -> list[str]:
    uniq = pd.unique(valid)
    try:
        uniq = sorted(uniq)
    except TypeError:
        uniq = sorted(uniq, key=str)
    return [_fmt_cat(u) for u in uniq]


def _fmt_cat(v) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def as_categorical(s: pd.Series, info: VariableInfo) -> pd.Series:
    """Série catégorielle dont les modalités suivent l'ordre validé par l'utilisateur."""
    out = s.map(lambda v: _fmt_cat(v) if pd.notna(v) else np.nan)
    cats = [c for c in info.categories if c in set(out.dropna())] or _sorted_categories(out.dropna())
    extra = [c for c in pd.unique(out.dropna()) if c not in cats]
    return pd.Series(pd.Categorical(out, categories=cats + extra, ordered=info.ordered or info.kind == "ordinale"),
                     index=s.index, name=s.name)
