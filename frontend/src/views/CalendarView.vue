<script setup>
import { ref, computed, watch, onMounted } from "vue";
import * as salesApi from "../api/sales";
import { formatCurrency, formatDate, toLocalISODate, todayISO } from "../utils/format";
import { extractApiError } from "../utils/validation";
import { useAuthStore } from "../stores/auth";
import { STATUS_LABELS, statusClass, isOverdue } from "../utils/orderStatus";
import Icon from "../components/Icon.vue";
import OrderStatusModal from "../components/OrderStatusModal.vue";

/* Calendario de pedidos: cada pedido aparece en su fecha de entrega comprometida.
   Vistas mes, semana y día; los pedidos son de día completo (no tienen hora). */
const auth = useAuthStore();
const today = todayISO();

const VIEWS = [
  { key: "month", label: "Mes" },
  { key: "week", label: "Semana" },
  { key: "day", label: "Día" },
];
const WEEKDAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
const MAX_PER_CELL = 3;

const VIEW_KEY = "zola:calendar:view";
function readSavedView() {
  try {
    const v = localStorage.getItem(VIEW_KEY);
    return VIEWS.some((x) => x.key === v) ? v : "month";
  } catch {
    return "month";
  }
}

const view = ref(readSavedView());
const cursor = ref(parseISO(today));
const showCancelled = ref(false);
// Estados visibles (leyenda clickeable). Cancelados se controlan aparte.
const visibleStatuses = ref(new Set(["pendiente", "en_produccion", "lista", "entregada"]));

const orders = ref([]);
const overdue = ref([]);
const loading = ref(true);
const error = ref("");
const openSaleId = ref(null);

watch(view, (v) => {
  try {
    localStorage.setItem(VIEW_KEY, v);
  } catch {
    // almacenamiento bloqueado: solo no se recuerda la vista
  }
});

/* -------- Fechas (siempre en hora local, como strings YYYY-MM-DD) --------
   Todas las fechas se fijan al MEDIODÍA: en Chile el cambio de horario de verano ocurre
   a medianoche (ese día las 00:00 no existen), y con fechas a medianoche un día podía
   correrse una hora y caerse del calendario. */
function atNoon(y, m, d) {
  return new Date(y, m, d, 12);
}
function parseISO(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return atNoon(y, m - 1, d);
}
function addDays(date, n) {
  return atNoon(date.getFullYear(), date.getMonth(), date.getDate() + n);
}
function startOfWeek(date) {
  // Semana de lunes a domingo.
  return addDays(date, -((date.getDay() + 6) % 7));
}

const range = computed(() => {
  const c = cursor.value;
  if (view.value === "month") {
    const first = startOfWeek(atNoon(c.getFullYear(), c.getMonth(), 1));
    return { from: first, to: addDays(first, 41), count: 42 };
  }
  if (view.value === "week") {
    const from = startOfWeek(c);
    return { from, to: addDays(from, 6), count: 7 };
  }
  return { from: c, to: c, count: 1 };
});

// Por cantidad de días (no comparando horas), para que siempre salgan 42 / 7 / 1.
const days = computed(() => Array.from({ length: range.value.count }, (_, i) => addDays(range.value.from, i)));

const capitalize = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const title = computed(() => {
  const c = cursor.value;
  if (view.value === "month") {
    return capitalize(c.toLocaleDateString("es-CL", { month: "long", year: "numeric" }));
  }
  if (view.value === "week") {
    const { from, to } = range.value;
    const f = from.toLocaleDateString("es-CL", { day: "numeric", month: "short" });
    const t = to.toLocaleDateString("es-CL", { day: "numeric", month: "short", year: "numeric" });
    return `${f} – ${t}`;
  }
  return capitalize(c.toLocaleDateString("es-CL", { weekday: "long", day: "numeric", month: "long", year: "numeric" }));
});

function move(step) {
  const c = cursor.value;
  if (view.value === "month") cursor.value = atNoon(c.getFullYear(), c.getMonth() + step, 1);
  else cursor.value = addDays(c, step * (view.value === "week" ? 7 : 1));
}
function goToday() {
  cursor.value = parseISO(today);
}
function openDay(date) {
  cursor.value = date;
  view.value = "day";
}

/* -------- Datos -------- */
async function load() {
  loading.value = true;
  error.value = "";
  const yesterday = toLocalISODate(addDays(parseISO(today), -1));
  try {
    const [inRange, late] = await Promise.all([
      salesApi.calendarOrders({
        date_from: toLocalISODate(range.value.from),
        date_to: toLocalISODate(range.value.to),
        include_cancelled: showCancelled.value,
      }),
      salesApi.calendarOrders({ date_to: yesterday, status: "abiertos" }),
    ]);
    orders.value = inRange;
    overdue.value = late;
  } catch (err) {
    error.value = extractApiError(err, "No se pudo cargar el calendario.");
  } finally {
    loading.value = false;
  }
}

watch([() => toLocalISODate(range.value.from), () => toLocalISODate(range.value.to), showCancelled], load);
onMounted(load);

const visibleOrders = computed(() =>
  orders.value.filter((o) => (o.status === "cancelado" ? showCancelled.value : visibleStatuses.value.has(o.status)))
);

const ordersByDay = computed(() => {
  const map = {};
  for (const o of visibleOrders.value) (map[o.promised_delivery_date] ||= []).push(o);
  return map;
});

const counts = computed(() => {
  const c = {};
  for (const o of orders.value) c[o.status] = (c[o.status] || 0) + 1;
  return c;
});

function toggleStatus(s) {
  const next = new Set(visibleStatuses.value);
  if (next.has(s)) next.delete(s);
  else next.add(s);
  visibleStatuses.value = next;
}

function dayOrders(date) {
  return ordersByDay.value[toLocalISODate(date)] || [];
}
function isToday(date) {
  return toLocalISODate(date) === today;
}
function inCurrentMonth(date) {
  return date.getMonth() === cursor.value.getMonth();
}
function daysLate(o) {
  return Math.round((parseISO(today) - parseISO(o.promised_delivery_date)) / 86400000);
}
// Dueño y quién lo registró, cuando no es uno mismo (transparencia del Observador).
function whoLabel(o) {
  const parts = [];
  if (o.owner_id !== auth.user?.id) parts.push(`de ${o.owner_username}`);
  if (o.created_by_username && o.created_by_username !== o.owner_username) parts.push(`registró ${o.created_by_username}`);
  return parts.join(" · ");
}

function onChanged() {
  load();
}
</script>

<template>
  <div>
    <div class="page-header">
      <p class="page-subtitle">
        Pedidos en su fecha de entrega comprometida.
        <template v-if="auth.isWatcher">Incluye los de los usuarios que observas.</template>
      </p>
    </div>

    <div class="calendar-layout">
      <div class="card calendar-card">
        <!-- Barra superior -->
        <div class="cal-toolbar">
          <div class="cal-nav">
            <button type="button" class="btn btn-secondary btn-sm" @click="goToday">Hoy</button>
            <button type="button" class="btn btn-icon btn-ghost" aria-label="Anterior" @click="move(-1)">
              <Icon name="chevronLeft" :size="20" />
            </button>
            <button type="button" class="btn btn-icon btn-ghost" aria-label="Siguiente" @click="move(1)">
              <Icon name="chevronRight" :size="20" />
            </button>
            <h2 class="cal-title">{{ title }}</h2>
          </div>
          <div class="cal-views" role="tablist" aria-label="Vista del calendario">
            <button
              v-for="v in VIEWS"
              :key="v.key"
              type="button"
              role="tab"
              :aria-selected="view === v.key"
              :class="{ active: view === v.key }"
              @click="view = v.key"
            >
              {{ v.label }}
            </button>
          </div>
        </div>

        <div v-if="error" class="alert alert-danger" style="margin-bottom: 12px">{{ error }}</div>

        <!-- Vista mes -->
        <div v-if="view === 'month'" class="month" :class="{ 'is-loading': loading }">
          <div v-for="w in WEEKDAYS" :key="w" class="month-weekday">{{ w }}</div>
          <div
            v-for="d in days"
            :key="d.getTime()"
            class="month-cell"
            :class="{ 'is-other': !inCurrentMonth(d), 'is-today': isToday(d) }"
          >
            <button type="button" class="day-number" :aria-label="`Ver ${formatDate(toLocalISODate(d))}`" @click="openDay(d)">
              {{ d.getDate() }}
            </button>
            <button
              v-for="o in dayOrders(d).slice(0, MAX_PER_CELL)"
              :key="o.id"
              type="button"
              class="cal-event"
              :class="[statusClass(o.status), { 'is-overdue': isOverdue(o, today) }]"
              :title="`${o.client_name} · ${STATUS_LABELS[o.status]}`"
              @click="openSaleId = o.id"
            >
              <span class="cal-event-text">{{ o.client_name }}</span>
            </button>
            <button
              v-if="dayOrders(d).length > MAX_PER_CELL"
              type="button"
              class="more-link"
              @click="openDay(d)"
            >
              +{{ dayOrders(d).length - MAX_PER_CELL }} más
            </button>
            <!-- En pantallas chicas los nombres no caben: puntos de color por estado. -->
            <button
              v-if="dayOrders(d).length"
              type="button"
              class="cell-dots"
              :aria-label="`${dayOrders(d).length} pedido(s): ver el día`"
              @click="openDay(d)"
            >
              <span
                v-for="o in dayOrders(d).slice(0, 6)"
                :key="o.id"
                class="cell-dot"
                :class="[statusClass(o.status), { 'is-overdue': isOverdue(o, today) }]"
              ></span>
              <span v-if="dayOrders(d).length > 6" class="cell-dots-more">+{{ dayOrders(d).length - 6 }}</span>
            </button>
          </div>
        </div>

        <!-- Vista semana -->
        <div v-else-if="view === 'week'" class="week" :class="{ 'is-loading': loading }">
          <div v-for="d in days" :key="d.getTime()" class="week-col" :class="{ 'is-today': isToday(d) }">
            <button type="button" class="week-head" @click="openDay(d)">
              <span class="week-day-name">{{ WEEKDAYS[(d.getDay() + 6) % 7] }}</span>
              <span class="week-day-number">{{ d.getDate() }}</span>
            </button>
            <div class="week-body">
              <button
                v-for="o in dayOrders(d)"
                :key="o.id"
                type="button"
                class="cal-card"
                :class="[statusClass(o.status), { 'is-overdue': isOverdue(o, today) }]"
                @click="openSaleId = o.id"
              >
                <strong class="cal-card-title">{{ o.client_name }}</strong>
                <span class="cal-card-meta">{{ formatCurrency(o.price) }}</span>
                <span v-if="whoLabel(o)" class="cal-card-meta">{{ whoLabel(o) }}</span>
              </button>
              <p v-if="!dayOrders(d).length" class="week-empty">—</p>
            </div>
          </div>
        </div>

        <!-- Vista día -->
        <div v-else class="day-list" :class="{ 'is-loading': loading }">
          <p v-if="!dayOrders(cursor).length" class="empty-state">No hay pedidos con entrega este día.</p>
          <button
            v-for="o in dayOrders(cursor)"
            :key="o.id"
            type="button"
            class="day-card"
            :class="[statusClass(o.status), { 'is-overdue': isOverdue(o, today) }]"
            @click="openSaleId = o.id"
          >
            <div class="day-card-top">
              <strong>{{ o.client_name }}</strong>
              <span class="mono">{{ formatCurrency(o.price) }}</span>
            </div>
            <div class="day-card-badges">
              <span class="badge" :class="statusClass(o.status)">{{ STATUS_LABELS[o.status] }}</span>
              <span v-if="isOverdue(o, today)" class="badge badge-overdue">Atrasado</span>
            </div>
            <div class="day-card-meta">
              <span v-if="o.buyer_name">Comprador: {{ o.buyer_name }}</span>
              <span>Impresora: {{ o.printer_name }}</span>
              <span>Pedido el {{ formatDate(o.sale_date) }}</span>
              <span v-if="whoLabel(o)">{{ whoLabel(o) }}</span>
            </div>
          </button>
        </div>
      </div>

      <!-- Panel lateral -->
      <aside class="calendar-side">
        <div class="card">
          <h3 class="side-title">Estados</h3>
          <div class="legend">
            <button
              v-for="s in ['pendiente', 'en_produccion', 'lista', 'entregada']"
              :key="s"
              type="button"
              class="legend-item"
              :class="{ off: !visibleStatuses.has(s) }"
              :aria-pressed="visibleStatuses.has(s)"
              @click="toggleStatus(s)"
            >
              <span class="legend-dot" :class="statusClass(s)"></span>
              {{ STATUS_LABELS[s] }}
              <span class="legend-count">{{ counts[s] || 0 }}</span>
            </button>
            <label class="legend-item legend-toggle">
              <input v-model="showCancelled" type="checkbox" style="width: auto" />
              Mostrar cancelados
            </label>
          </div>
          <p class="field-hint" style="margin-top: 8px">Los números cuentan los pedidos de la vista actual.</p>
        </div>

        <div class="card">
          <h3 class="side-title">
            Atrasados
            <span v-if="overdue.length" class="badge badge-overdue">{{ overdue.length }}</span>
          </h3>
          <p v-if="!overdue.length" class="field-hint">No hay pedidos atrasados. 🎉</p>
          <ul v-else class="overdue-list">
            <li v-for="o in overdue" :key="o.id">
              <button type="button" class="overdue-item" @click="openSaleId = o.id">
                <span class="legend-dot" :class="statusClass(o.status)"></span>
                <span class="overdue-text">
                  <strong>{{ o.client_name }}</strong>
                  <span class="text-sm text-muted">
                    Comprometido {{ formatDate(o.promised_delivery_date) }} · hace {{ daysLate(o) }}
                    {{ daysLate(o) === 1 ? "día" : "días" }}
                  </span>
                </span>
              </button>
            </li>
          </ul>
        </div>
      </aside>
    </div>

    <OrderStatusModal v-if="openSaleId" :sale-id="openSaleId" @close="openSaleId = null" @changed="onChanged" />
  </div>
</template>

<style scoped>
.calendar-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 16px;
  align-items: start;
}

.calendar-card {
  padding: 18px;
}

/* ---------- Barra superior ---------- */
.cal-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.cal-nav {
  display: flex;
  align-items: center;
  gap: 4px;
}

.cal-title {
  margin: 0 0 0 8px;
  font-size: 1.2rem;
  font-weight: 700;
}

.cal-views {
  display: inline-flex;
  padding: 3px;
  border-radius: 999px;
  background: var(--surface-alt);
  border: 1px solid var(--border);
}

.cal-views button {
  padding: 6px 14px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
}

.cal-views button.active {
  background: var(--primary);
  color: #fff;
  box-shadow: var(--shadow-sm);
}

.is-loading {
  opacity: 0.55;
  transition: opacity 0.15s;
}

/* ---------- Mes ---------- */
.month {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  border-top: 1px solid var(--border);
  border-left: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.month-weekday {
  padding: 8px 0;
  text-align: center;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
  background: var(--surface-alt);
  border-right: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}

.month-cell {
  min-height: 112px;
  padding: 4px 5px 6px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  border-right: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  min-width: 0;
}

.month-cell.is-other {
  background: var(--surface-alt);
}

.month-cell.is-other .day-number {
  color: var(--text-faint);
}

.day-number {
  align-self: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
}

.day-number:hover {
  background: var(--surface-alt);
}

.month-cell.is-today .day-number {
  background: var(--primary);
  color: #fff;
}

/* Pedido dentro del mes: barra suave con el color del estado a la izquierda. */
.cal-event {
  display: flex;
  align-items: center;
  width: 100%;
  min-width: 0;
  padding: 3px 7px;
  border: none;
  border-left: 3px solid var(--status-color);
  border-radius: 6px;
  color: var(--text);
  font: inherit;
  font-size: 0.76rem;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
}

.cal-event:hover,
.cal-card:hover,
.day-card:hover {
  filter: brightness(0.97);
  box-shadow: var(--shadow-sm);
}

.cal-event-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cal-event.status-entregada,
.cal-card.status-entregada {
  opacity: 0.75;
}

.cal-event.status-cancelado,
.cal-card.status-cancelado,
.day-card.status-cancelado {
  text-decoration: line-through;
}

/* Atrasado: anillo rojo alrededor, sin cambiar el color del estado. */
.is-overdue {
  box-shadow: inset 0 0 0 1.5px var(--danger);
}

.more-link {
  align-self: flex-start;
  padding: 0 4px;
  border: none;
  background: none;
  color: var(--text-muted);
  font: inherit;
  font-size: 0.74rem;
  font-weight: 700;
  cursor: pointer;
}

.more-link:hover {
  color: var(--primary);
}

.cell-dots {
  display: none;
  flex-wrap: wrap;
  justify-content: center;
  gap: 3px;
  padding: 2px 0;
  border: none;
  background: none;
  cursor: pointer;
}

.cell-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: none;
  background: var(--status-color);
}

.cell-dot.is-overdue {
  box-shadow: 0 0 0 1.5px var(--danger);
}

.cell-dots-more {
  font-size: 0.62rem;
  font-weight: 700;
  color: var(--text-muted);
}

/* ---------- Semana ---------- */
.week {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 8px;
}

.week-col {
  display: flex;
  flex-direction: column;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-alt);
  min-height: 320px;
}

.week-head {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 8px 0;
  border: none;
  border-bottom: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  cursor: pointer;
}

.week-day-name {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
}

.week-day-number {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  color: var(--text);
  font-size: 1.05rem;
  font-weight: 700;
}

.week-col.is-today .week-day-number {
  background: var(--primary);
  color: #fff;
}

.week-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
}

.week-empty {
  margin: 8px 0;
  text-align: center;
  color: var(--text-faint);
}

.cal-card {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 7px 8px;
  border: none;
  border-left: 3px solid var(--status-color);
  border-radius: 8px;
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
  min-width: 0;
}

.cal-card-title {
  font-size: 0.8rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cal-card-meta {
  font-size: 0.72rem;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ---------- Día ---------- */
.day-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.day-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-left: 4px solid var(--status-color);
  border-radius: var(--radius-md);
  background: var(--surface);
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.day-card-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 0.95rem;
}

.day-card-badges {
  display: flex;
  gap: 6px;
}

.day-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  font-size: 0.8rem;
  color: var(--text-muted);
}

/* ---------- Panel lateral ---------- */
.calendar-side {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.side-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  font-size: 0.95rem;
}

.legend {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 0.86rem;
  text-align: left;
  cursor: pointer;
}

.legend-item:hover {
  background: var(--surface-alt);
}

.legend-item.off {
  color: var(--text-faint);
}

.legend-item.off .legend-dot {
  opacity: 0.3;
}

.legend-toggle {
  font-weight: 400;
}

.legend-dot {
  flex-shrink: 0;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: none;
  background: var(--status-color);
}

.legend-count {
  margin-left: auto;
  font-size: 0.78rem;
  color: var(--text-muted);
}

.overdue-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 360px;
  overflow-y: auto;
}

.overdue-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
  padding: 7px 8px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.overdue-item:hover {
  background: var(--danger-soft);
}

.overdue-item .legend-dot {
  margin-top: 5px;
}

.overdue-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  font-size: 0.85rem;
}

/* ---------- Responsivo ---------- */
@media (max-width: 1100px) {
  .calendar-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .calendar-card {
    padding: 12px;
  }
  .month-cell {
    min-height: 64px;
    padding: 2px;
  }
  .month-cell .cal-event,
  .month-cell .more-link {
    display: none;
  }
  .cell-dots {
    display: flex;
  }
  .week {
    grid-template-columns: 1fr;
  }
  .week-col {
    min-height: 0;
  }
  .week-head {
    flex-direction: row;
    justify-content: flex-start;
    gap: 8px;
    padding: 6px 10px;
  }
}
</style>
