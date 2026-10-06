# CALCULDATA — capteurs virtuels ISO/TS 7849

Estimation du niveau de puissance acoustique rayonnée à partir de mesures
vibratoires, selon ISO/TS 7849-1 et ISO/TS 7849-2, avec tirage de combinaisons
d'accéléromètres (capteurs virtuels).

Le guide complet est dans `Guide_utilisation_CALCULDATA.docx` (et `.pdf`).
Le cahier des charges à jour est `prompt3.3_ISO7849-1-2_CapteursVirtuels.docx`.

## Lancer

```
python main1.py                 # ISO/TS 7849-1  -> DataISO7849_1.json
python main2.py                 # ISO/TS 7849-2  -> DataISO7849_2.json
python figures.py --interactif  # figures PNG + affichage à l'écran
python -m pytest -q             # 47 tests automatiques
```

Python 3.11. `matplotlib` n'est requis que par `figures.py`, `pytest` que par
les tests. Les deux programmes principaux n'utilisent que la bibliothèque
standard, sans accès réseau.

## Où se règlent les choses

Tout est dans `config.py` : nombre de tests, capteurs exclus, surface
rayonnante, constantes, graine aléatoire, figures. Le fichier de mesures
`DataMesure2_v01.json` n'est jamais modifié.

## Organisation

| Fichier | Rôle |
|---|---|
| `config.py` | paramètres de l'étude |
| `main1.py` / `main2.py` | programmes principaux des deux parties de la norme |
| `pipeline.py` | enchaînement commun aux deux (lecture, diagnostic, tests, écriture) |
| `selection_capteurs.py` | tirage, critère max/min, doublons |
| `calculs.py` | formules des normes, tableau 1, facteur de rayonnement |
| `data_io.py` | lecture, validation, écriture JSON, métadonnées |
| `figures.py` | graphiques et diagrammes en barres, script autonome |
| `tests/` | tests sur signaux artificiels à résultat connu |
| `normes/` | ISO/TS 7849-1 et 7849-2 (référence) |

## Points à connaître

* Le critère d'arrêt du paragraphe 7.3 compare l'écart max/min au nombre de
  positions : le **double** pour la partie 1, le nombre lui-même pour la
  partie 2, bande par bande. Ce facteur est réglable par
  `FACTEUR_CRITERE_ISO1` et `FACTEUR_CRITERE_ISO2`.
* L'écart max/min ne peut que croître avec le nombre de capteurs. Quand le
  critère est hors d'atteinte, le programme s'arrête avec un diagnostic chiffré
  au lieu de boucler. C'est le cas de `DataMesure2_v01.json` pour la partie 2.
  `SEUIL_ECART_DB` permet alors de poursuivre avec un seuil en décibels assumé
  et tracé dans les métadonnées.
* Chaque fichier de résultats porte un bloc `Metadata` contenant la graine
  aléatoire effective : la recopier dans `RANDOM_SEED` rejoue l'exécution à
  l'identique.
