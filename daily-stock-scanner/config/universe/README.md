# Compositions d'indices et listes de référence

Le scanner cherche la composition de chaque indice du palier 1 dans l'ordre défini par
`config/sources.yaml` (`priority.constituents`) :

1. **EODHD** (si `EODHD_API_KEY` est défini). La couverture des compositions varie selon les indices : à vérifier sur ton compte.
2. **Fichiers de ce dossier** : `SP500.csv`, `NDX100.csv`, `STOXX600.csv`, `SBF120.csv`.
3. **Wikipédia** : S&P 500 et Nasdaq-100 uniquement. Les tableaux du STOXX 600 et du SBF 120 n'y sont pas assez fiables.

Sans clé EODHD, **le STOXX 600 et le SBF 120 nécessitent un fichier CSV ici**. Sinon, ils sont
signalés « INDISPONIBLE » dans le rapport et l'Europe n'est pas couverte.

## Format

```csv
# commentaire libre (source, date de la liste)
symbol,name
MC.PA,LVMH
SAP.XETRA,SAP
ASML.AS,ASML Holding
```

Les symboles suivent la convention interne `TICKER.PLACE`, avec les codes de place d'EODHD : `US`, `PA`, `XETRA`, `AS`, `LSE`, `SW`, `MI`, `MC`, `BR`, `ST`, `CO`, `HE`, `OL`, `LS`, `VI`, `IR`.

## Listes optionnelles

- `srd_eligible.csv` (colonne `symbol`) : valeurs françaises éligibles au SRD (liste publiée par Euronext). Sans ce fichier, l'éligibilité est « inconnue ».
- `ttf_list.csv` (colonne `symbol`) : liste officielle annuelle des sociétés soumises à la TTF. Sans ce fichier, on l'approche par « siège en France et capitalisation > 1 Md€ ».

Ces listes changent dans le temps. Date-les dans un commentaire en tête de fichier.
