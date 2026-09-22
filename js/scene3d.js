/* =========================================================================
   Vue 3D (une par excitation affichée).
   - repère Z vers le haut (coordonnées capteurs / CAO en mm)
   - CAO : groupe transformable (échelle, translation, rotation, pivot)
   - mesures : InstancedMesh de sphères colorées + sélection / survol
   ========================================================================= */

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { fieldGeometry } from './cadLoader.js';

const SPHERE_GEO = new THREE.SphereGeometry(1, 20, 14);

export class Scene3D {
  constructor(container, opts = {}) {
    this.container = container;
    this.dirty = true;
    this.records = [];
    this.radius = 1;

    /* --- rendu --- */
    this.renderer = new THREE.WebGLRenderer({
      antialias: true, alpha: false, preserveDrawingBuffer: true,
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(1, 1, false);
    container.appendChild(this.renderer.domElement);

    /* --- scène --- */
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(opts.bg ?? 0x0b1725);

    this.scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    this.scene.add(new THREE.HemisphereLight(0xbcd8ff, 0x1c2836, 0.75));
    this.key = new THREE.DirectionalLight(0xffffff, 1.5);
    this.key.position.set(1, 1.2, 1.6);
    this.scene.add(this.key);
    this.fill = new THREE.DirectionalLight(0xcfe3ff, 0.7);
    this.fill.position.set(-1.2, -0.8, 0.6);
    this.scene.add(this.fill);

    /* --- caméra --- */
    this.persp = true;
    this.camera = this._makeCamera(true);
    this.controls = this._makeControls();

    /* --- racines --- */
    this.cadRoot = new THREE.Group();   // porte l'échelle / rotation / translation
    this.cadPivot = new THREE.Group();  // décalage de pivot (centre pièce)
    this.cadRoot.add(this.cadPivot);
    this.scene.add(this.cadRoot);

    this.pointsRoot = new THREE.Group();
    this.scene.add(this.pointsRoot);

    this.helpers = new THREE.Group();
    this.scene.add(this.helpers);

    /* --- marqueurs survol / sélection --- */
    const mk = (color, scale, op) => {
      const m = new THREE.Mesh(SPHERE_GEO, new THREE.MeshBasicMaterial({
        color, wireframe: true, transparent: true, opacity: op, depthTest: false,
      }));
      m.renderOrder = 20; m.visible = false; m.frustumCulled = false;
      this.scene.add(m);
      m.userData.k = scale;
      return m;
    };
    this.hoverMark = mk(0xffffff, 1.28, 0.9);
    this.selMark = mk(0xf28100, 1.5, 1.0);

    this.raycaster = new THREE.Raycaster();
    this._ro = new ResizeObserver(() => this.resize());
    this._ro.observe(container);
    this.resize();
  }

  /* ------------------------------------------------------------------ caméra */
  _makeCamera(persp) {
    const { w, h } = this._size();
    let cam;
    if (persp) {
      cam = new THREE.PerspectiveCamera(42, w / h, 0.05, 1e6);
    } else {
      const d = 500;
      cam = new THREE.OrthographicCamera(-d, d, d * h / w, -d * h / w, -1e6, 1e6);
    }
    cam.up.set(0, 0, 1);
    cam.position.set(1, -1, 0.7);
    return cam;
  }

  _makeControls() {
    const c = new OrbitControls(this.camera, this.renderer.domElement);
    c.enableDamping = true;
    c.dampingFactor = 0.09;
    c.rotateSpeed = 0.85;
    c.zoomSpeed = 0.9;
    c.panSpeed = 0.9;
    c.screenSpacePanning = true;
    c.addEventListener('change', () => {
      this.dirty = true;
      if (this.onCameraChange) this.onCameraChange(this);
    });
    return c;
  }

  setProjection(persp) {
    if (persp === this.persp) return;
    const target = this.controls.target.clone();
    const pos = this.camera.position.clone();
    const dist = pos.distanceTo(target);
    this.persp = persp;
    this.controls.dispose();
    this.camera = this._makeCamera(persp);
    this.camera.position.copy(pos);
    if (!persp) {
      const { w, h } = this._size();
      const d = dist * Math.tan(THREE.MathUtils.degToRad(21));
      this.camera.left = -d; this.camera.right = d;
      this.camera.top = d * h / w; this.camera.bottom = -d * h / w;
      this.camera.updateProjectionMatrix();
    }
    this.controls = this._makeControls();
    this.controls.target.copy(target);
    this.controls.update();
    this.dirty = true;
  }

  _size() {
    const r = this.container.getBoundingClientRect();
    return { w: Math.max(1, Math.round(r.width)), h: Math.max(1, Math.round(r.height)) };
  }

  resize() {
    const { w, h } = this._size();
    this.renderer.setSize(w, h, false);
    if (this.camera.isPerspectiveCamera) {
      this.camera.aspect = w / h;
    } else {
      const halfW = (this.camera.right - this.camera.left) / 2;
      this.camera.top = halfW * h / w;
      this.camera.bottom = -halfW * h / w;
    }
    this.camera.updateProjectionMatrix();
    this.dirty = true;
  }

  /* --------------------------------------------------------------------- CAO */
  setCad(group) {
    this.cadPivot.clear();
    if (group) this.cadPivot.add(group);
    this.cadGroup = group || null;
    // les anciens maillages (clones) disparaissent : l'état « champ » est à refaire
    if (this._origMats) this._origMats.clear();
    if (this._origGeos) this._origGeos.clear();
    this._fieldOn = false;
    this.dirty = true;
  }

  /**
   * Applique la transformation de recalage.
   * @param {{scale:number, t:number[], r:number[], pivotCenter:boolean, center:THREE.Vector3}} tr
   */
  setCadTransform(tr) {
    this.cadRoot.scale.setScalar(tr.scale);
    this.cadRoot.rotation.set(
      THREE.MathUtils.degToRad(tr.r[0]),
      THREE.MathUtils.degToRad(tr.r[1]),
      THREE.MathUtils.degToRad(tr.r[2]), 'XYZ');
    this.cadRoot.position.set(tr.t[0], tr.t[1], tr.t[2]);
    if (tr.pivotCenter && tr.center) {
      // p -> R.S.(p - c) + c + T  : la pièce ne « saute » pas quand on active le pivot
      this.cadPivot.position.copy(tr.center).multiplyScalar(-1);
      this.cadRoot.position.set(
        tr.t[0] + tr.center.x, tr.t[1] + tr.center.y, tr.t[2] + tr.center.z);
    } else {
      this.cadPivot.position.set(0, 0, 0);
    }
    this.cadRoot.updateMatrixWorld(true);
    this.dirty = true;
  }

  setCadVisibility(hiddenNames) {
    if (!this.cadGroup) return;
    for (const child of this.cadGroup.children) child.visible = !hiddenNames.has(child.name);
    this.dirty = true;
  }

  /* ------------------------------------------------- champ interpolé (RBF) */

  _fieldMeshes() {
    const out = [];
    if (this.cadGroup) this.cadGroup.traverse((o) => { if (o.isMesh && !o.userData.isEdge) out.push(o); });
    return out;
  }

  /**
   * Bascule les pièces en rendu « couleurs par sommet ».
   * Les géométries sont clonées à la première activation : chaque vue possède
   * alors ses propres couleurs (une excitation par vue), contrairement aux
   * géométries partagées du mode normal.
   */
  setFieldEnabled(on, opacity = 1, maxEdge = 0, unlit = true) {
    if (!this.cadGroup) return;
    if (!this._origMats) this._origMats = new Map();
    if (!this._origGeos) this._origGeos = new Map();

    if (on && (!this.fieldMat || this._fieldUnlit !== unlit)) {
      if (this.fieldMat) this.fieldMat.dispose();
      const common = { vertexColors: true, side: THREE.DoubleSide };
      this.fieldMat = unlit
        ? new THREE.MeshBasicMaterial(common)
        : new THREE.MeshStandardMaterial({ ...common, roughness: 0.82, metalness: 0 });
      this._fieldUnlit = unlit;
    }
    if (on) {
      this.fieldMat.opacity = opacity;
      this.fieldMat.transparent = opacity < 1;
      this.fieldMat.depthWrite = opacity >= 1;
      this.fieldMat.needsUpdate = true;
    }

    this.fieldTris = 0;
    this.fieldVerts = 0;
    this.fieldTruncated = false;
    for (const m of this._fieldMeshes()) {
      if (on) {
        const orig = this._origGeos.get(m) || m.geometry;
        if (!this._origGeos.has(m)) this._origGeos.set(m, orig);
        const edge = maxEdge > 0 ? maxEdge : Infinity;
        if (m.geometry.userData.fieldMaxEdge !== Math.round(edge * 100) / 100) {
          const g = maxEdge > 0 ? fieldGeometry(orig, maxEdge) : orig.clone();
          if (maxEdge <= 0) {
            g.setAttribute('color', new THREE.BufferAttribute(
              new Float32Array(g.attributes.position.count * 3).fill(0.55), 3));
            g.userData.fieldMaxEdge = Infinity;
            g.userData.fieldTris = (g.index ? g.index.count : g.attributes.position.count) / 3;
            g.userData.fieldVerts = g.attributes.position.count;
          }
          if (m.geometry !== orig) m.geometry.dispose();
          m.geometry = g;
        }
        this.fieldTris += m.geometry.userData.fieldTris || 0;
        this.fieldVerts += m.geometry.userData.fieldVerts || 0;
        if (m.geometry.userData.fieldTruncated) this.fieldTruncated = true;
        if (!this._origMats.has(m)) this._origMats.set(m, m.material);
        m.material = this.fieldMat;
      } else {
        if (this._origMats.has(m)) { m.material = this._origMats.get(m); this._origMats.delete(m); }
        if (this._origGeos.has(m)) {
          const orig = this._origGeos.get(m);
          if (m.geometry !== orig) m.geometry.dispose();
          m.geometry = orig;
          this._origGeos.delete(m);
        }
      }
    }
    this._fieldOn = !!on;
    this.dirty = true;
  }

  /**
   * Colorie les sommets. `sampler(x, y, z, out3)` reçoit la position en
   * coordonnées monde (transformation de recalage incluse) et écrit r,g,b.
   * @returns {number} nombre de sommets traités
   */
  paintField(sampler) {
    if (!this._fieldOn || !this.cadGroup) return 0;
    this.cadRoot.updateMatrixWorld(true);
    const v = new THREE.Vector3();
    const out = [0.5, 0.5, 0.5];
    let count = 0;
    for (const m of this._fieldMeshes()) {
      if (!m.visible) continue;
      const pos = m.geometry.attributes.position;
      const col = m.geometry.attributes.color;
      if (!col || col.count !== pos.count) continue;
      const mw = m.matrixWorld;
      const arr = col.array;
      for (let i = 0; i < pos.count; i++) {
        v.set(pos.getX(i), pos.getY(i), pos.getZ(i)).applyMatrix4(mw);
        sampler(v.x, v.y, v.z, out);
        arr[i * 3] = out[0]; arr[i * 3 + 1] = out[1]; arr[i * 3 + 2] = out[2];
      }
      col.needsUpdate = true;
      count += pos.count;
    }
    this.dirty = true;
    return count;
  }

  /** Nombre total de sommets des pièces visibles (indication de coût). */
  vertexCount() {
    let n = 0;
    for (const m of this._fieldMeshes()) if (m.visible) n += m.geometry.attributes.position.count;
    return n;
  }

  setPointsVisible(on) {
    this.pointsRoot.visible = !!on;
    this.dirty = true;
  }

  /**
   * Billes en couleurs brutes (non éclairées) : indispensable pour que leur
   * teinte soit comparable à celle de la surface interpolée et à la colorbar.
   * Le matériau est reconstruit au prochain setPoints().
   */
  setPointsUnlit(on) {
    this._pointsUnlit = !!on;
  }

  /* ------------------------------------------------------------------ billes */
  /**
   * @param {Array} records liste issue de buildRecords()
   * @param {Float32Array} colors 3 composantes par bille (0..1)
   * @param {number} radius rayon de base (unités scène = mm)
   * @param {Float32Array|null} scales facteur d'échelle par bille
   * @param {number} opacity
   */
  setPoints(records, colors, radius, scales, opacity) {
    this.records = records;
    this.radius = radius;
    this.scaleArr = scales || null;
    const n = records.length;

    if (!this.inst || this.inst.count !== n || this._instUnlit !== this._pointsUnlit) {
      if (this.inst) {
        this.pointsRoot.remove(this.inst);
        this.inst.material.dispose();
        this.inst.dispose();
        this.inst = null;
      }
      if (n > 0) {
        this._instUnlit = this._pointsUnlit;
        const mat = this._pointsUnlit
          ? new THREE.MeshBasicMaterial({})
          : new THREE.MeshStandardMaterial({ roughness: 0.38, metalness: 0.05 });
        this.inst = new THREE.InstancedMesh(SPHERE_GEO, mat, n);
        this.inst.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
        this.inst.frustumCulled = false;
        this.inst.renderOrder = 0;
        this.pointsRoot.add(this.inst);
      }
    }
    if (!this.inst) { this.dirty = true; return; }

    this.inst.material.transparent = opacity < 1;
    this.inst.material.opacity = opacity;
    this.inst.material.depthWrite = opacity >= 1;

    const m = new THREE.Matrix4();
    const c = new THREE.Color();
    for (let i = 0; i < n; i++) {
      const p = records[i].pos;
      const s = radius * (scales ? scales[i] : 1);
      m.makeScale(s, s, s);
      m.setPosition(p[0], p[1], p[2]);
      this.inst.setMatrixAt(i, m);
      c.setRGB(colors[i * 3], colors[i * 3 + 1], colors[i * 3 + 2]);
      this.inst.setColorAt(i, c);
    }
    this.inst.instanceMatrix.needsUpdate = true;
    if (this.inst.instanceColor) this.inst.instanceColor.needsUpdate = true;
    this.inst.computeBoundingSphere();

    /* En couleurs fidèles, les billes prennent exactement la teinte de la
       surface interpolée : un liseré sombre (faces arrière d'une sphère un peu
       plus grande) les garde repérables sans altérer leur couleur. */
    this._syncOutline(records, radius, scales);
    this.dirty = true;
  }

  _syncOutline(records, radius, scales) {
    const want = !!this._pointsUnlit && records.length > 0;
    if (!want) {
      if (this.instOut) {
        this.pointsRoot.remove(this.instOut);
        this.instOut.material.dispose(); this.instOut.dispose(); this.instOut = null;
      }
      return;
    }
    const n = records.length;
    if (!this.instOut || this.instOut.count !== n) {
      if (this.instOut) {
        this.pointsRoot.remove(this.instOut);
        this.instOut.material.dispose(); this.instOut.dispose();
      }
      this.instOut = new THREE.InstancedMesh(SPHERE_GEO, new THREE.MeshBasicMaterial({
        color: 0x0a1420, side: THREE.BackSide, transparent: true, opacity: 0.85,
      }), n);
      this.instOut.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      this.instOut.frustumCulled = false;
      this.pointsRoot.add(this.instOut);
    }
    const m = new THREE.Matrix4();
    for (let i = 0; i < n; i++) {
      const p = records[i].pos;
      const s = radius * (scales ? scales[i] : 1) * 1.16;
      m.makeScale(s, s, s);
      m.setPosition(p[0], p[1], p[2]);
      this.instOut.setMatrixAt(i, m);
    }
    this.instOut.instanceMatrix.needsUpdate = true;
    this.instOut.computeBoundingSphere();
  }

  /* ----------------------------------------------------------------- helpers */
  setHelpers({ grid, axes, box, sensorBox, size }) {
    this.helpers.clear();
    const s = Math.max(size || 100, 1);
    if (grid) {
      const step = niceStep(s / 8);
      const half = Math.ceil(s * 0.85 / step) * step;
      const g = new THREE.GridHelper(half * 2, (half * 2) / step, 0x35577a, 0x1d3350);
      g.rotation.x = Math.PI / 2;
      g.position.z = this._floorZ ?? 0;
      g.material.transparent = true; g.material.opacity = 0.5;
      this.helpers.add(g);
    }
    if (axes) {
      const a = new THREE.AxesHelper(s * 0.32);
      a.material.depthTest = false;
      a.renderOrder = 15;
      this.helpers.add(a);
    }
    if (box && sensorBox) {
      const b = new THREE.Box3Helper(sensorBox, new THREE.Color(0x00a3d7));
      b.material.transparent = true; b.material.opacity = 0.45;
      this.helpers.add(b);
    }
    this.dirty = true;
  }

  setFloorZ(z) { this._floorZ = z; }

  setBackground(hex) { this.scene.background = new THREE.Color(hex); this.dirty = true; }

  /* -------------------------------------------------------------- sélection */
  showHover(rec, idx = -1) { this._mark(this.hoverMark, rec, idx); }
  showSelection(rec, idx = -1) { this._mark(this.selMark, rec, idx); }

  _mark(mesh, rec, idx = -1) {
    if (!rec) { if (mesh.visible) { mesh.visible = false; this.dirty = true; } return; }
    const k = (idx >= 0 && this.scaleArr) ? this.scaleArr[idx] : 1;
    const s = this.radius * k * mesh.userData.k;
    mesh.position.set(rec.pos[0], rec.pos[1], rec.pos[2]);
    mesh.scale.setScalar(s);
    mesh.visible = true;
    this.dirty = true;
  }

  /** Renvoie l'indice de la bille sous le curseur, ou -1. */
  pick(clientX, clientY) {
    if (!this.inst) return -1;
    const r = this.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((clientX - r.left) / r.width) * 2 - 1,
      -((clientY - r.top) / r.height) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.camera);
    const hits = this.raycaster.intersectObject(this.inst, false);
    return hits.length ? hits[0].instanceId : -1;
  }

  /* ------------------------------------------------------------------ cadrage */
  boundsOfScene() {
    const box = new THREE.Box3();
    if (this.cadGroup) {
      this.cadRoot.updateMatrixWorld(true);
      const b = new THREE.Box3().setFromObject(this.cadRoot);
      if (!b.isEmpty()) box.union(b);
    }
    if (this.records.length) {
      const b = new THREE.Box3();
      for (const r of this.records) b.expandByPoint(new THREE.Vector3(r.pos[0], r.pos[1], r.pos[2]));
      b.expandByScalar(this.radius);
      box.union(b);
    }
    return box.isEmpty() ? null : box;
  }

  fit(box = null, immediate = true) {
    const b = box || this.boundsOfScene();
    if (!b) return;
    const center = b.getCenter(new THREE.Vector3());
    const radius = Math.max(b.getBoundingSphere(new THREE.Sphere()).radius, 1e-3);
    const dir = new THREE.Vector3().subVectors(this.camera.position, this.controls.target);
    if (dir.lengthSq() < 1e-9) dir.set(1, -1, 0.7);
    dir.normalize();

    if (this.camera.isPerspectiveCamera) {
      const fov = THREE.MathUtils.degToRad(this.camera.fov);
      const dist = (radius / Math.sin(fov / 2)) * 1.08;
      this.camera.position.copy(center).addScaledVector(dir, dist);
      this.camera.near = Math.max(dist / 5000, 0.01);
      this.camera.far = dist * 50;
    } else {
      const { w, h } = this._size();
      const d = radius * 1.1;
      this.camera.left = -d; this.camera.right = d;
      this.camera.top = d * h / w; this.camera.bottom = -d * h / w;
      this.camera.position.copy(center).addScaledVector(dir, radius * 4);
    }
    this.camera.updateProjectionMatrix();
    this.controls.target.copy(center);
    this.controls.update();
    this.dirty = true;
  }

  /** Vue prédéfinie : 'iso' | 'x' | 'y' | 'z' */
  setStandardView(v) {
    const b = this.boundsOfScene();
    const center = b ? b.getCenter(new THREE.Vector3()) : new THREE.Vector3();
    const dirs = { iso: [1, -1, 0.75], x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] };
    const d = dirs[v] || dirs.iso;
    const dist = this.camera.position.distanceTo(this.controls.target) || 1000;
    this.camera.position.copy(center).add(new THREE.Vector3(d[0], d[1], d[2]).normalize().multiplyScalar(dist));
    this.camera.up.set(0, 0, 1);
    if (v === 'z') this.camera.up.set(0, 1, 0);
    this.controls.target.copy(center);
    this.controls.update();
    this.fit(b);
  }

  getCameraState() {
    return {
      pos: this.camera.position.toArray(),
      up: this.camera.up.toArray(),
      target: this.controls.target.toArray(),
      zoom: this.camera.zoom,
      ortho: this.camera.isOrthographicCamera
        ? [this.camera.left, this.camera.right, this.camera.top, this.camera.bottom] : null,
    };
  }

  setCameraState(st, silent = true) {
    if (!st) return;
    this.camera.position.fromArray(st.pos);
    this.camera.up.fromArray(st.up);
    this.controls.target.fromArray(st.target);
    this.camera.zoom = st.zoom ?? 1;
    if (this.camera.isOrthographicCamera && st.ortho) {
      const { w, h } = this._size();
      const halfW = (st.ortho[1] - st.ortho[0]) / 2;
      this.camera.left = -halfW; this.camera.right = halfW;
      this.camera.top = halfW * h / w; this.camera.bottom = -halfW * h / w;
    }
    this.camera.updateProjectionMatrix();
    const cb = this.onCameraChange; if (silent) this.onCameraChange = null;
    this.controls.update();
    this.onCameraChange = cb;
    this.dirty = true;
  }

  /* -------------------------------------------------------------------- boucle */
  update() {
    const moved = this.controls.update();
    if (moved || this.dirty) {
      this.renderer.render(this.scene, this.camera);
      this.dirty = false;
      return true;
    }
    return false;
  }

  dispose() {
    this._ro.disconnect();
    this.controls.dispose();
    if (this.inst) this.inst.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }
}

function niceStep(x) {
  const p = Math.pow(10, Math.floor(Math.log10(Math.max(x, 1e-6))));
  const n = x / p;
  return (n < 1.5 ? 1 : n < 3.5 ? 2 : n < 7.5 ? 5 : 10) * p;
}
