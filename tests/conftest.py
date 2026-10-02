import sys
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")


@pytest.fixture(scope="session")
def demo_df():
    from scripts.generate_demo_data import simulate
    return simulate(n_clusters=80, seed=7)


@pytest.fixture(scope="session")
def demo_csv(tmp_path_factory, demo_df):
    p = tmp_path_factory.mktemp("donnees") / "enquete.csv"
    demo_df.to_csv(p, index=False, sep=";", decimal=",")
    return p


@pytest.fixture()
def dataset(demo_csv, tmp_path):
    from analyste.stats.io import read_dataset
    ds = read_dataset(demo_csv.read_bytes(), demo_csv.name, tmp_path)
    ds.variables["instruction"].kind = "ordinale"
    ds.variables["instruction"].ordered = True
    return ds
