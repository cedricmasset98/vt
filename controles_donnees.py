"""
Contrôles bloquants des données, exécutés après les téléchargements et avant toute publication.

Si un contrôle critique échoue, le script se termine avec une erreur : le workflow s'arrête,
rien n'est enregistré ni publié, et le site garde la dernière version valide. GitHub envoie
alors une notification d'échec. Le prochain passage repartira des données encore enregistrées
dans le dépôt.

Contrôles critiques (bloquants) :
- fichiers lisibles, dates uniques et croissantes, pas de valeur manquante ni négative ;
- plages plausibles (USD/CHF, taux T-bill, SARON) et variations quotidiennes plausibles ;
- pour VT : cours ajusté jamais au-dessus du cours de clôture ;
- par rapport à la version enregistrée dans le dépôt (git HEAD) : aucune ligne perdue,
  dernière date jamais en recul, historique ancien inchangé (cours de clôture identiques,
  rendements ajustés identiques ; seuls les derniers jours peuvent être corrigés par Yahoo).

Avertissement seulement (non bloquant) : données de VT en retard de plus de 7 jours.
Seuils fixés très au-dessus des extrêmes historiques : VT +13,5 % (13.10.2008),
USD/CHF −16 % (16.01.2015, fin du taux plancher).
"""
import io
import subprocess
import sys
from datetime import date

import pandas as pd

RECENT_JOURS = 30          # Yahoo peut corriger les dernières séances ; l'historique plus ancien doit être stable
MAX_JOUR_VT = 0.25         # variation quotidienne maximale admise (cours ajusté)
MAX_JOUR_FX = 0.30
PLAGE_FX = (0.5, 2.0)      # CHF pour 1 USD
PLAGE_IRX = (-2.0, 25.0)   # % par an
PLAGE_SARON = (-2.0, 10.0)

erreurs = []


def controle(cond, message):
    if not cond:
        erreurs.append(message)
    return cond


def lire(nom, contenu=None):
    src = io.StringIO(contenu) if contenu is not None else f"data/{nom}.csv"
    return pd.read_csv(src, parse_dates=["Date"], index_col="Date")


def version_enregistree(nom):
    """Fichier tel qu'il est dans le dernier commit (None s'il n'existe pas encore)."""
    r = subprocess.run(["git", "show", f"HEAD:data/{nom}.csv"], capture_output=True, text=True)
    return lire(nom, r.stdout) if r.returncode == 0 and r.stdout.strip() else None


def structure(nom, df, colonnes):
    controle(len(df) > 0, f"{nom}: fichier vide")
    controle(df.index.is_unique, f"{nom}: {df.index.duplicated().sum()} date(s) en double")
    controle(df.index.is_monotonic_increasing, f"{nom}: dates non croissantes")
    for c in colonnes:
        controle(df[c].notna().all(), f"{nom}: {df[c].isna().sum()} valeur(s) manquante(s) dans {c}")


def stabilite(nom, df, colonne_niveau, colonne_rendement=None):
    """Compare l'historique ancien à la version enregistrée dans le dépôt."""
    ancien = version_enregistree(nom)
    if ancien is None:
        print(f"{nom}: pas de version enregistrée, comparaison ignorée")
        return
    controle(len(df) >= len(ancien), f"{nom}: {len(ancien) - len(df)} ligne(s) perdue(s) par rapport au dépôt")
    controle(df.index[-1] >= ancien.index[-1],
             f"{nom}: la dernière date recule ({df.index[-1].date()} < {ancien.index[-1].date()})")
    limite = ancien.index[-1] - pd.Timedelta(days=RECENT_JOURS)
    communs = ancien.index[ancien.index <= limite].intersection(df.index)
    controle(len(communs) >= len(ancien.index[ancien.index <= limite]),
             f"{nom}: des dates anciennes ont disparu")
    if len(communs) > 1:
        a, n = ancien.loc[communs, colonne_niveau], df.loc[communs, colonne_niveau]
        ecart = ((n - a).abs() / a.abs().clip(lower=1e-9)).max()
        controle(ecart < 1e-6, f"{nom}: historique ancien modifié ({colonne_niveau}, écart relatif max {ecart:.2e})")
        if colonne_rendement:
            ra = ancien.loc[communs, colonne_rendement].pct_change().dropna()
            rn = df.loc[communs, colonne_rendement].pct_change().dropna()
            ecart = (rn - ra).abs().max()
            controle(ecart < 1e-6, f"{nom}: rendements anciens modifiés ({colonne_rendement}, écart max {ecart:.2e})")


# ---------------------------------------------------------------- VT
vt = lire("VT")
structure("VT", vt, ["Close", "Adj Close"])
controle((vt[["Close", "Adj Close"]] > 0).all().all(), "VT: cours nul ou négatif")
r = vt["Adj Close"].pct_change().dropna()
controle((r.abs() < MAX_JOUR_VT).all(),
         f"VT: variation quotidienne aberrante {r.abs().max():.1%} le {r.abs().idxmax().date()}")
controle((vt["Adj Close"] <= vt["Close"] * 1.001).all(), "VT: cours ajusté supérieur au cours de clôture")
stabilite("VT", vt, "Close", "Adj Close")
retard = (pd.Timestamp(date.today()) - vt.index[-1]).days
if retard > 7:
    print(f"::warning::VT: dernière séance le {vt.index[-1].date()} ({retard} jours), Yahoo ne répond peut-être plus")

# ---------------------------------------------------------------- USD/CHF
fx = lire("CHFX")
structure("CHFX", fx, ["Close"])
controle(fx["Close"].between(*PLAGE_FX).all(), f"CHFX: valeur hors de la plage {PLAGE_FX}")
rf = fx["Close"].pct_change().dropna()
controle((rf.abs() < MAX_JOUR_FX).all(),
         f"CHFX: variation quotidienne aberrante {rf.abs().max():.1%} le {rf.abs().idxmax().date()}")
stabilite("CHFX", fx, "Close")
controle(fx.index[0] <= vt.index[0], "CHFX: l'historique commence après VT")

# ---------------------------------------------------------------- T-bill 13 semaines
irx = lire("IRX")
structure("IRX", irx, ["Close"])
controle(irx["Close"].between(*PLAGE_IRX).all(), f"IRX: valeur hors de la plage {PLAGE_IRX}")
stabilite("IRX", irx, "Close")
controle(irx.index[0] <= vt.index[0], "IRX: l'historique commence après VT")

# ---------------------------------------------------------------- SARON (facultatif)
try:
    saron = pd.read_csv("data/SARON.csv", dtype={"Date": str}, index_col="Date")["SARON"]
    controle(saron.index.is_unique and saron.index.is_monotonic_increasing, "SARON: mois en double ou non croissants")
    controle(saron.between(*PLAGE_SARON).all(), f"SARON: valeur hors de la plage {PLAGE_SARON}")
    controle(saron.index[0] <= vt.index[0].strftime("%Y-%m"), "SARON: la série commence après VT")
except FileNotFoundError:
    print("SARON: fichier absent (le site affichera les ratios CHF sans taux sans risque)")

# ---------------------------------------------------------------- verdict
if erreurs:
    for e in erreurs:
        print(f"::error::{e}")
    print(f"{len(erreurs)} contrôle(s) critique(s) en échec : publication interrompue, le site garde la dernière version valide.")
    sys.exit(1)
print(f"Contrôles des données : OK (VT {len(vt)} séances jusqu'au {vt.index[-1].date()}, "
      f"USD/CHF jusqu'au {fx.index[-1].date()}, T-bill jusqu'au {irx.index[-1].date()})")
