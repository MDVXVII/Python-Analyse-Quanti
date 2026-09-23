# Scanner d'actions quotidien (daily-stock-scanner)

Outil personnel de sélection d'actions. Chaque jour avant l'ouverture, il combine analyse
fondamentale, analyse quantitative et technique (et, dans les phases suivantes, flux « smart
money », actualité analysée par LLM et régime macro). Il produit un classement **argumenté et
explicable** sur trois horizons :

| Livre | Horizon |
|---|---|
| **S** (swing) | 1 à 8 semaines |
| **M** (moyen terme) | 3 à 12 mois |
| **L** (long terme) | 5 ans et plus |

Il **mesure honnêtement sa propre performance** grâce à un protocole de validation hors
échantillon et à un journal horodaté, infalsifiable, des recommandations.

| Document | Contenu |
|---|---|
| [`research_notes.md`](research_notes.md) | Étape 0 : état de l'art (factor investing, quant, macro, value, anomalies, LLM), niveaux de preuve et traduction en signaux |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Plan d'architecture validé : sources et budget, univers, modèle point-in-time, scoring, validation, pipeline, phases |
| [`docs/validation_synthetique_exemple.md`](docs/validation_synthetique_exemple.md) | Exemple de rapport de validation, **sur données synthétiques** : il montre la mécanique, pas les marchés |

## Statut : Phase 1 livrée

Modules livrés : 1 (univers et données), 2 (fondamentaux), 3 (quant et technique),
8 (scoring), 9 (backtest et validation, version de base), 11 (pipeline, en version minimale)
et 12 (rapport). S'y ajoutent le journal horodaté et l'automatisation quotidienne minimale,
avancés de la Phase 4 comme convenu. Le **bilan détaillé** est à la fin de ce document.

## Démarrage rapide (aucune clé, aucun réseau)

```bash
cd daily-stock-scanner
uv venv --python 3.12 && source .venv/bin/activate   # ou : python3.12 -m venv .venv
uv pip install -e ".[dev]"                             # ou : pip install -e ".[dev]"
scanner demo --out data/demo                           # ~20 s : 2 rapports quotidiens synthétiques
scanner demo --out data/demo --validation              # + protocole de validation (~10 min)
pytest                                                 # 90+ tests (hors réseau)
```

La démo génère un marché **synthétique** : sociétés fictives, qualité et momentum plantés
connus. Elle exécute toute la chaîne : signaux, scores, rapport Markdown et HTML, journal
chaîné, empreinte publique.

## Configuration des API

Copier `.env.example` en `.env` (jamais versionné) :

| Variable | Obligatoire | Usage | Coût |
|---|---|---|---|
| `SEC_USER_AGENT` | **oui** | SEC EDGAR : fondamentaux US « tels que déposés », dates de publication. La SEC exige « Nom Prénom email ». | gratuit |
| `EODHD_API_KEY` | recommandé | Prix mondiaux, **délistés** (backtest sans biais du survivant), fondamentaux, compositions d'indices | ~100 €/mois (All-In-One) |
| `FINNHUB_API_KEY` | optionnel | Calendrier des résultats à venir (catalyseurs, pénalité d'événement binaire) | gratuit |
| `SMTP_*`, `REPORT_TO` | optionnel | Envoi du rapport par email (Gmail : mot de passe d'application) | gratuit |
| `FRED_API_KEY`, `ANTHROPIC_API_KEY` | Phases 2-3 | Macro, puis LLM | gratuit, puis ~45-80 $/mois |

Sans EODHD, le scanner fonctionne en **mode gratuit** (yfinance + SEC + Wikipédia), avec des
limites explicites (voir « Limites connues »). Pour l'Europe, il faut alors fournir les
compositions du STOXX 600 et du SBF 120 en CSV : voir [`config/universe/README.md`](config/universe/README.md).

Tous les paramètres (univers, seuils, pondérations, coûts, sources) sont dans `config/*.yaml`,
validés au démarrage. Toute faute de frappe provoque une erreur explicite.

## Lancement

```bash
scanner run                      # collecte + contrôles + signaux + scores + rapport + journal
scanner run --date 2026-09-23 --no-ingest --no-email
scanner validate --region US --start 2011-01-01 --oos-start 2019-01-01 \
                 --label "EODHD" --survivorship-free        # rapport de validation sur tes données
scanner snapshot                 # archive les consensus et les options (historique PIT construit par nous)
scanner journal verify           # vérifie que le journal n'a pas été modifié
```

Sorties, dans `data/` (ignoré par git) :
- `reports/<date>.md|.html` : les rapports ;
- `runs/<run_id>/` : signaux, scores, idées et manifeste, pour l'audit ;
- `journal/journal.jsonl` : le journal.

L'empreinte quotidienne du journal est écrite dans `commitments/<date>.json`, qui, lui, est versionné.

## Automatisation (GitHub Actions)

| Workflow | Déclenchement | Rôle |
|---|---|---|
| `scanner-ci` | chaque push | Ruff, mypy, tests (dont le test long du protocole), démo synthétique ; job `network-smoke` : parseurs confrontés aux vraies API |
| `scanner-daily` | 05:00 UTC du lundi au vendredi, ou manuel | Exécution quotidienne, email, publication de l'empreinte du journal |

Secrets à créer (Settings → Secrets and variables → Actions) :
- `SEC_USER_AGENT` : obligatoire ;
- `SCANNER_DATA_KEY` : **obligatoire**, une phrase de passe longue. Elle chiffre les données, les rapports et le journal conservés dans le cache du dépôt, car le dépôt est public et certaines données sont sous licence ;
- optionnels : `EODHD_API_KEY`, `FINNHUB_API_KEY`, `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `REPORT_TO`.

À savoir :
- Un workflow planifié ne tourne **que depuis `main`** : il démarrera une fois cette branche fusionnée.
- Les crons GitHub sont « best effort » : d'où la marge de 2 h avant l'ouverture européenne.
- Les rapports ne sont **pas** publiés dans le dépôt public : ils arrivent par email. Seule l'empreinte du journal est publique, avec une copie chiffrée du journal pour ne jamais le perdre.

## Architecture du code

```
src/scanner/
  core/          config typée (YAML + pydantic), conventions temporelles, référentiels, symboles
  data/          client HTTP (cache, limite de débit, relances), providers, stockage bitemporel,
                 PitView (unique accès aux données), contrôles qualité, change
  fundamentals/  états PIT (TTM, T4 déduit, retraitements), ratios, Piotroski, Altman, Beneish, SUE
  quant/         momentum (12-1, 6-1, résiduel, sectoriel), force relative, 52 semaines,
                 faible volatilité, volume anormal, EAR, Trend Template
  scoring/       rang gaussien secteur x région, familles, livres S/M/L, pénalités, décomposition
  backtest/      moteur (coûts, délistés, décalage d'exécution), IC et décroissance,
                 Newey-West, Deflated Sharpe, walk-forward, protocole et rapport de validation
  journal/       journal chaîné SHA-256, engagements publics, suivi de performance
  report/        rapport Markdown et HTML (Jinja2), email
  pipeline/      moteur commun, collecte, exécution quotidienne, démo
```

Le **même moteur** calcule les scores du rapport quotidien et ceux du backtest : ce qui est
validé est exactement ce qui est utilisé.

## Garanties méthodologiques

- **Pas de biais d'anticipation.** Toute donnée porte sa date de publication (`available_at`) et n'est visible qu'à travers `PitView(as_of)`. Le test `tests/test_no_lookahead.py` injecte des données futures absurdes (prix ×1000, retraitements ×10⁶, publications fictives) et vérifie qu'aucun signal ni score ne change.
- **Pas de biais du survivant en backtest.** L'univers est défini par des règles à chaque date, calculé sur une base de prix incluant les délistés (EODHD). Sinon, le rapport l'indique en tête (« résultats biaisés à la hausse »).
- **Pré-enregistrement.** Chaque signal a un signe attendu et un statut dans `config/signals.yaml`. Les règles de promotion et de rétrogradation sont écrites avant de voir les résultats. Tous les essais sont journalisés, et le Deflated Sharpe en tient compte.
- **Coûts réalistes.** Courtage, demi-spread par liquidité, taxes à l'achat (TTF 0,4 %, ITF, stamp duty).
- **Traçabilité.** Chaque exécution archive signaux, scores, configuration (empreinte) et version du code.

## Limites connues

1. **Pas encore d'exécution complète sur données réelles.** L'environnement de développement bloquait l'accès réseau. Les parseurs sont testés sur des réponses simulées. Le job `network-smoke` de la CI les a ensuite confrontés aux vraies API :
   - **yfinance** (prix d'AAPL et de LVMH) et **Wikipédia** (composition du S&P 500) : **OK** sur réponses réelles ;
   - **SEC** : en attente du secret `SEC_USER_AGENT` ;
   - **EODHD** et **Finnhub** : non testés (pas de clé).
2. **Aucun signal n'est encore validé par nos propres données.** Tous les signaux du score sont des « candidats » issus de la littérature, équipondérés a priori, et le rapport quotidien le dit. Le rapport de validation réel viendra avec les données.
3. **Mode gratuit (sans EODHD)** :
   - pas de délistés, donc un backtest biaisé à la hausse ;
   - des fondamentaux européens limités à environ 4 ans, avec une date de publication estimée ;
   - le STOXX 600 et le SBF 120 à fournir en CSV ;
   - yfinance est non officiel et sujet aux limitations de débit.
4. **Classification sectorielle actuelle**, non historisée (léger biais documenté).
5. **Livre S encore mince.** Initiés, short interest et actualité arrivent en Phases 2-3. Il est évalué à fréquence mensuelle en Phase 1.
6. **Probabilités, thèses et scénarios** : Phase 3 (LLM avec contrôle de fidélité aux sources).

## Bilan de la Phase 1

### Ce qui fonctionne

Vérifié par les tests automatisés, hors ligne :

- **Configuration centralisée**, validée au démarrage. Elle a déjà attrapé un vrai piège : la Norvège (`NO`) lue comme le booléen `false` par YAML.
- **Stockage bitemporel et `PitView`.** Le test d'empoisonnement du futur passe : aucune fuite d'information future.
- **Module 2**, calculé sur des cas à la main : Altman Z et Z'', Piotroski (9 critères), Beneish (8 variables), TTM avec T4 déduit de l'exercice, retraitements invisibles avant leur publication, exclusion des financières, valorisation bloquée si les devises diffèrent.
- **Module 3** : momentum (en sautant le dernier mois), momentum résiduel, EAR, avec une publication après la clôture traitée le lendemain.
- **Module 8** : la somme des contributions égale le score, le signe est inversé pour les signaux négatifs, les pénalités et l'exclusion pour liquidité s'appliquent.
- **Module 9** :
  - moteur avec coûts (TTF à l'achat seulement), délistés et décalage d'exécution ;
  - IC, Newey-West, Deflated Sharpe, walk-forward ;
  - sur un marché synthétique à vérité connue, le protocole **détecte** le signal planté et **ne promeut pas plus de 3 signaux sur ~30 quand tout est du bruit**, ce qui est le taux de faux positifs attendu au seuil t ≥ 2.
- **Pipeline de bout en bout** : rapport Markdown et HTML, changements par rapport à la veille attribués à une famille, alertes, journal chaîné (toute falsification ou suppression est détectée), engagement public.

### Ce qui ne fonctionne pas encore, ou n'est pas vérifié

- Pas d'exécution complète sur données réelles, donc aucun rapport de validation réel (voir « Limites connues », points 1 et 2).
- Le premier passage du job réseau a trouvé un vrai défaut : Wikipédia refusait (403) un User-Agent sans contact. Il est corrigé et vérifié.
- Le provider EODHD n'a jamais reçu de vraie réponse. Ses codes d'indices pour le STOXX 600 et le SBF 120 sont à confirmer.
- Performance : environ 1 à 2 s par date de décision pour 160 titres. Une validation US complète (1 000 titres × 15 ans) prendra de l'ordre de 20 à 40 minutes. C'est acceptable pour un travail ponctuel, à optimiser si besoin.

### Prochaines étapes

1. **Toi** : créer les secrets `SEC_USER_AGENT` et `SCANNER_DATA_KEY`, fusionner dans `main` pour activer le workflow quotidien, et fournir les CSV du STOXX 600 et du SBF 120 (ou souscrire EODHD).
2. Vérifier les parseurs sur les vraies API (job `network-smoke`), puis lancer la première **validation réelle** US et mettre à jour les statuts dans `config/signals.yaml`, avec changelog.
3. **Phase 2** : Module 4 (Form 4, 13F, short interest FINRA, positions courtes UE, initiés AMF) et Module 6 (régime macro avec millésimes ALFRED), palier 2 de l'univers.

## Avertissement

Projet personnel et éducatif. Rien ici ne constitue un conseil en investissement. L'outil
n'exécute aucun ordre.
