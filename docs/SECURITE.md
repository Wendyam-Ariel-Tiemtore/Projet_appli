# Sécurité

Ce document décrit les mesures de sécurité de l'application et les bonnes pratiques de déploiement. Pour signaler une vulnérabilité, voir [SECURITY.md](https://github.com/Wendyam-Ariel-Tiemtore/Projet_appli/blob/main/SECURITY.md).

## Modèle de menace

L'application traite des données de recherche potentiellement sensibles (enquêtes de santé, données nominatives). Elle vise à protéger contre :

- l'interception du trafic sur le réseau local ou Internet ;
- l'accès d'un utilisateur aux projets d'un autre utilisateur ;
- la prise de contrôle d'un compte (devinette de mot de passe, vol de session, falsification de requête) ;
- l'exploitation d'un fichier déposé malveillant ;
- la lecture des données par une personne ayant accès au disque (sauvegarde égarée, ordinateur volé) ;
- la fuite involontaire de données vers des services tiers.

Elle ne protège pas contre un administrateur système malveillant disposant d'un accès complet au serveur en fonctionnement, ni contre un poste utilisateur compromis.

## Mesures en place

### Transport

- **HTTPS obligatoire** : le proxy Caddy fourni chiffre le trafic (TLS 1.2 et 1.3 uniquement), avec une autorité de certification locale pour `localhost`, ou un certificat Let's Encrypt automatique pour un nom de domaine.
- **HSTS** (deux ans), redirection automatique de HTTP vers HTTPS.
- L'application elle-même n'écoute que sur le réseau interne Docker ; seul le proxy est exposé.

### Authentification et sessions

- Mots de passe hachés avec **Argon2id** (64 Mio, 3 passes), politique de 12 caractères minimum avec trois types de caractères et refus des mots de passe courants.
- **Verrouillage temporaire** du compte après 5 échecs (15 minutes), limitation de débit par adresse IP sur la connexion et la création de compte, réponse en temps constant pour ne pas révéler l'existence d'un identifiant.
- Sessions côté serveur : seul un jeton aléatoire de 256 bits est placé dans un cookie `HttpOnly`, `Secure`, `SameSite=Strict` ; la base ne conserve que son empreinte SHA-256. Expiration après 30 minutes d'inactivité et 8 heures au maximum ; rotation à la connexion ; fermeture de toutes les sessions au changement de mot de passe.
- Le premier compte créé est administrateur ; les inscriptions libres sont fermées par défaut.

### Requêtes

- **Jeton CSRF** sur tous les formulaires, comparé en temps constant, et vérification de l'en-tête `Origin` sur toutes les requêtes modifiantes.
- **Politique de sécurité du contenu (CSP)** stricte : scripts, styles et images uniquement depuis l'application elle-même, aucun script en ligne, aucun cadre (`frame-ancestors 'none'`).
- En-têtes `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy` ; pages non mises en cache.
- Hôtes autorisés limités (`TrustedHostMiddleware`) ; documentation automatique de l'API désactivée.
- Échappement automatique de toutes les variables dans les gabarits HTML.

### Fichiers déposés

- Liste blanche d'extensions, **vérification de la signature réelle** du contenu (un fichier renommé est refusé), taille maximale configurable.
- Classeurs Excel : refus des macros, protection contre les bombes de décompression, analyse XML durcie (`defusedxml`).
- Aucun format sérialisé exécutable (pickle, `.RData`) n'est accepté ; aucun nom de fichier fourni par l'utilisateur n'est utilisé sur le disque.
- Les cellules exportées vers Excel sont neutralisées contre l'injection de formules.

### Données au repos

- **AES-256-GCM** : une clé aléatoire par projet, elle-même chiffrée par une clé maîtresse stockée hors de la base (fichier en `0600`).
- Les fichiers de travail sont créés dans un répertoire temporaire en mémoire (`tmpfs`) et effacés à la fin de chaque analyse.
- SQLite configuré avec `secure_delete` ; suppression d'un projet par **effacement cryptographique** (destruction de la clé).
- Purge automatique des projets inactifs.

### Conteneur

- Image minimale, exécution sous un **utilisateur non privilégié**, système de fichiers racine en **lecture seule**, toutes les capacités Linux retirées (`cap_drop: ALL`), `no-new-privileges`, limites de mémoire et de processus.
- Dépendances épinglées ; audit automatique (`pip-audit`), analyse statique (`bandit`, CodeQL) et mises à jour (Dependabot) dans l'intégration continue GitHub.

### Journalisation

- Journal d'audit des actions (connexion, échec de connexion, dépôt, analyse, téléchargement, suppression) **sans aucun contenu de données**.
- Les messages d'erreur affichés ne révèlent ni trace d'exécution ni chemin interne.

## Bonnes pratiques de déploiement

1. **Sauvegardez la clé maîtresse** (`donnees/secrets/cle_maitresse`) séparément des données : sans elle, aucun projet ne peut être déchiffré ; avec elle et une copie des données, tout peut l'être.
2. Gardez le système et Docker à jour ; reconstruisez l'image régulièrement (`docker compose build --pull`).
3. Sur un serveur accessible depuis Internet : utilisez un nom de domaine avec certificat Let's Encrypt, un pare-feu n'ouvrant que les ports 80 et 443, et le chiffrement du disque.
4. Pour un usage strictement hors ligne : `ANALYSTE_ALLOW_LITERATURE=false` et `ANALYSTE_ALLOW_EXTERNAL_LLM=false`, et un réseau Docker sans accès sortant.
5. Ne désactivez jamais `ANALYSTE_HTTPS` en dehors d'un test local sans proxy.
6. Changez les mots de passe initiaux communiqués aux utilisateurs.
