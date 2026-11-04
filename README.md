# vt
## Contenu

- `data/` : historiques quotidiens Yahoo Finance (VT, USD/CHF, T-bill 13 semaines), mis à jour chaque soir de semaine par GitHub Actions, de façon incrémentale (`telecharger.py`).
- `data/SARON.csv` : taux sans risque en francs (SARON, moyenne mensuelle depuis 1999), source Banque nationale suisse (data.snb.ch, cube `zimoma`), mis à jour par `telecharger_snb.py`. Une seule requête par mois au plus ; si le portail ne répond pas ou si la réponse échoue aux contrôles, l'ancien fichier est conservé et la mise à jour quotidienne continue. Utilisé pour le ratio de Sharpe en CHF (dashboard et rapport).
- `docs/` : tableau de bord GitHub Pages (https://cedricmasset.ch/vt/), généré par `build_site.py` à partir de `site/index.template.html`, des CSV et de `report/analysis_results.json` (calculs lourds faits par `analysis.py`). Graphiques : Apache ECharts, hébergé dans `site/vendor/` (licence Apache 2.0).
- `report/VT_analysis.pdf` : analyse complète de VT, en anglais (rendement et risque, distribution, efficience de marché, horizon de l'investisseur, perspective CHF), régénérée à partir des CSV par `analysis.py` et mise en page en LaTeX (`report/template.tex`, source `report/VT_analysis.tex` utilisable dans Overleaf), sans requête supplémentaire vers Yahoo.

- `kelly.py` : critère de Kelly, simulation de portefeuilles à levier (financement par morceaux, coûts, insolvabilité, marge) et décomposition du volatility drag, utilisés par la section 4.5 du rapport. Tests : `python tests/test_kelly.py`.

## Mise à jour automatique et contrôles

Le workflow `.github/workflows/donnees.yml` tourne chaque nuit de semaine (GitHub décale souvent les tâches planifiées de quelques heures). Ordre des étapes : téléchargements, `controles_donnees.py`, tests, vérification de syntaxe, rapport, site, enregistrement.

- `controles_donnees.py` bloque la publication si les données semblent corrompues : dates en double ou non croissantes, valeurs manquantes, plages ou variations quotidiennes aberrantes, lignes perdues ou historique ancien modifié par rapport à la version enregistrée. En cas d'échec, rien n'est publié, le site garde la dernière version valide et GitHub envoie une notification.
- Un seul passage à la fois (`concurrency`) ; avant d'enregistrer, le workflow se recale sur la branche si elle a avancé entre-temps.

## Mise à jour trimestrielle de la validation Vanguard

Ajouter dans `data/reference/` un fichier `vanguard_vt_trailing_AAAA-MM-JJ.csv` (date de fin de trimestre, mêmes colonnes que le fichier existant, chiffres de la fiche Vanguard F3141). Le fichier le plus récent est utilisé automatiquement par le rapport et le site.
