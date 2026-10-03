# Aide et questions fréquentes

## Prise en main

### Que fait l'application, concrètement ?

Vous déposez un fichier de données, vous indiquez le rôle de chaque variable et le type de document voulu (article, mémoire, rapport de stage, rapport d'étude, note de synthèse). L'application :

1. contrôle la qualité des données et repère les identifiants personnels ;
2. produit les statistiques descriptives avec intervalles de confiance ;
3. croise la variable dépendante avec chaque variable explicative, en choisissant automatiquement le test adapté et en corrigeant pour les tests multiples ;
4. estime le modèle multivarié adapté à la variable dépendante (linéaire, logistique binaire, multinomiale, ordonnée, Poisson ou binomiale négative), avec ses diagnostics ;
5. si un identifiant de contexte est déclaré, conduit l'analyse multi-niveaux par étapes (modèle vide, variables individuelles, variables contextuelles) ;
6. au besoin, réalise ACP, ACM, typologie et analyse de survie ;
7. si vous l'autorisez, recherche la littérature scientifique dans OpenAlex à partir de vos seuls mots-clés ;
8. assemble un document Word structuré, accompagné d'un classeur Excel de tous les tableaux, des figures et des paramètres de reproductibilité.

### Quels formats de fichiers sont acceptés ?

CSV, TSV et TXT délimités (virgule, point-virgule, tabulation ; virgule décimale reconnue), Excel `.xlsx` (première feuille), SPSS `.sav` et Stata `.dta`. Pour SPSS et Stata, les étiquettes de valeurs et le caractère ordinal déclaré dans SPSS sont repris automatiquement. Les classeurs contenant des macros sont refusés.

### Comment préparer mes données ?

- Une ligne par observation (individu, ménage, établissement…), une colonne par variable, la première ligne contenant les noms.
- Codez les valeurs manquantes par une cellule vide (les codes `NA`, `N/A`, `NSP` et `.` sont aussi reconnus). Un code numérique comme `99` ou `-9` doit être recodé avant le dépôt : sinon il sera pris pour une vraie valeur.
- Retirez les colonnes nominatives inutiles (noms, téléphones). L'application les repère et propose de les supprimer, mais le plus sûr est de ne pas les déposer.

### Pourquoi faut-il vérifier le type des variables ?

Parce qu'il commande tout le reste. Une variable codée 1, 2, 3 peut être nominale (région), ordinale (niveau d'instruction) ou un comptage (nombre d'enfants) : le choix du test, du coefficient d'association et du modèle en dépend. L'application propose un type, avec sa raison ; vous seul savez ce que mesure la variable.

## Méthodes

### Comment le test bivarié est-il choisi ?

Selon le niveau de mesure des deux variables et la vérification de ses conditions d'application : khi-deux de Pearson si les effectifs attendus respectent la règle de Cochran, test exact de Fisher pour un tableau 2 × 2 à faibles effectifs, probabilité critique par permutations sinon ; t de Welch ou Mann-Whitney pour deux groupes ; ANOVA, ANOVA de Welch ou Kruskal-Wallis au-delà, suivis de comparaisons deux à deux ; Pearson ou Spearman pour deux variables quantitatives. Un tableau du document justifie le test retenu pour chaque variable. Le détail figure dans le [guide méthodologique](/methodologie).

### Pourquoi deux probabilités critiques, « p » et « p (FDR) » ou « p (Holm) » ?

Quand on teste une dizaine de variables, le risque d'obtenir au moins un résultat significatif par hasard augmente. La procédure de Benjamini et Hochberg (choix par défaut) ou celle de Holm, plus conservatrice, corrige ce risque ; seule la probabilité corrigée est utilisée pour conclure, mais les deux sont présentées par transparence. Si vous choisissez de ne pas corriger, le document le signale.

### Comment déclencher l'analyse multi-niveaux ?

Donnez le rôle « Identifiant du contexte » à la variable qui regroupe les observations (grappe d'enquête, village, école, établissement). Les variables constantes au sein de chaque contexte sont reconnues comme contextuelles ; vous pouvez aussi les désigner explicitement avec le rôle « Explicative contextuelle ». La variable dépendante doit être binaire ou continue dans cette version.

### Que sont les « blocs » ?

Ils permettent d'estimer des modèles emboîtés : numérotez 1 les caractéristiques sociodémographiques, 2 les caractéristiques économiques, 3 les variables contextuelles, par exemple. Le document présente alors les modèles côte à côte, avec leurs critères d'ajustement.

### L'application peut-elle conclure à une relation de cause à effet ?

Non. Sur des données d'observation, elle parle d'association, et le contrôle automatique de la rédaction rejette les formulations causales (« entraîne », « provoque », « impact »…). Si votre dispositif autorise une interprétation causale (expérimentation, quasi-expérience), c'est à vous de l'argumenter dans la discussion.

### Les données pondérées sont-elles prises en compte ?

Les statistiques descriptives sont pondérées si vous déclarez une variable de pondération, avec l'effectif efficace de Kish pour les intervalles de confiance. Les modèles ne tiennent pas compte d'un plan de sondage complexe (stratification) : cette limite est rappelée dans le document.

## Rédaction et intégrité académique

### Le document est-il prêt à être déposé ?

Non, et c'est voulu. Les résultats, les tableaux, les figures et la section Méthodes sont complets et rigoureux. Mais certaines parties exigent ce que seul l'auteur connaît : le contexte de son terrain, sa structure d'accueil, sa lecture de la littérature, l'interprétation finale. Elles sont surlignées en jaune « [À compléter par l'auteur] ». Relisez tout : vous êtes l'auteur et le responsable du document.

### Un modèle de langage peut-il inventer des chiffres ou des références ?

Il pourrait essayer ; l'application l'en empêche. Tout paragraphe rédigé par un modèle est vérifié : chaque nombre doit figurer dans les résultats calculés ou dans votre texte, chaque citation doit appartenir à la bibliographie (références méthodologiques vérifiées, ou articles réellement trouvés dans OpenAlex). Un paragraphe qui échoue est renvoyé au modèle une fois avec les corrections exigées, puis remplacé par le texte produit par les règles s'il échoue encore. Le journal de rédaction, en annexe du document, indique ce qui a été rédigé par un modèle.

### Dois-je déclarer l'usage de l'application ?

Oui, selon les règles de votre institution. Une déclaration type figure en annexe de chaque document produit. L'outil automatise des calculs et une mise en forme ; la démarche scientifique, la problématique et l'interprétation restent les vôtres.

### Le texte produit ressemble-t-il à un texte généré par une IA ?

Non. Les paragraphes sont rédigés dans le style des mémoires de statistique sociale et de démographie : « nous » de modestie, connecteurs sobres, petits nombres écrits en lettres (« sept (07) »), rapports de cotes lus en « fois plus de chances », aucune ponctuation par tiret long. Un nettoyage typographique final s'applique à tout le document, y compris aux textes rédigés par un modèle. Pour un rendu encore plus personnel, précisez à l'étape « Variables » l'unité d'observation, l'événement étudié et la formulation de chaque variable, puis collez à l'étape « Demande » un extrait de l'un de vos propres textes : le modèle de langage en imitera les tournures.

### Comment obtenir une présentation pour ma soutenance ou une réunion ?

À l'étape « Demande », cochez « Produire aussi une présentation PowerPoint » et choisissez :

- **le type** : soutenance (mémoire, rapport de stage, thèse), communication scientifique, séminaire de recherche, restitution professionnelle (décideurs, partenaires, bailleurs) ou atelier de validation ; chaque type propose des réglages par défaut que vous pouvez modifier ;
- **la durée** (10 à 45 minutes) : environ une diapositive par minute et demie, les diapositives secondaires étant écartées si le temps manque ;
- **le déroulé** : démarche classique (contexte, méthodes, résultats, conclusion) ou messages clés d'abord, comme on le fait devant des décideurs ;
- **le niveau de détail** : détaillé (tests, intervalles de confiance, probabilités critiques) ou allégé (chiffres essentiels en mots simples) ;
- **la présentation des résultats** : graphiques, tableaux, ou les deux ;
- **le thème visuel, le format** (16:9 ou 4:3), **les contenus** à présenter, **vos recommandations**, les **notes de l'orateur** et les **annexes techniques**.

Les titres des diapositives sont des phrases tirées de vos résultats (« La prévalence contraceptive moderne augmente avec le niveau d'instruction »), les graphiques sont modifiables dans PowerPoint et les notes de l'orateur reprennent le texte du document, adapté à l'oral. Aucune recommandation n'est inventée : seules les vôtres apparaissent.

### Puis-je choisir mes méthodes d'analyse ?

Oui. À l'étape « Demande », vous choisissez les analyses à conduire (bivariée, multivariée, multi-niveaux, factorielles, survie), le seuil de signification (1, 5 ou 10 %), la correction pour les tests multiples (Benjamini et Hochberg, Holm ou aucune) et l'approche des tests pour les variables quantitatives (choix automatique selon les conditions d'application, ou tests non paramétriques uniquement). Ces choix sont rappelés dans la section Méthodes du document et dans les paramètres de reproductibilité. Le type de modèle multivarié reste dicté par la nature de la variable dépendante, comme l'exige la rigueur.

### Quelle différence entre rédaction locale et rédaction par Claude ?

| Option | Où s'exécute le modèle | Ce qui est envoyé | Qualité de rédaction |
|---|---|---|---|
| Règles de l'application | Sur la machine | Rien | Résultats rédigés précisément ; introduction et discussion à compléter |
| Modèle local (Ollama) | Sur la machine | Rien | Dépend du modèle installé et de la puissance de l'ordinateur |
| Claude (API Anthropic) | Chez Anthropic | Résultats agrégés et texte de cadrage, jamais les données individuelles | La plus élevée |

## Confidentialité

### Mes données sortent-elles de ma machine ?

Non, sauf deux échanges que vous déclenchez explicitement : la requête bibliographique (vos mots-clés, rien d'autre, affichés avant envoi) et, si vous choisissez Claude et cochez la case de consentement, les résultats agrégés envoyés pour la rédaction. Voir la page [Confidentialité](/confidentialite).

### Combien de temps les projets sont-ils conservés ?

Ils sont supprimés automatiquement après la durée fixée par l'administrateur (7 jours par défaut) sans activité. Vous pouvez supprimer un projet à tout moment : sa clé de chiffrement est détruite, ce qui rend les fichiers résiduels illisibles.

## Problèmes courants

### Le navigateur affiche « ERR_SSL_PROTOCOL_ERROR » ou « Client sent an HTTP request to an HTTPS server »

Le second message apparaît quand on ouvre `http://127.0.0.1:443` : il faut taper `https://`, sans numéro de port, soit **https://localhost**. Le premier apparaissait avec `https://127.0.0.1` dans les versions antérieures à 1.2.1, car un navigateur n'indique pas de nom de serveur pour une adresse IP et le proxy ne savait pas quel certificat présenter. Mettez à jour (`git pull`, `docker compose up -d --build`, puis `docker compose restart proxy`) ou utilisez https://localhost.

### Le navigateur indique que la connexion n'est pas privée

Le certificat provient de l'autorité locale de votre installation, que le navigateur ne connaît pas encore. Lancez `scripts\faire_confiance.ps1` (Windows) ou `scripts/faire_confiance.sh` (macOS, Linux) depuis le dossier du projet, puis rouvrez le navigateur.

### « L'analyse a échoué »

Causes fréquentes : une variable qualitative déclarée comme continue ; une modalité très rare qui empêche l'estimation (séparation parfaite) ; deux variables redondantes (par exemple l'âge et le groupe d'âge dans le même modèle). Vérifiez le typage, regroupez les modalités rares dans votre fichier, retirez les doublons, puis relancez.

### Le sommaire est vide à l'ouverture du document

Word demande à l'ouverture s'il faut mettre à jour les champs : acceptez. Sinon, clic droit sur le sommaire, puis « Mettre à jour les champs ». Dans LibreOffice : Outils, puis Mettre à jour, puis Tout mettre à jour.

### Le modèle local ne rédige rien

Vérifiez qu'Ollama est lancé et que le modèle configuré est installé (`ollama pull <modèle>`). Si le modèle n'est pas disponible, l'application produit le document avec les textes de règles et l'indique dans le journal de rédaction.

### La recherche bibliographique ne renvoie rien

La machine doit avoir accès à Internet, et les mots-clés doivent être assez précis. Essayez des mots-clés en anglais : la majorité des publications indexées le sont.
