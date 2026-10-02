# Politique de sécurité

## Signaler une vulnérabilité

Merci de **ne pas** ouvrir de ticket public pour une faille de sécurité. Utilisez la fonction de signalement privé de GitHub : onglet **Security**, puis **Report a vulnerability**. Indiquez la version concernée, les étapes pour reproduire et l'impact supposé.

Un accusé de réception est envoyé sous sept jours. Les correctifs sont publiés dès que possible, avec une mention du signalement si vous le souhaitez.

## Versions maintenues

| Version | Correctifs de sécurité |
|---|---|
| 1.x | Oui |

## Mesures en place

Le détail des protections (HTTPS, Argon2id, sessions, CSRF, CSP, chiffrement AES-256-GCM au repos, conteneur durci, contrôle des fichiers déposés) est décrit dans [docs/SECURITE.md](docs/SECURITE.md). Les dépendances sont auditées à chaque modification (`pip-audit`), le code est analysé par `bandit` et CodeQL, et Dependabot propose les mises à jour chaque semaine.
