"""Analyses multivariées descriptives : ACP, ACM (AFCM), classification ascendante hiérarchique, α de Cronbach."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.cluster.hierarchy import fcluster, linkage
from sklearn.metrics import silhouette_score

from ..writing.phrases import Redac, pcrit
from ..writing.style import a as a_
from ..writing.style import de, enumeration, guillemets, nombre, ordinal
from . import figures, fmt
from .io import Dataset, as_categorical
from .results import Figure, Section, Table

SEED = 42


# ---------------------------------------------------------------------------
# Diagnostics de factorabilité
# ---------------------------------------------------------------------------

def kmo(R: np.ndarray) -> float:
    inv = np.linalg.pinv(R)
    d = np.sqrt(np.outer(np.diag(inv), np.diag(inv)))
    partial = -inv / d
    np.fill_diagonal(partial, 0)
    r2 = R.copy()
    np.fill_diagonal(r2, 0)
    return float((r2 ** 2).sum() / ((r2 ** 2).sum() + (partial ** 2).sum()))


def bartlett_sphericity(R: np.ndarray, n: int) -> tuple[float, int, float]:
    p = R.shape[0]
    det = np.linalg.det(R)
    det = max(det, 1e-300)
    chi = -(n - 1 - (2 * p + 5) / 6) * np.log(det)
    dof = p * (p - 1) // 2
    return float(chi), dof, float(stats.chi2.sf(chi, dof))


def horn_parallel(n: int, p: int, reps: int = 500, q: float = 0.95) -> np.ndarray:
    rng = np.random.default_rng(SEED)
    eig = np.empty((reps, p))
    for i in range(reps):
        z = rng.standard_normal((n, p))
        eig[i] = np.sort(np.linalg.eigvalsh(np.corrcoef(z, rowvar=False)))[::-1]
    return np.quantile(eig, q, axis=0)


def cronbach_alpha(items: pd.DataFrame) -> float:
    items = items.dropna()
    k = items.shape[1]
    if k < 2 or len(items) < 3:
        return np.nan
    var_items = items.var(ddof=1).sum()
    var_tot = items.sum(axis=1).var(ddof=1)
    return float(k / (k - 1) * (1 - var_items / var_tot)) if var_tot > 0 else np.nan


# ---------------------------------------------------------------------------
# ACP
# ---------------------------------------------------------------------------

def pca(ds: Dataset, variables: list[str], outdir: Path) -> Section:
    sec = Section(key="acp", title="Analyse en composantes principales", level=2)
    sec.refs |= {"kaiser1974", "bartlett1950", "horn1965"}
    df = ds.df[variables].apply(pd.to_numeric, errors="coerce").dropna()
    n, p = df.shape
    labels = [ds.variables[v].label for v in variables]
    if n < 30 or p < 3:
        sec.warnings.append("L'ACP n'a pas été réalisée : elle nécessite au moins trois (03) variables quantitatives "
                            "et trente (30) observations complètes.")
        return sec
    Z = (df - df.mean()) / df.std(ddof=1)
    R = np.corrcoef(Z.to_numpy(), rowvar=False)
    eigval, eigvec = np.linalg.eigh(R)
    order = np.argsort(eigval)[::-1]
    eigval, eigvec = eigval[order], eigvec[:, order]
    k_kmo = kmo(R)
    chi, dof, p_b = bartlett_sphericity(R, n)
    horn = horn_parallel(n, p)
    retained = int(np.sum(np.cumprod(eigval > horn)))
    sec.facts.update({"acp.kmo": k_kmo, "acp.bartlett_chi2": chi, "acp.bartlett_ddl": dof, "acp.bartlett_p": p_b,
                      "acp.n": n, "acp.p": p, "acp.retenues": retained})
    rows = []
    cum = 0.0
    for i, (ev, h) in enumerate(zip(eigval, horn, strict=True), start=1):
        share = ev / p * 100
        cum += share
        rows.append({"Composante": f"CP{i}", "Valeur propre": fmt.num(ev, 3), "Variance (%)": fmt.num(share, 1),
                     "Variance cumulée (%)": fmt.num(cum, 1), "Seuil de Horn (q95)": fmt.num(h, 3),
                     "Retenue": "Oui" if i <= retained else "Non"})
        sec.facts[f"acp.cp{i}.valeur_propre"] = ev
        sec.facts[f"acp.cp{i}.variance_pct"] = share
        sec.facts[f"acp.cp{i}.variance_cumulee"] = cum
        sec.facts[f"acp.cp{i}.horn"] = h
    sec.tables.append(Table(
        title="Valeurs propres et critère de rétention de l'analyse parallèle de Horn",
        data=pd.DataFrame(rows),
        note=(f"Indice KMO = {fmt.num(k_kmo, 3)} ; test de sphéricité de Bartlett : χ²({dof}) = {fmt.num(chi)} ; "
              f"{fmt.p_phrase(p_b)} ; n = {fmt.integer(n)}. Une composante est retenue si sa valeur propre dépasse le "
              "quantile d'ordre 0,95 des valeurs propres de 500 jeux de données aléatoires de même dimension.")))
    fig = figures.scree(eigval, horn, outdir)
    sec.figures.append(Figure(fig, "Éboulis des valeurs propres et seuil de l'analyse parallèle"))

    factorable = k_kmo >= 0.5 and p_b < 0.05 and retained >= 1
    kmo_lab = ("inacceptable" if k_kmo < 0.5 else "médiocre" if k_kmo < 0.6 else "moyen" if k_kmo < 0.7 else
               "bon" if k_kmo < 0.8 else "très bon" if k_kmo < 0.9 else "excellent")
    R = Redac(ds)
    sec.paragraphs.append(
        f"Avant toute interprétation, nous avons vérifié la factorabilité des {nombre(p, 'variables')} sur "
        f"{nombre(n, 'observations', True)} complètes. L'indice de Kaiser-Meyer-Olkin vaut {fmt.num(k_kmo, 3)}, un "
        f"niveau jugé {kmo_lab}. Par ailleurs, le test de sphéricité de Bartlett "
        + ("rejette" if p_b < 0.05 else "ne rejette pas")
        + f" l'hypothèse d'indépendance mutuelle des variables, avec un khi-deux de {fmt.num(chi)} pour "
        f"{nombre(dof, 'degrés')} de liberté et {pcrit(p_b)}. Enfin, l'analyse parallèle de Horn conduit à retenir "
        + (f"{nombre(retained, 'composantes', True)}." if retained != 1 else "une seule composante."))
    if not factorable:
        sec.paragraphs.append(
            "Les diagnostics ne justifient donc pas une réduction de dimension, car les variables ne partagent pas de "
            "structure factorielle suffisante. Ce constat est en soi un résultat : les dimensions mesurées doivent être "
            "analysées séparément plutôt que résumées par un indice composite.")
        return sec
    kshow = max(retained, 2)
    loadings = eigvec[:, :kshow] * np.sqrt(eigval[:kshow])
    lrows = []
    for v, lab, row in zip(variables, labels, loadings, strict=True):
        d = {"Variable": lab}
        for j in range(kshow):
            d[f"CP{j + 1}"] = fmt.num(row[j], 3)
            sec.facts[f"acp.{v}.cp{j + 1}"] = row[j]
        d["Qualité (cos²)"] = fmt.num(float((row[:kshow] ** 2).sum()), 3)
        lrows.append(d)
    sec.tables.append(Table(title="Corrélations des variables avec les composantes (saturations)",
                            data=pd.DataFrame(lrows),
                            note="Saturations supérieures à 0,5 en valeur absolue : contribution marquée à la "
                                 "composante. cos² : qualité de représentation sur les composantes présentées."))
    for j in range(retained):
        strong = sorted(zip(variables, loadings[:, j], strict=True), key=lambda t: -abs(t[1]))
        pos = [f"{a_(R.v(v))} ({fmt.num(x, 2)})" for v, x in strong if x >= 0.5]
        neg = [f"{a_(R.v(v))} ({fmt.num(x, 2)})" for v, x in strong if x <= -0.5]
        txt = (f"La {ordinal(j + 1, True)} composante restitue {fmt.num(eigval[j] / p * 100, 1)} % de l'inertie "
               "totale.")
        if pos:
            txt += " Elle est corrélée positivement " + enumeration(pos)
        if neg:
            txt += (", et négativement " if pos else " Elle est corrélée négativement ") + enumeration(neg)
        if not pos and not neg:
            txt += " Aucune variable n'y présente une saturation supérieure à 0,5 en valeur absolue"
        sec.paragraphs.append(txt + ".")
        if j == 0:
            sec.key_points.append(txt + ".")
    fig = figures.factor_map(pd.DataFrame(loadings[:, :2]), labels, (eigval[0] / p * 100, eigval[1] / p * 100),
                             outdir, title="Cercle des corrélations")
    sec.figures.append(Figure(fig, "Projection des variables sur le premier plan factoriel"))
    scores = Z.to_numpy() @ eigvec[:, :kshow]
    sec.extra["coords"] = pd.DataFrame(scores, index=df.index)
    sec.method_notes.append(
        "Les variables quantitatives sont résumées par une analyse en composantes principales normée. Sa pertinence "
        "est vérifiée au préalable par l'indice de Kaiser-Meyer-Olkin (Kaiser, 1974), le test de sphéricité de "
        "Bartlett (1950) et l'analyse parallèle de Horn (1965), plus exigeante que la règle de Kaiser.")
    return sec


# ---------------------------------------------------------------------------
# ACM / AFCM
# ---------------------------------------------------------------------------

def mca(ds: Dataset, variables: list[str], outdir: Path, max_axes: int = 5) -> Section:
    sec = Section(key="acm", title="Analyse des correspondances multiples", level=2)
    sec.refs |= {"greenacre2017", "benzecri1979"}
    cols = {ds.variables[v].label: as_categorical(ds.df[v], ds.variables[v]) for v in variables}
    df = pd.DataFrame(cols).dropna()
    Q = len(variables)
    n = len(df)
    if Q < 3 or n < 30:
        sec.warnings.append("L'ACM n'a pas été réalisée : elle nécessite au moins trois (03) variables qualitatives "
                            "et trente (30) observations complètes.")
        return sec
    Z = pd.get_dummies(df, prefix_sep=" = ", dtype=float)
    Z = Z.loc[:, Z.sum() > 0]
    names = list(Z.columns)
    Zm = Z.to_numpy()
    P = Zm / (n * Q)
    r = P.sum(axis=1)
    c = P.sum(axis=0)
    S = (P - np.outer(r, c)) / np.sqrt(np.outer(r, c))
    U, sv, Vt = np.linalg.svd(S, full_matrices=False)
    lam = sv ** 2
    K = Zm.shape[1]
    nax = min(max_axes, K - Q)
    lam = lam[:K - Q]
    corr = np.where(lam > 1 / Q, (Q / (Q - 1)) ** 2 * (lam - 1 / Q) ** 2, 0)
    corr_pct = corr / corr.sum() * 100 if corr.sum() > 0 else np.zeros_like(corr)
    raw_pct = lam / lam.sum() * 100
    rows = []
    for i in range(nax):
        rows.append({"Axe": i + 1, "Valeur propre": fmt.num(lam[i], 4), "Inertie brute (%)": fmt.num(raw_pct[i], 1),
                     "Inertie corrigée de Benzécri (%)": fmt.num(corr_pct[i], 1)})
        sec.facts[f"acm.axe{i + 1}.inertie_corrigee"] = corr_pct[i]
        sec.facts[f"acm.axe{i + 1}.inertie_brute"] = raw_pct[i]
    sec.tables.append(Table(title="Valeurs propres et taux d'inertie des axes de l'ACM", data=pd.DataFrame(rows),
                            note="Les taux bruts sous-estiment fortement la part d'information des premiers axes en "
                                 "ACM ; les taux corrigés de Benzécri (1979) en donnent une mesure plus réaliste."))
    G = (Vt.T[:, :nax] * sv[:nax]) / np.sqrt(c)[:, None]
    ctr = (c[:, None] * G ** 2) / lam[:nax] * 100
    cos2 = G ** 2 / np.maximum((G ** 2).sum(axis=1, keepdims=True), 1e-12)
    crow = []
    mean_ctr = 100 / K
    for i, nm in enumerate(names):
        crow.append({"Modalité": nm, "Coord. axe 1": fmt.num(G[i, 0], 3), "Contrib. axe 1 (%)": fmt.num(ctr[i, 0], 1),
                     "Coord. axe 2": fmt.num(G[i, 1], 3) if nax > 1 else "-",
                     "Contrib. axe 2 (%)": fmt.num(ctr[i, 1], 1) if nax > 1 else "-",
                     "cos² (plan 1-2)": fmt.num(cos2[i, :2].sum(), 3)})
    sec.tables.append(Table(title="Coordonnées, contributions et qualité de représentation des modalités",
                            data=pd.DataFrame(crow),
                            note=f"Une modalité contribue notablement à un axe si sa contribution dépasse la "
                                 f"contribution moyenne, soit {fmt.num(mean_ctr, 1)} %."))
    R = Redac(ds)
    by_label = {ds.variables[v].label: v for v in variables}

    def modalite(nm: str) -> str:
        lab, _, mod = nm.partition(" = ")
        return f"{guillemets(mod)} {de(R.v(by_label.get(lab, lab)))}"

    for ax in range(min(2, nax)):
        neg = [modalite(names[i]) for i in np.argsort(G[:, ax]) if ctr[i, ax] > mean_ctr and G[i, ax] < 0][:4]
        pos = [modalite(names[i]) for i in np.argsort(-G[:, ax]) if ctr[i, ax] > mean_ctr and G[i, ax] > 0][:4]
        txt = (f"Le {ordinal(ax + 1)} axe, qui concentre {fmt.num(corr_pct[ax], 1)} % de l'inertie corrigée, ")
        if ax > 0 and corr_pct[ax] < 5:
            sec.paragraphs.append(f"Le {ordinal(ax + 1)} axe ne concentre que {fmt.num(corr_pct[ax], 1)} % de "
                                  "l'inertie corrigée : il apporte peu d'information supplémentaire et n'est donc pas "
                                  "interprété.")
            continue
        if neg and pos:
            txt += (f"oppose les modalités {enumeration(neg)}, situées du côté négatif, aux modalités "
                    f"{enumeration(pos)}, situées du côté positif.")
        elif neg or pos:
            txt += f"est principalement construit par les modalités {enumeration(neg or pos)}."
        else:
            txt += "n'est porté par aucune modalité dont la contribution dépasse la contribution moyenne."
        sec.paragraphs.append(txt)
        if ax == 0:
            sec.key_points.append(txt)
    shown = [nm if (ctr[i, 0] > mean_ctr or (nax > 1 and ctr[i, 1] > mean_ctr)) else ""
             for i, nm in enumerate(names)]
    fig = figures.factor_map(pd.DataFrame(G[:, :2]), shown, (corr_pct[0], corr_pct[1] if nax > 1 else 0), outdir,
                             title="Modalités sur le premier plan factoriel")
    sec.figures.append(Figure(fig, "Représentation des modalités sur le premier plan de l'ACM"))
    F = (U[:, :nax] * sv[:nax]) / np.sqrt(r)[:, None]
    keep = max(2, int(np.sum(corr_pct[:nax] > 5)))
    sec.extra["coords"] = pd.DataFrame(F[:, :keep], index=df.index)
    sec.method_notes.append(
        "Les variables qualitatives sont analysées conjointement par une analyse des correspondances multiples "
        "(Greenacre, 2017), dont les taux d'inertie sont corrigés selon Benzécri (1979). Les axes sont interprétés à "
        "partir des modalités dont la contribution dépasse la contribution moyenne.")
    return sec


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify(ds: Dataset, coords: pd.DataFrame, describe_vars: list[str], outdir: Path,
             k_range: range = range(2, 8)) -> Section:
    sec = Section(key="cah", title="Typologie par classification ascendante hiérarchique", level=2)
    sec.refs |= {"ward1963", "rousseeuw1987"}
    X = coords.to_numpy()
    n = len(X)
    if n < 30:
        return sec
    rng = np.random.default_rng(SEED)
    sample = rng.choice(n, size=min(n, 3000), replace=False)
    if n <= 6000:
        Lk = linkage(X, method="ward")
        labels_for = {k: fcluster(Lk, k, criterion="maxclust") for k in k_range}
        method = "classification ascendante hiérarchique (critère de Ward)"
    else:
        from sklearn.cluster import KMeans
        labels_for = {k: KMeans(k, n_init=10, random_state=SEED).fit_predict(X) + 1 for k in k_range}
        method = "méthode des k-moyennes (effectif trop élevé pour une CAH complète)"
    sil = {k: float(silhouette_score(X[sample], lab[sample])) for k, lab in labels_for.items()
           if len(set(lab[sample])) > 1}
    if not sil:
        return sec
    k_best = max(sil, key=sil.get)
    lab = labels_for[k_best]
    sec.facts.update({"cah.k": k_best, "cah.silhouette": sil[k_best]})
    srows = [{"Nombre de classes": k, "Largeur moyenne de silhouette": fmt.num(s, 3),
              "Retenu": "Oui" if k == k_best else ""} for k, s in sil.items()]
    sec.tables.append(Table(title="Choix du nombre de classes", data=pd.DataFrame(srows),
                            note="La partition retenue maximise la largeur moyenne de silhouette (Rousseeuw, 1987) ; "
                                 "une valeur supérieure à 0,25 indique une structure faible, à 0,50 une structure "
                                 "raisonnable, à 0,70 une structure forte."))
    s_lab = ("forte" if sil[k_best] > 0.7 else "raisonnable" if sil[k_best] > 0.5 else "faible"
             if sil[k_best] > 0.25 else "très peu marquée")
    sizes = pd.Series(lab).value_counts().sort_index()
    R = Redac(ds)
    parts = [f"{fmt.integer(v)} ({fmt.pct(v / n)})" for v in sizes.values]
    sec.paragraphs.append(
        f"La {method}, appliquée aux coordonnées factorielles, conduit à retenir {nombre(k_best, 'classes', True)}. "
        f"Cette partition maximise la largeur moyenne de silhouette, qui vaut {fmt.num(sil[k_best], 3)}, ce qui "
        f"traduit une structure {s_lab}. Les classes comptent respectivement {enumeration(parts)} observations.")
    sec.key_points.append(f"La typologie distingue {nombre(k_best, 'classes', True)} de {R.unite}, avec une "
                          f"structure {s_lab}.")
    portraits = []
    # Description des classes par les valeurs-tests
    idx = coords.index
    cl = pd.Series(lab, index=idx, name="classe")
    desc_rows = []
    for k in sizes.index:
        mask = cl == k
        nk = int(mask.sum())
        feats = []
        for v in describe_vars:
            info = ds.variables[v]
            col = ds.df.loc[idx, v]
            if info.kind in ("binaire", "nominale", "ordinale"):
                s = as_categorical(col, info)
                for mod in s.cat.categories:
                    nj = int((s == mod).sum())
                    nkj = int(((s == mod) & mask).sum())
                    if nj == 0 or nj == n:
                        continue
                    var = nk * (n - nk) / (n - 1) * (nj / n) * (1 - nj / n)
                    vt = (nkj - nk * nj / n) / np.sqrt(var) if var > 0 else 0
                    if vt > 2:
                        feats.append((vt, f"{info.label} = {mod} ({fmt.pct(nkj / nk)} contre {fmt.pct(nj / n)})",
                                      f"la modalité {guillemets(str(mod))} {de(R.v(v))} ({fmt.pct(nkj / nk)} "
                                      f"contre {fmt.pct(nj / n)} dans l'ensemble)"))
            elif info.kind in ("continue", "comptage"):
                x = pd.to_numeric(col, errors="coerce")
                m, mk, sd = x.mean(), x[mask].mean(), x.std(ddof=0)
                if sd > 0:
                    vt = (mk - m) / np.sqrt(sd ** 2 / nk * (n - nk) / (n - 1))
                    if abs(vt) > 2:
                        feats.append((abs(vt), f"{info.label} {'élevé' if vt > 0 else 'faible'} (moyenne "
                                               f"{fmt.num(mk)} contre {fmt.num(m)})",
                                      f"des valeurs plus {'élevées' if vt > 0 else 'faibles'} {de(R.v(v))} "
                                      f"(moyenne de {fmt.num(mk)} contre {fmt.num(m)})"))
        feats.sort(key=lambda t: -t[0])
        top = [f for _, f, _ in feats[:5]]
        desc_rows.append({"Classe": f"Classe {k}", "Effectif": fmt.integer(nk), "Part": fmt.pct(nk / n),
                          "Caractéristiques sur-représentées (valeur-test > 2)": " ; ".join(top) or "aucune marquée"})
        if feats:
            items = [t if i == 0 else t.replace(" dans l'ensemble)", ")") for i, (_, _, t) in enumerate(feats[:3])]
            portraits.append(f"La classe {k}, qui regroupe {fmt.pct(nk / n)} des {R.unite}, se caractérise "
                             f"notamment par {enumeration(items)}.")
        else:
            portraits.append(f"La classe {k}, qui regroupe {fmt.pct(nk / n)} des {R.unite}, ne présente pas de "
                             "caractéristique nettement sur-représentée.")
        sec.facts[f"cah.classe{k}.n"] = nk
        sec.facts[f"cah.classe{k}.part"] = 100 * nk / n
    sec.tables.append(Table(title="Description des classes", data=pd.DataFrame(desc_rows),
                            note="Les modalités et moyennes listées sont significativement sur-représentées dans la "
                                 "classe (valeur-test supérieure à 2, soit environ p < 0,05). Entre parenthèses : "
                                 "fréquence ou moyenne dans la classe contre l'ensemble."))
    sec.paragraphs.extend(portraits)
    if coords.shape[1] >= 2:
        fig = figures.factor_map(coords.iloc[sample[:800]].reset_index(drop=True),
                                 [""] * min(800, len(sample)), (0, 0), outdir,
                                 groups=[int(x) for x in lab[sample[:800]]], title="Individus colorés par classe")
        sec.figures.append(Figure(fig, "Individus sur le premier plan factoriel, colorés selon leur classe"))
    sec.extra["classes"] = cl
    sec.method_notes.append(
        "Une typologie est construite par classification ascendante hiérarchique sur les coordonnées factorielles, "
        "selon le critère d'agrégation de Ward (1963) ; le nombre de classes maximise la largeur moyenne de "
        "silhouette (Rousseeuw, 1987). Les classes sont décrites par les modalités et moyennes significativement "
        "sur-représentées (valeurs-tests).")
    return sec


def scale_reliability(ds: Dataset, items: list[str], name: str) -> Section:
    sec = Section(key="cronbach", title=f"Cohérence interne de l'échelle « {name} »", level=3)
    sec.refs.add("cronbach1951")
    df = ds.df[items].apply(pd.to_numeric, errors="coerce")
    a = cronbach_alpha(df)
    rows = [{"Item retiré": "(aucun)", "α de Cronbach": fmt.num(a, 3)}]
    for it in items:
        rows.append({"Item retiré": ds.variables[it].label,
                     "α de Cronbach": fmt.num(cronbach_alpha(df.drop(columns=[it])), 3)})
    sec.tables.append(Table(title=f"α de Cronbach de l'échelle « {name} »", data=pd.DataFrame(rows),
                            note="Seuil conventionnel de 0,70 pour une recherche appliquée. Un α faible pour un indice "
                                 "construit par comptage traduit un indice formatif, non une mauvaise mesure."))
    sec.facts[f"cronbach.{name}"] = a
    sec.paragraphs.append(
        f"L'α de Cronbach de l'échelle {guillemets(name)}, composée de {nombre(len(items), 'items')}, vaut "
        f"{fmt.num(a, 3)}, "
        + ("au-dessus du seuil conventionnel de 0,70 : les items mesurent donc un même construit de manière cohérente."
           if a >= 0.7 else
           "en deçà du seuil conventionnel de 0,70 : les items ne mesurent donc pas un construit unique. Si l'indice "
           "est un comptage de pratiques distinctes, il doit être traité comme un indice formatif."))
    return sec
