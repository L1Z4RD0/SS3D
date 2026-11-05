/* Memoria de las consultas (GET) de la sesión, para que cambiar de módulo no vuelva a
   cargar todo cada vez.

   - Una consulta repetida se responde al instante con lo que ya se trajo.
   - Si eso tiene más de FRESH_MS, igual se muestra al instante y se actualiza en segundo
     plano (la próxima vez que se entre ya está al día: así se ven los cambios de los socios).
   - Pasado MAX_AGE_MS (ej. la pestaña quedó abierta toda la noche) se espera la respuesta
     nueva, como siempre.
   - Cualquier cambio (crear, editar, borrar...) borra toda la memoria: lo que se hizo se ve
     siempre al tiro. También se borra al iniciar o cerrar sesión.
   - Un filtro o una consulta distinta (otros parámetros) es otra entrada: se consulta.
*/
const FRESH_MS = 30 * 1000;
const MAX_AGE_MS = 10 * 60 * 1000;

const entries = new Map(); // clave -> { data, at }
const inflight = new Map(); // clave -> promesa de la respuesta
let generation = 0;
const listeners = new Set();

function sortedParams(params) {
  if (!params) return "";
  return JSON.stringify(
    Object.keys(params)
      .filter((k) => params[k] !== undefined)
      .sort()
      .map((k) => [k, params[k]])
  );
}

const keyFor = (url, params) => `${url}?${sortedParams(params)}`;

// Cada pantalla recibe su propia copia: si la modifica, no ensucia lo guardado.
const copy = (data) => (data === undefined || data === null ? data : structuredClone(data));

// No se guardan: descargas (Excel), la sesión y la auditoría (debe verse siempre al día).
function cacheable(url, config) {
  if (config?.responseType || config?.noCache) return false;
  return !url.startsWith("/api/auth") && !url.startsWith("/api/admin/audit");
}

export function createCachedGet(rawGet) {
  function fetchInto(key, url, config) {
    const gen = generation;
    const promise = rawGet(url, config)
      .then((res) => {
        // Si hubo un cambio mientras viajaba, la respuesta puede ser vieja: no se guarda.
        if (gen === generation) entries.set(key, { data: res.data, at: Date.now() });
        return res;
      })
      .finally(() => {
        if (inflight.get(key) === promise) inflight.delete(key);
      });
    inflight.set(key, promise);
    return promise;
  }

  return async function cachedGet(url, config = {}) {
    // (Se lee antes del primer await: la precarga lanza sus consultas de forma síncrona.)
    if (silentDepth > 0) config = { ...config, silent: true };
    if (!cacheable(url, config)) return rawGet(url, config);
    const key = keyFor(url, config.params);
    const hit = entries.get(key);
    const age = hit ? Date.now() - hit.at : Infinity;
    if (hit && age < MAX_AGE_MS) {
      if (age > FRESH_MS && !inflight.has(key)) {
        fetchInto(key, url, { ...config, silent: true }).catch(() => {});
      }
      return { data: copy(hit.data), status: 200, headers: {}, config, fromCache: true };
    }
    const res = await (inflight.get(key) || fetchInto(key, url, config));
    return { ...res, data: copy(res.data) };
  };
}

/* Precarga en segundo plano: las consultas que se lanzan dentro de fn() no encienden la
   barra de actividad. Si ya están en memoria y al día, no se vuelven a pedir. */
let silentDepth = 0;
export function silently(fn) {
  silentDepth += 1;
  try {
    return fn();
  } finally {
    silentDepth -= 1;
  }
}

export function clearApiCache() {
  generation += 1;
  entries.clear();
  inflight.clear();
  listeners.forEach((fn) => fn());
}

// Avisa cuando la memoria se borra por un cambio (la precarga vuelve a calentarse).
export function onCacheCleared(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
