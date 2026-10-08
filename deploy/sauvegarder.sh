#!/usr/bin/env bash
# Sauvegarde chiffrée des comptes et des projets (volume « donnees »).
# Usage, dans le dossier de l'application sur le serveur :  ./deploy/sauvegarder.sh [dossier_de_destination]
# La phrase de passe est demandée, ou lue dans le fichier indiqué par SAUVEGARDE_PHRASE_FICHIER (droits 600).
# Conservez la phrase de passe HORS du serveur (gestionnaire de mots de passe) : sans elle, la sauvegarde est
# illisible, et c'est voulu. Copiez ensuite les fichiers .gpg hors du serveur (voir le guide pas à pas).
set -euo pipefail
DEST="${1:-$HOME/sauvegardes}"
GARDER="${SAUVEGARDE_GARDER:-14}"
mkdir -p "$DEST" && chmod 700 "$DEST"
VOLUME="$(docker volume ls -q | grep -E '(^|_)donnees$' | head -n 1)"
[ -n "$VOLUME" ] || { echo "Volume de données introuvable."; exit 1; }
DATE="$(date +%Y-%m-%d_%H%M)"
ARCHIVE="$DEST/analyste-donnees-$DATE.tar.gz"

echo "Arrêt bref de l'application pour une copie cohérente..."
docker compose stop app
trap 'docker compose start app >/dev/null' EXIT
docker run --rm -v "$VOLUME":/donnees:ro -v "$DEST":/sauvegarde alpine:3.22 \
  tar czf "/sauvegarde/$(basename "$ARCHIVE")" -C /donnees .
docker compose start app >/dev/null
trap - EXIT

if [ -n "${SAUVEGARDE_PHRASE_FICHIER:-}" ]; then
  gpg --batch --yes --pinentry-mode loopback --passphrase-file "$SAUVEGARDE_PHRASE_FICHIER" \
      --symmetric --cipher-algo AES256 -o "$ARCHIVE.gpg" "$ARCHIVE"
else
  gpg --symmetric --cipher-algo AES256 -o "$ARCHIVE.gpg" "$ARCHIVE"
fi
shred -u "$ARCHIVE" 2>/dev/null || rm -f "$ARCHIVE"
chmod 600 "$ARCHIVE.gpg"
ls -1t "$DEST"/analyste-donnees-*.tar.gz.gpg | tail -n +"$((GARDER + 1))" | xargs -r rm -f
echo "Sauvegarde chiffrée : $ARCHIVE.gpg"
