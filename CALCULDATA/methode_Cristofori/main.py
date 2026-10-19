# -*- coding: utf-8 -*-
"""Programme principal : méthode Cristofori_Mucchi.

Usage (depuis n'importe quel dossier) :
    python main.py                 calcul + enregistrement JSON + figures
    python main.py --sans-figures  calcul et JSON seulement

Codes de sortie : 0 succès, 1 données/configuration/calcul invalides,
2 sélection impossible.
"""

from __future__ import annotations

import os
import sys

# Le dossier du programme est prioritaire : aucun module d'un autre dossier
# (notamment les méthodes ISO 7849) ne peut être importé par erreur.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import calculs
import config
import data_io
import methode
import selection_capteurs as selection


def main(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    avec_figures = "--sans-figures" not in arguments
    try:
        resultats = methode.executer()
        chemin = data_io.ecrire_resultats(config.FICHIER_SORTIE, resultats)
        print("")
        print("Fichier de résultats écrit : %s" % chemin)
        if avec_figures:
            import figures
            figures.tracer(resultats)
    except (data_io.ErreurDonnees, methode.ErreurConfiguration,
            calculs.ErreurCalcul) as err:
        print("\nERREUR : %s" % err, file=sys.stderr)
        return 1
    except selection.SelectionImpossible as err:
        print("\nERREUR de sélection : %s" % err, file=sys.stderr)
        return 2
    print("\nTerminé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
