# Note de recherche — Étape 0 : état de l'art et traduction en signaux

> **Statut :** v0.1, rédigée le 23/09/2026. En attente de validation, aucun code n'est écrit.
> **Objet :** pour chaque approche de référence, ce qui est **prouvé empiriquement**, ce qui **ne l'est pas**, et **comment je la traduis (ou non) en signal** pour le scanner.
> **Document lié :** [`ARCHITECTURE.md`](ARCHITECTURE.md), le plan d'architecture qui s'appuie sur cette note.

---

## 0. Comment lire cette note

### 0.1 Niveaux de preuve

| Niveau | Signification |
|---|---|
| **A** | Effet publié dans des revues à comité de lecture, **répliqué** par des équipes indépendantes, **hors échantillon** (autres périodes et autres pays). |
| **B** | Publié et évalué par les pairs, mais la réplication est partielle, l'effet s'est affaibli, ou il se concentre dans des segments peu investissables (micro-caps). |
| **C** | Working paper, échantillon court, ou données non accessibles à un particulier. |
| **D** | Pratique de gérant, livre ou déclaration publique **sans validation académique vérifiable**. |
| **X** | Les preuves disponibles vont **contre** l'efficacité revendiquée. |

### 0.2 Statut dans le scanner

| Statut | Signification |
|---|---|
| **CŒUR** | Signal candidat au score. Il n'entre dans le score qu'après avoir passé **notre** backtest hors échantillon (Module 9). |
| **OBS** | En observation : calculé, archivé, suivi en paper trading, **pondération nulle** tant qu'il n'est pas validé. |
| **FILTRE / PÉNALITÉ** | Sert à exclure ou à pénaliser, pas à classer. |
| **CONTEXTE** | Information affichée dans le rapport (thèse, risques), sans effet sur le score. |
| **REJETÉ** | Non retenu ; la raison est donnée. |

### 0.3 Règles d'honnêteté appliquées ici

- Les chiffres de performance cités sont **ceux publiés par les auteurs** ; je ne les ai pas reproduits. Notre implémentation fera **moins bien** : décroissance post-publication, coûts réels, univers différent (voir §1).
- Les références académiques classiques sont citées par auteur, année et revue (bibliographie complète en §12). Celles dont j'ai **revérifié en ligne** les détails le 23/09/2026 portent le signe ✔.
- Pour les gérants (Renaissance, Two Sigma, Tiger…), je distingue ce qui est **publiquement documenté** de ce qui relève de la **légende** ou du marketing. Sur plusieurs d'entre eux, on sait peu de choses, et je le dis.

---

## 1. Méta-enseignements, avant toute approche

Ces constats conditionnent tout le reste du projet.

### 1.1 Beaucoup d'anomalies publiées ne survivent pas

- **Hou, Xue & Zhang (2020)** répliquent plus de 450 anomalies. Une **majorité** n'est plus significative quand on neutralise le poids des micro-caps (pondération par capitalisation, points de coupure NYSE). → **Preuve A** que beaucoup d'« alphas » publiés sont des artefacts de micro-caps.
- **Jensen, Kelly & Pedersen (2023)** ✔ arrivent à une conclusion plus optimiste avec une approche bayésienne : la plupart des facteurs, regroupés en **13 thèmes**, se répliquent, y compris dans **93 pays**. Leurs rendements de facteurs sont **téléchargeables gratuitement** sur [jkpfactors.com](https://jkpfactors.com/).
- **Chen & Zimmermann (2022)** ✔ reproduisent 319 prédicteurs avec du code ouvert ([openassetpricing.com](https://www.openassetpricing.com/)). Les signaux qui étaient clairement significatifs dans les articles d'origine le restent dans leur réplication.

**Ce que j'en retiens :** je ne retiens que des familles de signaux qui se répliquent dans **JKP et/ou Chen-Zimmermann**, **hors micro-caps**, et **dans la région concernée** (US, Europe, émergents). La base JKP sert de **prior externe gratuit** pour décider si un facteur mérite d'être testé en Europe ou dans les émergents avant même d'avoir nos propres données.

### 1.2 Les anomalies décroissent après publication

- **McLean & Pontiff (2016)** : les rendements des anomalies sont environ **26 % plus faibles hors échantillon** et environ **58 % plus faibles après publication**. → **Preuve A**.

**Ce que j'en retiens :** j'anticipe des rendements attendus **divisés par environ deux** par rapport aux articles, et je dimensionne les attentes et les coûts en conséquence.

### 1.3 Le data mining est la norme, il faut le corriger

- **Harvey, Liu & Zhu (2016)** : avec des centaines de facteurs testés, le seuil de t-statistique pour un **nouveau** facteur devrait être d'environ **3,0**, pas 2,0.
- **Bailey & López de Prado (2014)** : le *Deflated Sharpe Ratio* corrige le Sharpe du nombre d'essais et de la non-normalité.
- **Arnott, Harvey & Markowitz (2019)** proposent un protocole de backtest : hypothèse économique préalable, journal de tous les essais, pas de réutilisation de l'échantillon de test.

**Ce que j'en retiens :**
- Un signal **issu de la littérature** et **pré-enregistré** dans `config/signals.yaml` avec son signe attendu doit simplement avoir le **bon signe** et un t ≥ 2 hors échantillon.
- Un signal **inventé par nous** doit atteindre t ≥ 3 hors échantillon et un Deflated Sharpe positif.
- Chaque backtest lancé est **journalisé**, y compris ceux qui échouent, pour pouvoir compter le nombre d'essais.

### 1.4 Les coûts de transaction tuent les signaux à fort turnover

- **Novy-Marx & Velikov (2016)** : les anomalies à fort turnover (retournement court terme, certaines variantes de momentum mensuel) perdent l'essentiel de leur rentabilité après coûts. Les anomalies à faible turnover (value, rentabilité, investissement) survivent.
- **Chez nous**, les coûts sont ceux d'un particulier : courtage, spread, et **taxe sur les transactions financières française portée de 0,3 % à 0,4 % depuis le 1er avril 2025** ✔ sur les achats d'actions françaises de plus d'un milliard d'euros de capitalisation ([LégiFiscal](https://www.legifiscal.fr/actualites-fiscales/4142-taxe-transactions-financieres-04-1er-avril.html)). S'y ajoutent l'ITF italienne, la taxe espagnole et le stamp duty britannique, à paramétrer.

**Ce que j'en retiens :** le coût est un **paramètre de premier ordre** du backtest (fichier `costs.yaml`), différencié par pays, par tranche de liquidité et par type d'enveloppe. Les signaux à fort turnover sont **OBS** par défaut.

### 1.5 Combiner beaucoup de signaux faibles, simplement

- **Grinold (1989)**, « loi fondamentale de la gestion active » : IR ≈ IC × √(nombre de paris indépendants). Un IC de 0,02 à 0,05 est **normal et exploitable** si l'on a beaucoup de paris peu corrélés.
- **DeMiguel, Garlappi & Uppal (2009)** : la pondération naïve 1/N bat la plupart des optimisations hors échantillon, car l'erreur d'estimation domine.

**Ce que j'en retiens :** au sein d'un module, les signaux validés sont **équipondérés** par défaut. On ne s'écarte de l'équipondération que si le gain hors échantillon est significatif, et par **rétrécissement** vers 1/N, jamais par optimisation libre.

### 1.6 Biais du survivant et de délistage

- **Brown, Goetzmann, Ibbotson & Ross (1992)** et **Shumway (1997)** : ignorer les sociétés disparues ou le rendement de délistage **gonfle** les performances, surtout pour les stratégies value et petites capitalisations.

**Ce que j'en retiens :** le backtest utilise un **univers défini par des règles à chaque date** (top N par capitalisation et par liquidité), calculé sur une base de prix qui **inclut les délistés**. EODHD revendique 26 000+ tickers US depuis 2000, délistés compris ✔ ; voir `ARCHITECTURE.md` §3. Sans cette base, les résultats sont marqués **« biaisés à la hausse »**.

---

## 2. Factor investing

### 2.1 Fama-French : du modèle à 3 au modèle à 5 facteurs

**Prouvé :**
- **Value (HML)** et **taille (SMB)** : Fama & French (1993). Value : **A** au niveau international (Fama & French 2012, 2017). Taille : **B, voire faible** ; la prime est concentrée dans les micro-caps et en janvier, et elle réapparaît surtout une fois contrôlée la qualité (« junk ») : Asness et al. (2018).
- **Rentabilité (RMW)** et **investissement (CMA)** : Fama & French (2015). **A**, et robustes à l'international (Fama & French 2017).

**Non prouvé ou débattu :**
- La value a connu une longue sous-performance entre 2007 et 2020. Arnott, Harvey, Kalesnik & Linnainmaa (2021) l'attribuent surtout à la **compression des multiples** et aux actifs intangibles non comptabilisés, pas à une disparition structurelle. Le débat reste ouvert.
- Le modèle à 5 facteurs **n'explique pas le momentum**, que Fama et French laissent de côté.

**Traduction :**
- **Pas de signal « taille »** : la capitalisation sert de **contrôle** (neutralisation) et de filtre de liquidité.
- **Value multi-mesures** plutôt que le seul book-to-market, qui est pénalisé par les intangibles : EBIT/EV, FCF/EV et B/M.
- **Rentabilité** (voir §5) et **investissement**, c'est-à-dire la croissance des actifs, avec un **signe négatif** (Cooper, Gulen & Schill 2008).

### 2.2 AQR : value, momentum, qualité, faible risque

| Travaux | Prouvé | Niveau |
|---|---|---|
| *Value and Momentum Everywhere* (Asness, Moskowitz & Pedersen 2013) | Value et momentum présents dans 8 marchés et classes d'actifs ; **corrélation négative entre eux**, donc la combinaison est plus robuste que chacun seul. | A |
| *Fact, Fiction and Momentum Investing* (Asness, Frazzini, Israel & Moskowitz 2014) | Démonte des idées reçues : le momentum existe aussi dans les grandes capitalisations, n'est pas qu'un effet de la jambe short, survit aux coûts raisonnables et reste robuste sur longue période. | A |
| *Quality Minus Junk* (Asness, Frazzini & Pedersen 2019) | La « qualité », définie comme rentabilité, croissance **de la rentabilité**, sécurité (faible levier, faible volatilité des résultats) et distribution, a une prime ajustée du risque positive, dans 24 pays. | A |
| *Betting Against Beta* (Frazzini & Pedersen 2014) | Les actions à faible bêta ont un alpha positif, cohérent avec les contraintes de levier des investisseurs. | A– (sensible à la construction) |

**Non prouvé ou fragile :**
- Le momentum subit des **krachs** violents lors des rebonds de marché après une forte baisse (Daniel & Moskowitz 2016). Mettre la volatilité à l'échelle réduit ce risque : Barroso & Santa-Clara (2015).
- Le *timing* des facteurs selon leur valorisation est **difficile et peu fiable** (Asness, Chandra, Ilmanen & Israel 2017). Cela plaide contre une rotation agressive des facteurs selon le régime (voir §4).

**Traduction :**
- Le livre moyen terme (3 à 12 mois) repose sur **value + momentum + qualité + faible risque**, équipondérés entre familles.
- Le momentum est **mis à l'échelle de sa volatilité**, et une alerte « risque de krach momentum » est émise quand le marché rebondit fortement après un drawdown important (conditions de Daniel & Moskowitz).
- La qualité suit la définition QMJ, ce qui répond à la demande « qualité » du Module 2.

### 2.3 Jegadeesh & Titman : le momentum

**Prouvé :**
- Acheter les gagnants et vendre les perdants sur 3 à 12 mois rapporte environ **1 % par mois** sur le marché US entre 1965 et 1989 (Jegadeesh & Titman 1993). Le résultat est confirmé hors échantillon sur la décennie suivante (Jegadeesh & Titman 2001). → **A**.
- L'effet est présent en **Europe** (Rouwenhorst 1998), dans la plupart des pays **sauf le Japon** (Fama & French 2012), et plus faible et bruité dans les **émergents** (Rouwenhorst 1999).
- **Variantes robustes :**
  - **Momentum résiduel**, calculé sur les résidus d'un modèle factoriel : il est moins exposé aux krachs (Blitz, Huij & Martens 2011) → **B+**.
  - **Momentum sectoriel** (Moskowitz & Grinblatt 1999) → **A–**.
  - **Proximité du plus haut sur 52 semaines** (George & Hwang 2004) → **B+**.

**Traduction :**
- Momentum 12-1 mois (on saute le dernier mois pour éviter le retournement court terme) et momentum 6-1 mois : **CŒUR**.
- Momentum résiduel : **CŒUR**.
- Force relative par rapport au secteur et à l'indice : **CŒUR**. C'est une version sectorielle du momentum.
- Momentum sectoriel : **CŒUR** pour le livre swing.
- Proximité du plus haut 52 semaines : **CŒUR** (swing). Elle fait le lien avec O'Neil et Minervini (§6).

---

## 3. Quant systématique : ce qu'on sait des grandes maisons

> Ces firmes publient très peu. Ce qui suit se limite à ce qui est **documenté publiquement**. Tout le reste relève de la spéculation, et je ne l'utilise pas.

### 3.1 Renaissance Technologies

**Documenté :**
- La meilleure source publique est le livre de Zuckerman (2019). Selon ce livre, le fonds **Medallion** a rapporté environ **66 % par an avant frais** et **39 % après frais** entre 1988 et 2018 ✔ ([InvestmentNews](https://www.investmentnews.com/guides/what-the-man-who-solved-the-market-teaches-about-quantitative-investing/265700)).
- Les ingrédients rapportés :
  - un très grand nombre de **signaux faibles** combinés ;
  - des horizons **courts** ;
  - un soin extrême apporté au **nettoyage des données** ;
  - une modélisation fine des **coûts et de l'impact de marché** ;
  - du levier ;
  - un modèle unique et intégré plutôt qu'une juxtaposition de stratégies.
- L'idée qu'il suffit d'avoir raison un peu plus d'une fois sur deux, sur un très grand nombre de paris, est cohérente avec la loi de Grinold (§1.5).

**Non transférable :** l'horizon (intraday ou jours), l'infrastructure d'exécution, les données propriétaires et le levier. Les fonds ouverts aux investisseurs extérieurs (RIEF et autres) ont d'ailleurs des performances **sans commune mesure** avec Medallion. Les déclarations 13F de Renaissance ne reflètent donc **pas** Medallion.

**Traduction :** je retiens la **philosophie**, pas des signaux :
1. Combiner beaucoup de signaux faibles et peu corrélés.
2. Une qualité des données obsessionnelle, c'est-à-dire le Module 11 de contrôles qualité.
3. Des coûts modélisés dès le premier jour.
4. **Exclure les 13F de Renaissance, Two Sigma et D.E. Shaw** du signal « smart money » : ce sont des portefeuilles quantitatifs très diversifiés, dont les positions ne portent pas de conviction individuelle.

### 3.2 Two Sigma

**Documenté :** une culture « data science », une forte ingestion de données alternatives, et un cadre public de décomposition factorielle, le *Two Sigma Factor Lens*, qui explique les portefeuilles par un petit nombre de facteurs macro et de style.
**Non documenté :** leurs signaux eux-mêmes.
**Traduction :** Module 10. Le panier d'idées du jour est **décomposé en expositions factorielles** (marché, taille, value, momentum, qualité, faible volatilité, secteurs, pays, devises). Cela évite qu'un « top 20 » ne soit en réalité un seul pari déguisé, par exemple « long tech / long momentum ».

### 3.3 D.E. Shaw

**Documenté :** firme pionnière du calcul appliqué à la finance (fondée en 1988), qui combine des stratégies **systématiques** et **discrétionnaires**.
**Non documenté :** le détail des modèles ; les informations publiques sont très maigres.
**Traduction :** seulement l'architecture **hybride** que l'on reproduit ici : un filtre quantitatif systématique en amont, puis une analyse qualitative (LLM plus lecture humaine) sur une liste réduite.

### 3.4 Man AHL : suivi de tendance

**Prouvé :**
- Le **momentum de série temporelle**, c'est-à-dire le suivi de tendance d'un actif par rapport à son propre passé, est robuste sur 58 contrats à terme (Moskowitz, Ooi & Pedersen 2012) et sur **plus d'un siècle** (Hurst, Ooi & Pedersen 2017). → **A pour les futures diversifiés**.
- Ses propriétés de « **crisis alpha** » sont documentées par des chercheurs de Man Group (Harvey et al. 2019).
- Sur les **indices actions**, une règle de tendance simple (prix contre moyenne mobile 10 mois) réduit les drawdowns sans détruire le rendement (Faber 2007). → **B**.

**Non prouvé :** le suivi de tendance **sur actions individuelles**, comme filtre de sélection, est beaucoup moins documenté que sur futures.

**Traduction :**
- **Overlay de risque au niveau du marché** : quand l'indice de référence passe sous sa tendance longue, le rapport recommande de **réduire l'exposition nette**, via le cash, un ETF inverse ou des puts selon le compte. C'est la façon la plus réaliste d'avoir une jambe « short » avec un PEA et un CTO (voir `ARCHITECTURE.md` §1).
- Le filtre de tendance sur actions individuelles est en **OBS** pour le livre swing (voir §6.2).

---

## 4. Macro

### 4.1 Bridgewater : régimes et cycle de la dette

**Documenté :**
- Le cadre « All Weather » découpe l'environnement en **4 régimes** : croissance en hausse ou en baisse, croissance croisée avec inflation en hausse ou en baisse. Chaque classe d'actifs est sensible à un régime ; la construction en **parité de risque** équilibre ces sensibilités.
- Dalio (2018) décrit le **cycle de la dette** (désendettement « beau » ou « laid »).
- Des sensibilités empiriques des classes d'actifs à la croissance et à l'inflation sont documentées par Ilmanen, Maloney & Ross (2014) : les actions font le mieux en croissance haussière avec une inflation baissière. → **B**.

**Non prouvé :** qu'un classement de régime en temps réel permette de **timer les facteurs actions** dans le cross-section. Les preuves disponibles sont décevantes (Asness et al. 2017), et les régimes sont connus **avec retard**, car les données macro sont publiées puis révisées.

**Traduction (Module 6) :**
- Un **régime croissance × inflation** calculé **en temps réel**, avec les **millésimes ALFRED** (FRED archivé) pour que le backtest n'utilise que les données macro telles qu'elles étaient publiées à la date.
- Usage par défaut : **CONTEXTE + gestion du risque**, c'est-à-dire l'exposition nette et le niveau de couverture.
- L'ajustement des pondérations de facteurs par régime reste **OBS** : il n'est activé que s'il bat l'équipondération hors échantillon **avec** correction pour essais multiples.

### 4.2 Druckenmiller : liquidité et banques centrales

**Documenté :**
- On lui attribue largement la formule selon laquelle ce ne sont pas les résultats qui font le marché dans son ensemble, mais la **Fed et la liquidité**. La citation est rapportée comme issue de sa conférence au Lost Tree Club (2015), dont la transcription n'est pas officielle ([source secondaire](https://aryadeniz.substack.com/p/stanley-druckenmillers-lost-tree)).
- Côté preuves académiques voisines :
  - la **dérive pré-FOMC** : les actions US montaient en moyenne dans les 24 h précédant les annonces du FOMC (Lucca & Moench 2015). Cet effet s'est **fortement affaibli** après sa publication (Kurov, Wolfe & Gilbert 2021) ;
  - les communications des banques centrales font bouger les taux au-delà de la décision elle-même (Gürkaynak, Sack & Swanson 2005).

**Non prouvé :** les indicateurs populaires de « liquidité nette » (bilan de la Fed, moins le reverse repo, moins le compte du Trésor) n'ont **pas de validation hors échantillon** rigoureuse comme signal de timing. Ce sont des corrélations de la période des QE. → **D**.

**Traduction :**
- **CONTEXTE** : calendrier et suivi des banques centrales (Fed, BCE, BoE, BoJ) ; indicateurs de liquidité affichés.
- Les discours des banquiers centraux sont analysés par le LLM (Module 5) en ton « hawkish/dovish » et en surprise par rapport aux attentes.
- Aucun score de timing fondé sur la « liquidité nette » tant qu'il n'est pas validé (**OBS**).

### 4.3 Soros : réflexivité

**Documenté :** la théorie de la **réflexivité** (Soros 1987 ; Soros 2013) : les perceptions des acteurs modifient les fondamentaux, qui renforcent ensuite les perceptions, d'où les cycles d'expansion et d'effondrement. C'est un cadre conceptuel, pas un modèle testable en l'état. → **D**.

**Traduction :** **CONTEXTE** dans le Module 7 (scénarios). Le LLM doit identifier explicitement les **boucles auto-renforçantes** d'une thèse. Exemple : cours en hausse → augmentation de capital facile → croissance externe → hausse des BPA → cours en hausse. Il doit aussi identifier ce qui **casserait la boucle**. Cela alimente l'analyse contradictoire, pas le score.

### 4.4 Indicateurs macro avec un vrai support empirique

| Indicateur | Preuve | Usage |
|---|---|---|
| Pente de la courbe des taux (10 ans - 3 mois) | Prédit les récessions US (Estrella & Mishkin 1998) → **A** | Régime et risque |
| Spreads de crédit, *excess bond premium* | Prédit l'activité (Gilchrist & Zakrajšek 2012) → **A–** ; l'EBP est publié gratuitement par la Fed | Régime et risque |
| Incertitude de politique économique (indice EPU) | Mesure validée par Baker, Bloom & Davis (2016), données gratuites | Contexte, filtre sur les événements politiques |
| PMI | Les PMI S&P Global sont propriétaires ; l'ISM a été **retiré de FRED**. Alternatives gratuites : OECD CLI, enquêtes des Fed régionales, communiqués de presse (titres). | Régime (croissance) |
| VIX, dollar, pétrole | Variables d'état standard | Contexte et risque |

---

## 5. Fondamental et value

### 5.1 Buffett et Berkshire Hathaway

**Prouvé :** Frazzini, Kabiller & Pedersen (2018) ✔ montrent que Berkshire affiche un **Sharpe de 0,79**. Son alpha devient **non significatif** une fois contrôlés les facteurs **BAB** (faible risque) et **QMJ** (qualité), avec un levier moyen d'environ **1,7 pour 1** financé par le float de l'assurance (1,6 dans la version working paper). En résumé : des actions **bon marché, sûres et de qualité**, avec un levier bon marché. → **A** (explication factorielle).

**Non prouvé ou non transférable :** l'accès aux transactions privées, les conditions de financement du float, et la taille. L'appréciation qualitative du management et du « moat » n'est pas mesurable directement.

**Traduction :**
- Le **livre long terme (5 ans et plus)** = qualité (QMJ) + faible risque + valorisation raisonnable. C'est une version « Buffett factorisée ».
- Le moat est approché par des **proxys mesurables** : stabilité du ROIC et des marges sur 5 à 10 ans, rentabilité brute élevée et faible intensité capitalistique.
- Le 13F de Berkshire est suivi (Module 4), en tenant compte du retard de publication.

### 5.2 Greenblatt : la Magic Formula

**Documenté :** classement combiné du **rendement sur capital** (EBIT / (BFR + immobilisations nettes)) et du **rendement bénéficiaire** (EBIT / EV) (Greenblatt 2005). La performance revendiquée dans le livre est un **backtest de l'auteur**, sans publication évaluée par les pairs. → **D** pour la formule telle quelle.

**Tests indépendants :**
- Gray & Carlisle (2012) trouvent qu'**EBIT/EV seul fait au moins aussi bien** que la formule combinée.
- Loughran & Wellman (2011) valident le **multiple d'entreprise** (EV/EBITDA) comme prédicteur → **B+**.

**Traduction :** pas de Magic Formula en tant que telle. Ses deux ingrédients sont intégrés séparément, EBIT/EV dans la **value** et le rendement sur capital dans la **qualité**, là où l'équipondération des familles les combine de toute façon.

### 5.3 Piotroski : le F-Score

**Prouvé :**
- Neuf critères binaires (rentabilité, levier et liquidité, efficacité opérationnelle). Parmi les actions à fort book-to-market, la stratégie « long F élevé / short F faible » rapporte environ **23 % par an** entre 1976 et 1996 selon l'auteur (Piotroski 2000).
- L'auteur note lui-même que l'effet se concentre dans les **petites capitalisations peu suivies par les analystes**. → **B**.

**Non prouvé :** la robustesse dans les grandes capitalisations liquides et sur les périodes récentes est moindre. Le F-score recoupe largement les composantes rentabilité et accruals de la qualité.

**Traduction :** F-score **CŒUR dans la qualité** (santé financière) et **FILTRE** dans le livre value : on n'achète pas une value avec F ≤ 3, c'est-à-dire une « value trap » probable. Il est **non applicable aux financières** (banques, assurances), qui sont exclues de ce calcul.

### 5.4 Altman : le Z-Score

**Prouvé :**
- Prédiction de faillite à 1 ou 2 ans (Altman 1968), estimée sur un petit échantillon d'industriels américains.
- Variante **Z''** pour les sociétés non industrielles et les émergents (Altman 2005).
- En **rendement** : les sociétés en détresse **sous-performent**. C'est l'« anomalie de détresse » (Dichev 1998 ; Campbell, Hilscher & Szilagyi 2008) → **A–**.

**Non prouvé :** les coefficients de 1968 ne sont pas optimaux aujourd'hui, et l'indicateur n'a pas de sens pour les financières.

**Traduction :** **PÉNALITÉ** pour les longs en zone de détresse (Z < 1,81, ou Z'' < 1,1). C'est aussi un **candidat short** (livre moyen terme) lorsqu'il se combine à un momentum négatif. Les financières sont exclues.

### 5.5 Beneish : le M-Score

**Prouvé :**
- Modèle à 8 variables de **détection de manipulation comptable** (Beneish 1999).
- Beneish, Lee & Nichols (2013) montrent que les sociétés à forte probabilité de manipulation ont des **rendements futurs plus faibles**, au-delà des accruals et d'autres facteurs connus → **B+**.

**Non prouvé :** le taux de faux positifs est élevé. Le modèle n'est pas un verdict : c'est un signal d'enquête.

**Traduction :** **PÉNALITÉ** sur le score composite quand le M-score dépasse -1,78 (version à 8 variables), avec une **alerte explicite** dans le rapport. Il n'est jamais utilisé seul pour un short. Les financières sont exclues.

### 5.6 Rentabilité, accruals, émissions : les « briques » robustes

| Signal | Référence | Preuve | Traduction |
|---|---|---|---|
| Rentabilité brute (GP/Actifs) | Novy-Marx (2013) | A | CŒUR qualité |
| Rentabilité opérationnelle fondée sur le cash | Ball, Gerakos, Linnainmaa & Nikolaev (2016) | A– | CŒUR qualité |
| Accruals (signe négatif) | Sloan (1996) | A (affaibli dans les données récentes) | CŒUR qualité, sous forme de conversion résultat → cash-flow |
| Émissions nettes d'actions (négatif) / rachats (positif) | Pontiff & Woodgate (2008) ; Daniel & Titman (2006) | A | CŒUR |
| Croissance des actifs (négatif) | Cooper, Gulen & Schill (2008) | A | CŒUR |
| **Croissance passée du CA ou du BPA** | Lakonishok, Shleifer & Vishny (1994) | **X comme signal positif** : les « glamour stocks » à forte croissance passée sous-performent | **Pas de score brut « croissance »**. On utilise la **croissance de la rentabilité** (QMJ), les **surprises** (§7.1) et les **révisions** (§7.2). |

> **Point important pour la demande « Croissance : CA, BPA, révisions » du Module 2 :** la croissance *passée* du CA ou du BPA n'est **pas** un bon prédicteur. Elle est déjà dans les prix, voire surpayée. Ce qui prédit, ce sont les **surprises** et les **révisions**. Je remplace donc la croissance brute par ces mesures. La croissance brute reste **affichée** dans le rapport comme information descriptive.

### 5.7 Tiger Management et les « Tiger Cubs »

**Documenté :**
- Julian Robertson : long/short **fondamental**, recherche approfondie, acheter les meilleures sociétés d'un secteur et vendre les plus faibles.
- Les « cubs » (Lone Pine, Viking, Maverick, Tiger Global, Coatue…) ont prolongé ce style, souvent orienté croissance.
- Leçon de risque documentée : le fonds phare de **Tiger Global a perdu environ 55 % en 2022** selon la presse financière ✔ ([CNBC](https://www.cnbc.com/2022/06/02/tiger-global-drops-14percent-in-may-during-the-tech-sell-off-pushing-hedge-funds-2022-losses-to-over-50percent.html)). Les causes rapportées : concentration sur des valeurs de croissance à duration longue, exposition factorielle non couverte et crowding.

**Non prouvé :** qu'un particulier puisse capter leur alpha via les 13F (voir §7.6).

**Traduction :**
- **Paires intra-sectorielles** dans le livre long/short : meilleur contre pire score **dans le même secteur**, ce qui neutralise le facteur secteur.
- Les cubs figurent dans la **liste de fonds suivis** en 13F.
- **Garde-fou factoriel** (Module 10) : on alerte si le panier est concentré sur un facteur, par exemple croissance ou duration longue.

### 5.8 Pershing Square

**Documenté :**
- Portefeuille **très concentré** (une dizaine de lignes), activisme.
- Critères publics : sociétés **simples, prévisibles, génératrices de free cash-flow, avec de fortes barrières à l'entrée** et un bilan solide.
- Couvertures asymétriques ponctuelles, comme le gain sur CDS en mars 2020, largement rapporté par la presse.

**Non prouvé :** l'activisme crée de la valeur en moyenne (Brav, Jiang, Partnoy & Thomas 2008), mais un particulier ne peut **pas** le répliquer. Le 13F de Pershing arrive avec retard.

**Traduction :**
- Les critères « simple, prévisible, FCF » sont traduits en **proxys** pour le livre long terme : faible volatilité du FCF, marge stable, ROIC élevé et levier modéré.
- Le 13F de Pershing Square est suivi.
- L'**idée de couverture convexe** est reprise dans le Module 10 : proposer un put indiciel ou une réduction d'exposition quand le régime se dégrade.

---

## 6. Croissance et momentum discrétionnaires

### 6.1 O'Neil : CAN SLIM

**Documenté (O'Neil 2009) :**
- **C** : forte croissance du BPA trimestriel.
- **A** : croissance annuelle.
- **N** : nouveau produit, nouveau management, **nouveaux plus hauts**.
- **S** : offre et demande (volume).
- **L** : leader, avec une force relative élevée.
- **I** : soutien institutionnel.
- **M** : direction du marché.

**Non prouvé :** je ne connais pas de validation académique évaluée par les pairs du **système complet**. Les performances revendiquées viennent de l'auteur et de screens commerciaux → **D** pour le système.

**En revanche, presque chaque lettre correspond à une anomalie documentée :**

| Lettre | Anomalie documentée | Preuve |
|---|---|---|
| C, A | Surprises de résultats, PEAD (§7.1) ; momentum des bénéfices (Chan, Jegadeesh & Lakonishok 1996) | A/B |
| N | Proximité du plus haut 52 semaines (George & Hwang 2004) | B+ |
| S | Prime de volume anormal (Gervais, Kaniel & Mingelgrin 2001) | B |
| L | Momentum (§2.3) | A |
| I | Variation de la détention institutionnelle (Gompers & Metrick 2001) | B |
| M | Filtre de tendance du marché (Faber 2007) | B |

**Traduction :** le **livre swing (1 à 8 semaines)** est un « CAN SLIM factorisé ». Chaque composante est un signal séparé, validé séparément, puis combiné. La combinaison entière est testée comme un tout, sans reprendre les seuils magiques du livre.

### 6.2 Minervini : Trend Template et VCP

**Documenté :**
- Le **Trend Template** ✔ ([ChartMill](https://www.chartmill.com/documentation/stock-screener/technical-analysis-trading-strategies/496-Mark-Minervini-Trend-Template-A-Step-by-Step-Guide-for-Beginners)) :
  - cours au-dessus des moyennes mobiles 150 et 200 jours ;
  - MM150 au-dessus de la MM200 ;
  - MM200 orientée à la hausse depuis au moins 1 mois ;
  - MM50 au-dessus des MM150 et MM200, et cours au-dessus de la MM50 ;
  - cours au moins 25 à 30 % au-dessus du plus bas 52 semaines ;
  - cours à moins de 25 % du plus haut 52 semaines ;
  - force relative d'au moins 70.
- Le **VCP** (*volatility contraction pattern*), lui, est un motif graphique discrétionnaire.
- Les performances revendiquées (championnat américain de trading) ne constituent **pas** une preuve académique → **D**.

**Traduction :**
- Trend Template : **FILTRE booléen en OBS** pour le livre swing. Il est backtesté contre et avec le momentum pur ; s'il n'apporte rien au-delà du momentum 12-1 et du plus haut 52 semaines, il reste simple information.
- VCP : **OBS**. Proxy mesurable : contraction de l'ATR et de l'amplitude sur 3 à 6 semaines, avec baisse du volume.

---

## 7. Anomalies documentées : événements et flux

### 7.1 Post-earnings announcement drift (PEAD)

**Prouvé :**
- Les cours continuent de dériver dans le sens de la surprise de résultats pendant 60 jours et plus (Ball & Brown 1968 ; Bernard & Thomas 1989) → historiquement **A**.
- Une mesure par les **prix**, le rendement anormal sur 3 jours autour de l'annonce (EAR), porte un drift au moins aussi fort (Brandt, Kishore, Santa-Clara & Venkatachalam 2008 ; working paper).
- La dérive est plus forte quand l'attention est faible : annonces du vendredi (DellaVigna & Pollet 2009), jours chargés en annonces (Hirshleifer, Lim & Teoh 2009).

**Affaiblissement documenté :** selon **Martineau (2022)** ✔, le PEAD a **disparu pour les grandes capitalisations US depuis environ 2006**, et plus récemment pour les micro-caps. → Le statut actuel est **B–, voire X pour les large caps US**. Il reste possiblement présent en Europe et dans les petites et moyennes capitalisations, **à vérifier**.

**Traduction :**
- SUE (surprise standardisée, calculée **sans consensus** avec un modèle de marche aléatoire saisonnière) et EAR (rendement anormal sur 3 jours) : **CŒUR candidat** pour le livre swing.
- Leur survie dans **notre** univers n'est pas acquise, compte tenu de Martineau (2022). Ils sont **backtestés séparément par région et par taille**, et l'on accepte le verdict.
- Les dates d'annonce US sont **point-in-time** grâce aux dépôts 8-K (item 2.02) sur EDGAR.

### 7.2 Révisions des analystes

**Prouvé :**
- Les révisions de prévisions de BPA prédisent les rendements (Givoly & Lakonishok 1979 ; Stickel 1991 ; Chan, Jegadeesh & Lakonishok 1996) → **A–**.

**Problème de données :** l'**historique point-in-time** des consensus (I/B/E/S) coûte des milliers d'euros par an, hors budget. Les sources abordables (yfinance, EODHD, Finnhub) donnent un **instantané** : consensus actuel et variation sur 7, 30, 60 et 90 jours. Elles ne donnent pas d'historique exploitable.

**Traduction :** les révisions entrent en **OBS dès le jour 1**. On archive **chaque jour** l'instantané des consensus, ce qui construit notre **propre historique point-in-time**. Le signal pourra être validé en **forward**, après environ 12 à 18 mois d'archive. D'ici là, il est **affiché** sans être pondéré.

### 7.3 Transactions d'initiés

**Prouvé :**
- Les **achats** d'initiés sont informatifs ; les **ventes** beaucoup moins, car elles sont souvent motivées par la liquidité ou la diversification (Seyhun 1986 ; Lakonishok & Lee 2001) → **A**.
- Il faut distinguer les initiés « **routiniers** », qui achètent chaque année au même mois et dont les transactions ne sont pas informatives, des « **opportunistes** », qui le sont (Cohen, Malloy & Pomorski 2012) → **A–**.
- **Achats groupés** : les initiés d'une même société achètent souvent le même jour, et les achats groupés sont suivis de **rendements anormaux supérieurs à 2 % le mois suivant** (Alldredge & Blank 2019 ✔).
- En Europe : le Royaume-Uni est documenté (Fidrmuc, Goergen & Renneboog 2006), avec des effets similaires.

**Données :**
- **US** : les *Insider Transactions Data Sets* de la SEC ✔ ([sec.gov](https://www.sec.gov/about/dera_form-345)), gratuits, structurés, mis à jour trimestriellement. Pour le quotidien, les Form 4 sont lus directement sur EDGAR. Seul le **code transaction « P »** (achat sur le marché) compte : les codes M (exercice d'options), A (attribution) et F (retenue fiscale) sont ignorés.
- **France** : déclarations au titre de l'article 19 de MAR, publiées par l'AMF dans la **BDIF** ✔ ([bdif.amf-france.org](https://bdif.amf-france.org/)). Il n'existe pas d'API structurée dédiée identifiée à ce jour : il faudra un **parseur des publications**, à valider en Phase 2.
- **Autres pays européens** : chaque régulateur publie séparément. Couverture progressive, en commençant par l'Allemagne via la BaFin.

**Traduction :** **CŒUR** (livres swing et moyen terme). Score = somme pondérée des achats en numéraire sur 30 à 90 jours, avec :
- un bonus « cluster » à partir de 3 initiés distincts ;
- un bonus CEO/CFO ;
- une pondération par le montant relatif à la position existante ;
- l'exclusion des initiés routiniers ;
- une décroissance temporelle.

Les ventes n'ont **aucun poids positif** : elles entrent seulement en OBS, pour les ventes groupées exceptionnelles.

### 7.4 Short interest et days-to-cover

**Prouvé :**
- Un short interest élevé prédit des rendements futurs faibles. Les vendeurs à découvert sont informés (Dechow, Hutton, Meulbroek & Sloan 2001 ; Boehmer, Jones & Zhang 2008) → **A**.
- Le **days-to-cover** (short interest / volume moyen) est un meilleur prédicteur que le ratio brut. Une stratégie long/short fondée sur le DTC rapporte environ **1,2 % par mois** selon les auteurs (Hong, Li, Ni, Scheinkman & Yan 2015 ✔, NBER WP 21166) → **B+**.
- En Europe, la publication nominative des positions courtes nettes au-delà de 0,5 % du capital modifie le comportement des investisseurs et porte de l'information (Jank, Roling & Smajlbegovic 2021) → **B+**.

**Données :**
- **US** : short interest FINRA, **gratuit**, publié **deux fois par mois** avec environ une semaine de délai ✔ ([FINRA](https://www.finra.org/finra-data/browse-catalog/equity-short-interest/data)).
- **UE** : positions courtes nettes **publiques à partir de 0,5 %** du capital (déclaration au régulateur dès 0,1 %) ✔ ([ESMA](https://www.esma.europa.eu/esmas-activities/markets-and-infrastructure/short-selling)). Publication par l'AMF, la BaFin, la CONSOB, etc.

**Traduction :** DTC (US) et somme des positions courtes publiques (UE) : **CŒUR**, avec un signe négatif pour les longs et positif pour les shorts. Un **short squeeze** potentiel (DTC très élevé et momentum positif) déclenche une **alerte de risque** pour les idées short, pas une idée long.

### 7.5 « Lazy Prices »

**Prouvé :** les sociétés qui **modifient sensiblement le texte** de leur 10-K ou 10-Q d'une année sur l'autre, en particulier dans les sections risques et contentieux, **sous-performent** ensuite. Le marché met du temps à intégrer ces changements (Cohen, Malloy & Nguyen 2020) → **B+**, et plutôt robuste car le turnover est faible. Le vocabulaire financier doit être traité avec un dictionnaire spécifique (Loughran & McDonald 2011).

**Traduction :** **CŒUR candidat** (livres moyen et long terme), **US seulement**. On calcule une similarité cosinus et une similarité de Jaccard entre sections du 10-K (N) et du 10-K (N-1), sur EDGAR, à la **date de dépôt**. Le calcul est **backtestable** et point-in-time, sans LLM, donc sans le biais d'anticipation propre aux LLM (§8.3). Phase 3.

### 7.6 Déclarations 13F

**Prouvé :**
- Les « **best ideas** » des gérants, c'est-à-dire leurs plus fortes surpondérations, surperforment (Cohen, Polk & Silli 2010 ; working paper) → **B–/C**.
- Des fonds « copycat » construits à partir des positions publiées obtiennent des rendements **comparables** aux fonds copiés, avant frais (Frank, Poterba, Shackelford & Shoven 2004) → **B**.

**Limites majeures, à afficher à chaque fois :**
- **Retard** : 45 jours après la fin du trimestre, donc des positions vieilles de 45 à 135 jours.
- **Longs US uniquement** : pas de shorts, pas de titres non US, pas de dérivés en dehors des options US.
- **Positions confidentielles** omises, qui sont justement les plus informatives (Agarwal, Jiang, Tang & Yang 2013).
- **Crowding** : les positions communes aux hedge funds chutent ensemble lors des déleveragings (Khandani & Lo 2011).

**Données :** les *Form 13F Data Sets* de la SEC ✔ ([sec.gov](https://www.sec.gov/dera/data/form-13f)), gratuits, disponibles depuis 2013.

**Traduction :**
- **OBS** au départ, puis éventuellement CŒUR à faible poids. Mesures : consensus entre les fonds suivis, nouvelles lignes, renforcements et « best ideas ». Le signal est backtestable depuis 2013 avec les dates de dépôt réelles.
- **PÉNALITÉ de crowding** quand trop de hedge funds détiennent le même titre.
- **Date de la donnée et retard toujours affichés.**

### 7.7 Transactions des parlementaires américains (STOCK Act)

**Preuves :**
- Une étude ancienne trouvait des rendements anormaux pour les sénateurs (Ziobrowski et al. 2004).
- Les études plus récentes **ne trouvent pas de surperformance**, et même une légère sous-performance après le STOCK Act de 2012 (Eggers & Hainmueller 2013 ; Belmont, Sacerdote, Sehgal & Van Hoek 2022 ✔). → **X/C**.
- **Délai de déclaration** : jusqu'à 45 jours, et souvent dépassé.

**Traduction :** **CONTEXTE uniquement**, avec une pondération nulle. On l'affiche lorsqu'un parlementaire membre d'une commission compétente pour le secteur achète ou vend, car cela peut être un indice d'information politique. Données officielles gratuites (House Clerk, Senate eFD) ou agrégateurs gratuits. **Je déconseille** l'abonnement Quiver (30 $/mois ✔) pour ce seul usage.

### 7.8 Flux d'options

**Preuves :**
- Le volume d'options **initié par les acheteurs**, une donnée non publique à l'époque de l'étude, prédit les rendements (Pan & Poteshman 2006) → non reproductible avec des données publiques.
- Les écarts à la parité call-put (Cremers & Weinbaum 2010) et la pente du smile de volatilité, ou *smirk* (Xing, Zhang & Zhao 2010), prédisent les rendements. Ce sont des données **calculables** à partir des chaînes d'options → **B+**.

**Traduction :**
- Le *smirk* (IV put OTM - IV call ATM) et l'écart de parité sont en **OBS**, pour les titres US dont on archive **chaque jour** l'instantané des chaînes d'options gratuites (construction d'un historique propre).
- Les services payants d'« unusual options flow » sont **REJETÉS** au départ : leur coût est de l'ordre de 50 à 250 $/mois, et leur valeur ajoutée n'est pas prouvée sur données publiques.

### 7.9 Liens économiques et effets de second ordre

**Prouvé :**
- Les rendements des **clients** d'une société prédisent ceux de ses **fournisseurs** : l'information se diffuse lentement le long de la chaîne de valeur (Cohen & Frazzini 2008) → **A–**.
- Même phénomène entre secteurs liés par les tables entrées-sorties (Menzly & Ozbas 2010) et entre secteurs (Hou 2007).

**Données :** aux États-Unis, les 10-K doivent mentionner les **clients représentant plus de 10 % du CA** (norme de reporting sectoriel ASC 280). Les tables entrées-sorties du BEA, gratuites, donnent les liens entre secteurs.

**Traduction :**
- **Module 7, effets de second ordre**, sous la forme d'un graphe d'exposition :
  - liens **secteur → secteur** (entrées-sorties) ;
  - liens **société → société**, avec les clients importants extraits des 10-K par le LLM **avec citation de la phrase source**.
- Signal « **momentum des clients** » en **OBS**, backtestable aux États-Unis.

### 7.10 Retournement court terme et volume anormal

**Prouvé :**
- **Retournement à 1 mois** (Jegadeesh 1990) : **A** en brut, mais il ne survit pas aux coûts hors petites capitalisations (Novy-Marx & Velikov 2016).
- **Prime de volume élevé** (Gervais, Kaniel & Mingelgrin 2001) → **B**.

**Traduction :**
- Retournement : **OBS**, comme modulateur du point d'entrée pour le swing. On évite d'acheter un titre après une hausse de +15 % en une semaine sans nouvelle.
- Volume anormal : **CŒUR** (swing), **conditionné** à l'existence d'une nouvelle identifiable. Un volume anormal sans nouvelle sur une petite capitalisation est un signal de **prudence** (§8.4).

---

## 8. Actualité, réseaux sociaux, discours politiques et LLM

### 8.1 Ce qui est prouvé sur le texte et les médias

| Résultat | Référence | Preuve |
|---|---|---|
| Le pessimisme médiatique prédit une pression baissière, **suivie d'un retournement** : c'est du sentiment, pas de l'information. | Tetlock (2007) | A– |
| La proportion de mots négatifs dans les nouvelles sur une société prédit ses **résultats** et ses rendements. | Tetlock, Saar-Tsechansky & Macskassy (2008) | A– |
| Les nouvelles **périmées** (déjà connues) provoquent une surréaction **suivie d'un retournement**. La **nouveauté** compte. | Tetlock (2011) | B+ |
| Les dictionnaires génériques classent mal le vocabulaire financier (« liability », « tax »…) : il faut des dictionnaires financiers. | Loughran & McDonald (2011) | A |
| Un pic d'attention (recherches Google) provoque une hausse à court terme **suivie d'un retournement**. | Da, Engelberg & Gao (2011) ; Barber & Odean (2008) | A– |
| L'attention des particuliers (Robinhood) produit un comportement grégaire suivi de **rendements négatifs**. | Barber, Huang, Odean & Schwarz (2022) | B+ |
| Les articles et commentaires de Seeking Alpha prédisent les rendements et les surprises de résultats. | Chen, De, Hu & Hwang (2014) | B |
| Les chambres d'écho sur StockTwits amplifient les biais de croyance. | Cookson, Engelberg & Mullins (2023) | B |
| La manipulation par de fausses nouvelles sur les réseaux sociaux affecte les petites capitalisations, et sa révélation réduit la réactivité à **toutes** les nouvelles. | Kogan, Moskowitz & Niessner (2023) ✔ | B |
| Un LLM (GPT) appliqué aux titres de presse prédit le rendement du lendemain, surtout pour les petites capitalisations, avec une décroissance rapide. | Lopez-Lira & Tang (2023), working paper | C |

### 8.2 Politique, banques centrales et commerce

| Résultat | Référence | Preuve |
|---|---|---|
| L'incertitude de politique économique se mesure à partir de la presse (indice EPU) et affecte l'investissement et la volatilité. | Baker, Bloom & Davis (2016) | A |
| Les **déclarations** des banques centrales font bouger les marchés au-delà des décisions de taux. | Gürkaynak, Sack & Swanson (2005) ; Hansen & McMahon (2016) | A– |
| Les droits de douane américains de 2018 ont été **répercutés presque intégralement** sur les prix intérieurs. Cela permet d'identifier les perdants (importateurs, clients) et les gagnants (producteurs domestiques protégés). | Amiti, Redding & Weinstein (2019) | A– |

### 8.3 Le piège spécifique des LLM : le biais d'anticipation

**Glasserman & Lin (2023)** ✔ (arXiv 2309.17322) identifient deux biais quand on backteste un signal LLM sur une période couverte par ses données d'entraînement :
1. le **biais d'anticipation** : le modèle « connaît » la suite ;
2. l'**effet de distraction** : sa connaissance générale de la société contamine la lecture du texte.

Ils proposent d'**anonymiser** les sociétés dans le texte.

**Conséquence directe pour le principe n° 2 (zéro biais d'anticipation) :**
- Les signaux LLM **ne peuvent pas être backtestés honnêtement** sur des données antérieures à la date de coupure du modèle. Ils sont évalués **uniquement en forward**, via le journal horodaté des recommandations (Module 9), à partir du premier jour.
- Pour l'évaluation, on utilise la **version anonymisée** du texte (nom → « Société A ») afin de mesurer le seul contenu informationnel.
- Le LLM ne produit **jamais** de chiffre qui n'existe pas dans les données fournies. Un contrôle automatique (« grounding check ») rejette toute sortie contenant un nombre absent des entrées (voir `ARCHITECTURE.md` §8).

### 8.4 Hype et manipulation

**Prouvé :**
- Les campagnes de promotion (« pump & dump ») ciblent des **petites capitalisations peu liquides**, avec un pic de mentions, souvent coordonné, sans information fondamentale nouvelle (Kogan et al. 2023 ; alertes investisseurs de la SEC et de l'AMF).
- Les pics d'attention sont suivis de **retournements** (§8.1).

**Traduction :** un **score de hype**, qui fonctionne comme une **PÉNALITÉ**, jamais comme un signal d'achat. Il combine :
- un z-score des mentions par rapport à une base de 30 jours ;
- une petite capitalisation et une liquidité faible ;
- une hausse de volume **sans** nouvelle crédible (dépôt réglementaire ou agence de presse) ;
- la concentration des auteurs (peu de comptes produisent l'essentiel des messages) ;
- une part élevée de comptes récents.

### 8.5 Accès réel aux sources sociales (vérifié le 23/09/2026)

| Source | Situation | Décision |
|---|---|---|
| **X (Twitter)** | Plus de palier gratuit. Tarification à l'usage d'environ **0,005 $ par post lu** ; les anciens abonnements Basic à 200 $/mois ont été migrés ✔ ([X Developers](https://devcommunity.x.com/t/announcing-the-launch-of-x-api-pay-per-use-pricing/256476)). 100 000 lectures par mois coûteraient environ 500 $. | **REJETÉ**, hors budget. |
| **Reddit** | Gratuit pour un usage **non commercial** (100 requêtes/min), mais les nouvelles applications passent par une **approbation manuelle** depuis fin 2025, avec un délai incertain ✔ ([source](https://www.socialcrawl.dev/blog/reddit-data-api-2026)). | **Demande à faire** en Phase 3 ; module optionnel. |
| **StockTwits** | **Inscriptions développeurs suspendues** ✔ ([api.stocktwits.com](https://api.stocktwits.com/developers)). | **REJETÉ** tant que c'est fermé. |
| **Truth Social et autres comptes politiques** | Pas d'API officielle. | Remplacés par les **canaux officiels** : Federal Register API (décrets et proclamations tarifaires, gratuit et horodaté), Maison-Blanche, USTR, salle de presse de la Commission européenne, flux RSS de la Fed, de la BCE, de la BoE, et discours des banquiers centraux agrégés par la BRI. **GDELT**, gratuit, pour la couverture mondiale. |

**Conclusion honnête :** avec 300 €/mois, la couche « réseaux sociaux » sera **mince**, limitée à Reddit si l'accès est approuvé. La valeur de la couche « actualité » viendra surtout des **dépôts réglementaires** (8-K, communiqués, déclarations AMF), des **agences de presse via RSS** et des **canaux officiels politiques et banques centrales**. C'est aussi là que la littérature trouve le plus d'information : le social est surtout du sentiment qui se retourne.

---

## 9. Méthodologie de validation : références retenues

| Référence | Ce qu'on en retient |
|---|---|
| Arnott, Harvey & Markowitz (2019) | Protocole : hypothèse économique d'abord, journal de tous les essais, test final non réutilisé. |
| Bailey & López de Prado (2014) | Deflated Sharpe Ratio dans le rapport de validation. |
| López de Prado (2018) | Validation croisée **purgée avec embargo** si l'on utilise un jour du ML, car les labels se chevauchent dans le temps. |
| Harvey, Liu & Zhu (2016) | Seuil t ≥ 3 pour les signaux « maison ». |
| Gu, Kelly & Xiu (2020) | Le ML (arbres, réseaux de neurones) améliore la prédiction, mais surtout via le momentum, la liquidité et la volatilité, avec un gain qui se concentre dans les petites capitalisations. **Pas de ML en Phase 1-3** ; éventuellement un modèle de combinaison en Phase 5, s'il bat l'équipondération hors échantillon. |
| Kelly, Malamud & Zhou (2024) | Contrepoint : des modèles plus complexes *peuvent* mieux prédire. Je le note, mais la robustesse reste prioritaire (principe n° 4). |

---

## 10. Synthèse : catalogue initial des signaux

Livres : **S** = swing (1 à 8 semaines), **M** = moyen terme (3 à 12 mois), **L** = long terme (5 ans et plus).
Colonne « PIT » : l'historique **point-in-time** est-il disponible pour un backtest ?

| ID | Signal | Module | Livres | Réf. principale | Preuve | Données (source) | PIT ? | Statut initial | Phase |
|---|---|---|---|---|---|---|---|---|---|
| Q-MOM-12-1 | Momentum 12-1 (volatilité mise à l'échelle) | 3 | M, S | Jegadeesh-Titman 93 ; Barroso-Santa-Clara 15 | A | Prix (EODHD, yfinance) | Oui | CŒUR | 1 |
| Q-MOM-6-1 | Momentum 6-1 | 3 | S | Jegadeesh-Titman 93 | A | Prix | Oui | CŒUR | 1 |
| Q-RESMOM | Momentum résiduel | 3 | M | Blitz et al. 11 | B+ | Prix + facteurs | Oui | CŒUR | 1 |
| Q-INDMOM | Momentum sectoriel | 3 | S | Moskowitz-Grinblatt 99 | A– | Prix + secteurs | Partiel (secteur actuel) | CŒUR | 1 |
| Q-RS | Force relative vs secteur et indice | 3 | S, M | variante du momentum | A– | Prix | Oui | CŒUR | 1 |
| Q-52WH | Proximité du plus haut 52 semaines | 3 | S | George-Hwang 04 | B+ | Prix | Oui | CŒUR | 1 |
| Q-LOWVOL | Faible volatilité / faible bêta | 3 | M, L | Frazzini-Pedersen 14 ; Ang et al. 06 | A | Prix | Oui | CŒUR | 1 |
| Q-ABVOL | Volume anormal (avec nouvelle) | 3 | S | Gervais et al. 01 | B | Prix/volume (+ nouvelles en Phase 3) | Oui | CŒUR | 1 |
| Q-EAR | Réaction aux résultats (EAR 3 jours) | 3 | S | Brandt et al. 08 ; Chan et al. 96 | B (voir Martineau 22) | Prix + dates d'annonce (8-K) | Oui (US) | CŒUR à valider | 1 |
| Q-TREND | Trend Template (filtre) | 3 | S | Minervini | D | Prix | Oui | OBS | 1 |
| Q-VCP | Contraction de volatilité | 3 | S | Minervini | D | Prix | Oui | OBS | 1 |
| Q-STREV | Retournement 1 mois | 3 | S | Jegadeesh 90 | A brut, faible net | Prix | Oui | OBS | 1 |
| F-GP | Rentabilité brute / actifs | 2 | M, L | Novy-Marx 13 | A | Fondamentaux (EDGAR, EODHD) | Oui US, lag estimé UE | CŒUR | 1 |
| F-CBOP | Rentabilité opérationnelle fondée sur le cash | 2 | M, L | Ball et al. 16 | A– | Fondamentaux | idem | CŒUR | 1 |
| F-ROIC | ROIC niveau + stabilité 5 ans | 2 | L | QMJ | A– (via QMJ) | Fondamentaux | idem | CŒUR | 1 |
| F-ACCR | Accruals / conversion en FCF | 2 | M, L | Sloan 96 | A (affaibli) | Fondamentaux | idem | CŒUR | 1 |
| F-EY | EBIT/EV | 2 | M, L | Loughran-Wellman 11 ; Gray-Carlisle 12 | B+ | Fondamentaux + prix | idem | CŒUR | 1 |
| F-FCFY | FCF/EV | 2 | M, L | famille value | B+ | idem | idem | CŒUR | 1 |
| F-BM | Book-to-market (financières surtout) | 2 | M | Fama-French 93 | A (affaibli) | idem | idem | CŒUR | 1 |
| F-PE-HIST | P/E relatif à l'historique propre | 2 | L | pratique | D | idem | idem | OBS (affiché) | 1 |
| F-ISSUE | Émissions nettes (négatif) / rachats | 2 | M, L | Pontiff-Woodgate 08 | A | Nombre d'actions | Oui US | CŒUR | 1 |
| F-AGR | Croissance des actifs (négatif) | 2 | M | Cooper et al. 08 | A | Bilan | idem | CŒUR | 1 |
| F-DPROF | Croissance de la rentabilité (5 ans) | 2 | L | QMJ | A– | Fondamentaux | idem | CŒUR | 1 |
| F-PIOT | Piotroski F-score | 2 | M, L | Piotroski 00 | B | Fondamentaux | idem | CŒUR + FILTRE value | 1 |
| F-ALTZ | Altman Z / Z'' (hors financières) | 2 | tous | Altman 68, 05 ; Campbell et al. 08 | A– (détresse) | Fondamentaux | idem | PÉNALITÉ + candidat short | 1 |
| F-BENM | Beneish M (hors financières) | 2 | tous | Beneish 99 ; Beneish et al. 13 | B+ | Fondamentaux | idem | PÉNALITÉ + alerte | 1 |
| F-LEV | Levier, couverture des intérêts | 2 | L | QMJ (sécurité) | A– | Fondamentaux | idem | CŒUR (sécurité) | 1 |
| F-SUE | Surprise de BPA (sans consensus) | 2 | S | Bernard-Thomas 89 ; Martineau 22 | B– (grandes caps US) | BPA trimestriels | Oui US | CŒUR à valider | 1 |
| F-REV | Révisions de consensus | 2 | S, M | Chan et al. 96 | A– | Instantanés quotidiens archivés | **Non** (on construit l'historique) | OBS → forward | 1 (archivage) |
| S-INS | Achats d'initiés groupés (code P) | 4 | S, M | Lakonishok-Lee 01 ; Cohen et al. 12 ; Alldredge-Blank 19 | A | SEC Form 4 ; AMF BDIF | Oui US ; FR à construire | CŒUR | 2 |
| S-DTC | Days-to-cover (US) | 4 | M, S | Hong et al. 15 | B+ | FINRA | Oui | CŒUR | 2 |
| S-EUSHORT | Positions courtes publiques UE | 4 | M, S | Jank et al. 21 | B+ | AMF, BaFin, CONSOB… | Oui (depuis 2012) | CŒUR | 2 |
| S-13F | Consensus et best ideas des fonds suivis | 4 | M, L | Cohen-Polk-Silli 10 ; Frank et al. 04 | B–/C | SEC 13F Data Sets | Oui (depuis 2013) | OBS | 2 |
| S-CROWD | Crowding hedge funds | 4 | M | Khandani-Lo 11 | B | 13F | Oui | PÉNALITÉ (OBS) | 2 |
| S-CONG | Transactions des parlementaires | 4 | — | Belmont et al. 22 | X/C | House / Senate | Oui | CONTEXTE | 2 |
| S-OPT | Smirk de volatilité / parité call-put | 4 | S | Xing et al. 10 ; Cremers-Weinbaum 10 | B+ | Chaînes d'options archivées | **Non** (on construit) | OBS | 2 |
| M-REG | Régime croissance × inflation | 6 | tous | Ilmanen et al. 14 | B | FRED/ALFRED, OCDE, BCE | Oui (millésimes) | CONTEXTE + risque | 2 |
| M-TREND | Tendance de l'indice (overlay) | 6/10 | tous | Faber 07 ; Hurst et al. 17 | B | Prix des indices | Oui | Risque (exposition nette) | 2 |
| T-LAZY | Lazy Prices (similarité 10-K) | 5 | M, L | Cohen-Malloy-Nguyen 20 | B+ | EDGAR (texte) | Oui | CŒUR à valider | 3 |
| T-NEWS | Sentiment + nouveauté des nouvelles (LLM) | 5 | S | Tetlock 07/11 ; Lopez-Lira-Tang 23 | C (LLM) | RSS, EDGAR 8-K, GDELT | **Non** (biais LLM) | OBS → forward | 3 |
| T-HYPE | Score de hype / manipulation | 5 | S | Kogan et al. 23 ; Da et al. 11 | B | Reddit (si accès), volumes | Partiel | PÉNALITÉ | 3 |
| T-CUSTMOM | Momentum des clients (chaîne de valeur) | 7 | S, M | Cohen-Frazzini 08 | A– | 10-K (clients > 10 % du CA) | Oui US | OBS | 3 |
| T-POLICY | Impact d'un événement politique ou macro | 5/7 | S | Amiti et al. 19 ; Baker et al. 16 | B (qualitatif) | Federal Register, BCE, Fed, GDELT | Non | CONTEXTE (scénarios) | 3 |

---

## 11. Ce que je ne retiens pas, et pourquoi

1. **Le facteur taille seul** : la prime est faible hors micro-caps et hors contrôle de la qualité. Les micro-caps sont exclues pour des raisons de liquidité.
2. **La croissance passée brute du CA ou du BPA comme score positif** : les preuves vont dans l'autre sens (Lakonishok, Shleifer & Vishny 1994). Elle est remplacée par les surprises, les révisions et la croissance de la rentabilité.
3. **La Magic Formula telle quelle** : ses deux ingrédients sont intégrés séparément.
4. **Les transactions des parlementaires comme score** : pas de surperformance après le STOCK Act.
5. **L'« unusual options flow » payant et X/Twitter** : coût élevé, preuve faible ou fondée sur des données non publiques.
6. **La « liquidité nette » comme signal de timing** : pas de validation hors échantillon.
7. **Le timing de facteurs agressif selon le régime** : preuve décevante. Il reste en observation.
8. **Le ML complexe au démarrage** : robustesse d'abord. On y revient seulement s'il bat l'équipondération, avec validation croisée purgée.
9. **Des probabilités de scénarios « calculées » par le LLM** : elles sont présentées comme **subjectives**, raisonnement à l'appui, et leur **calibration** (score de Brier) est mesurée dans le temps. On apprend ainsi si elles valent quelque chose.

---

## 12. Bibliographie

*(✔ = détails revérifiés en ligne le 23/09/2026)*

- Agarwal, V., Jiang, W., Tang, Y., Yang, B. (2013). Uncovering hedge fund skill from the portfolio holdings they hide. *Journal of Finance*, 68(2).
- Alldredge, D., Blank, B. (2019). Do insiders cluster trades with colleagues? Evidence from daily insider trading. *Journal of Financial Research*, 42(2), 331–360. ✔ [DOI](https://onlinelibrary.wiley.com/doi/abs/10.1111/jfir.12172)
- Altman, E. (1968). Financial ratios, discriminant analysis and the prediction of corporate bankruptcy. *Journal of Finance*, 23(4).
- Altman, E. (2005). An emerging market credit scoring system for corporate bonds. *Emerging Markets Review*, 6(4).
- Amiti, M., Redding, S., Weinstein, D. (2019). The impact of the 2018 tariffs on prices and welfare. *Journal of Economic Perspectives*, 33(4).
- Ang, A., Hodrick, R., Xing, Y., Zhang, X. (2006). The cross-section of volatility and expected returns. *Journal of Finance*, 61(1).
- Arnott, R., Harvey, C., Kalesnik, V., Linnainmaa, J. (2021). Reports of value's death may be greatly exaggerated. *Financial Analysts Journal*, 77(1).
- Arnott, R., Harvey, C., Markowitz, H. (2019). A backtesting protocol in the era of machine learning. *Journal of Financial Data Science*, 1(1).
- Asness, C., Chandra, S., Ilmanen, A., Israel, R. (2017). Contrarian factor timing is deceptively difficult. *Journal of Portfolio Management*, 43(5).
- Asness, C., Frazzini, A., Israel, R., Moskowitz, T. (2014). Fact, fiction, and momentum investing. *Journal of Portfolio Management*, 40(5).
- Asness, C., Frazzini, A., Israel, R., Moskowitz, T., Pedersen, L. (2018). Size matters, if you control your junk. *Journal of Financial Economics*, 129(3).
- Asness, C., Frazzini, A., Pedersen, L. (2019). Quality minus junk. *Review of Accounting Studies*, 24(1).
- Asness, C., Moskowitz, T., Pedersen, L. (2013). Value and momentum everywhere. *Journal of Finance*, 68(3).
- Bailey, D., López de Prado, M. (2014). The deflated Sharpe ratio. *Journal of Portfolio Management*, 40(5).
- Baker, S., Bloom, N., Davis, S. (2016). Measuring economic policy uncertainty. *Quarterly Journal of Economics*, 131(4).
- Ball, R., Brown, P. (1968). An empirical evaluation of accounting income numbers. *Journal of Accounting Research*, 6(2).
- Ball, R., Gerakos, J., Linnainmaa, J., Nikolaev, V. (2016). Accruals, cash flows, and operating profitability in the cross section of stock returns. *Journal of Financial Economics*, 121(1).
- Barber, B., Huang, X., Odean, T., Schwarz, C. (2022). Attention-induced trading and returns: Evidence from Robinhood users. *Journal of Finance*, 77(6).
- Barber, B., Odean, T. (2008). All that glitters. *Review of Financial Studies*, 21(2).
- Barroso, P., Santa-Clara, P. (2015). Momentum has its moments. *Journal of Financial Economics*, 116(1).
- Belmont, W., Sacerdote, B., Sehgal, R., Van Hoek, I. (2022). Do senators and house members beat the stock market? Evidence from the STOCK Act. *Journal of Public Economics*, 207. ✔ (NBER WP 26975)
- Beneish, M. (1999). The detection of earnings manipulation. *Financial Analysts Journal*, 55(5).
- Beneish, M., Lee, C., Nichols, D. C. (2013). Earnings manipulation and expected returns. *Financial Analysts Journal*, 69(2).
- Bernard, V., Thomas, J. (1989). Post-earnings-announcement drift: Delayed price response or risk premium? *Journal of Accounting Research*, 27 (Supplement).
- Blitz, D., Huij, J., Martens, M. (2011). Residual momentum. *Journal of Empirical Finance*, 18(3).
- Boehmer, E., Jones, C., Zhang, X. (2008). Which shorts are informed? *Journal of Finance*, 63(2).
- Brandt, M., Kishore, R., Santa-Clara, P., Venkatachalam, M. (2008). Earnings announcements are full of surprises. Working paper, SSRN.
- Brav, A., Jiang, W., Partnoy, F., Thomas, R. (2008). Hedge fund activism, corporate governance, and firm performance. *Journal of Finance*, 63(4).
- Brown, S., Goetzmann, W., Ibbotson, R., Ross, S. (1992). Survivorship bias in performance studies. *Review of Financial Studies*, 5(4).
- Campbell, J., Hilscher, J., Szilagyi, J. (2008). In search of distress risk. *Journal of Finance*, 63(6).
- Carhart, M. (1997). On persistence in mutual fund performance. *Journal of Finance*, 52(1).
- Chan, L., Jegadeesh, N., Lakonishok, J. (1996). Momentum strategies. *Journal of Finance*, 51(5).
- Chen, A., Zimmermann, T. (2022). Open source cross-sectional asset pricing. *Critical Finance Review*, 11(2), 207–264. ✔
- Chen, H., De, P., Hu, Y., Hwang, B.-H. (2014). Wisdom of crowds: The value of stock opinions transmitted through social media. *Review of Financial Studies*, 27(5).
- Cohen, L., Frazzini, A. (2008). Economic links and predictable returns. *Journal of Finance*, 63(4).
- Cohen, L., Malloy, C., Nguyen, Q. (2020). Lazy prices. *Journal of Finance*, 75(3).
- Cohen, L., Malloy, C., Pomorski, L. (2012). Decoding inside information. *Journal of Finance*, 67(3).
- Cohen, R., Polk, C., Silli, B. (2010). Best ideas. Working paper, SSRN.
- Cookson, J. A., Engelberg, J., Mullins, W. (2023). Echo chambers. *Review of Financial Studies*, 36(2).
- Cooper, M., Gulen, H., Schill, M. (2008). Asset growth and the cross-section of stock returns. *Journal of Finance*, 63(4).
- Corwin, S., Schultz, P. (2012). A simple way to estimate bid-ask spreads from daily high and low prices. *Journal of Finance*, 67(2).
- Cremers, M., Weinbaum, D. (2010). Deviations from put-call parity and stock return predictability. *Journal of Financial and Quantitative Analysis*, 45(2).
- Da, Z., Engelberg, J., Gao, P. (2011). In search of attention. *Journal of Finance*, 66(5).
- Dalio, R. (2018). *Principles for Navigating Big Debt Crises*. Bridgewater.
- Daniel, K., Moskowitz, T. (2016). Momentum crashes. *Journal of Financial Economics*, 122(2).
- Daniel, K., Titman, S. (2006). Market reactions to tangible and intangible information. *Journal of Finance*, 61(4).
- Dechow, P., Hutton, A., Meulbroek, L., Sloan, R. (2001). Short-sellers, fundamental analysis, and stock returns. *Journal of Financial Economics*, 61(1).
- DellaVigna, S., Pollet, J. (2009). Investor inattention and Friday earnings announcements. *Journal of Finance*, 64(2).
- DeMiguel, V., Garlappi, L., Uppal, R. (2009). Optimal versus naive diversification: How inefficient is the 1/N portfolio strategy? *Review of Financial Studies*, 22(5).
- Dichev, I. (1998). Is the risk of bankruptcy a systematic risk? *Journal of Finance*, 53(3).
- Eggers, A., Hainmueller, J. (2013). Capitol losses: The mediocre performance of Congressional stock portfolios. *Journal of Politics*, 75(2).
- Estrella, A., Mishkin, F. (1998). Predicting U.S. recessions: Financial variables as leading indicators. *Review of Economics and Statistics*, 80(1).
- Faber, M. (2007). A quantitative approach to tactical asset allocation. *Journal of Wealth Management*, 9(4).
- Fama, E., French, K. (1993). Common risk factors in the returns on stocks and bonds. *Journal of Financial Economics*, 33(1).
- Fama, E., French, K. (2012). Size, value, and momentum in international stock returns. *Journal of Financial Economics*, 105(3).
- Fama, E., French, K. (2015). A five-factor asset pricing model. *Journal of Financial Economics*, 116(1).
- Fama, E., French, K. (2017). International tests of a five-factor asset pricing model. *Journal of Financial Economics*, 123(3).
- Fidrmuc, J., Goergen, M., Renneboog, L. (2006). Insider trading, news releases, and ownership concentration. *Journal of Finance*, 61(6).
- Frank, M., Poterba, J., Shackelford, D., Shoven, J. (2004). Copycat funds: Information disclosure regulation and the returns to active management in the mutual fund industry. *Journal of Law and Economics*, 47(2).
- Frazzini, A., Kabiller, D., Pedersen, L. (2018). Buffett's alpha. *Financial Analysts Journal*, 74(4), 35–55. ✔
- Frazzini, A., Pedersen, L. (2014). Betting against beta. *Journal of Financial Economics*, 111(1).
- George, T., Hwang, C.-Y. (2004). The 52-week high and momentum investing. *Journal of Finance*, 59(5).
- Gervais, S., Kaniel, R., Mingelgrin, D. (2001). The high-volume return premium. *Journal of Finance*, 56(3).
- Gilchrist, S., Zakrajšek, E. (2012). Credit spreads and business cycle fluctuations. *American Economic Review*, 102(4).
- Givoly, D., Lakonishok, J. (1979). The information content of financial analysts' forecasts of earnings. *Journal of Accounting and Economics*, 1(3).
- Glasserman, P., Lin, C. (2023). Assessing look-ahead bias in stock return predictions generated by GPT sentiment analysis. arXiv:2309.17322 / SSRN 4586726. ✔
- Gompers, P., Metrick, A. (2001). Institutional investors and equity prices. *Quarterly Journal of Economics*, 116(1).
- Gray, W., Carlisle, T. (2012). *Quantitative Value*. Wiley.
- Greenblatt, J. (2005). *The Little Book That Beats the Market*. Wiley.
- Grinold, R. (1989). The fundamental law of active management. *Journal of Portfolio Management*, 15(3).
- Gu, S., Kelly, B., Xiu, D. (2020). Empirical asset pricing via machine learning. *Review of Financial Studies*, 33(5).
- Gürkaynak, R., Sack, B., Swanson, E. (2005). Do actions speak louder than words? *International Journal of Central Banking*, 1(1).
- Hansen, S., McMahon, M. (2016). Shocking language: Understanding the macroeconomic effects of central bank communication. *Journal of International Economics*, 99.
- Harvey, C., Hoyle, E., Korgaonkar, R., Rattray, S., Sargaison, M., Van Hemert, O. (2019). The best of strategies for the worst of times: Can portfolios be crisis proofed? *Journal of Portfolio Management*.
- Harvey, C., Liu, Y., Zhu, H. (2016). … and the cross-section of expected returns. *Review of Financial Studies*, 29(1).
- Hirshleifer, D., Lim, S., Teoh, S. (2009). Driven to distraction: Extraneous events and underreaction to earnings news. *Journal of Finance*, 64(5).
- Hong, H., Li, W., Ni, S., Scheinkman, J., Yan, P. (2015). Days to cover and stock returns. NBER Working Paper 21166. ✔
- Hou, K. (2007). Industry information diffusion and the lead-lag effect in stock returns. *Review of Financial Studies*, 20(4).
- Hou, K., Xue, C., Zhang, L. (2020). Replicating anomalies. *Review of Financial Studies*, 33(5).
- Hurst, B., Ooi, Y. H., Pedersen, L. (2017). A century of evidence on trend-following investing. *Journal of Portfolio Management*, 44(1).
- Ilmanen, A., Maloney, T., Ross, A. (2014). Exploring macroeconomic sensitivities: How investments respond to different economic environments. *Journal of Portfolio Management*, 40(3).
- Jank, S., Roling, C., Smajlbegovic, E. (2021). Flying under the radar: The effects of short-sale disclosure rules on investor behavior and stock prices. *Journal of Financial Economics*, 139(1).
- Jegadeesh, N. (1990). Evidence of predictable behavior of security returns. *Journal of Finance*, 45(3).
- Jegadeesh, N., Titman, S. (1993). Returns to buying winners and selling losers. *Journal of Finance*, 48(1).
- Jegadeesh, N., Titman, S. (2001). Profitability of momentum strategies: An evaluation of alternative explanations. *Journal of Finance*, 56(2).
- Jensen, T., Kelly, B., Pedersen, L. (2023). Is there a replication crisis in finance? *Journal of Finance*, 78(5). ✔ (données : [jkpfactors.com](https://jkpfactors.com/))
- Kelly, B., Malamud, S., Zhou, K. (2024). The virtue of complexity in return prediction. *Journal of Finance*, 79(1).
- Khandani, A., Lo, A. (2011). What happened to the quants in August 2007? *Journal of Financial Markets*, 14(1).
- Kogan, S., Moskowitz, T., Niessner, M. (2023). Social media and financial news manipulation. *Review of Finance*, 27(4), 1229–1268. ✔
- Kurov, A., Wolfe, M., Gilbert, T. (2021). The disappearing pre-FOMC announcement drift. *Finance Research Letters*, 40.
- Lakonishok, J., Lee, I. (2001). Are insider trades informative? *Review of Financial Studies*, 14(1).
- Lakonishok, J., Shleifer, A., Vishny, R. (1994). Contrarian investment, extrapolation, and risk. *Journal of Finance*, 49(5).
- Lopez-Lira, A., Tang, Y. (2023). Can ChatGPT forecast stock price movements? Return predictability and large language models. Working paper, SSRN.
- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley.
- Loughran, T., McDonald, B. (2011). When is a liability not a liability? Textual analysis, dictionaries, and 10-Ks. *Journal of Finance*, 66(1).
- Loughran, T., Wellman, J. (2011). New evidence on the relation between the enterprise multiple and average stock returns. *Journal of Financial and Quantitative Analysis*, 46(6).
- Lucca, D., Moench, E. (2015). The pre-FOMC announcement drift. *Journal of Finance*, 70(1).
- Martineau, C. (2022). Rest in peace post-earnings announcement drift. *Critical Finance Review*, 11(3-4), 613–646. ✔
- McLean, R. D., Pontiff, J. (2016). Does academic research destroy stock return predictability? *Journal of Finance*, 71(1).
- Menzly, L., Ozbas, O. (2010). Market segmentation and cross-predictability of returns. *Journal of Finance*, 65(4).
- Minervini, M. (2013). *Trade Like a Stock Market Wizard*. McGraw-Hill. Minervini, M. *Think & Trade Like a Champion*.
- Moskowitz, T., Grinblatt, M. (1999). Do industries explain momentum? *Journal of Finance*, 54(4).
- Moskowitz, T., Ooi, Y. H., Pedersen, L. (2012). Time series momentum. *Journal of Financial Economics*, 104(2).
- Novy-Marx, R. (2013). The other side of value: The gross profitability premium. *Journal of Financial Economics*, 108(1).
- Novy-Marx, R., Velikov, M. (2016). A taxonomy of anomalies and their trading costs. *Review of Financial Studies*, 29(1).
- O'Neil, W. (2009). *How to Make Money in Stocks*, 4e éd. McGraw-Hill.
- Pan, J., Poteshman, A. (2006). The information in option volume for future stock prices. *Review of Financial Studies*, 19(3).
- Piotroski, J. (2000). Value investing: The use of historical financial statement information to separate winners from losers. *Journal of Accounting Research*, 38 (Supplement).
- Pontiff, J., Woodgate, A. (2008). Share issuance and cross-sectional returns. *Journal of Finance*, 63(2).
- Rapach, D., Ringgenberg, M., Zhou, G. (2016). Short interest and aggregate stock returns. *Journal of Financial Economics*, 121(1).
- Rouwenhorst, K. G. (1998). International momentum strategies. *Journal of Finance*, 53(1).
- Rouwenhorst, K. G. (1999). Local return factors and turnover in emerging stock markets. *Journal of Finance*, 54(4).
- Seyhun, H. N. (1986). Insiders' profits, costs of trading, and market efficiency. *Journal of Financial Economics*, 16(2).
- Shumway, T. (1997). The delisting bias in CRSP data. *Journal of Finance*, 52(1).
- Sloan, R. (1996). Do stock prices fully reflect information in accruals and cash flows about future earnings? *The Accounting Review*, 71(3).
- Soros, G. (1987). *The Alchemy of Finance*. Simon & Schuster.
- Soros, G. (2013). Fallibility, reflexivity, and the human uncertainty principle. *Journal of Economic Methodology*, 20(4).
- Stickel, S. (1991). Common stock returns surrounding earnings forecast revisions: More puzzling evidence. *The Accounting Review*, 66(2).
- Tetlock, P. (2007). Giving content to investor sentiment: The role of media in the stock market. *Journal of Finance*, 62(3).
- Tetlock, P. (2011). All the news that's fit to reprint: Do investors react to stale information? *Review of Financial Studies*, 24(5).
- Tetlock, P., Saar-Tsechansky, M., Macskassy, S. (2008). More than words: Quantifying language to measure firms' fundamentals. *Journal of Finance*, 63(3).
- Xing, Y., Zhang, X., Zhao, R. (2010). What does the individual option volatility smirk tell us about future equity returns? *Journal of Financial and Quantitative Analysis*, 45(3).
- Ziobrowski, A., Cheng, P., Boyd, J., Ziobrowski, B. (2004). Abnormal returns from the common stock investments of the U.S. Senate. *Journal of Financial and Quantitative Analysis*, 39(4).
- Zuckerman, G. (2019). *The Man Who Solved the Market*. Portfolio/Penguin.
