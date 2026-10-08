# Image de l'application : multi-étapes, utilisateur non privilégié, aucun outil de compilation à l'exécution.
FROM python:3.13-slim AS construction
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /construction
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

FROM python:3.13-slim
LABEL org.opencontainers.image.title="Analyste académique" \
      org.opencontainers.image.source="https://github.com/Wendyam-Ariel-Tiemtore/Projet_appli" \
      org.opencontainers.image.licenses="LicenseRef-Proprietaire" \
      org.opencontainers.image.vendor="Wendyam Ariel Tiemtoré"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib HOME=/tmp TMPDIR=/tmp \
    ANALYSTE_DATA_DIR=/donnees \
    ANALYSTE_MASTER_KEY_FILE=/donnees/secrets/cle_maitresse \
    FORWARDED_ALLOW_IPS=127.0.0.1
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin analyste \
 && mkdir -p /donnees && chown 10001:10001 /donnees && chmod 700 /donnees
COPY --from=construction /install /usr/local
WORKDIR /app
COPY --chown=root:root analyste ./analyste
COPY --chown=root:root docs ./docs
COPY --chown=root:root LICENSE THIRD_PARTY_NOTICES.md ./
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/sante', timeout=4).status == 200 else 1)"
# Un seul processus web : la file des analyses et la limitation de débit sont en mémoire (chaque analyse
# s'exécute ensuite dans son propre processus borné). Seul le proxy (adresse fixée dans docker-compose.yml,
# variable FORWARDED_ALLOW_IPS) est cru lorsqu'il transmet l'adresse réelle du visiteur.
CMD ["uvicorn", "--factory", "analyste.web.app:create_app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--no-server-header", "--workers", "1", \
     "--timeout-keep-alive", "10", "--limit-concurrency", "200"]
