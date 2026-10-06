/* =========================================================================
   Projets VISUDATA (.visudata.json)

   Un projet contient toute la configuration de l'interface et une référence
   aux deux fichiers de données. Les navigateurs n'autorisent pas à rouvrir un
   fichier par son chemin : on conserve donc, quand le navigateur le permet
   (API File System Access : Chrome / Edge), une « poignée » persistante dans
   IndexedDB, ce qui permet de recharger les mêmes fichiers en un clic.
   À défaut, seuls les noms sont mémorisés et l'utilisateur les re-sélectionne.
   ========================================================================= */

const DB_NAME = 'visudata';
const STORE = 'handles';

export const fsaAvailable = typeof window.showOpenFilePicker === 'function';

/* ----------------------------------------------------------- IndexedDB mini */

function openDb() {
  return new Promise((resolve, reject) => {
    const rq = indexedDB.open(DB_NAME, 1);
    rq.onupgradeneeded = () => {
      if (!rq.result.objectStoreNames.contains(STORE)) rq.result.createObjectStore(STORE);
    };
    rq.onsuccess = () => resolve(rq.result);
    rq.onerror = () => reject(rq.error);
  });
}

async function idb(mode, fn) {
  try {
    const db = await openDb();
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, mode);
      const rq = fn(tx.objectStore(STORE));
      tx.oncomplete = () => { db.close(); resolve(rq ? rq.result : undefined); };
      tx.onerror = () => { db.close(); reject(tx.error); };
    });
  } catch (e) {
    return undefined;                       // navigation privée, quota, etc.
  }
}

export const putHandle = (key, handle) => idb('readwrite', (s) => s.put(handle, key));
export const getHandle = (key) => idb('readonly', (s) => s.get(key));
export const clearHandles = () => idb('readwrite', (s) => s.clear());

/* ------------------------------------------------------ sélection / lecture */

const TYPES = {
  cad: [{ description: 'CAO', accept: { 'model/step': ['.step', '.stp'], 'model/iges': ['.iges', '.igs'], 'application/octet-stream': ['.brep'] } }],
  json: [{ description: 'Mesures JSON', accept: { 'application/json': ['.json'] } }],
  project: [{ description: 'Projet VISUDATA', accept: { 'application/json': ['.json', '.visudata.json'] } }],
};

/**
 * Ouvre un sélecteur de fichier. Renvoie {file, handle} ou null si annulé.
 * Renvoie undefined si l'API n'est pas disponible (l'appelant doit alors
 * s'appuyer sur un <input type="file">).
 */
export async function pickFile(kind) {
  if (!fsaAvailable) return undefined;
  try {
    const [handle] = await window.showOpenFilePicker({
      multiple: false, id: 'visudata-' + kind, types: TYPES[kind] || [],
    });
    return { file: await handle.getFile(), handle };
  } catch (e) {
    return null;                            // annulation utilisateur
  }
}

/** Récupère une poignée depuis un élément déposé (si l'API le permet). */
export async function handleOfDropItem(item) {
  try {
    if (item && typeof item.getAsFileSystemHandle === 'function') {
      const h = await item.getAsFileSystemHandle();
      return h && h.kind === 'file' ? h : null;
    }
  } catch (e) { /* ignoré */ }
  return null;
}

/**
 * Relit un fichier depuis une poignée mémorisée.
 * @param {boolean} ask autorise la demande de permission (nécessite un geste utilisateur)
 * @returns {Promise<File|null>}
 */
export async function fileFromHandle(handle, ask = true) {
  if (!handle) return null;
  try {
    const opt = { mode: 'read' };
    let p = await handle.queryPermission(opt);
    if (p !== 'granted' && ask) p = await handle.requestPermission(opt);
    if (p !== 'granted') return null;
    return await handle.getFile();
  } catch (e) {
    return null;                            // fichier déplacé ou supprimé
  }
}

/* --------------------------------------------------------- écriture / lecture */

/** Enregistre un objet JSON (boîte « Enregistrer sous » si disponible). */
export async function saveJson(obj, filename) {
  const txt = JSON.stringify(obj, null, 2);
  if (typeof window.showSaveFilePicker === 'function') {
    try {
      const h = await window.showSaveFilePicker({
        suggestedName: filename, id: 'visudata-project',
        types: [{ description: 'Projet VISUDATA', accept: { 'application/json': ['.json'] } }],
      });
      const w = await h.createWritable();
      await w.write(txt);
      await w.close();
      return h.name;
    } catch (e) {
      if (e && e.name === 'AbortError') return null;
      /* sinon : repli sur le téléchargement */
    }
  }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([txt], { type: 'application/json' }));
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  return filename;
}

export async function readJson(file) {
  return JSON.parse(await file.text());
}

export const fileMeta = (file) => (file ? {
  name: file.name, size: file.size, lastModified: file.lastModified,
} : null);
