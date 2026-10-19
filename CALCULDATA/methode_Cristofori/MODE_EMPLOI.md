# Méthode Cristofori_Mucchi — mode d'emploi

Programme autonome : il n'importe aucun fichier des méthodes ISO 7849-1 / 7849-2.
La phase 1 (sélection des capteurs) est une copie sans modification de
comportement de `selection_capteurs.py` de l'ISO 7849-2 avec favorisation spatiale.

## Prérequis
Python 3.9+, `numpy`, `matplotlib` (et `pytest` pour les tests).

## Lancement
```
python main.py                  # calcul + JSON + figures
python main.py --sans-figures   # calcul + JSON
python figures.py [--fichier f.json] [--interactif]   # figures depuis un JSON existant
python -m pytest tests          # tests
```
Codes de sortie : 0 succès, 1 données/configuration/calcul invalides, 2 sélection impossible.
Tous les paramètres sont dans `config.py` (seul fichier à modifier). Les chemins
relatifs sont résolus par rapport à ce dossier.

## Fichiers
| Fichier | Rôle |
|---|---|
| `config.py` | paramètres (valeurs par défaut du cahier des charges) |
| `main.py` | point d'entrée |
| `methode.py` | enchaînement : tests, phase 1, phase 2, relances, construction du JSON |
| `selection_capteurs.py` | phase 1 (copie autonome ISO 7849-2 favorisation spatiale) |
| `calculs.py` | formules (Lv_j, Lvib_j, delta_mk, similarité, rayonnement, incertitudes) |
| `data_io.py` | lecture/validation du JSON d'entrée, écriture des résultats |
| `figures.py` | figures PNG |
| `tests/test_cristofori.py` | tests |

## Déroulement
Pour chaque n de `N_CAPTEUR_COMBINAISON` (ordre croissant) et chaque test
(`Nb_Test` par valeur de n), une nouvelle sélection de p capteurs est tirée
(phase 1), puis la phase 2 évalue les C(p,n) combinaisons :
Lv_j, Lvib_j, Lvib, delta_mk = |Lvib − Lac| ; k'_m = {delta_mk < TARGET_VALUE}.
* Plusieurs excitations : k' = intersection des k'_m ; Spectral_Similarity = somme
  des Spectral_Similarity_m ; k_2prime = minimum.
* Une excitation : k_2prime = minimum de Spectral_Similarity_m sur k'_m.

Clés d'entrée : `Accel.Data_3rdOctave_Vel` (Lv_i_j), `Micro.Data_3rdOctaveMean_Lw`
(Lac_j), `Micro.Data_GlobalLevelMean_Lw` (Lac), `Micro.Data_3rdOctave_Lw`
(runs, incertitudes). Le bloc `BDF` est ignoré.

## Relances et erreurs explicites
Le tirage de la sélection est recommencé (limite `MAX_TENTATIVES_PAR_TEST`) si : critère
max/min inatteignable, doublon (`CapteursCommuns`, entre tests d'un même n),
p < n, C(p,n) > `MAX_COMBINAISONS`. Si k' (ou k'_m) est vide, relance limitée par
`MAX_RELANCES_K_PRIME` ; au-delà, erreur explicite. Erreurs aussi pour : bande hors
`INCERTITUDE_TERMES_BANDES`, R = 1 run, Lac_j négatif (racine de la similarité),
excitation exclue inexistante, fichier invalide.

## Sortie JSON (`FICHIER_SORTIE`)
`DataCristofori` (plusieurs excitations) ou `DataCristofori_EXCx` (une seule)
→ `n_equal_x` → `TESTX` → `Data_k`, `Data_k_prime_m`, `Data_k_prime` (plusieurs
exc.), `Data_k_2prime`, `Data_Accel`, `Data_Acou`, `Data_Selection` ; plus `Metadata`
(tous les paramètres, graine, résumé des tests). Orthographe des clés corrigée par
rapport aux exemples (`Data_3rdOctave_Radiation_Factor`, `Spectral_Similarity_m`,
`k_2prime_ensemble`). `Data_k_2prime` contient aussi le facteur de rayonnement moyen
sur les excitations (moyenne arithmétique, incertitude GUM = √(Σu²)/M).

## Figures
`figures/n_equal_x/TESTX/<type>_n<x>_TESTX_<excitation>.png`. Quatre groupes
activables (`FIGURES_GROUPE_*`). Niveaux acoustiques en rouge, abscisses en échelle log.
Au-delà de `FIGURES_MAX_COMBINAISONS_TRACEES` combinaisons, seules les meilleures
(similarité la plus faible) sont tracées dans les spectres et barres de k'.
Le facteur de rayonnement est en échelle logarithmique ; une barre d'incertitude
plus grande que la valeur est tronquée vers le bas par l'échelle log.
Les incertitudes ne sont tracées que si elles sont dans le JSON (`INCERTITUDES_DANS_RESULTATS`).

## Reproductibilité
`RANDOM_SEED = None` tire une graine libre, enregistrée dans `Metadata.graine_aleatoire` ;
la recopier dans `RANDOM_SEED` pour rejouer.
