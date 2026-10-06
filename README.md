# CapteurVirtuel

Outils Cetim d'acoustique : estimation de la puissance acoustique rayonnée à
partir de mesures vibratoires (ISO/TS 7849-1 et 7849-2), avec des capteurs
virtuels, et visualisation 3D des niveaux sur la CAO.

| Dossier | Outil | Rôle |
|---|---|---|
| [`CALCULDATA/`](CALCULDATA/) | Python 3.11 | Calculs ISO/TS 7849-1 / -2 sur combinaisons d'accéléromètres → `DataISO7849_1.json`, `DataISO7849_2.json` |
| [`VISUDATA/`](VISUDATA/) | page web locale (three.js, sans build) | Cartographie 3D des niveaux vibratoires sur une CAO STEP. Lit les mesures `DataMesure_v01` et `DataMesure2_v02`, ainsi que les résultats ISO de CALCULDATA |

Chaque dossier a son propre `README.md` (mode d'emploi). Les deux outils
fonctionnent hors ligne, sans installation autre que Python.

## Démarrage rapide

```
cd CALCULDATA
python main1.py              # ISO/TS 7849-1
python main2.py              # ISO/TS 7849-2

cd ../VISUDATA
Lancer_VISUDATA.bat          # ouvre http://localhost:8765/
```
