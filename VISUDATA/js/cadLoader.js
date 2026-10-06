/* =========================================================================
   Lecture d'un fichier CAO (STEP / IGES / BREP) via OpenCascade (WASM)
   et construction des géométries three.js.

   Le module renvoie un THREE.Group « modèle » dont les enfants directs sont
   les pièces (une pièce = un noeud de l'assemblage portant des maillages).
   Les géométries et matériaux sont partagés entre les différentes vues :
   chaque vue utilise group.clone() (three.js conserve les références).
   ========================================================================= */

import * as THREE from 'three';

let occtPromise = null;

function getOcct() {
  if (!occtPromise) {
    if (typeof window.occtimportjs !== 'function') {
      return Promise.reject(new Error("Bibliothèque OpenCascade absente (vendor/occt-import-js.js)."));
    }
    occtPromise = window.occtimportjs({
      locateFile: (f) => new URL('../vendor/' + f, import.meta.url).href,
    });
  }
  return occtPromise;
}

/** Pré-chargement (facultatif) du noyau WASM. */
export function warmup() { getOcct().catch(() => {}); }

/* Regroupe les maillages par noeud d'assemblage nommé. */
function collectParts(root, meshCount) {
  const parts = [];
  const seen = new Set();

  const walk = (node, inherited) => {
    if (!node) return;
    const name = (node.name || '').trim();
    const label = name || inherited;
    const ids = Array.isArray(node.meshes) ? node.meshes.filter((i) => i >= 0 && i < meshCount) : [];
    if (ids.length) {
      parts.push({ name: label || `Pièce ${parts.length + 1}`, meshIds: ids });
      ids.forEach((i) => seen.add(i));
    }
    (node.children || []).forEach((c) => walk(c, label));
  };
  walk(root, '');

  // maillages orphelins (hiérarchie absente ou incomplète)
  const orphans = [];
  for (let i = 0; i < meshCount; i++) if (!seen.has(i)) orphans.push(i);
  if (orphans.length) parts.push({ name: parts.length ? 'Autres solides' : 'Modèle', meshIds: orphans });

  return parts;
}

const DEFAULT_CAD_COLOR = 0x9fb3c8;

/**
 * Charge un fichier CAO.
 * @param {File} file
 * @param {(msg:string)=>void} [onStep] retour d'avancement
 * @returns {Promise<{group:THREE.Group, parts:Array, bbox:THREE.Box3, nTriangles:number, nMeshes:number}>}
 */
export async function loadCadFile(file, onStep = () => {}) {
  const ext = (file.name.split('.').pop() || '').toLowerCase();
  onStep('Initialisation du noyau CAO…');
  const occt = await getOcct();

  onStep('Lecture du fichier…');
  const buf = new Uint8Array(await file.arrayBuffer());

  const params = {
    linearUnit: 'millimeter',
    linearDeflectionType: 'bounding_box_ratio',
    linearDeflection: 0.001,
    angularDeflection: 0.35,
  };

  onStep('Triangulation des surfaces (peut prendre quelques secondes)…');
  await new Promise((r) => setTimeout(r, 30)); // laisse l'overlay s'afficher

  let res;
  if (ext === 'step' || ext === 'stp') res = occt.ReadStepFile(buf, params);
  else if (ext === 'iges' || ext === 'igs') res = occt.ReadIgesFile(buf, params);
  else if (ext === 'brep') res = occt.ReadBrepFile(buf, params);
  else throw new Error(`Format « .${ext} » non pris en charge (attendu : step, stp, iges, igs, brep).`);

  if (!res || !res.success || !Array.isArray(res.meshes) || !res.meshes.length) {
    throw new Error('Le fichier CAO n\'a pu être triangulé (fichier vide ou corrompu ?).');
  }

  onStep('Construction de la scène…');
  const group = new THREE.Group();
  group.name = 'CAO';
  const parts = collectParts(res.root, res.meshes.length);
  let nTriangles = 0;

  const built = res.meshes.map((m) => {
    const geo = new THREE.BufferGeometry();
    const pos = m.attributes?.position?.array;
    if (!pos || !pos.length) return null;
    geo.setAttribute('position', new THREE.Float32BufferAttribute(Float32Array.from(pos), 3));
    const nor = m.attributes?.normal?.array;
    if (nor && nor.length === pos.length) {
      geo.setAttribute('normal', new THREE.Float32BufferAttribute(Float32Array.from(nor), 3));
    }
    if (m.index?.array?.length) {
      const idx = m.index.array;
      geo.setIndex(new THREE.BufferAttribute(
        pos.length / 3 > 65535 ? Uint32Array.from(idx) : Uint16Array.from(idx), 1));
      nTriangles += idx.length / 3;
    } else {
      nTriangles += pos.length / 9;
    }
    if (!nor || nor.length !== pos.length) geo.computeVertexNormals();
    geo.computeBoundingBox();

    const col = Array.isArray(m.color) && m.color.length >= 3
      ? new THREE.Color(m.color[0], m.color[1], m.color[2])
      : new THREE.Color(DEFAULT_CAD_COLOR);

    const mat = new THREE.MeshStandardMaterial({
      color: col, metalness: 0.25, roughness: 0.62,
      transparent: true, opacity: 0.35, depthWrite: false,
      side: THREE.DoubleSide, flatShading: false,
    });
    mat.userData.baseColor = col.getHex();

    const mesh = new THREE.Mesh(geo, mat);
    mesh.name = m.name || '';
    mesh.renderOrder = 1;
    return mesh;
  });

  const partInfos = [];
  for (const p of parts) {
    const g = new THREE.Group();
    g.name = p.name;
    let n = 0;
    for (const i of p.meshIds) {
      const mesh = built[i];
      if (mesh) { g.add(mesh); n++; }
    }
    if (!n) continue;
    group.add(g);
    partInfos.push({
      name: p.name,
      group: g,
      materials: g.children.map((c) => c.material),
      color: '#' + new THREE.Color(g.children[0].material.userData.baseColor).getHexString(),
      visible: true,
    });
  }

  const bbox = new THREE.Box3().setFromObject(group);
  return { group, parts: partInfos, bbox, nTriangles: Math.round(nTriangles), nMeshes: built.filter(Boolean).length };
}

/* =========================================================================
   Raffinement pour l'affichage d'un champ interpolé.

   La triangulation issue du STEP est dimensionnée pour la *géométrie*, pas
   pour un champ : une surface réglée (cylindre) reçoit beaucoup de segments
   circonférentiels mais deux rangées seulement sur la hauteur, soit des
   triangles en lamelles de plusieurs centaines de millimètres. Colorier par
   sommet sur un tel maillage écrase les variations. On subdivise donc par
   bissection du plus long côté jusqu'à une longueur d'arête cible.

   Les positions/normales raffinées sont mises en cache et *partagées* entre
   les vues (seul l'attribut `color` est propre à chaque vue).
   ========================================================================= */

const refineCache = new WeakMap();

function buildRefined(geo, maxEdge, budget) {
  const srcPos = geo.attributes.position;
  const srcNor = geo.attributes.normal;
  const srcIdx = geo.index;
  const nTri = srcIdx ? srcIdx.count / 3 : srcPos.count / 3;
  const maxE2 = maxEdge * maxEdge;

  /* --- 1) soudure des sommets source (position + normale) -----------------
     Indispensable pour que deux triangles voisins partagent l'indice de leurs
     sommets, donc la même décision de découpe. On distingue les normales pour
     ne pas arrondir les arêtes vives. */
  const P = [], N = [];
  const weld = new Map();
  const push = (px, py, pz, nx, ny, nz) => {
    const k = `${Math.round(px * 1e3)},${Math.round(py * 1e3)},${Math.round(pz * 1e3)},`
      + `${Math.round(nx * 50)},${Math.round(ny * 50)},${Math.round(nz * 50)}`;
    let i = weld.get(k);
    if (i === undefined) {
      i = P.length / 3;
      weld.set(k, i);
      P.push(px, py, pz);
      N.push(nx, ny, nz);
    }
    return i;
  };
  let tris = [];
  for (let t = 0; t < nTri * 3; t++) {
    const k = srcIdx ? srcIdx.getX(t) : t;
    tris.push(push(
      srcPos.getX(k), srcPos.getY(k), srcPos.getZ(k),
      srcNor ? srcNor.getX(k) : 0, srcNor ? srcNor.getY(k) : 0, srcNor ? srcNor.getZ(k) : 1));
  }

  /* --- 2) raffinage conforme (« rouge-vert ») ------------------------------
     Une arête est découpée si et seulement si sa longueur dépasse la cible :
     le critère ne dépend que de l'arête, donc les deux triangles qui la
     partagent prennent la même décision — aucun sommet en T, donc aucune
     strie de couleur. Les points milieux sont mutualisés par arête. */
  const long2 = (a, b) => {
    const dx = P[a * 3] - P[b * 3], dy = P[a * 3 + 1] - P[b * 3 + 1], dz = P[a * 3 + 2] - P[b * 3 + 2];
    return dx * dx + dy * dy + dz * dz > maxE2;
  };
  let truncated = false;

  for (let pass = 0; pass < 12; pass++) {
    /* Coût de la passe estimé AVANT de l'exécuter : un motif « 3 arêtes
       longues » quadruple le nombre de triangles, un contrôle a posteriori
       laisserait donc dépasser le budget d'un facteur 4. */
    let predicted = 0, toSplit = 0;
    for (let i = 0; i < tris.length; i += 3) {
      const a = tris[i], b = tris[i + 1], c = tris[i + 2];
      const n = (long2(a, b) ? 1 : 0) + (long2(b, c) ? 1 : 0) + (long2(c, a) ? 1 : 0);
      predicted += n === 3 ? 4 : n === 2 ? 3 : n === 1 ? 2 : 1;
      if (n) toSplit++;
    }
    if (!toSplit) break;
    if (predicted > budget) { truncated = true; break; }

    const mids = new Map();
    const midOf = (a, b) => {
      const lo = a < b ? a : b, hi = a < b ? b : a;
      const key = lo * 1e6 + hi;
      let m = mids.get(key);
      if (m === undefined) {
        m = P.length / 3;
        P.push((P[a * 3] + P[b * 3]) / 2, (P[a * 3 + 1] + P[b * 3 + 1]) / 2, (P[a * 3 + 2] + P[b * 3 + 2]) / 2);
        let nx = N[a * 3] + N[b * 3], ny = N[a * 3 + 1] + N[b * 3 + 1], nz = N[a * 3 + 2] + N[b * 3 + 2];
        const l = Math.hypot(nx, ny, nz) || 1;
        N.push(nx / l, ny / l, nz / l);
        mids.set(key, m);
      }
      return m;
    };

    const out = [];
    let split = 0;
    for (let i = 0; i < tris.length; i += 3) {
      let a = tris[i], b = tris[i + 1], c = tris[i + 2];
      let f0 = long2(a, b), f1 = long2(b, c), f2 = long2(c, a);
      const n = (f0 ? 1 : 0) + (f1 ? 1 : 0) + (f2 ? 1 : 0);
      if (n === 0) { out.push(a, b, c); continue; }
      split++;
      // rotation pour ramener le motif en position canonique
      const rot = () => { const t0 = a; a = b; b = c; c = t0; const g = f0; f0 = f1; f1 = f2; f2 = g; };
      if (n === 1) { while (!f0) rot(); }
      else if (n === 2) { while (!(f0 && f1)) rot(); }

      if (n === 3) {
        const mab = midOf(a, b), mbc = midOf(b, c), mca = midOf(c, a);
        out.push(a, mab, mca, mab, b, mbc, mca, mbc, c, mab, mbc, mca);
      } else if (n === 2) {
        const mab = midOf(a, b), mbc = midOf(b, c);
        out.push(a, mab, mbc, mab, b, mbc, a, mbc, c);
      } else {
        const mab = midOf(a, b);
        out.push(a, mab, c, mab, b, c);
      }
    }
    tris = out;
    if (!split) break;
  }

  const verts = P.length / 3;
  return {
    position: new THREE.Float32BufferAttribute(new Float32Array(P), 3),
    normal: new THREE.Float32BufferAttribute(new Float32Array(N), 3),
    index: new THREE.BufferAttribute(
      verts > 65535 ? new Uint32Array(tris) : new Uint16Array(tris), 1),
    tris: tris.length / 3,
    verts,
    truncated,
  };
}

/**
 * Géométrie destinée au champ interpolé : positions/normales raffinées
 * partagées, attribut `color` propre à l'appelant.
 */
export function fieldGeometry(origGeo, maxEdge, budget = 120000) {
  let byEdge = refineCache.get(origGeo);
  if (!byEdge) { byEdge = new Map(); refineCache.set(origGeo, byEdge); }
  const key = Math.round(maxEdge * 100) / 100;
  let base = byEdge.get(key);
  if (!base) { base = buildRefined(origGeo, maxEdge, budget); byEdge.set(key, base); }

  const g = new THREE.BufferGeometry();
  g.setAttribute('position', base.position);
  g.setAttribute('normal', base.normal);
  g.setIndex(base.index);
  g.setAttribute('color', new THREE.BufferAttribute(new Float32Array(base.verts * 3).fill(0.55), 3));
  g.userData.fieldMaxEdge = key;
  g.userData.fieldTris = base.tris;
  g.userData.fieldVerts = base.verts;
  g.userData.fieldTruncated = base.truncated;
  g.computeBoundingSphere();
  return g;
}

const EDGE_NAME = '__edges';

/**
 * Construit une fois pour toutes les arêtes de contour sur le groupe « maître ».
 * À appeler avant de cloner le groupe dans les vues.
 */
export function ensureCadEdges(group, color = 0x14212e) {
  let created = 0;
  const meshes = [];
  group.traverse((o) => { if (o.isMesh && !o.userData.isEdge) meshes.push(o); });
  for (const o of meshes) {
    if (o.children.some((c) => c.name === EDGE_NAME)) continue;
    try {
      const eg = new THREE.EdgesGeometry(o.geometry, 22);
      const edge = new THREE.LineSegments(eg, new THREE.LineBasicMaterial({
        color, transparent: true, opacity: 0.6, depthWrite: false,
      }));
      edge.name = EDGE_NAME;
      edge.userData.isEdge = true;
      edge.renderOrder = 3;
      edge.visible = false;
      o.add(edge);
      created++;
    } catch (e) { /* géométrie non exploitable */ }
  }
  return created;
}

export function hasCadEdges(group) {
  let found = false;
  group.traverse((o) => { if (o.name === EDGE_NAME) found = true; });
  return found;
}

/** Affiche / masque les arêtes déjà construites. */
export function setCadEdgesVisible(group, on) {
  group.traverse((o) => { if (o.name === EDGE_NAME) o.visible = !!on; });
}
