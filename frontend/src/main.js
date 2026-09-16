import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import { useAuthStore } from "./stores/auth";
import "./assets/main.css";

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
