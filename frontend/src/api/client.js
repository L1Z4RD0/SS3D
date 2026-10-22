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

client.interceptors.request.use((config) => {
  requestStarted();
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

let refreshPromise = null;

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

    if (status === 401 && !original._retry && !original.url?.includes("/api/auth/")) {
      original._retry = true;
      try {
        if (!refreshPromise) {
          refreshPromise = axios
            .post(`${baseURL}/api/auth/refresh`, {}, { withCredentials: true })
            .finally(() => {
              refreshPromise = null;
            });
        }
        const { data } = await refreshPromise;
        setAccessToken(data.access_token);
        original.headers.Authorization = `Bearer ${data.access_token}`;
        return client(original);
      } catch (refreshError) {
        const refreshStatus = refreshError.response?.status;
        // Solo se cierra la sesión si el servidor dice que ya no es válida. Si falló la
        // conexión (servidor despertando, sin internet) la sesión sigue: se puede reintentar.
        if (refreshStatus === 401 || refreshStatus === 403) {
          if (onUnauthorized) onUnauthorized();
          return Promise.reject(friendlyError(original, "Tu sesión expiró. Vuelve a iniciar sesión.", 401));
        }
        return Promise.reject(
          friendlyError(original, "No se pudo conectar con el servidor. Intenta de nuevo en unos segundos.", refreshStatus || 0)
        );
      }
    }

    return Promise.reject(error);
  }
);

export default client;
