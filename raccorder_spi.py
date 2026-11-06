"""
Construit une série continue du SPI rendement total (CHF) depuis 1988 :

- jusqu'au 16 mai 2025 : historique de référence (data/reference/SPI_TR_historique.csv),
  repris du dépôt Financial-time-series-analysis ;
- ensuite : Yahoo Finance (^SSHI, data/SSHI.csv), dont l'historique ne remonte
  qu'à 2013 environ.

Avant de raccorder, les deux sources sont comparées sur leur période commune.
Si elles ne décrivent pas le même indice (par exemple SPI prix contre SPI
rendement total, ce qui crée un écart croissant avec les dividendes), le script
s'arrête sans toucher à data/SPI_TR.csv.

Aucune requête réseau : à lancer après telecharger.py.
"""
import sys

import pandas as pd

REFERENCE = "data/reference/SPI_TR_historique.csv"
YAHOO = "data/SSHI.csv"
SORTIE = "data/SPI_TR.csv"

MIN_JOURS_COMMUNS = 250      # au moins une année de recouvrement
TOL_NIVEAU = 0.01            # écart de niveau médian toléré (1 %)
TOL_DERIVE = 0.01            # dérive tolérée du ratio entre début et fin du recouvrement
TOL_JOUR = 0.005             # écart ponctuel « normal » (0,5 %)
MAX_JOURS_ABERRANTS = 0.02   # au plus 2 % de jours au-delà de TOL_JOUR


def charger(chemin):
    df = pd.read_csv(chemin, parse_dates=["Date"], index_col="Date")
    s = df["Close"].dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def verifier(ref, yahoo):
    communs = ref.index.intersection(yahoo.index)
    if len(communs) < MIN_JOURS_COMMUNS:
        return f"recouvrement trop court ({len(communs)} séances)"

    ratio = yahoo.loc[communs] / ref.loc[communs]
    med = ratio.median()
    debut, fin = ratio.iloc[:60].median(), ratio.iloc[-60:].median()
    aberrants = ((ratio / med - 1).abs() > TOL_JOUR).mean()

    print(f"Recouvrement : {len(communs)} séances, "
          f"{communs[0].date()} → {communs[-1].date()}")
    print(f"Ratio Yahoo/référence : médiane {med:.5f}, début {debut:.5f}, fin {fin:.5f}, "
          f"jours aberrants {aberrants:.2%}")

    if abs(med - 1) > TOL_NIVEAU:
        return f"niveaux différents (ratio médian {med:.4f}) : autre variante de l'indice ?"
    if abs(fin / debut - 1) > TOL_DERIVE:
        return f"dérive de {fin / debut - 1:+.2%} : variante prix contre rendement total ?"
    if aberrants > MAX_JOURS_ABERRANTS:
        return f"trop de jours divergents ({aberrants:.2%})"
    return None


def raccorder(ref, yahoo):
    """Garde la référence telle quelle, puis prolonge avec les rendements Yahoo."""
    jonction = ref.index[-1]
    if jonction not in yahoo.index:
        jonction = ref.index.intersection(yahoo.index)[-1]
    suite = yahoo[yahoo.index > jonction] * (ref.loc[jonction] / yahoo.loc[jonction])
    serie = pd.concat([ref[ref.index <= jonction], suite])
    source = pd.Series("reference", index=serie.index)
    source[serie.index > jonction] = "yahoo"
    return pd.DataFrame({"Close": serie.round(2), "Source": source}), jonction


if __name__ == "__main__":
    ref, yahoo = charger(REFERENCE), charger(YAHOO)
    probleme = verifier(ref, yahoo)
    if probleme:
        print(f"Raccordement refusé : {probleme}. {SORTIE} n'est pas modifié.")
        sys.exit(1)
    df, jonction = raccorder(ref, yahoo)
    df.index.name = "Date"
    df.to_csv(SORTIE)
    print(f"{SORTIE} : {len(df)} séances, {df.index[0].date()} → {df.index[-1].date()} "
          f"(jonction au {jonction.date()})")
