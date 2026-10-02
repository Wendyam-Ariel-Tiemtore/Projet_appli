# Politique de confidentialité

Cette page décrit ce que l'application fait des données que vous lui confiez. Elle s'applique à l'installation locale, sur votre ordinateur ou sur un serveur de votre institution : l'auteur de l'application ne reçoit aucune donnée, n'exploite aucun service en ligne et ne collecte aucune statistique d'usage.

## Principes

1. **Traitement local.** Les calculs statistiques, la mise en forme des documents et, si vous le choisissez, la rédaction par un modèle local (Ollama) s'exécutent sur la machine qui héberge l'application.
2. **Minimisation.** L'application repère les identifiants directs (noms, téléphones, courriels, adresses, numéros d'identité) et propose de les supprimer avant l'analyse, ou de les remplacer par un code non réversible lorsqu'ils servent à regrouper des observations.
3. **Chiffrement au repos.** Les fichiers déposés et les résultats sont chiffrés (AES-256-GCM), avec une clé propre à chaque projet. Le nom du projet, le nom du fichier, la configuration et le texte de votre demande sont également chiffrés dans la base.
4. **Cloisonnement.** Chaque utilisateur ne voit que ses projets. L'administrateur gère les comptes mais n'a pas accès aux données des autres.
5. **Durée de conservation limitée.** Les projets inactifs sont supprimés automatiquement (7 jours par défaut). La suppression détruit la clé du projet : les fichiers résiduels deviennent illisibles.
6. **Aucun traceur.** Pas de cookie publicitaire ni de mesure d'audience. Aucune police, aucun script ni aucune image n'est chargé depuis un site tiers.

## Ce qui peut quitter la machine, et seulement à votre demande

| Échange | Déclenchement | Contenu transmis | Destinataire |
|---|---|---|---|
| Recherche bibliographique | Case « Rechercher la littérature » cochée | Vos mots-clés, nettoyés, affichés avant l'envoi | OpenAlex (OurResearch), et Crossref en repli |
| Rédaction par Claude | Option « Claude » choisie **et** case de consentement cochée | Paragraphes de résultats agrégés, intitulés des variables, texte de cadrage que vous avez saisi, titres et résumés des articles trouvés | API d'Anthropic |

**Les données individuelles ne sont jamais transmises**, ni à OpenAlex, ni à Anthropic. Les résultats envoyés pour la rédaction sont des statistiques agrégées (pourcentages, coefficients, probabilités critiques) ; les proportions calculées sur moins de 10 observations ne sont pas reprises dans les phrases de synthèse.

L'administrateur peut interdire ces deux échanges dans la configuration (`ANALYSTE_ALLOW_LITERATURE=false`, `ANALYSTE_ALLOW_EXTERNAL_LLM=false`). L'application fonctionne alors entièrement hors ligne.

## Données conservées

| Donnée | Forme | Durée |
|---|---|---|
| Identifiant de compte | En clair | Jusqu'à la suppression du compte |
| Mot de passe | Empreinte Argon2id (irréversible) | Jusqu'à la suppression du compte |
| Clé d'API Claude personnelle | Chiffrée | Jusqu'à son retrait |
| Fichier de données, résultats | Chiffrés, clé par projet | Durée de conservation configurée |
| Journal d'audit | Actions (connexion, dépôt, analyse, téléchargement, suppression), sans contenu de données | Jusqu'à la suppression de la base |

## Vos droits

Vous pouvez à tout moment supprimer un projet ou votre compte (Paramètres). Ces suppressions sont immédiates et définitives. Pour toute autre demande, adressez-vous à l'administrateur de votre installation, qui est le responsable du traitement au sens du règlement général sur la protection des données (RGPD) ou de la législation applicable dans votre pays.

## Responsabilités du chercheur

L'application aide à protéger les données ; elle ne remplace pas les obligations éthiques et légales de la recherche :

- disposer du droit d'utiliser les données (convention d'accès, consentement des participants, avis d'un comité d'éthique le cas échéant) ;
- ne déposer que les variables nécessaires à l'analyse ;
- respecter l'anonymat des participants dans le document final, en particulier pour les petits effectifs (une modalité regroupant deux ou trois personnes peut suffire à les identifier).
