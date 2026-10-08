# Journal des modifications

## 1.3.0 : 8 octobre 2026

Fiabilité maximale, hypothèses, langage simple, sécurité renforcée, application installable et cadre légal.

- **Hypothèses de recherche** : saisie guidée (phrase, variable, sens attendu), déduction automatique de la variable et du sens, verdict argumenté pour chacune et tableau récapitulatif.
- **Fiabilité des résultats** : régression logistique de Firth en cas de séparation ; validation interne par bootstrap (optimisme de l'AUC ou du R², pente de calibration) ; modèle d'apprentissage automatique témoin en validation croisée formée de grappes entières ; recherche systématique d'effets non linéaires (splines cubiques restreintes) et d'interactions avec correction de Holm ; bilan chiffré avec appréciation globale.
- **Pour les non-spécialistes** : annexe « Lecture des résultats en langage simple », lexique des notions employées, page Lexique, encadré « Ce qu'il faut retenir » et contrôles de fiabilité expliqués sur la page du projet.
- **Sécurité** (audit offensif) : lecture des fichiers bornée et en flux ; corps des requêtes limité avant lecture ; analyses dans un processus borné en durée et en mémoire, une à la fois par compte ; blocage de connexion par compte et par adresse sans divulgation ; premier administrateur atomique et code d'installation sur serveur ; cookies `__Host-` ; adresse réelle crue seulement depuis le proxy ; garde contre l'injection d'instructions ; actions et images épinglées. Tests de non-régression pour chaque faille.
- **Application installable** sur téléphone, tablette et ordinateur (manifeste, icônes, service worker limité aux ressources statiques, page hors connexion) ; lien Android pour Google Play.
- **Cadre légal et signature** : licence propriétaire, mentions légales, CGU, CGV, politique de confidentialité complétée (RGPD et loi burkinabè n° 001-2021/AN), page À propos, composants tiers, signature dans le pied de page et les propriétés des documents.
- **Publication signée** : image Docker publiée et signée (Sigstore), SBOM, attestation de provenance, archive et empreintes signées.
- **Guide pas à pas** (Git, Docker, VS Code, serveur durci, sauvegardes chiffrées, téléphone, ordinateur) et scripts `deploy/preparer_serveur.sh`, `deploy/sauvegarder.sh`, `deploy/restaurer.sh`.

## 1.2.1 : 3 octobre 2026

- Accès par https://127.0.0.1 corrigé : le proxy présente un certificat de l'autorité locale quand le navigateur n'envoie pas de nom de serveur (erreur ERR_SSL_PROTOCOL_ERROR).
- Scripts `faire_confiance.ps1` (Windows) et `faire_confiance.sh` (macOS, Linux) pour supprimer l'avertissement du navigateur.
- En-tête HSTS sans `includeSubDomains`, pour ne pas imposer HTTPS aux autres sous-domaines d'un nom de domaine.
- Procédure de mise à jour documentée.

## 1.2.0 : 3 octobre 2026

Présentations orales et choix de méthodes.

- Présentation PowerPoint facultative : soutenance, communication scientifique, séminaire, restitution professionnelle ou atelier ; durée, déroulé (classique ou messages clés d'abord), niveau de détail, graphiques ou tableaux, quatre thèmes, format 16:9 ou 4:3, contenus, recommandations de l'auteur, notes de l'orateur et annexes techniques.
- Titres de diapositives tirés des résultats, graphiques natifs modifiables, graphique en forêt des effets significatifs, espaces insécables du français.
- Choix de méthodes : analyses à conduire, seuil de signification (1, 5 ou 10 %), correction pour les tests multiples (Benjamini et Hochberg, Holm ou aucune), tests non paramétriques uniquement.
- Chapitres du mémoire numérotés selon les analyses réellement conduites.
- Métadonnées des fichiers Word, PowerPoint et Excel au nom de l'auteur, sans mention des bibliothèques de génération.

## 1.1.0 : 2 octobre 2026

Rédaction au style des mémoires et rapports de stage.

- Plus aucun tiret long ni demi-cadratin dans les documents : nettoyage typographique de tous les textes, titres, légendes et notes, y compris ceux d'un modèle de langage.
- Commentaires réécrits pour toutes les analyses (descriptive, bivariée, multivariée, multi-niveaux, factorielle, survie, littérature) : « nous » de modestie, connecteurs variés, nombres en lettres (« sept (07) »), variables nommées avec leur article, modalités regroupées par variable, rapports de cotes lus en « fois plus de chances » ou « % moins de chances ».
- Nouvelles options : unité d'observation, événement étudié, nom de l'indicateur et formulation de chaque variable dans le texte ; extrait de l'écriture de l'auteur transmis au modèle de langage pour qu'il en imite le style.
- Consignes de style renforcées pour le modèle de langage (expressions typiques des textes générés proscrites).
- Mémoire et rapport de stage : chapitres et parties numérotés à la française (« Chapitre 2 : Méthodologie », sections 2.1, 2.2) ; légendes « Tableau n » et « Graphique n » numérotées dès l'ouverture du document.
- Phrases de synthèse dédiées pour le résumé, la discussion et la conclusion.

## 1.0.0 : 2 octobre 2026

Première version.

- Dépôt de données CSV, Excel, SPSS et Stata ; typage automatique des variables, repérage et suppression ou pseudonymisation des identifiants personnels.
- Analyses descriptives, bivariées (choix automatique du test, tailles d'effet, correction de Benjamini-Hochberg), multivariées (linéaire, logistique binaire, multinomiale, ordonnée, Poisson, binomiale négative), multi-niveaux (linéaire et logistique à ordonnée aléatoire), factorielles (ACP, ACM, classification) et de survie.
- Revue de littérature à partir d'OpenAlex (repli Crossref), sur mots-clés uniquement.
- Rédaction par règles, avec rédaction assistée facultative par un modèle local (Ollama) ou par Claude, sous contrôle automatique des nombres, des références et des formulations causales.
- Documents Word (article, mémoire, rapport de stage, rapport d'étude, note de synthèse), classeur Excel, figures et paramètres de reproductibilité.
- Sécurité : HTTPS, Argon2id, sessions côté serveur, CSRF, CSP, chiffrement AES-256-GCM au repos, purge automatique, conteneur durci, intégration continue avec audit des dépendances et analyse statique.
