<!-- Généré par `scanner demo --validation` (marché synthétique, graine 7, 240 titres). Régénérable à l'identique. -->

# Rapport de validation — US, 2015-06-01 → 2026-06-30

*Généré le 2026-09-23T15:51:17+00:00 UTC · configuration `e2f45062fa3a9609` · essai n° 1 sur ces données.*

> **DONNÉES SYNTHÉTIQUES.** Ce rapport vérifie la mécanique du protocole (détection d'un signal planté, rejet d'un signal inopérant, absence de biais d'anticipation). Ses chiffres n'ont **aucune valeur économique** et ne disent rien des marchés réels.

## Protocole

- Données : synthétique (générateur interne). Base de prix incluant les délistés : **oui**.
- Période de conception : 2015-06-01 → 2020-01-01 ; **hors échantillon** : 2020-01-01 → 2026-06-30 (consulté une fois par décision).
- Décisions en fin de mois, exécution à la clôture de la séance suivante (décalage 1 j), univers défini par des règles à chaque date.
- Signaux normalisés par secteur x région et orientés selon leur signe pré-enregistré ; IC de rang, t de Newey-West (chevauchement des horizons).
- Portefeuilles : quintile supérieur équipondéré (long) et quintile inférieur (short papier), nets de courtage, demi-spread et taxes (TTF 0,4 %…).
- Règles de décision : promotion si IC > 0 et t ≥ 2 (≥ 3 pour un signal en observation) et spread net > 0 ; rétrogradation si IC < 0 et t ≤ -1 ; sinon maintien.

## Signaux

| Signal | Statut actuel | Horizon | IC conception | IC hors éch. | t (NW) | % IC > 0 | Dates | Spread Q5-Q1 ann. | Décision |
|---|---|---|---|---|---|---|---|---|---|
| F-REV — Révisions de consensus | observation | 21 j | n.d. | n.d. | n.d. | n.d. | 0 | n.d. | **DONNÉES INSUFFISANTES** — 0 dates hors échantillon (< 24) |
| F-SUE — Surprise de BPA (SUE, sans consensus) | core_candidate | 21 j | 0.028 | 0.017 | 1.64 | 55.1 % | 78 | 4.8 % | **MAINTENIR** — preuve insuffisante (IC +0.017, t = 1.64 < 2) |
| F-FCFY — FCF / EV | core_candidate | 63 j | 0.094 | 0.031 | 1.62 | 61.0 % | 77 | 2.7 % | **MAINTENIR** — preuve insuffisante (IC +0.031, t = 1.62 < 2) |
| Q-RESMOM — Momentum résiduel | core_candidate | 63 j | 0.031 | 0.017 | 1.27 | 53.2 % | 77 | 1.9 % | **MAINTENIR** — preuve insuffisante (IC +0.017, t = 1.27 < 2) |
| Q-LOWVOL — Faible volatilité | core_candidate | 63 j | 0.018 | 0.003 | 0.21 | 49.4 % | 77 | -8.1 % | **MAINTENIR** — preuve insuffisante (IC +0.003, t = 0.21 < 2) |
| Q-EAR — Réaction aux résultats (EAR 3 jours) | core_candidate | 21 j | -0.010 | -0.003 | -0.25 | 51.3 % | 78 | 0.5 % | **MAINTENIR** — preuve insuffisante (IC -0.003, t = -0.25 < 2) |
| Q-ABVOL — Volume anormal | core_candidate | 21 j | 0.026 | -0.004 | -0.47 | 52.6 % | 78 | 0.7 % | **MAINTENIR** — preuve insuffisante (IC -0.004, t = -0.47 < 2) |
| F-EY — EBIT / EV | core_candidate | 63 j | 0.060 | -0.011 | -0.65 | 50.6 % | 77 | -0.9 % | **MAINTENIR** — preuve insuffisante (IC -0.011, t = -0.65 < 2) |
| Q-STREV — Retournement court terme 1 mois | observation | 21 j | -0.009 | -0.009 | -0.98 | 47.4 % | 78 | -6.2 % | **MAINTENIR** — preuve insuffisante (IC -0.009, t = -0.98 < 3) |
| Q-TREND — Trend Template (Minervini) | observation | 21 j | 0.028 | 0.030 | 3.04 | 61.5 % | 78 | 8.5 % | **PROMOUVOIR (candidat)** — IC +0.030, t = 3.04 ≥ 3 |
| F-LEV — Levier financier | core_candidate | 126 j | 0.155 | 0.102 | 6.54 | 91.9 % | 74 | 14.9 % | **PROMOUVOIR (validé)** — IC +0.102, t = 6.54 ≥ 2 |
| F-COVER — Couverture des intérêts | core_candidate | 126 j | 0.153 | 0.099 | 5.06 | 83.8 % | 74 | 12.8 % | **PROMOUVOIR (validé)** — IC +0.099, t = 5.06 ≥ 2 |
| F-ROIC — ROIC | core_candidate | 126 j | 0.155 | 0.095 | 4.73 | 83.8 % | 74 | 11.9 % | **PROMOUVOIR (validé)** — IC +0.095, t = 4.73 ≥ 2 |
| Q-MOM-6-1 — Momentum 6-1 mois | core_candidate | 21 j | 0.019 | 0.040 | 4.02 | 67.9 % | 78 | 12.3 % | **PROMOUVOIR (validé)** — IC +0.040, t = 4.02 ≥ 2 |
| F-ISSUE — Émissions nettes / rachats | core_candidate | 63 j | 0.075 | 0.056 | 3.98 | 71.4 % | 77 | 13.8 % | **PROMOUVOIR (validé)** — IC +0.056, t = 3.98 ≥ 2 |
| F-ACCR — Accruals | core_candidate | 63 j | 0.090 | 0.066 | 3.78 | 71.4 % | 77 | 14.0 % | **PROMOUVOIR (validé)** — IC +0.066, t = 3.78 ≥ 2 |
| F-GP — Rentabilité brute / actifs | core_candidate | 63 j | 0.122 | 0.063 | 3.72 | 68.8 % | 77 | 13.2 % | **PROMOUVOIR (validé)** — IC +0.063, t = 3.72 ≥ 2 |
| F-CBOP — Rentabilité opérationnelle cash (proxy) | core_candidate | 63 j | 0.119 | 0.064 | 3.65 | 67.5 % | 77 | 13.6 % | **PROMOUVOIR (validé)** — IC +0.064, t = 3.65 ≥ 2 |
| Q-52WH — Proximité du plus haut 52 semaines | core_candidate | 21 j | 0.028 | 0.033 | 3.61 | 61.5 % | 78 | 11.2 % | **PROMOUVOIR (validé)** — IC +0.033, t = 3.61 ≥ 2 |
| Q-MOM-12-1 — Momentum 12-1 mois | core_candidate | 63 j | 0.036 | 0.047 | 3.48 | 74.0 % | 77 | 9.1 % | **PROMOUVOIR (validé)** — IC +0.047, t = 3.48 ≥ 2 |
| Q-RS — Force relative 3 mois vs secteur | core_candidate | 21 j | 0.017 | 0.022 | 2.71 | 60.3 % | 78 | 8.8 % | **PROMOUVOIR (validé)** — IC +0.022, t = 2.71 ≥ 2 |
| F-DPROF — Croissance de la rentabilité | core_candidate | 126 j | 0.079 | 0.056 | 2.62 | 77.0 % | 74 | 6.6 % | **PROMOUVOIR (validé)** — IC +0.056, t = 2.62 ≥ 2 |
| Q-INDMOM — Momentum sectoriel | core_candidate | 21 j | 0.019 | 0.034 | 2.53 | 56.4 % | 78 | 9.6 % | **PROMOUVOIR (validé)** — IC +0.034, t = 2.53 ≥ 2 |
| F-PIOT — Piotroski F-Score | core_candidate | 63 j | 0.063 | 0.024 | 2.39 | 63.6 % | 77 | 3.3 % | **PROMOUVOIR (validé)** — IC +0.024, t = 2.39 ≥ 2 |
| F-AGR — Croissance des actifs | core_candidate | 63 j | 0.056 | 0.035 | 2.31 | 62.3 % | 77 | 8.3 % | **PROMOUVOIR (validé)** — IC +0.035, t = 2.31 ≥ 2 |
| Q-VCP — Contraction de volatilité (proxy VCP) | observation | 21 j | -0.021 | -0.011 | -1.23 | 43.6 % | 78 | -3.1 % | **RÉTROGRADER (observation)** — IC de mauvais signe (-0.011, t = -1.23) |
| F-GM-STAB — Stabilité de la marge brute (5 ans) | core_candidate | 126 j | 0.013 | -0.042 | -1.97 | 32.4 % | 74 | -7.9 % | **RÉTROGRADER (observation)** — IC de mauvais signe (-0.042, t = -1.97) |
| F-PE-HIST — Rendement bénéficiaire vs historique propre | observation | 126 j | 0.006 | -0.040 | -2.45 | 32.4 % | 74 | -5.2 % | **RÉTROGRADER (observation)** — IC de mauvais signe (-0.040, t = -2.45) |
| F-ROIC-STAB — Stabilité du ROIC (5 ans) | core_candidate | 126 j | 0.012 | -0.050 | -2.68 | 25.7 % | 74 | -6.8 % | **RÉTROGRADER (observation)** — IC de mauvais signe (-0.050, t = -2.68) |
| F-BM — Book-to-market | core_candidate | 63 j | -0.006 | -0.043 | -3.17 | 29.9 % | 77 | -7.5 % | **RÉTROGRADER (observation)** — IC de mauvais signe (-0.043, t = -3.17) |

### Décroissance de l'IC hors échantillon selon l'horizon

| Signal | 1 j | 5 j | 21 j | 63 j | 126 j | 252 j |
|---|---|---|---|---|---|---|
| Q-MOM-12-1 | -0.003 | 0.016 | 0.040 | 0.047 | 0.053 | 0.069 |
| Q-MOM-6-1 | -0.007 | 0.008 | 0.040 | 0.037 | 0.041 | 0.046 |
| Q-RESMOM | 0.000 | 0.007 | 0.012 | 0.017 | 0.023 | 0.033 |
| Q-INDMOM | 0.009 | 0.010 | 0.034 | 0.025 | 0.014 | 0.010 |
| Q-RS | 0.004 | 0.003 | 0.022 | 0.047 | 0.046 | 0.048 |
| Q-52WH | 0.005 | 0.013 | 0.033 | 0.046 | 0.048 | 0.055 |
| Q-LOWVOL | -0.001 | 0.009 | 0.003 | 0.003 | 0.005 | 0.002 |
| Q-ABVOL | 0.012 | 0.006 | -0.004 | 0.011 | 0.007 | -0.002 |
| Q-EAR | -0.007 | -0.006 | -0.003 | -0.016 | -0.011 | 0.009 |
| Q-TREND | -0.009 | 0.006 | 0.030 | 0.043 | 0.056 | 0.058 |
| Q-VCP | 0.008 | 0.003 | -0.011 | -0.022 | -0.011 | -0.014 |
| Q-STREV | -0.004 | -0.007 | -0.009 | -0.032 | -0.035 | -0.030 |
| F-GP | -0.018 | 0.008 | 0.039 | 0.063 | 0.096 | 0.135 |
| F-CBOP | -0.018 | 0.009 | 0.040 | 0.064 | 0.095 | 0.137 |
| F-ROIC | -0.018 | 0.008 | 0.039 | 0.064 | 0.095 | 0.135 |
| F-ROIC-STAB | -0.028 | -0.005 | -0.028 | -0.038 | -0.050 | -0.082 |
| F-GM-STAB | -0.025 | -0.002 | -0.018 | -0.026 | -0.042 | -0.076 |
| F-ACCR | -0.014 | 0.015 | 0.039 | 0.066 | 0.097 | 0.133 |
| F-EY | 0.005 | -0.003 | -0.006 | -0.011 | -0.009 | 0.002 |
| F-FCFY | 0.000 | 0.004 | 0.019 | 0.031 | 0.049 | 0.072 |
| F-BM | 0.006 | -0.006 | -0.030 | -0.043 | -0.058 | -0.071 |
| F-PE-HIST | 0.002 | -0.017 | -0.026 | -0.033 | -0.040 | -0.048 |
| F-ISSUE | -0.007 | 0.025 | 0.034 | 0.056 | 0.083 | 0.131 |
| F-AGR | -0.002 | 0.003 | 0.019 | 0.035 | 0.059 | 0.088 |
| F-DPROF | 0.005 | -0.001 | 0.018 | 0.036 | 0.056 | 0.082 |
| F-PIOT | -0.004 | 0.003 | 0.013 | 0.024 | 0.037 | 0.074 |
| F-LEV | -0.017 | 0.005 | 0.041 | 0.069 | 0.102 | 0.144 |
| F-COVER | -0.019 | 0.011 | 0.042 | 0.067 | 0.099 | 0.138 |
| F-SUE | 0.000 | 0.008 | 0.017 | 0.023 | 0.010 | 0.009 |
| F-REV | n.d. | n.d. | n.d. | n.d. | n.d. | n.d. |

## Portefeuilles (nets de coûts)

| Portefeuille | Période | Rend. ann. | Vol. ann. | Sharpe | Sortino | Drawdown max | % jours > 0 | Deflated Sharpe | Rotation ann. |
|---|---|---|---|---|---|---|---|---|---|
| Univers équipondéré (sans coûts) | conception | 12.4 % | 18.8 % | 0.72 | 1.04 | -23.8 % | 51.7 % | 0.94 | n.d. |
| Univers équipondéré (sans coûts) | hors éch. | -2.7 % | 18.1 % | -0.06 | -0.09 | -55.0 % | 50.8 % | 0.43 | n.d. |
| Momentum 12-1 seul (long, net) | conception | 14.9 % | 19.3 % | 0.82 | 1.19 | -23.6 % | 52.0 % | 0.96 | n.d. |
| Momentum 12-1 seul (long, net) | hors éch. | 2.6 % | 19.1 % | 0.23 | 0.33 | -41.0 % | 50.4 % | 0.73 | n.d. |
| Livre S — long (net) | conception | 16.9 % | 19.4 % | 0.90 | 1.32 | -22.4 % | 52.9 % | 0.97 | 7.83 |
| Livre S — long (net) | hors éch. | -2.8 % | 18.9 % | -0.06 | -0.08 | -55.0 % | 50.8 % | 0.44 | 7.83 |
| Livre S — long/short papier (net) | conception | 12.0 % | 8.8 % | 1.33 | 2.01 | -8.4 % | 53.2 % | 1.00 | n.d. |
| Livre S — long/short papier (net) | hors éch. | 5.0 % | 9.1 % | 0.58 | 0.83 | -19.3 % | 52.6 % | 0.94 | n.d. |
| Livre M — long (net) | conception | 18.1 % | 17.9 % | 1.02 | 1.51 | -24.4 % | 52.5 % | 0.99 | 1.67 |
| Livre M — long (net) | hors éch. | 0.8 % | 17.5 % | 0.13 | 0.19 | -42.1 % | 49.5 % | 0.64 | 1.67 |
| Livre M — long/short papier (net) | conception | 12.6 % | 8.9 % | 1.39 | 2.10 | -8.5 % | 54.3 % | 1.00 | n.d. |
| Livre M — long/short papier (net) | hors éch. | 6.5 % | 8.8 % | 0.76 | 1.12 | -15.4 % | 52.3 % | 0.98 | n.d. |
| Livre L — long (net) | conception | 20.9 % | 18.0 % | 1.14 | 1.69 | -23.8 % | 53.1 % | 0.99 | 1.28 |
| Livre L — long (net) | hors éch. | 0.6 % | 17.6 % | 0.12 | 0.17 | -46.3 % | 50.1 % | 0.63 | 1.28 |
| Livre L — long/short papier (net) | conception | 16.1 % | 8.7 % | 1.76 | 2.74 | -8.0 % | 54.9 % | 1.00 | n.d. |
| Livre L — long/short papier (net) | hors éch. | 5.6 % | 8.9 % | 0.66 | 0.96 | -13.9 % | 53.3 % | 0.96 | n.d. |

*Deflated Sharpe : probabilité que le Sharpe dépasse le maximum attendu par chance après 1 essai(s) sur ces données (Bailey & López de Prado 2014). Une valeur < 0,95 signifie que la performance n'est pas distinguable du hasard.*

## Walk-forward : pondération par l'IC passé vs équipondération (livre M)

- IC hors échantillon, pondération apprise (rétrécie vers 1/N) : 0.055 (t = 4.24)
- IC hors échantillon, équipondération : 0.051 (t = 3.92)
- Écart : 0.005 (t = 1.92), 8 périodes de test.
- Conclusion : la pondération apprise ne fait pas significativement mieux : **on garde 1/N**.

## Limites

- Les secteurs sont ceux d'aujourd'hui (classification non historisée).
- Taux de change de repli fixes pour les filtres de liquidité en backtest.
- Le livre S est évalué à fréquence mensuelle en Phase 1 (hebdomadaire prévue).
- Les décisions ci-dessus sont des **recommandations** : le changement de statut d'un signal se fait dans `config/signals.yaml`, avec une entrée de changelog.
