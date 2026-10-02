"""Recherche bibliographique dans les bases ouvertes (OpenAlex, repli Crossref).

Confidentialité : seuls les mots-clés validés par l'utilisateur sont transmis. Aucune donnée, aucun
résultat d'analyse ni aucun identifiant personnel ne quitte la machine par ce module.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field

import httpx

OPENALEX = "https://api.openalex.org/works"
CROSSREF = "https://api.crossref.org/works"
USER_AGENT = "AnalysteAcademique/1.0 (application locale de recherche ; https://github.com/Wendyam-Ariel-Tiemtore/Projet_appli)"


@dataclass
class Work:
    key: str
    title: str
    authors: list[str]
    year: int | None
    venue: str
    doi: str | None
    abstract: str
    cited_by: int
    is_oa: bool = False
    volume: str = ""
    issue: str = ""
    pages: str = ""
    kind: str = ""
    source: str = "OpenAlex"
    url: str = ""
    extracted: dict = field(default_factory=dict)

    def citation(self) -> str:
        """Forme courte « Nom, année » ou « Nom et Nom, année » ou « Nom et al., année »."""
        surnames = [_surname(a) for a in self.authors] or ["Anonyme"]
        y = self.year or "s. d."
        if len(surnames) == 1:
            return f"{surnames[0]}, {y}"
        if len(surnames) == 2:
            return f"{surnames[0]} et {surnames[1]}, {y}"
        return f"{surnames[0]} et al., {y}"

    def apa(self) -> str:
        auth = _apa_authors(self.authors)
        y = f"({self.year})" if self.year else "(s. d.)"
        title = self.title.rstrip(".")
        ref = f"{auth} {y}. {title}."
        if self.venue:
            ref += f" *{self.venue}*"
            if self.volume:
                ref += f", *{self.volume}*"
                if self.issue:
                    ref += f"({self.issue})"
            if self.pages:
                ref += f", {self.pages}"
            ref += "."
        if self.doi:
            ref += f" https://doi.org/{self.doi}"
        return ref


def _surname(full: str) -> str:
    full = full.strip()
    if "," in full:
        return full.split(",")[0].strip()
    parts = full.split()
    return parts[-1] if parts else full


def _initials(given: str) -> str:
    out = []
    for p in re.split(r"[\s]+", given.strip()):
        if not p:
            continue
        sub = [s for s in p.split("-") if s]
        out.append("-".join(f"{s[0]}." for s in sub))
    return " ".join(out)


def _apa_one(full: str) -> str:
    if "," in full:
        sur, given = [x.strip() for x in full.split(",", 1)]
    else:
        parts = full.split()
        if len(parts) == 1:
            return parts[0]
        sur, given = parts[-1], " ".join(parts[:-1])
    return f"{sur}, {_initials(given)}".strip().rstrip(",")


def _apa_authors(authors: list[str]) -> str:
    if not authors:
        return "Anonyme."
    a = [_apa_one(x) for x in authors]
    if len(a) == 1:
        return a[0]
    if len(a) <= 20:
        return ", ".join(a[:-1]) + ", et " + a[-1]
    return ", ".join(a[:19]) + ", … " + a[-1]


def reconstruct_abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    positions = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def _norm_title(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", s or "")).strip()


def build_query(keywords: list[str]) -> str:
    """Requête transmise : uniquement les mots-clés, nettoyés (pas de chiffres longs, pas d'adresse)."""
    clean = []
    for k in keywords:
        k = re.sub(r"\S+@\S+", "", k)  # pas d'adresse électronique
        k = re.sub(r"\d{5,}", "", k)  # pas de longs identifiants numériques
        k = re.sub(r"[^\w\s\-'’]", " ", k).strip()
        if 1 < len(k) <= 80:
            clean.append(k)
    return " ".join(dict.fromkeys(clean))[:300]


def parse_openalex(payload: dict) -> list[Work]:
    works = []
    for i, r in enumerate(payload.get("results", [])):
        doi = (r.get("doi") or "").replace("https://doi.org/", "") or None
        loc = r.get("primary_location") or {}
        src = (loc.get("source") or {}) if isinstance(loc, dict) else {}
        bib = r.get("biblio") or {}
        pages = ""
        if bib.get("first_page"):
            pages = bib["first_page"] + (f"-{bib['last_page']}" if bib.get("last_page") else "")
        works.append(Work(
            key=f"oa{i}",
            title=_strip_tags(r.get("title") or r.get("display_name") or "Sans titre"),
            authors=[a.get("author", {}).get("display_name", "") for a in r.get("authorships", [])
                     if a.get("author", {}).get("display_name")],
            year=r.get("publication_year"),
            venue=src.get("display_name") or "",
            doi=doi,
            abstract=reconstruct_abstract(r.get("abstract_inverted_index")),
            cited_by=int(r.get("cited_by_count") or 0),
            is_oa=bool((r.get("open_access") or {}).get("is_oa")),
            volume=str(bib.get("volume") or ""), issue=str(bib.get("issue") or ""), pages=pages,
            kind=r.get("type") or "", source="OpenAlex", url=r.get("id") or ""))
    return works


def parse_crossref(payload: dict) -> list[Work]:
    works = []
    for i, r in enumerate(payload.get("message", {}).get("items", [])):
        year = None
        for k in ("published-print", "published-online", "issued"):
            parts = (r.get(k) or {}).get("date-parts") or []
            if parts and parts[0] and parts[0][0]:
                year = int(parts[0][0])
                break
        authors = []
        for a in r.get("author", []):
            if a.get("family"):
                authors.append(f"{a['family']}, {a.get('given', '')}".strip().rstrip(","))
        works.append(Work(
            key=f"cr{i}", title=_strip_tags((r.get("title") or ["Sans titre"])[0]), authors=authors, year=year,
            venue=(r.get("container-title") or [""])[0], doi=r.get("DOI"), abstract=_strip_tags(r.get("abstract", "")),
            cited_by=int(r.get("is-referenced-by-count") or 0), volume=str(r.get("volume") or ""),
            issue=str(r.get("issue") or ""), pages=str(r.get("page") or ""), kind=r.get("type") or "",
            source="Crossref", url=r.get("URL") or ""))
    return works


def search(keywords: list[str], limit: int = 50, year_from: int | None = None, api_key: str | None = None,
           mailto: str | None = None, timeout: float = 20.0, client: httpx.Client | None = None) -> tuple[list[Work], dict]:
    """Interroge OpenAlex puis Crossref en repli. Renvoie (travaux, journal de la requête)."""
    q = build_query(keywords)
    log = {"requete": q, "base": None, "date": None, "n_bruts": 0, "erreur": None}
    if not q:
        log["erreur"] = "Aucun mot-clé exploitable."
        return [], log
    own = client is None
    client = client or httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=False)
    try:
        params = {"search": q, "per-page": min(limit, 100), "sort": "relevance_score:desc",
                  "select": "id,doi,title,display_name,publication_year,authorships,primary_location,"
                            "cited_by_count,abstract_inverted_index,open_access,type,biblio"}
        filt = ["type:article|review|book-chapter|book|dissertation"]
        if year_from:
            filt.append(f"from_publication_date:{year_from}-01-01")
        params["filter"] = ",".join(filt)
        if api_key:
            params["api_key"] = api_key
        if mailto:
            params["mailto"] = mailto
        try:
            r = client.get(OPENALEX, params=params)
            r.raise_for_status()
            works = parse_openalex(r.json())
            log["base"] = "OpenAlex"
        except (httpx.HTTPError, ValueError) as exc:
            log["erreur"] = f"OpenAlex indisponible ({type(exc).__name__})"
            cp = {"query.bibliographic": q, "rows": min(limit, 100),
                  "select": "DOI,title,author,issued,published-print,published-online,container-title,abstract,"
                            "is-referenced-by-count,volume,issue,page,type,URL"}
            if year_from:
                cp["filter"] = f"from-pub-date:{year_from}"
            r = client.get(CROSSREF, params=cp)
            r.raise_for_status()
            works = parse_crossref(r.json())
            log["base"] = "Crossref"
    except (httpx.HTTPError, ValueError) as exc:
        log["erreur"] = f"Bases bibliographiques injoignables ({type(exc).__name__})"
        return [], log
    finally:
        if own:
            client.close()
    from datetime import date
    log["date"] = date.today().isoformat()
    log["n_bruts"] = len(works)
    return dedupe(works), log


def dedupe(works: list[Work]) -> list[Work]:
    seen_doi, seen_title, out = set(), set(), []
    for w in works:
        t = _norm_title(w.title)
        d = (w.doi or "").lower()
        if (d and d in seen_doi) or t in seen_title or len(t) < 8:
            continue
        seen_doi.add(d)
        seen_title.add(t)
        out.append(w)
    return out
