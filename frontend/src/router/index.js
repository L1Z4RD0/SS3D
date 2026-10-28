import { createRouter, createWebHistory } from "vue-router";
import { nextTick } from "vue";
import { useAuthStore } from "../stores/auth";
import { prefersReducedMotion } from "../composables/useMotion";

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
  },
  {
    path: "/almacen",
    name: "warehouse",
    component: () => import("../views/WarehouseView.vue"),
  },
  {
    path: "/calendario",
    name: "calendar",
    component: () => import("../views/CalendarView.vue"),
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
  },
  {
    path: "/rendimiento",
    name: "performance",
    component: () => import("../views/PerformanceView.vue"),
    meta: { companyOnly: true },
  },
  {
    path: "/reparto",
    name: "split",
    component: () => import("../views/SplitView.vue"),
  },
  {
    path: "/inversion",
    name: "investment",
    component: () => import("../views/InvestmentView.vue"),
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
  // El watcher registra ventas con el inventario de sus usuarios asignados, pero no
  // administra impresoras: no entra a Impresoras aunque escriba la URL a mano.
  // Rendimiento por cuenta: solo la cuenta Empresa (el servidor lo valida igual).
  if (to.meta.companyOnly && !auth.isCompany) {
    return { name: "dashboard" };
  }
  if (to.meta.blockedForWatcher && auth.isWatcher) {
    return { name: "inventory" };
  }
  return true;
});

// Cambio de sección con View Transitions: el navegador toma una foto de la página que sale
// y la funde con la que entra (estilos en motion.css). Navegadores sin soporte, el botón de
// "movimiento reducido" o entrar/salir del login: cambio normal, sin esperar nada.
let finishTransition = null;
let navigationDone = false;
router.beforeResolve((to, from) => {
  const sameShell = from.matched.length && !from.meta.public && !to.meta.public;
  if (!document.startViewTransition || !sameShell || to.path === from.path || prefersReducedMotion()) return true;
  navigationDone = false;
  return new Promise((resolve) => {
    document.documentElement.classList.add("vt-nav");
    const transition = document.startViewTransition(() =>
      // Si la navegación ya terminó por el plazo de abajo, no hay nada que esperar.
      navigationDone
        ? undefined
        : new Promise((done) => {
            finishTransition = done;
            resolve(true);
          })
    );
    transition.finished.finally(() => document.documentElement.classList.remove("vt-nav"));
    // Por si el navegador demora la foto (pestaña en segundo plano): la navegación no espera.
    setTimeout(() => resolve(true), 400);
  });
});
router.afterEach((to, from) => {
  // El contenido se desplaza dentro de .app-main (no la ventana): al cambiar de sección
  // vuelve arriba, si no la página nueva aparecía a media altura.
  if (to.path !== from.path) document.querySelector(".app-main")?.scrollTo(0, 0);
  navigationDone = true;
  if (!finishTransition) return;
  const done = finishTransition;
  finishTransition = null;
  // Espera a que Vue pinte la página nueva antes de que el navegador tome la segunda foto.
  nextTick(done);
});

export default router;
