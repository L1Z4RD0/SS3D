<script setup>
import { watch } from "vue";
import { useRoute } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { useMobileNav } from "../composables/useMobileNav";
import Icon from "./Icon.vue";

const auth = useAuthStore();
const route = useRoute();
const mobileNav = useMobileNav();

const links = [
  { to: "/dashboard", label: "Dashboard", icon: "dashboard" },
  { to: "/calculadora", label: "Calculadora", icon: "calculator" },
  { to: "/ventas", label: "Ventas", icon: "sales" },
  { to: "/inventario", label: "Inventario", icon: "inventory" },
  { to: "/impresoras", label: "Impresoras", icon: "printer" },
  { to: "/historial", label: "Historial", icon: "history" },
];

watch(
  () => route.fullPath,
  () => mobileNav.close()
);
</script>

<template>
  <div v-if="mobileNav.isOpen.value" class="sidebar-backdrop" @click="mobileNav.close()" />

  <aside class="sidebar" :class="{ open: mobileNav.isOpen.value }">
    <div class="sidebar-brand">
      <div class="brand-mark">Z</div>
      <span>Zola</span>
      <button type="button" class="sidebar-close" @click="mobileNav.close()">
        <Icon name="close" :size="18" />
      </button>
    </div>

    <nav class="sidebar-nav">
      <router-link v-for="link in links" :key="link.to" :to="link.to" class="nav-item">
        <Icon :name="link.icon" :size="20" />
        <span>{{ link.label }}</span>
      </router-link>

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
          <span>{{ auth.user?.role === "admin" ? "Administrador" : "Usuario" }}</span>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 240px;
  flex-shrink: 0;
  background: var(--sidebar-bg);
  color: var(--sidebar-text);
  display: flex;
  flex-direction: column;
  padding: 20px 14px;
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
  border-radius: 9px;
  background: linear-gradient(135deg, var(--primary), var(--accent));
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  color: #fff;
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
</style>
