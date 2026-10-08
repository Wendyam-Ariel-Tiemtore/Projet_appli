# Guide pas à pas : installer, publier et distribuer Analyste académique

Ce guide part de zéro. Il suppose seulement que Git, Docker Desktop et VS Code sont installés sur un ordinateur Windows (les différences pour macOS sont signalées). Chaque étape indique **où** taper la commande, **quoi** taper et **ce que vous devez voir**. Avancez dans l'ordre : chaque partie s'appuie sur la précédente.

| Partie | Objectif | Durée indicative |
|---|---|---|
| 1 | Comprendre les outils en cinq minutes | 5 min |
| 2 | Maîtriser VS Code, Git et GitHub au quotidien | 30 min |
| 3 | Maîtriser Docker au quotidien | 20 min |
| 4 | Protéger le code : dépôt privé et signature | 20 min |
| 5 | Mettre l'application en ligne sur un site très sécurisé | 2 à 3 h |
| 6 | En faire une application de téléphone | 30 min à 1 jour |
| 7 | En faire un logiciel d'ordinateur | 15 min |
| 8 | Publier une nouvelle version signée | 10 min |
| 9 | Liste de contrôle avant l'ouverture au public | 30 min |

---

## Partie 1 : les outils en cinq minutes

- **VS Code** est votre atelier : il affiche les fichiers du projet, permet de les modifier et contient un **terminal** (une fenêtre où l'on tape des commandes).
- **Git** est l'historique du projet : chaque « commit » est une photographie datée et commentée de tous les fichiers. On peut revenir en arrière à tout moment.
- **GitHub** est le coffre en ligne qui conserve cet historique (le « dépôt »). Il exécute aussi les tests automatiques à chaque envoi.
- **Docker** fabrique une « boîte » (le conteneur) qui contient l'application et tout ce dont elle a besoin. La même boîte fonctionne à l'identique sur votre ordinateur et sur un serveur.
- **Caddy** est le portier : il reçoit les visiteurs en HTTPS, gère le certificat et transmet les demandes à l'application.

> Règle d'or : on ne modifie jamais directement le serveur. On modifie le projet sur son ordinateur, on l'envoie sur GitHub, puis le serveur récupère la nouvelle version.

---

## Partie 2 : VS Code, Git et GitHub au quotidien

### 2.1 Ouvrir le projet dans VS Code

1. Ouvrez VS Code.
2. Menu **Fichier > Ouvrir le dossier...**, choisissez le dossier `Projet_appli`.
3. Si VS Code demande « Faites-vous confiance aux auteurs de ce dossier ? », répondez **Oui**.
4. Ouvrez le terminal : menu **Terminal > Nouveau terminal** (raccourci `Ctrl` + `ù` sur un clavier français). Une zone apparaît en bas, avec une invite du type `PS C:\Users\...\Projet_appli>`.

Toutes les commandes de ce guide marquées « terminal VS Code » se tapent là, puis on appuie sur `Entrée`.

### 2.2 Se présenter à Git (une seule fois par ordinateur)

Dans le terminal VS Code :

```powershell
git config --global user.name "Wendyam Ariel Tiemtoré"
git config --global user.email "votre-adresse@exemple.com"
git config --global init.defaultBranch main
git config --global pull.rebase false
```

Utilisez l'adresse associée à votre compte GitHub. Vérification : `git config --global --list` affiche ces valeurs.

### 2.3 Le cycle quotidien : récupérer, modifier, enregistrer, envoyer

**Avec la souris (recommandé pour commencer)** : cliquez sur l'icône **Contrôle de code source** dans la barre de gauche (trois ronds reliés).

1. **Récupérer** les dernières modifications : bouton `...` puis **Extraire (Pull)**.
2. **Modifier** vos fichiers et enregistrez-les (`Ctrl` + `S`). Les fichiers modifiés apparaissent dans la liste avec la lettre `M`.
3. **Préparer** : survolez « Modifications » et cliquez sur `+` (tout indexer).
4. **Enregistrer** : tapez un message clair dans la zone de texte (par exemple « Ajout des conditions générales de vente ») puis cliquez sur **Valider (Commit)**.
5. **Envoyer** : cliquez sur **Synchroniser les modifications** (ou `...` puis **Envoyer (Push)**).

**Les mêmes étapes en commandes** (terminal VS Code) :

```powershell
git pull                      # 1. récupérer
git status                    # voir ce qui a changé
git add -A                    # 3. tout préparer
git commit -m "Message clair" # 4. enregistrer
git push                      # 5. envoyer sur GitHub
```

Après un `git push`, ouvrez votre dépôt sur github.com, onglet **Actions** : une coche verte signifie que tous les tests sont passés. Une croix rouge signifie qu'un contrôle a échoué ; cliquez dessus pour lire l'erreur.

### 2.4 Revenir en arrière

- Annuler les modifications d'un fichier non encore validées : clic droit sur le fichier dans le panneau Git, **Ignorer les modifications**.
- Voir l'historique : `git log --oneline -15`.
- Défaire le dernier commit **déjà envoyé**, proprement : `git revert HEAD` puis `git push`. On n'efface jamais l'historique d'un dépôt partagé.

### 2.5 Ne jamais envoyer de secret

Le fichier `.env` (mots de passe, clés) est exclu de Git par le fichier `.gitignore`. Ne le retirez jamais de cette liste. Si un secret a été envoyé par erreur, considérez-le comme compromis : changez-le immédiatement (le supprimer de l'historique ne suffit pas).

---

## Partie 3 : Docker au quotidien

Docker Desktop doit être **démarré** (icône de baleine dans la barre des tâches, état « Engine running ») avant toute commande.

| Je veux... | Commande (terminal VS Code, dans le dossier du projet) |
|---|---|
| Démarrer l'application (et la reconstruire après une modification) | `docker compose up -d --build` |
| Voir si elle tourne | `docker compose ps` (colonne STATUS : `Up ... (healthy)`) |
| Lire ce qui se passe | `docker compose logs -f app` (sortir avec `Ctrl` + `C`) |
| L'arrêter | `docker compose down` |
| La redémarrer | `docker compose restart` |
| Faire de la place sur le disque | `docker system prune` (supprime les images inutilisées, jamais vos données) |

Les données (comptes, projets) sont dans un **volume** Docker nommé `analyste-academique_donnees`. `docker compose down` ne les efface pas. Seule la commande `docker compose down -v` les efface : ne l'utilisez jamais sans sauvegarde.

Dans Docker Desktop, la même chose se fait à la souris : onglet **Containers**, groupe `analyste-academique`, boutons lecture, arrêt et corbeille, et un clic sur un conteneur affiche ses journaux.

Ouvrez ensuite **https://localhost** (le `s` de `https` est indispensable). Pour supprimer l'avertissement de certificat sur votre poste, exécutez une fois `powershell -ExecutionPolicy Bypass -File scripts\faire_confiance.ps1`, puis fermez et rouvrez le navigateur.

---

## Partie 4 : protéger le code

Le logiciel est propriétaire (voir `LICENSE`). Deux mesures s'imposent avant de le commercialiser.

### 4.1 Rendre le dépôt privé

1. Sur github.com, ouvrez le dépôt `Projet_appli`.
2. Onglet **Settings** (Paramètres), tout en bas : zone **Danger Zone**.
3. **Change repository visibility > Change to private**, puis confirmez en tapant le nom du dépôt.

Conséquences : seules les personnes que vous invitez voient le code ; les tests automatiques continuent de fonctionner (2 000 minutes gratuites par mois, largement suffisantes) ; l'analyse CodeQL, réservée aux dépôts publics dans l'offre gratuite, est automatiquement mise en pause.

### 4.2 Signer vos commits (badge « Verified »)

La signature prouve que les modifications viennent bien de vous. Dans le terminal VS Code :

```powershell
ssh-keygen -t ed25519 -C "signature-git"        # Entrée trois fois (ou choisissez une phrase de passe)
git config --global gpg.format ssh
git config --global user.signingkey "$env:USERPROFILE\.ssh\id_ed25519.pub"
git config --global commit.gpgsign true
git config --global tag.gpgsign true
Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub"   # affiche la clé publique à copier
```

Sur macOS, remplacez les chemins par `~/.ssh/id_ed25519.pub` et `cat ~/.ssh/id_ed25519.pub`.

Sur github.com : photo de profil > **Settings > SSH and GPG keys > New SSH key**, champ **Key type : Signing Key**, collez la clé, enregistrez. Vos prochains commits porteront la mention **Verified**.

### 4.3 Ce qui signe déjà l'application

- Chaque page affiche « conçu par Wendyam Ariel Tiemtoré » et une page **À propos** avec version et droits.
- Chaque document Word et PowerPoint produit porte dans ses propriétés la mention « Produit avec Analyste académique », la version et vos droits.
- Chaque version publiée (partie 8) est signée cryptographiquement, avec une attestation de provenance et la liste complète de ses composants (SBOM).

---

## Partie 5 : mettre l'application en ligne sur un site très sécurisé

### 5.1 Ce qu'il vous faut

| Élément | Où | Coût indicatif |
|---|---|---|
| Un nom de domaine (par exemple `analyste-academique.com`) | Un bureau d'enregistrement : OVHcloud, Gandi, Infomaniak, Namecheap, Cloudflare | 10 à 20 € par an |
| Un serveur privé virtuel (VPS) Linux, **8 Go de mémoire**, 2 à 4 processeurs, 80 Go de disque, Ubuntu 24.04 LTS | Un hébergeur : Hetzner, OVHcloud, Scaleway, Infomaniak | 8 à 25 € par mois |
| Une adresse électronique professionnelle (pour Let's Encrypt et le contact) | Souvent incluse avec le domaine | 0 à 5 € par mois |

Choisissez un hébergeur situé dans l'Union européenne : vos utilisateurs bénéficient alors du RGPD, ce qui rassure les ONG et les institutions.

### 5.2 Créer votre clé de connexion au serveur (sur votre ordinateur)

Dans PowerShell (ou le terminal VS Code) :

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\serveur_analyste" -C "acces-serveur"
Get-Content "$env:USERPROFILE\.ssh\serveur_analyste.pub"
```

Choisissez une **phrase de passe** quand elle est demandée et notez-la dans votre gestionnaire de mots de passe. Copiez la ligne affichée (elle commence par `ssh-ed25519`) : c'est votre clé **publique**, que l'on peut donner sans risque. Le fichier sans `.pub` est votre clé **privée** : il ne quitte jamais votre ordinateur.

### 5.3 Louer le serveur

Dans l'espace client de l'hébergeur :

1. Créer un serveur : image **Ubuntu 24.04**, emplacement en Europe, offre à 8 Go de mémoire.
2. À la rubrique **SSH keys**, collez votre clé publique.
3. Activez, si elle est proposée, l'option de **sauvegardes automatiques** et le **pare-feu de l'hébergeur** (ouvrez les ports 22, 80 et 443).
4. Notez l'**adresse IPv4** du serveur (par exemple `203.0.113.25`).

### 5.4 Relier le domaine au serveur

Chez le bureau d'enregistrement, rubrique **Zone DNS** :

| Type | Nom | Valeur |
|---|---|---|
| A | `@` (le domaine nu) | l'adresse IPv4 du serveur |
| A | `www` | l'adresse IPv4 du serveur |
| AAAA (si l'hébergeur fournit une IPv6) | `@` | l'adresse IPv6 |
| CAA | `@` | `0 issue "letsencrypt.org"` |

L'enregistrement CAA interdit à toute autre autorité d'émettre un certificat pour votre domaine. La propagation prend de quelques minutes à quelques heures. Vérification : `nslookup analyste-academique.com` affiche l'adresse du serveur.

### 5.5 Première connexion et durcissement automatique

Sur votre ordinateur :

```powershell
scp -i "$env:USERPROFILE\.ssh\serveur_analyste" deploy\preparer_serveur.sh root@203.0.113.25:/root/
ssh -i "$env:USERPROFILE\.ssh\serveur_analyste" root@203.0.113.25
```

À la première connexion, répondez `yes` pour mémoriser l'empreinte du serveur. Vous êtes maintenant **sur le serveur** (l'invite devient `root@...:~#`). Lancez :

```bash
bash /root/preparer_serveur.sh analyste
```

Le script, en sept étapes affichées à l'écran : met le système à jour ; crée l'utilisateur `analyste` (il vous demande son mot de passe, utilisé seulement pour `sudo`) ; interdit la connexion en root et par mot de passe ; ferme tous les ports sauf SSH, HTTP et HTTPS ; installe fail2ban, qui bannit les adresses qui insistent ; active les mises à jour de sécurité automatiques ; installe Docker avec des journaux bornés.

**Avant de fermer la fenêtre**, ouvrez une seconde fenêtre PowerShell et vérifiez que vous pouvez vous reconnecter :

```powershell
ssh -i "$env:USERPROFILE\.ssh\serveur_analyste" analyste@203.0.113.25
```

Pour simplifier les connexions suivantes, créez sur votre ordinateur le fichier `C:\Users\<vous>\.ssh\config` :

```
Host analyste
    HostName 203.0.113.25
    User analyste
    IdentityFile ~/.ssh/serveur_analyste
```

Ensuite, `ssh analyste` suffit.

### 5.6 Récupérer le code sur le serveur (dépôt privé)

Sur le serveur (connecté en `analyste`) :

```bash
ssh-keygen -t ed25519 -f ~/.ssh/cle_deploiement -N "" -C "deploiement-serveur"
cat ~/.ssh/cle_deploiement.pub
```

Sur github.com, dans le dépôt : **Settings > Deploy keys > Add deploy key**, collez la clé, **ne cochez pas** « Allow write access ». Cette clé ne peut que lire ce dépôt-là. Puis, sur le serveur :

```bash
cat >> ~/.ssh/config <<'CONF'
Host github.com
    IdentityFile ~/.ssh/cle_deploiement
CONF
sudo mkdir -p /opt/analyste && sudo chown analyste:analyste /opt/analyste
git clone git@github.com:Wendyam-Ariel-Tiemtore/Projet_appli.git /opt/analyste
cd /opt/analyste
```

### 5.7 Configurer l'application

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # copiez le code affiché
nano .env
```

Dans l'éditeur `nano`, modifiez ces lignes (les flèches déplacent le curseur ; `Ctrl` + `O` puis `Entrée` enregistre ; `Ctrl` + `X` quitte) :

```ini
SITE_ADDRESS=analyste-academique.com, www.analyste-academique.com
TLS_MODE=contact@analyste-academique.com
BIND_ADDRESS=0.0.0.0
ANALYSTE_ALLOWED_HOSTS=["analyste-academique.com","www.analyste-academique.com","127.0.0.1"]
ANALYSTE_SETUP_TOKEN=<le code généré juste avant>
ANALYSTE_REGISTRATION_OPEN=false
```

Mettez `ANALYSTE_REGISTRATION_OPEN=true` seulement le jour où vous ouvrez les inscriptions au public. Puis protégez le fichier : `chmod 600 .env`.

### 5.8 Démarrer

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f proxy     # attendez « certificate obtained successfully », puis Ctrl + C
```

Ouvrez `https://analyste-academique.com` : la page de création du compte administrateur s'affiche ; saisissez le code d'installation. Personne d'autre ne peut créer ce premier compte.

### 5.9 Vérifier la sécurité de l'extérieur

| Test | Adresse | Résultat attendu |
|---|---|---|
| Certificat et chiffrement | ssllabs.com/ssltest | A ou A+ |
| En-têtes de sécurité | securityheaders.com | A ou A+ |
| Bilan général | developer.mozilla.org/fr/observatory | B+ ou mieux |
| Ports ouverts (depuis votre ordinateur) | `Test-NetConnection 203.0.113.25 -Port 8000` | Échec : seul le portier HTTPS est exposé |

### 5.10 Sauvegarder

Sur le serveur, dans `/opt/analyste` :

```bash
./deploy/sauvegarder.sh                 # demande une phrase de passe ; produit un fichier .gpg chiffré
```

Notez la phrase de passe dans votre gestionnaire de mots de passe, **pas** sur le serveur. Pour automatiser chaque nuit à 3 h :

```bash
umask 077 && nano ~/.phrase_sauvegarde          # tapez la phrase de passe, enregistrez
crontab -e                                      # choisissez nano, puis ajoutez la ligne suivante
0 3 * * * cd /opt/analyste && SAUVEGARDE_PHRASE_FICHIER=$HOME/.phrase_sauvegarde ./deploy/sauvegarder.sh >> $HOME/sauvegarde.log 2>&1
```

Une sauvegarde restée sur le serveur ne protège pas d'une panne du serveur. Une fois par semaine, rapatriez-la sur votre ordinateur (PowerShell) :

```powershell
scp "analyste:~/sauvegardes/*.gpg" "$env:USERPROFILE\Documents\Sauvegardes-analyste\"
```

Restauration (sur le serveur) : `./deploy/restaurer.sh ~/sauvegardes/analyste-donnees-AAAA-MM-JJ_HHMM.tar.gz.gpg`. Faites un essai de restauration une fois par trimestre : une sauvegarde jamais testée n'est pas une sauvegarde.

### 5.11 Mettre à jour

À chaque nouvelle version envoyée sur GitHub, sur le serveur :

```bash
cd /opt/analyste
./deploy/sauvegarder.sh
git pull
docker compose build --pull
docker compose up -d
docker compose ps
```

Le système d'exploitation se met à jour seul (mises à jour de sécurité). Redémarrez le serveur quand le message `*** System restart required ***` apparaît à la connexion : `sudo reboot` ; l'application redémarre d'elle-même.

### 5.12 Surveiller

Créez un compte gratuit sur un service de surveillance (UptimeRobot, Better Stack…) et faites surveiller `https://analyste-academique.com/sante` toutes les cinq minutes : vous recevez un courriel si le site ne répond plus.

---

## Partie 6 : une application de téléphone

### 6.1 L'application installable (déjà prête, gratuite)

L'application est une **application web progressive** : elle s'installe depuis le navigateur, avec son icône, en plein écran, sans passer par un magasin d'applications.

- **Android** (Chrome) : ouvrez le site, menu `⋮` > **Installer l'application** (ou **Ajouter à l'écran d'accueil**).
- **iPhone et iPad** (Safari) : ouvrez le site, bouton **Partager** > **Sur l'écran d'accueil**.

Les mises à jour sont automatiques : il suffit de mettre à jour le serveur. Aucune donnée n'est conservée sur le téléphone (seuls la feuille de style, le script et les icônes le sont).

### 6.2 Publier sur Google Play (facultatif)

1. Créez un compte développeur Google Play (paiement unique d'environ 25 dollars, vérification d'identité).
2. Sur **pwabuilder.com**, saisissez l'adresse de votre site, puis **Package for stores > Android**. Indiquez l'identifiant `com.analysteacademique.app` (par exemple) et téléchargez le paquet.
3. Le paquet contient un fichier `assetlinks.json`. Copiez son contenu **sur une seule ligne** dans le `.env` du serveur : `ANALYSTE_ANDROID_ASSETLINKS=[{...}]`, puis `docker compose up -d`. Vérifiez que `https://analyste-academique.com/.well-known/assetlinks.json` l'affiche.
4. Dans la console Google Play, créez l'application, envoyez le fichier `.aab`, remplissez la fiche (description, captures d'écran, politique de confidentialité : `https://analyste-academique.com/confidentialite`), puis soumettez pour examen.

Conservez précieusement la clé de signature fournie par PWABuilder : elle est indispensable pour publier les mises à jour.

### 6.3 L'App Store d'Apple

La publication exige un Mac, Xcode et l'abonnement Apple Developer (environ 99 dollars par an), et Apple refuse souvent les applications qui ne font qu'afficher un site. Pour iPhone, l'application installable de la section 6.1 est la voie recommandée.

---

## Partie 7 : un logiciel d'ordinateur

### 7.1 Depuis le site (le plus simple)

Dans Chrome ou Edge, sur Windows, macOS ou Linux : ouvrez le site, puis l'icône **Installer** à droite de la barre d'adresse (ou menu > **Installer Analyste académique**). L'application s'ouvre dans sa propre fenêtre, apparaît dans le menu Démarrer et peut être épinglée à la barre des tâches.

Pour le **Microsoft Store**, PWABuilder produit aussi un paquet Windows (MSIX) à soumettre depuis l'espace partenaire Microsoft.

### 7.2 Version hors ligne, sur le poste de l'utilisateur

Pour une ONG ou un chercheur qui veut que les données ne quittent jamais son ordinateur : installer Docker Desktop, récupérer l'application (archive de la version, partie 8), puis double-cliquer sur `scripts\lancer.ps1` (Windows) ou lancer `./scripts/lancer.sh` (macOS, Linux). C'est l'offre « licence institutionnelle » : vous fournissez l'archive signée et une aide à l'installation.

---

## Partie 8 : publier une nouvelle version signée

1. Mettez à jour le numéro de version dans `analyste/__init__.py` et `pyproject.toml` (par exemple `1.3.1`), et décrivez les changements en tête de `CHANGELOG.md` sous un titre `## 1.3.1 : JJ mois AAAA`.
2. Validez et envoyez (partie 2.3), attendez la coche verte dans **Actions**.
3. Créez l'étiquette signée et envoyez-la :

```powershell
git tag -s v1.3.1 -m "Version 1.3.1"
git push origin v1.3.1
```

Le flux **Publication signée d'une version** (onglet Actions) construit l'image Docker, la publie sur le registre de GitHub, la **signe** avec Sigstore, ajoute l'attestation de provenance et la nomenclature des composants, puis crée la page de version avec l'archive du code, ses empreintes SHA-256 et leur signature.

Toute personne peut alors vérifier qu'une image vient bien de vous (outil `cosign`) :

```bash
cosign verify ghcr.io/wendyam-ariel-tiemtore/analyste-academique:v1.3.1 \
  --certificate-identity-regexp '^https://github.com/Wendyam-Ariel-Tiemtore/Projet_appli/\.github/workflows/publication\.yml@refs/tags/v' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

---

## Partie 9 : liste de contrôle avant l'ouverture au public

- [ ] Dépôt GitHub privé (partie 4.1).
- [ ] Champs entre crochets complétés dans `docs/MENTIONS_LEGALES.md`, `docs/CGU.md` et `docs/CGV.md` (statut, adresse, immatriculation, hébergeur, prix, médiateur), relus si possible par un juriste.
- [ ] Statut juridique créé : en France, micro-entreprise déclarée sur le guichet unique (formalites.entreprises.gouv.fr) ; au Burkina Faso, entreprise individuelle immatriculée au CEFORE (RCCM et IFU).
- [ ] Moyens de paiement ouverts (prestataire de paiement par carte, mobile money) et modèle de facture prêt.
- [ ] Serveur durci (partie 5.5), notes A ou A+ aux tests de la partie 5.9.
- [ ] Sauvegarde nocturne active, une restauration testée, copie hors du serveur.
- [ ] Surveillance de disponibilité active (partie 5.12).
- [ ] Compte administrateur protégé par un mot de passe long et unique, rangé dans un gestionnaire de mots de passe.
- [ ] Première version signée publiée (partie 8).
- [ ] Une analyse complète réalisée de bout en bout sur le site en ligne, depuis un ordinateur et depuis un téléphone.

En cas de doute à n'importe quelle étape, ne forcez pas : relisez le message d'erreur, il indique presque toujours la cause, et conservez une sauvegarde avant chaque opération importante.
