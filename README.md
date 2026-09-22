# VISUDATA — Cartographie vibratoire 3D sur CAO

Outil web local (aucune installation, aucun accès réseau) permettant de superposer
les niveaux vibratoires mesurés par accéléromètres sur la CAO de la machine étudiée.

---

## 1. Démarrage

Double-cliquer sur **`Lancer_VISUDATA.bat`**.

Le script démarre un petit serveur HTTP local (`serveur.py`, Python) puis ouvre le
navigateur sur `http://localhost:8765/`. Laisser la fenêtre noire ouverte pendant
l'utilisation. Le port est modifiable : `python serveur.py 8766`.

> **Pourquoi un serveur ?** Les modules ES et le noyau WebAssembly de lecture STEP
> sont bloqués par les navigateurs lorsqu'une page est ouverte en `file://`.
> Toute alternative fonctionne : extension *Live Server* de VS Code, IIS, nginx…
> Il suffit de servir ce dossier.

Navigateurs testés : Edge / Chrome (moteur Chromium). Firefox convient également.

## 2. Chargement des fichiers

Deux fichiers, via les zones du panneau **Fichiers** ou par glisser-déposer
n'importe où dans la fenêtre :

| Fichier | Formats | Rôle |
|---|---|---|
| CAO machine | `.step` `.stp` `.iges` `.igs` `.brep` | géométrie support (une ou plusieurs pièces) |
| Analyse mesures | `.json` | positions capteurs + niveaux |

L'ordre n'a pas d'importance, et chacun peut être rechargé à tout moment.
Les mesures s'affichent même sans CAO.

### Structure JSON attendue

```
EXCITATION1 / EXCITATION2 / EXCITATION3
   └── famille (base, cylindre, dome, plaque, structure…)
        └── groupe de capteurs (Accel, Micro, TeteImpedancePot…)
             ├── run_info.run_name[N]          noms des mesures
             ├── sensor_name[S]                noms des capteurs (Accel01…Accel10)
             ├── sensor_coordinates[N][S][3]   X, Y, Z en mm
             ├── frq_3rdOctave[B]              fréquences centrales
             ├── Data_3rdOctave_Vel[N][S][B]   spectres de vitesse vibratoire
             └── Data_GlobalLevel_Vel[N][S]    niveaux globaux
```

Souplesses prises en charge :

* **Coordonnées renseignées pour une seule excitation.** Elles sont mutualisées
  entre excitations en rapprochant les mesures homologues (nom de mesure privé de
  son préfixe `Exc<n>_`). Le panneau *Fichiers* signale les cas concernés.
* **Coordonnées absentes ou partielles** : les capteurs sans position ne sont pas
  représentés, la mesure est marquée `∅` (ou `n/S`) dans l'arbre des mesures.
* **Clés `_Vel` absentes** : bascule automatique sur `Data_3rdOctave` /
  `Data_GlobalLevel`.
* Nombre d'excitations, de familles, de capteurs et de bandes quelconque.
* Si plusieurs groupes de capteurs exploitables existent, un sélecteur apparaît
  sous *Grandeur affichée* (`Accel` par défaut).

## 3. Fonctions

**Grandeur affichée** — niveau global, ou tiers d'octave avec curseur de
fréquence (boutons ◀ ▶ et flèches du clavier).

**Échelle de couleurs** — 6 palettes ; dynamique automatique sur la sélection
courante, ou bornes min/max saisies à la main. `Recalculer sur la sélection` /
`Sur toutes les mesures` recalent les bornes. L'option *Écrêter hors bornes*
décide du sort des valeurs qui sortent de l'échelle (écrêtées, ou masquées).

**Billes** — rayon réglable (mm), opacité, option *taille proportionnelle au
niveau*.

**Recalage CAO** — facteur d'échelle, translation X/Y/Z, rotations θX/θY/θZ
(ordre XYZ), pivot au centre de la pièce ou à l'origine, opacité, arêtes,
teinte neutre ou couleurs du fichier STEP, visibilité pièce par pièce.
`Auto-ajuster sur les capteurs` fournit un pré-recalage grossier (recouvrement
des boîtes englobantes) à affiner ensuite.

**Mesures** — arbre par famille, cases individuelles et par famille (état
intermédiaire visible), filtre texte, tout cocher / tout décocher. Tout est
coché par défaut.

**Excitations** — une ou plusieurs ; chaque excitation cochée ouvre une vue
supplémentaire juxtaposée, toutes partageant la même échelle de couleurs.
Les vues sont liées par défaut (bouton *Vues liées* dans la barre du haut).

**Mode identification** — au survol d'une bille : capteur, valeur, mesure,
famille. Au clic : fiche détaillée (position, valeur pour chaque excitation
affichée, spectre tiers d'octave complet avec la bande courante repérée). Le
capteur sélectionné est repéré simultanément dans toutes les vues.
La fiche possède une **légende cliquable** sous le graphe : chaque excitation
peut être masquée pour ne comparer que les courbes utiles (au moins une reste
affichée), et le bouton ⤢ **agrandit la fenêtre** pour lire le spectre en grand
(la légende est alors aussi dessinée dans le graphe, avec les titres d'axes).

**Interpolation de surface (RBF)** — reconstruit un champ continu sur la CAO à
partir des **seules billes affichées**, une résolution indépendante par
excitation. Une mesure décochée, ou une bille masquée parce que sa valeur sort
des bornes de couleur alors que l'écrêtage est désactivé, n'alimente pas le
solveur — le bilan indique combien de billes ont été exclues à ce titre. Si
plus rien n'est affiché, la surface repasse en teinte neutre au lieu de
conserver un champ périmé.
Hyperparamètres réglables dans le menu déroulant *Interpolation surface* :

| Réglage | Effet |
|---|---|
| Noyau radial | gaussien, multiquadrique (± inverse), plaque mince `r²·ln r`, linéaire |
| ε | portée du noyau (mm) ; le bouton *ε automatique* prend 1,6 × la distance moyenne entre capteurs voisins |
| λ | lissage (régularisation). λ = 0 ⇒ passage exact par les mesures ; λ croissant ⇒ champ plus lisse, l'écart aux mesures est affiché |
| Terme polynomial | aucun / constante / affine — **nécessaire** pour les noyaux non décroissants (plaque mince, linéaire, multiquadrique) |
| Distance d'influence max | au-delà, la surface est grisée : aucune extrapolation trompeuse loin des capteurs |
| Pas de maillage du champ | la triangulation STEP est faite pour la géométrie (le cylindre n'a que deux rangées de sommets sur la hauteur) : elle est raffinée pour le champ. Bornes liées à ε, défaut ε/2,5 |
| Opacité surface | transparence du champ |
| Couleurs fidèles | surface **et** billes en couleur brute, non modulée par l'éclairage : la teinte correspond exactement à la colorbar (les billes reçoivent alors un liseré sombre pour rester repérables) |
| Points max | nombre de nœuds du solveur ; les mesures au même endroit sont d'abord moyennées, le surplus est décimé (indiqué dans le bilan) |

Affichage *Surface + points* ou *Surface seule*. Le champ utilise la même
palette et les mêmes bornes que les billes : la colorbar vaut pour les deux.
Le recalcul est automatique (déclenché par un changement de bande, de mesures,
d'excitation ou de recalage CAO) et peut être basculé en manuel.

Le bilan affiché sous les réglages est là pour être lu : nombre de nœuds
effectivement résolus, écart du champ aux nœuds (effet de λ), taille du
maillage, temps de calcul, et surtout **fidélité bille ↔ surface** — l'écart
entre la valeur d'un capteur et celle du champ sur la surface juste à côté.
C'est le contrôle qui dit si le réglage est honnête. Ordres de grandeur mesurés
sur le cas d'exemple (340 points, 2 vues) :

| Pas de maillage | Triangles / vue | Fidélité moyenne | Temps (2 vues) |
|---|---|---|---|
| 46 mm | 15 000 | 2,0 dB | 44 ms |
| 24 mm | 33 000 | 1,4 dB | 65 ms |
| 12 mm (défaut) | 91 000 | 0,8 dB | 125 ms |
| 10 mm | 133 000 | 0,6 dB | 194 ms |

Si le budget de triangles est atteint, un avertissement le signale : le champ
reste affiché mais certaines zones ne sont pas raffinées.

**Projets** — `Projet` enregistre un fichier `*.visudata.json` contenant toute
la configuration (fichiers liés, excitations, mesures cochées, grandeur et
bande, palette et bornes, billes, recalage CAO, pièces masquées, réglages
d'interpolation, affichage, thème, position de caméra) ; `Ouvrir` la restaure.
Un projet ouvert avant les mesures reste en attente et s'applique dès leur
chargement. Sur Chrome/Edge, les deux fichiers de données sont mémorisés :
le bouton **Recharger les derniers fichiers** les réouvre en un clic à la
session suivante (le navigateur demande une confirmation d'accès).

**Divers** — export PNG des vues juxtaposées, thème sombre / clair, projection
perspective ou orthographique, vues normalisées (Iso, +X, +Y, +Z), grille,
trièdre, boîte englobante des capteurs.

**Souris** : clic gauche = rotation · molette = zoom · clic droit = panoramique.
**Clavier** : `F` recadrer · `←` `→` bande de fréquence · `Échap` fermer la fiche.

## 4. Organisation du code

```
serveur.py            serveur HTTP local (sans cache, MIME wasm correct)
index.html            structure de l'interface
css/style.css         thème Cetim (variables CSS en tête de fichier)
js/app.js             état applicatif, interface, orchestration
js/dataModel.js       lecture du JSON, mutualisation des coordonnées, accès aux valeurs
js/cadLoader.js       lecture STEP/IGES/BREP (OpenCascade) -> géométries three.js
js/scene3d.js         vue 3D : caméra, CAO transformable, billes instanciées, picking, champ RBF
js/interp.js          interpolation RBF (noyaux, solveur dense, régularisation)
js/project.js         projets .visudata.json, mémorisation des fichiers (IndexedDB)
js/colormaps.js       palettes de couleurs
cetim-logo.png        logotype affiché en haut à gauche
vendor/               three.js r164, OrbitControls, occt-import-js (OpenCascade WASM)
```

Les géométries et matériaux CAO sont partagés entre les vues ; les billes sont
rendues via un `InstancedMesh` (une seule passe de rendu par vue).

Couleurs de marque : `--cetim-blue`, `--cetim-orange`, `--cetim-cyan` en tête de
`css/style.css` — à ajuster si la charte évolue.

Depuis la console du navigateur, `window.VISUDATA` expose `state`, `views`,
`refreshAll()`, `handleFile()`, `selectRecord()` et `snapshot()`.

## 5. Points d'attention

* Les niveaux `*_Vel` sont affichés en **dB** (le champ `unit` du JSON décrit le
  capteur, `ms-2`, et non l'unité du niveau de vitesse calculé).
* Les coordonnées et la CAO sont supposées en **millimètres**.
* Le jeu de données d'exemple contient une mesure `dome / Dome_Aleatoire_Pos1_Rep1`
  sans aucune coordonnée capteur : elle est listée mais non représentée.
