# Journal des modifications

## 1.0.0 — 2 octobre 2026

Première version.

- Dépôt de données CSV, Excel, SPSS et Stata ; typage automatique des variables, repérage et suppression ou pseudonymisation des identifiants personnels.
- Analyses descriptives, bivariées (choix automatique du test, tailles d'effet, correction de Benjamini-Hochberg), multivariées (linéaire, logistique binaire, multinomiale, ordonnée, Poisson, binomiale négative), multi-niveaux (linéaire et logistique à ordonnée aléatoire), factorielles (ACP, ACM, classification) et de survie.
- Revue de littérature à partir d'OpenAlex (repli Crossref), sur mots-clés uniquement.
- Rédaction par règles, avec rédaction assistée facultative par un modèle local (Ollama) ou par Claude, sous contrôle automatique des nombres, des références et des formulations causales.
- Documents Word (article, mémoire, rapport de stage, rapport d'étude, note de synthèse), classeur Excel, figures et paramètres de reproductibilité.
- Sécurité : HTTPS, Argon2id, sessions côté serveur, CSRF, CSP, chiffrement AES-256-GCM au repos, purge automatique, conteneur durci, intégration continue avec audit des dépendances et analyse statique.
