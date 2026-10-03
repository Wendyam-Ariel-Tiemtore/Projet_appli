#!/usr/bin/env bash
# Fait confiance à l'autorité locale du proxy HTTPS (macOS, Linux). À lancer depuis le dossier du projet.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose cp proxy:/data/caddy/pki/authorities/local/root.crt ./autorite-locale.crt
case "$(uname -s)" in
  Darwin)
    sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ./autorite-locale.crt ;;
  Linux)
    sudo cp ./autorite-locale.crt /usr/local/share/ca-certificates/analyste-academique.crt
    sudo update-ca-certificates ;;
esac
echo "Autorité locale ajoutée. Redémarrez le navigateur, puis ouvrez https://localhost"
