<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from "vue";
import * as betaApi from "../api/beta";
import { useRoute } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { useMobileNav } from "../composables/useMobileNav";
import Icon from "./Icon.vue";

const auth = useAuthStore();
const route = useRoute();
const mobileNav = useMobileNav();

const allLinks = [
  { to: "/dashboard", label: "Dashboard", icon: "dashboard" },
  { to: "/calculadora", label: "Calculadora", icon: "calculator" },
  { to: "/cotizaciones", label: "Cotizaciones", icon: "sales" },
  { to: "/ventas", label: "Ventas", icon: "sales" },
  { to: "/calendario", label: "Calendario", icon: "calendar" },
  { to: "/inventario", label: "Inventario", icon: "inventory" },
  { to: "/almacen", label: "Almacén", icon: "box" },
  { to: "/impresoras", label: "Impresoras", icon: "printer", hideForWatcher: true },
  { to: "/historial", label: "Historial", icon: "history" },
  // Solo la cuenta Empresa: Diego, Sntg y la Empresa por separado y juntas.
  { to: "/rendimiento", label: "Rendimiento", icon: "trend", companyOnly: true },
];

const roleLabel = computed(() => {
  if (auth.isAdmin) return "Administrador";
  if (auth.isCompany) return "Empresa";
  if (auth.isWatcher) return "Observador";
  return "Usuario";
});

// La Empresa sí tiene impresoras propias (a futuro); el observador común no.
const links = computed(() =>
  allLinks.filter(
    (link) => !(link.hideForWatcher && auth.isWatcher && !auth.isCompany) && !(link.companyOnly && !auth.isCompany)
  )
);

// Vistas BETA (Reparto e Inversión): solo para quien tiene acceso.
const beta = ref({ split: false, investment: false });
watch(
  () => auth.user?.id,
  async (id) => {
    beta.value = { split: false, investment: false };
    if (!id) return;
    try {
      beta.value = await betaApi.getBetaAccess();
    } catch {
      // Si falla, simplemente no se muestran las vistas beta.
    }
  },
  { immediate: true }
);

watch(
  () => route.fullPath,
  () => mobileNav.close()
);

// Fondo de la sección activa que se desliza de una opción a otra.
const navEl = ref(null);
const indicator = ref({ top: 0, height: 0, visible: false });
function moveIndicator() {
  const active = navEl.value?.querySelector(".nav-item.router-link-active");
  indicator.value = active
    ? { top: active.offsetTop, height: active.offsetHeight, visible: true }
    : { ...indicator.value, visible: false };
}
watch(
  () => [route.fullPath, beta.value.split, beta.value.investment, auth.isAdmin],
  () => nextTick(moveIndicator)
);
onMounted(() => {
  nextTick(moveIndicator);
  window.addEventListener("resize", moveIndicator);
});
onBeforeUnmount(() => window.removeEventListener("resize", moveIndicator));
</script>

<template>
  <div v-if="mobileNav.isOpen.value" class="sidebar-backdrop" @click="mobileNav.close()" />

  <aside class="sidebar" :class="{ open: mobileNav.isOpen.value }">
    <div class="sidebar-brand">
      <img class="brand-mark" src="/img/LogoZola.png" alt="" />
      <span>Zola</span>
      <button type="button" class="sidebar-close" @click="mobileNav.close()">
        <Icon name="close" :size="18" />
      </button>
    </div>

    <nav ref="navEl" class="sidebar-nav" :class="{ 'has-indicator': indicator.visible }">
      <div
        class="nav-indicator"
        :class="{ visible: indicator.visible }"
        :style="{ transform: `translateY(${indicator.top}px)`, height: `${indicator.height}px` }"
        aria-hidden="true"
      ></div>
      <router-link v-for="link in links" :key="link.to" :to="link.to" class="nav-item">
        <Icon :name="link.icon" :size="20" />
        <span>{{ link.label }}</span>
      </router-link>

      <template v-if="beta.split || beta.investment">
        <div class="nav-divider" />
        <router-link v-if="beta.split" to="/reparto" class="nav-item">
          <Icon name="users" :size="20" />
          <span>Reparto</span>
          <span class="nav-beta">BETA</span>
        </router-link>
        <router-link v-if="beta.investment" to="/inversion" class="nav-item">
          <Icon name="dashboard" :size="20" />
          <span>Mi inversión</span>
          <span class="nav-beta">BETA</span>
        </router-link>
      </template>

      <div v-if="auth.isAdmin" class="nav-divider" />

      <router-link v-if="auth.isAdmin" to="/admin" class="nav-item">
        <Icon name="admin" :size="20" />
        <span>Administración</span>
      </router-link>
    </nav>

    <div class="sidebar-footer">
      <div class="user-chip">
        <div class="user-avatar">{{ auth.user?.username?.[0]?.toUpperCase() }}</div>
        <div class="user-meta">
          <strong>{{ auth.user?.username }}</strong>
          <span>{{ roleLabel }}</span>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 240px;
  flex-shrink: 0;
  height: 100vh;
  background: var(--sidebar-bg);
  color: var(--sidebar-text);
  display: flex;
  flex-direction: column;
  padding: 20px 14px;
  overflow: hidden;
  position: relative;
  isolation: isolate;
}

/* Brillo de la marca que "respira" detrás del logo */
.sidebar::before {
  content: "";
  position: absolute;
  left: -90px;
  top: -110px;
  width: 260px;
  height: 260px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(91, 75, 245, 0.45), transparent 65%);
  animation: sidebar-breathe 7s ease-in-out infinite;
  pointer-events: none;
  z-index: -1;
}
@keyframes sidebar-breathe {
  50% {
    transform: translate(30px, 20px) scale(1.15);
    opacity: 0.7;
  }
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px 24px;
  font-weight: 800;
  font-size: 1.2rem;
  color: #fff;
  letter-spacing: -0.01em;
}

.brand-mark {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  object-fit: cover;
  flex-shrink: 0;
}

.sidebar-close {
  display: none;
  margin-left: auto;
  background: transparent;
  border: none;
  color: var(--sidebar-text);
  padding: 6px;
  border-radius: 8px;
  cursor: pointer;
}

.sidebar-close:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex: 1;
  min-height: 0; /* lets this shrink and actually scroll instead of pushing the footer out */
  overflow-y: auto;
}

.nav-divider {
  height: 1px;
  background: rgba(255, 255, 255, 0.08);
  margin: 10px 10px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 12px;
  border-radius: 10px;
  text-decoration: none;
  color: var(--sidebar-text);
  font-size: 1rem;
  font-weight: 550;
  transition: background 0.15s ease, color 0.15s ease;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.06);
  color: var(--sidebar-text-active);
}

.nav-item.router-link-active {
  background: var(--sidebar-active-bg);
  color: var(--sidebar-text-active);
}

.sidebar-nav {
  position: relative;
}

.nav-item {
  position: relative;
  z-index: 1;
}

/* Con el indicador listo, el fondo activo lo dibuja el indicador (que se desliza). */
.sidebar-nav.has-indicator .nav-item.router-link-active {
  background: transparent;
}

.nav-indicator {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  border-radius: 10px;
  background: var(--sidebar-active-bg);
  opacity: 0;
  transition: transform 0.45s var(--ease-spring), height 0.3s var(--ease-out), opacity 0.2s;
  pointer-events: none;
}

.nav-indicator.visible {
  opacity: 1;
}

.nav-indicator::before {
  content: "";
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 3px;
  border-radius: 3px;
  background: linear-gradient(var(--primary), var(--accent));
}

.sidebar-footer {
  padding-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.user-chip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
}

.user-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--primary-soft);
  color: var(--primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.9rem;
  flex-shrink: 0;
}

.user-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.user-meta strong {
  color: #fff;
  font-size: 0.92rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-meta span {
  font-size: 0.8rem;
  color: var(--sidebar-text);
}

.sidebar-backdrop {
  display: none;
}

/* Tablet / small laptop: compact icon-only rail */
@media (max-width: 900px) {
  .sidebar {
    width: 76px;
  }
  .sidebar-brand span,
  .nav-item span,
  .user-meta {
    display: none;
  }
  .nav-item {
    justify-content: center;
  }
  .user-chip {
    justify-content: center;
  }
}

/* Mobile: off-canvas drawer, opened via the hamburger button in the topbar */
@media (max-width: 640px) {
  .sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    z-index: 200;
    width: min(78vw, 280px);
    transform: translateX(-100%);
    transition: transform 0.22s ease;
    box-shadow: var(--shadow-lg);
  }

  .sidebar.open {
    transform: translateX(0);
  }

  .sidebar-brand span,
  .nav-item span {
    display: block;
  }

  .user-meta {
    display: flex;
  }

  .sidebar-close {
    display: flex;
  }

  .nav-item {
    justify-content: flex-start;
  }

  .user-chip {
    justify-content: flex-start;
  }

  .sidebar-backdrop {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(10, 10, 20, 0.5);
    z-index: 190;
  }
}

.nav-beta {
  margin-left: auto;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  font-size: 0.62rem;
  font-weight: 800;
  letter-spacing: 0.05em;
}
</style>
