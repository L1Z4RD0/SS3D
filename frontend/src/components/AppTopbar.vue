<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { useTheme } from "../composables/useTheme";
import Icon from "./Icon.vue";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const { theme, toggle } = useTheme();

const titles = {
  dashboard: "Dashboard",
  calculator: "Calculadora de precios",
  sales: "Registro de ventas",
  inventory: "Inventario",
  printers: "Impresoras",
  admin: "Administración",
};

const title = computed(() => titles[route.name] || "Zola");

async function handleLogout() {
  await auth.logout();
  router.push({ name: "login" });
}
</script>

<template>
  <header class="topbar">
    <h1 class="topbar-title">{{ title }}</h1>
    <div class="topbar-actions">
      <button class="btn btn-icon btn-ghost" @click="toggle" :title="theme === 'dark' ? 'Modo claro' : 'Modo oscuro'">
        <Icon :name="theme === 'dark' ? 'sun' : 'moon'" :size="18" />
      </button>
      <button class="btn btn-secondary btn-sm" @click="handleLogout">
        <Icon name="logout" :size="15" />
        Cerrar sesión
      </button>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 32px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  position: sticky;
  top: 0;
  z-index: 10;
}

.topbar-title {
  font-size: 1.1rem;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 640px) {
  .topbar {
    padding: 14px 16px;
  }
}
</style>
