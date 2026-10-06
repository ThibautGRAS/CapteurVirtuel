/* =========================================================================
   Lecture et mise à plat du JSON d'analyse des mesures.

   Trois structures sont reconnues (detectFormat) :
     * 'mesure1' — DataMesure 1 : excitation > famille > groupe (décrit ci-dessous) ;
     * 'mesure2' — DataMesure 2 : excitation > groupe, une ligne par capteur,
       chaque capteur portant un nom unique (sensor_name) ;
     * 'iso'     — DataISO7849_1 / _2 : <racine> > TEST > excitation, tiers
       d'octave uniquement (pas de niveau global).
   Les deux derniers formats sont ramenés au même modèle que le premier, à
   raison d'une « mesure » (run) par capteur : toute la chaîne d'affichage
   (billes, échelle, RBF, fiche) reste commune. `model.flat` les signale.

   Structure DataMesure 1 attendue (tolérante) :
     { EXCITATION1: { <famille>: { <groupe capteurs>: {
            run_info: { run_name:[N], position:[N], repetition:[N] },
            sensor_name: [S],
            sensor_coordinates: [N][S][3],
            Data_3rdOctave_Vel: [N][S][B],
            Data_GlobalLevel_Vel: [N][S],
            frq_3rdOctave: [B],
            unit: [S]
       } } }, EXCITATION2: {...}, ... }

   Particularité gérée : les coordonnées capteurs ne sont renseignées que
   pour une (ou quelques) excitation(s). Elles sont donc mutualisées entre
   excitations en s'appuyant sur le nom de mesure privé de son préfixe
   « Exc<n>_ » (identique d'une excitation à l'autre).
   ========================================================================= */

const FAM_LABELS = {
  base: 'Base',
  cylindre: 'Cylindre',
  cylinder: 'Cylindre',
  dome: 'Dôme',
  plaque: 'Plaque',
  structure: 'Structure intégrale',
};

export const EXC_COLORS = ['#f28100', '#00a3d7', '#3ecf8e', '#c86bd8', '#f5d442'];

/* --- petits utilitaires --------------------------------------------------- */

const isObj = (o) => o !== null && typeof o === 'object' && !Array.isArray(o);
const isArr = Array.isArray;
const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : NaN);

/** Tri « naturel » : hauteur_18deg passe après hauteur_0deg et avant hauteur_36deg. */
export function naturalCompare(a, b) {
  const ra = String(a).match(/(\d+|\D+)/g) || [];
  const rb = String(b).match(/(\d+|\D+)/g) || [];
  for (let i = 0; i < Math.max(ra.length, rb.length); i++) {
    const x = ra[i], y = rb[i];
    if (x === undefined) return -1;
    if (y === undefined) return 1;
    const nx = parseFloat(x), ny = parseFloat(y);
    if (!isNaN(nx) && !isNaN(ny)) { if (nx !== ny) return nx - ny; }
    else { const c = x.localeCompare(y, 'fr'); if (c) return c; }
  }
  return 0;
}

const capitalize = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const famLabel = (k) => FAM_LABELS[k.toLowerCase()] || capitalize(k.replace(/_/g, ' '));
const excLabel = (k) => {
  const m = k.match(/^EXCITATION[_\s]*(\d+)$/i);
  return m ? `Excitation ${m[1]}` : k.replace(/_/g, ' ');
};

/** Retire le préfixe d'excitation d'un nom de mesure. */
function runKeyOf(runName, famKey) {
  let s = String(runName).replace(/^exc(itation)?[_\-\s]*\d+[_\-\s]*/i, '');
  return s || String(runName);
}

/** Libellé court affiché dans l'arbre des mesures. */
function runLabelOf(runKey, famKey) {
  let s = runKey;
  const fam = famKey.toLowerCase();
  if (s.toLowerCase().startsWith(fam)) s = s.slice(fam.length).replace(/^[_\-\s]+/, '');
  return (s || runKey).replace(/_/g, ' ');
}

/* --- reconnaissance des clés de données ---------------------------------- */

const KEY_SETS = [
  { third: 'Data_3rdOctave_Vel', global: 'Data_GlobalLevel_Vel', quantity: 'Vitesse vibratoire' },
  { third: 'Data_3rdOctave', global: 'Data_GlobalLevel', quantity: 'Accélération / niveau brut' },
];

function pickKeySet(block) {
  for (const ks of KEY_SETS) {
    if (isArr(block[ks.third]) || isArr(block[ks.global])) return ks;
  }
  return null;
}

/**
 * Inventaire rapide du fichier : excitations, familles, groupes de capteurs.
 */
export function scanJson(json) {
  if (!isObj(json)) throw new Error('Le JSON ne contient pas un objet racine.');
  const excitations = Object.keys(json).filter((k) => isObj(json[k]));
  if (!excitations.length) throw new Error('Aucune excitation trouvée à la racine du JSON.');
  excitations.sort(naturalCompare);

  const families = [];
  const groups = new Map(); // nom -> nb d'occurrences exploitables
  for (const e of excitations) {
    for (const f of Object.keys(json[e])) {
      if (!isObj(json[e][f])) continue;
      if (!families.includes(f)) families.push(f);
      for (const g of Object.keys(json[e][f])) {
        const blk = json[e][f][g];
        if (isObj(blk) && pickKeySet(blk)) groups.set(g, (groups.get(g) || 0) + 1);
      }
    }
  }
  families.sort(naturalCompare);
  if (!groups.size) throw new Error("Aucun groupe de capteurs exploitable (clés Data_*_Vel absentes).");

  // « Accel » en tête si présent
  const groupList = [...groups.keys()].sort((a, b) =>
    (a === 'Accel' ? -1 : b === 'Accel' ? 1 : naturalCompare(a, b)));

  return { excitations, families, groups: groupList };
}

/* --- reconnaissance du format ---------------------------------------------- */

/** Racine d'un fichier ISO 7849 : objet dont les enfants TEST* contiennent des excitations avec Accel_name. */
function findIsoRoot(json) {
  for (const k of Object.keys(json)) {
    const o = json[k];
    if (!isObj(o)) continue;
    const hasTest = Object.keys(o).some((t) => /^TEST/i.test(t) && isObj(o[t])
      && Object.values(o[t]).some((x) => isObj(x) && isArr(x.Accel_name)));
    if (hasTest) return k;
  }
  return null;
}

/** Bloc capteurs placé directement sous une excitation (DataMesure 2). */
function flatBlocks(json) {
  const out = [];
  for (const e of Object.keys(json)) {
    if (!isObj(json[e])) continue;
    for (const g of Object.keys(json[e])) {
      const blk = json[e][g];
      if (isObj(blk) && pickKeySet(blk)) out.push({ exc: e, group: g });
    }
  }
  return out;
}

const isoLabel = (m) => String(m).replace(/^ISO\s*(\d+)[_\-\s]?(\d+)?$/i, (s, a, b) => `ISO ${a}${b ? '-' + b : ''}`);

/**
 * Identifie la structure du fichier et liste ce que l'utilisateur peut choisir.
 * @returns {{kind:'mesure1'|'mesure2'|'iso', label:string, groups:string[], tests:string[], root?:string}}
 */
export function detectFormat(json) {
  if (!isObj(json)) throw new Error('Le JSON ne contient pas un objet racine.');

  const root = findIsoRoot(json);
  if (root) {
    const tests = Object.keys(json[root]).filter((t) => isObj(json[root][t])).sort(naturalCompare);
    const methode = json.Metadata?.methode || root.replace(/^Data/i, '');
    return { kind: 'iso', label: `Méthode ${isoLabel(methode)}`, root, tests, groups: [] };
  }

  const flat = flatBlocks(json);
  if (flat.length) {
    const groups = [...new Set(flat.map((b) => b.group))].sort((a, b) =>
      (a === 'Accel' ? -1 : b === 'Accel' ? 1 : naturalCompare(a, b)));
    return { kind: 'mesure2', label: 'DataMesure 2 — capteurs à nom unique', groups, tests: [] };
  }

  const scan = scanJson(json);
  return { kind: 'mesure1', label: 'DataMesure 1 — mesures par famille', groups: scan.groups, tests: [] };
}

/**
 * Construit le modèle exploitable par l'application.
 * @param {object} json  contenu brut du fichier
 * @param {{group?:string, test?:string}} opts groupe de capteurs (« Accel ») / test ISO
 */
export function buildModel(json, opts = {}) {
  const fmt = detectFormat(json);
  let model;
  if (fmt.kind === 'iso') model = buildModelIso(json, fmt, opts.test);
  else if (fmt.kind === 'mesure2') model = buildModelFlat(json, fmt, opts.group);
  else model = buildModelV1(json, opts.group);
  model.format = fmt.kind;
  model.formatLabel = fmt.label;
  return model;
}

/** Modèle d'une liste de capteurs uniques (DataMesure 2 et ISO) : un run par capteur. */
function flatModel({ group, excitations, sensors, freqs, quantity, hasGlobal, famTitle, warnings, extra }) {
  const runList = [...sensors.values()].sort((a, b) => naturalCompare(a.key, b.key));
  let nNoCoord = 0;
  for (const run of runList) {
    if (!run.coords[0]) nNoCoord++;
    run.nCoords = run.coords[0] ? 1 : 0;
  }
  if (nNoCoord) warnings.push(`<b>${nNoCoord}</b> capteur(s) sans coordonnées : non représenté(s) en 3D.`);
  return {
    group,
    excitations,
    families: [{ key: '', label: 'Capteurs', runs: runList }],
    runList,
    runById: new Map(runList.map((r) => [r.id, r])),
    freqs: freqs || [],
    nBands: freqs ? freqs.length : 0,
    quantity,
    rawUnit: null,
    unit: 'dB',
    warnings,
    availableGroups: [group],
    flat: true,
    hasGlobal,
    famTitle,
    ...extra,
  };
}

/** Capteur (run à un seul capteur) créé à la première rencontre de son nom. */
function sensorRun(sensors, name, famLabelTxt) {
  if (!sensors.has(name)) {
    sensors.set(name, {
      id: name, famKey: '', famLabel: famLabelTxt,
      key: name, label: name,
      fullNames: {}, data: {},
      sensorNames: [name], nSensors: 1,
      coords: [null], coordsFrom: null,
    });
  }
  return sensors.get(name);
}

function readCoord(p) {
  if (!isArr(p) || p.length < 3) return null;
  const x = num(p[0]), y = num(p[1]), z = num(p[2]);
  return isNaN(x) || isNaN(y) || isNaN(z) ? null : [x, y, z];
}

/**
 * DataMesure 2 : { EXCITATION<n>: { Accel: { sensor_name:[N], run_info:{run_name:[N]},
 *   sensor_coordinates:[N][3], Data_3rdOctave_Vel:[N][B], Data_GlobalLevel_Vel:[N] } } }
 * Une ligne = un capteur, identifié par son nom unique (pas par son nom dans le lot).
 */
function buildModelFlat(json, fmt, group) {
  group = fmt.groups.includes(group) ? group : fmt.groups[0];
  const warnings = [];
  const all = Object.keys(json).filter((k) => isObj(json[k]?.[group]) && pickKeySet(json[k][group]));
  /* Seules les excitations sont retenues : le bruit de fond (BDF) ne porte pas
     de coordonnées et ses noms de capteurs sont des noms de lot, qui
     récupéreraient à tort la position des capteurs homonymes. */
  const excKeys = all.some((k) => /^exc/i.test(k)) ? all.filter((k) => /^exc/i.test(k)) : all;
  const ignored = all.filter((k) => !excKeys.includes(k));
  if (ignored.length) warnings.push(`Bloc(s) ${ignored.join(', ')} ignoré(s) : pas de coordonnées capteurs.`);
  excKeys.sort(naturalCompare);
  if (!excKeys.length) throw new Error('Aucune excitation exploitable dans ce fichier DataMesure 2.');

  const excitations = excKeys.map((key, i) => ({ key, label: excLabel(key), color: EXC_COLORS[i % EXC_COLORS.length] }));
  const sensors = new Map();
  let freqs = null, quantity = null, nDup = 0;

  for (const exc of excKeys) {
    const blk = json[exc][group];
    const ks = pickKeySet(blk);
    if (!quantity) quantity = ks.quantity;
    if (!freqs && isArr(blk.frq_3rdOctave) && blk.frq_3rdOctave.length) freqs = blk.frq_3rdOctave.map(Number);
    const names = isArr(blk.sensor_name) ? blk.sensor_name : [];
    const runNames = blk.run_info?.run_name;
    const third = isArr(blk[ks.third]) ? blk[ks.third] : null;
    const glob = isArr(blk[ks.global]) ? blk[ks.global] : null;
    const coords = isArr(blk.sensor_coordinates) ? blk.sensor_coordinates : null;
    const n = Math.max(names.length, third ? third.length : 0, glob ? glob.length : 0);
    const seen = new Set();

    for (let r = 0; r < n; r++) {
      let name = names[r] != null ? String(names[r]) : `Capteur ${String(r + 1).padStart(3, '0')}`;
      if (seen.has(name)) { nDup++; let k = 2; while (seen.has(`${name} (${k})`)) k++; name = `${name} (${k})`; }
      seen.add(name);
      const runName = isArr(runNames) && runNames[r] != null ? String(runNames[r]) : exc;
      const run = sensorRun(sensors, name, runKeyOf(runName).replace(/_/g, ' '));
      run.fullNames[exc] = runName;
      run.data[exc] = {
        third: third && isArr(third[r]) ? [third[r]] : null,
        global: glob && glob[r] != null ? [glob[r]] : null,
      };
      if (!run.coords[0]) {
        const c = readCoord(coords && coords[r]);
        if (c) { run.coords[0] = c; run.coordsFrom = exc; }
      }
    }
  }
  if (nDup) warnings.push(`<b>${nDup}</b> nom(s) de capteur en double dans une même excitation : suffixés.`);

  return flatModel({
    group, excitations, sensors, freqs,
    quantity: quantity || 'Niveau', hasGlobal: true,
    famTitle: 'Mesure d\'origine', warnings, extra: {},
  });
}

/**
 * DataISO7849_1 / _2 : { DataISO7849_x: { TEST<n>: { EXCITATION<n>: {
 *   Accel_name:[S], Accel_coordinates:[S][3], Data_3rdOctave_Vel:[S][B], frq_3rdOctave:[B] } } },
 *   Metadata: {...} }
 * Seul le spectre de vitesse en tiers d'octave est exploité (pas de niveau global).
 */
function buildModelIso(json, fmt, test) {
  if (!fmt.tests.length) throw new Error('Aucun TEST dans ce fichier ISO 7849.');
  test = fmt.tests.includes(test) ? test : fmt.tests[0];
  const T = json[fmt.root][test];
  const excKeys = Object.keys(T).filter((k) => isObj(T[k]) && isArr(T[k].Accel_name)).sort(naturalCompare);
  if (!excKeys.length) throw new Error(`Aucune excitation exploitable dans ${test}.`);
  const warnings = [];
  const excitations = excKeys.map((key, i) => ({ key, label: excLabel(key), color: EXC_COLORS[i % EXC_COLORS.length] }));
  const sensors = new Map();
  let freqs = null, nNoData = 0;

  for (const exc of excKeys) {
    const E = T[exc];
    if (!freqs && isArr(E.frq_3rdOctave) && E.frq_3rdOctave.length) freqs = E.frq_3rdOctave.map(Number);
    const third = isArr(E.Data_3rdOctave_Vel) ? E.Data_3rdOctave_Vel : null;
    if (!third) nNoData++;
    const coords = isArr(E.Accel_coordinates) ? E.Accel_coordinates : null;
    E.Accel_name.forEach((nm, s) => {
      const name = String(nm);
      const run = sensorRun(sensors, name, test.replace(/_/g, ' '));
      run.fullNames[exc] = `${fmt.label.replace(/^Méthode /, '')} · ${test}`;
      run.data[exc] = { third: third && isArr(third[s]) ? [third[s]] : null, global: null };
      if (!run.coords[0]) {
        const c = readCoord(coords && coords[s]);
        if (c) { run.coords[0] = c; run.coordsFrom = exc; }
      }
    });
  }
  if (nNoData) warnings.push(`<b>${nNoData}</b> excitation(s) sans Data_3rdOctave_Vel dans ${test}.`);

  return flatModel({
    group: 'Accel', excitations, sensors, freqs,
    quantity: 'Vitesse vibratoire', hasGlobal: false,
    famTitle: 'Test', warnings,
    extra: { tests: fmt.tests, test },
  });
}

/**
 * DataMesure 1 : construit le modèle pour un groupe de capteurs.
 * @param {object} json  contenu brut du fichier
 * @param {string} group nom du groupe (ex. « Accel »)
 */
function buildModelV1(json, group) {
  const scan = scanJson(json);
  if (!scan.groups.includes(group)) group = scan.groups.includes('Accel') ? 'Accel' : scan.groups[0];
  const excitations = scan.excitations.map((key, i) => ({
    key, label: excLabel(key), color: EXC_COLORS[i % EXC_COLORS.length],
  }));

  const warnings = [];
  let freqs = null;
  let quantity = null;
  let rawUnit = null;

  /* 1) Collecte : famille -> runKey -> { fullNames, data par excitation, coords candidates } */
  const famMap = new Map();

  for (const exc of scan.excitations) {
    for (const famKey of Object.keys(json[exc] || {})) {
      const blk = json[exc][famKey]?.[group];
      if (!isObj(blk)) continue;
      const ks = pickKeySet(blk);
      if (!ks) continue;
      if (!quantity) quantity = ks.quantity;

      const names = blk.run_info?.run_name;
      const third = isArr(blk[ks.third]) ? blk[ks.third] : null;
      const glob = isArr(blk[ks.global]) ? blk[ks.global] : null;
      const coords = isArr(blk.sensor_coordinates) ? blk.sensor_coordinates : null;
      const sensorNames = isArr(blk.sensor_name) ? blk.sensor_name.map(String) : null;
      const pos = blk.run_info?.position;
      const rep = blk.run_info?.repetition;

      if (isArr(blk.frq_3rdOctave) && blk.frq_3rdOctave.length && !freqs) {
        freqs = blk.frq_3rdOctave.map(Number);
      }
      if (!rawUnit && isArr(blk.unit) && blk.unit.length) rawUnit = String(blk.unit[0]);

      const nRuns = Math.max(
        isArr(names) ? names.length : 0,
        third ? third.length : 0,
        glob ? glob.length : 0,
      );
      if (!nRuns) continue;

      if (!famMap.has(famKey)) famMap.set(famKey, new Map());
      const runs = famMap.get(famKey);

      for (let r = 0; r < nRuns; r++) {
        const fullName = isArr(names) && names[r] != null ? String(names[r]) : `${famKey}_run${r + 1}`;
        const rk = runKeyOf(fullName, famKey);

        if (!runs.has(rk)) {
          runs.set(rk, {
            id: `${famKey}::${rk}`,
            famKey, famLabel: famLabel(famKey),
            key: rk, label: runLabelOf(rk, famKey),
            fullNames: {}, data: {}, coordCandidates: [],
            sensorNames: sensorNames ? sensorNames.slice() : null,
            position: isArr(pos) ? pos[r] : undefined,
            repetition: isArr(rep) ? rep[r] : undefined,
            nSensors: 0, coords: null, coordsFrom: null,
          });
        }
        const run = runs.get(rk);
        run.fullNames[exc] = fullName;
        if (!run.sensorNames && sensorNames) run.sensorNames = sensorNames.slice();

        const dThird = third && isArr(third[r]) ? third[r] : null;
        const dGlob = glob && isArr(glob[r]) ? glob[r] : null;
        run.data[exc] = { third: dThird, global: dGlob };
        run.nSensors = Math.max(run.nSensors, dThird ? dThird.length : 0, dGlob ? dGlob.length : 0);

        const c = coords && isArr(coords[r]) ? coords[r] : null;
        if (c && c.length) run.coordCandidates.push({ exc, c });
      }
    }
  }

  /* 2) Résolution des coordonnées (mutualisation entre excitations, capteur par capteur) */
  const runList = [];
  const families = [];
  let nNoCoord = 0, nPartial = 0;

  for (const famKey of [...famMap.keys()].sort(naturalCompare)) {
    const runs = [...famMap.get(famKey).values()].sort((a, b) => naturalCompare(a.key, b.key));
    for (const run of runs) {
      const S = Math.max(run.nSensors, run.sensorNames ? run.sensorNames.length : 0);
      run.nSensors = S;
      if (!run.sensorNames || run.sensorNames.length < S) {
        run.sensorNames = Array.from({ length: S }, (_, i) =>
          (run.sensorNames && run.sensorNames[i]) || `Capteur ${String(i + 1).padStart(2, '0')}`);
      }
      const coords = new Array(S).fill(null);
      let got = 0;
      for (const cand of run.coordCandidates) {
        for (let s = 0; s < S; s++) {
          if (coords[s]) continue;
          const p = cand.c[s];
          if (isArr(p) && p.length >= 3) {
            const x = num(p[0]), y = num(p[1]), z = num(p[2]);
            if (!isNaN(x) && !isNaN(y) && !isNaN(z)) {
              coords[s] = [x, y, z];
              got++;
              if (!run.coordsFrom) run.coordsFrom = cand.exc;
            }
          }
        }
        if (got === S) break;
      }
      run.coords = coords;
      run.nCoords = got;
      delete run.coordCandidates;
      if (got === 0) nNoCoord++;
      else if (got < S) nPartial++;
      runList.push(run);
    }
    families.push({ key: famKey, label: famLabel(famKey), runs });
  }

  if (nNoCoord) warnings.push(`<b>${nNoCoord}</b> mesure(s) sans aucune coordonnée capteur : non représentée(s) en 3D.`);
  if (nPartial) warnings.push(`<b>${nPartial}</b> mesure(s) avec des coordonnées partielles.`);

  const excWithCoords = new Set(runList.map((r) => r.coordsFrom).filter(Boolean));
  if (excitations.length > 1 && excWithCoords.size < excitations.length) {
    warnings.push(`Coordonnées capteurs renseignées uniquement pour ${[...excWithCoords].map(excLabel).join(', ')} : elles sont réutilisées pour les autres excitations (mesures homologues).`);
  }

  if (!freqs) freqs = [];

  return {
    group,
    excitations,
    families,
    runList,
    runById: new Map(runList.map((r) => [r.id, r])),
    freqs,
    nBands: freqs.length,
    quantity: quantity || 'Niveau',
    rawUnit,
    unit: 'dB',
    warnings,
    availableGroups: scan.groups,
    flat: false,
    hasGlobal: true,
    famTitle: 'Famille',
  };
}

/** Valeur affichée pour un capteur donné. */
export function sensorValue(run, excKey, sensorIdx, mode, band) {
  const d = run.data[excKey];
  if (!d) return NaN;
  if (mode === 'band') {
    const row = d.third && d.third[sensorIdx];
    return isArr(row) ? num(row[band]) : NaN;
  }
  return d.global ? num(d.global[sensorIdx]) : NaN;
}

/** Spectre complet d'un capteur (pour la fiche capteur). */
export function sensorSpectrum(run, excKey, sensorIdx) {
  const d = run.data[excKey];
  const row = d && d.third && d.third[sensorIdx];
  return isArr(row) ? row.map(num) : null;
}

/**
 * Construit la liste des billes à afficher.
 * @returns {Array} [{run, excKey, si, name, runName, pos:[x,y,z], value}]
 */
export function buildRecords(model, runIds, excKey, mode, band) {
  const out = [];
  for (const id of runIds) {
    const run = model.runById.get(id);
    if (!run) continue;
    for (let s = 0; s < run.nSensors; s++) {
      const p = run.coords[s];
      if (!p) continue;
      const v = sensorValue(run, excKey, s, mode, band);
      if (!Number.isFinite(v)) continue;
      out.push({
        run, excKey, si: s,
        name: run.sensorNames[s],
        runName: run.fullNames[excKey] || run.key,
        pos: p, value: v,
      });
    }
  }
  return out;
}

/** Étendue min/max des valeurs pour un jeu de mesures / excitations. */
export function valueRange(model, runIds, excKeys, mode, band) {
  let mn = Infinity, mx = -Infinity;
  for (const id of runIds) {
    const run = model.runById.get(id);
    if (!run) continue;
    for (const e of excKeys) {
      for (let s = 0; s < run.nSensors; s++) {
        if (!run.coords[s]) continue;
        const v = sensorValue(run, e, s, mode, band);
        if (!Number.isFinite(v)) continue;
        if (v < mn) mn = v;
        if (v > mx) mx = v;
      }
    }
  }
  if (!isFinite(mn) || !isFinite(mx)) return null;
  if (mx - mn < 1e-6) { mn -= 1; mx += 1; }
  return [mn, mx];
}

/** Formatage d'une fréquence de tiers d'octave. */
export function formatFreq(f) {
  if (!Number.isFinite(f)) return '—';
  if (f >= 1000) {
    const k = f / 1000;
    return `${(Math.round(k * 100) / 100).toString().replace('.', ',')} kHz`;
  }
  return `${Math.round(f)} Hz`;
}
