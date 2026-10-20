<script setup>
import { computed, ref, watch } from "vue";
import { useRequestActivity } from "../composables/useRequestActivity";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { useTheme } from "../composables/useTheme";
import { useMotion } from "../composables/useMotion";
import Icon from "./Icon.vue";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const { theme, toggle } = useTheme();
const { motion, toggle: toggleMotion } = useMotion();

const titles = {
  dashboard: "Dashboard",
  calculator: "Calculadora de precios",
  sales: "Registro de ventas",
  calendar: "Calendario de entregas",
  warehouse: "Almacén",
  quotes: "Cotizaciones",
  inventory: "Inventario",
  printers: "Impresoras",
  history: "Historial",
  admin: "Administración",
  split: "Reparto del mes",
  investment: "Mi inversión",
};

const title = computed(() => titles[route.name] || "Zola");

// Barra fina mientras se actualizan datos. Solo aparece si la espera supera 250 ms, para
// que las respuestas rápidas no la hagan parpadear.
const { pending } = useRequestActivity();
const refreshing = ref(false);
let refreshTimer = null;
watch(pending, (count) => {
  clearTimeout(refreshTimer);
  if (count > 0) refreshTimer = setTimeout(() => (refreshing.value = true), 250);
  else refreshing.value = false;
});

async function handleLogout() {
  await auth.logout();
  router.push({ name: "login" });
}
</script>

<template>
  <header class="topbar">
    <div class="topbar-left">
      <h1 class="topbar-title">{{ title }}</h1>
    </div>
    <div class="topbar-actions">
      <button
        class="btn btn-icon btn-ghost motion-btn"
        :class="{ off: motion === 'reduced' }"
        @click="toggleMotion"
        :title="motion === 'reduced' ? 'Movimiento: reducido (activar animaciones)' : 'Movimiento: completo (reducir animaciones)'"
      >
        <Icon name="sparkle" :size="18" />
      </button>
      <button class="btn btn-icon btn-ghost" @click="toggle" :title="theme === 'dark' ? 'Modo claro' : 'Modo oscuro'">
        <Icon :name="theme === 'dark' ? 'sun' : 'moon'" :size="18" />
      </button>
      <button class="btn btn-secondary btn-sm" @click="handleLogout">
        <Icon name="logout" :size="15" />
        <span class="logout-label">Cerrar sesión</span>
      </button>
    </div>
    <div class="refresh-bar" :class="{ on: refreshing }" aria-hidden="true"></div>
  </header>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 32px;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
  /* Translúcida: deja ver el fondo de colores (aurora) que hay detrás. */
  background: color-mix(in srgb, var(--surface) 62%, transparent);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
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

.topbar-title {
  font-size: 1.1rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.motion-btn {
  color: var(--primary);
}

/* Tachado cuando las animaciones están reducidas */
.motion-btn.off {
  color: var(--text-faint);
  position: relative;
}
.motion-btn.off::after {
  content: "";
  position: absolute;
  width: 20px;
  height: 2px;
  border-radius: 2px;
  background: currentColor;
  transform: rotate(-45deg);
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
}

@media (max-width: 420px) {
  .logout-label {
    display: none;
  }
}
</style>
