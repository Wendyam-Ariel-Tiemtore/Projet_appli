
import numpy as np
import pandas as pd
import pytest

from analyste.stats import audit
from analyste.stats.io import DataReadError, read_dataset


def test_typage(dataset):
    v = dataset.variables
    assert v["id_femme"].kind == "identifiant"
    assert v["contraception_moderne"].kind == "binaire"
    assert v["age"].kind == "continue"
    assert v["parite"].kind == "comptage"
    assert v["quintile_bien_etre"].kind == "ordinale"
    assert v["grappe"].kind == "nominale" and v["grappe"].suggested_role == "ignorer"


def test_detection_identifiants(dataset):
    ids = audit.detect_identifiers(dataset)
    assert {"nom", "prenom", "telephone"} <= set(ids)
    assert "region" not in ids


def test_pseudonymisation_stable_et_non_reversible(dataset):
    s = dataset.df["grappe"]
    a = audit.pseudonymize(s, b"k" * 32)
    b = audit.pseudonymize(s, b"k" * 32)
    c = audit.pseudonymize(s, b"autre-cle-de-32-octets-exactement")
    assert (a == b).all() and not (a == c).any()
    assert a.nunique() == s.nunique()
    assert not set(a).intersection(set(s))


def test_suppression_identifiants(dataset):
    log = audit.apply_privacy(dataset, {"nom": "supprimer", "telephone": "supprimer"}, b"k" * 32)
    assert "nom" not in dataset.df.columns and "telephone" not in dataset.df.columns
    assert len(log) == 2


def test_csv_point_virgule_virgule_decimale(tmp_path):
    raw = b"a;b;c\n1,5;x;10\n2,5;y;20\n3,5;x;30\n4,5;y;40\n5,5;x;50\n"
    ds = read_dataset(raw, "t.csv", tmp_path)
    assert ds.df["a"].tolist() == [1.5, 2.5, 3.5, 4.5, 5.5]


def test_format_refuse(tmp_path):
    with pytest.raises(DataReadError):
        read_dataset(b"x", "donnees.pkl", tmp_path)


def test_stata_etiquettes(tmp_path):
    import pyreadstat
    df = pd.DataFrame({"sexe": [1, 2, 1, 2, 1, 2], "age": [20, 30, 40, 50, 60, 70]})
    p = tmp_path / "t.dta"
    pyreadstat.write_dta(df, str(p), variable_value_labels={"sexe": {1: "Homme", 2: "Femme"}})
    ds = read_dataset(p.read_bytes(), "t.dta", tmp_path)
    assert set(ds.df["sexe"].astype(str)) == {"Homme", "Femme"}
    assert ds.variables["sexe"].kind == "binaire"


def test_qualite(dataset):
    sec = audit.quality_section(dataset, ["imc", "religion", "contraception_moderne"], "contraception_moderne")
    assert sec.tables and sec.facts["qualite.n"] == len(dataset.df)
    assert np.isfinite(sec.facts["qualite.doublons"])
