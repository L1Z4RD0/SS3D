import axios from "axios";
import { requestFinished, requestStarted } from "../composables/useRequestActivity";

// En producción la app llama a /api en su MISMO dominio y Vercel lo reenvía al backend
// (vercel.json). Así la cookie de sesión es "propia" del sitio: Safari/iPhone y Brave bloquean
// las cookies de otro dominio (vercel.app -> onrender.com) y la sesión se perdía al recargar o
// a los 15 minutos. En desarrollo se usa VITE_API_URL. Se quita la "/" final: con ella las
// rutas quedaban "//api/..." y el servidor respondía "Not Found".
const baseURL = (import.meta.env.PROD ? "" : import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/+$/, "");

const client = axios.create({
  baseURL,
  withCredentials: true,
  // El servidor gratis puede tardar ~1 minuto en despertar: se espera, pero no para siempre.
  timeout: 90000,
});

// Error con el mismo formato que los del servidor ({ detail }), para que las pantallas
// muestren un texto claro en vez de "Not Found" o un mensaje genérico.
function friendlyError(original, detail, status) {
  const err = new Error(detail);
  err.config = original;
  err.response = { status, data: { detail } };
  return err;
}

let accessToken = null;
let onUnauthorized = null;

export function setAccessToken(token) {
  accessToken = token;
}

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

// Rutas de auth que NO deben reintentarse con un refresh (las demás de /api/auth/, como
// /me o /me/observed-users, sí: también usan el access token que vence a los 15 min).
const NO_REFRESH_PATHS = ["/api/auth/login", "/api/auth/refresh", "/api/auth/logout"];

// Un refresh que falla con 401/403 significa que la sesión de verdad terminó. Cualquier
// otro fallo (sin red, backend de Render despertando, 502/503) es pasajero: NO hay que
// cerrar la sesión por eso, o la interfaz desaparece aunque la sesión siga viva.
export function isSessionEndedError(error) {
  const status = error?.response?.status;
  return status === 401 || status === 403;
}

const RETRY_DELAYS_MS = [1500, 4000];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function postRefresh() {
  for (let attempt = 0; ; attempt++) {
    try {
      const { data } = await axios.post(`${baseURL}/api/auth/refresh`, {}, { withCredentials: true });
      return data;
    } catch (err) {
      if (isSessionEndedError(err) || attempt >= RETRY_DELAYS_MS.length) throw err;
      await sleep(RETRY_DELAYS_MS[attempt]);
    }
  }
}

// El refresh token rota en cada uso: si dos pestañas (o la app instalada y una pestaña)
// lo usan a la vez, la segunda manda un token ya revocado y el backend la deja afuera.
// Pasa seguido porque la actualización automática de la PWA recarga TODAS las pestañas a
// la vez. Con Web Locks las pestañas hacen el refresh de a una; como la cookie es
// compartida, la siguiente ya manda la cookie nueva.
function refreshWithLock() {
  if (typeof navigator !== "undefined" && navigator.locks?.request) {
    return navigator.locks.request("zola-auth-refresh", postRefresh);
  }
  return postRefresh();
}

let refreshPromise = null;

// Único punto que renueva la sesión (interceptor, arranque de la app y bfcache): así
// dentro de una pestaña nunca hay dos refresh en paralelo.
export function refreshSession() {
  if (!refreshPromise) {
    refreshPromise = refreshWithLock()
      .then((data) => {
        setAccessToken(data.access_token);
        return data;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

client.interceptors.request.use((config) => {
  requestStarted();
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => {
    requestFinished();
    return response;
  },
  async (error) => {
    // Si la petición nunca llegó a enviarse (error en el interceptor de salida) no hay nada
    // que descontar; en cualquier otro caso esta petición terminó.
    if (error.config) requestFinished();
    const original = error.config;
    const status = error.response?.status;

    if (status === 401 && original && !original._retry && !NO_REFRESH_PATHS.some((p) => original.url?.includes(p))) {
      original._retry = true;
      const sentToken = original.headers?.Authorization;
      try {
        // Si otra petición ya renovó el token mientras ésta viajaba, basta con reintentar.
        if (!accessToken || sentToken === `Bearer ${accessToken}`) {
          await refreshSession();
        }
        original.headers.Authorization = `Bearer ${accessToken}`;
        return client(original);
      } catch (refreshError) {
        if (isSessionEndedError(refreshError)) {
          if (onUnauthorized) onUnauthorized();
          return Promise.reject(friendlyError(original, "Tu sesión expiró. Vuelve a iniciar sesión.", 401));
        }
        return Promise.reject(
          friendlyError(
            original,
            "No se pudo conectar con el servidor. Intenta de nuevo en unos segundos.",
            refreshError.response?.status || 0
          )
        );
      }
    }

    return Promise.reject(error);
  }
);

export default client;
