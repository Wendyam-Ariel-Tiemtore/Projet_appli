"""Parcours complet de l'interface et contrôles de sécurité de bout en bout."""

import re
import time

import pytest
from fastapi.testclient import TestClient

from analyste.config import Settings
from analyste.web.app import create_app

PWD = "Tres-Solide-2026!"


def csrf(html):
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


@pytest.fixture()
def app(tmp_path):
    s = Settings(data_dir=tmp_path / "d", master_key_file=tmp_path / "d" / "secrets" / "cle", https=False,
                 allow_literature=False, allow_external_llm=False)
    return create_app(s)


def login(app, name, admin=False):
    c = TestClient(app, base_url="http://localhost")
    if admin:
        r = c.get("/installation")
        c.post("/installation", data={"csrf": csrf(r.text), "username": name, "password": PWD, "password2": PWD})
    else:
        r = c.get("/connexion")
        c.post("/connexion", data={"csrf": csrf(r.text), "username": name, "password": PWD})
    return c


def test_parcours_complet_et_isolation(app, demo_csv):
    c = login(app, "ariel", admin=True)
    r = c.get("/")
    assert r.status_code == 200 and "Mes analyses" in r.text
    for h in ("content-security-policy", "x-frame-options", "x-content-type-options", "referrer-policy"):
        assert h in r.headers
    assert r.headers["cache-control"].startswith("no-store")

    r = c.get("/projets/nouveau")
    r = c.post("/projets/nouveau", data={"csrf": csrf(r.text), "nom": "Test"},
               files={"fichier": ("e.csv", demo_csv.read_bytes(), "text/csv")}, follow_redirects=False)
    assert r.status_code == 303
    pid = r.headers["location"].split("/")[2]

    r = c.get(f"/projets/{pid}/variables")
    assert "identifiants personnels" in r.text
    form = {"csrf": csrf(r.text)}
    roles = {"contraception_moderne": "dependante", "instruction": "explicative", "milieu": "niveau2",
             "exposition_medias": "explicative", "grappe": "contexte", "age": "explicative"}
    for n in re.findall(r'name="role__([^"]+)"', r.text):
        form[f"role__{n}"] = roles.get(n, "ignorer")
    for n in ("nom", "prenom", "telephone"):
        form[f"priv__{n}"] = "supprimer"
    assert 'name="texte__instruction"' in r.text and 'name="red_unite"' in r.text
    form.update({"texte__instruction": "le niveau d'instruction de la femme", "red_unite": "femmes",
                 "red_evenement": "utiliser une méthode contraceptive moderne"})
    assert c.post(f"/projets/{pid}/variables", data=form, follow_redirects=False).status_code == 303
    r = c.get(f"/projets/{pid}/variables")
    assert "le niveau d&#39;instruction de la femme" in r.text and 'value="femmes"' in r.text

    r = c.get(f"/projets/{pid}/demande")
    assert 'name="style_sample"' in r.text
    r = c.post(f"/projets/{pid}/demande", data={"csrf": csrf(r.text), "doc_type": "article", "title": "Essai",
                                                 "llm": "aucun", "style_sample": "Nous constatons que...",
                                                 "pres_active": "on", "pres_genre": "communication",
                                                 "pres_theme": "nuit", "pres_contenus": ["bivarie", "multivarie"],
                                                 "analyses_presentes": "1", "analyses": ["bivarie", "multivarie"],
                                                 "alpha": "0.05", "correction": "holm",
                                                 "hyp_texte_0": "Le niveau d'instruction favorise l'utilisation",
                                                 "hyp_var_0": "", "hyp_sens_0": ""},
               follow_redirects=False)
    assert r.status_code == 303
    for _ in range(120):
        etat = c.get(f"/projets/{pid}/etat").json()
        if etat["statut"] != "en_cours":
            break
        time.sleep(1)
    assert etat["statut"] == "termine", etat
    r = c.get(f"/projets/{pid}")
    assert "Ce qu&#39;il faut retenir" in r.text or "Ce qu'il faut retenir" in r.text
    assert c.get("/lexique").status_code == 200 and "Rapport de cotes" in c.get("/lexique").text
    files = re.findall(rf"/projets/{pid}/fichiers/([a-z]+\.enc)", r.text)
    assert set(files) == {"docx.enc", "pptx.enc", "xlsx.enc", "zip.enc", "params.enc"}
    pp = c.get(f"/projets/{pid}/fichiers/pptx.enc")
    assert pp.status_code == 200 and pp.content[:2] == b"PK"
    assert "presentationml" in pp.headers["content-type"]
    d = c.get(f"/projets/{pid}/fichiers/docx.enc")
    assert d.status_code == 200 and d.content[:2] == b"PK"

    # Un second utilisateur ne voit rien du premier, même l'administrateur ne lit pas ses fichiers
    r = c.get("/admin")
    c.post("/admin/utilisateurs", data={"csrf": csrf(r.text), "username": "autre", "password": PWD})
    c2 = login(app, "autre")
    assert c2.get(f"/projets/{pid}").status_code == 404
    assert c2.get(f"/projets/{pid}/fichiers/docx.enc").status_code == 404
    assert c2.get("/admin").status_code == 404

    # CSRF et origine
    assert c.post(f"/projets/{pid}/supprimer", data={"csrf": "faux"}).status_code == 403
    r = c.get("/")
    assert c.post(f"/projets/{pid}/supprimer", data={"csrf": csrf(r.text)},
                  headers={"origin": "https://malveillant.example"}).status_code == 403
    assert c.post(f"/projets/{pid}/supprimer", data={"csrf": csrf(r.text)},
                  follow_redirects=False).status_code == 303
    assert c.get(f"/projets/{pid}").status_code == 404


def test_verrouillage_apres_echecs(app):
    login(app, "ariel", admin=True)
    c = TestClient(app, base_url="http://localhost")
    r = c.get("/connexion")
    t = csrf(r.text)
    for _ in range(5):
        c.post("/connexion", data={"csrf": t, "username": "ariel", "password": "mauvais"})
    r = c.post("/connexion", data={"csrf": t, "username": "ariel", "password": PWD})
    assert r.status_code == 401 and "verrouillé" in r.text


def test_pages_protegees_et_hote(app):
    c = TestClient(app, base_url="http://localhost")
    assert c.get("/", follow_redirects=False).status_code == 303
    assert c.get("/projets/nouveau", follow_redirects=False).status_code == 303
    assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404
    evil = TestClient(app, base_url="http://attaquant.example")
    assert evil.get("/sante").status_code == 400


def test_fichier_malveillant_refuse(app):
    c = login(app, "ariel", admin=True)
    r = c.get("/projets/nouveau")
    r = c.post("/projets/nouveau", data={"csrf": csrf(r.text), "nom": "x"},
               files={"fichier": ("x.xlsx", b"ceci n'est pas un classeur", "application/octet-stream")})
    assert r.status_code == 400 and "Excel valide" in r.text


def test_code_installation_exige(tmp_path):
    s = Settings(data_dir=tmp_path / "d", master_key_file=tmp_path / "d" / "k", https=False, setup_token="code-secret")
    c = TestClient(create_app(s), base_url="http://localhost")
    r = c.get("/installation")
    assert "Code d'installation" in r.text
    r = c.post("/installation", data={"csrf": csrf(r.text), "username": "admin1", "password": PWD, "password2": PWD,
                                      "jeton": "mauvais"})
    assert r.status_code == 400
    r = c.post("/installation", data={"csrf": csrf(r.text), "username": "admin1", "password": PWD, "password2": PWD,
                                      "jeton": "code-secret"}, follow_redirects=False)
    assert r.status_code == 303
