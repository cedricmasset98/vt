"""
Met à jour le taux sans risque en francs suisses : SARON, moyenne mensuelle publiée
par la Banque nationale suisse (cube « zimoma » du portail data.snb.ch, série SARON).

La série mensuelle remonte à juin 1999 et couvre donc tout l'historique de VT
(lancé en juin 2008), sans raccord avec un autre taux.

Le script est conçu pour ne jamais casser la mise à jour quotidienne :

- aucune requête si le dernier mois publié est déjà dans data/SARON.csv
  (la BNS publie le mois écoulé dans les premiers jours ouvrables du mois suivant) ;
- la réponse est contrôlée (identifiant du cube, colonnes, plage des valeurs,
  mois consécutifs, couverture du début de VT) avant d'écraser quoi que ce soit ;
- en cas d'échec réseau ou de contrôle, l'ancien fichier est conservé tel quel
  et le script se termine sans erreur : le site utilise le dernier taux connu.

Pas de dépendance supplémentaire : urllib (bibliothèque standard) et pandas.
"""
import io
import os
import sys
import urllib.request
from datetime import date

import pandas as pd

URL = "https://data.snb.ch/api/cube/zimoma/data/csv/en"
CUBE = "zimoma"
SERIE = "SARON"
CHEMIN = "data/SARON.csv"
DEBUT_REQUIS = "2008-06"         # premier mois de VT
PLAGE = (-2.0, 10.0)             # % par an ; le SARON a été négatif de 2015 à 2022
TIMEOUT = 60


def mois_attendu():
    """Dernier mois qui peut être publié : le mois précédant le mois en cours."""
    t = date.today().replace(day=1)
    return (pd.Period(t, "M") - 1).strftime("%Y-%m")


def lire_csv_bns(texte):
    """Lit le CSV de la BNS : deux lignes de métadonnées, une ligne vide, puis Date;D0;Value."""
    lignes = texte.lstrip("﻿").splitlines()
    meta = {}
    for k, l in enumerate(lignes):
        champs = [c.strip('"') for c in l.split(";")]
        if champs[0] == "Date":
            df = pd.read_csv(io.StringIO("\n".join(lignes[k:])), sep=";", dtype={"Date": str, "D0": str})
            return meta, df
        if len(champs) >= 2:
            meta[champs[0]] = champs[1]
    raise ValueError("en-tête Date;D0;Value introuvable (réponse inattendue du portail)")


def extraire(texte):
    """Renvoie la série SARON mensuelle (index YYYY-MM, valeurs en % par an), contrôlée."""
    meta, df = lire_csv_bns(texte)
    if meta.get("CubeId") != CUBE:
        raise ValueError(f"cube inattendu : {meta.get('CubeId')!r}")
    if list(df.columns) != ["Date", "D0", "Value"]:
        raise ValueError(f"colonnes inattendues : {list(df.columns)}")
    s = df[df["D0"] == SERIE].dropna(subset=["Value"])
    s = pd.Series(pd.to_numeric(s["Value"]).values, index=s["Date"].values, name="SARON").sort_index()
    if s.empty:
        raise ValueError("série SARON absente")
    mois = pd.PeriodIndex(s.index, freq="M").asi8   # nombre de mois depuis 1970
    if len(mois) > 1 and (mois[1:] - mois[:-1] != 1).any():
        raise ValueError("mois manquants ou en double dans la série")
    if s.index[0] > DEBUT_REQUIS:
        raise ValueError(f"la série commence en {s.index[0]}, après le lancement de VT ({DEBUT_REQUIS})")
    if not s.between(*PLAGE).all():
        raise ValueError(f"valeurs hors de la plage {PLAGE} : {s[~s.between(*PLAGE)].to_dict()}")
    meta_pub = meta.get("PublishingDate", "?")
    return s, meta_pub


def ancien():
    if not os.path.exists(CHEMIN):
        return None
    return pd.read_csv(CHEMIN, dtype={"Date": str}, index_col="Date")["SARON"]


def main():
    vieux = ancien()
    attendu = mois_attendu()
    if vieux is not None and vieux.index[-1] >= attendu:
        print(f"SARON: déjà à jour ({vieux.index[-1]}), aucune requête")
        return
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "vt-dashboard (github.com/cedricmasset98/vt)"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as rep:
            texte = rep.read().decode("utf-8")
        s, publie = extraire(texte)
        if vieux is not None:
            if s.index[-1] < vieux.index[-1]:
                raise ValueError(f"la série reçue s'arrête en {s.index[-1]}, avant le fichier existant ({vieux.index[-1]})")
            commun = vieux.index.intersection(s.index)
            ecart = (s.loc[commun] - vieux.loc[commun]).abs().max()
            if ecart > 0.05:   # révision de plus de 5 points de base : on l'accepte mais on la signale
                print(f"SARON: attention, révision de l'historique (écart max {ecart:.3f} point de %)")
    except Exception as e:  # réseau, format, contrôle : on garde l'ancien fichier
        print(f"SARON: mise à jour ignorée, ancien fichier conservé ({type(e).__name__}: {e})")
        return
    s.index.name = "Date"
    s.to_csv(CHEMIN)
    print(f"SARON: {len(s)} mois, {s.index[0]} à {s.index[-1]} (publication BNS {publie})")


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    if len(sys.argv) == 2:          # usage local : python telecharger_snb.py fichier_bns.csv
        s, publie = extraire(open(sys.argv[1], encoding="utf-8").read())
        s.index.name = "Date"
        s.to_csv(CHEMIN)
        print(f"SARON (fichier local): {len(s)} mois, {s.index[0]} à {s.index[-1]} (publication BNS {publie})")
    else:
        main()
