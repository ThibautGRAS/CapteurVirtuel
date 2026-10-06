/* =========================================================================
   Palettes de couleurs (interpolation linéaire entre points de contrôle)
   Chaque palette renvoie [r,g,b] dans [0,1] pour t dans [0,1].
   ========================================================================= */

const STOPS = {
  cetim: {
    label: 'Spectre Cetim',
    stops: ['#0b2d52', '#0a5c9e', '#00a3d7', '#5fd0b0', '#ffd24d', '#f28100', '#d92b2b'],
  },
  viridis: {
    label: 'Viridis',
    stops: ['#440154', '#414487', '#2a788e', '#22a884', '#7ad151', '#fde725'],
  },
  magma: {
    label: 'Magma',
    stops: ['#000004', '#3b0f70', '#8c2981', '#de4968', '#fe9f6d', '#fcfdbf'],
  },
  jet: {
    label: 'Jet (classique)',
    stops: ['#00007f', '#0000ff', '#007fff', '#00ffff', '#7fff7f', '#ffff00', '#ff7f00', '#ff0000', '#7f0000'],
  },
  fire: {
    label: 'Chaud (noir→jaune)',
    stops: ['#08080c', '#4b1076', '#b3193f', '#f26b0a', '#ffd93b', '#fffbe8'],
  },
  grey: {
    label: 'Niveaux de gris',
    stops: ['#12181f', '#8a97a5', '#ffffff'],
  },
};

function hex2rgb(h) {
  const n = parseInt(h.slice(1), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

const CACHE = new Map();

/** Renvoie la liste des palettes disponibles : [{key, label}] */
export function listColormaps() {
  return Object.entries(STOPS).map(([key, v]) => ({ key, label: v.label }));
}

/**
 * Fonction d'échantillonnage d'une palette.
 * @param {string} key nom de la palette
 * @returns {(t:number)=>number[]} t dans [0,1] -> [r,g,b] dans [0,1]
 */
export function colormap(key) {
  if (!CACHE.has(key)) {
    const def = STOPS[key] || STOPS.cetim;
    CACHE.set(key, def.stops.map(hex2rgb));
  }
  const cols = CACHE.get(key);
  const n = cols.length - 1;
  return (t) => {
    if (!Number.isFinite(t)) return [0.5, 0.5, 0.5];
    const x = Math.min(1, Math.max(0, t)) * n;
    const i = Math.min(n - 1, Math.floor(x));
    const f = x - i;
    const a = cols[i], b = cols[i + 1];
    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
  };
}

/** Conversion utilitaire vers une chaîne CSS. */
export function cssColor(rgb) {
  return `rgb(${Math.round(rgb[0] * 255)},${Math.round(rgb[1] * 255)},${Math.round(rgb[2] * 255)})`;
}

/** Dessine un dégradé vertical (bas = 0) ou horizontal (gauche = 0) dans un canvas. */
export function paintGradient(canvas, key, vertical = false) {
  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;
  const cm = colormap(key);
  ctx.clearRect(0, 0, w, h);
  if (vertical) {
    for (let y = 0; y < h; y++) {
      ctx.fillStyle = cssColor(cm(1 - y / (h - 1)));
      ctx.fillRect(0, y, w, 1);
    }
  } else {
    for (let x = 0; x < w; x++) {
      ctx.fillStyle = cssColor(cm(x / (w - 1)));
      ctx.fillRect(x, 0, 1, h);
    }
  }
}
