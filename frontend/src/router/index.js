import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "../stores/auth";

const routes = [
  {
    path: "/login",
    name: "login",
    component: () => import("../views/LoginView.vue"),
    meta: { public: true },
  },
  {
    path: "/",
    redirect: "/dashboard",
  },
  {
    path: "/dashboard",
    name: "dashboard",
    component: () => import("../views/DashboardView.vue"),
  },
  {
    path: "/calculadora",
    name: "calculator",
    component: () => import("../views/CalculatorView.vue"),
  },
  {
    path: "/cotizaciones",
    name: "quotes",
    component: () => import("../views/QuotesView.vue"),
  },
  {
    path: "/ventas",
    name: "sales",
    component: () => import("../views/SalesView.vue"),
    meta: { blockedForWatcher: true },
  },
  {
    path: "/inventario",
    name: "inventory",
    component: () => import("../views/InventoryView.vue"),
  },
  {
    path: "/impresoras",
    name: "printers",
    component: () => import("../views/PrintersView.vue"),
    meta: { blockedForWatcher: true },
  },
  {
    path: "/historial",
    name: "history",
    component: () => import("../views/HistoryView.vue"),
    meta: { blockedForWatcher: true },
  },
  {
    path: "/admin",
    name: "admin",
    component: () => import("../views/AdminView.vue"),
    meta: { requiresAdmin: true },
  },
  {
    path: "/:pathMatch(.*)*",
    name: "not-found",
    component: () => import("../views/NotFoundView.vue"),
    meta: { public: true },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  const auth = useAuthStore();

  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (to.name === "login" && auth.isAuthenticated) {
    return { name: "dashboard" };
  }
  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { name: "dashboard" };
  }
  // El watcher solo observa: no entra a Ventas, Impresoras ni Historial (datos propios
  // que no tiene), aunque escriba la URL a mano.
  if (to.meta.blockedForWatcher && auth.isWatcher) {
    return { name: "inventory" };
  }
  return true;
});

export default router;
