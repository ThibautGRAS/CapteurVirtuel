/* =========================================================================
   VISUDATA — application principale
   Chargement CAO + mesures, pilotage de l'interface, synchronisation des vues.
   ========================================================================= */

import * as THREE from 'three';
import { Scene3D } from './scene3d.js';
import {
  loadCadFile, ensureCadEdges, hasCadEdges, setCadEdgesVisible, warmup,
} from './cadLoader.js';
import {
  buildModel, detectFormat, buildRecords, valueRange, sensorValue, sensorSpectrum, formatFreq,
} from './dataModel.js';
import { colormap, listColormaps, paintGradient, cssColor } from './colormaps.js';
import { KERNELS, POLY, buildRbf, meanNearestDistance } from './interp.js';
import {
  fsaAvailable, pickFile, putHandle, getHandle, fileFromHandle, handleOfDropItem,
  saveJson, readJson, fileMeta,
} from './project.js';

const $ = (id) => document.getElementById(id);
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const fmt = (v, d = 1) => (Number.isFinite(v) ? v.toFixed(d).replace('.', ',') : '—');

/* ============================== ÉTAT ============================== */

const state = {
  rawJson: null,
  model: null,
  cad: null,                 // { group, parts, bbox, ... }
  group: null,               // groupe de capteurs actif (Accel…)
  test: null,                // test affiché (format ISO 7849)

  excSel: new Set(),
  mode: 'global',            // 'global' | 'band'
  band: 0,

  selRuns: new Set(),
  famOpen: new Set(),

  cmap: 'cetim',
  autoScale: true,
  vmin: 0, vmax: 1,
  clampOut: true,

  radiusT: 0.49,             // position du curseur (échelle log)
  radius: 5,
  ballOpacity: 1,
  scaleByLevel: false,
  inspect: true,
  labels: true,              // étiquettes de noms (formats à capteurs nommés) ; null = auto

  cadScale: 1,
  cadT: [0, 0, 0],
  cadR: [0, 0, 0],
  cadPivot: false,
  cadOpacity: 0.35,
  cadEdges: false,
  cadFlat: true,
  hiddenParts: new Set(),

  showGrid: true,
  showAxes: true,
  showBox: false,
  persp: true,
  sync: true,
  theme: 'dark',

  selected: null,            // { rec, idx, excKey }
  hover: null,
  detailBig: false,
  excFilter: new Set(),      // excitations masquées dans le graphe de la fiche

  files: { cad: null, json: null },   // métadonnées (nom, taille) des fichiers chargés

  interp: {
    on: false,
    kernel: 'gauss',
    eps: 0, epsAuto: true,
    lambda: 1e-3,
    poly: 'const',
    mask: true, dmax: 0,
    opacity: 1,
    maxPts: 400,
    live: true,
    display: 'both',         // 'both' | 'surf'
    meshStep: 0,             // longueur d'arête cible du maillage du champ (mm)
    unlit: true,             // couleurs non modulées par l'éclairage
  },
};

const LABELS_AUTO_MAX = 60;  // étiquettes affichées d'office jusqu'à ce nombre de capteurs

let pendingProject = null;   // projet à appliquer dès que les mesures seront là
let interpTimer = null;

const views = new Map();     // key -> { key, label, color, el, scene, meta }
let sceneSize = 500;         // dimension caractéristique (mm)
let sensorBox = null;        // THREE.Box3 des capteurs
let syncing = false;

/* ============================== UTILITAIRES UI ============================== */

function toast(msg, type = '') {
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  $('toasts').appendChild(t);
  setTimeout(() => { t.style.transition = 'opacity .3s'; t.style.opacity = '0'; }, type === 'err' ? 5200 : 2600);
  setTimeout(() => t.remove(), type === 'err' ? 5600 : 3000);
}

function showLoading(txt) { $('loadingTxt').textContent = txt; $('loading').hidden = false; }
function setLoading(txt) { $('loadingTxt').textContent = txt; }
function hideLoading() { $('loading').hidden = true; }

/* ============================== CHARGEMENT FICHIERS ============================== */

async function handleFile(file, handle = null) {
  const ext = (file.name.split('.').pop() || '').toLowerCase();
  if (ext === 'json') {
    // un fichier .json peut aussi être un projet VISUDATA
    try {
      const probe = JSON.parse(await file.text());
      if (probe && probe.app === 'VISUDATA') return openProjectObject(probe, file.name);
      return loadJson(file, handle, probe);
    } catch (e) {
      toast('JSON illisible : ' + e.message, 'err');
      return;
    }
  }
  if (['step', 'stp', 'iges', 'igs', 'brep'].includes(ext)) return loadCad(file, handle);
  toast(`Format « .${ext} » non reconnu.`, 'err');
}

async function loadJson(file, handle = null, parsed = null) {
  showLoading('Lecture du fichier de mesures…');
  try {
    const json = parsed || JSON.parse(await file.text());
    const fmt = detectFormat(json);
    state.rawJson = json;
    state.group = fmt.groups.includes('Accel') ? 'Accel' : (fmt.groups[0] || null);
    state.test = fmt.tests[0] || null;
    // changement de fichier (et éventuellement de format) : rien de l'ancien modèle ne survit
    state.selected = null;
    state.excFilter.clear();
    state.excSel.clear();
    state.labels = null;           // choix automatique selon le nombre de capteurs
    buildFromJson();
    if (state.cad) { attachCad(); applyCadTransform(); applyCadAppearance(); applyInterp(true); }
    state.files.json = fileMeta(file);
    if (handle) putHandle('json', handle);
    $('jsonName').textContent = `${file.name} — ${(file.size / 1048576).toFixed(1)} Mo`;
    $('dropJson').classList.add('ok');
    toast(state.model.flat
      ? `${state.model.formatLabel} : ${state.model.runList.length} capteurs chargés`
      : `${state.model.runList.length} mesures chargées`, 'ok');
    if (pendingProject) { const p = pendingProject; pendingProject = null; applyProject(p); }
  } catch (e) {
    console.error(e);
    toast('JSON illisible : ' + e.message, 'err');
  } finally {
    hideLoading();
    updateFileBadge();
  }
}

function buildFromJson() {
  const model = buildModel(state.rawJson, { group: state.group, test: state.test });
  state.model = model;
  state.group = model.group;
  if (model.test) state.test = model.test;

  // sélections par défaut : tout coché ; les excitations déjà affichées sont
  // conservées si elles existent encore (changement de test ou de groupe)
  state.selRuns = new Set(model.runList.map((r) => r.id));
  const keepExc = model.excitations.filter((e) => state.excSel.has(e.key)).map((e) => e.key);
  // à défaut, première excitation ayant des billes affichables (un bloc BDF
  // placé en tête, sans coordonnées, ouvrirait sinon une vue vide)
  const firstExc = model.excitations.find((e) => valueRange(model, [...state.selRuns], [e.key], 'global', 0)
    || valueRange(model, [...state.selRuns], [e.key], 'band', 0)) || model.excitations[0];
  state.excSel = new Set(keepExc.length ? keepExc : (firstExc ? [firstExc.key] : []));
  state.famOpen = new Set(model.families.map((f) => f.key));
  state.band = Math.min(state.band, Math.max(0, model.nBands - 1));
  if (!model.nBands) state.mode = 'global';
  if (!model.hasGlobal && model.nBands) state.mode = 'band';   // ISO 7849 : tiers d'octave uniquement
  if (state.selected && !model.runById.has(state.selected.rec.run.id)) state.selected = null;
  // au-delà de LABELS_AUTO_MAX capteurs les étiquettes se recouvrent : survol seul par défaut
  if (state.labels === null) state.labels = model.runList.length <= LABELS_AUTO_MAX;

  // boîte englobante des capteurs -> dimension caractéristique
  sensorBox = new THREE.Box3();
  for (const r of model.runList) {
    for (const p of r.coords) if (p) sensorBox.expandByPoint(new THREE.Vector3(p[0], p[1], p[2]));
  }
  if (sensorBox.isEmpty()) sensorBox = null;
  sceneSize = sensorBox ? Math.max(sensorBox.getSize(new THREE.Vector3()).length(), 10) : 500;
  state.radius = radiusFromT(state.radiusT);

  buildExcChips();
  buildTestSelect();
  buildGroupSelect();
  buildRunTree();
  buildBandSlider();
  setupRangeBounds();
  setupInterpBounds();
  showPanels(true);
  refreshWarnings();
  refreshFormatInfo();
  $('labelsWrap').hidden = !model.flat;
  $('chkLabels').checked = state.labels;

  rebuildViews(true);
  refreshAll();
  updateInterpUI();
  applyInterp(true);
}

async function loadCad(file, handle = null) {
  showLoading('Initialisation du noyau CAO…');
  try {
    const cad = await loadCadFile(file, setLoading);
    state.files.cad = fileMeta(file);
    if (handle) putHandle('cad', handle);
    // noms de pièces uniques (indispensable pour les bascules de visibilité)
    const used = new Map();
    for (const p of cad.parts) {
      let n = p.name;
      if (used.has(n)) { const k = used.get(n) + 1; used.set(n, k); n = `${p.name} (${k})`; }
      else used.set(n, 1);
      p.name = n; p.group.name = n;
    }
    state.cad = cad;
    state.hiddenParts.clear();
    $('cadName').textContent = `${file.name} — ${cad.parts.length} pièce(s), ${cad.nTriangles.toLocaleString('fr-FR')} triangles`;
    $('dropCad').classList.add('ok');
    $('badgeCad').textContent = `${cad.parts.length} pc`;
    $('badgeParts').textContent = cad.parts.length;
    buildPartList();
    showPanels(!!state.model);
    document.querySelector('[data-sec="cad"]').hidden = false;
    document.querySelector('[data-sec="cad"]').classList.add('open');

    if (!views.size) rebuildViews(true);
    attachCad();
    applyCadTransform();
    applyCadAppearance();
    updateInterpUI();
    applyInterp(true);
    fitAll();
    toast('CAO chargée', 'ok');
  } catch (e) {
    console.error(e);
    toast('CAO : ' + e.message, 'err');
  } finally {
    hideLoading();
    updateFileBadge();
  }
}

function updateFileBadge() {
  const n = (state.cad ? 1 : 0) + (state.model ? 1 : 0);
  $('badgeFiles').textContent = `${n}/2`;
  $('emptyState').hidden = n > 0;
  $('metricReadout').hidden = !state.model;
  $('colorbar').hidden = !state.model;
}

function refreshWarnings() {
  const w = state.model?.warnings || [];
  const box = $('warnBox');
  box.hidden = !w.length;
  box.innerHTML = w.map((x) => `<div>• ${x}</div>`).join('');
}

/** Encart « format détecté » de la carte Fichiers. */
function refreshFormatInfo() {
  const m = state.model;
  const box = $('fmtBox');
  box.hidden = !m;
  if (!m) return;
  const nExc = m.excitations.length;
  const parts = [`Format : <b>${m.formatLabel}</b>`];
  if (m.tests) parts.push(`${m.tests.length} test(s) · ${nExc} excitation(s) dans ${m.test}`);
  else parts.push(`${nExc} excitation(s)`);
  parts.push(m.flat ? `${m.runList.length} capteur(s)` : `${m.runList.length} mesure(s)`);
  if (!m.hasGlobal) parts.push('Tiers d\'octave uniquement (pas de niveau global dans ce fichier)');
  box.innerHTML = parts.join('<br>');
}

function showPanels(withModel) {
  for (const sec of ['exc', 'metric', 'color', 'balls', 'interp', 'runs', 'disp']) {
    const el = document.querySelector(`[data-sec="${sec}"]`);
    if (el) el.hidden = !withModel;
  }
}

/* ============================== CONSTRUCTION UI ============================== */

function buildExcChips() {
  const box = $('excChips');
  box.innerHTML = '';
  for (const e of state.model.excitations) {
    const b = document.createElement('button');
    b.className = 'chip' + (state.excSel.has(e.key) ? ' is-on' : '');
    b.innerHTML = `<span class="dot" style="background:${e.color}"></span>${e.label}`;
    b.onclick = () => {
      if (state.excSel.has(e.key)) {
        if (state.excSel.size === 1) { toast('Au moins une excitation doit rester affichée.'); return; }
        state.excSel.delete(e.key);
      } else state.excSel.add(e.key);
      // conserve l'ordre du modèle
      const ordered = state.model.excitations.filter((x) => state.excSel.has(x.key)).map((x) => x.key);
      state.excSel = new Set(ordered);
      state.excFilter.clear();
      buildExcChips();
      rebuildViews(false);
      refreshAll();
      applyInterp(true);
      updateDetail();
    };
    box.appendChild(b);
  }
  $('badgeExc').textContent = `${state.excSel.size}/${state.model.excitations.length}`;
  $('excTitle').textContent = state.model.tests ? 'Test et excitations' : 'Excitations';
}

/** Choix du TEST (format ISO 7849) : reconstruit le modèle du test choisi. */
function buildTestSelect() {
  const tests = state.model.tests || [];
  $('testWrap').hidden = !tests.length;
  const sel = $('selTest');
  sel.innerHTML = tests.map((t) => `<option value="${t}"${t === state.test ? ' selected' : ''}>${t.replace(/_/g, ' ')}</option>`).join('');
  sel.onchange = () => {
    state.test = sel.value;
    state.selected = null;
    state.excFilter.clear();
    buildFromJson();
    if (state.cad) { attachCad(); applyCadTransform(); applyCadAppearance(); applyInterp(true); }
    updateDetail();
  };
}

function buildGroupSelect() {
  const groups = state.model.availableGroups;
  const wrap = $('groupWrap');
  wrap.hidden = groups.length < 2;
  const sel = $('selGroup');
  sel.innerHTML = groups.map((g) => `<option value="${g}"${g === state.group ? ' selected' : ''}>${g}</option>`).join('');
  sel.onchange = () => {
    state.group = sel.value;
    buildFromJson();
    if (state.cad) { attachCad(); applyCadTransform(); applyCadAppearance(); }
  };
}

function buildBandSlider() {
  const m = state.model;
  const s = $('bandSlider');
  s.max = Math.max(0, m.nBands - 1);
  s.value = state.band;
  s.disabled = m.nBands === 0;
  const t = $('bandTicks');
  if (m.nBands) {
    const idx = [0, Math.floor((m.nBands - 1) / 2), m.nBands - 1];
    t.innerHTML = idx.map((i) => `<span>${formatFreq(m.freqs[i])}</span>`).join('');
  } else t.innerHTML = '';
  document.querySelector('#segMode [data-mode="band"]').disabled = m.nBands === 0;
  const gBtn = document.querySelector('#segMode [data-mode="global"]');
  gBtn.disabled = !m.hasGlobal;
  gBtn.title = m.hasGlobal ? '' : 'Niveau global absent de ce fichier';
  document.querySelectorAll('#segMode button').forEach((b) => b.classList.toggle('is-on', b.dataset.mode === state.mode));
  $('bandWrap').hidden = state.mode !== 'band';
  updateBandOut();
}

function updateBandOut() {
  const m = state.model;
  $('bandOut').textContent = m && m.nBands ? formatFreq(m.freqs[state.band]) : '—';
}

function buildRunTree() {
  const tree = $('runTree');
  tree.innerHTML = '';
  const flat = state.model.flat;
  tree.classList.toggle('flat', flat);
  $('runsTitle').textContent = flat ? 'Capteurs' : 'Mesures';
  $('runSearch').placeholder = flat ? 'Filtrer les capteurs…' : 'Filtrer les mesures…';
  $('runSearch').value = '';
  $('runsHint').hidden = !flat;
  if (flat) { buildSensorList(tree); return; }
  for (const fam of state.model.families) {
    const famEl = document.createElement('div');
    famEl.className = 'fam' + (state.famOpen.has(fam.key) ? ' open' : '');
    famEl.dataset.fam = fam.key;

    const head = document.createElement('div');
    head.className = 'fam-head';
    head.innerHTML = `<span class="fchev"></span>
      <label class="check"><input type="checkbox"><span></span></label>
      <span class="fam-name">${fam.label}</span>
      <span class="fam-count"></span>`;
    const famChk = head.querySelector('input');
    famChk.onclick = (ev) => {
      ev.stopPropagation();
      const on = famChk.checked;
      for (const r of fam.runs) {
        if (on) state.selRuns.add(r.id); else state.selRuns.delete(r.id);
      }
      syncRunChecks();
      refreshAll();
    };
    head.querySelector('label').onclick = (ev) => ev.stopPropagation();
    head.onclick = () => {
      famEl.classList.toggle('open');
      if (famEl.classList.contains('open')) state.famOpen.add(fam.key); else state.famOpen.delete(fam.key);
    };
    famEl.appendChild(head);

    const body = document.createElement('div');
    body.className = 'fam-body';
    for (const r of fam.runs) {
      const lab = document.createElement('label');
      lab.className = 'run check';
      lab.title = Object.values(r.fullNames).join('\n');
      lab.dataset.run = r.id;
      const noCoord = r.nCoords === 0;
      lab.innerHTML = `<input type="checkbox"><span></span>
        <span class="rn">${r.label}</span>
        ${noCoord ? '<span class="nocoord" title="Aucune coordonnée capteur">∅</span>'
          : (r.nCoords < r.nSensors ? `<span class="nocoord" title="Coordonnées partielles">${r.nCoords}/${r.nSensors}</span>` : '')}`;
      const chk = lab.querySelector('input');
      chk.onchange = () => {
        if (chk.checked) state.selRuns.add(r.id); else state.selRuns.delete(r.id);
        syncRunChecks();
        refreshAll();
      };
      body.appendChild(lab);
    }
    famEl.appendChild(body);
    tree.appendChild(famEl);
  }
  syncRunChecks();
}

/** Liste plate des capteurs à nom unique (DataMesure 2, ISO 7849), sans familles. */
function buildSensorList(tree) {
  for (const r of state.model.runList) {
    const lab = document.createElement('label');
    lab.className = 'run check';
    lab.dataset.run = r.id;
    const origin = [...new Set(Object.values(r.fullNames))];
    lab.title = `${r.label}\n${origin.join('\n')}`;
    lab.innerHTML = `<input type="checkbox"><span></span>
      <span class="rn">${r.label}</span>
      ${r.nCoords === 0 ? '<span class="nocoord" title="Aucune coordonnée capteur">∅</span>'
        : (state.model.tests ? '' : `<span class="ro">${r.famLabel}</span>`)}`;
    const chk = lab.querySelector('input');
    chk.onchange = () => {
      if (chk.checked) state.selRuns.add(r.id); else state.selRuns.delete(r.id);
      syncRunChecks();
      refreshAll();
      highlightSensor(r.id);       // les indices des billes ont changé
    };
    lab.onmouseenter = () => highlightSensor(r.id);
    lab.onmouseleave = () => highlightSensor(null);
    tree.appendChild(lab);
  }
  syncRunChecks();
}

/** Met en évidence un capteur dans toutes les vues (bille + étiquette). */
function highlightSensor(runId) {
  for (const v of views.values()) {
    const i = runId ? v.scene.records.findIndex((rec) => rec.run.id === runId) : -1;
    const shown = i >= 0 && (!v.scene.scaleArr || v.scene.scaleArr[i] > 0);
    v.scene.showHover(shown ? v.scene.records[i] : null, i);
    v.scene.setLabelHot(shown ? i : -1);
  }
}

function syncRunChecks() {
  if (state.model.flat) {
    for (const lab of $('runTree').querySelectorAll('.run')) {
      lab.querySelector('input').checked = state.selRuns.has(lab.dataset.run);
    }
    $('badgeRuns').textContent = `${state.selRuns.size}/${state.model.runList.length}`;
    return;
  }
  for (const fam of state.model.families) {
    const famEl = $('runTree').querySelector(`.fam[data-fam="${cssEsc(fam.key)}"]`);
    if (!famEl) continue;
    let n = 0;
    for (const r of fam.runs) {
      const lab = famEl.querySelector(`.run[data-run="${cssEsc(r.id)}"]`);
      const on = state.selRuns.has(r.id);
      if (lab) lab.querySelector('input').checked = on;
      if (on) n++;
    }
    const chk = famEl.querySelector('.fam-head input');
    chk.checked = n === fam.runs.length && n > 0;
    chk.indeterminate = n > 0 && n < fam.runs.length;
    famEl.querySelector('.fam-count').textContent = `${n}/${fam.runs.length}`;
  }
  $('badgeRuns').textContent = `${state.selRuns.size}/${state.model.runList.length}`;
}

const cssEsc = (s) => (window.CSS && CSS.escape ? CSS.escape(s) : String(s).replace(/["\\]/g, '\\$&'));

function buildPartList() {
  const box = $('partList');
  box.innerHTML = '';
  if (!state.cad) return;
  for (const p of state.cad.parts) {
    const el = document.createElement('label');
    el.className = 'part check';
    el.innerHTML = `<input type="checkbox" checked><span></span>
      <span class="sw" style="background:${p.color}"></span>
      <span class="nm" title="${p.name}">${p.name}</span>`;
    const chk = el.querySelector('input');
    chk.onchange = () => {
      if (chk.checked) state.hiddenParts.delete(p.name); else state.hiddenParts.add(p.name);
      for (const v of views.values()) v.scene.setCadVisibility(state.hiddenParts);
      scheduleInterp();          // les pièces réaffichées doivent être colorées
    };
    box.appendChild(el);
  }
}

/* ============================== VUES ============================== */

function viewKeys() {
  if (state.model && state.excSel.size) {
    return state.model.excitations.filter((e) => state.excSel.has(e.key));
  }
  return [{ key: '__cad__', label: 'CAO', color: '#00a3d7' }];
}

function rebuildViews(resetCam) {
  const keys = viewKeys();
  const cam = views.size ? [...views.values()][0].scene.getCameraState() : null;

  for (const v of views.values()) { v.scene.dispose(); v.el.remove(); }
  views.clear();

  const host = $('views');
  host.innerHTML = '';
  const bg = getComputedStyle(document.body).getPropertyValue('--scene').trim() || '#0b1725';

  for (const k of keys) {
    const el = document.createElement('section');
    el.className = 'view';
    el.innerHTML = `<div class="view-head">
        <span class="vh-dot" style="background:${k.color};color:${k.color}"></span>
        <span class="vh-name">${k.label}</span>
        <span class="vh-meta"></span>
      </div><div class="view-canvas"></div>`;
    host.appendChild(el);

    const scene = new Scene3D(el.querySelector('.view-canvas'), { bg: new THREE.Color(bg).getHex() });
    scene.setProjection(state.persp);
    scene.onCameraChange = onCameraChange;
    const v = { ...k, el, scene, meta: el.querySelector('.vh-meta') };
    views.set(k.key, v);
    bindPointer(v);
  }

  if (state.cad) attachCad();
  applyCadTransform();
  applyCadAppearance();
  applyHelpers();

  if (cam && !resetCam) for (const v of views.values()) v.scene.setCameraState(cam);
  else setTimeout(() => fitAll(), 30);
}

function onCameraChange(src) {
  if (!state.sync || syncing) return;
  syncing = true;
  const st = src.getCameraState();
  for (const v of views.values()) if (v.scene !== src) v.scene.setCameraState(st);
  syncing = false;
}

function attachCad() {
  for (const v of views.values()) {
    v.scene.setCad(state.cad ? state.cad.group.clone() : null);
    v.scene.setCadVisibility(state.hiddenParts);
    if (state.cad) setCadEdgesVisible(v.scene.cadGroup, state.cadEdges);
  }
}

function fitAll() {
  for (const v of views.values()) v.scene.fit();
}

/* ============================== INTERACTIONS 3D ============================== */

function bindPointer(v) {
  const el = v.scene.renderer.domElement;
  let down = null, pending = null;

  el.addEventListener('pointermove', (ev) => {
    if (!state.inspect) return;
    pending = ev;
    if (pending._q) return;
    pending._q = true;
    requestAnimationFrame(() => {
      const e = pending; pending = null;
      if (!e) return;
      const idx = v.scene.pick(e.clientX, e.clientY);
      const rec = idx >= 0 ? v.scene.records[idx] : null;
      v.scene.showHover(rec, idx);
      v.scene.setLabelHot(rec ? idx : -1);
      if (rec) showTip(e.clientX, e.clientY, rec, v);
      else $('tip').hidden = true;
      el.style.cursor = rec ? 'pointer' : '';
    });
  });

  el.addEventListener('pointerleave', () => {
    v.scene.showHover(null);
    v.scene.setLabelHot(-1);
    $('tip').hidden = true;
  });

  el.addEventListener('pointerdown', (ev) => { down = { x: ev.clientX, y: ev.clientY, t: Date.now() }; });
  el.addEventListener('pointerup', (ev) => {
    if (!down) return;
    const moved = Math.hypot(ev.clientX - down.x, ev.clientY - down.y);
    const quick = Date.now() - down.t < 400;
    down = null;
    if (moved > 5 || !quick || ev.button !== 0) return;
    const idx = v.scene.pick(ev.clientX, ev.clientY);
    if (idx >= 0) selectRecord(v.scene.records[idx], idx, v.key);
    else selectRecord(null);
  });
}

function showTip(x, y, rec, v) {
  const tip = $('tip');
  const unit = state.model.unit;
  tip.innerHTML = `<div><b>${rec.name}</b> · ${fmt(rec.value, 1)} ${unit}</div>
    <div class="t-run">${rec.runName}</div>
    <div class="t-run">${v.label}${state.model.flat ? '' : ` · ${rec.run.famLabel}`} · ${metricShort()}</div>`;
  tip.hidden = false;
  const r = tip.getBoundingClientRect();
  tip.style.left = clamp(x + 14, 6, window.innerWidth - r.width - 6) + 'px';
  tip.style.top = clamp(y + 14, 6, window.innerHeight - r.height - 6) + 'px';
}

function selectRecord(rec, idx = -1, excKey = null) {
  state.selected = rec ? { rec, idx, excKey } : null;
  for (const v of views.values()) {
    if (!rec) { v.scene.showSelection(null); continue; }
    // marque le même capteur / même mesure dans toutes les vues
    const i = v.scene.records.findIndex((r) => r.run.id === rec.run.id && r.si === rec.si);
    v.scene.showSelection(i >= 0 ? v.scene.records[i] : null, i);
    v.scene.setLabelSelected(i);
  }
  if (!rec) for (const v of views.values()) v.scene.setLabelSelected(-1);
  markSelectedRow(rec);
  updateDetail();
}

/** Surligne (et fait défiler jusqu'à) la ligne du capteur sélectionné dans la liste. */
function markSelectedRow(rec) {
  const tree = $('runTree');
  const prev = tree.querySelector('.run.is-sel');
  const id = rec && state.model?.flat ? rec.run.id : null;
  if (prev && prev.dataset.run === id) return;
  if (prev) prev.classList.remove('is-sel');
  if (!id) return;
  const row = tree.querySelector(`.run[data-run="${cssEsc(id)}"]`);
  if (row) { row.classList.add('is-sel'); row.scrollIntoView({ block: 'nearest' }); }
}

/* ============================== DÉTAIL CAPTEUR ============================== */

function updateDetail() {
  const d = $('detail');
  const sel = state.selected;
  if (!sel || !state.model) { d.hidden = true; return; }
  const { rec } = sel;
  d.hidden = false;
  $('dSensor').textContent = `${rec.name} — ${state.model.group}`;
  $('dRun').textContent = rec.runName;
  $('dFamLbl').textContent = state.model.famTitle;
  $('dFam').textContent = rec.run.famLabel;
  $('dPos').textContent = `${fmt(rec.pos[0], 1)} ; ${fmt(rec.pos[1], 1)} ; ${fmt(rec.pos[2], 1)}`;
  $('dMetric').textContent = metricShort();

  const cm = colormap(state.cmap);
  const shown = state.model.excitations.filter((e) => state.excSel.has(e.key));
  const rows = [];
  for (const e of shown) {
    const v = sensorValue(rec.run, e.key, rec.si, state.mode, state.band);
    const t = (v - state.vmin) / (state.vmax - state.vmin || 1);
    rows.push(`<div class="d-val" title="Couleur de la bille dans la vue ${e.label}">
      <span class="sw" style="background:${Number.isFinite(v) ? cssColor(cm(t)) : 'transparent'}"></span>
      <span class="nm">${e.label}</span><b>${fmt(v, 1)} ${state.model.unit}</b></div>`);
  }
  $('dVals').innerHTML = rows.join('');
  $('dSpecUnit').textContent = state.model.unit;

  /* légende du graphe : cliquable pour filtrer les courbes */
  const leg = shown.map((e) => {
    const off = state.excFilter.has(e.key);
    const v = sensorValue(rec.run, e.key, rec.si, state.mode, state.band);
    return `<span class="lg${off ? ' off' : ''}" data-exc="${e.key}" style="color:${e.color}"
      title="${off ? 'Afficher' : 'Masquer'} la courbe ${e.label}"><i></i>${e.label}
      <span class="v">${fmt(v, 1)}</span></span>`;
  });
  if (shown.length > 1) leg.push('<span class="lg-hint">cliquez pour filtrer</span>');
  const legBox = $('dLegend');
  legBox.innerHTML = leg.join('');
  legBox.querySelectorAll('.lg[data-exc]').forEach((el) => {
    el.onclick = () => {
      const k = el.dataset.exc;
      if (state.excFilter.has(k)) state.excFilter.delete(k);
      else if (visibleCurves().length > 1) state.excFilter.add(k);
      else { toast('Au moins une courbe doit rester visible.'); return; }
      updateDetail();
    };
  });

  drawSpectrum(rec);
}

/** Excitations affichées dans le graphe (sélection moins filtre de légende). */
function visibleCurves() {
  return state.model.excitations.filter((e) => state.excSel.has(e.key) && !state.excFilter.has(e.key));
}

function drawSpectrum(rec) {
  const cv = $('dSpec');
  const m = state.model;
  const dpr = Math.min(window.devicePixelRatio, 2);
  const w = cv.clientWidth || 300;
  const h = Math.max(cv.clientHeight || 130, 90);
  cv.width = w * dpr; cv.height = h * dpr;
  const ctx = cv.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  if (!m.nBands) return;

  const cs = getComputedStyle(document.body);
  const cLine = cs.getPropertyValue('--line-2').trim();
  const cTxt = cs.getPropertyValue('--txt-3').trim();

  const curves = [];
  for (const e of visibleCurves()) {
    const sp = sensorSpectrum(rec.run, e.key, rec.si);
    if (sp) curves.push({ e, sp });
  }
  if (!curves.length) return;

  let mn = Infinity, mx = -Infinity;
  for (const c of curves) for (const v of c.sp) if (Number.isFinite(v)) { mn = Math.min(mn, v); mx = Math.max(mx, v); }
  if (!isFinite(mn)) return;
  const pad = Math.max((mx - mn) * 0.12, 2);
  mn = Math.floor((mn - pad) / 5) * 5; mx = Math.ceil((mx + pad) / 5) * 5;

  const L = 30, R = 4, T = 6, B = 16;
  const px = (i) => L + (i / (m.nBands - 1)) * (w - L - R);
  const py = (v) => T + (1 - (v - mn) / (mx - mn)) * (h - T - B);

  // grille + axes
  ctx.strokeStyle = cLine; ctx.globalAlpha = 0.5; ctx.lineWidth = 1;
  ctx.font = '9px "Segoe UI", sans-serif'; ctx.fillStyle = cTxt;
  const nY = 4;
  for (let i = 0; i <= nY; i++) {
    const v = mn + (i / nY) * (mx - mn);
    const y = Math.round(py(v)) + 0.5;
    ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(w - R, y); ctx.stroke();
    ctx.globalAlpha = 1; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    ctx.fillText(Math.round(v), L - 4, y); ctx.globalAlpha = 0.5;
  }
  ctx.globalAlpha = 1;
  ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  const tickIdx = [0, Math.floor((m.nBands - 1) / 3), Math.floor(2 * (m.nBands - 1) / 3), m.nBands - 1];
  for (const i of tickIdx) ctx.fillText(formatFreq(m.freqs[i]), clamp(px(i), 16, w - 16), h - B + 3);

  // bande courante
  if (state.mode === 'band') {
    const x = Math.round(px(state.band)) + 0.5;
    ctx.strokeStyle = cs.getPropertyValue('--accent').trim();
    ctx.globalAlpha = 0.35; ctx.lineWidth = 6;
    ctx.beginPath(); ctx.moveTo(x, T); ctx.lineTo(x, h - B); ctx.stroke();
    ctx.globalAlpha = 1; ctx.lineWidth = 1;
  }

  // courbes
  for (const c of curves) {
    ctx.strokeStyle = c.e.color; ctx.lineWidth = 1.8;
    ctx.beginPath();
    let started = false;
    c.sp.forEach((v, i) => {
      if (!Number.isFinite(v)) { started = false; return; }
      const x = px(i), y = py(v);
      if (started) ctx.lineTo(x, y); else { ctx.moveTo(x, y); started = true; }
    });
    ctx.stroke();
    if (state.mode === 'band' && Number.isFinite(c.sp[state.band])) {
      ctx.fillStyle = c.e.color;
      ctx.beginPath(); ctx.arc(px(state.band), py(c.sp[state.band]), 3, 0, 7); ctx.fill();
    }
  }

  /* légende intégrée au graphe (le rend autonome une fois agrandi ou exporté) */
  const big = state.detailBig;
  ctx.font = `${big ? 12 : 10}px "Segoe UI", sans-serif`;
  const items = curves.map((c) => ({ t: c.e.label, col: c.e.color }));
  const lh = big ? 16 : 13;
  const bw = Math.max(...items.map((i) => ctx.measureText(i.t).width)) + 26;
  const bx = w - R - bw - 4, by = T + 3;
  ctx.fillStyle = cs.getPropertyValue('--panel').trim();
  ctx.globalAlpha = 0.82;
  ctx.fillRect(bx, by, bw, items.length * lh + 6);
  ctx.globalAlpha = 1;
  ctx.strokeStyle = cLine;
  ctx.strokeRect(bx + 0.5, by + 0.5, bw, items.length * lh + 6);
  ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
  items.forEach((it, i) => {
    const y = by + 3 + lh * (i + 0.5);
    ctx.strokeStyle = it.col; ctx.lineWidth = 2.4;
    ctx.beginPath(); ctx.moveTo(bx + 6, y); ctx.lineTo(bx + 18, y); ctx.stroke();
    ctx.fillStyle = cs.getPropertyValue('--txt').trim();
    ctx.fillText(it.t, bx + 22, y);
  });

  if (big) {
    ctx.fillStyle = cTxt; ctx.font = '11px "Segoe UI", sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
    ctx.fillText('Fréquence centrale de tiers d\'octave', (L + w - R) / 2, h - 1);
    ctx.save();
    ctx.translate(9, (T + h - B) / 2); ctx.rotate(-Math.PI / 2);
    ctx.textBaseline = 'top';
    ctx.fillText(`Niveau (${m.unit})`, 0, 0);
    ctx.restore();
  }
}

/* ============================== RAFRAÎCHISSEMENT ============================== */

function metricShort() {
  if (!state.model) return '—';
  return state.mode === 'band'
    ? `Tiers d'octave ${formatFreq(state.model.freqs[state.band])}`
    : 'Niveau global';
}

function radiusFromT(t) {
  const rmin = sceneSize * 0.002, rmax = sceneSize * 0.08;
  return rmin * Math.pow(rmax / rmin, clamp(t, 0, 1));
}

/** Recalcul complet : billes, couleurs, échelle, colorbar, compteurs. */
function refreshAll() {
  if (!state.model) return;
  const m = state.model;
  const runIds = [...state.selRuns];
  const excKeys = [...state.excSel];

  if (state.autoScale) {
    const rg = valueRange(m, runIds, excKeys, state.mode, state.band);
    if (rg) {
      state.vmin = Math.floor(rg[0] * 2) / 2;
      state.vmax = Math.ceil(rg[1] * 2) / 2;
    }
  }
  $('inMin').value = fmtNum(state.vmin);
  $('inMax').value = fmtNum(state.vmax);

  const cm = colormap(state.cmap);
  const span = (state.vmax - state.vmin) || 1;

  for (const v of views.values()) {
    if (v.key === '__cad__') { v.meta.textContent = state.cad ? `${state.cad.parts.length} pièce(s)` : ''; continue; }
    const recs = buildRecords(m, runIds, v.key, state.mode, state.band);
    const n = recs.length;
    const colors = new Float32Array(n * 3);
    const scales = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const t = (recs[i].value - state.vmin) / span;
      const tc = clamp(t, 0, 1);
      const c = cm(tc);
      colors[i * 3] = c[0]; colors[i * 3 + 1] = c[1]; colors[i * 3 + 2] = c[2];
      let k = state.scaleByLevel ? 0.4 + 1.0 * tc : 1;
      if (!state.clampOut && (t < 0 || t > 1)) k = 0;
      scales[i] = k;
    }
    v.scene.setPoints(recs, colors, state.radius, scales, state.ballOpacity);
    v.scene.setLabels(m.flat
      ? recs.map((r, i) => ({ idx: i, text: r.name, pos: r.pos })).filter((it) => scales[it.idx] > 0)
      : null, state.labels);
    const nRuns = new Set(recs.map((r) => r.run.id)).size;
    v.meta.textContent = `${nRuns} mesure(s) · ${n} bille(s)`;
  }

  // marqueur de sélection à repositionner (les billes ont été reconstruites)
  if (state.selected) selectRecord(state.selected.rec, state.selected.idx, state.selected.excKey);

  $('mrValue').textContent = `${metricShort()} · ${fmt(state.vmin, 1)} → ${fmt(state.vmax, 1)} ${m.unit}`;
  $('outRadius').textContent = `${fmt(state.radius, 1)} mm`;
  updateColorbar();
  scheduleInterp();          // le champ dépend des mêmes valeurs que les billes
}

const fmtNum = (v) => (Number.isFinite(v) ? Math.round(v * 100) / 100 : '');

function updateColorbar() {
  if (!state.model) return;
  paintGradient($('cbCanvas'), state.cmap, true);
  $('cbMax').textContent = fmt(state.vmax, 1);
  $('cbMin').textContent = fmt(state.vmin, 1);
  $('cbUnit').textContent = state.model.unit;
  paintGradient($('cmapPreview'), state.cmap, false);
}

function applyHelpers() {
  for (const v of views.values()) {
    v.scene.setFloorZ(sensorBox ? Math.min(sensorBox.min.z, 0) : 0);
    v.scene.setHelpers({
      grid: state.showGrid, axes: state.showAxes, box: state.showBox,
      sensorBox, size: sceneSize,
    });
  }
}

/* ============================== CAO : TRANSFORMATION / ASPECT ============================== */

function cadCenter() {
  if (!state.cad) return new THREE.Vector3();
  return state.cad.bbox.getCenter(new THREE.Vector3());
}

function applyCadTransform() {
  const tr = {
    scale: state.cadScale, t: state.cadT, r: state.cadR,
    pivotCenter: state.cadPivot, center: cadCenter(),
  };
  for (const v of views.values()) v.scene.setCadTransform(tr);

  $('outScale').textContent = state.cadScale.toFixed(3).replace('.', ',');
  $('inScale').value = Math.round(state.cadScale * 1e6) / 1e6;
  $('rngScale').value = Math.log10(state.cadScale);
  AXES.forEach((ax, i) => {
    $('inT' + ax).value = Math.round(state.cadT[i] * 100) / 100;
    $('rngT' + ax).value = state.cadT[i];
    $('inR' + ax).value = Math.round(state.cadR[i] * 10) / 10;
    $('rngR' + ax).value = state.cadR[i];
  });
}

const AXES = ['x', 'y', 'z'];

function applyCadAppearance() {
  $('outOpacity').textContent = `${Math.round(state.cadOpacity * 100)} %`;
  if (!state.cad) return;
  const neutral = new THREE.Color(state.theme === 'light' ? 0x8fa4ba : 0x9fb3c8);
  for (const p of state.cad.parts) {
    for (const mat of p.materials) {
      mat.opacity = state.cadOpacity;
      mat.transparent = state.cadOpacity < 1;
      mat.depthWrite = state.cadOpacity >= 1;
      mat.color.copy(state.cadFlat ? neutral : new THREE.Color(mat.userData.baseColor));
      mat.needsUpdate = true;
    }
  }
  for (const v of views.values()) {
    if (v.scene.cadGroup) setCadEdgesVisible(v.scene.cadGroup, state.cadEdges);
    v.scene.dirty = true;
  }
}

function setupRangeBounds() {
  const lim = Math.max(Math.round(sceneSize * 2), 100);
  const step = Math.max(Math.round(sceneSize / 500), 1);
  for (const ax of AXES) {
    const r = $('rngT' + ax);
    r.min = -lim; r.max = lim; r.step = step;
    $('inT' + ax).step = step;
  }
  $('rngRadius').value = Math.round(state.radiusT * 100);
}

/* ====================== INTERPOLATION DE SURFACE (RBF) ====================== */

/** Bornes des curseurs ε et distance d'influence, déduites de la taille du modèle. */
function setupInterpBounds() {
  const I = state.interp;
  if (I.epsAuto || !I.eps) I.eps = autoEps();
  if (!I.dmax) I.dmax = Math.max(sceneSize * 0.06, 1);
  if (!I.meshStep) I.meshStep = autoMeshStep();
  const r = $('rngDmax');
  r.min = Math.max(sceneSize * 0.005, 0.5);
  r.max = Math.max(sceneSize * 0.35, 2);
  r.step = (r.max - r.min) / 200;
  pushInterpControls();
}

/**
 * Pas de maillage par défaut : ε/3, soit trois échantillons par portée de noyau.
 * Les bornes sont liées à ε — descendre sous ε/6 n'ajoute aucune information
 * sur le champ et sature inutilement le budget de triangles.
 */
function autoMeshStep() {
  return clamp(state.interp.eps / 2.5, MESH_MIN(), MESH_MAX());
}
const MESH_MIN = () => Math.max(state.interp.eps / 6, sceneSize * 0.004, 0.4);
const MESH_MAX = () => Math.max(state.interp.eps * 1.5, MESH_MIN() * 4);
/** Replace le pas dans les bornes après un changement de ε. */
function clampMeshStep() {
  state.interp.meshStep = clamp(state.interp.meshStep || autoMeshStep(), MESH_MIN(), MESH_MAX());
}
const meshFromT = (t) => MESH_MIN() * Math.pow(MESH_MAX() / MESH_MIN(), clamp(t, 0, 1));
const tFromMesh = (v) => Math.log(clamp(v, MESH_MIN(), MESH_MAX()) / MESH_MIN()) / Math.log(MESH_MAX() / MESH_MIN());

const EPS_MIN = () => Math.max(sceneSize * 0.004, 0.2);
const EPS_MAX = () => Math.max(sceneSize * 0.6, 5);
const epsFromT = (t) => EPS_MIN() * Math.pow(EPS_MAX() / EPS_MIN(), clamp(t, 0, 1));
const tFromEps = (e) => Math.log(clamp(e, EPS_MIN(), EPS_MAX()) / EPS_MIN()) / Math.log(EPS_MAX() / EPS_MIN());

/** ε « automatique » : distance moyenne entre capteurs voisins × 1,6. */
function autoEps() {
  const pts = allSensorPoints();
  if (!pts || pts.length < 6) return Math.max(sceneSize * 0.05, 1);
  return Math.max(meanNearestDistance(pts) * 1.6, sceneSize * 0.005);
}

function allSensorPoints() {
  if (!state.model) return null;
  const out = [];
  for (const id of state.selRuns) {
    const run = state.model.runById.get(id);
    if (!run) continue;
    for (const p of run.coords) if (p) out.push(p[0], p[1], p[2]);
  }
  return Float64Array.from(out);
}

function themeNeutral() {
  return state.theme === 'light' ? [0.80, 0.83, 0.87] : [0.15, 0.19, 0.24];
}

/** Affiche / masque la carte et met à jour les libellés. */
function updateInterpUI() {
  const I = state.interp;
  const noCad = !state.cad;
  $('interpNoCad').hidden = !noCad;
  $('interpOpts').classList.toggle('off', !I.on || noCad);
  $('chkInterp').disabled = noCad;
  $('badgeInterp').textContent = I.on && !noCad ? 'actif' : 'off';
  $('outEps').textContent = `${fmt(I.eps, 1)} mm`;
  $('outLambda').textContent = I.lambda > 0 ? I.lambda.toExponential(0).replace('e', 'e') : '0';
  $('outDmax').textContent = `${fmt(I.dmax, 0)} mm`;
  $('outFieldOpacity').textContent = `${Math.round(I.opacity * 100)} %`;
  const sc0 = views.size ? [...views.values()][0].scene : null;
  const tris = sc0 ? sc0.fieldTris : 0;
  $('outMesh').textContent = `${fmt(I.meshStep, 1)} mm` + (tris ? ` · ${tris.toLocaleString('fr-FR')} tri.` : '');
}

function pushInterpControls() {
  const I = state.interp;
  $('chkInterp').checked = I.on;
  $('selKernel').value = I.kernel;
  $('selPoly').value = I.poly;
  $('rngEps').value = Math.round(tFromEps(I.eps) * 100);
  $('inEps').value = Math.round(I.eps * 10) / 10;
  $('rngLambda').value = I.lambda > 0 ? clamp(Math.log10(I.lambda), -8, 0) : -8;
  $('chkMask').checked = I.mask;
  $('rngDmax').value = I.dmax;
  $('rngFieldOpacity').value = Math.round(I.opacity * 100);
  $('rngMesh').value = Math.round(tFromMesh(I.meshStep) * 100);
  $('chkFieldUnlit').checked = I.unlit;
  $('inMaxPts').value = I.maxPts;
  $('chkInterpLive').checked = I.live;
  document.querySelectorAll('#segField button').forEach((b) => b.classList.toggle('is-on', b.dataset.f === I.display));
  updateInterpUI();
}

/** Active/désactive le mode champ dans les vues puis (re)calcule si demandé. */
function applyInterp(recompute = true) {
  const I = state.interp;
  const on = I.on && !!state.cad && !!state.model;
  const unlitPoints = on && I.unlit;      // comparabilité bille / surface
  let matChanged = false;
  for (const v of views.values()) {
    v.scene.setFieldEnabled(on, I.opacity, I.meshStep, I.unlit);
    v.scene.setPointsVisible(!on || I.display === 'both');
    if (!!v.scene._pointsUnlit !== unlitPoints) { v.scene.setPointsUnlit(unlitPoints); matChanged = true; }
  }
  if (matChanged) refreshAll();           // reconstruit les billes avec le bon matériau
  if (!on) { $('interpStat').innerHTML = ''; updateInterpUI(); return; }
  applyCadAppearance();          // les arêtes restent gérées par ce chemin
  if (recompute) runInterp();
  updateInterpUI();
}

function scheduleInterp() {
  if (!state.interp.on || !state.interp.live) return;
  clearTimeout(interpTimer);
  interpTimer = setTimeout(() => runInterp(), 220);
}

/** Surface uniformément neutre : aucun champ exploitable pour cette vue. */
function paintNeutral(v, neutral) {
  v.scene.paintField((x, y, z, out) => {
    out[0] = neutral[0]; out[1] = neutral[1]; out[2] = neutral[2];
  });
}

/** Résout puis peint le champ, une fois par vue (une excitation par vue). */
function runInterp() {
  const I = state.interp;
  if (!I.on || !state.cad || !state.model || !views.size) return;
  const t0 = performance.now();
  const cm = colormap(state.cmap);
  const span = (state.vmax - state.vmin) || 1;
  const neutral = themeNeutral();
  const rows = [];

  for (const v of views.values()) {
    /* Seules les billes réellement affichées alimentent l'interpolation : une
       bille masquée (valeur hors bornes quand l'écrêtage est désactivé) est
       exclue du solveur, sinon le champ resterait piloté par une donnée que
       l'utilisateur a délibérément écartée. Les mesures décochées sont déjà
       absentes de `records`. */
    const all = v.scene.records;
    const sarr = v.scene.scaleArr;
    const recs = sarr ? all.filter((r, i) => sarr[i] > 0) : all;
    const hidden = all.length - recs.length;
    if (recs.length < 3) {
      rows.push(`<div class="err">${v.label} : ${recs.length} point(s) affiché(s) — 3 minimum.</div>`);
      paintNeutral(v, neutral);       // ne pas laisser un champ périmé à l'écran
      continue;
    }
    const pts = new Float64Array(recs.length * 3);
    const vals = new Float64Array(recs.length);
    for (let i = 0; i < recs.length; i++) {
      pts[i * 3] = recs[i].pos[0]; pts[i * 3 + 1] = recs[i].pos[1]; pts[i * 3 + 2] = recs[i].pos[2];
      vals[i] = recs[i].value;
    }
    const rbf = buildRbf(pts, vals, {
      kernel: I.kernel, eps: I.eps, lambda: I.lambda, poly: I.poly,
      maxPoints: I.maxPts, mergeTol: Math.max(sceneSize * 0.001, 0.2),
    });
    if (!rbf) {
      rows.push(`<div class="err">${v.label} : système mal conditionné — augmentez λ ou changez de noyau.</div>`);
      paintNeutral(v, neutral);
      continue;
    }
    const mask = I.mask, dmax = I.dmax;
    // fidélité : on retient, pour chaque nœud, la valeur du champ au sommet
    // de surface le plus proche → écart réellement visible entre bille et surface
    const bestD = new Float64Array(rbf.n).fill(Infinity);
    const bestV = new Float64Array(rbf.n);
    const nv = v.scene.paintField((x, y, z, out) => {
      const val = rbf.eval(x, y, z);
      const i = rbf.dminIdx;
      if (rbf.dmin < bestD[i]) { bestD[i] = rbf.dmin; bestV[i] = val; }
      if (mask && rbf.dmin > dmax) { out[0] = neutral[0]; out[1] = neutral[1]; out[2] = neutral[2]; return; }
      const c = cm(clamp((val - state.vmin) / span, 0, 1));
      out[0] = c[0]; out[1] = c[1]; out[2] = c[2];
    });
    let fSum = 0, fMax = 0, fN = 0, dSurfMax = 0;
    for (let i = 0; i < rbf.n; i++) {
      if (!isFinite(bestD[i])) continue;
      const d = Math.abs(bestV[i] - rbf.values[i]);
      fSum += d; fMax = Math.max(fMax, d); fN++;
      dSurfMax = Math.max(dSurfMax, bestD[i]);
    }
    rows.push(`<div><b>${v.label}</b> : ${rbf.n} nœuds (${rbf.nInput} billes affichées`
      + `${hidden ? `, <b>${hidden} masquée(s) exclue(s)</b>` : ''}`
      + `${rbf.nInput - rbf.nMerged ? `, ${rbf.nInput - rbf.nMerged} fusionnés` : ''}`
      + `${rbf.dropped ? `, ${rbf.dropped} écartés` : ''}) · ${nv.toLocaleString('fr-FR')} sommets`
      + ` · écart aux nœuds ${fmt(rbf.residualMean, 2)} dB (max ${fmt(rbf.residualMax, 2)})`
      + `<br>fidélité bille ↔ surface : <b>${fmt(fN ? fSum / fN : NaN, 2)} dB</b>`
      + ` (max ${fmt(fMax, 2)}, sur ${fN} nœuds ; capteur le plus éloigné de la surface : ${fmt(dSurfMax, 0)} mm)</div>`);
    if (v.scene.fieldTruncated) {
      rows.push('<div class="err">Maillage plafonné : augmentez le pas de maillage du champ.</div>');
    }
  }
  const sc0 = views.size ? [...views.values()][0].scene : null;
  rows.push(`<div>maillage du champ : ${(sc0?.fieldTris || 0).toLocaleString('fr-FR')} triangles,`
    + ` ${(sc0?.fieldVerts || 0).toLocaleString('fr-FR')} sommets par vue`
    + ` · temps de calcul total <b>${Math.round(performance.now() - t0)} ms</b></div>`);
  $('interpStat').innerHTML = rows.join('');
  updateInterpUI();
}

/* ============================== PROJETS ============================== */

function projectToObject() {
  const cam = views.size ? [...views.values()][0].scene.getCameraState() : null;
  const I = state.interp;
  return {
    app: 'VISUDATA', version: 1, saved: new Date().toISOString(),
    files: { cad: state.files.cad, json: state.files.json },
    data: { group: state.group, exc: [...state.excSel], runs: [...state.selRuns] },
    metric: { mode: state.mode, band: state.band },
    color: {
      cmap: state.cmap, autoScale: state.autoScale,
      vmin: state.vmin, vmax: state.vmax, clampOut: state.clampOut,
    },
    balls: {
      radiusT: state.radiusT, opacity: state.ballOpacity,
      scaleByLevel: state.scaleByLevel, inspect: state.inspect,
    },
    cad: {
      scale: state.cadScale, t: [...state.cadT], r: [...state.cadR], pivot: state.cadPivot,
      opacity: state.cadOpacity, edges: state.cadEdges, flat: state.cadFlat,
      hidden: [...state.hiddenParts],
    },
    interp: { ...I },
    view: {
      grid: state.showGrid, axes: state.showAxes, box: state.showBox,
      persp: state.persp, sync: state.sync, theme: state.theme, camera: cam,
    },
  };
}

async function saveProject() {
  const base = (state.files.json?.name || 'projet').replace(/\.json$/i, '');
  const name = await saveJson(projectToObject(), `${base}.visudata.json`);
  if (name) toast(`Projet enregistré : ${name}`, 'ok');
}

async function openProject() {
  const picked = await pickFile('project');
  if (picked === null) return;                       // annulé
  if (picked === undefined) { $('fileProj').click(); return; }
  try {
    openProjectObject(await readJson(picked.file), picked.file.name);
  } catch (e) {
    toast('Projet illisible : ' + e.message, 'err');
  }
}

function openProjectObject(obj, fname) {
  if (!obj || obj.app !== 'VISUDATA') { toast('Ce fichier n\'est pas un projet VISUDATA.', 'err'); return; }
  if (!state.model) {
    pendingProject = obj;
    const f = obj.files || {};
    $('projBox').hidden = false;
    $('projBox').innerHTML = `<b>Projet « ${fname} » en attente.</b><br>`
      + `Chargez les mesures pour l'appliquer : <b>${f.json?.name || 'fichier JSON'}</b>`
      + (f.cad?.name ? `<br>CAO associée : <b>${f.cad.name}</b>` : '');
    toast('Projet chargé — il reste à ouvrir les fichiers de mesures.');
    return;
  }
  applyProject(obj);
  toast(`Projet « ${fname} » appliqué`, 'ok');
}

function applyProject(o) {
  const m = state.model;
  if (!m) { pendingProject = o; return; }

  // groupe de capteurs : reconstruit tout le modèle si nécessaire
  if (o.data?.group && o.data.group !== state.group && m.availableGroups.includes(o.data.group)) {
    state.group = o.data.group;
    buildFromJson();
  }
  const mm = state.model;

  if (Array.isArray(o.data?.exc)) {
    const keep = o.data.exc.filter((k) => mm.excitations.some((e) => e.key === k));
    if (keep.length) state.excSel = new Set(mm.excitations.filter((e) => keep.includes(e.key)).map((e) => e.key));
  }
  if (Array.isArray(o.data?.runs)) {
    const keep = o.data.runs.filter((id) => mm.runById.has(id));
    // projet issu d'un autre format de fichier : aucun identifiant commun, tout reste coché
    if (keep.length || !o.data.runs.length) state.selRuns = new Set(keep);
  }
  if (o.metric) {
    state.mode = (o.metric.mode === 'band' || !mm.hasGlobal) && mm.nBands ? 'band' : 'global';
    state.band = clamp(o.metric.band | 0, 0, Math.max(0, mm.nBands - 1));
  }
  if (o.color) {
    if (listColormaps().some((c) => c.key === o.color.cmap)) state.cmap = o.color.cmap;
    state.autoScale = !!o.color.autoScale;
    if (Number.isFinite(o.color.vmin)) state.vmin = o.color.vmin;
    if (Number.isFinite(o.color.vmax)) state.vmax = o.color.vmax;
    state.clampOut = o.color.clampOut !== false;
  }
  if (o.balls) {
    if (Number.isFinite(o.balls.radiusT)) { state.radiusT = clamp(o.balls.radiusT, 0, 1); state.radius = radiusFromT(state.radiusT); }
    if (Number.isFinite(o.balls.opacity)) state.ballOpacity = clamp(o.balls.opacity, 0.1, 1);
    state.scaleByLevel = !!o.balls.scaleByLevel;
    state.inspect = o.balls.inspect !== false;
  }
  if (o.cad) {
    if (Number.isFinite(o.cad.scale) && o.cad.scale > 0) state.cadScale = o.cad.scale;
    if (Array.isArray(o.cad.t) && o.cad.t.length === 3) state.cadT = o.cad.t.map(Number);
    if (Array.isArray(o.cad.r) && o.cad.r.length === 3) state.cadR = o.cad.r.map(Number);
    state.cadPivot = !!o.cad.pivot;
    if (Number.isFinite(o.cad.opacity)) state.cadOpacity = clamp(o.cad.opacity, 0, 1);
    state.cadFlat = o.cad.flat !== false;
    state.cadEdges = !!o.cad.edges;
    state.hiddenParts = new Set(Array.isArray(o.cad.hidden) ? o.cad.hidden : []);
  }
  if (o.interp) {
    const I = state.interp;
    for (const k of ['kernel', 'poly', 'display']) if (o.interp[k]) I[k] = o.interp[k];
    for (const k of ['eps', 'lambda', 'dmax', 'opacity', 'maxPts', 'meshStep']) {
      if (Number.isFinite(o.interp[k])) I[k] = o.interp[k];
    }
    I.on = !!o.interp.on; I.mask = o.interp.mask !== false;
    I.live = o.interp.live !== false; I.epsAuto = !!o.interp.epsAuto;
    I.unlit = o.interp.unlit !== false;
    if (!I.meshStep) I.meshStep = autoMeshStep();
    if (!KERNELS[I.kernel]) I.kernel = 'gauss';
    if (!POLY[I.poly]) I.poly = 'const';
  }
  if (o.view) {
    state.showGrid = o.view.grid !== false;
    state.showAxes = o.view.axes !== false;
    state.showBox = !!o.view.box;
    state.persp = o.view.persp !== false;
    state.sync = o.view.sync !== false;
    if (o.view.theme) setTheme(o.view.theme);
  }

  // remise en cohérence de l'interface puis des vues
  buildExcChips();
  buildBandSlider();
  syncRunChecks();
  pushStateToControls();
  rebuildViews(true);
  refreshAll();
  applyCadTransform();
  applyCadAppearance();
  applyHelpers();
  buildPartList();
  applyInterp(true);
  if (o.view?.camera) {
    for (const v of views.values()) v.scene.setCameraState(o.view.camera);
  } else fitAll();
  $('projBox').hidden = true;

  // signale les fichiers attendus s'ils ne correspondent pas
  const f = o.files || {};
  const diff = [];
  if (f.json?.name && state.files.json?.name && f.json.name !== state.files.json.name) diff.push(`mesures : ${f.json.name}`);
  if (f.cad?.name && (!state.files.cad || f.cad.name !== state.files.cad.name)) diff.push(`CAO : ${f.cad.name}`);
  if (diff.length) {
    $('projBox').hidden = false;
    $('projBox').innerHTML = `<b>Fichiers du projet différents de ceux chargés</b><br>` + diff.join('<br>');
  }
}

/** Recopie l'état dans tous les contrôles de l'interface. */
function pushStateToControls() {
  $('selCmap').value = state.cmap;
  $('chkAuto').checked = state.autoScale;
  $('inMin').disabled = $('inMax').disabled = state.autoScale;
  $('chkClamp').checked = state.clampOut;
  $('rngRadius').value = Math.round(state.radiusT * 100);
  $('rngBallOpacity').value = Math.round(state.ballOpacity * 100);
  $('outBallOpacity').textContent = `${Math.round(state.ballOpacity * 100)} %`;
  $('chkScaleByLevel').checked = state.scaleByLevel;
  $('chkInspect').checked = state.inspect;
  $('chkPivot').checked = state.cadPivot;
  $('rngOpacity').value = Math.round(state.cadOpacity * 100);
  $('chkFlat').checked = state.cadFlat;
  $('chkEdges').checked = state.cadEdges;
  $('chkGrid').checked = state.showGrid;
  $('chkAxes').checked = state.showAxes;
  $('chkBox').checked = state.showBox;
  $('chkPersp').checked = state.persp;
  $('btnSync').classList.toggle('is-on', state.sync);
  document.querySelectorAll('#segMode button').forEach((b) => b.classList.toggle('is-on', b.dataset.mode === state.mode));
  $('bandWrap').hidden = state.mode !== 'band';
  $('selGroup').value = state.group;
  pushInterpControls();
}

/** Propose de recharger les fichiers de la session précédente (poignées mémorisées). */
async function initFileHandles() {
  const [hj, hc] = await Promise.all([getHandle('json'), getHandle('cad')]);
  if (!hj && !hc) return;
  const names = [hj?.name, hc?.name].filter(Boolean).join(' + ');
  const btn = $('btnReloadFiles');
  btn.hidden = false;
  btn.title = names;
  btn.onclick = async () => {
    btn.disabled = true;
    try {
      if (hj) { const f = await fileFromHandle(hj); if (f) await loadJson(f, hj); }
      if (hc) { const f = await fileFromHandle(hc); if (f) await loadCad(f, hc); }
      if (!state.model && !state.cad) toast('Accès aux fichiers refusé ou fichiers déplacés.', 'err');
    } finally { btn.disabled = false; }
  };
}

/* ============================== CAPTURE PNG ============================== */

function snapshot() {
  const vs = [...views.values()];
  if (!vs.length) return;
  for (const v of vs) { v.scene.dirty = true; v.scene.update(); }
  const gap = 2;
  const h = Math.max(...vs.map((v) => v.scene.renderer.domElement.height));
  const w = vs.reduce((s, v) => s + v.scene.renderer.domElement.width, 0) + gap * (vs.length - 1);
  const cv = document.createElement('canvas');
  cv.width = w; cv.height = h + 46;
  const ctx = cv.getContext('2d');
  const cs = getComputedStyle(document.body);
  ctx.fillStyle = cs.getPropertyValue('--panel').trim(); ctx.fillRect(0, 0, w, h + 46);

  let x = 0;
  for (const v of vs) {
    const c = v.scene.renderer.domElement;
    ctx.drawImage(c, x, 46);
    drawSnapshotLabels(ctx, v.scene, x, 46, cs);
    ctx.fillStyle = v.color;
    ctx.fillRect(x, 46, c.width, 3);
    ctx.fillStyle = cs.getPropertyValue('--txt').trim();
    ctx.font = 'bold 20px "Segoe UI", sans-serif'; ctx.textBaseline = 'middle';
    ctx.fillText(v.label, x + 16, 24);
    x += c.width + gap;
  }
  ctx.fillStyle = cs.getPropertyValue('--txt-2').trim();
  ctx.font = '14px "Segoe UI", sans-serif'; ctx.textAlign = 'right';
  ctx.fillText(`${metricShort()} — échelle ${fmt(state.vmin, 1)} → ${fmt(state.vmax, 1)} ${state.model?.unit || ''}`, w - 16, 24);

  const a = document.createElement('a');
  const tag = state.model && state.mode === 'band'
    ? Math.round(state.model.freqs[state.band]) + 'Hz' : 'global';
  a.download = `VISUDATA_${tag}.png`;
  a.href = cv.toDataURL('image/png');
  a.click();
  toast('Image exportée', 'ok');
}

/** Reporte les étiquettes HTML de la vue sur l'image exportée. */
function drawSnapshotLabels(ctx, scene, ox, oy, cs) {
  const tags = scene.labelSnapshot();
  if (!tags.length) return;
  const dpr = scene.renderer.getPixelRatio();
  ctx.save();
  ctx.font = `600 ${Math.round(10 * dpr)}px "Segoe UI", sans-serif`;
  ctx.textBaseline = 'middle'; ctx.textAlign = 'left';
  const accent = cs.getPropertyValue('--accent').trim();
  for (const t of tags) {
    const w = ctx.measureText(t.text).width + 10 * dpr, h = 15 * dpr;
    const bx = ox + t.x + 7 * dpr, by = oy + t.y - 7 * dpr - h;
    ctx.globalAlpha = 0.85;
    ctx.fillStyle = t.hot ? accent : cs.getPropertyValue('--panel').trim();
    ctx.fillRect(bx, by, w, h);
    ctx.globalAlpha = 1;
    ctx.fillStyle = t.hot ? '#fff' : cs.getPropertyValue('--txt').trim();
    ctx.fillText(t.text, bx + 5 * dpr, by + h / 2);
  }
  ctx.restore();
}

/* ============================== BOUCLE DE RENDU ============================== */

function loop() {
  for (const v of views.values()) v.scene.update();
  requestAnimationFrame(loop);
}

/* ============================== BRANCHEMENT DE L'INTERFACE ============================== */

function bindUI() {
  /* --- sections repliables --- */
  document.querySelectorAll('.card-head').forEach((h) => {
    h.onclick = () => h.parentElement.classList.toggle('open');
  });

  /* --- fichiers --- */
  $('fileCad').onchange = (e) => { if (e.target.files[0]) loadCad(e.target.files[0]); e.target.value = ''; };
  $('fileJson').onchange = (e) => { if (e.target.files[0]) handleFile(e.target.files[0]); e.target.value = ''; };
  $('fileProj').onchange = async (e) => {
    const f = e.target.files[0]; e.target.value = '';
    if (f) { try { openProjectObject(await readJson(f), f.name); } catch (err) { toast('Projet illisible : ' + err.message, 'err'); } }
  };

  /* Sélecteur natif quand l'API File System Access est disponible : il fournit
     une poignée persistante, donc le rechargement en un clic à la session suivante. */
  if (fsaAvailable) {
    const hook = (dropId, kind, loader) => {
      $(dropId).addEventListener('click', async (e) => {
        e.preventDefault();
        const r = await pickFile(kind);
        if (r) loader(r.file, r.handle);
      });
    };
    hook('dropCad', 'cad', (f, h) => loadCad(f, h));
    hook('dropJson', 'json', (f, h) => handleFile(f, h));
  }

  /* Voile de dépôt : piloté par une temporisation et non par un compteur
     dragenter/dragleave (un drag abandonné hors de la fenêtre laisserait le
     compteur déséquilibré, donc un voile plein écran bloquant l'application).
     Le modèle HTML de glisser-déposer réémet « dragover » toutes les ~350 ms. */
  let veilTimer = null;
  const hideVeil = () => { clearTimeout(veilTimer); veilTimer = null; $('dropVeil').hidden = true; };
  const pokeVeil = () => {
    $('dropVeil').hidden = false;
    clearTimeout(veilTimer);
    veilTimer = setTimeout(hideVeil, 900);
  };
  const hasFiles = (e) => !e.dataTransfer || [...(e.dataTransfer.types || [])].includes('Files');

  for (const ev of ['dragenter', 'dragover']) {
    window.addEventListener(ev, (e) => { e.preventDefault(); if (hasFiles(e)) pokeVeil(); });
  }
  for (const ev of ['dragend', 'dragleave', 'pointermove', 'pointerdown', 'blur']) {
    window.addEventListener(ev, () => { if (veilTimer !== null && ev !== 'dragleave') hideVeil(); });
  }
  $('dropVeil').addEventListener('click', hideVeil);
  window.addEventListener('drop', async (e) => {
    e.preventDefault(); hideVeil();
    const items = [...(e.dataTransfer?.items || [])];
    const files = [...(e.dataTransfer?.files || [])];
    if (!files.length) { toast('Aucun fichier reconnu dans le dépôt.', 'err'); return; }
    // récupère si possible une poignée persistante (rechargement ultérieur en 1 clic)
    const handles = await Promise.all(items.map((it) => handleOfDropItem(it)));
    for (let i = 0; i < files.length; i++) await handleFile(files[i], handles[i] || null);
  });

  // Filet de sécurité : l'overlay de chargement ne doit jamais bloquer
  // définitivement l'interface (clic ou Échap pour le refermer).
  $('loading').addEventListener('click', hideLoading);

  /* --- grandeur --- */
  document.querySelectorAll('#segMode button').forEach((b) => {
    b.onclick = () => {
      if (b.disabled) return;
      state.mode = b.dataset.mode;
      document.querySelectorAll('#segMode button').forEach((x) => x.classList.toggle('is-on', x === b));
      $('bandWrap').hidden = state.mode !== 'band';
      refreshAll(); updateDetail();
    };
  });
  $('bandSlider').oninput = (e) => {
    state.band = +e.target.value;
    updateBandOut(); refreshAll(); updateDetail();
  };
  $('bandPrev').onclick = () => stepBand(-1);
  $('bandNext').onclick = () => stepBand(1);

  /* --- couleurs --- */
  const sel = $('selCmap');
  sel.innerHTML = listColormaps().map((c) => `<option value="${c.key}">${c.label}</option>`).join('');
  sel.value = state.cmap;
  sel.onchange = () => { state.cmap = sel.value; refreshAll(); updateDetail(); };

  $('chkAuto').onchange = (e) => {
    state.autoScale = e.target.checked;
    $('inMin').disabled = $('inMax').disabled = state.autoScale;
    refreshAll();
  };
  const onBound = () => {
    let a = parseFloat($('inMin').value), b = parseFloat($('inMax').value);
    if (!Number.isFinite(a) || !Number.isFinite(b)) return;
    if (b <= a) b = a + 1;
    state.vmin = a; state.vmax = b;
    state.autoScale = false; $('chkAuto').checked = false;
    $('inMin').disabled = $('inMax').disabled = false;
    refreshAll(); updateDetail();
  };
  $('inMin').onchange = onBound;
  $('inMax').onchange = onBound;
  $('btnAutoScale').onclick = () => { state.autoScale = true; $('chkAuto').checked = true; $('inMin').disabled = $('inMax').disabled = true; refreshAll(); };
  $('btnAllScale').onclick = () => {
    if (!state.model) return;
    const rg = valueRange(state.model, state.model.runList.map((r) => r.id),
      state.model.excitations.map((e) => e.key), state.mode, state.band);
    if (!rg) return;
    state.autoScale = false; $('chkAuto').checked = false;
    $('inMin').disabled = $('inMax').disabled = false;
    state.vmin = Math.floor(rg[0] * 2) / 2; state.vmax = Math.ceil(rg[1] * 2) / 2;
    refreshAll(); updateDetail();
  };
  $('chkClamp').onchange = (e) => { state.clampOut = e.target.checked; refreshAll(); };

  /* --- billes --- */
  $('rngRadius').oninput = (e) => {
    state.radiusT = +e.target.value / 100;
    state.radius = radiusFromT(state.radiusT);
    refreshAll();
  };
  $('rngBallOpacity').oninput = (e) => {
    state.ballOpacity = +e.target.value / 100;
    $('outBallOpacity').textContent = `${e.target.value} %`;
    refreshAll();
  };
  $('chkScaleByLevel').onchange = (e) => { state.scaleByLevel = e.target.checked; refreshAll(); };
  $('chkLabels').onchange = (e) => {
    state.labels = e.target.checked;
    for (const v of views.values()) v.scene.setLabels(v.scene.labels, state.labels);
  };
  $('chkInspect').onchange = (e) => {
    state.inspect = e.target.checked;
    if (!state.inspect) { $('tip').hidden = true; for (const v of views.values()) v.scene.showHover(null); }
  };

  /* --- CAO --- */
  $('rngScale').oninput = (e) => { state.cadScale = Math.pow(10, +e.target.value); applyCadTransform(); };
  $('inScale').onchange = (e) => {
    const v = parseFloat(e.target.value);
    if (Number.isFinite(v) && v > 0) { state.cadScale = clamp(v, 1e-3, 1e3); applyCadTransform(); }
  };
  AXES.forEach((ax, i) => {
    $('rngT' + ax).oninput = (e) => { state.cadT[i] = +e.target.value; applyCadTransform(); };
    $('inT' + ax).onchange = (e) => {
      const v = parseFloat(e.target.value);
      if (!Number.isFinite(v)) return;
      state.cadT[i] = v;
      const r = $('rngT' + ax);                       // élargit la plage du curseur si besoin
      if (v < +r.min || v > +r.max) { const l = Math.abs(v) * 1.2; r.min = -l; r.max = l; }
      applyCadTransform();
    };
    $('rngR' + ax).oninput = (e) => { state.cadR[i] = +e.target.value; applyCadTransform(); };
    $('inR' + ax).onchange = (e) => { const v = parseFloat(e.target.value); if (Number.isFinite(v)) { state.cadR[i] = ((v + 180) % 360 + 360) % 360 - 180; applyCadTransform(); } };
  });
  $('chkPivot').onchange = (e) => { state.cadPivot = e.target.checked; applyCadTransform(); };
  $('rngOpacity').oninput = (e) => { state.cadOpacity = +e.target.value / 100; applyCadAppearance(); };
  $('chkFlat').onchange = (e) => { state.cadFlat = e.target.checked; applyCadAppearance(); };
  $('chkEdges').onchange = (e) => {
    state.cadEdges = e.target.checked;
    if (state.cadEdges && state.cad && !hasCadEdges(state.cad.group)) {
      showLoading('Calcul des arêtes…');
      setTimeout(() => {
        ensureCadEdges(state.cad.group);
        attachCad(); applyCadTransform(); applyCadAppearance();
        applyInterp(true);            // les clones sont neufs : champ à refaire
        hideLoading();
      }, 20);
    } else applyCadAppearance();
  };
  $('btnCadReset').onclick = () => {
    state.cadScale = 1; state.cadT = [0, 0, 0]; state.cadR = [0, 0, 0];
    applyCadTransform(); fitAll();
  };
  $('btnCadAuto').onclick = () => {
    if (!state.cad || !sensorBox) { toast('CAO et mesures nécessaires.', 'err'); return; }
    const cs = state.cad.bbox.getSize(new THREE.Vector3()).length() || 1;
    const ss = sensorBox.getSize(new THREE.Vector3()).length() || 1;
    const s = clamp(ss / cs, 1e-3, 1e3);
    const cc = cadCenter(), sc = sensorBox.getCenter(new THREE.Vector3());
    state.cadScale = s;
    state.cadR = [0, 0, 0];
    state.cadPivot = false; $('chkPivot').checked = false;
    state.cadT = [sc.x - s * cc.x, sc.y - s * cc.y, sc.z - s * cc.z];
    applyCadTransform(); fitAll();
    toast('Pré-recalage appliqué — ajustez finement si besoin.');
  };

  /* --- mesures --- */
  $('btnAllRuns').onclick = () => {
    state.model.runList.forEach((r) => state.selRuns.add(r.id));
    syncRunChecks(); refreshAll();
  };
  $('btnNoRuns').onclick = () => { state.selRuns.clear(); syncRunChecks(); refreshAll(); };
  $('runSearch').oninput = (e) => {
    const q = e.target.value.trim().toLowerCase();
    if (state.model?.flat) {
      for (const lab of $('runTree').querySelectorAll('.run')) {
        lab.classList.toggle('hidden', !!q && !(lab.textContent + ' ' + lab.title).toLowerCase().includes(q));
      }
      return;
    }
    for (const famEl of $('runTree').querySelectorAll('.fam')) {
      let visible = 0;
      for (const lab of famEl.querySelectorAll('.run')) {
        const txt = (lab.textContent + ' ' + lab.title).toLowerCase();
        const ok = !q || txt.includes(q);
        lab.classList.toggle('hidden', !ok);
        if (ok) visible++;
      }
      const famName = famEl.querySelector('.fam-name').textContent.toLowerCase();
      const show = visible > 0 || (!!q && famName.includes(q));
      famEl.classList.toggle('hidden', !show);
      if (q && show) famEl.classList.add('open');
    }
  };

  /* --- affichage --- */
  $('chkGrid').onchange = (e) => { state.showGrid = e.target.checked; applyHelpers(); };
  $('chkAxes').onchange = (e) => { state.showAxes = e.target.checked; applyHelpers(); };
  $('chkBox').onchange = (e) => { state.showBox = e.target.checked; applyHelpers(); };
  $('chkPersp').onchange = (e) => {
    state.persp = e.target.checked;
    for (const v of views.values()) { v.scene.setProjection(state.persp); v.scene.onCameraChange = onCameraChange; }
    fitAll();
  };
  document.querySelectorAll('#segView button').forEach((b) => {
    b.onclick = () => {
      document.querySelectorAll('#segView button').forEach((x) => x.classList.toggle('is-on', x === b));
      for (const v of views.values()) v.scene.setStandardView(b.dataset.v);
    };
  });

  /* --- interpolation RBF --- */
  $('selKernel').innerHTML = Object.entries(KERNELS)
    .map(([k, v]) => `<option value="${k}">${v.label}</option>`).join('');
  $('selPoly').innerHTML = Object.entries(POLY)
    .map(([k, v]) => `<option value="${k}">${v.label}</option>`).join('');
  pushInterpControls();

  $('chkInterp').onchange = (e) => {
    state.interp.on = e.target.checked;
    if (state.interp.on && state.interp.epsAuto) state.interp.eps = autoEps();
    pushInterpControls();
    applyInterp(true);
  };
  $('selKernel').onchange = (e) => { state.interp.kernel = e.target.value; scheduleInterp(); };
  $('selPoly').onchange = (e) => { state.interp.poly = e.target.value; scheduleInterp(); };
  $('rngEps').oninput = (e) => {
    state.interp.eps = epsFromT(+e.target.value / 100);
    state.interp.epsAuto = false;
    clampMeshStep();
    $('inEps').value = Math.round(state.interp.eps * 10) / 10;
    $('rngMesh').value = Math.round(tFromMesh(state.interp.meshStep) * 100);
    updateInterpUI();
    clearTimeout(interpTimer);
    interpTimer = setTimeout(() => applyInterp(true), 300);
  };
  $('inEps').onchange = (e) => {
    const v = parseFloat(e.target.value);
    if (!Number.isFinite(v) || v <= 0) return;
    state.interp.eps = v; state.interp.epsAuto = false;
    clampMeshStep();
    $('rngEps').value = Math.round(tFromEps(v) * 100);
    $('rngMesh').value = Math.round(tFromMesh(state.interp.meshStep) * 100);
    updateInterpUI(); applyInterp(true);
  };
  $('btnInterpAuto').onclick = () => {
    state.interp.eps = autoEps(); state.interp.epsAuto = true;
    state.interp.meshStep = autoMeshStep();
    pushInterpControls(); applyInterp(true);
  };
  $('rngLambda').oninput = (e) => {
    const v = +e.target.value;
    state.interp.lambda = v <= -8 ? 0 : Math.pow(10, v);
    updateInterpUI(); scheduleInterp();
  };
  $('chkMask').onchange = (e) => { state.interp.mask = e.target.checked; scheduleInterp(); };
  $('rngDmax').oninput = (e) => { state.interp.dmax = +e.target.value; updateInterpUI(); scheduleInterp(); };
  $('rngFieldOpacity').oninput = (e) => {
    state.interp.opacity = +e.target.value / 100;
    updateInterpUI();
    const I = state.interp;
    for (const v of views.values()) v.scene.setFieldEnabled(I.on && !!state.cad, I.opacity, I.meshStep, I.unlit);
  };
  $('chkFieldUnlit').onchange = (e) => {
    state.interp.unlit = e.target.checked;
    applyInterp(true);
  };
  $('rngMesh').oninput = (e) => {
    state.interp.meshStep = meshFromT(+e.target.value / 100);
    updateInterpUI();
    clearTimeout(interpTimer);
    interpTimer = setTimeout(() => applyInterp(true), 320);   // reconstruit le maillage
  };
  $('inMaxPts').onchange = (e) => {
    const v = parseInt(e.target.value, 10);
    if (Number.isFinite(v)) { state.interp.maxPts = clamp(v, 10, 1500); e.target.value = state.interp.maxPts; scheduleInterp(); }
  };
  $('chkInterpLive').onchange = (e) => { state.interp.live = e.target.checked; };
  $('btnInterpRun').onclick = () => runInterp();
  document.querySelectorAll('#segField button').forEach((b) => {
    b.onclick = () => {
      state.interp.display = b.dataset.f;
      document.querySelectorAll('#segField button').forEach((x) => x.classList.toggle('is-on', x === b));
      for (const v of views.values()) v.scene.setPointsVisible(!state.interp.on || state.interp.display === 'both');
    };
  });

  /* --- barre supérieure --- */
  $('btnSaveProj').onclick = saveProject;
  $('btnOpenProj').onclick = openProject;
  $('dBig').onclick = () => {
    state.detailBig = !state.detailBig;
    $('detail').classList.toggle('is-big', state.detailBig);
    requestAnimationFrame(() => { if (state.selected) drawSpectrum(state.selected.rec); });
  };
  $('btnFit').onclick = () => fitAll();
  $('btnSync').onclick = () => {
    state.sync = !state.sync;
    $('btnSync').classList.toggle('is-on', state.sync);
    if (state.sync && views.size) onCameraChange([...views.values()][0].scene);
  };
  $('btnSnap').onclick = snapshot;
  $('btnTheme').onclick = () => setTheme(state.theme === 'dark' ? 'light' : 'dark');
  $('dClose').onclick = () => selectRecord(null);

  /* --- clavier --- */
  window.addEventListener('keydown', (e) => {
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName)) return;
    if (e.key === 'f' || e.key === 'F') fitAll();
    else if (e.key === 'Escape') { hideLoading(); $('dropVeil').hidden = true; selectRecord(null); }
    else if (e.key === 'ArrowRight') stepBand(1);
    else if (e.key === 'ArrowLeft') stepBand(-1);
  });

  window.addEventListener('resize', () => { if (state.selected) drawSpectrum(state.selected.rec); });
}

function stepBand(d) {
  if (!state.model || !state.model.nBands) return;
  if (state.mode !== 'band') {
    state.mode = 'band';
    document.querySelectorAll('#segMode button').forEach((x) => x.classList.toggle('is-on', x.dataset.mode === 'band'));
    $('bandWrap').hidden = false;
  }
  state.band = clamp(state.band + d, 0, state.model.nBands - 1);
  $('bandSlider').value = state.band;
  updateBandOut(); refreshAll(); updateDetail();
}

function setTheme(t) {
  state.theme = t;
  document.documentElement.dataset.theme = t;
  const bg = getComputedStyle(document.body).getPropertyValue('--scene').trim();
  const hex = new THREE.Color(bg).getHex();
  for (const v of views.values()) v.scene.setBackground(hex);
  applyCadAppearance();
  applyHelpers();
  updateColorbar();
  scheduleInterp();                  // la teinte « sans mesure » suit le thème
  if (state.selected) drawSpectrum(state.selected.rec);
}

/* ============================== DÉMARRAGE ============================== */

bindUI();
$('inMin').disabled = $('inMax').disabled = state.autoScale;
updateFileBadge();
updateColorbar();
setupInterpBounds();
initFileHandles();
loop();
warmup();

// Aide au débogage / automatisation depuis la console du navigateur
window.VISUDATA = {
  state, views, refreshAll, handleFile, selectRecord, snapshot,
  runInterp, applyInterp, projectToObject, applyProject, openProjectObject,
};
