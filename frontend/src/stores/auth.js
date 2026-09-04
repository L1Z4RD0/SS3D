import { defineStore } from "pinia";
import * as authApi from "../api/auth";
import { setAccessToken, setUnauthorizedHandler } from "../api/client";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    user: null,
    ready: false,
    loading: false,
    error: null,
  }),
  getters: {
    isAuthenticated: (state) => !!state.user,
    isAdmin: (state) => state.user?.role === "admin",
  },
  actions: {
    async login(username, password) {
      this.loading = true;
      this.error = null;
      try {
        const { access_token } = await authApi.login(username, password);
        setAccessToken(access_token);
        this.user = await authApi.fetchMe();
        return true;
      } catch (err) {
        this.error = err.response?.data?.detail || "No se pudo iniciar sesión";
        throw err;
      } finally {
        this.loading = false;
      }
    },
    async logout() {
      try {
        await authApi.logout();
      } catch {
        // ignore network errors on logout
      }
      setAccessToken(null);
      this.user = null;
    },
    async tryRestoreSession() {
      try {
        const { access_token } = await authApi.refresh();
        setAccessToken(access_token);
        this.user = await authApi.fetchMe();
      } catch {
        setAccessToken(null);
        this.user = null;
      } finally {
        this.ready = true;
      }
    },
    init() {
      setUnauthorizedHandler(() => {
        this.user = null;
      });
      return this.tryRestoreSession();
    },
  },
});
