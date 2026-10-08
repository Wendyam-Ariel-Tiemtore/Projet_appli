#!/usr/bin/env bash
# Restauration d'une sauvegarde produite par sauvegarder.sh (remplace les données actuelles).
# Usage, dans le dossier de l'application :  ./deploy/restaurer.sh chemin/analyste-donnees-AAAA-MM-JJ_HHMM.tar.gz.gpg
set -euo pipefail
FICHIER="${1:?Indiquez le fichier de sauvegarde .tar.gz.gpg}"
VOLUME="$(docker volume ls -q | grep -E '(^|_)donnees$' | head -n 1)"
[ -n "$VOLUME" ] || { echo "Volume de données introuvable : lancez d'abord « docker compose up -d »."; exit 1; }
read -r -p "Les données actuelles seront remplacées. Taper RESTAURER pour confirmer : " OK
[ "$OK" = "RESTAURER" ] || { echo "Abandon."; exit 1; }
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
gpg -o "$TMP/donnees.tar.gz" -d "$FICHIER"
docker compose stop app
docker run --rm -v "$VOLUME":/donnees -v "$TMP":/sauvegarde:ro alpine:3.22 \
  sh -c 'rm -rf /donnees/* /donnees/.[!.]* 2>/dev/null; tar xzf /sauvegarde/donnees.tar.gz -C /donnees && chown -R 10001:10001 /donnees && chmod 700 /donnees'
docker compose start app
echo "Restauration terminée."
