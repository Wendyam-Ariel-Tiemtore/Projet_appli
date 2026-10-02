# Journal des modifications

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
