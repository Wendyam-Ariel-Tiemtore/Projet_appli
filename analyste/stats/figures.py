"""Figures au style homogène, lisibles en impression noir et blanc."""

from __future__ import annotations

import uuid
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# Palette d'Okabe et Ito, distinguable par les personnes daltoniennes
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442", "#000000"]
MAIN = PALETTE[0]

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.6,
    "figure.dpi": 100,
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
    "axes.prop_cycle": matplotlib.cycler(color=PALETTE),
})


def _fr(x, _pos=None):
    s = f"{x:g}"
    return s.replace(".", ",")


def _apply_fr(ax, x: bool = True, y: bool = True):
    if x:
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(_fr))
    if y:
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fr))


def _save(fig, outdir: Path, stem: str) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"{stem}_{uuid.uuid4().hex[:8]}.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def histogram(x: pd.Series, label: str, outdir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(5.2, 3.2))
    data = pd.to_numeric(x, errors="coerce").dropna()
    ax.hist(data, bins="auto", color=MAIN, alpha=0.85, edgecolor="white", linewidth=0.5)
    ax.axvline(data.mean(), color=PALETTE[3], linestyle="--", linewidth=1, label="Moyenne")
    ax.axvline(data.median(), color=PALETTE[1], linestyle=":", linewidth=1.4, label="Médiane")
    ax.set_xlabel(label)
    ax.set_ylabel("Effectif")
    ax.legend(frameon=False)
    _apply_fr(ax)
    return _save(fig, outdir, "hist")


def bar_categories(counts: pd.Series, label: str, outdir: Path) -> Path:
    props = counts / counts.sum() * 100
    fig, ax = plt.subplots(figsize=(5.2, max(2.2, 0.35 * len(props) + 0.8)))
    ax.barh([str(i) for i in props.index][::-1], props.values[::-1], color=MAIN, alpha=0.9)
    for i, v in enumerate(props.values[::-1]):
        ax.text(v + 0.5, i, f"{v:.1f} %".replace(".", ","), va="center", fontsize=8)
    ax.set_xlabel("Pourcentage")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, max(props.max() * 1.18, 5))
    _apply_fr(ax, y=False)
    return _save(fig, outdir, "barres")


def stacked_by_group(ct_pct: pd.DataFrame, x_label: str, y_label: str, outdir: Path) -> Path:
    """Barres empilées à 100 % : modalités de la VD (colonnes) selon les groupes (lignes)."""
    ct_pct = ct_pct.iloc[::-1]  # première modalité en haut, comme dans les tableaux
    fig, ax = plt.subplots(figsize=(5.6, max(2.4, 0.4 * len(ct_pct) + 1)))
    left = np.zeros(len(ct_pct))
    labels = [str(i) for i in ct_pct.index]
    for j, col in enumerate(ct_pct.columns):
        vals = ct_pct[col].to_numpy()
        ax.barh(labels, vals, left=left, color=PALETTE[j % len(PALETTE)], label=str(col), edgecolor="white",
                linewidth=0.5)
        for i, v in enumerate(vals):
            if v >= 8:
                ax.text(left[i] + v / 2, i, f"{v:.0f}", ha="center", va="center", fontsize=7, color="white")
        left += vals
    ax.set_xlim(0, 100)
    ax.set_xlabel(f"{y_label} : répartition en pourcentage")
    ax.set_ylabel(x_label)
    ax.grid(axis="y", visible=False)
    ax.legend(frameon=False, bbox_to_anchor=(1.0, 1.0), loc="upper left", fontsize=8)
    _apply_fr(ax, y=False)
    return _save(fig, outdir, "empile")


def box_by_group(y: pd.Series, g: pd.Series, y_label: str, g_label: str, outdir: Path) -> Path:
    groups = [str(c) for c in (g.cat.categories if hasattr(g, "cat") else sorted(g.dropna().unique()))]
    data = [pd.to_numeric(y[g.astype(str) == k], errors="coerce").dropna() for k in groups]
    keep = [(k, d) for k, d in zip(groups, data, strict=True) if len(d)]
    fig, ax = plt.subplots(figsize=(5.4, 3.2))
    ax.boxplot([d for _, d in keep], tick_labels=[k for k, _ in keep], patch_artist=True,
               boxprops={"facecolor": "#cfe3f3", "edgecolor": MAIN},
               medianprops={"color": PALETTE[3]}, flierprops={"markersize": 3, "alpha": 0.5})
    ax.set_ylabel(y_label)
    ax.set_xlabel(g_label)
    if len(keep) > 5:
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    _apply_fr(ax, x=False)
    return _save(fig, outdir, "boites")


def scatter(x: pd.Series, y: pd.Series, x_label: str, y_label: str, outdir: Path) -> Path:
    d = pd.DataFrame({"x": pd.to_numeric(x, errors="coerce"), "y": pd.to_numeric(y, errors="coerce")}).dropna()
    fig, ax = plt.subplots(figsize=(4.8, 3.4))
    ax.scatter(d["x"], d["y"], s=10, alpha=0.5, color=MAIN, edgecolor="none")
    if len(d) > 2 and d["x"].std() > 0:
        b, a = np.polyfit(d["x"], d["y"], 1)
        xs = np.linspace(d["x"].min(), d["x"].max(), 50)
        ax.plot(xs, a + b * xs, color=PALETTE[3], linewidth=1.2, label="Droite des moindres carrés")
        ax.legend(frameon=False)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    _apply_fr(ax)
    return _save(fig, outdir, "nuage")


def forest(rows: pd.DataFrame, effect_label: str, outdir: Path, log_scale: bool = True,
           diapo: dict | None = None) -> Path:
    """Graphique en forêt : colonnes 'terme', 'est', 'lo', 'hi'.

    `diapo` (facultatif) produit une version pour présentation : police plus grande, couleurs du thème
    (clés 'couleur', 'accent', 'largeur', 'police')."""
    if diapo:
        with plt.rc_context({"font.size": diapo.get("police", 13), "axes.labelsize": diapo.get("police", 13)}):
            return _forest(rows, effect_label, outdir, log_scale, diapo)
    return _forest(rows, effect_label, outdir, log_scale, None)


def _forest(rows, effect_label, outdir, log_scale, diapo):
    rows = rows.iloc[::-1]
    if diapo:
        fig, ax = plt.subplots(figsize=(diapo.get("largeur", 7.0), max(3.0, 0.55 * len(rows) + 1.2)))
        couleur, ecouleur, ms = diapo.get("couleur", MAIN), diapo.get("accent", "#7aa6c8"), 8
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#9AA5AD")
    else:
        fig, ax = plt.subplots(figsize=(5.6, max(2.4, 0.3 * len(rows) + 0.9)))
        couleur, ecouleur, ms = MAIN, "#7aa6c8", 4
    ys = np.arange(len(rows))
    ax.errorbar(rows["est"], ys, xerr=[rows["est"] - rows["lo"], rows["hi"] - rows["est"]], fmt="o",
                color=couleur, ecolor=ecouleur, capsize=3 if diapo else 2, markersize=ms,
                elinewidth=2.2 if diapo else 1.0)
    ax.axvline(1.0 if log_scale else 0.0, color="grey", linestyle="--", linewidth=0.8)
    ax.set_yticks(ys, rows["terme"])
    if log_scale:
        ax.set_xscale("log")
        lo, hi = float(np.nanmin(rows["lo"])), float(np.nanmax(rows["hi"]))
        cands = [0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 4, 5, 10, 20, 50, 100]
        ticks = [t for t in cands if lo * 0.8 <= t <= hi * 1.25] or [1]
        if len(ticks) > 7:
            ticks = ticks[::2] if 1 in ticks[::2] else ticks[1::2]
        ax.xaxis.set_major_locator(mticker.FixedLocator(ticks))
        ax.xaxis.set_minor_locator(mticker.NullLocator())
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(_fr))
    else:
        _apply_fr(ax, y=False)
    ax.set_xlabel(effect_label + " (IC à 95 %)")
    ax.grid(axis="y", visible=False)
    return _save(fig, outdir, "foret")


def scree(eigen: np.ndarray, threshold: np.ndarray | None, outdir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(4.8, 3.0))
    k = np.arange(1, len(eigen) + 1)
    ax.plot(k, eigen, marker="o", color=MAIN, label="Valeurs propres observées")
    if threshold is not None:
        ax.plot(k, threshold, marker="x", linestyle="--", color=PALETTE[3], label="Seuil de Horn (q95)")
    ax.axhline(1, color="grey", linewidth=0.7, linestyle=":")
    ax.set_xlabel("Composante")
    ax.set_ylabel("Valeur propre")
    ax.set_xticks(k)
    ax.legend(frameon=False)
    _apply_fr(ax)
    return _save(fig, outdir, "eboulis")


def factor_map(coords: pd.DataFrame, labels: list[str], inertia: tuple[float, float], outdir: Path,
               groups: list[int] | None = None, title: str = "") -> Path:
    fig, ax = plt.subplots(figsize=(5.6, 4.6))
    colors = [PALETTE[g % len(PALETTE)] for g in groups] if groups else MAIN
    ax.scatter(coords.iloc[:, 0], coords.iloc[:, 1], s=14, c=colors, alpha=0.8)
    for (x, y), lab in zip(coords.iloc[:, :2].to_numpy(), labels, strict=False):
        ax.annotate(lab, (x, y), fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax.axhline(0, color="grey", linewidth=0.6)
    ax.axvline(0, color="grey", linewidth=0.6)
    ax.set_xlabel(f"Axe 1 ({inertia[0]:.1f} %)".replace(".", ","))
    ax.set_ylabel(f"Axe 2 ({inertia[1]:.1f} %)".replace(".", ","))
    _apply_fr(ax)
    return _save(fig, outdir, "plan")


def km_curves(curves: dict[str, pd.DataFrame], time_label: str, outdir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(5.4, 3.4))
    for i, (name, c) in enumerate(curves.items()):
        ax.step(c.index, c.iloc[:, 0], where="post", color=PALETTE[i % len(PALETTE)], label=str(name))
    ax.set_ylim(0, 1.02)
    ax.set_xlabel(time_label)
    ax.set_ylabel("Probabilité de survie")
    ax.legend(frameon=False)
    _apply_fr(ax)
    return _save(fig, outdir, "km")


def caterpillar(u: pd.DataFrame, outdir: Path, label: str) -> Path:
    """Effets aléatoires de niveau 2 ordonnés, avec IC à 95 % ('est', 'se')."""
    u = u.sort_values("est")
    fig, ax = plt.subplots(figsize=(5.6, 3.2))
    xs = np.arange(len(u))
    ax.errorbar(xs, u["est"], yerr=1.96 * u["se"], fmt="o", markersize=2.5, color=MAIN, ecolor="#9cbfd9",
                elinewidth=0.8)
    ax.axhline(0, color=PALETTE[3], linestyle="--", linewidth=0.8)
    ax.set_xlabel(f"{label} (classés)")
    ax.set_ylabel("Effet aléatoire estimé")
    ax.set_xticks([])
    _apply_fr(ax)
    return _save(fig, outdir, "chenille")
