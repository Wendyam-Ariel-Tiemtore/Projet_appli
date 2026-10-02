import httpx

from analyste.literature import review, sources

OPENALEX = {
    "results": [
        {"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1007/s13524-014-0374-x",
         "title": "Fertility decline and child schooling in urban Burkina Faso", "publication_year": 2015,
         "authorships": [{"author": {"display_name": "Moussa Bougma"}},
                         {"author": {"display_name": "Thomas K. LeGrand"}},
                         {"author": {"display_name": "Jean-François Kobiané"}}],
         "primary_location": {"source": {"display_name": "Demography"}}, "cited_by_count": 120,
         "abstract_inverted_index": {"This": [0], "study": [1], "examines": [2], "schooling.": [3]},
         "open_access": {"is_oa": True}, "type": "article",
         "biblio": {"volume": "52", "issue": "1", "first_page": "281", "last_page": "313"}},
        {"id": "https://openalex.org/W2", "doi": None, "title": "Fertility decline and child schooling in urban "
                                                                "Burkina Faso", "publication_year": 2015,
         "authorships": [], "primary_location": None, "cited_by_count": 0, "abstract_inverted_index": None},
    ]
}


def test_reconstruction_resume_et_apa():
    w = sources.parse_openalex(OPENALEX)
    assert w[0].abstract == "This study examines schooling."
    assert w[0].citation() == "Bougma et al., 2015"
    apa = w[0].apa()
    assert apa.startswith("Bougma, M., LeGrand, T. K., et Kobiané, J.-F. (2015).")
    assert "*Demography*, *52*(1), 281-313." in apa and apa.endswith("https://doi.org/10.1007/s13524-014-0374-x")


def test_dedoublonnage():
    assert len(sources.dedupe(sources.parse_openalex(OPENALEX))) == 1


def test_requete_ne_contient_que_les_mots_cles():
    q = sources.build_query(["contraception moderne", "ariel@mail.com", "Burkina 2268834455", "multiniveau"])
    assert "@" not in q and "2268834455" not in q
    assert q == "contraception moderne Burkina multiniveau"


def test_recherche_avec_transport_simule():
    vus = []

    def handler(request: httpx.Request):
        vus.append(request)
        return httpx.Response(200, json=OPENALEX)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    works, log = sources.search(["contraception", "Burkina"], client=client)
    assert log["base"] == "OpenAlex" and len(works) == 1
    assert vus[0].url.host == "api.openalex.org"
    assert vus[0].url.params["search"] == "contraception Burkina"


def test_repli_crossref():
    def handler(request: httpx.Request):
        if request.url.host == "api.openalex.org":
            return httpx.Response(503)
        return httpx.Response(200, json={"message": {"items": [
            {"DOI": "10.1/x", "title": ["Un titre suffisamment long"], "author": [{"family": "Soura", "given": "Abdramane B."}],
             "issued": {"date-parts": [[2009]]}, "container-title": ["Population"], "is-referenced-by-count": 3}]}})

    works, log = sources.search(["mortalité"], client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert log["base"] == "Crossref" and works[0].citation() == "Soura, 2009"


def test_section_litterature_sans_resultat():
    sec = review.literature_section([], {"erreur": "réseau indisponible"}, "Sujet")
    assert sec.warnings and "À compléter" in sec.paragraphs[0]
