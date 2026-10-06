# -*- coding: utf-8 -*-
"""Programme principal ISO/TS 7849-1 : produit DataISO7849_1.json.

Méthode : pour chaque test, une combinaison de capteurs est constituée à partir
du nombre initial de positions donné par le tableau 1 de la norme (5 positions
pour une surface rayonnante inférieure à 1 m2), puis le niveau de puissance
acoustique est estimé sans facteur de rayonnement, selon l'équation (12) de la
norme.

Critère d'arrêt de la sélection (7.3) : des positions sont ajoutées tant que
l'écart entre niveaux vibratoires maximal et minimal dépasse le double du
nombre de positions.

Usage :
    python main1.py

Tous les paramètres (nombre de tests, capteurs exclus, constantes) se règlent
dans config.py. Le fichier de mesures n'est jamais modifié.
"""

from __future__ import annotations

import sys

import calculs
import config
import pipeline


def nombre_capteurs_initial():
    """Nombre de capteurs de la combinaison initiale pour ISO/TS 7849-1."""
    if config.N_CAPTEURS_INIT_ISO1 is not None:
        return int(config.N_CAPTEURS_INIT_ISO1)
    return calculs.positions_initiales_table1(1)


def main():
    """Exécute la méthode ISO/TS 7849-1 et renvoie le code de sortie."""
    return pipeline.executer_en_ligne_de_commande(
        nom_methode="ISO7849_1",
        n_init=nombre_capteurs_initial(),
        cle_racine="DataISO7849_1",
        chemin_sortie=config.FICHIER_SORTIE_ISO1,
        avec_facteur_rayonnement=False,
        facteur_critere=config.FACTEUR_CRITERE_ISO1,
    )


if __name__ == "__main__":
    sys.exit(main())
