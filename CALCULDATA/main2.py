# -*- coding: utf-8 -*-
"""Programme principal ISO/TS 7849-2 : produit DataISO7849_2.json.

Méthode : même logique de sélection que ISO/TS 7849-1, avec deux différences
issues de la norme :

* le nombre initial de positions vient du tableau 1 de la partie 2, soit le
  double de celui de la partie 1 (10 positions pour une surface rayonnante
  inférieure à 1 m2) ;
* le critère d'arrêt (7.3) compare l'écart max/min, dans chaque bande de
  fréquence, au nombre de positions (et non à son double) ;
* le niveau de puissance acoustique est corrigé par le facteur de rayonnement,
  selon l'équation (15) de la norme.

Le facteur de rayonnement est calculé une seule fois, avant les tests, à partir
de tous les capteurs utilisables et des excitations listées dans
config.Excitations_RF. La même valeur sert ensuite à tous les tests et à toutes
les excitations.

Usage :
    python main2.py
"""

from __future__ import annotations

import sys

import calculs
import config
import pipeline


def nombre_capteurs_initial():
    """Nombre de capteurs de la combinaison initiale pour ISO/TS 7849-2."""
    if config.N_CAPTEURS_INIT_ISO2 is not None:
        return int(config.N_CAPTEURS_INIT_ISO2)
    return calculs.positions_initiales_table1(2)


def main():
    """Exécute la méthode ISO/TS 7849-2 et renvoie le code de sortie."""
    return pipeline.executer_en_ligne_de_commande(
        nom_methode="ISO7849_2",
        n_init=nombre_capteurs_initial(),
        cle_racine="DataISO7849_2",
        chemin_sortie=config.FICHIER_SORTIE_ISO2,
        avec_facteur_rayonnement=True,
        facteur_critere=config.FACTEUR_CRITERE_ISO2,
    )


if __name__ == "__main__":
    sys.exit(main())
