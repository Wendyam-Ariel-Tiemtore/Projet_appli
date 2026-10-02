#!/usr/bin/env sh
# Lancement sans Docker (Linux, macOS) : https://localhost:8443
set -eu
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
fi
[ -f donnees/certificats/certificat.pem ] || .venv/bin/python scripts/certificat_local.py
echo "Application disponible sur https://localhost:8443 (arrêt : Ctrl+C)"
exec .venv/bin/uvicorn --factory analyste.web.app:create_app --host 127.0.0.1 --port 8443 \
  --ssl-keyfile donnees/certificats/cle.pem --ssl-certfile donnees/certificats/certificat.pem \
  --no-server-header --workers 1
