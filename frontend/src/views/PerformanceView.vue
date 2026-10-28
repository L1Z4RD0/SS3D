<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { getPerformance } from "../api/performance";
import { formatCurrency, formatNumber, formatPercent, toLocalISODate } from "../utils/format";
import { extractApiError } from "../utils/validation";
import StatCard from "../components/StatCard.vue";
import DoughnutChart from "../components/DoughnutChart.vue";
import MonthlyTrendChart from "../components/MonthlyTrendChart.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import Icon from "../components/Icon.vue";

/* Rendimiento por cuenta (solo la cuenta Empresa). Ingresos, ganancia y pedidos: de la cuenta
   que REGISTRÓ la venta. Costos, horas y filamento: de quien puso cada recurso (impresora,
   filamento, insumos). "Todas juntas" cuenta cada venta una sola vez. */
const ACCOUNT_COLORS = ["#5b4bf5", "#17b3a3", "#f0ad4e", "#d7473f", "#3567d6"];
const MONTHS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const ALL = "todas";

const data = ref(null);
const loading = ref(true);
const error = ref("");

/* -------- Período -------- */
function monthRange(offsetStart, offsetEnd = 0) {
  const now = new Date();
  return {
    date_from: toLocalISODate(new Date(now.getFullYear(), now.getMonth() - offsetStart, 1)),
    date_to: toLocalISODate(new Date(now.getFullYear(), now.getMonth() - offsetEnd + 1, 0)),
  };
}
const PRESETS = [
  { key: "mes", label: "Este mes", range: () => monthRange(0) },
  { key: "anterior", label: "Mes anterior", range: () => monthRange(1, 1) },
  { key: "tres", label: "Últimos 3 meses", range: () => monthRange(2) },
  { key: "anio", label: "Este año", range: () => ({ date_from: `${new Date().getFullYear()}-01-01`, date_to: monthRange(0).date_to }) },
  { key: "todo", label: "Todo", range: () => ({ date_from: "", date_to: "" }) },
];
const preset = ref("tres");
const period = reactive(PRESETS[2].range());
function choosePreset(p) {
  preset.value = p.key;
  Object.assign(period, p.range());
  load();
}
function applyCustom() {
  preset.value = "";
  load();
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const params = {};
    if (period.date_from) params.date_from = period.date_from;
    if (period.date_to) params.date_to = period.date_to;
    data.value = await getPerformance(params);
  } catch (err) {
    error.value = extractApiError(err, "No se pudo calcular el rendimiento.");
  } finally {
    loading.value = false;
  }
}
onMounted(load);

/* -------- Cuentas -------- */
const accounts = computed(() =>
  (data.value?.accounts || []).map((a, i) => ({ ...a, color: ACCOUNT_COLORS[i % ACCOUNT_COLORS.length] }))
);
const selected = ref(ALL);
const tabs = computed(() => [
  ...accounts.value.map((a) => ({ key: a.user_id, label: a.username, color: a.color })),
  { key: ALL, label: "Todas juntas", color: "var(--primary)" },
]);
const current = computed(() => accounts.value.find((a) => a.user_id === selected.value) || null);

// Píldora que se desliza bajo la cuenta elegida.
const tabsEl = ref(null);
// Sigue también la fila: en el celular las cuentas pueden ocupar dos líneas.
const pill = ref({ left: 0, top: 0, width: 0, height: 0, visible: false });
function movePill() {
  const btn = tabsEl.value?.querySelector("button.on");
  pill.value = btn
    ? { left: btn.offsetLeft, top: btn.offsetTop, width: btn.offsetWidth, height: btn.offsetHeight, visible: true }
    : { ...pill.value, visible: false };
}
watch([selected, () => tabs.value.length], () => nextTick(movePill));

/* -------- Series mensuales -------- */
const months = computed(() => data.value?.months || []);
const monthLabels = computed(() =>
  months.value.map((m) => {
    const [y, mo] = m.month.split("-").map(Number);
    return `${MONTHS[mo - 1]} ${String(y).slice(2)}`;
  })
);
const seriesFor = (field) =>
  months.value.length >= 2
    ? months.value.map((m) => Number(selected.value === ALL ? m.combined[field] : m.accounts[selected.value]?.[field] || 0))
    : null;

const view = computed(() => {
  if (!data.value) return null;
  if (current.value) {
    const r = current.value.registered;
    return { jobs: r.jobs, revenue: r.revenue, profit: r.profit, margin: r.margin_percent };
  }
  const c = data.value.combined;
  return { jobs: c.jobs, revenue: c.revenue, profit: c.profit, margin: c.margin_percent };
});

/* -------- Costos de los recursos -------- */
const COST_PARTS = [
  { key: "machine", label: "Máquina (depreciación + luz)" },
  { key: "material", label: "Material (filamento)" },
  { key: "supplies", label: "Insumos" },
];
const costBars = computed(() => {
  const own = current.value?.own_costs;
  if (!own) return [];
  const max = Math.max(1, ...COST_PARTS.map((p) => Number(own[p.key])));
  return COST_PARTS.map((p) => ({ ...p, value: Number(own[p.key]), width: (Number(own[p.key]) / max) * 100 }));
});

/* -------- Comparación -------- */
const METRICS = [
  { key: "revenue", label: "Ingresos", format: formatCurrency },
  { key: "profit", label: "Ganancia", format: formatCurrency },
  { key: "own_cost", label: "Costos propios", format: formatCurrency },
  { key: "jobs", label: "Pedidos", format: (v) => `${Math.round(v)}` },
];
const metric = ref("revenue");
const metricInfo = computed(() => METRICS.find((m) => m.key === metric.value));
const compareSeries = computed(() =>
  accounts.value.map((a) => ({
    name: a.username,
    data: months.value.map((m) => Number(m.accounts[a.user_id]?.[metric.value] || 0)),
  }))
);

const rangeLabel = computed(() => {
  if (!period.date_from && !period.date_to) return "todo el historial";
  const f = (d) => (d ? d.split("-").reverse().join("-") : "…");
  return `del ${f(period.date_from)} al ${f(period.date_to)}`;
});
</script>

<template>
  <div>
    <div class="page-header">
      <p class="page-subtitle">
        Diego, Sntg y la Empresa por separado y todas juntas. <strong>Ingresos y ganancia</strong>: de la cuenta que
        registró cada venta. <strong>Costos</strong>: de quien puso cada recurso (impresora, filamento, insumos).
      </p>
    </div>

    <div class="card perf-controls">
      <div class="preset-row">
        <button
          v-for="p in PRESETS"
          :key="p.key"
          type="button"
          class="month-chip"
          :class="{ selected: preset === p.key }"
          @click="choosePreset(p)"
        >
          {{ p.label }}
        </button>
      </div>
      <div class="custom-range">
        <label>Desde <input v-model="period.date_from" type="date" @change="applyCustom" /></label>
        <label>Hasta <input v-model="period.date_to" type="date" @change="applyCustom" /></label>
        <span class="text-muted text-sm">Pedidos entregados {{ rangeLabel }}</span>
      </div>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="loading && !data" class="card"><LoadingSkeleton :lines="6" /></div>

    <template v-if="data">
      <div ref="tabsEl" class="account-tabs" role="tablist" aria-label="Cuenta">
        <span
          class="account-pill"
          :class="{ visible: pill.visible }"
          :style="{ transform: `translate(${pill.left}px, ${pill.top}px)`, width: `${pill.width}px`, height: `${pill.height}px` }"
          aria-hidden="true"
        ></span>
        <button
          v-for="t in tabs"
          :key="t.key"
          type="button"
          role="tab"
          :class="{ on: selected === t.key }"
          :aria-selected="selected === t.key"
          @click="selected = t.key"
        >
          <i :style="{ background: t.color }"></i>{{ t.label }}
        </button>
      </div>

      <div class="grid grid-cols-4" style="margin-bottom: 20px">
        <StatCard
          :label="current ? 'Pedidos que registró' : 'Pedidos'"
          :value="formatNumber(view.jobs, 0)"
          :spark="seriesFor('jobs')"
        />
        <StatCard
          :label="current ? 'Ingresos de sus ventas' : 'Ingresos'"
          :value="formatCurrency(view.revenue)"
          :spark="seriesFor('revenue')"
          color="var(--accent)"
        />
        <StatCard
          :label="current ? 'Ganancia de sus ventas' : 'Ganancia'"
          :value="formatCurrency(view.profit)"
          :spark="seriesFor('profit')"
          color="var(--success)"
        />
        <StatCard label="Margen" :value="formatPercent(view.margin)" :ring="Number(view.margin)" color="var(--warning)" />
      </div>

      <!-- Una cuenta: sus costos propios. -->
      <div v-if="current" v-reveal class="card glow" style="margin-bottom: 20px">
        <div class="card-header">
          <h3>Costos de sus recursos</h3>
          <span class="text-muted text-sm">Lo que pusieron sus impresoras, filamentos e insumos, en cualquier venta</span>
        </div>
        <div class="own-costs">
          <div class="own-total">
            <span class="text-muted text-sm">Total</span>
            <strong class="mono">{{ formatCurrency(current.own_costs.total) }}</strong>
            <span class="text-muted text-sm">en {{ current.own_costs.sales_with_resources }} pedido(s)</span>
            <div class="own-usage">
              <span><Icon name="printer" :size="15" /> {{ formatNumber(current.own_costs.print_hours, 1) }} h en sus impresoras</span>
              <span><Icon name="spool" :size="15" /> {{ formatNumber(current.own_costs.filament_g, 0) }} g de su filamento</span>
            </div>
          </div>
          <ul class="cost-bars">
            <li v-for="(b, i) in costBars" :key="b.key" :style="{ '--d': `${0.1 + i * 0.1}s`, '--c': current.color }">
              <div class="cost-bar-head">
                <span>{{ b.label }}</span>
                <strong class="mono">{{ formatCurrency(b.value) }}</strong>
              </div>
              <div class="cost-track"><div class="cost-fill" :style="{ width: `${b.width}%` }"></div></div>
            </li>
          </ul>
        </div>
        <p class="rule-note">
          Las ventas que registró otra cuenta con recursos de {{ current.username }} suman aquí sus costos (máquina,
          material o insumos), pero sus ingresos quedan en la cuenta que las registró.
        </p>
      </div>

      <!-- Todas juntas: costo total, uso y de quién son los costos. -->
      <div v-else v-reveal class="grid grid-cols-2" style="margin-bottom: 20px; align-items: start">
        <div class="card glow">
          <div class="card-header">
            <h3>Todas juntas</h3>
            <span class="text-muted text-sm">Cada venta se cuenta una sola vez</span>
          </div>
          <dl class="combined-list">
            <div><dt>Costo total</dt><dd class="mono">{{ formatCurrency(data.combined.cost) }}</dd></div>
            <div><dt>Horas de impresión</dt><dd class="mono">{{ formatNumber(data.combined.print_hours, 1) }} h</dd></div>
            <div><dt>Filamento usado</dt><dd class="mono">{{ formatNumber(data.combined.filament_g, 0) }} g</dd></div>
            <div>
              <dt>Postprocesado y delivery</dt>
              <dd class="mono">{{ formatCurrency(data.combined.shared_cost) }}</dd>
            </div>
            <div>
              <dt>Ventas que usaron recursos de otra cuenta</dt>
              <dd class="mono">{{ data.combined.mixed_sales }}</dd>
            </div>
          </dl>
        </div>
        <div class="card glow">
          <div class="card-header">
            <h3>De quién son los costos</h3>
            <span class="text-muted text-sm">Máquina + material + insumos de cada cuenta</span>
          </div>
          <DoughnutChart
            :labels="accounts.map((a) => a.username)"
            :values="accounts.map((a) => Number(a.own_costs.total))"
            :colors="accounts.map((a) => a.color)"
            center-label="Costos propios"
          />
        </div>
      </div>

      <div v-reveal class="card glow" style="margin-bottom: 20px">
        <div class="card-header">
          <h3>Comparación por cuenta</h3>
          <div class="metric-toggle" role="tablist" aria-label="Qué comparar">
            <button
              v-for="m in METRICS"
              :key="m.key"
              type="button"
              :class="{ on: metric === m.key }"
              @click="metric = m.key"
            >
              {{ m.label }}
            </button>
          </div>
        </div>
        <div v-if="!months.length" class="empty-state">Sin pedidos entregados en este período.</div>
        <!-- :key: al cambiar lo que se compara el gráfico se crea de nuevo (y conserva el formato $). -->
        <MonthlyTrendChart
          v-else
          :key="metric"
          type="bar"
          :categories="monthLabels"
          :series="compareSeries"
          :colors="accounts.map((a) => a.color)"
          :value-formatter="metricInfo.format"
        />
        <div class="table-wrap mt-2">
          <table>
            <thead>
              <tr>
                <th>Cuenta</th>
                <th class="text-right">Pedidos</th>
                <th class="text-right">Ingresos</th>
                <th class="text-right">Ganancia</th>
                <th class="text-right">Margen</th>
                <th class="text-right">Costos propios</th>
                <th class="text-right">Horas</th>
                <th class="text-right">Filamento</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="a in accounts" :key="a.user_id" :class="{ 'row-selected': selected === a.user_id }" @click="selected = a.user_id">
                <td><i class="dot" :style="{ background: a.color }"></i><strong>{{ a.username }}</strong></td>
                <td class="text-right mono">{{ a.registered.jobs }}</td>
                <td class="text-right mono">{{ formatCurrency(a.registered.revenue) }}</td>
                <td class="text-right mono" style="color: var(--success)">{{ formatCurrency(a.registered.profit) }}</td>
                <td class="text-right">{{ formatPercent(a.registered.margin_percent) }}</td>
                <td class="text-right mono">{{ formatCurrency(a.own_costs.total) }}</td>
                <td class="text-right mono">{{ formatNumber(a.own_costs.print_hours, 1) }}</td>
                <td class="text-right mono">{{ formatNumber(a.own_costs.filament_g, 0) }} g</td>
              </tr>
              <tr class="row-total" :class="{ 'row-selected': selected === ALL }" @click="selected = ALL">
                <td><strong>Todas juntas</strong></td>
                <td class="text-right mono">{{ data.combined.jobs }}</td>
                <td class="text-right mono">{{ formatCurrency(data.combined.revenue) }}</td>
                <td class="text-right mono" style="color: var(--success)">{{ formatCurrency(data.combined.profit) }}</td>
                <td class="text-right">{{ formatPercent(data.combined.margin_percent) }}</td>
                <td class="text-right mono">{{ formatCurrency(accounts.reduce((s, a) => s + Number(a.own_costs.total), 0)) }}</td>
                <td class="text-right mono">{{ formatNumber(data.combined.print_hours, 1) }}</td>
                <td class="text-right mono">{{ formatNumber(data.combined.filament_g, 0) }} g</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="rule-note">
          Ingresos, ganancia y pedidos son de la cuenta que registró la venta; costos propios, horas y filamento, de
          quien puso cada recurso. Por eso una venta de la Empresa hecha con la impresora de un socio suma sus ingresos a
          la Empresa y el costo de la máquina al socio. Solo pedidos Entregados, por su fecha de entrega.
        </p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.perf-controls {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}

.preset-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.month-chip {
  padding: 7px 13px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface-alt);
  color: var(--text);
  font: inherit;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.month-chip.selected {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
}

.custom-range {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}
.custom-range label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: 0.85rem;
  font-weight: 600;
}
.custom-range input {
  width: auto;
}

/* Selector de cuenta con píldora deslizante. */
.account-tabs {
  position: relative;
  display: inline-flex;
  flex-wrap: wrap;
  gap: 2px;
  max-width: 100%;
  margin-bottom: 16px;
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface);
}
.account-tabs button {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 16px;
  border: 0;
  border-radius: 999px;
  background: none;
  color: var(--text-muted);
  font: inherit;
  font-size: 0.88rem;
  font-weight: 700;
  cursor: pointer;
  transition: color 0.25s;
}
.account-tabs button.on {
  color: #fff;
}
.account-tabs i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}
.account-tabs button.on i {
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.85);
}
.account-pill {
  position: absolute;
  top: 0;
  left: 0;
  border-radius: 999px;
  background: linear-gradient(135deg, var(--primary), color-mix(in srgb, var(--primary) 70%, #a855f7));
  opacity: 0;
  transition: transform 0.45s var(--ease-spring), width 0.45s var(--ease-spring), opacity 0.2s;
}
.account-pill.visible {
  opacity: 1;
}

/* Costos de una cuenta. */
.own-costs {
  display: grid;
  grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.2fr);
  gap: 24px;
  align-items: center;
}
.own-total {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.own-total strong {
  font-size: 1.7rem;
}
.own-usage {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
  font-size: 0.85rem;
}
.own-usage span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.cost-bars {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.cost-bar-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 0.88rem;
}
.cost-track {
  height: 10px;
  margin-top: 6px;
  border-radius: 999px;
  background: var(--surface-alt);
  overflow: hidden;
}
.cost-fill {
  height: 100%;
  border-radius: 999px;
  background: var(--c);
  transform-origin: left;
  animation: cost-grow 0.9s var(--ease-out) var(--d) both;
}
@keyframes cost-grow {
  from {
    transform: scaleX(0);
  }
}

.combined-list {
  display: flex;
  flex-direction: column;
  margin: 0;
}
.combined-list div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 0;
  border-bottom: 1px solid var(--border);
  font-size: 0.9rem;
}
.combined-list div:last-child {
  border-bottom: none;
}
.combined-list dt {
  color: var(--text-muted);
}
.combined-list dd {
  margin: 0;
  font-weight: 700;
}

.metric-toggle {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
}
.metric-toggle button {
  padding: 5px 11px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface-alt);
  color: var(--text);
  font: inherit;
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
}
.metric-toggle button.on {
  border-color: var(--primary);
  background: var(--primary-soft);
  color: var(--primary);
}

.dot {
  display: inline-block;
  width: 9px;
  height: 9px;
  margin-right: 8px;
  border-radius: 50%;
}
tbody tr {
  cursor: pointer;
}
.row-selected td {
  background: var(--primary-soft);
}
.row-total td {
  border-top: 2px solid var(--border);
}

.rule-note {
  margin: 14px 0 0;
  color: var(--text-muted);
  font-size: 0.82rem;
  line-height: 1.5;
}

@media (max-width: 640px) {
  .own-costs {
    grid-template-columns: 1fr;
  }
  .account-tabs {
    border-radius: 18px;
  }
  .account-tabs button {
    padding: 7px 12px;
    font-size: 0.82rem;
  }
}
</style>
