/* =========================================================================
   Interpolation de champ par RBF (Radial Basis Functions).

   On résout  (Φ + λ̃·I)·w = f   avec  Φij = φ(‖xi − xj‖ / ε),
   éventuellement augmenté d'un terme polynomial (constante ou affine) :

        | Φ   P | | w |   | f |
        | Pᵗ  0 | | c | = | 0 |

   Le terme polynomial est indispensable pour les noyaux non décroissants
   (plaque mince, linéaire, multiquadrique) et améliore l'extrapolation.
   ========================================================================= */

export const KERNELS = {
  gauss: {
    label: 'Gaussien  exp(−(r/ε)²)',
    scaled: true,
    f: (r, e) => Math.exp(-(r * r) / (e * e)),
  },
  imq: {
    label: 'Multiquadrique inverse  1/√(1+(r/ε)²)',
    scaled: true,
    f: (r, e) => 1 / Math.sqrt(1 + (r * r) / (e * e)),
  },
  mq: {
    label: 'Multiquadrique  √(1+(r/ε)²)',
    scaled: true,
    f: (r, e) => Math.sqrt(1 + (r * r) / (e * e)),
  },
  tps: {
    label: 'Plaque mince  r²·ln r',
    scaled: false,
    f: (r) => (r > 1e-9 ? r * r * Math.log(r) : 0),
  },
  linear: {
    label: 'Linéaire  r',
    scaled: false,
    f: (r) => r,
  },
};

export const POLY = {
  none: { label: 'Aucun', n: 0 },
  const: { label: 'Constante', n: 1 },
  linear: { label: 'Affine (1, x, y, z)', n: 4 },
};

/* ---------------------------------------------------------------- solveur */

/** Élimination de Gauss avec pivot partiel. A : Float64Array n×n (par lignes). */
function solveDense(A, b, n) {
  const x = new Float64Array(n);
  for (let k = 0; k < n; k++) {
    // pivot
    let piv = k, best = Math.abs(A[k * n + k]);
    for (let i = k + 1; i < n; i++) {
      const v = Math.abs(A[i * n + k]);
      if (v > best) { best = v; piv = i; }
    }
    if (best < 1e-12) return null;                       // système singulier
    if (piv !== k) {
      for (let j = k; j < n; j++) {
        const t = A[k * n + j]; A[k * n + j] = A[piv * n + j]; A[piv * n + j] = t;
      }
      const t = b[k]; b[k] = b[piv]; b[piv] = t;
    }
    const akk = A[k * n + k];
    for (let i = k + 1; i < n; i++) {
      const m = A[i * n + k] / akk;
      if (m === 0) continue;
      A[i * n + k] = 0;
      for (let j = k + 1; j < n; j++) A[i * n + j] -= m * A[k * n + j];
      b[i] -= m * b[k];
    }
  }
  for (let i = n - 1; i >= 0; i--) {
    let s = b[i];
    for (let j = i + 1; j < n; j++) s -= A[i * n + j] * x[j];
    x[i] = s / A[i * n + i];
  }
  return x;
}

/* --------------------------------------------------------- sous-échantillon */

/**
 * Réduit le nuage à `maxPoints` en fusionnant d'abord les positions
 * quasi identiques (plusieurs mesures au même endroit) puis en gardant un
 * échantillon régulièrement réparti dans l'espace (tri par cellule).
 */
function reducePoints(pts, vals, maxPoints, mergeTol) {
  const n = pts.length / 3;
  // 1) fusion des doublons de position (moyenne des valeurs)
  const cell = Math.max(mergeTol, 1e-6);
  const map = new Map();
  for (let i = 0; i < n; i++) {
    const k = `${Math.round(pts[i * 3] / cell)}|${Math.round(pts[i * 3 + 1] / cell)}|${Math.round(pts[i * 3 + 2] / cell)}`;
    const e = map.get(k);
    if (e) { e.x += pts[i * 3]; e.y += pts[i * 3 + 1]; e.z += pts[i * 3 + 2]; e.v += vals[i]; e.n++; }
    else map.set(k, { x: pts[i * 3], y: pts[i * 3 + 1], z: pts[i * 3 + 2], v: vals[i], n: 1 });
  }
  let list = [...map.values()].map((e) => ({ x: e.x / e.n, y: e.y / e.n, z: e.z / e.n, v: e.v / e.n, k: e.n }));
  const nMerged = list.length;

  // 2) décimation régulière si encore trop de points
  let dropped = 0;
  if (list.length > maxPoints) {
    const step = list.length / maxPoints;
    const keep = [];
    for (let i = 0; i < maxPoints; i++) keep.push(list[Math.floor(i * step)]);
    dropped = list.length - keep.length;
    list = keep;
  }

  const P = new Float64Array(list.length * 3);
  const F = new Float64Array(list.length);
  list.forEach((e, i) => { P[i * 3] = e.x; P[i * 3 + 1] = e.y; P[i * 3 + 2] = e.z; F[i] = e.v; });
  return { P, F, n: list.length, nInput: n, nMerged, dropped };
}

/** Distance moyenne au plus proche voisin (échelle naturelle du nuage). */
export function meanNearestDistance(pts) {
  const n = pts.length / 3;
  if (n < 2) return 1;
  const step = n > 400 ? Math.ceil(n / 400) : 1;   // échantillon suffisant
  let sum = 0, cnt = 0;
  for (let i = 0; i < n; i += step) {
    let best = Infinity;
    for (let j = 0; j < n; j++) {
      if (i === j) continue;
      const dx = pts[i * 3] - pts[j * 3], dy = pts[i * 3 + 1] - pts[j * 3 + 1], dz = pts[i * 3 + 2] - pts[j * 3 + 2];
      const d = dx * dx + dy * dy + dz * dz;
      if (d < best) best = d;
    }
    if (best < Infinity) { sum += Math.sqrt(best); cnt++; }
  }
  return cnt ? sum / cnt : 1;
}

/* ------------------------------------------------------------------- modèle */

/**
 * Construit l'interpolant.
 * @param {Float32Array|number[]} pts positions xyz aplaties
 * @param {Float32Array|number[]} vals valeurs associées
 * @param {object} o {kernel, eps, lambda, poly, maxPoints, mergeTol}
 * @returns {object|null} interpolant : eval(x,y,z) -> valeur ; propriété `dmin`
 *                        mise à jour à chaque appel (distance au point le plus proche)
 */
export function buildRbf(pts, vals, o = {}) {
  const t0 = performance.now();
  const kernelKey = KERNELS[o.kernel] ? o.kernel : 'gauss';
  const K = KERNELS[kernelKey];
  const polyKey = POLY[o.poly] ? o.poly : 'const';
  const m = POLY[polyKey].n;
  const maxPoints = Math.max(4, o.maxPoints || 400);

  const red = reducePoints(pts, vals, maxPoints, o.mergeTol ?? 0.5);
  const n = red.n;
  if (n < 3) return null;

  const P = red.P, F = red.F;
  const eps = K.scaled ? Math.max(o.eps || 1, 1e-6) : 1;
  const N = n + m;

  const A = new Float64Array(N * N);
  const b = new Float64Array(N);
  let absSum = 0;

  for (let i = 0; i < n; i++) {
    for (let j = i; j < n; j++) {
      const dx = P[i * 3] - P[j * 3], dy = P[i * 3 + 1] - P[j * 3 + 1], dz = P[i * 3 + 2] - P[j * 3 + 2];
      const v = K.f(Math.sqrt(dx * dx + dy * dy + dz * dz), eps);
      A[i * N + j] = v; A[j * N + i] = v;
      absSum += Math.abs(v) * (i === j ? 1 : 2);
    }
    b[i] = F[i];
  }
  // régularisation (lissage) : relative à l'amplitude moyenne de Φ
  const scale = absSum / (n * n) || 1;
  const lam = (o.lambda ?? 0) * scale;
  if (lam > 0) for (let i = 0; i < n; i++) A[i * N + i] += lam;

  // bloc polynomial
  if (m > 0) {
    for (let i = 0; i < n; i++) {
      const cols = m === 1 ? [1] : [1, P[i * 3], P[i * 3 + 1], P[i * 3 + 2]];
      for (let c = 0; c < m; c++) {
        A[i * N + (n + c)] = cols[c];
        A[(n + c) * N + i] = cols[c];
      }
    }
  }

  const sol = solveDense(A, b, N);
  if (!sol) return null;

  const w = sol.subarray(0, n);
  const c = m > 0 ? sol.subarray(n, N) : null;
  const kf = K.f;
  /* Le noyau gaussien est négligeable au-delà de ~3,5 ε (5·10⁻⁶) : on évite
     l'exponentielle, de loin le coût dominant de l'évaluation. Les autres
     noyaux décroissent trop lentement (ou croissent) pour être tronqués. */
  const cut2 = kernelKey === 'gauss' ? (3.5 * eps) * (3.5 * eps) : Infinity;

  const model = {
    kernel: kernelKey, poly: polyKey, eps, lambda: o.lambda ?? 0,
    n, nInput: red.nInput, nMerged: red.nMerged, dropped: red.dropped,
    dmin: 0, dminIdx: 0,
    points: P, values: F,

    /** Valeur interpolée ; met à jour `model.dmin` et `model.dminIdx`. */
    eval(x, y, z) {
      let s = 0, best = Infinity, bi = 0;
      for (let i = 0; i < n; i++) {
        const dx = x - P[i * 3], dy = y - P[i * 3 + 1], dz = z - P[i * 3 + 2];
        const r2 = dx * dx + dy * dy + dz * dz;
        if (r2 < best) { best = r2; bi = i; }
        if (r2 > cut2) continue;
        s += w[i] * kf(Math.sqrt(r2), eps);
      }
      if (c) s += m === 1 ? c[0] : c[0] + c[1] * x + c[2] * y + c[3] * z;
      model.dmin = Math.sqrt(best);
      model.dminIdx = bi;
      return s;
    },
  };

  // écart résiduel aux points de données (non nul dès que λ > 0)
  let resMax = 0, resSum = 0;
  for (let i = 0; i < n; i++) {
    const d = Math.abs(model.eval(P[i * 3], P[i * 3 + 1], P[i * 3 + 2]) - F[i]);
    resMax = Math.max(resMax, d); resSum += d;
  }
  model.residualMax = resMax;
  model.residualMean = resSum / n;
  model.ms = Math.round(performance.now() - t0);
  return model;
}
