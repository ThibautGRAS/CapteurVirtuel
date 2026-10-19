# -*- coding: utf-8 -*-
"""Paramètres de configuration de la méthode Cristofori_Mucchi.

Ce fichier est le SEUL à modifier pour une étude courante. Il est propre à la
méthode Cristofori_Mucchi : le dossier methode_Cristofori est autonome et ne
dépend d'aucun fichier des méthodes ISO 7849-1 / ISO 7849-2.
Aucune valeur métier n'est codée en dur dans les autres modules.
"""

import os

# Dossier du programme : les chemins relatifs ci-dessous y sont résolus, quel
# que soit le dossier depuis lequel le programme est lancé.
DOSSIER_PROGRAMME = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# 1. Fichiers
# ---------------------------------------------------------------------------

#: Fichier de mesures d'entrée (jamais modifié par le programme).
FICHIER_ENTREE = "DataMesure2_v03_rep1_allsensors.json"

#: Fichier de résultats JSON.
FICHIER_SORTIE = "DataCristofori_Mucchi.json"

#: Dossier racine des figures : figures/n_equal_x/TESTX/...
DOSSIER_FIGURES = "figures"

# ---------------------------------------------------------------------------
# 2. Constantes physiques (mêmes valeurs que les méthodes ISO 7849)
# ---------------------------------------------------------------------------

#: Surface rayonnante de la structure mesurée (m²).
S = 0.369286

#: Surface de référence (m²).
S0 = 1.0

#: Impédance caractéristique normalisée de l'air (N.s/m3).
ZC = 411.0

#: Impédance acoustique de référence (N.s/m3).
ZC0 = 400

#: Puissance acoustique de référence (W).
W0 = 1e-12

#: Facteur de rayonnement de référence (sans unité). Présent par cohérence avec
#: ISO 7849-2 ; non utilisé par la formule Lvib_j de Cristofori_Mucchi.
Sigma_Ref = 1

# ---------------------------------------------------------------------------
# 3. Plan d'essai et phase 1 (sélection des capteurs, identique ISO 7849-2)
# ---------------------------------------------------------------------------

#: Nombre de tests réalisés POUR CHAQUE valeur de n de N_CAPTEUR_COMBINAISON.
Nb_Test = 1

#: Nombre de capteurs de la combinaison initiale. None -> tableau 1 de
#: ISO/TS 7849-2 selon S (S < 1 m2 -> 10 ; 1 <= S <= 10 -> 20 ; S > 10 -> 2*S/S0).
N_CAPTEURS_INIT_ISO2 = None

#: Seuil du critère max/min : un capteur est ajouté tant que, sur au moins un
#: tiers d'octave, (max - min) >= FACTEUR_CRITERE_ISO2 x (nombre de capteurs).
FACTEUR_CRITERE_ISO2 = 1

#: Graine du générateur aléatoire (None -> tirage libre, graine enregistrée
#: dans les métadonnées pour pouvoir rejouer l'exécution).
RANDOM_SEED = None

#: Proportion maximale de capteurs communs entre deux sélections finales de
#: tests successifs (pour une même valeur de n).
CapteursCommuns = 0.5

#: Excitations à ne pas traiter (numéros, par exemple [1, 2]).
#: Liste vide -> toutes les excitations du fichier sont traitées.
EXCITATIONS_A_EXCLURE = []

#: Capteurs à ne jamais sélectionner (noms du fichier d'entrée).
CAPTEURS_EXCLUS = []

#: Nombre maximal de tirages de sélection pour UN test (doublon, critère
#: max/min inatteignable, moins de n capteurs sélectionnés...).
MAX_TENTATIVES_PAR_TEST = 200

#: Seuil fixe en dB remplaçant la règle écart_j < facteur x n (None = règle
#: normative). Dérogation explicite, tracée dans les métadonnées.
SEUIL_ECART_DB = None

# ---------------------------------------------------------------------------
# 4. Phase 2 (combinaisons de n capteurs parmi les p sélectionnés)
# ---------------------------------------------------------------------------

#: Nombres n de capteurs par combinaison finale, traités par ordre croissant.
#: Exemple : [2, 4] -> étude pour n = 2 puis n = 4 (Nb_Test tests chacun).
N_CAPTEUR_COMBINAISON = [2]

#: Valeur cible TV (dB) : on conserve les combinaisons avec delta_mk < TV.
TARGET_VALUE = 1

#: Nombre maximal de relances de la sélection (phase 1 + phase 2) lorsque
#: l'ensemble k' (ou k'_m) est vide, pour UN test. Au-delà : erreur explicite.
MAX_RELANCES_K_PRIME = 50

#: Nombre maximal de combinaisons C(p, n) évaluées pour un tirage de la phase 1.
#: Au-delà : le tirage est rejeté (compte comme une tentative) avec un message.
MAX_COMBINAISONS = 50000

# ---------------------------------------------------------------------------
# 5. Incertitudes
# ---------------------------------------------------------------------------

#: Enregistre les incertitudes dans le fichier de résultats.
INCERTITUDES_DANS_RESULTATS = True

#: Affiche les barres d'incertitude dans les figures.
FIGURES_INCERTITUDES = True

#: Facteur d'élargissement de u(Lac_j) = k x sqrt(s_j^2 + s_r0^2).
INCERTITUDE_FACTEUR_ELARGISSEMENT = 2.0

#: Termes s_r0 par plage de tiers d'octave : (fréquence min, fréquence max,
#: s_r0), bornes incluses, en Hz et en dB. Une bande hors de toutes les plages
#: provoque une erreur explicite. Plages ajoutables / retirables librement.
INCERTITUDE_TERMES_BANDES = [
    (100.0, 160.0, 3.0),
    (200.0, 315.0, 2.0),
    (400.0, 5000.0, 1.5),
    (6300.0, 10000.0, 2.5),
]

# ---------------------------------------------------------------------------
# 6. Figures
# ---------------------------------------------------------------------------

#: Enregistrement des figures au format PNG.
FIGURES_ENREGISTRER_PNG = True

#: Affichage interactif des figures (fenêtres matplotlib).
FIGURES_INTERACTIF = False

#: Groupes de figures activables séparément.
FIGURES_GROUPE_COMBINAISON_FINALE = True   # k_2prime
FIGURES_GROUPE_K_PRIME = True              # k' (plusieurs exc.) ou k'_m (une exc.)
FIGURES_GROUPE_SIMILARITE = True           # indices de similarité spectrale
FIGURES_GROUPE_RAYONNEMENT = True          # facteur de rayonnement

#: Résolution des PNG (dpi).
FIGURES_DPI = 150

#: Couleur imposée de tous les niveaux acoustiques.
FIGURES_COULEUR_ACOU = "red"

#: Nombre maximal de combinaisons tracées en courbes/barres dans un même
#: graphique de k' (lisibilité) ; au-delà, les meilleures (indice de similarité
#: le plus faible) sont tracées et un message l'indique. 0 = pas de limite.
FIGURES_MAX_COMBINAISONS_TRACEES = 30
