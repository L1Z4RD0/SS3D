/* Precarga de los módulos al iniciar sesión, en segundo plano.

   Primero lo que más se usa (Dashboard, Calculadora y Ventas) y después, cuando el
   navegador está libre, el resto. Cada consulta queda en la memoria de la sesión (cache.js)
   con los MISMOS parámetros que usa la pantalla al abrirse, así al entrar al módulo ya está
   cargado. Si algo falla no pasa nada: la pantalla lo consulta al abrirse, como siempre.

   Después de un cambio (crear, editar...) la memoria se borra y se vuelve a precargar a los
   pocos segundos, para que el siguiente cambio de módulo también sea instantáneo. */
import * as dashboardApi from "./dashboard";
import * as historyApi from "./history";
import * as printersApi from "./printers";
import * as salesApi from "./sales";
import * as inventoryApi from "./inventory";
import * as authApi from "./auth";
import * as warehouseApi from "./warehouse";
import * as quotesApi from "./quotes";
import * as betaApi from "./beta";
import { getPerformance } from "./performance";
import { getFilamentCatalog } from "./catalog";
import { onCacheCleared, silently } from "./cache";
import { currentMonthRange, toLocalISODate, todayISO } from "../utils/format";
import { addDays, calendarRange, parseISO, readSavedCalendarView } from "../utils/calendarRange";

const settle = (promises) => Promise.allSettled(promises);
const idle = () =>
  new Promise((resolve) =>
    typeof window !== "undefined" && window.requestIdleCallback
      ? window.requestIdleCallback(() => resolve(), { timeout: 1500 })
      : setTimeout(resolve, 300)
  );

// Dashboard, Calculadora y Ventas (lo mismo que piden al abrirse).
function priorityRequests(auth) {
  return silently(() => [
    dashboardApi.getSummary(currentMonthRange()),
    dashboardApi.getByPrinter(currentMonthRange()),
    dashboardApi.getByPaymentMethod(currentMonthRange()),
    dashboardApi.getBySource(currentMonthRange()),
    dashboardApi.getStockAlerts(),
    historyApi.getMonthlyHistory(),
    printersApi.listPrinters(),
    salesApi.listSales({ status: "en_produccion", limit: 200 }),
    inventoryApi.listFilaments(),
    inventoryApi.listSupplies(),
    ...(auth.isWatcher ? [authApi.fetchObservedUsers()] : []),
    salesApi.listSales({ limit: 100, offset: 0, sort: "fecha", direction: "desc" }),
  ]);
}

function threeMonths() {
  const now = new Date();
  return {
    date_from: toLocalISODate(new Date(now.getFullYear(), now.getMonth() - 2, 1)),
    date_to: toLocalISODate(new Date(now.getFullYear(), now.getMonth() + 1, 0)),
  };
}

// El resto de los módulos.
async function otherRequests(auth) {
  const today = todayISO();
  const range = calendarRange(readSavedCalendarView(), parseISO(today));
  const month = today.slice(0, 7);
  const list = silently(() => [
    salesApi.calendarOrders({
      date_from: toLocalISODate(range.from),
      date_to: toLocalISODate(range.to),
      include_cancelled: false,
    }),
    salesApi.calendarOrders({ date_to: toLocalISODate(addDays(parseISO(today), -1)), status: "abiertos" }),
    quotesApi.listQuotes({ limit: 20, offset: 0 }),
    getFilamentCatalog(),
    ...(auth.isCompany ? [getPerformance(threeMonths())] : []),
  ]);
  // El Almacén de un observador se abre con el primero de sus usuarios.
  if (auth.isWatcher) {
    list.push(
      silently(() => authApi.fetchObservedUsers()).then((users) =>
        users[0] ? silently(() => warehouseApi.listPieces({ status: "en_almacen,reservada", owner_id: users[0].id })) : null
      )
    );
  } else {
    list.push(silently(() => warehouseApi.listPieces({ status: "en_almacen,reservada" })));
  }
  // Vistas beta: solo si tiene acceso.
  list.push(
    silently(() => betaApi.getBetaAccess()).then((access) => {
      const more = [];
      if (access.split) {
        more.push(...silently(() => [betaApi.getMonthlySplit(month), betaApi.listExpenses(month), betaApi.getCashBox(month)]));
      }
      if (access.investment) more.push(silently(() => betaApi.getMyInvestment()));
      return settle(more);
    })
  );
  return settle(list);
}

let running = null;
let pendingAgain = false;
let currentAuth = null;
let rewarmTimer = null;

async function run() {
  const auth = currentAuth;
  if (!auth?.user) return;
  await settle(priorityRequests(auth));
  await idle();
  if (currentAuth !== auth || !auth.user) return;
  await otherRequests(auth);
}

function schedule() {
  if (running) {
    pendingAgain = true;
    return;
  }
  running = run()
    .catch(() => {})
    .finally(() => {
      running = null;
      if (pendingAgain) {
        pendingAgain = false;
        schedule();
      }
    });
}

// Tras un cambio la memoria se borra: se vuelve a precargar cuando todo se calma.
onCacheCleared(() => {
  if (!currentAuth?.user) return;
  clearTimeout(rewarmTimer);
  rewarmTimer = setTimeout(schedule, 4000);
});

export function startPrefetch(auth) {
  currentAuth = auth;
  schedule();
}

export function stopPrefetch() {
  currentAuth = null;
  clearTimeout(rewarmTimer);
}
