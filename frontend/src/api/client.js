import axios from "axios";
import { requestFinished, requestStarted } from "../composables/useRequestActivity";

const baseURL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const client = axios.create({
  baseURL,
  withCredentials: true,
});

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
        if (onUnauthorized) onUnauthorized();
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export default client;
