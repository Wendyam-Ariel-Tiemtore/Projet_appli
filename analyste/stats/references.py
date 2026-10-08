"""Bibliothèque de références méthodologiques vérifiées (APA 7).

Chaque analyse déclare les clés des références qu'elle mobilise ; la
bibliographie du document est construite à partir de cette table. Aucune
référence méthodologique n'est générée par un modèle de langage.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Reference:
    key: str
    citation: str  # forme courte pour le texte : « Auteur (année) »
    apa: str  # référence complète APA 7


_REFS = [
    Reference("agresti2013", "Agresti, 2013",
              "Agresti, A. (2013). *Categorical data analysis* (3e éd.). Wiley."),
    Reference("bartlett1950", "Bartlett, 1950",
              "Bartlett, M. S. (1950). Tests of significance in factor analysis. *British Journal of "
              "Psychology (Statistical Section)*, 3(2), 77-85."),
    Reference("benjamini1995", "Benjamini et Hochberg, 1995",
              "Benjamini, Y., et Hochberg, Y. (1995). Controlling the false discovery rate: A practical and "
              "powerful approach to multiple testing. *Journal of the Royal Statistical Society: Series B*, "
              "57(1), 289-300. https://doi.org/10.1111/j.2517-6161.1995.tb02031.x"),
    Reference("benzecri1979", "Benzécri, 1979",
              "Benzécri, J.-P. (1979). Sur le calcul des taux d'inertie dans l'analyse d'un questionnaire. "
              "*Cahiers de l'Analyse des Données*, 4(3), 377-378."),
    Reference("brant1990", "Brant, 1990",
              "Brant, R. (1990). Assessing proportionality in the proportional odds model for ordinal "
              "logistic regression. *Biometrics*, 46(4), 1171-1178. https://doi.org/10.2307/2532457"),
    Reference("breusch1979", "Breusch et Pagan, 1979",
              "Breusch, T. S., et Pagan, A. R. (1979). A simple test for heteroscedasticity and random "
              "coefficient variation. *Econometrica*, 47(5), 1287-1294. https://doi.org/10.2307/1911963"),
    Reference("cameron1990", "Cameron et Trivedi, 1990",
              "Cameron, A. C., et Trivedi, P. K. (1990). Regression-based tests for overdispersion in the "
              "Poisson model. *Journal of Econometrics*, 46(3), 347-364. "
              "https://doi.org/10.1016/0304-4076(90)90014-K"),
    Reference("cochran1954", "Cochran, 1954",
              "Cochran, W. G. (1954). Some methods for strengthening the common χ² tests. *Biometrics*, "
              "10(4), 417-451. https://doi.org/10.2307/3001616"),
    Reference("cohen1988", "Cohen, 1988",
              "Cohen, J. (1988). *Statistical power analysis for the behavioral sciences* (2e éd.). "
              "Lawrence Erlbaum Associates."),
    Reference("cox1972", "Cox, 1972",
              "Cox, D. R. (1972). Regression models and life-tables. *Journal of the Royal Statistical "
              "Society: Series B*, 34(2), 187-220. https://doi.org/10.1111/j.2517-6161.1972.tb00899.x"),
    Reference("cramer1946", "Cramér, 1946",
              "Cramér, H. (1946). *Mathematical methods of statistics*. Princeton University Press."),
    Reference("cronbach1951", "Cronbach, 1951",
              "Cronbach, L. J. (1951). Coefficient alpha and the internal structure of tests. "
              "*Psychometrika*, 16(3), 297-334. https://doi.org/10.1007/BF02310555"),
    Reference("davidsonpilon2019", "Davidson-Pilon, 2019",
              "Davidson-Pilon, C. (2019). lifelines: Survival analysis in Python. *Journal of Open Source "
              "Software*, 4(40), 1317. https://doi.org/10.21105/joss.01317"),
    Reference("dunn1964", "Dunn, 1964",
              "Dunn, O. J. (1964). Multiple comparisons using rank sums. *Technometrics*, 6(3), 241-252. "
              "https://doi.org/10.1080/00401706.1964.10490181"),
    Reference("fisher1922", "Fisher, 1922",
              "Fisher, R. A. (1922). On the interpretation of χ² from contingency tables, and the "
              "calculation of P. *Journal of the Royal Statistical Society*, 85(1), 87-94. "
              "https://doi.org/10.2307/2340521"),
    Reference("games1976", "Games et Howell, 1976",
              "Games, P. A., et Howell, J. F. (1976). Pairwise multiple comparison procedures with unequal "
              "n's and/or variances: A Monte Carlo study. *Journal of Educational Statistics*, 1(2), "
              "113-125. https://doi.org/10.3102/10769986001002113"),
    Reference("goldstein2011", "Goldstein, 2011",
              "Goldstein, H. (2011). *Multilevel statistical models* (4e éd.). Wiley."),
    Reference("grambsch1994", "Grambsch et Therneau, 1994",
              "Grambsch, P. M., et Therneau, T. M. (1994). Proportional hazards tests and diagnostics based "
              "on weighted residuals. *Biometrika*, 81(3), 515-526. https://doi.org/10.1093/biomet/81.3.515"),
    Reference("greenacre2017", "Greenacre, 2017",
              "Greenacre, M. (2017). *Correspondence analysis in practice* (3e éd.). Chapman and Hall/CRC."),
    Reference("holm1979", "Holm, 1979",
              "Holm, S. (1979). A simple sequentially rejective multiple test procedure. *Scandinavian "
              "Journal of Statistics*, 6(2), 65-70."),
    Reference("horn1965", "Horn, 1965",
              "Horn, J. L. (1965). A rationale and test for the number of factors in factor analysis. "
              "*Psychometrika*, 30(2), 179-185. https://doi.org/10.1007/BF02289447"),
    Reference("hosmer2013", "Hosmer, Lemeshow et Sturdivant, 2013",
              "Hosmer, D. W., Lemeshow, S., et Sturdivant, R. X. (2013). *Applied logistic regression* "
              "(3e éd.). Wiley. https://doi.org/10.1002/9781118548387"),
    Reference("kaiser1974", "Kaiser, 1974",
              "Kaiser, H. F. (1974). An index of factorial simplicity. *Psychometrika*, 39(1), 31-36. "
              "https://doi.org/10.1007/BF02291575"),
    Reference("kaplan1958", "Kaplan et Meier, 1958",
              "Kaplan, E. L., et Meier, P. (1958). Nonparametric estimation from incomplete observations. "
              "*Journal of the American Statistical Association*, 53(282), 457-481. "
              "https://doi.org/10.1080/01621459.1958.10501452"),
    Reference("kleinbaum2010", "Kleinbaum et Klein, 2010",
              "Kleinbaum, D. G., et Klein, M. (2010). *Logistic regression: A self-learning text* "
              "(3e éd.). Springer."),
    Reference("kramer1956", "Kramer, 1956",
              "Kramer, C. Y. (1956). Extension of multiple range tests to group means with unequal numbers "
              "of replications. *Biometrics*, 12(3), 307-310. https://doi.org/10.2307/3001469"),
    Reference("kruskal1952", "Kruskal et Wallis, 1952",
              "Kruskal, W. H., et Wallis, W. A. (1952). Use of ranks in one-criterion variance analysis. "
              "*Journal of the American Statistical Association*, 47(260), 583-621. "
              "https://doi.org/10.1080/01621459.1952.10483441"),
    Reference("larsen2005", "Larsen et Merlo, 2005",
              "Larsen, K., et Merlo, J. (2005). Appropriate assessment of neighborhood effects on individual "
              "health: Integrating random and fixed effects in multilevel logistic regression. *American "
              "Journal of Epidemiology*, 161(1), 81-88. https://doi.org/10.1093/aje/kwi017"),
    Reference("levene1960", "Levene, 1960",
              "Levene, H. (1960). Robust tests for equality of variances. Dans I. Olkin (dir.), "
              "*Contributions to probability and statistics* (p. 278-292). Stanford University Press."),
    Reference("mackinnon1985", "MacKinnon et White, 1985",
              "MacKinnon, J. G., et White, H. (1985). Some heteroskedasticity-consistent covariance matrix "
              "estimators with improved finite sample properties. *Journal of Econometrics*, 29(3), 305-325. "
              "https://doi.org/10.1016/0304-4076(85)90158-7"),
    Reference("mann1947", "Mann et Whitney, 1947",
              "Mann, H. B., et Whitney, D. R. (1947). On a test of whether one of two random variables is "
              "stochastically larger than the other. *The Annals of Mathematical Statistics*, 18(1), 50-60. "
              "https://doi.org/10.1214/aoms/1177730491"),
    Reference("mantel1966", "Mantel, 1966",
              "Mantel, N. (1966). Evaluation of survival data and two new rank order statistics arising in "
              "its consideration. *Cancer Chemotherapy Reports*, 50(3), 163-170."),
    Reference("mccullagh1980", "McCullagh, 1980",
              "McCullagh, P. (1980). Regression models for ordinal data. *Journal of the Royal Statistical "
              "Society: Series B*, 42(2), 109-142. https://doi.org/10.1111/j.2517-6161.1980.tb01109.x"),
    Reference("mcfadden1974", "McFadden, 1974",
              "McFadden, D. (1974). Conditional logit analysis of qualitative choice behavior. Dans "
              "P. Zarembka (dir.), *Frontiers in econometrics* (p. 105-142). Academic Press."),
    Reference("merlo2006", "Merlo et al., 2006",
              "Merlo, J., Chaix, B., Ohlsson, H., Beckman, A., Johnell, K., Hjerpe, P., Råstam, L., et "
              "Larsen, K. (2006). A brief conceptual tutorial of multilevel analysis in social epidemiology: "
              "Using measures of clustering in multilevel logistic regression to investigate contextual "
              "phenomena. *Journal of Epidemiology and Community Health*, 60(4), 290-297. "
              "https://doi.org/10.1136/jech.2004.029454"),
    Reference("nagelkerke1991", "Nagelkerke, 1991",
              "Nagelkerke, N. J. D. (1991). A note on a general definition of the coefficient of "
              "determination. *Biometrika*, 78(3), 691-692. https://doi.org/10.1093/biomet/78.3.691"),
    Reference("nakagawa2013", "Nakagawa et Schielzeth, 2013",
              "Nakagawa, S., et Schielzeth, H. (2013). A general and simple method for obtaining R² from "
              "generalized linear mixed-effects models. *Methods in Ecology and Evolution*, 4(2), 133-142. "
              "https://doi.org/10.1111/j.2041-210x.2012.00261.x"),
    Reference("pinheiro1995", "Pinheiro et Bates, 1995",
              "Pinheiro, J. C., et Bates, D. M. (1995). Approximations to the log-likelihood function in the "
              "nonlinear mixed-effects model. *Journal of Computational and Graphical Statistics*, 4(1), "
              "12-35. https://doi.org/10.1080/10618600.1995.10474663"),
    Reference("priem2022", "Priem, Piwowar et Orr, 2022",
              "Priem, J., Piwowar, H., et Orr, R. (2022). *OpenAlex: A fully-open index of scholarly works, "
              "authors, venues, institutions, and concepts* (arXiv:2205.01833). "
              "https://doi.org/10.48550/arXiv.2205.01833"),
    Reference("ramsey1969", "Ramsey, 1969",
              "Ramsey, J. B. (1969). Tests for specification errors in classical linear least-squares "
              "regression analysis. *Journal of the Royal Statistical Society: Series B*, 31(2), 350-371. "
              "https://doi.org/10.1111/j.2517-6161.1969.tb00796.x"),
    Reference("raudenbush2002", "Raudenbush et Bryk, 2002",
              "Raudenbush, S. W., et Bryk, A. S. (2002). *Hierarchical linear models: Applications and data "
              "analysis methods* (2e éd.). Sage."),
    Reference("rousseeuw1987", "Rousseeuw, 1987",
              "Rousseeuw, P. J. (1987). Silhouettes: A graphical aid to the interpretation and validation of "
              "cluster analysis. *Journal of Computational and Applied Mathematics*, 20, 53-65. "
              "https://doi.org/10.1016/0377-0427(87)90125-7"),
    Reference("rubin1976", "Rubin, 1976",
              "Rubin, D. B. (1976). Inference and missing data. *Biometrika*, 63(3), 581-592. "
              "https://doi.org/10.1093/biomet/63.3.581"),
    Reference("seabold2010", "Seabold et Perktold, 2010",
              "Seabold, S., et Perktold, J. (2010). Statsmodels: Econometric and statistical modeling with "
              "Python. Dans *Proceedings of the 9th Python in Science Conference* (p. 92-96). "
              "https://doi.org/10.25080/Majora-92bf1922-011"),
    Reference("self1987", "Self et Liang, 1987",
              "Self, S. G., et Liang, K.-Y. (1987). Asymptotic properties of maximum likelihood estimators "
              "and likelihood ratio tests under nonstandard conditions. *Journal of the American "
              "Statistical Association*, 82(398), 605-610. https://doi.org/10.1080/01621459.1987.10478472"),
    Reference("shapiro1965", "Shapiro et Wilk, 1965",
              "Shapiro, S. S., et Wilk, M. B. (1965). An analysis of variance test for normality (complete "
              "samples). *Biometrika*, 52(3-4), 591-611. https://doi.org/10.1093/biomet/52.3-4.591"),
    Reference("snijders2012", "Snijders et Bosker, 2012",
              "Snijders, T. A. B., et Bosker, R. J. (2012). *Multilevel analysis: An introduction to basic "
              "and advanced multilevel modeling* (2e éd.). Sage."),
    Reference("somers1962", "Somers, 1962",
              "Somers, R. H. (1962). A new asymmetric measure of association for ordinal variables. "
              "*American Sociological Review*, 27(6), 799-811. https://doi.org/10.2307/2090408"),
    Reference("spearman1904", "Spearman, 1904",
              "Spearman, C. (1904). The proof and measurement of association between two things. *The "
              "American Journal of Psychology*, 15(1), 72-101. https://doi.org/10.2307/1412159"),
    Reference("tomczak2014", "Tomczak et Tomczak, 2014",
              "Tomczak, M., et Tomczak, E. (2014). The need to report effect size estimates revisited. An "
              "overview of some recommended measures of effect size. *Trends in Sport Sciences*, 1(21), "
              "19-25."),
    Reference("tukey1977", "Tukey, 1977",
              "Tukey, J. W. (1977). *Exploratory data analysis*. Addison-Wesley."),
    Reference("virtanen2020", "Virtanen et al., 2020",
              "Virtanen, P., Gommers, R., Oliphant, T. E., et al. (2020). SciPy 1.0: Fundamental algorithms "
              "for scientific computing in Python. *Nature Methods*, 17(3), 261-272. "
              "https://doi.org/10.1038/s41592-019-0686-2"),
    Reference("vonelm2007", "von Elm et al., 2007",
              "von Elm, E., Altman, D. G., Egger, M., Pocock, S. J., Gøtzsche, P. C., et Vandenbroucke, J. P. "
              "(2007). The Strengthening the Reporting of Observational Studies in Epidemiology (STROBE) "
              "statement: Guidelines for reporting observational studies. *The Lancet*, 370(9596), "
              "1453-1457. https://doi.org/10.1016/S0140-6736(07)61602-X"),
    Reference("ward1963", "Ward, 1963",
              "Ward, J. H. (1963). Hierarchical grouping to optimize an objective function. *Journal of the "
              "American Statistical Association*, 58(301), 236-244. "
              "https://doi.org/10.1080/01621459.1963.10500845"),
    Reference("wasserstein2016", "Wasserstein et Lazar, 2016",
              "Wasserstein, R. L., et Lazar, N. A. (2016). The ASA statement on p-values: Context, process, "
              "and purpose. *The American Statistician*, 70(2), 129-133. "
              "https://doi.org/10.1080/00031305.2016.1154108"),
    Reference("welch1947", "Welch, 1947",
              "Welch, B. L. (1947). The generalization of 'Student's' problem when several different "
              "population variances are involved. *Biometrika*, 34(1-2), 28-35. "
              "https://doi.org/10.1093/biomet/34.1-2.28"),
    Reference("wilson1927", "Wilson, 1927",
              "Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. "
              "*Journal of the American Statistical Association*, 22(158), 209-212. "
              "https://doi.org/10.1080/01621459.1927.10502953"),
    Reference("firth1993", "Firth, 1993",
              "Firth, D. (1993). Bias reduction of maximum likelihood estimates. *Biometrika*, 80(1), 27-38. "
              "https://doi.org/10.1093/biomet/80.1.27"),
    Reference("heinze2002", "Heinze et Schemper, 2002",
              "Heinze, G., et Schemper, M. (2002). A solution to the problem of separation in logistic regression. "
              "*Statistics in Medicine*, 21(16), 2409-2419. https://doi.org/10.1002/sim.1047"),
    Reference("harrell1996", "Harrell, Lee et Mark, 1996",
              "Harrell, F. E., Lee, K. L., et Mark, D. B. (1996). Multivariable prognostic models: Issues in "
              "developing models, evaluating assumptions and adequacy, and measuring and reducing errors. "
              "*Statistics in Medicine*, 15(4), 361-387. "
              "https://doi.org/10.1002/(SICI)1097-0258(19960229)15:4<361::AID-SIM168>3.0.CO;2-4"),
    Reference("steyerberg2001", "Steyerberg et al., 2001",
              "Steyerberg, E. W., Harrell, F. E., Borsboom, G. J. J. M., Eijkemans, M. J. C., Vergouwe, Y., et "
              "Habbema, J. D. F. (2001). Internal validation of predictive models: Efficiency of some procedures "
              "for logistic regression analysis. *Journal of Clinical Epidemiology*, 54(8), 774-781. "
              "https://doi.org/10.1016/S0895-4356(01)00341-9"),
    Reference("friedman2001", "Friedman, 2001",
              "Friedman, J. H. (2001). Greedy function approximation: A gradient boosting machine. *The Annals of "
              "Statistics*, 29(5), 1189-1232. https://doi.org/10.1214/aos/1013203451"),
    Reference("breiman2001", "Breiman, 2001",
              "Breiman, L. (2001). Random forests. *Machine Learning*, 45(1), 5-32. "
              "https://doi.org/10.1023/A:1010933404324"),
    Reference("pedregosa2011", "Pedregosa et al., 2011",
              "Pedregosa, F., Varoquaux, G., Gramfort, A., Michel, V., Thirion, B., Grisel, O., et al. (2011). "
              "Scikit-learn: Machine learning in Python. *Journal of Machine Learning Research*, 12, 2825-2830."),
    Reference("harrell2015", "Harrell, 2015",
              "Harrell, F. E. (2015). *Regression modeling strategies: With applications to linear models, logistic "
              "and ordinal regression, and survival analysis* (2e éd.). Springer. "
              "https://doi.org/10.1007/978-3-319-19425-7"),
    Reference("peduzzi1996", "Peduzzi et al., 1996",
              "Peduzzi, P., Concato, J., Kemper, E., Holford, T. R., et Feinstein, A. R. (1996). A simulation "
              "study of the number of events per variable in logistic regression analysis. *Journal of Clinical "
              "Epidemiology*, 49(12), 1373-1379. https://doi.org/10.1016/S0895-4356(96)00236-3"),
    Reference("maas2005", "Maas et Hox, 2005",
              "Maas, C. J. M., et Hox, J. J. (2005). Sufficient sample sizes for multilevel modeling. "
              "*Methodology*, 1(3), 86-92. https://doi.org/10.1027/1614-2241.1.3.86"),
]

REFERENCES: dict[str, Reference] = {r.key: r for r in _REFS}


def cite(key: str) -> str:
    """Forme courte « (Auteur, année) » pour le texte."""
    return f"({REFERENCES[key].citation})"


def bibliography(keys: set[str] | list[str]) -> list[str]:
    """Références APA triées par ordre alphabétique."""
    entries = [REFERENCES[k].apa for k in set(keys) if k in REFERENCES]
    return sorted(entries, key=lambda s: s.lower())
