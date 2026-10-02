"""Application web (FastAPI) : interface en français, sécurisée, entièrement locale."""

from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..config import Settings, ensure_secret_file, get_settings
from ..db import Database, Project, SessionRow, User
from ..jobs import ProjectStore
from ..literature.sources import build_query
from ..pipeline import AnalysisConfig
from ..security import crypto
from ..security.auth import COOKIE, USERNAME_RE, Auth, csrf_ok, password_problems
from ..security.web import OriginCheck, RateLimiter, SecurityHeaders, UploadError, validate_upload
from ..stats.audit import detect_identifiers
from ..stats.io import KINDS, DataReadError
from ..writing import presentation as presentation_opts
from ..writing.composer import DOC_TYPES, RequestSpec
from ..writing.style import avec_article

HERE = Path(__file__).parent
DOCS = HERE.parent.parent / "docs"
log = logging.getLogger("analyste")

ROLES = [("ignorer", "Ne pas utiliser"), ("dependante", "Dépendante"), ("explicative", "Explicative"),
         ("niveau2", "Explicative de niveau 2"), ("contexte", "Identifiant du contexte"), ("poids", "Pondération"),
         ("duree", "Durée (survie)"), ("evenement", "Événement (survie)")]
ANALYSES_LIBELLES = {
    "bivarie": ("Analyse bivariée", "Un test adapté à chaque couple de variables, avec taille d'effet."),
    "multivarie": ("Analyse multivariée", "Modèle choisi selon la variable dépendante : linéaire, logistique, "
                                          "multinomial, ordonné ou de comptage."),
    "multiniveau": ("Analyse multi-niveaux", "Si un identifiant de contexte a été déclaré (grappe, village, école)."),
    "factorielles": ("Analyses factorielles et typologie", "ACP, ACM et classification lorsque au moins trois "
                                                            "variables du même type sont disponibles."),
    "survie": ("Analyse de survie", "Si une durée et un événement ont été déclarés."),
}
PRIVACY = [("supprimer", "Supprimer avant l'analyse"), ("pseudonymiser", "Remplacer par un code"),
           ("conserver", "Conserver")]


class LoginRequired(Exception):
    pass


class Ctx:
    def __init__(self, user: User, sess: SessionRow, token: str):
        self.user, self.sess, self.token = user, sess, token


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    data_dir.chmod(0o700)
    master = ensure_secret_file(Path(settings.master_key_file))
    db = Database(f"sqlite:///{data_dir / 'analyste.db'}")
    try:
        (data_dir / "analyste.db").chmod(0o600)
    except OSError:
        pass
    auth = Auth(db, settings)
    store = ProjectStore(db, settings, master)
    limiter = RateLimiter()
    templates = Jinja2Templates(directory=str(HERE / "templates"))
    templates.env.globals.update(DOC_TYPES=DOC_TYPES, KINDS=KINDS, ROLES=ROLES, PRIVACY=PRIVACY,
                                 settings=settings, P=presentation_opts, ANALYSES_LIBELLES=ANALYSES_LIBELLES)

    app = FastAPI(title="Analyste académique", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SecurityHeaders, https=settings.https)
    app.add_middleware(OriginCheck)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts + ["testserver"])
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
    app.state.store, app.state.db, app.state.auth = store, db, auth

    # --- Purge périodique ------------------------------------------------
    def purge_loop():
        while True:
            try:
                n = store.purge_expired()
                auth.purge_sessions()
                if n:
                    log.info("%d projet(s) expiré(s) supprimé(s).", n)
            except Exception:  # noqa: BLE001
                log.exception("Erreur lors de la purge")
            time.sleep(3600)

    threading.Thread(target=purge_loop, daemon=True, name="purge").start()

    # --- Outils ----------------------------------------------------------
    def ip(request: Request) -> str:
        return request.client.host if request.client else "inconnu"

    def ctx(request: Request) -> Ctx:
        token = request.cookies.get(COOKIE)
        res = auth.resolve(token)
        if res is None:
            raise LoginRequired
        return Ctx(res[0], res[1], token)

    def maybe_ctx(request: Request) -> Ctx | None:
        try:
            return ctx(request)
        except LoginRequired:
            return None

    def render(request: Request, name: str, c: Ctx | None = None, status: int = 200, **kw) -> HTMLResponse:
        pre = request.cookies.get("aa_pre") or secrets.token_urlsafe(24)
        resp = templates.TemplateResponse(request, name, {"user": c.user if c else None,
                                                          "csrf": c.sess.csrf if c else pre, **kw},
                                          status_code=status)
        if not c and not request.cookies.get("aa_pre"):
            resp.set_cookie("aa_pre", pre, httponly=True, secure=settings.https, samesite="strict", max_age=3600)
        return resp

    def check_csrf(request: Request, c: Ctx | None, token: str | None) -> None:
        expected = c.sess.csrf if c else request.cookies.get("aa_pre", "")
        if not expected or not csrf_ok(expected, token):
            raise StarletteHTTPException(403, "Jeton de sécurité invalide ou expiré. Rechargez la page.")

    def set_session_cookie(resp: Response, token: str) -> None:
        resp.set_cookie(COOKIE, token, httponly=True, secure=settings.https, samesite="strict", path="/",
                        max_age=settings.session_max_hours * 3600)

    def redirect(url: str) -> RedirectResponse:
        return RedirectResponse(url, status_code=303)

    # --- Gestion des erreurs ----------------------------------------------
    @app.exception_handler(LoginRequired)
    async def _login(request: Request, exc: LoginRequired):
        if db.user_count() == 0:
            return redirect("/installation")
        return redirect("/connexion")

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        msg = exc.detail if isinstance(exc.detail, str) and exc.status_code in (400, 403, 413, 429) else \
            {404: "Page introuvable.", 405: "Méthode non autorisée."}.get(exc.status_code, "Erreur.")
        return render(request, "erreur.html", maybe_ctx(request), status=exc.status_code, message=msg,
                      code=exc.status_code)

    @app.exception_handler(Exception)
    async def _any(request: Request, exc: Exception):
        log.error("Erreur interne : %s", type(exc).__name__)
        return render(request, "erreur.html", None, status=500, code=500,
                      message="Erreur interne. Aucune donnée n'a été transmise à l'extérieur.")

    # --- Santé -----------------------------------------------------------
    @app.get("/sante")
    def sante():
        return JSONResponse({"etat": "ok"})

    # --- Installation et authentification -------------------------------
    @app.get("/installation", response_class=HTMLResponse)
    def installation(request: Request):
        if db.user_count() > 0:
            return redirect("/connexion")
        return render(request, "installation.html")

    @app.post("/installation")
    def installation_post(request: Request, csrf: str = Form(""), username: str = Form(""),
                          password: str = Form(""), password2: str = Form(""), jeton: str = Form("")):
        check_csrf(request, None, csrf)
        if db.user_count() > 0:
            return redirect("/connexion")
        if not limiter.allow(f"install:{ip(request)}", 10, 600):
            raise StarletteHTTPException(429, "Trop de tentatives. Patientez quelques minutes.")
        errors = _account_errors(username, password, password2)
        if settings.setup_token and not csrf_ok(settings.setup_token, jeton.strip()):
            errors.append("Code d'installation incorrect (voir la variable ANALYSTE_SETUP_TOKEN).")
        if errors:
            return render(request, "installation.html", status=400, errors=errors, username=username)
        u = auth.create_user(username, password, is_admin=True)
        db.audit("creation_administrateur", user_id=u.id)
        resp = redirect("/")
        set_session_cookie(resp, auth.open_session(u.id))
        return resp

    @app.get("/connexion", response_class=HTMLResponse)
    def connexion(request: Request):
        if db.user_count() == 0:
            return redirect("/installation")
        if maybe_ctx(request):
            return redirect("/")
        return render(request, "connexion.html")

    @app.post("/connexion")
    def connexion_post(request: Request, csrf: str = Form(""), username: str = Form(""), password: str = Form("")):
        check_csrf(request, None, csrf)
        if not limiter.allow(f"login:{ip(request)}", 10, 300):
            return render(request, "connexion.html", status=429,
                          errors=["Trop de tentatives depuis cette adresse. Patientez quelques minutes."])
        u, err = auth.authenticate(username.strip()[:64], password[:256])
        if u is None:
            db.audit("connexion_echec", detail=f"identifiant={username[:32]!r}")
            return render(request, "connexion.html", status=401, errors=[err], username=username)
        old = request.cookies.get(COOKIE)
        auth.close_session(old)  # rotation de session
        resp = redirect("/")
        set_session_cookie(resp, auth.open_session(u.id))
        db.audit("connexion", user_id=u.id)
        return resp

    @app.post("/deconnexion")
    def deconnexion(request: Request, csrf: str = Form("")):
        c = ctx(request)
        check_csrf(request, c, csrf)
        auth.close_session(c.token)
        resp = redirect("/connexion")
        resp.delete_cookie(COOKIE, path="/")
        return resp

    @app.get("/inscription", response_class=HTMLResponse)
    def inscription(request: Request):
        if not settings.registration_open:
            return render(request, "erreur.html", status=403, code=403,
                          message="Les inscriptions sont fermées. Demandez un compte à l'administrateur.")
        return render(request, "inscription.html")

    @app.post("/inscription")
    def inscription_post(request: Request, csrf: str = Form(""), username: str = Form(""),
                         password: str = Form(""), password2: str = Form("")):
        check_csrf(request, None, csrf)
        if not settings.registration_open:
            raise StarletteHTTPException(403, "Les inscriptions sont fermées.")
        if not limiter.allow(f"register:{ip(request)}", 5, 3600):
            raise StarletteHTTPException(429, "Trop de créations de compte depuis cette adresse.")
        errors = _account_errors(username, password, password2)
        with db.session() as s:
            if s.scalar(select(User).where(User.username == username)):
                errors.append("Cet identifiant n'est pas disponible.")
        if errors:
            return render(request, "inscription.html", status=400, errors=errors, username=username)
        u = auth.create_user(username, password)
        db.audit("inscription", user_id=u.id)
        resp = redirect("/")
        set_session_cookie(resp, auth.open_session(u.id))
        return resp

    # --- Tableau de bord ------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def accueil(request: Request):
        c = ctx(request)
        rows = [{"id": p.id, "nom": store.name(p), "fichier": store.filename(p), "statut": p.status,
                 "progression": p.progress, "maj": p.updated_at} for p in store.list(c.user)]
        return render(request, "tableau.html", c, projets=rows)

    # --- Nouveau projet ---------------------------------------------------
    @app.get("/projets/nouveau", response_class=HTMLResponse)
    def nouveau(request: Request):
        return render(request, "nouveau.html", ctx(request))

    @app.post("/projets/nouveau")
    async def nouveau_post(request: Request, csrf: str = Form(""), nom: str = Form(""),
                           fichier: UploadFile = File(...)):
        c = ctx(request)
        check_csrf(request, c, csrf)
        if not limiter.allow(f"upload:{c.user.id}", 30, 3600):
            raise StarletteHTTPException(429, "Trop de dépôts en une heure. Réessayez plus tard.")
        max_bytes = settings.max_upload_mb * 1024 * 1024
        raw = await fichier.read(max_bytes + 1)
        try:
            fname = validate_upload(fichier.filename or "donnees.csv", raw, max_bytes)
        except UploadError as exc:
            return render(request, "nouveau.html", c, status=400, errors=[str(exc)], nom=nom)
        pid = store.create(c.user.id, (nom.strip() or fname)[:120], fname, raw)
        del raw
        p = store.get(pid, c.user)
        try:
            ds = store.load_dataset(p)
        except DataReadError as exc:
            store.delete(pid)
            return render(request, "nouveau.html", c, status=400, errors=[str(exc)], nom=nom)
        except Exception:  # noqa: BLE001
            store.delete(pid)
            return render(request, "nouveau.html", c, status=400, nom=nom,
                          errors=["Le fichier n'a pas pu être lu. Vérifiez qu'il contient un tableau avec une ligne "
                                  "d'en-tête."])
        ids = detect_identifiers(ds)
        cfg = AnalysisConfig(privacy_actions={k: ("supprimer" if v == "direct" else "conserver")
                                              for k, v in ids.items()})
        store.update(pid, config_enc=store.enc(p, json.loads(json.dumps(cfg.__dict__))), status="importe")
        db.audit("depot_donnees", user_id=c.user.id, project_id=pid,
                 detail=f"{len(ds.df)} lignes, {len(ds.df.columns)} colonnes")
        return redirect(f"/projets/{pid}/variables")

    def project_or_404(request: Request, pid: str) -> tuple[Ctx, Project]:
        c = ctx(request)
        p = store.get(pid, c.user)
        if p is None:
            raise StarletteHTTPException(404)
        return c, p

    # --- Variables --------------------------------------------------------
    @app.get("/projets/{pid}/variables", response_class=HTMLResponse)
    def variables(request: Request, pid: str):
        c, p = project_or_404(request, pid)
        ds = store.load_dataset(p)
        cfg = AnalysisConfig.from_dict(store.dec(p, p.config_enc, {}))
        ids = detect_identifiers(ds)
        rows = []
        for name, info in ds.variables.items():
            # Par défaut, aucune variable n'est retenue : le choix découle du cadre conceptuel de l'auteur.
            role = _role_of(name, cfg) or "ignorer"
            rows.append({"name": name, "label": cfg.labels.get(name, info.label), "kind": cfg.kinds.get(name, info.kind),
                         "detected": info.kind, "reason": info.reason, "n_valid": info.n_valid,
                         "n_missing": info.n_missing, "n_unique": info.n_unique,
                         "categories": info.categories[:40], "role": role,
                         "reference": cfg.references.get(name, ""),
                         "bloc": _bloc_of(name, cfg), "echelle": _scale_of(name, cfg),
                         "identifier": ids.get(name), "privacy": cfg.privacy_actions.get(name, "conserver"),
                         "texte": cfg.textes.get(name, ""),
                         "prose": avec_article(cfg.labels.get(name, info.label))})
        return render(request, "variables.html", c, projet={"id": pid, "nom": store.name(p), "statut": p.status},
                      rows=rows, n=len(ds.df), cfg=cfg, etape=2)

    @app.post("/projets/{pid}/variables")
    async def variables_post(request: Request, pid: str):
        c, p = project_or_404(request, pid)
        form = await request.form()
        check_csrf(request, c, form.get("csrf"))
        ds = store.load_dataset(p)
        old = AnalysisConfig.from_dict(store.dec(p, p.config_enc, {}))
        cfg = AnalysisConfig(literature=old.literature, keywords=old.keywords, year_from=old.year_from, llm=old.llm,
                             consent_external=old.consent_external, factorial=old.factorial)
        for key in ("unite", "evenement", "indicateur"):
            val = " ".join(str(form.get(f"red_{key}", "")).split())[:200]
            if val:
                cfg.redaction[key] = val
        errors = []
        blocks: dict[int, list[str]] = {}
        scales: dict[str, list[str]] = {}
        for name, info in ds.variables.items():
            role = str(form.get(f"role__{name}", "ignorer"))
            kind = str(form.get(f"kind__{name}", info.kind))
            label = str(form.get(f"label__{name}", info.label))[:120]
            if kind in KINDS and kind != info.kind:
                cfg.kinds[name] = kind
            if label.strip() and label != name:
                cfg.labels[name] = label.strip()
            texte = " ".join(str(form.get(f"texte__{name}", "")).split())[:150]
            if texte:
                cfg.textes[name] = texte
            ref = str(form.get(f"ref__{name}", ""))
            if ref and ref in info.categories:
                cfg.references[name] = ref
            priv = str(form.get(f"priv__{name}", ""))
            if priv in dict(PRIVACY):
                cfg.privacy_actions[name] = priv
            if role == "dependante":
                if cfg.outcome:
                    errors.append("Une seule variable dépendante peut être choisie.")
                cfg.outcome = name
            elif role in ("explicative", "niveau2"):
                cfg.explanatory.append(name)
                if role == "niveau2":
                    cfg.level2 = (cfg.level2 or []) + [name]
                b = str(form.get(f"bloc__{name}", ""))
                if b.isdigit() and 1 <= int(b) <= 5:
                    blocks.setdefault(int(b), []).append(name)
            elif role == "contexte":
                if cfg.cluster:
                    errors.append("Un seul identifiant de contexte peut être choisi (modèle à deux niveaux).")
                cfg.cluster = name
            elif role == "poids":
                cfg.weight = name
            elif role == "duree":
                cfg.time_var = name
            elif role == "evenement":
                cfg.event_var = name
            sc = str(form.get(f"echelle__{name}", "")).strip()[:60]
            if sc:
                scales.setdefault(sc, []).append(name)
            if cfg.privacy_actions.get(name) == "supprimer" and role != "ignorer":
                errors.append(f"La variable « {name} » est marquée pour suppression : choisissez « Ne pas utiliser » "
                              "ou changez l'action de confidentialité.")
        cfg.blocks = [blocks[k] for k in sorted(blocks)] if blocks else None
        cfg.scales = {k: v for k, v in scales.items() if len(v) >= 2}
        cfg.event_level = str(form.get("event_level", "")).strip()[:80] or None
        rs = str(form.get("random_slope", "")).strip()
        cfg.random_slope = rs if rs in cfg.explanatory else None
        sg = str(form.get("survival_group", "")).strip()
        cfg.survival_group = sg if sg in ds.variables else None
        if bool(cfg.time_var) != bool(cfg.event_var):
            errors.append("L'analyse de survie exige à la fois une variable de durée et une variable d'événement.")
        if cfg.weight and ds.variables[cfg.weight].kind not in ("continue", "comptage"):
            errors.append("La variable de pondération doit être numérique.")
        if not cfg.outcome and not cfg.explanatory:
            errors.append("Choisissez au moins une variable à analyser.")
        store.update(pid, config_enc=store.enc(p, json.loads(json.dumps(cfg.__dict__))))
        if errors:
            return render(request, "erreur.html", c, status=400, code=400, message=" ".join(dict.fromkeys(errors)),
                          retour=f"/projets/{pid}/variables")
        store.update(pid, status="configure" if p.status in ("importe", "configure") else p.status)
        return redirect(f"/projets/{pid}/demande")

    # --- Demande ----------------------------------------------------------
    @app.get("/projets/{pid}/demande", response_class=HTMLResponse)
    def demande(request: Request, pid: str):
        c, p = project_or_404(request, pid)
        spec = store.dec(p, p.spec_enc, None) or RequestSpec(title=store.name(p)).__dict__
        cfg = AnalysisConfig.from_dict(store.dec(p, p.config_enc, {}))
        has_key = bool(c.user.api_key_enc) or bool(settings.anthropic_api_key)
        pres = presentation_opts.PresentationSpec.from_dict(spec.get("presentation"))
        return render(request, "demande.html", c, projet={"id": pid, "nom": store.name(p), "statut": p.status},
                      spec=spec, cfg=cfg, pres=pres, has_key=has_key, etape=3)

    @app.post("/projets/{pid}/demande")
    async def demande_post(request: Request, pid: str):
        c, p = project_or_404(request, pid)
        form = await request.form()
        check_csrf(request, c, form.get("csrf"))
        if not limiter.allow(f"run:{c.user.id}", 30, 3600):
            raise StarletteHTTPException(429, "Trop d'analyses lancées en une heure.")

        def lines(key):
            return [x.strip()[:400] for x in str(form.get(key, "")).splitlines() if x.strip()][:12]

        dt = str(form.get("doc_type", "rapport_etude"))
        spec = RequestSpec(
            doc_type=dt if dt in DOC_TYPES else "rapport_etude",
            title=str(form.get("title", "")).strip()[:300] or store.name(p),
            author=str(form.get("author", "")).strip()[:200], institution=str(form.get("institution", "")).strip()[:200],
            supervisor=str(form.get("supervisor", "")).strip()[:200], date_text=str(form.get("date_text", "")).strip()[:60],
            context=str(form.get("context", "")).strip()[:6000],
            data_description=str(form.get("data_description", "")).strip()[:4000],
            problematique=str(form.get("problematique", "")).strip()[:1500],
            objectives=lines("objectives"), hypotheses=lines("hypotheses"),
            keywords=[k.strip()[:80] for k in str(form.get("keywords", "")).split(",") if k.strip()][:10],
            english_abstract=form.get("english_abstract") == "on",
            style_sample=str(form.get("style_sample", "")).strip()[:2500],
            presentation=_presentation_depuis(form, lines))
        cfg = AnalysisConfig.from_dict(store.dec(p, p.config_enc, {}))
        cfg.literature = form.get("literature") == "on" and settings.allow_literature
        cfg.keywords = spec.keywords
        yf = str(form.get("year_from", "")).strip()
        cfg.year_from = int(yf) if yf.isdigit() and 1900 < int(yf) < 2100 else None
        from ..pipeline import ANALYSES
        if form.get("analyses_presentes") == "1":  # cases décochées : absentes du formulaire
            cfg.analyses = [a for a in form.getlist("analyses") if a in ANALYSES]
            cfg.factorial = "factorielles" in cfg.analyses
        alpha = str(form.get("alpha", "0.05"))
        cfg.alpha = float(alpha) if alpha in ("0.01", "0.05", "0.10") else 0.05
        corr = str(form.get("correction", "fdr_bh"))
        cfg.correction = corr if corr in ("fdr_bh", "holm", "aucune") else "fdr_bh"
        cfg.non_parametrique = form.get("approche") == "non_parametrique"
        llm = str(form.get("llm", "aucun"))
        cfg.llm = llm if llm in ("aucun", "local", "claude") else "aucun"
        cfg.consent_external = form.get("consent_external") == "on"
        errors = []
        if cfg.llm == "claude":
            if not settings.allow_external_llm:
                errors.append("L'administrateur a désactivé les services de rédaction externes.")
            elif not cfg.consent_external:
                errors.append("Pour utiliser Claude, cochez la case de consentement à l'envoi des résultats agrégés.")
            elif not (c.user.api_key_enc or settings.anthropic_api_key):
                errors.append("Aucune clé d'API Claude n'est configurée (voir Paramètres).")
        if cfg.literature and not cfg.keywords:
            errors.append("La revue de littérature nécessite au moins un mot-clé.")
        store.update(pid, spec_enc=store.enc(p, spec.__dict__), config_enc=store.enc(p, json.loads(json.dumps(
            cfg.__dict__))))
        if errors:
            return render(request, "erreur.html", c, status=400, code=400, message=" ".join(errors),
                          retour=f"/projets/{pid}/demande")
        user_id = c.user.id

        def provider_factory(cfg_: AnalysisConfig):
            from ..writing.llm import AnthropicProvider, NoProvider, OllamaProvider
            if cfg_.llm == "local":
                prov = OllamaProvider(settings.ollama_url, settings.ollama_model)
                return prov if prov.available() else NoProvider()
            if cfg_.llm == "claude" and cfg_.consent_external and settings.allow_external_llm:
                key = settings.anthropic_api_key
                with db.session() as s:
                    u = s.get(User, user_id)
                    if u and u.api_key_enc:
                        key = crypto.decrypt(master, u.api_key_enc, f"api:{u.id}".encode()).decode()
                return AnthropicProvider(key, settings.anthropic_model) if key else NoProvider()
            return NoProvider()

        store.submit(pid, user_id, provider_factory)
        db.audit("analyse_lancee", user_id=user_id, project_id=pid,
                 detail=f"type={spec.doc_type}, redaction={cfg.llm}, litterature={cfg.literature}")
        return redirect(f"/projets/{pid}")

    # --- Projet -------------------------------------------------------------
    @app.get("/projets/{pid}", response_class=HTMLResponse)
    def projet(request: Request, pid: str):
        c, p = project_or_404(request, pid)
        res = store.results(p) if p.status == "termine" else {"fichiers": [], "journal": []}
        cfg = AnalysisConfig.from_dict(store.dec(p, p.config_enc, {}))
        return render(request, "projet.html", c, projet={"id": pid, "nom": store.name(p), "statut": p.status,
                                                          "progression": p.progress, "message": p.message,
                                                          "fichier": store.filename(p), "maj": p.updated_at},
                      fichiers=res["fichiers"], journal=res["journal"], cfg=cfg, etape=4,
                      requete=build_query(cfg.keywords) if cfg.literature else "")

    @app.get("/projets/{pid}/etat")
    def etat(request: Request, pid: str):
        _, p = project_or_404(request, pid)
        return JSONResponse({"statut": p.status, "progression": p.progress, "message": p.message})

    @app.get("/projets/{pid}/fichiers/{stor}")
    def fichier(request: Request, pid: str, stor: str):
        c, p = project_or_404(request, pid)
        for f in store.results(p)["fichiers"]:
            if f["stockage"] == stor:
                data = store.read_result(p, stor)
                db.audit("telechargement", user_id=c.user.id, project_id=pid, detail=f["type"])
                media = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                         "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                         "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         "zip": "application/zip", "params": "application/json"}[f["type"]]
                return Response(data, media_type=media, headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{quote(f['nom'])}"})
        raise StarletteHTTPException(404)

    @app.post("/projets/{pid}/supprimer")
    def supprimer(request: Request, pid: str, csrf: str = Form("")):
        c, p = project_or_404(request, pid)
        check_csrf(request, c, csrf)
        if p.status == "en_cours":
            raise StarletteHTTPException(400, "Attendez la fin de l'analyse avant de supprimer le projet.")
        store.delete(pid)
        db.audit("suppression_projet", user_id=c.user.id, project_id=pid)
        return redirect("/")

    # --- Paramètres du compte ----------------------------------------------
    @app.get("/parametres", response_class=HTMLResponse)
    def parametres(request: Request):
        c = ctx(request)
        return render(request, "parametres.html", c, has_key=bool(c.user.api_key_enc))

    @app.post("/parametres/mot-de-passe")
    def mdp(request: Request, csrf: str = Form(""), old: str = Form(""), new: str = Form(""), new2: str = Form("")):
        c = ctx(request)
        check_csrf(request, c, csrf)
        if new != new2:
            return render(request, "parametres.html", c, status=400, has_key=bool(c.user.api_key_enc),
                          errors=["Les deux nouveaux mots de passe ne correspondent pas."])
        err = auth.change_password(c.user.id, old, new)
        if err:
            return render(request, "parametres.html", c, status=400, has_key=bool(c.user.api_key_enc), errors=[err])
        db.audit("changement_mot_de_passe", user_id=c.user.id)
        resp = redirect("/connexion")
        resp.delete_cookie(COOKIE, path="/")
        return resp

    @app.post("/parametres/cle-api")
    def cle_api(request: Request, csrf: str = Form(""), cle: str = Form(""), action: str = Form("enregistrer")):
        c = ctx(request)
        check_csrf(request, c, csrf)
        with db.session() as s:
            u = s.get(User, c.user.id)
            if action == "supprimer":
                u.api_key_enc = None
            else:
                cle = cle.strip()
                if not cle.startswith("sk-ant-") or len(cle) > 300:
                    return render(request, "parametres.html", c, status=400, has_key=bool(u.api_key_enc),
                                  errors=["Clé d'API non reconnue (elle commence par « sk-ant- »)."])
                u.api_key_enc = crypto.encrypt(master, cle.encode(), f"api:{u.id}".encode())
            s.commit()
        db.audit("cle_api_" + ("supprimee" if action == "supprimer" else "enregistree"), user_id=c.user.id)
        return redirect("/parametres")

    @app.post("/parametres/supprimer-compte")
    def supprimer_compte(request: Request, csrf: str = Form(""), password: str = Form("")):
        c = ctx(request)
        check_csrf(request, c, csrf)
        u, err = auth.authenticate(c.user.username, password)
        if u is None:
            return render(request, "parametres.html", c, status=400, has_key=bool(c.user.api_key_enc),
                          errors=["Mot de passe incorrect : le compte n'a pas été supprimé."])
        if c.user.is_admin:
            with db.session() as s:
                admins = s.scalars(select(User).where(User.is_admin.is_(True))).all()
            if len(admins) <= 1:
                return render(request, "parametres.html", c, status=400, has_key=bool(c.user.api_key_enc),
                              errors=["Le dernier compte administrateur ne peut pas être supprimé."])
        for p in store.list(c.user):
            store.delete(p.id)
        with db.session() as s:
            s.execute(delete(SessionRow).where(SessionRow.user_id == c.user.id))
            s.delete(s.get(User, c.user.id))
            s.commit()
        db.audit("suppression_compte", user_id=c.user.id)
        resp = redirect("/connexion")
        resp.delete_cookie(COOKIE, path="/")
        return resp

    # --- Administration ----------------------------------------------------
    @app.get("/admin", response_class=HTMLResponse)
    def admin(request: Request):
        c = ctx(request)
        if not c.user.is_admin:
            raise StarletteHTTPException(404)
        with db.session() as s:
            users = s.scalars(select(User).order_by(User.created_at)).all()
            counts = {u.id: len(s.scalars(select(Project.id).where(Project.owner_id == u.id)).all()) for u in users}
        return render(request, "admin.html", c, users=users, counts=counts)

    @app.post("/admin/utilisateurs")
    def admin_create(request: Request, csrf: str = Form(""), username: str = Form(""), password: str = Form(""),
                     is_admin: str = Form("")):
        c = ctx(request)
        check_csrf(request, c, csrf)
        if not c.user.is_admin:
            raise StarletteHTTPException(404)
        errors = _account_errors(username, password, password)
        with db.session() as s:
            if s.scalar(select(User).where(User.username == username)):
                errors.append("Cet identifiant existe déjà.")
        if errors:
            return render(request, "erreur.html", c, status=400, code=400, message=" ".join(errors), retour="/admin")
        u = auth.create_user(username, password, is_admin=is_admin == "on")
        db.audit("creation_compte", user_id=c.user.id, detail=f"nouvel utilisateur #{u.id}")
        return redirect("/admin")

    @app.post("/admin/utilisateurs/{uid}/supprimer")
    def admin_delete(request: Request, uid: int, csrf: str = Form("")):
        c = ctx(request)
        check_csrf(request, c, csrf)
        if not c.user.is_admin or uid == c.user.id:
            raise StarletteHTTPException(404)
        with db.session() as s:
            u = s.get(User, uid)
            if u is None:
                raise StarletteHTTPException(404)
            for p in s.scalars(select(Project).where(Project.owner_id == uid)).all():
                store.delete(p.id)
            s.execute(delete(SessionRow).where(SessionRow.user_id == uid))
            s.delete(u)
            s.commit()
        db.audit("suppression_compte_admin", user_id=c.user.id, detail=f"utilisateur #{uid}")
        return redirect("/admin")

    # --- Pages d'aide --------------------------------------------------------
    pages = {"aide": ("FAQ.md", "Aide et questions fréquentes"),
             "confidentialite": ("CONFIDENTIALITE.md", "Confidentialité"),
             "securite": ("SECURITE.md", "Sécurité"), "methodologie": ("METHODOLOGIE.md", "Guide méthodologique")}

    @app.get("/{page}", response_class=HTMLResponse)
    def doc_page(request: Request, page: str):
        if page not in pages:
            raise StarletteHTTPException(404)
        import markdown
        fname, title = pages[page]
        path = DOCS / fname
        html = markdown.markdown(path.read_text(encoding="utf-8"), extensions=["tables", "toc", "fenced_code"]) \
            if path.exists() else "<p>Document indisponible.</p>"
        return render(request, "doc.html", maybe_ctx(request), titre=title, contenu=html)

    return app


def _account_errors(username: str, password: str, password2: str) -> list[str]:
    errs = []
    if not USERNAME_RE.match(username or ""):
        errs.append("L'identifiant doit compter 3 à 32 caractères : lettres, chiffres, point, tiret ou soulignement.")
    if password != password2:
        errs.append("Les deux mots de passe ne correspondent pas.")
    probs = password_problems(password, username)
    if probs:
        errs.append("Le mot de passe doit comporter " + ", ".join(probs) + ".")
    return errs


def _presentation_depuis(form, lines) -> dict:
    """Options de la présentation saisies dans la page Demande, validées par PresentationSpec."""
    d = {"active": form.get("pres_active") == "on", "notes": form.get("pres_notes") == "on",
         "annexes": form.get("pres_annexes") == "on",
         "contenus": [str(x) for x in form.getlist("pres_contenus")],
         "recommandations": lines("pres_recommandations"),
         "contact": str(form.get("pres_contact", "")).strip()[:120]}
    for k in ("genre", "duree", "deroule", "niveau", "visuels", "theme", "format"):
        v = str(form.get(f"pres_{k}", "")).strip()[:40]
        if v:
            d[k] = v
    return presentation_opts.PresentationSpec.from_dict(d).__dict__


def _role_of(name: str, cfg: AnalysisConfig) -> str | None:
    if name == cfg.outcome:
        return "dependante"
    if cfg.level2 and name in cfg.level2:
        return "niveau2"
    if name in cfg.explanatory:
        return "explicative"
    return {cfg.cluster: "contexte", cfg.weight: "poids", cfg.time_var: "duree", cfg.event_var: "evenement"}.get(name)


def _bloc_of(name: str, cfg: AnalysisConfig) -> str:
    for i, b in enumerate(cfg.blocks or [], start=1):
        if name in b:
            return str(i)
    return ""


def _scale_of(name: str, cfg: AnalysisConfig) -> str:
    for k, v in cfg.scales.items():
        if name in v:
            return k
    return ""


app = None


def get_app() -> FastAPI:
    global app
    if app is None:
        app = create_app()
    return app
