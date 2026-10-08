# Guide méthodologique

Ce document décrit **les règles que l'application applique automatiquement** pour choisir, conduire et rédiger chaque analyse. Il est la référence à citer dans la section « Méthodes » de vos travaux, et la grille à laquelle vous pouvez confronter chaque résultat produit.

Ces règles s'appuient sur les manuels de référence (cités en fin de document) et sur les enseignements de statistique sociale et de démographie de l'ISSP (Université Joseph Ki-Zerbo) : statistique descriptive, mesures d'association, régression linéaire et logistique (Y. Onadja), analyse multivariée (ACP, AFC, AFCM, classification), analyse multi-niveaux (A. B. Soura), analyse de survie, technique de rédaction (M. Bougma, G. Sangli ; guide d'A. Buttler, EPFL).

---

## 1. Principes généraux

1. **Posture associative par défaut.** Sur des données d'observation transversales, l'application parle d'*association*, jamais d'*effet* ni de *cause*. Les formulations causales sont filtrées à la rédaction.
2. **Le niveau de mesure commande la méthode.** Chaque variable est typée (identifiant, binaire, nominale, ordinale, continue, comptage, date) ; le choix des tests et des coefficients découle de ce typage, que l'utilisateur valide avant l'analyse.
3. **Les conditions d'application sont vérifiées, pas supposées.** Normalité, homogénéité des variances, effectifs attendus, multicolinéarité, adéquation du modèle : chaque test retenu est accompagné du diagnostic qui le justifie, et le test de repli est appliqué quand la condition échoue.
4. **Taille d'effet et intervalle de confiance avec chaque test.** Une probabilité critique seule n'est jamais rapportée (Wasserstein et Lazar, 2016).
5. **Correction de la multiplicité.** Toute famille de tests (par exemple, la variable dépendante croisée avec chaque variable explicative) est corrigée par la procédure de Benjamini et Hochberg (1995). Les probabilités brutes et corrigées sont toujours présentées côte à côte.
6. **Aucun chiffre n'est inventé.** Tout nombre figurant dans le texte rédigé provient d'un calcul de l'application ; un contrôle automatique rejette tout paragraphe contenant un nombre absent des résultats.
7. **Aucune référence n'est inventée.** Les références bibliographiques proviennent soit d'une bibliothèque méthodologique vérifiée intégrée à l'application, soit d'une base scientifique ouverte (OpenAlex, Crossref) avec DOI ; un contrôle rejette toute citation absente de la bibliographie.
8. **Reproductibilité.** Graine aléatoire fixée (42), versions des bibliothèques et paramètres consignés en annexe de chaque document.

## 2. Typage des variables

| Type | Règle de détection automatique (modifiable par l'utilisateur) |
|---|---|
| Identifiant | Valeurs uniques pour plus de 95 % des lignes, ou nom évocateur (`id`, `code`, `matricule`…) ; exclu des analyses |
| Binaire | Exactement deux modalités observées |
| Nominale | Texte, ou numérique entier avec au plus 12 modalités sans ordre déclaré |
| Ordinale | Étiquettes ordonnées déclarées (SPSS/Stata) ou désignées par l'utilisateur |
| Comptage | Entiers positifs ou nuls, plus de 12 valeurs distinctes ou désignés comme tels |
| Continue | Numérique avec plus de 12 valeurs distinctes |
| Date | Format date reconnu |

## 3. Analyse descriptive univariée

- **Variables qualitatives** : effectifs, pourcentages et intervalle de confiance à 95 % de Wilson (1927), plus robuste que l'approximation normale pour les petits effectifs et les proportions extrêmes.
- **Variables quantitatives** : effectif, moyenne, écart type, médiane, intervalle interquartile, minimum, maximum, asymétrie, aplatissement, test de normalité de Shapiro-Wilk (1965) jusqu'à 5 000 observations, de D'Agostino-Pearson au-delà.
- **Valeurs manquantes** : taux par variable, signalement au-delà de 5 %, et avertissement si les manquants diffèrent selon la variable dépendante (mécanisme possiblement non MCAR, Rubin, 1976).
- **Valeurs atypiques** : règle de Tukey (1977) à 1,5 et 3 intervalles interquartiles ; signalées, jamais supprimées automatiquement.
- **Pondération** : si une variable de poids est déclarée, les proportions et moyennes descriptives sont pondérées et l'effectif non pondéré est également rapporté.

## 4. Analyse bivariée : choix automatique du test

### 4.1 Deux variables qualitatives

| Situation | Test | Mesure d'association |
|---|---|---|
| Tableau 2 × 2, un effectif attendu < 5 | Exact de Fisher (1922) | Rapport de cotes et IC 95 % |
| Effectifs attendus ≥ 5 dans au moins 80 % des cases et aucun < 1 (Cochran, 1954) | Khi-deux de Pearson | V de Cramér (1946) |
| Règle de Cochran non respectée, tableau > 2 × 2 | Khi-deux avec probabilité critique par simulation de Monte-Carlo (10 000 tirages) | V de Cramér, fiabilité signalée « faible » |
| Deux variables ordinales (ou ordinale × binaire ordonnable) | Khi-deux + test de la tendance | d de Somers (1962) asymétrique, VD en ligne |

**Règle de choix du coefficient** (synthèse des coefficients d'association, ISSP) : on retient le coefficient adapté à la variable de **plus faible** niveau de mesure : V de Cramér dès qu'une variable est nominale ; d de Somers si les deux sont au moins ordinales ; r de Pearson seulement si les deux sont d'intervalle ou de rapport.

**Repères d'intensité** (indicatifs) :

| Coefficient | Absence | Très faible | Faible | Modérée | Forte | Très forte |
|---|---|---|---|---|---|---|
| V de Cramér | < 0,05 | [0,05 ; 0,10[ | [0,10 ; 0,20[ | [0,20 ; 0,40[ | [0,40 ; 0,80[ | ≥ 0,80 |
| d de Somers (valeur absolue) | < 0,05 | [0,05 ; 0,10[ | [0,10 ; 0,20[ | [0,20 ; 0,40[ | [0,40 ; 0,80[ | ≥ 0,80 |
| r de Pearson / ρ de Spearman (valeur absolue) | 0 | ]0 ; 0,20[ | [0,20 ; 0,40[ | [0,40 ; 0,60[ | [0,60 ; 0,90[ | ≥ 0,90 |

### 4.2 Une variable quantitative et une variable qualitative

| Groupes | Conditions vérifiées | Test retenu | Taille d'effet |
|---|---|---|---|
| 2 | Normalité dans chaque groupe (ou n ≥ 30 par groupe) | t de Welch (1947), qui ne suppose pas l'égalité des variances | d de Cohen (1988) et IC 95 % |
| 2 | Normalité rejetée et n < 30 dans un groupe, ou asymétrie forte (\|asymétrie\| > 1) | U de Mann-Whitney (1947) | Corrélation bisériale de rang |
| ≥ 3 | Normalité et homogénéité des variances (Levene, 1960) | ANOVA à un facteur, comparaisons de Tukey-Kramer (1956) | η² et ω² |
| ≥ 3 | Normalité, variances hétérogènes | ANOVA de Welch, comparaisons de Games-Howell (1976) | ω² |
| ≥ 3 | Normalité rejetée | Kruskal-Wallis (1952), comparaisons de Dunn (1964) ajustées par Holm (1979) | ε² (Tomczak et Tomczak, 2014) |

### 4.3 Deux variables quantitatives

- **Pearson** si les deux distributions sont compatibles avec la normalité et sans valeur atypique extrême ; **Spearman** (1904) sinon. Les deux sont toujours calculés ; le coefficient retenu est justifié. IC 95 % par transformation de Fisher.

## 5. Modélisation explicative

La forme du modèle découle du type de la variable dépendante. Chaque modèle est présenté en **deux colonnes** : association brute (modèle à une variable) et association ajustée (modèle complet), selon l'usage en démographie et en épidémiologie (von Elm et al., 2007).

| Variable dépendante | Modèle | Coefficients rapportés | Diagnostics systématiques |
|---|---|---|---|
| Continue | Moindres carrés ordinaires, erreurs types robustes HC3 (MacKinnon et White, 1985) | β, IC 95 %, β standardisés | R² et R² ajusté, test F, VIF, Breusch-Pagan (1979), normalité des résidus, RESET de Ramsey (1969), distance de Cook |
| Binaire | Régression logistique (Hosmer, Lemeshow et Sturdivant, 2013) | Rapports de cotes (OR), IC 95 % | Rapport de vraisemblance global, pseudo-R² de McFadden (1974) et de Nagelkerke (1991), Hosmer-Lemeshow, aire sous la courbe ROC, VIF, rapport événements/paramètres |
| Nominale > 2 modalités | Logistique multinomiale | Rapports de risques relatifs (RRR) par rapport à la modalité de référence | Rapport de vraisemblance, pseudo-R² ; rappel de l'hypothèse d'indépendance des alternatives |
| Ordinale | Logistique ordonnée à cotes proportionnelles (McCullagh, 1980) | OR cumulés | Test de l'hypothèse de cotes proportionnelles (comparaison avec le modèle multinomial ; Brant, 1990) |
| Comptage | Poisson ; binomiale négative si surdispersion (Cameron et Trivedi, 1990) | Rapports de taux d'incidence (IRR) | Test de surdispersion, déviance |

**Règles de prudence appliquées** :
- Au moins 10 événements par paramètre estimé en logistique ; en deçà, un avertissement est inséré et la sélection de variables est signalée comme fragile.
- VIF > 5 signalé, VIF > 10 qualifié de multicolinéarité forte.
- Modalité de référence : la plus fréquente par défaut, modifiable.
- Si une variable de grappe est déclarée sans analyse multi-niveaux, les erreurs types sont robustes à la grappe.
- **Séparation des données** (une modalité qui connaît toujours, ou jamais, l'événement) : détectée automatiquement ; la régression logistique est alors estimée par la vraisemblance pénalisée de Firth (1993 ; Heinze et Schemper, 2002), qui fournit des estimations finies et peu biaisées. Le document le signale.

### 5.1 Fiabilité des résultats

Une section dédiée évalue la solidité du modèle explicatif à l'aide de critères chiffrés, chacun accompagné d'un repère de la littérature et d'une explication en langage courant. Une appréciation globale en découle (élevée, bonne, satisfaisante ou à interpréter avec prudence).

| Contrôle | Méthode | Repère |
|---|---|---|
| Taille et exclusions | Observations analysées, part exclue pour valeurs manquantes | au moins 100 ; moins de 10 % exclues |
| Stabilité des coefficients | Événements par paramètre (Peduzzi et al., 1996), VIF, séparation | au moins 10 ; VIF < 5 |
| Ajustement | Hosmer et Lemeshow | p ≥ 0,05 |
| Sur-ajustement | Validation interne par bootstrap, 200 rééchantillonnages, correction de l'optimisme de l'AUC ou du R² et pente de calibration (Harrell, Lee et Mark, 1996 ; Steyerberg et al., 2001) | optimisme < 0,03 |
| Pouvoir discriminant | AUC corrigée de l'optimisme | 0,70 et plus : élevé |
| Effets omis | Modèle d'apprentissage automatique témoin (gradient boosting ; Friedman, 2001) comparé en validation croisée à cinq blocs, **formés de grappes entières** lorsque les observations sont regroupées, pour éviter qu'un modèle flexible ne « reconnaisse » les grappes ; importance des variables par permutation (Breiman, 2001) | écart d'AUC ou de R² < 0,03 |
| Forme du modèle | Tests du rapport de vraisemblance de la non-linéarité de chaque variable quantitative (spline cubique restreinte à quatre noeuds ; Harrell, 2015) et des interactions entre les quatre variables les plus importantes, avec correction de Holm | aucun effet omis significatif |
| Contextes | Nombre d'unités de niveau 2 (Maas et Hox, 2005) | au moins 30 |

Le modèle d'apprentissage automatique sert de témoin et n'est jamais interprété : le document reste fondé sur un modèle explicatif lisible, conformément aux usages des sciences sociales.

### 5.2 Vérification des hypothèses

L'auteur peut saisir jusqu'à six hypothèses, en indiquant pour chacune la variable concernée et le sens attendu (association positive, négative ou simple association), ou laisser l'application les déduire de la phrase. Chaque hypothèse est confrontée au modèle final (multi-niveaux s'il existe, sinon multivarié) et, à défaut, au test bivarié. Le verdict est l'un des suivants : **confirmée** (effet significatif dans le sens attendu), **partiellement confirmée** (sens attendu pour une partie des modalités seulement, ou association bivariée qui ne résiste pas à l'ajustement), **non confirmée** (aucune association significative), **infirmée** (effet significatif de sens contraire) ou **non vérifiable** (variable absente des analyses). Un tableau récapitulatif et un paragraphe argumenté par hypothèse sont insérés avant la discussion.

### 5.3 Lecture pour les non-spécialistes

Chaque document comporte une annexe « Lecture des résultats en langage simple » (ce qui a été fait, ce qui en ressort, comment lire un rapport de cotes, quelle confiance accorder aux résultats) et un lexique limité aux notions effectivement employées. La page du projet affiche l'encadré « Ce qu'il faut retenir » et les contrôles de fiabilité expliqués simplement.

## 6. Analyse multi-niveaux

Démarche par étapes, du plus simple au plus complexe (Soura, cours 2POP2302 ; Snijders et Bosker, 2012 ; Goldstein, 2011) :

1. **M0, modèle vide** à variance composée : la variance contextuelle est-elle significative ? Test du rapport de vraisemblance contre le modèle sans effet aléatoire, avec correction pour la valeur à la frontière de l'espace des paramètres (mélange 50:50 de khi-deux, Self et Liang, 1987).
2. **M1** : ajout des variables individuelles (niveau 1). Évolution de la variance contextuelle : sa baisse mesure la part des différences entre contextes due à des **effets de composition**.
3. **M2** : ajout des variables contextuelles (niveau 2). La baisse supplémentaire de variance mesure la part expliquée par les **effets de contexte** observés.
4. **M3**, au besoin : pente aléatoire d'une variable individuelle (modèle linéaire), interactions entre niveaux.

**Indicateurs rapportés** :
- **Coefficient de partition de la variance (VPC / CCI)** : σ²ᵤ / (σ²ᵤ + σ²ₑ) en linéaire ; en logistique, σ²ᵤ / (σ²ᵤ + π²/3), la variance de niveau 1 étant fixée à π²/3 ≈ 3,29 par l'approche de la variable latente.
- **Variation de la variance contextuelle** en pourcentage par rapport à M0.
- **Rapport de cotes médian (MOR)** en logistique : exp(√(2σ²ᵤ) × Φ⁻¹(0,75)) (Larsen et Merlo, 2005 ; Merlo et al., 2006).
- Tests de Wald pour les effets fixes, rapport de vraisemblance pour les effets aléatoires.

**Mise en garde rédigée automatiquement** : inférence écologique fallacieuse (ne pas lire au niveau individuel une relation agrégée) et erreur atomiste (ignorer le contexte).

**Estimation** : modèle linéaire mixte par maximum de vraisemblance (statsmodels) ; logistique multi-niveaux à ordonnée aléatoire par maximum de vraisemblance avec quadrature de Gauss-Hermite adaptative (Pinheiro et Bates, 1995), implémentée dans l'application et validée sur données simulées (tests automatisés).

**Condition minimale** : au moins 10 contextes et une moyenne d'au moins 5 individus par contexte ; en deçà, l'analyse est signalée comme peu fiable.

## 7. Analyses multivariées descriptives

- **ACP** (variables quantitatives, au moins 3) : diagnostics de factorabilité **avant** interprétation, à savoir l'indice KMO (Kaiser, 1974 ; < 0,50 inacceptable), test de sphéricité de Bartlett (1950), analyse parallèle de Horn (1965, 500 réplications, quantile 95 %). Si ces diagnostics échouent, l'absence de structure factorielle est rapportée comme un **résultat** et l'ACP n'est pas interprétée comme une réduction.
- **AFCM / ACM** (variables qualitatives, au moins 3) : taux d'inertie corrigés de Benzécri (1979), contributions et cosinus carrés des modalités (Greenacre, 2017).
- **Classification ascendante hiérarchique** sur les coordonnées factorielles, critère de Ward (1963) ; nombre de classes par la largeur moyenne de silhouette (Rousseeuw, 1987) ; description des classes par les modalités sur-représentées (test de la valeur-test).
- **Cohérence interne d'une échelle** : α de Cronbach (1951) ; seuil conventionnel de 0,70. Un α faible sur un indice de comptage est interprété comme un indice formatif, et non comme une mauvaise mesure.

## 8. Analyse de survie (si durée et événement déclarés)

Estimateur de Kaplan-Meier (1958), test du log-rank (Mantel, 1966), modèle de Cox (1972) avec rapports de risques instantanés (HR) et test de l'hypothèse des risques proportionnels par les résidus de Schoenfeld (Grambsch et Therneau, 1994).

## 9. Revue de littérature

- **Seuls les mots-clés** du sujet sont envoyés à OpenAlex (Priem, Piwowar et Orr, 2022) ; jamais les données ni leurs résultats. L'utilisateur voit et valide la requête avant envoi.
- Déduplication par DOI, classement par pertinence et par citations, regroupement thématique (TF-IDF et classification).
- **Tableau de synthèse** par thème : auteurs et année, objet, méthode, principaux résultats, limites (format du rapport INNOGOUV), rempli à partir des résumés disponibles.
- Les éléments non disponibles dans le résumé sont marqués « non renseigné dans le résumé » plutôt qu'extrapolés.
- Avec un modèle de langage, l'extraction de ces éléments et l'intitulé des thèmes sont rédigés par le modèle à partir du seul résumé ; tout nombre absent du résumé fait rejeter l'élément, remplacé par l'extraction par règles.
- Références au format APA 7, avec DOI.

## 10. Structure des documents

| Document | Structure |
|---|---|
| Article scientifique | Résumé et mots-clés, Introduction (avec revue), Données et méthodes, Résultats, Discussion, Conclusion, Références (format IMRaD) ; proportions indicatives : introduction 10 %, méthodes 20 %, résultats 20 %, discussion 40 % (Duchemin) |
| Mémoire | Introduction générale ; cadre théorique et conceptuel (revue, hypothèses) ; méthodologie (sources, variables, méthodes) ; résultats descriptifs ; facteurs associés (bivarié) ; analyse explicative (multivarié, multi-niveaux) ; discussion ; conclusion et recommandations ; bibliographie ; annexes |
| Rapport de stage | Remerciements ; introduction ; présentation de la structure d'accueil (à compléter par l'auteur) ; cadre théorique ; données et méthodes ; résultats et discussion ; apport du stage (à compléter) ; conclusion ; bibliographie ; annexes |
| Rapport d'étude | Résumé exécutif ; contexte et objectifs ; méthodologie ; résultats ; conclusions et recommandations ; annexes méthodologiques |
| Note de synthèse | Messages clés ; résultats principaux ; méthode en bref ; limites |

Chaque tableau porte un numéro, un titre explicite, une source (« Source : données de l'utilisateur, calculs de l'auteur ») et une note de lecture des seuils de significativité. Les sections que seule une personne peut rédiger (remerciements, présentation de la structure d'accueil, apport personnel) sont marquées clairement **[À compléter par l'auteur]** : l'application ne les invente pas.

## 11. Style de rédaction

Les textes produits suivent les usages des mémoires et rapports de stage en statistique sociale et en démographie, et non le style d'un outil :

- aucun tiret long ni demi-cadratin comme ponctuation (virgule, deux-points ou parenthèses à la place) ; un nettoyage typographique final s'applique aussi aux textes rédigés par un modèle de langage et au texte de cadrage saisi par l'auteur ;
- première personne du pluriel (« nous constatons que », « nous pouvons donc dire que ») ou forme impersonnelle (« il ressort que », « il convient de préciser que ») ;
- connecteurs sobres et variés (En effet, Par ailleurs, De même, Quant à, En ce qui concerne, En revanche, Enfin) ;
- petits effectifs écrits en lettres suivis des chiffres entre parenthèses (« sept (07) variables »), chiffres seuls au-delà de 99 ;
- variables désignées par un groupe nominal avec article (« le niveau d'instruction »), guillemets réservés aux modalités (« Primaire ») ;
- modalités d'une même variable regroupées dans un seul paragraphe, avec la tendance d'ensemble lorsqu'elle est monotone (« Nous pouvons donc dire que les chances d'utiliser une méthode contraceptive moderne augmentent avec le niveau d'instruction ») ;
- probabilités critiques écrites en toutes lettres dans le texte (« une probabilité critique inférieure à 0,001 »), symboles réservés aux parenthèses et aux tableaux.

**Lecture des rapports de cotes.** Conformément à l'usage en démographie (cours de régression logistique de l'ISSP), un rapport de cotes supérieur à 1 est lu comme « x fois plus de chances » et un rapport inférieur à 1 comme « (1 - OR) × 100 % moins de chances ». Il s'agit de rapports de cotes et non de rapports de probabilités ; les deux sont proches lorsque l'événement est peu fréquent, et la section Méthodes du document le rappelle.

**Formulations personnalisables.** À l'étape « Variables », l'auteur peut préciser l'unité d'observation (« femmes », « ménages »), l'événement étudié à l'infinitif (« utiliser une méthode contraceptive moderne »), le nom de l'indicateur (« la prévalence contraceptive moderne ») et la formulation de chaque variable dans le texte. À l'étape « Demande », un extrait de sa propre écriture peut être fourni au modèle de langage, qui en imite la grammaire et les tournures sans en reprendre le contenu.

## 12. Choix de méthodes laissés à l'auteur

| Choix | Options | Effet |
|---|---|---|
| Analyses conduites | bivariée, multivariée, multi-niveaux, factorielles et typologie, survie | l'audit de qualité et l'analyse descriptive sont toujours réalisés |
| Seuil de signification | 1 %, 5 % (usuel), 10 % | lecture des associations, des effets ajustés et de la variance contextuelle ; les tests de conditions d'application (normalité, Levene, Hosmer-Lemeshow, Brant) restent à 5 % |
| Correction pour les tests multiples | Benjamini et Hochberg (1995), Holm (1979), aucune | sans correction, le document le signale et rappelle le risque accru de faux positifs |
| Tests pour les variables quantitatives | choix automatique, ou non paramétriques uniquement | Mann-Whitney, Kruskal-Wallis et Spearman remplacent alors t de Welch, ANOVA et Pearson |

Le type de modèle multivarié n'est pas laissé au choix : il découle de la nature de la variable dépendante (linéaire, logistique binaire, multinomiale, ordonnée, Poisson ou binomiale négative), seule spécification correcte.

## 13. Présentations orales

La présentation est construite à partir des résultats calculés, sans aucune valeur ajoutée.

- **Types** : soutenance, communication scientifique, séminaire, restitution professionnelle, atelier de validation ; chacun fixe des réglages par défaut (durée, déroulé, niveau de détail, visuels, annexes) que l'auteur peut modifier.
- **Durée** : environ une diapositive par minute et demie ; au-delà, les diapositives secondaires (hypothèses détaillées, deuxième graphique bivarié, typologie, survie, limites) sont retirées en premier.
- **Titres affirmatifs** tirés des résultats (« Sept (07) facteurs sur neuf (09) sont associés à… », « Après ajustement, quatre (04) facteurs restent associés à… »), conformément à l'usage des présentations de résultats.
- **Graphiques natifs** modifiables dans PowerPoint, étiquettes écrites à la française ; graphique en forêt des seuls effets significatifs ; tableaux allégés pour les décideurs.
- **Notes de l'orateur** : paragraphes du document adaptés à l'oral, avec une formule d'ouverture propre au type (« Monsieur le Président du jury, Mesdames et Messieurs les membres du jury… » pour une soutenance).
- **Mise en page** : fonds sombres pour l'ouverture, la conclusion et la clôture ; pastilles numérotées comme seul motif ; aucune ligne décorative ; polices disponibles partout (Cambria et Calibri) ; espaces insécables du français (nombre et unité, guillemets, deux-points).
- **Recommandations** : seules celles saisies par l'auteur sont reprises.

## 14. Ce que l'application ne fait pas, et le dit

- Pas d'inférence causale sur des données d'observation (pas de variables instrumentales ni d'appariement dans cette version).
- Pas de plan de sondage complexe complet (stratification et pondération dans les estimations de variance) : la pondération est appliquée aux descriptifs, et les erreurs types sont robustes à la grappe si une grappe est déclarée. Un avertissement le rappelle dans la section Méthodes.
- Pas de pente aléatoire en logistique multi-niveaux (ordonnée aléatoire uniquement) dans cette version.
- Pas de modification automatique du modèle à partir des effets omis détectés : l'application les signale et suggère comment en tenir compte, l'auteur décide.

---

## Références méthodologiques

Les références complètes, au format APA 7, sont dans le fichier [`analyste/stats/references.py`](../analyste/stats/references.py), qui alimente automatiquement la bibliographie de chaque document produit.
