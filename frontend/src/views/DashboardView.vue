<script setup>
import { ref, reactive, computed, onMounted } from "vue";
import * as dashboardApi from "../api/dashboard";
import * as historyApi from "../api/history";
import * as printersApi from "../api/printers";
import * as salesApi from "../api/sales";
import { sparkPath } from "../utils/motion";
import { PAYMENT_METHODS } from "../api/sales";
import { formatCurrency, formatNumber, formatPercent, currentMonthRange } from "../utils/format";
import { BUSINESS_NAME, BUSINESS_LOGO_URL } from "../utils/business";
import StatCard from "../components/StatCard.vue";
import DoughnutChart from "../components/DoughnutChart.vue";
import SourceBreakdown from "../components/SourceBreakdown.vue";
import Icon from "../components/Icon.vue";
import { useAuthStore } from "../stores/auth";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";

const auth = useAuthStore();

const summary = ref(null);
const byPrinter = ref([]);
const byPayment = ref([]);
const bySource = ref([]);
const stockAlerts = ref([]);
const loading = ref(true);

const filters = reactive(currentMonthRange());

const statusLabels = { disponible: "Disponible", alerta: "Alerta", critico: "Crítico", vacio: "Vacío" };
const statusBadge = { disponible: "badge-success", alerta: "badge-warning", critico: "badge-danger", vacio: "badge-danger" };
const paymentLabel = (v) => PAYMENT_METHODS.find((p) => p.value === v)?.label || v;

/* -------- Contador de transferencias -------- */
const TRANSFER_MAX = 50;
const transferCount = computed(() => {
  const entry = byPayment.value.find((p) => p.payment_method === "transferencia");
  return entry ? entry.jobs : 0;
});
const transferLevel = computed(() => {
  if (transferCount.value > 40) return "danger";
  if (transferCount.value >= 26) return "warning";
  return "success";
});

/* -------- Últimos meses (banner, mini gráficos y barras) --------
   Sale del Historial (pedidos entregados por mes). Los meses sin ventas cuentan como 0. */
const MONTH_SHORT = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const MONTH_LONG = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const history = ref([]);
const recentMonths = computed(() => {
  const byKey = Object.fromEntries(history.value.map((m) => [`${m.year}-${m.month}`, m]));
  const now = new Date();
  return Array.from({ length: 8 }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() - 7 + i, 1);
    const m = byKey[`${d.getFullYear()}-${d.getMonth() + 1}`];
    return {
      key: `${d.getFullYear()}-${d.getMonth()}`,
      short: MONTH_SHORT[d.getMonth()],
      long: MONTH_LONG[d.getMonth()],
      jobs: m ? Number(m.total_jobs) : 0,
      revenue: m ? Number(m.total_revenue) : 0,
      profit: m ? Number(m.total_profit) : 0,
      hours: m ? Number(m.total_print_hours) : 0,
    };
  });
});
const hasHistory = computed(() => recentMonths.value.some((m) => m.jobs > 0));
const spark = (field) => (hasHistory.value ? recentMonths.value.map((m) => m[field]) : null);
const heroLine = computed(() => (hasHistory.value ? sparkPath(spark("profit"), 400, 90) : null));
// Este mes contra el anterior (solo si el anterior tuvo ganancia).
const monthDelta = computed(() => {
  const [prev, cur] = recentMonths.value.slice(-2);
  if (!prev || prev.profit <= 0) return null;
  return { pct: ((cur.profit - prev.profit) / prev.profit) * 100, prevLabel: prev.long };
});
const barMonths = computed(() => recentMonths.value.slice(-6));
const barMax = computed(() => Math.max(...barMonths.value.map((m) => m.profit), 1));
const barHeight = (m) => `${Math.max(0, (m.profit / barMax.value) * 100)}%`;
const barsIn = ref(false);

/* -------- Impresoras: Ocupada si tiene un pedido En producción, si no Libre -------- */
const printers = ref([]);
const printerJobs = ref({});

async function loadExtras() {
  // Complementos visuales: si alguno falla, el resto del Dashboard se muestra igual.
  const [h, p, prod] = await Promise.allSettled([
    historyApi.getMonthlyHistory(),
    printersApi.listPrinters(),
    salesApi.listSales({ status: "en_produccion", limit: 200 }),
  ]);
  history.value = h.status === "fulfilled" ? h.value : [];
  printers.value = p.status === "fulfilled" ? p.value : [];
  const jobs = {};
  if (prod.status === "fulfilled") {
    for (const sale of prod.value.items) {
      (jobs[sale.printer_id] ||= []).push(sale.client_name);
    }
  }
  printerJobs.value = jobs;
  requestAnimationFrame(() => requestAnimationFrame(() => (barsIn.value = true)));
}

async function loadAll() {
  loading.value = true;
  try {
    const params = {};
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;

    // Aparte y tolerante: si falla, el resto del Dashboard se muestra igual.
    const sourcePromise = dashboardApi.getBySource(params).catch(() => []);
    const [s, p, pm, alerts] = await Promise.all([
      dashboardApi.getSummary(params),
      dashboardApi.getByPrinter(params),
      dashboardApi.getByPaymentMethod(params),
      dashboardApi.getStockAlerts(),
    ]);
    summary.value = s;
    byPrinter.value = p;
    byPayment.value = pm;
    stockAlerts.value = alerts;
    bySource.value = (await sourcePromise).map((r) => ({ source: r.sale_source, jobs: r.jobs, revenue: r.revenue }));
  } finally {
    loading.value = false;
  }
}

function applyFilters() {
  loadAll();
}
function resetFilters() {
  Object.assign(filters, currentMonthRange());
  loadAll();
}

onMounted(() => {
  loadAll();
  loadExtras();
});
</script>

<template>
  <div>
    <div class="page-header">
      <div class="flex items-center gap-3">
        <img :src="BUSINESS_LOGO_URL" alt="Logo del negocio" class="dashboard-logo" />
        <div>
          <h1>{{ BUSINESS_NAME }}</h1>
          <p v-if="auth.isWatcher" class="page-subtitle">
            Resumen de los pedidos entregados que registraste con el inventario de los usuarios que observas
          </p>
          <p v-else class="page-subtitle">
            Resumen ejecutivo de tu negocio de impresión 3D (incluye los pedidos que registró un observador con tu
            inventario)
          </p>
          <p class="page-subtitle" style="font-size: 0.8rem">
            Solo cuentan los pedidos <strong>Entregados</strong>, según su fecha de entrega. Los pedidos abiertos aún no
            suman ingresos.
          </p>
        </div>
      </div>
      <div
        v-if="summary"
        class="transfer-chip"
        :class="transferLevel"
        :title="`Transferencias en el período: ${transferCount} de ${TRANSFER_MAX}${transferLevel === 'danger' ? ' — superaste el límite recomendado.' : ''}`"
      >
        Transferencias <strong>{{ transferCount }}/{{ TRANSFER_MAX }}</strong>
      </div>
    </div>

    <section v-if="summary" v-reveal class="hero">
      <div class="hero-ring" aria-hidden="true"></div>
      <div class="hero-grid">
        <div>
          <small>Hola {{ auth.user?.username }} 👋 · Ganancia del período</small>
          <StatCard class="hero-value" label="" :value="formatCurrency(summary.total_profit)" />
          <span v-if="monthDelta" class="hero-delta">
            {{ monthDelta.pct >= 0 ? "▲" : "▼" }} {{ formatNumber(Math.abs(monthDelta.pct), 0) }}% este mes vs
            {{ monthDelta.prevLabel }}
          </span>
        </div>
        <svg v-if="heroLine" class="hero-spark" viewBox="0 0 400 90" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <linearGradient id="heroFill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stop-color="#fff" stop-opacity=".35" />
              <stop offset="1" stop-color="#fff" stop-opacity="0" />
            </linearGradient>
          </defs>
          <path class="hero-area" :d="`${heroLine.d} L400,90 L0,90Z`" fill="url(#heroFill)" />
          <path class="draw-line" pathLength="1" :d="heroLine.d" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" />
          <circle class="hero-halo" :cx="heroLine.last[0]" :cy="heroLine.last[1]" r="6" fill="#fff" />
          <circle class="hero-dot" :cx="heroLine.last[0]" :cy="heroLine.last[1]" r="6" fill="#fff" />
        </svg>
      </div>
    </section>

    <div class="card" style="margin-bottom: 20px">
      <div class="flex gap-3" style="align-items: flex-end; flex-wrap: wrap">
        <div class="field" style="max-width: 200px">
          <label>Desde</label>
          <input v-model="filters.date_from" type="date" />
        </div>
        <div class="field" style="max-width: 200px">
          <label>Hasta</label>
          <input v-model="filters.date_to" type="date" />
        </div>
        <button class="btn btn-primary" @click="applyFilters">Filtrar</button>
        <button class="btn btn-secondary" @click="resetFilters">Limpiar</button>
      </div>
    </div>

    <LoadingSkeleton v-if="loading && !summary" />

    <template v-else-if="summary">
      <div class="grid grid-cols-4 stats-grid" style="margin-bottom: 20px">
        <StatCard label="Trabajos" :value="formatNumber(summary.total_jobs, 0)" :spark="spark('jobs')" />
        <StatCard label="Ingresos" :value="formatCurrency(summary.total_revenue)" :spark="spark('revenue')" color="var(--accent)" />
        <StatCard label="Ganancia" :value="formatCurrency(summary.total_profit)" :spark="spark('profit')" color="var(--success)" />
        <StatCard
          label="Margen promedio"
          :value="formatPercent(summary.avg_margin_percent)"
          :ring="Number(summary.avg_margin_percent)"
          color="var(--warning)"
        />
        <StatCard label="Costo total" :value="formatCurrency(summary.total_cost)" />
        <StatCard label="Horas impresas" :value="formatNumber(summary.total_print_hours, 1)" :spark="spark('hours')" color="var(--info)" />
        <StatCard label="Filamento usado" :value="`${formatNumber(summary.total_filament_used_g, 0)} g`" />
        <StatCard label="Luz gastada" :value="formatCurrency(summary.total_energy)" />
        <!-- Pedidos todavía sin entregar (hoy, no dependen del período). -->
        <StatCard label="Pedidos abiertos" :value="formatNumber(summary.open_orders, 0)" />
        <!-- Cancelaciones sin pieza al Almacén + piezas descartadas, en el período. -->
        <StatCard label="Pérdidas (cancelaciones y descartes)" :value="formatCurrency(summary.total_losses)" />
        <!-- Costo de las piezas En almacén y Reservadas (hoy). -->
        <StatCard label="Valor en Almacén" :value="formatCurrency(summary.warehouse_value)" />
      </div>

      <div class="grid" :class="printers.length ? 'grid-cols-2' : ''" style="margin-bottom: 20px; align-items: start">
        <div v-reveal class="card glow">
          <div class="card-header">
            <h3>Ganancia mensual</h3>
            <span class="text-muted text-sm">Últimos 6 meses · pedidos entregados</span>
          </div>
          <div class="bars" :class="{ in: barsIn }">
            <div v-for="(m, i) in barMonths" :key="m.key" class="bar-col">
              <div
                class="bar"
                :class="{ cur: i === barMonths.length - 1 }"
                :style="{ height: barHeight(m), '--bar-delay': `${0.15 + i * 0.08}s` }"
                :title="`${m.long}: ${formatCurrency(m.profit)}`"
              ></div>
              <span class="bar-label">{{ m.short }}</span>
            </div>
          </div>
        </div>

        <div v-if="printers.length" v-reveal="0.08" class="card glow">
          <div class="card-header">
            <h3>Impresoras</h3>
            <span class="text-muted text-sm">Ocupada = tiene un pedido En producción</span>
          </div>
          <div class="printer-list">
            <div v-for="p in printers" :key="p.id" class="printer-row" :class="{ busy: printerJobs[p.id] }">
              <div class="printer-icon"><Icon name="printer" :size="20" /></div>
              <div class="printer-meta">
                <strong>{{ p.name }}</strong>
                <span v-if="printerJobs[p.id]" class="text-muted text-sm">
                  {{ printerJobs[p.id][0] }}<template v-if="printerJobs[p.id].length > 1"> y {{ printerJobs[p.id].length - 1 }} más</template>
                </span>
              </div>
              <span class="badge" :class="printerJobs[p.id] ? 'badge-info' : 'badge-success'">
                {{ printerJobs[p.id] ? "Ocupada" : "Libre" }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-2" style="margin-bottom: 20px; align-items: start">
        <div v-reveal class="card glow">
          <div class="card-header">
            <h3>Por impresora</h3>
          </div>
          <div v-if="!byPrinter.length" class="empty-state">Sin datos en este rango.</div>
          <div v-else class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Impresora</th>
                  <th class="text-right">Trabajos</th>
                  <th class="text-right">Horas</th>
                  <th class="text-right">Ingresos</th>
                  <th class="text-right">Margen</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in byPrinter" :key="p.printer_id">
                  <td>{{ p.printer_name }}</td>
                  <td class="text-right mono">{{ p.jobs }}</td>
                  <td class="text-right mono">{{ formatNumber(p.hours, 1) }}</td>
                  <td class="text-right mono">{{ formatCurrency(p.revenue) }}</td>
                  <td class="text-right">{{ formatPercent(p.margin_percent) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-reveal="0.08" class="card glow">
          <div class="card-header">
            <h3>Por método de pago</h3>
          </div>
          <div v-if="!byPayment.length" class="empty-state">Sin datos en este rango.</div>
          <div v-else class="grid grid-cols-2" style="align-items: center">
            <DoughnutChart :labels="byPayment.map((p) => paymentLabel(p.payment_method))" :values="byPayment.map((p) => Number(p.revenue))" center-label="Ingresos" />
            <table style="min-width: unset">
              <tbody>
                <tr v-for="p in byPayment" :key="p.payment_method">
                  <td>{{ paymentLabel(p.payment_method) }}</td>
                  <td class="text-right mono">{{ formatCurrency(p.revenue) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div v-reveal class="card glow" style="margin-bottom: 20px">
        <div class="card-header">
          <h3>Ventas por fuente</h3>
          <span class="text-muted text-sm">De dónde llegaron los pedidos entregados del período</span>
        </div>
        <SourceBreakdown :items="bySource" />
      </div>

      <div v-if="!auth.isWatcher" v-reveal class="card">
        <div class="card-header">
          <h3>Alertas de stock de filamento</h3>
        </div>
        <div v-if="!stockAlerts.length" class="empty-state">Sin filamentos registrados.</div>
        <div v-else class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Filamento</th>
                <th class="text-right">Disponible</th>
                <th class="text-right">% stock</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="f in stockAlerts" :key="f.filament_id">
                <td>
                  {{ f.brand }} · {{ f.color }} <span class="text-muted text-sm">({{ f.type }})</span>
                  <span v-if="f.sku" class="badge badge-neutral" style="margin-left: 6px">{{ f.sku }}</span>
                </td>
                <td class="text-right mono">{{ formatNumber(f.available_g, 0) }} g</td>
                <td class="text-right mono">
                  <div class="stock-cell">
                    <span class="stock-meter" :class="f.status">
                      <i :style="{ width: `${Math.min(100, Math.max(0, Number(f.stock_percent)))}%` }"></i>
                    </span>
                    {{ formatPercent(f.stock_percent) }}
                  </div>
                </td>
                <td>
                  <span class="badge" :class="statusBadge[f.status]">
                    <Icon v-if="f.status !== 'disponible'" name="alert" :size="11" />
                    {{ statusLabels[f.status] }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* ---------- Medidor de stock: se llena cuando la tarjeta aparece ---------- */
.stock-cell {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}
.stock-meter {
  width: 70px;
  height: 7px;
  border-radius: 999px;
  background: var(--surface-alt);
  overflow: hidden;
}
.stock-meter i {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--success);
  transform-origin: left;
  transition: transform 1s var(--ease-out) 0.3s;
}
.stock-meter.alerta i {
  background: var(--warning);
}
.stock-meter.critico i,
.stock-meter.vacio i {
  background: var(--danger);
}
.reveal:not(.in) .stock-meter i {
  transform: scaleX(0);
}

/* ---------- Banner de ganancia ---------- */
.hero {
  position: relative;
  overflow: hidden;
  margin-bottom: 20px;
  padding: 24px 26px;
  border-radius: var(--radius-lg);
  color: #fff;
  background: linear-gradient(120deg, #4b3be0, #6a4cf0 40%, #1aa596);
  background-size: 200% 200%;
  animation: hero-shift 12s ease-in-out infinite;
  box-shadow: 0 18px 40px rgba(91, 75, 245, 0.28);
}
@keyframes hero-shift {
  50% { background-position: 100% 50%; }
}
.hero::before {
  content: "";
  position: absolute;
  inset: 0;
  background-image: radial-gradient(rgba(255, 255, 255, 0.18) 1px, transparent 1px);
  background-size: 18px 18px;
  mask-image: linear-gradient(90deg, transparent, #000 60%);
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 60%);
}
.hero-ring {
  position: absolute;
  right: -60px;
  top: -60px;
  width: 260px;
  height: 260px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.18);
  animation: hero-spin 30s linear infinite;
}
.hero-ring::after {
  content: "";
  position: absolute;
  top: 50%;
  left: -7px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 0 18px #fff;
}
@keyframes hero-spin {
  to { transform: rotate(360deg); }
}
.hero-grid {
  position: relative;
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 20px;
  align-items: end;
}
.hero small {
  font-size: 0.85rem;
  opacity: 0.85;
}
/* Reusa el contador de StatCard, sin su caja */
.hero-value.stat-card {
  padding: 0;
  margin: 4px 0 8px;
  background: none;
  border: 0;
  box-shadow: none;
  animation: none;
  transform: none;
}
.hero-value.stat-card::before,
.hero-value :deep(.stat-label) {
  display: none;
}
.hero-value :deep(.stat-value) {
  font-size: 2.4rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  line-height: 1.1;
  color: #fff;
}
.hero-delta {
  display: inline-flex;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.18);
  font-size: 0.8rem;
  font-weight: 700;
}
.hero-spark {
  width: 100%;
  height: 90px;
  overflow: visible;
}
.hero-area {
  opacity: 0;
  animation: hero-fade 1s ease 1.1s forwards;
}
@keyframes hero-fade {
  to { opacity: 1; }
}
.hero-dot,
.hero-halo {
  transform-box: fill-box;
  transform-origin: center;
}
.hero-dot {
  opacity: 0;
  animation: zola-pop-in 0.5s var(--ease-spring) 1.7s forwards;
}
.hero-halo {
  opacity: 0;
  animation: hero-halo 2s ease-out 2s infinite;
}
@keyframes hero-halo {
  from { opacity: 0.7; transform: scale(1); }
  to { opacity: 0; transform: scale(3); }
}

/* ---------- Ganancia mensual (barras que crecen) ---------- */
.bars {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  height: 200px;
  padding-top: 24px;
}
.bar-col {
  flex: 1;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}
.bar {
  width: 100%;
  max-width: 40px;
  min-height: 3px;
  border-radius: 9px 9px 4px 4px;
  background: linear-gradient(to top, var(--primary), color-mix(in srgb, var(--primary) 55%, #fff));
  transform: scaleY(0);
  transform-origin: bottom;
  transition: transform 0.9s var(--ease-spring) var(--bar-delay, 0s);
}
.bar.cur {
  background: linear-gradient(to top, var(--accent), color-mix(in srgb, var(--accent) 55%, #fff));
  box-shadow: 0 8px 20px color-mix(in srgb, var(--accent) 35%, transparent);
}
.bars.in .bar {
  transform: scaleY(1);
}
.bar-label {
  font-size: 0.75rem;
  color: var(--text-muted);
}

/* ---------- Impresoras ---------- */
.printer-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.printer-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.printer-icon {
  position: relative;
  width: 42px;
  height: 42px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 12px;
  background: var(--primary-soft);
  color: var(--primary);
}
.printer-row.busy .printer-icon::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: 12px;
  border: 2px solid var(--info);
  animation: zola-ping 1.8s var(--ease-out) infinite;
}
.printer-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.printer-meta span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 640px) {
  .hero {
    padding: 18px;
  }
  .hero-grid {
    grid-template-columns: 1fr;
    gap: 6px;
  }
  .hero-value :deep(.stat-value) {
    font-size: 2rem;
  }
  .hero-spark {
    height: 64px;
  }
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
  }
  .stats-grid :deep(.stat-value) {
    font-size: 1.2rem;
  }
  .bars {
    height: 160px;
    gap: 8px;
  }
}

.dashboard-logo {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  object-fit: contain;
  border: 1px solid var(--border);
  background: var(--surface);
  flex-shrink: 0;
}

.transfer-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
  cursor: default;
}

.transfer-chip strong {
  font-weight: 800;
}

.transfer-chip.success {
  background: var(--success-soft);
  color: var(--success);
}

.transfer-chip.warning {
  background: var(--warning-soft);
  color: var(--warning);
}

.transfer-chip.danger {
  background: var(--danger-soft);
  color: var(--danger);
}
</style>
