# Scanner d'actions quotidien (daily-stock-scanner)

Outil personnel de sélection d'actions. Chaque jour, avant l'ouverture des marchés, il combine :
- l'analyse fondamentale ;
- l'analyse quantitative et technique ;
- les flux « smart money » (initiés, 13F, short interest) ;
- l'actualité, avec une analyse par LLM ;
- le contexte macro.

Il produit un classement argumenté (thèse, catalyseurs, scénarios, risques) sur trois horizons : swing, moyen terme et long terme. Il mesure aussi honnêtement sa propre performance dans le temps.

## Statut

**Phase 0 : recherche et architecture, en attente de validation.** Aucun code n'est encore écrit.

| Document | Contenu |
|---|---|
| [`research_notes.md`](research_notes.md) | Étape 0 : synthèse critique des références (factor investing, quant, macro, value, CAN SLIM, anomalies, LLM), ce qui est prouvé et ce qui ne l'est pas, et la traduction en signaux |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Plan d'architecture : sources et budget vérifiés, univers, modèle de données anti-look-ahead, scoring, validation, pipeline LLM, automatisation, phases, points à valider |

Les sections installation, configuration des API, lancement et limites connues seront complétées à partir de la Phase 1.

## Avertissement

Projet personnel et éducatif. Rien ici ne constitue un conseil en investissement. L'outil n'exécute aucun ordre.
