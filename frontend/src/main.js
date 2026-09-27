import { createApp } from "vue";
import { createPinia } from "pinia";
import { registerSW } from "virtual:pwa-register";
import App from "./App.vue";
import router from "./router";
import { useAuthStore } from "./stores/auth";
import "./assets/main.css";

// Actualización de la PWA. Antes el service worker se registraba con el script por
// defecto, que descarga la versión nueva en segundo plano pero nunca recarga la página:
// la app podía quedarse días mostrando una versión vieja contra un backend nuevo (así
// se veían precios en $0 y columnas de IVA ya eliminadas). Con registerSW en modo
// autoUpdate, apenas la versión nueva toma el control la página se recarga sola.
// Además se revisa cada 30 minutos por si la app queda abierta mucho tiempo.
// (El borrador de la Calculadora se guarda solo, así que una recarga no lo pierde.)
const UPDATE_CHECK_MS = 30 * 60 * 1000;
registerSW({
  immediate: true,
  onRegisteredSW(_swUrl, registration) {
    if (!registration) return;
    setInterval(() => {
      if (navigator.onLine) registration.update().catch(() => {});
    }, UPDATE_CHECK_MS);
  },
});

const app = createApp(App);
app.use(createPinia());

const authStore = useAuthStore();
authStore.init().finally(() => {
  app.use(router);
  app.mount("#app");
});

// If the browser restores this page from back/forward cache (bfcache) -- e.g. hitting
// Back, or a link/shortcut that reuses a frozen tab -- the whole JS heap is restored
// exactly as it was, INCLUDING the Pinia auth state from before a logout that happened
// afterward, without main.js (or authStore.init()) ever running again. That would show
// the authenticated app as if nothing happened. On restore, re-check the session with
// the server and bounce to /login if it's no longer valid.
window.addEventListener("pageshow", (event) => {
  if (!event.persisted) return;
  authStore.tryRestoreSession().then(() => {
    if (!authStore.isAuthenticated && !router.currentRoute.value.meta.public) {
      router.push({ name: "login" });
    }
  });
});
