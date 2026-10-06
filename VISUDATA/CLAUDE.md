# VISUDATA — notes pour Claude Code

Outil web **local, sans build, sans dépendance réseau** : superposition de niveaux
vibratoires (JSON de mesures) sur une CAO STEP. Voir `README.md` pour le mode
d'emploi utilisateur ; ce fichier ne couvre que ce qu'il faut savoir pour modifier
le code.

## Lancer / tester

```
Lancer_VISUDATA.bat          # -> python serveur.py 8765
```

Ne jamais ouvrir `index.html` en `file://` : les modules ES et le WASM
OpenCascade sont bloqués par le navigateur.

`serveur.py` remplace `python -m http.server` pour deux raisons : envoyer
`Cache-Control: no-store` (sinon le navigateur continue de servir l'ancien
`app.js` / `style.css` après modification — piège vécu, un test peut valider du
code qui n'est pas celui qui tourne) et déclarer `application/wasm`.

Ce poste n'a **pas Node.js** (Python 3.11 et Edge/Chrome uniquement). Pour valider
une modification sans intervention manuelle : servir le dossier avec un petit
serveur Python acceptant `POST /result`, dupliquer `index.html` en y ajoutant un
`<script type="module">` de scénario (il s'exécute après `app.js`, donc
`window.VISUDATA` est disponible), piloter l'interface avec des `click()` /
`dispatchEvent(new Event('input'))`, puis `fetch('/result', {method:'POST', …})`
le rapport. Lancer `msedge --headless=new --enable-unsafe-swiftshader
--window-size=1680,945 <url>` et attendre l'arrivée du fichier.
`--screenshot` est peu fiable ici ; pour un contrôle visuel, appeler
`VISUDATA.snapshot()` en neutralisant `HTMLAnchorElement.prototype.click` et
poster la dataURL. Penser à supprimer les fichiers `_*.html` / `_*.js` de test
après coup.

## Architecture

| Fichier | Rôle |
|---|---|
| `js/app.js` | objet `state` unique + branchement de toute l'interface. Point d'entrée. |
| `js/dataModel.js` | `detectFormat()` + JSON → modèle plat (`runList`, `families`, `excitations`), accès aux valeurs |
| `js/cadLoader.js` | STEP/IGES/BREP → `THREE.Group` (OpenCascade WASM) |
| `js/scene3d.js` | classe `Scene3D` : une instance par vue/excitation |
| `js/interp.js` | RBF : noyaux, solveur dense (Gauss + pivot), réduction du nuage |
| `js/project.js` | `.visudata.json`, File System Access + poignées en IndexedDB |
| `js/colormaps.js` | palettes (points de contrôle + interpolation) |
| `vendor/` | three.js r164, OrbitControls, occt-import-js — **figés, ne pas régénérer** |

Chaîne de rafraîchissement, à respecter pour toute nouvelle commande :

* `refreshAll()` → recalcule bornes auto, `buildRecords()` par vue, couleurs,
  tailles, colorbar, compteurs. À appeler après tout changement de données,
  de sélection, d'échelle ou de palette. Volontairement **exclu** de `applyHelpers()`
  (recréation de géométries) pour rester fluide au déplacement du curseur de bande.
* `applyCadTransform()` / `applyCadAppearance()` → recalage et aspect CAO.
* `rebuildViews()` → uniquement quand la liste des excitations affichées change
  (recrée les `Scene3D`, réattache la CAO, restaure l'état caméra).

Deux pièges de visibilité déjà corrigés, à ne pas réintroduire :

* La règle globale `[hidden] { display: none !important; }` en tête de
  `style.css` est **indispensable** : les overlays, l'écran d'accueil et la
  colorbar portent un `display: grid/flex` d'auteur qui l'emporte sinon sur la
  feuille de style du navigateur, et l'attribut `hidden` reste sans effet
  (application entièrement couverte, donc « bloquée »).
* Un test qui lit `el.hidden` en JS ne voit pas ce défaut : vérifier
  `getComputedStyle(el).display`.
* Le voile de glisser-déposer est piloté par une temporisation (~900 ms, le
  modèle HTML réémet `dragover` toutes les ~350 ms) et non par un compteur
  `dragenter`/`dragleave`, qui se déséquilibre sur un drag abandonné et laisse
  un voile plein écran. Échap et le clic referment voile et overlay.

## Invariants à ne pas casser

* **Repère Z vers le haut** (`camera.up = (0,0,1)`, grille tournée de π/2) : les
  coordonnées capteurs et la CAO sont en mm, Z = hauteur machine.
* **Coordonnées capteurs mutualisées entre excitations** : dans les jeux de
  données réels seule `EXCITATION1` les renseigne. `dataModel.js` rapproche les
  mesures homologues via le nom privé de son préfixe `Exc<n>_`, capteur par
  capteur. Ne pas indexer les coordonnées sur l'excitation courante.
* **Géométries et matériaux CAO partagés** entre les vues : chaque vue reçoit un
  `group.clone()`. Conséquence : ne jamais stocker d'objet three.js dans
  `Object3D.userData` (`clone()` sérialise `userData` en JSON) — c'est pourquoi
  les arêtes sont des enfants nommés `__edges` et `baseColor` est un entier hex.
  Un changement d'opacité/couleur agit sur toutes les vues en une passe : voulu.
* **Billes = un seul `InstancedMesh` par vue** ; le picking passe par
  `intersection.instanceId`, index aligné sur `scene.records`. Les tableaux
  `colors` / `scales` doivent rester dans le même ordre que `records`.
* **Transformation CAO** : `p → R·S·(p − c) + c + T` quand le pivot centre est
  actif (sinon `c = 0`). Implémentée par `cadRoot` (S, R, T+c) > `cadPivot` (−c).
* Palette et bornes min/max **communes à toutes les vues** : c'est ce qui rend la
  comparaison entre excitations valide. Le champ interpolé partage cette échelle.
* **Mode champ (RBF)** : c'est la seule exception au partage des géométries.
  `Scene3D.setFieldEnabled()` clone la géométrie de chaque maillage de la vue et
  lui ajoute un attribut `color` — indispensable, les vues affichant des
  excitations différentes. Toute reconstruction des clones CAO (`attachCad()`,
  `rebuildViews()`) invalide cet état : rappeler `applyInterp(true)` derrière.
  `paintField()` reçoit les positions **en coordonnées monde** (recalage inclus),
  donc le champ suit la CAO quand on la déplace.
* Le solveur RBF est dense (O(n³)) : `interp.maxPts` borne la taille du système,
  les mesures coïncidentes étant d'abord moyennées. Ne pas retirer ce garde-fou.
* **Le champ ne peut pas être colorié sur la triangulation STEP telle quelle.**
  OpenCascade maille pour la géométrie : un cylindre reçoit ~60 segments
  circonférentiels mais deux rangées sur la hauteur, soit des lamelles de
  plusieurs centaines de mm. Mesuré avant correction : sommet le plus proche
  d'un capteur à 55 mm en moyenne, écart bille ↔ surface 5,3 dB (max 23).
  D'où `cadLoader.fieldGeometry()` : raffinage **conforme** (une arête est
  découpée si et seulement si sa longueur dépasse la cible, donc les deux
  triangles voisins prennent la même décision — sinon apparaissent des sommets
  en T et des stries de couleur), points milieux mutualisés par arête, sommets
  soudés par position **et** normale (arêtes vives préservées, coût du champ
  divisé par ~3). Budget de triangles vérifié *avant* chaque passe : un motif
  « 3 arêtes longues » quadruple le compte. Après correction : 0,5–0,8 dB.
* Le champ se construit sur les **billes visibles uniquement** :
  `runInterp()` filtre `scene.records` par `scene.scaleArr[i] > 0` (une bille
  masquée par l'écrêtage désactivé a une échelle nulle). Ce qui n'est pas à
  l'écran ne doit pas piloter le champ. Quand il reste moins de 3 points, ou que
  le système est singulier, la surface est repeinte en teinte neutre
  (`paintNeutral`) : jamais de champ périmé affiché.
* Le bilan affiche la **fidélité bille ↔ surface**, calculée sans surcoût
  pendant la peinture via `rbf.dminIdx` (nœud le plus proche de chaque sommet).
  Garder cet indicateur : c'est lui qui prouve que le champ et les billes
  reposent bien sur la même base.
* `interp.unlit` (défaut) rend surface **et** billes en `MeshBasicMaterial` :
  sans cela l'éclairage module les teintes et la comparaison à la colorbar est
  fausse. Les billes reçoivent alors un liseré (`_syncOutline`, faces arrière
  d'une sphère 1,16×) pour rester distinguables du fond de même couleur.
* Les noyaux non décroissants (plaque mince, linéaire, multiquadrique) exigent le
  terme polynomial ; en cas de système singulier, `buildRbf()` renvoie `null` et
  l'interface invite à augmenter λ.
* Projets : `projectToObject()` / `applyProject()` doivent rester symétriques, et
  `applyProject()` tolérant (mesures ou CAO absentes, ids de mesures disparus,
  `version` inconnue). Tout nouvel état durable s'ajoute aux deux fonctions **et**
  à `pushStateToControls()`.
* **Trois formats JSON, un seul modèle.** `detectFormat()` distingue
  `mesure1` (excitation › famille › groupe), `mesure2` (excitation › groupe,
  une ligne par capteur) et `iso` (racine › `TEST*` › excitation avec
  `Accel_name`). Les deux derniers sont ramenés au modèle historique avec **un
  run par capteur** (`nSensors = 1`, `run.id` = nom unique du capteur) et
  `model.flat = true` : billes, échelle, RBF, fiche et sélection inter-vues
  (`run.id` + `si`) restent communs. Ne pas créer de chemin d'affichage
  parallèle pour un nouveau format : le ramener à ce modèle.
* `model.hasGlobal = false` (ISO) force `state.mode = 'band'` et grise le
  bouton global ; `applyProject()` respecte cette contrainte.
* DataMesure 2 : seules les clés `EXC*` sont retenues quand il y en a. Le
  `BDF` n'a pas de coordonnées et ses `sensor_name` sont des noms de lot :
  mutualiser ses coordonnées par nom lui attribuerait à tort la position des
  capteurs homonymes.
* **Étiquettes** (`Scene3D.setLabels`) : calque HTML par vue, projeté dans
  `update()` après chaque rendu, `idx` aligné sur `records`. Le DOM n'est
  reconstruit que si la liste change (clé texte + position), pas au curseur de
  bande. `state.labels = null` au chargement = choix automatique
  (`LABELS_AUTO_MAX`).

## Conventions

* Interface, commentaires et messages **en français**.
* Aucun outil de build, aucun CDN, aucun paquet npm : tout ajout de dépendance
  se fait par un fichier déposé dans `vendor/`.
* Couleurs de marque : variables `--cetim-*` en tête de `css/style.css`.
  Le thème clair est une simple surcharge de variables sous `[data-theme="light"]`.
* Lecture du JSON volontairement tolérante (nombre d'excitations, familles,
  capteurs et bandes quelconque ; repli `Data_*` si `Data_*_Vel` absent ;
  capteurs sans coordonnées signalés et ignorés en 3D). Conserver cette
  souplesse plutôt que de coder en dur `10` capteurs / `3` excitations / `20` bandes.
* `window.VISUDATA` expose `state`, `views`, `refreshAll`, `handleFile`,
  `selectRecord`, `snapshot` — utile en console et indispensable aux tests.
