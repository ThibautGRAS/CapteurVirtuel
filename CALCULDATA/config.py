# -*- coding: utf-8 -*-
"""Paramètres de configuration des routines ISO 7849-1 et ISO 7849-2.

C'est le SEUL fichier à modifier pour une étude courante : tous les autres
modules lisent leurs paramètres ici. Aucune valeur métier n'est codée en dur
ailleurs dans le programme.
"""

# ---------------------------------------------------------------------------
# 1. Fichiers
# ---------------------------------------------------------------------------

#: Fichier de mesures d'entrée. Il n'est JAMAIS modifié par le programme.
FICHIER_ENTREE = "DataMesure2_v01.json"

#: Fichiers de résultats produits par main1.py et main2.py.
FICHIER_SORTIE_ISO1 = "DataISO7849_1.json"
FICHIER_SORTIE_ISO2 = "DataISO7849_2.json"

#: Dossier où figures.py enregistre les images PNG.
DOSSIER_FIGURES = "figures"


# ---------------------------------------------------------------------------
# 2. Constantes physiques et normatives
# ---------------------------------------------------------------------------

#: Surface rayonnante de la structure mesurée (m²).
S = 0.369286

#: Surface de référence (m²).
S0 = 1.0

#: Impédance caractéristique normalisée de l'air, Zc,n (N.s/m3).
#: Valeur imposée par les deux normes : 411 N.s/m3.
ZC = 411.0

#: Impédance acoustique de référence, Zc,0 (N.s/m3).
#: ISO/TS 7849-1 equation (12) et ISO/TS 7849-2 equation (15) : Zc,0 = 400.
#: Le terme 10*log10(411/400) vaut +0,12 dB ; avec ZC0 = 411 (valeur indiquée
#: dans le cahier des charges 3.2) ce terme s'annule et les niveaux sont
#: minorés de 0,12 dB. Mettre 411.0 ici pour retrouver exactement les valeurs
#: du cahier des charges initial.
ZC0 = 400.0

#: Puissance acoustique de référence (W).
W0 = 1e-12

#: Facteur de rayonnement de référence, utilisé par ISO 7849-2 (sans unité).
Sigma_Ref = 1.0


# ---------------------------------------------------------------------------
# 3. Plan d'essai
# ---------------------------------------------------------------------------

#: Nombre de tests (combinaisons de capteurs distinctes) à générer.
#: Valeur lue uniquement ici, jamais demandée en console.
Nb_Test = 5

#: Nombre de capteurs de la combinaison initiale, par méthode.
#: None -> déduit de la surface S par le tableau 1 de la norme concernée :
#:   ISO/TS 7849-1 : S < 1 m2 -> 5  ; 1 <= S <= 10 -> 10 ; S > 10 -> S/S0
#:   ISO/TS 7849-2 : S < 1 m2 -> 10 ; 1 <= S <= 10 -> 20 ; S > 10 -> 2*S/S0
#: Avec S = 0,369286 m2, ces tableaux donnent 5 et 10, valeurs du cahier des
#: charges. Un entier force la valeur et ignore le tableau.
N_CAPTEURS_INIT_ISO1 = None
N_CAPTEURS_INIT_ISO2 = None

#: Facteur appliqué au nombre de capteurs dans le critère d'arrêt :
#: un capteur est ajouté tant que écart_j >= FACTEUR x n.
#:   ISO/TS 7849-1, 7.3 : "larger than DOUBLE the number of positions" -> 2
#:   ISO/TS 7849-2, 7.3 : "larger than the number of positions"        -> 1
#: Mettre 1.0 pour ISO 7849-1 revient à appliquer le critère du cahier des
#: charges 3.2 (écart_j < n), plus sévère que la norme.
FACTEUR_CRITERE_ISO1 = 2.0
FACTEUR_CRITERE_ISO2 = 1.0

#: Graine du générateur aléatoire.
#: None  -> tirage non reproductible (une graine effective est tout de même
#:          enregistrée dans les métadonnées du fichier de résultats, ce qui
#:          permet de rejouer l'exécution a posteriori).
#: entier -> séquence reproductible.
RANDOM_SEED = None

#: Excitations utilisées pour le calcul du facteur de rayonnement
#: (numéros d'excitation, pas des indices). [1] = EXCITATION1 seule.
#: Avec [1, 3, 6], un facteur est calculé par excitation puis la MOYENNE
#: ARITHMÉTIQUE des facteurs (grandeurs linéaires) est retenue, bande par bande.
Excitations_RF = [1]

#: Proportion maximale de capteurs communs autorisée entre deux combinaisons
#: finales. 0.5 = deux tests ne peuvent pas partager plus de la moitié de leurs
#: capteurs. Le dénominateur est la PLUS PETITE des deux combinaisons.
CapteursCommuns = 0.5

#: Capteurs à ne jamais sélectionner (capteurs défaillants, mal collés, etc.).
#: Les noms doivent correspondre à sensor_name du fichier d'entrée.
#: Exemple : ["Accel01", "Accel49"]
CAPTEURS_EXCLUS = []


# ---------------------------------------------------------------------------
# 4. Garde-fous anti-boucle infinie
# ---------------------------------------------------------------------------

#: Nombre maximal de tentatives (combinaisons initiales successives) pour
#: aboutir à une combinaison finale valide et distincte, pour UN test donné.
#: Une tentative est consommée lorsqu'un doublon est détecté ou lorsque le
#: critère max/min ne peut pas être satisfait avec les capteurs disponibles.
MAX_TENTATIVES_PAR_TEST = 200


# ---------------------------------------------------------------------------
# 5. Critère max/min : dérogation explicite (désactivée par défaut)
# ---------------------------------------------------------------------------

#: Règle normative : un capteur est ajouté tant que, sur au moins un tiers
#: d'octave, écart_j = max_j - min_j (dB) est supérieur ou égal au nombre n de
#: capteurs de la combinaison.
#:
#: Sur certains jeux de mesures, cette règle est inatteignable : si la
#: dispersion des niveaux dépasse le nombre total de capteurs disponibles,
#: aucune combinaison ne peut la satisfaire, même en prenant tous les capteurs.
#: Le programme le détecte et l'annonce avant de lancer les tests.
#:
#: SEUIL_ECART_DB permet alors de poursuivre l'étude avec un seuil explicite,
#: en dB, décidé par l'utilisateur et tracé dans les métadonnées :
#:   None  -> règle normative écart_j < n (valeur par défaut).
#:   float -> le critère devient écart_j < SEUIL_ECART_DB.
#: Ce paramètre ne doit être utilisé qu'en connaissance de cause : il change le
#: critère d'arrêt et doit être mentionné dans le rapport d'essai.
SEUIL_ECART_DB = None


# ---------------------------------------------------------------------------
# 6. Figures
# ---------------------------------------------------------------------------

#: Enregistrement des figures au format PNG.
FIGURES_ENREGISTRER_PNG = True

#: Affichage interactif des figures (fenêtres matplotlib) en fin de tracé.
#: Peut aussi être activé en ligne de commande : python figures.py --interactif
FIGURES_INTERACTIF = False

#: Résolution des PNG enregistrés (points par pouce).
FIGURES_DPI = 150

#: Couleur de la courbe de puissance acoustique (imposée : rouge).
FIGURES_COULEUR_ACOU = "red"

#: Palette matplotlib utilisée pour les courbes de puissance vibratoire.
FIGURES_PALETTE_VIB = "viridis"
