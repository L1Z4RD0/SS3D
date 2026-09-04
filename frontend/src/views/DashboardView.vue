<script setup>
import { ref, reactive, computed, onMounted } from "vue";
import * as dashboardApi from "../api/dashboard";
import * as businessProfileApi from "../api/businessProfile";
import { PAYMENT_METHODS } from "../api/sales";
import { formatCurrency, formatNumber, formatPercent, currentMonthRange } from "../utils/format";
import StatCard from "../components/StatCard.vue";
import DoughnutChart from "../components/DoughnutChart.vue";
import Icon from "../components/Icon.vue";

const summary = ref(null);
const byPrinter = ref([]);
const byPayment = ref([]);
const stockAlerts = ref([]);
const loading = ref(true);
const businessProfile = ref({ business_name: "", logo_data_url: "" });

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
const transferGaugePercent = computed(() => Math.min(100, (transferCount.value / TRANSFER_MAX) * 100));

async function loadAll() {
  loading.value = true;
  try {
    const params = {};
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;

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

onMounted(async () => {
  loadAll();
  businessProfile.value = await businessProfileApi.getBusinessProfile();
});
</script>

<template>
  <div>
    <div class="page-header">
      <div class="flex items-center gap-3">
        <img v-if="businessProfile.logo_data_url" :src="businessProfile.logo_data_url" alt="Logo del negocio" class="dashboard-logo" />
        <div v-else class="dashboard-logo dashboard-logo-placeholder">
          <Icon name="image" :size="20" />
        </div>
        <div>
          <h1 v-if="businessProfile.business_name">{{ businessProfile.business_name }}</h1>
          <p class="page-subtitle">Resumen ejecutivo de tu negocio de impresión 3D</p>
        </div>
      </div>
    </div>

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

    <div v-if="loading" class="empty-state">Cargando...</div>

    <template v-else-if="summary">
      <div class="grid grid-cols-4" style="margin-bottom: 20px">
        <StatCard label="Trabajos" :value="formatNumber(summary.total_jobs, 0)" />
        <StatCard label="Ingresos" :value="formatCurrency(summary.total_revenue)" />
        <StatCard label="Ganancia" :value="formatCurrency(summary.total_profit)" />
        <StatCard label="Margen promedio" :value="formatPercent(summary.avg_margin_percent)" />
        <StatCard label="Costo total" :value="formatCurrency(summary.total_cost)" />
        <StatCard label="IVA cobrado" :value="formatCurrency(summary.total_iva)" />
        <StatCard label="Horas impresas" :value="formatNumber(summary.total_print_hours, 1)" />
        <StatCard label="Filamento usado" :value="`${formatNumber(summary.total_filament_used_g, 0)} g`" />
      </div>

      <div class="card" style="margin-bottom: 20px">
        <div class="card-header">
          <h3>Contador de transferencias</h3>
          <span class="badge" :class="`badge-${transferLevel}`">{{ transferCount }} / {{ TRANSFER_MAX }}</span>
        </div>
        <div class="transfer-gauge-track">
          <div class="transfer-gauge-fill" :class="transferLevel" :style="{ width: transferGaugePercent + '%' }"></div>
        </div>
        <div v-if="transferLevel === 'danger'" class="alert alert-danger mt-4">
          <Icon name="alert" :size="16" />
          <span>Atención: superaste 40 transferencias en el período mostrado.</span>
        </div>
      </div>

      <div class="grid grid-cols-2" style="margin-bottom: 20px; align-items: start">
        <div class="card">
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

        <div class="card">
          <div class="card-header">
            <h3>Por método de pago</h3>
          </div>
          <div v-if="!byPayment.length" class="empty-state">Sin datos en este rango.</div>
          <div v-else class="grid grid-cols-2" style="align-items: center">
            <DoughnutChart :labels="byPayment.map((p) => paymentLabel(p.payment_method))" :values="byPayment.map((p) => Number(p.revenue))" />
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

      <div class="card">
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
                <td class="text-right mono">{{ formatPercent(f.stock_percent) }}</td>
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
.dashboard-logo {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  object-fit: contain;
  border: 1px solid var(--border);
  background: var(--surface);
  flex-shrink: 0;
}

.dashboard-logo-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--surface-alt);
  color: var(--text-faint);
}

.transfer-gauge-track {
  height: 14px;
  border-radius: 999px;
  background: var(--surface-alt);
  overflow: hidden;
}

.transfer-gauge-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.3s ease;
}

.transfer-gauge-fill.success {
  background: var(--success);
}

.transfer-gauge-fill.warning {
  background: var(--warning);
}

.transfer-gauge-fill.danger {
  background: var(--danger);
}
</style>
