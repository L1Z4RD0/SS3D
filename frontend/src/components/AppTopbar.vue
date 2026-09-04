<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { useTheme } from "../composables/useTheme";
import { useMobileNav } from "../composables/useMobileNav";
import Icon from "./Icon.vue";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const { theme, toggle } = useTheme();
const mobileNav = useMobileNav();

const titles = {
  dashboard: "Dashboard",
  calculator: "Calculadora de precios",
  sales: "Registro de ventas",
  inventory: "Inventario",
  printers: "Impresoras",
  history: "Historial",
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
    <div class="topbar-left">
      <button type="button" class="btn btn-icon btn-ghost menu-btn" @click="mobileNav.toggle()">
        <Icon name="menu" :size="20" />
      </button>
      <h1 class="topbar-title">{{ title }}</h1>
    </div>
    <div class="topbar-actions">
      <button class="btn btn-icon btn-ghost" @click="toggle" :title="theme === 'dark' ? 'Modo claro' : 'Modo oscuro'">
        <Icon :name="theme === 'dark' ? 'sun' : 'moon'" :size="18" />
      </button>
      <button class="btn btn-secondary btn-sm" @click="handleLogout">
        <Icon name="logout" :size="15" />
        <span class="logout-label">Cerrar sesión</span>
      </button>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 32px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  position: sticky;
  top: 0;
  z-index: 10;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.menu-btn {
  display: none;
  flex-shrink: 0;
}

.topbar-title {
  font-size: 1.1rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

@media (max-width: 640px) {
  .topbar {
    padding: 14px 16px;
  }
  .menu-btn {
    display: flex;
  }
}

@media (max-width: 420px) {
  .logout-label {
    display: none;
  }
}
</style>
