# Guide de déploiement

> Vous débutez avec Git, Docker ou les serveurs ? Suivez plutôt le [guide pas à pas](/guide) (fichier `docs/GUIDE-PAS-A-PAS.md`), qui détaille chaque commande, le durcissement automatique du serveur (`deploy/preparer_serveur.sh`) et les sauvegardes chiffrées (`deploy/sauvegarder.sh`).

## 1. Sur votre ordinateur (usage personnel)

Suivre la section « Installation » du [README](../README.md). Par défaut, l'application n'écoute que sur `127.0.0.1` : elle n'est pas joignable depuis le réseau.

## 2. Sur un serveur de laboratoire ou d'institution

### Prérequis

- Serveur Linux à jour (Ubuntu 24.04 LTS ou équivalent), 4 cœurs et 8 Go de mémoire au minimum (16 Go avec un modèle local).
- Docker Engine et le greffon Compose.
- Un nom de domaine pointant vers le serveur (par exemple `analyse.mon-labo.org`), ports 80 et 443 ouverts.
- Chiffrement du disque recommandé.

### Étapes

```bash
git clone https://github.com/Wendyam-Ariel-Tiemtore/Projet_appli.git /opt/analyste
cd /opt/analyste
cp .env.example .env
```

Dans `.env` :

```ini
SITE_ADDRESS=analyse.mon-labo.org
TLS_MODE=admin@mon-labo.org
BIND_ADDRESS=0.0.0.0
ANALYSTE_ALLOWED_HOSTS=["analyse.mon-labo.org","127.0.0.1"]
ANALYSTE_SETUP_TOKEN=<code secret, par exemple : python -c "import secrets; print(secrets.token_urlsafe(24))">
```

Puis :

```bash
docker compose up -d --build
```

Caddy obtient et renouvelle automatiquement le certificat Let's Encrypt. Connectez-vous sur `https://analyse.mon-labo.org` pour créer le compte administrateur : le code `ANALYSTE_SETUP_TOKEN` est demandé, ce qui empêche un visiteur de s'approprier l'installation avant vous.

### Pare-feu

```bash
sudo ufw default deny incoming
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### Comptes

Les inscriptions libres sont fermées par défaut. L'administrateur crée les comptes dans **Administration** et communique le mot de passe initial par un canal sûr.

## 3. Fonctionnement entièrement hors ligne

Pour des données particulièrement sensibles :

1. Dans `.env` : `ANALYSTE_ALLOW_LITERATURE=false` et `ANALYSTE_ALLOW_EXTERNAL_LLM=false`.
2. Dans `docker-compose.yml`, déclarer le réseau interne sans accès sortant :

```yaml
networks:
  reseau:
    internal: true
    ipam:
      config:
        - subnet: 172.30.57.0/24
```

Avec un réseau interne, Caddy ne peut plus obtenir de certificat Let's Encrypt : conserver `TLS_MODE=internal`. Les images Docker et le modèle Ollama doivent être téléchargés avant de couper l'accès.

## 4. Sauvegarde et restauration

Deux éléments sont indispensables, et doivent être conservés **séparément** :

| Élément | Emplacement | Rôle |
|---|---|---|
| Clé maîtresse | volume `donnees`, `secrets/cle_maitresse` | Déchiffre les clés des projets |
| Base et fichiers chiffrés | volume `donnees` | Comptes et projets |

```bash
# Sauvegarde (application arrêtée)
docker compose stop app
docker run --rm -v analyste-academique_donnees:/donnees -v "$PWD":/sauvegarde alpine \
  tar czf /sauvegarde/donnees-$(date +%F).tar.gz -C /donnees .
docker compose start app
```

Rappel : les projets sont purgés après la durée de conservation ; la sauvegarde sert surtout aux comptes.

## 5. Mises à jour

```bash
cd /opt/analyste
git pull
docker compose build --pull
docker compose up -d
```

## 6. Choix du modèle local

| Mémoire disponible | Modèle suggéré (`ANALYSTE_OLLAMA_MODEL`) |
|---|---|
| 8 Go | un modèle de 7 à 8 milliards de paramètres en version « instruct » |
| 16 Go | `qwen2.5:14b-instruct` (valeur par défaut) |
| 32 Go et plus | un modèle de 30 milliards de paramètres ou plus |

Tout modèle disponible dans Ollama peut être utilisé. Quel que soit le modèle, les textes sont soumis aux mêmes vérifications : un modèle plus petit verra simplement plus de paragraphes rejetés et remplacés par le texte produit par les règles.

## 7. Journal d'audit

Le journal (table `journal` de la base SQLite) enregistre connexions, échecs, dépôts, analyses, téléchargements et suppressions, sans aucun contenu de données :

```bash
docker compose exec app python -c "import sqlite3; c=sqlite3.connect('/donnees/analyste.db'); [print(r) for r in c.execute('select ts, action, user_id, project_id, detail from journal order by ts desc limit 50')]"
```
