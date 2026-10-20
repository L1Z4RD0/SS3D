import { test, expect } from "@playwright/test";

// Pruebas del bug de sesión: el login que "parpadea" y vuelve a pedir credenciales, y la
// interfaz del dashboard que desaparecía. Corren contra el backend real; los fallos de red
// y los tokens vencidos se simulan interceptando peticiones con page.route.

const API = "http://localhost:8001";
const USERNAME = process.env.E2E_USERNAME || "e2e_admin";
const PASSWORD = process.env.E2E_PASSWORD || "e2e-password-123";

const shell = (page) => page.locator(".app-shell");
const sidebarLink = (page, label) => page.locator(".nav-item", { hasText: label });

async function login(page) {
  await page.goto("/login");
  await page.locator("#username").fill(USERNAME);
  await page.locator("#password").fill(PASSWORD);
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(shell(page)).toBeVisible();
}

// Responde 401 a la próxima petición de datos (no de auth), como si el access token de 15
// minutos hubiera vencido justo en ese momento.
async function expireAccessTokenOnce(page) {
  let done = false;
  // Solo llamadas al backend: el servidor de Vite también sirve /src/api/*.js.
  await page.route((url) => url.origin === API && !url.pathname.startsWith("/api/auth/"), async (route) => {
    if (done) return route.continue();
    done = true;
    await route.fulfill({ status: 401, json: { detail: "Token invalido o expirado" } });
  });
}

// Simula la latencia de producción (Render): un /refresh que sale mientras otro está en
// curso queda retenido hasta que el primero responde. Así llega al backend con la cookie
// vieja DESPUÉS de que el primero la rotó, que es cuando el usuario quedaba afuera.
// (En local las dos peticiones llegan en el mismo milisegundo y el choque no se ve.)
async function delayOverlappingRefreshes(target) {
  let inFlight = null;
  await target.route(`${API}/api/auth/refresh`, async (route) => {
    const previous = inFlight;
    let finish;
    inFlight = new Promise((r) => (finish = r));
    if (previous) await previous;
    try {
      const response = await route.fetch();
      await route.fulfill({ response });
    } finally {
      finish();
    }
  });
}

test("credenciales incorrectas muestran el error y no entran", async ({ page }) => {
  await page.goto("/login");
  await page.locator("#username").fill(USERNAME);
  await page.locator("#password").fill("contraseña-incorrecta");
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await expect(page.locator(".alert-danger")).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

test("después del login, recargar mantiene la sesión", async ({ page }) => {
  await login(page);
  await page.reload();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(shell(page)).toBeVisible();
});

test("token vencido: se renueva solo y la interfaz no desaparece", async ({ page }) => {
  await login(page);
  await expireAccessTokenOnce(page);
  const refreshed = page.waitForResponse((r) => r.url().includes("/api/auth/refresh") && r.ok());
  await sidebarLink(page, "Ventas").click();
  await refreshed;
  await expect(page).toHaveURL(/\/ventas$/);
  await expect(shell(page)).toBeVisible();
});

test("refresh con falla pasajera (backend despertando) se reintenta sin cerrar la sesión", async ({ page }) => {
  await login(page);
  let refreshCalls = 0;
  await page.route(`${API}/api/auth/refresh`, async (route) => {
    refreshCalls += 1;
    if (refreshCalls === 1) return route.fulfill({ status: 503, body: "Service Unavailable" });
    return route.continue();
  });
  await expireAccessTokenOnce(page);
  await sidebarLink(page, "Inventario").click();
  await expect(page).toHaveURL(/\/inventario$/);
  await expect.poll(() => refreshCalls).toBeGreaterThanOrEqual(2);
  await expect(shell(page)).toBeVisible();
  await expect(page).not.toHaveURL(/\/login/);
});

test("sesión terminada de verdad: lleva al login en vez de dejar la vista sin interfaz", async ({ page }) => {
  await login(page);
  await page.route(`${API}/api/auth/refresh`, (route) =>
    route.fulfill({ status: 401, json: { detail: "Sesión inválida o expirada" } })
  );
  await expireAccessTokenOnce(page);
  await sidebarLink(page, "Historial").click();
  await expect(page).toHaveURL(/\/login\?redirect=/);
  await expect(page.locator("#username")).toBeVisible();
  await expect(shell(page)).toHaveCount(0);
});

test("dos pestañas recargadas a la vez (actualización de la PWA) siguen con sesión", async ({ context }) => {
  const first = await context.newPage();
  await login(first);
  const second = await context.newPage();
  await second.goto("/dashboard");
  await expect(shell(second)).toBeVisible();
  await delayOverlappingRefreshes(context);

  // Cada recarga dispara un /refresh con la misma cookie: antes, una de las dos perdía.
  for (let i = 0; i < 3; i++) {
    await Promise.all([first.reload(), second.reload()]);
    for (const page of [first, second]) {
      await expect(page).toHaveURL(/\/dashboard$/);
      await expect(shell(page)).toBeVisible();
    }
  }
});

test("dos refresh simultáneos con la misma cookie: el backend acepta ambos", async ({ page }) => {
  // Sin Web Locks de por medio (p. ej. navegador viejo o dos dispositivos con la cookie
  // copiada por la PWA): la ventana de gracia del backend tiene que cubrirlo.
  await login(page);
  await delayOverlappingRefreshes(page);
  const statuses = await page.evaluate(async (api) => {
    const call = () => fetch(`${api}/api/auth/refresh`, { method: "POST", credentials: "include" }).then((r) => r.status);
    return Promise.all([call(), call()]);
  }, API);
  expect(statuses).toEqual([200, 200]);
});

test("cerrar sesión y recargar vuelve al login", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "Cerrar sesión" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.reload();
  await expect(page).toHaveURL(/\/login/);
  await expect(page.locator("#username")).toBeVisible();
});
