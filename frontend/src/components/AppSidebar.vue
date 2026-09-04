<script setup>
import { useAuthStore } from "../stores/auth";
import Icon from "./Icon.vue";

const auth = useAuthStore();

const links = [
  { to: "/dashboard", label: "Dashboard", icon: "dashboard" },
  { to: "/calculadora", label: "Calculadora", icon: "calculator" },
  { to: "/ventas", label: "Ventas", icon: "sales" },
  { to: "/inventario", label: "Inventario", icon: "inventory" },
  { to: "/impresoras", label: "Impresoras", icon: "printer" },
];
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-brand">
      <div class="brand-mark">Z</div>
      <span>Zola</span>
    </div>

    <nav class="sidebar-nav">
      <router-link v-for="link in links" :key="link.to" :to="link.to" class="nav-item">
        <Icon :name="link.icon" :size="18" />
        <span>{{ link.label }}</span>
      </router-link>

      <div v-if="auth.isAdmin" class="nav-divider" />

      <router-link v-if="auth.isAdmin" to="/admin" class="nav-item">
        <Icon name="admin" :size="18" />
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
  font-size: 1.15rem;
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
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
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
  gap: 11px;
  padding: 10px 12px;
  border-radius: 10px;
  text-decoration: none;
  color: var(--sidebar-text);
  font-size: 0.88rem;
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
}

.user-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.user-meta strong {
  color: #fff;
  font-size: 0.84rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-meta span {
  font-size: 0.74rem;
  color: var(--sidebar-text);
}

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
</style>
