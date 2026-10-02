"""Chaîne d'analyse complète : de la base validée au dossier de résultats (Word, Excel, figures, paramètres)."""

from __future__ import annotations

import json
import platform
import warnings
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from .stats import audit, bivariate, descriptive, models, multilevel, multivariate, survival
from .stats.io import KINDS, Dataset
from .stats.results import Section, Table
from .writing.composer import RequestSpec, compose
from .writing.style import nettoyer, nombre

Progress = Callable[[int, str], None]


@dataclass
class AnalysisConfig:
    outcome: str | None = None
    explanatory: list[str] = field(default_factory=list)
    cluster: str | None = None
    level2: list[str] | None = None
    weight: str | None = None
    time_var: str | None = None
    event_var: str | None = None
    survival_group: str | None = None
    event_level: str | None = None
    references: dict[str, str] = field(default_factory=dict)
    blocks: list[list[str]] | None = None
    random_slope: str | None = None
    factorial: bool = True
    scales: dict[str, list[str]] = field(default_factory=dict)
    kinds: dict[str, str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    textes: dict[str, str] = field(default_factory=dict)  # formulation de la variable dans le texte
    redaction: dict[str, str] = field(default_factory=dict)  # unite, evenement, indicateur
    orders: dict[str, list[str]] = field(default_factory=dict)
    privacy_actions: dict[str, str] = field(default_factory=dict)
    literature: bool = False
    keywords: list[str] = field(default_factory=list)
    year_from: int | None = None
    llm: str = "aucun"  # aucun | local | claude
    consent_external: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> AnalysisConfig:
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


def apply_overrides(ds: Dataset, cfg: AnalysisConfig) -> None:
    for v, k in cfg.kinds.items():
        if v in ds.variables and k in KINDS:
            ds.variables[v].kind = k
            ds.variables[v].ordered = k == "ordinale"
    for v, lab in cfg.labels.items():
        if v in ds.variables and lab.strip():
            ds.variables[v].label = lab.strip()[:120]
    for v, txt in cfg.textes.items():
        if v in ds.variables and txt.strip():
            ds.variables[v].texte = nettoyer(txt.strip())[:150]
    for v, order in cfg.orders.items():
        if v in ds.variables and order:
            ds.variables[v].categories = [str(o) for o in order]
    ds.redaction = {k: nettoyer(str(cfg.redaction.get(k, "")).strip())[:200]
                    for k in ("unite", "evenement", "indicateur") if str(cfg.redaction.get(k, "")).strip()}


def run(ds: Dataset, cfg: AnalysisConfig, spec: RequestSpec, workdir: Path, settings, secret: bytes,
        progress: Progress | None = None, provider=None) -> dict[str, Path]:
    say = progress or (lambda pct, msg: None)
    warnings.filterwarnings("ignore")
    workdir.mkdir(parents=True, exist_ok=True)
    figdir = workdir / "figures"
    figdir.mkdir(exist_ok=True)

    say(3, "Protection des identifiants")
    privacy_log = audit.apply_privacy(ds, cfg.privacy_actions, secret)
    apply_overrides(ds, cfg)

    used = [v for v in ([cfg.outcome] if cfg.outcome else []) + cfg.explanatory if v and v in ds.variables]
    used = list(dict.fromkeys(used))
    sections: dict[str, Section] = {}

    say(8, "Audit de qualité des données")
    sections["qualite"] = audit.quality_section(ds, used, cfg.outcome)

    say(15, "Analyse descriptive")
    sections["descriptif"] = descriptive.describe(ds, used, figdir, weight=cfg.weight, outcome=cfg.outcome)

    expl = [v for v in cfg.explanatory if v in ds.variables and v != cfg.outcome and v != cfg.cluster]
    if cfg.outcome and expl:
        say(28, "Analyse bivariée et choix des tests")
        sections["bivarie"] = bivariate.bivariate(ds, cfg.outcome, expl, figdir)

        say(42, "Modélisation multivariée")
        try:
            sections["multivarie"] = models.explain(
                ds, cfg.outcome, [v for v in expl if v not in (cfg.level2 or [])] if cfg.cluster else expl, figdir,
                cfg.references, cfg.event_level, cfg.blocks, cluster=cfg.cluster)
        except Exception as exc:  # noqa: BLE001
            sections["multivarie"] = _failed("multivarie", "Analyse explicative multivariée", exc)

        if cfg.cluster and cfg.cluster in ds.variables:
            say(55, "Modèles multi-niveaux")
            try:
                sections["multiniveau"] = multilevel.multilevel(
                    ds, cfg.outcome, expl, cfg.cluster, figdir, cfg.level2, cfg.references, cfg.event_level,
                    cfg.random_slope)
            except Exception as exc:  # noqa: BLE001
                sections["multiniveau"] = _failed("multiniveau", "Analyse multi-niveaux", exc)

    if cfg.factorial:
        say(66, "Analyses factorielles et typologie")
        quant = [v for v in used if ds.variables[v].kind in ("continue", "comptage") and v != cfg.outcome]
        qual = [v for v in used if ds.variables[v].kind in ("binaire", "nominale", "ordinale") and v != cfg.outcome]
        coords, desc_vars = None, used
        if len(quant) >= 3:
            sections["acp"] = multivariate.pca(ds, quant, figdir)
            coords = sections["acp"].extra.get("coords")
        if len(qual) >= 3:
            sections["acm"] = multivariate.mca(ds, qual, figdir)
            if coords is None:
                coords = sections["acm"].extra.get("coords")
        if coords is not None and len(coords) >= 30:
            sections["cah"] = multivariate.classify(ds, coords, desc_vars, figdir)
    for name, items in cfg.scales.items():
        sec = multivariate.scale_reliability(ds, items, name)
        sections.setdefault("descriptif", Section("descriptif", "Analyse descriptive")).paragraphs += sec.paragraphs
        sections["descriptif"].tables += sec.tables
        sections["descriptif"].refs |= sec.refs

    if cfg.time_var and cfg.event_var:
        say(74, "Analyse de survie")
        try:
            sections["survie"] = survival.survival(ds, cfg.time_var, cfg.event_var,
                                                   [v for v in expl if v not in (cfg.time_var, cfg.event_var)],
                                                   figdir, cfg.survival_group, cfg.references)
        except Exception as exc:  # noqa: BLE001
            sections["survie"] = _failed("survie", "Analyse de survie", exc)

    lit_refs, lit_cites, lit_digest = [], [], ""
    if cfg.literature and cfg.keywords:
        say(80, "Recherche bibliographique (mots-clés uniquement)")
        from .literature import review, sources
        works, log = sources.search(cfg.keywords, limit=60, year_from=cfg.year_from,
                                    api_key=settings.openalex_api_key or None, mailto=settings.openalex_mailto or None)
        extractor = namer = None
        from .writing.llm import NoProvider
        if provider is not None and not isinstance(provider, NoProvider):
            from .writing.assist import make_extractor, make_namer
            extractor, namer = make_extractor(provider), make_namer(provider)
        sections["litterature"] = review.literature_section(works, log, spec.title, extractor=extractor,
                                                            namer=namer)
        sel = sections["litterature"].extra.get("works", [])
        lit_refs = review.work_references(sections["litterature"])
        lit_cites = [w.citation() for w in sel]
        lit_digest = "\n".join(f"- ({w.citation()}) {w.title}. Objet : {w.extracted.get('objet', '')} Résultats : "
                               f"{w.extracted.get('resultats', '')}" for w in sel)

    say(86, "Rédaction du document")
    data_info = _data_info(ds, cfg, sections)
    var_table = _variables_table(ds, cfg)
    software = _software_versions()
    document = compose(spec, sections, data_info, var_table, privacy_log, provider, lit_refs, lit_cites, lit_digest,
                       software)

    say(93, "Mise en forme Word et Excel")
    from .report.docx_builder import build_docx, export_tables_xlsx
    stem = _slug(spec.title) or "rapport"
    docx_path = build_docx(document, workdir / f"{stem}.docx")
    all_tables = [var_table] + [t for s in sections.values() for t in s.tables]
    xlsx_path = export_tables_xlsx(all_tables, workdir / f"{stem}_tableaux.xlsx")
    params = workdir / "parametres_reproductibilite.json"
    params.write_text(json.dumps(data_info["parameters"], ensure_ascii=False, indent=2), encoding="utf-8")
    bundle = workdir / f"{stem}_dossier_complet.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(docx_path, docx_path.name)
        z.write(xlsx_path, xlsx_path.name)
        z.write(params, params.name)
        for f in sorted(figdir.glob("*.png")):
            z.write(f, f"figures/{f.name}")
    say(100, "Terminé")
    return {"docx": docx_path, "xlsx": xlsx_path, "zip": bundle, "params": params,
            "log": document.log}  # type: ignore[dict-item]


def _failed(key: str, title: str, exc: Exception) -> Section:
    s = Section(key=key, title=title)
    s.warnings.append(f"Cette analyse n'a pas pu être conduite ({type(exc).__name__}). Vérifier le typage des "
                      "variables, les effectifs par modalité et l'absence de variables redondantes.")
    return s


def _data_info(ds: Dataset, cfg: AnalysisConfig, sections: dict[str, Section]) -> dict:
    n = len(ds.df)
    used = [v for v in [cfg.outcome, *cfg.explanatory] if v]
    desc = (f"La base analysée compte {nombre(n, 'observations', True)} et {nombre(len(ds.df.columns), 'variables')}, "
            f"dont {nombre(len(set(used)), 'variables')} retenues pour les analyses.")
    if cfg.outcome:
        desc += f" La variable dépendante est {ds.variables[cfg.outcome].prose}."
    if cfg.cluster:
        k = ds.df[cfg.cluster].nunique()
        desc += (f" Les observations sont réparties entre {nombre(k, 'unités', True)} de niveau 2, identifiées par "
                 f"{ds.variables[cfg.cluster].prose}.")
    params = {
        "date_analyse": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "graine_aleatoire": 42, "seuil": 0.05, "correction_multiplicite": "Benjamini-Hochberg",
        "observations": n, "variable_dependante": cfg.outcome, "variables_explicatives": cfg.explanatory,
        "contexte": cfg.cluster, "niveau2": cfg.level2, "poids": cfg.weight, "references": cfg.references,
        "modalite_modelisee": cfg.event_level, "blocs": cfg.blocks, "pente_aleatoire": cfg.random_slope,
        "types": {v: ds.variables[v].kind for v in set(used) if v in ds.variables},
        "logiciels": _software_versions(), "python": platform.python_version(),
        "quadrature_gauss_hermite": 15, "repetitions_horn": 500,
    }
    return {"n": n, "description": desc, "parameters": params, "weighted": bool(cfg.weight)}


def _variables_table(ds: Dataset, cfg: AnalysisConfig) -> Table:
    rows = []
    roles = {}
    if cfg.outcome:
        roles[cfg.outcome] = "Dépendante"
    for v in cfg.explanatory:
        roles.setdefault(v, "Explicative" + (" (niveau 2)" if cfg.level2 and v in cfg.level2 else ""))
    if cfg.cluster:
        roles[cfg.cluster] = "Contexte (niveau 2)"
    if cfg.weight:
        roles[cfg.weight] = "Pondération"
    if cfg.time_var:
        roles[cfg.time_var] = "Durée"
    if cfg.event_var:
        roles.setdefault(cfg.event_var, "Événement")
    for v, role in roles.items():
        if v not in ds.variables:
            continue
        info = ds.variables[v]
        mods = ", ".join(info.categories[:8]) + ("…" if len(info.categories) > 8 else "") if info.categories else "-"
        rows.append({"Variable": info.label, "Nom": v, "Rôle": role, "Type": info.kind,
                     "Modalités": mods if info.kind in ("binaire", "nominale", "ordinale")
                     and not role.startswith("Contexte") else (f"{len(info.categories)} modalités"
                                                              if info.categories else "-")})
    return Table(title="Variables de l'étude", data=pd.DataFrame(rows),
                 note="Le type de chaque variable détermine les méthodes appliquées (voir la section consacrée aux méthodes "
                      "d'analyse).")


def _software_versions() -> dict[str, str]:
    import numpy
    import scipy
    import sklearn
    import statsmodels
    return {"pandas": pd.__version__, "NumPy": numpy.__version__, "SciPy": scipy.__version__,
            "statsmodels": statsmodels.__version__, "scikit-learn": sklearn.__version__}


def _slug(s: str) -> str:
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return s[:60]


def config_to_json(cfg: AnalysisConfig) -> str:
    return json.dumps(asdict(cfg), ensure_ascii=False)
