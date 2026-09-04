<script setup>
import { ref, reactive, onMounted } from "vue";
import * as dashboardApi from "../api/dashboard";
import { PAYMENT_METHODS } from "../api/sales";
import { formatCurrency, formatNumber, formatPercent } from "../utils/format";
import StatCard from "../components/StatCard.vue";
import DoughnutChart from "../components/DoughnutChart.vue";
import Icon from "../components/Icon.vue";

const summary = ref(null);
const byPrinter = ref([]);
const byPayment = ref([]);
const stockAlerts = ref([]);
const loading = ref(true);

const filters = reactive({ date_from: "", date_to: "" });

const statusLabels = { disponible: "Disponible", alerta: "Alerta", critico: "Crítico", vacio: "Vacío" };
const statusBadge = { disponible: "badge-success", alerta: "badge-warning", critico: "badge-danger", vacio: "badge-danger" };
const paymentLabel = (v) => PAYMENT_METHODS.find((p) => p.value === v)?.label || v;

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
  filters.date_from = "";
  filters.date_to = "";
  loadAll();
}

onMounted(loadAll);
</script>

<template>
  <div>
    <div class="page-header">
      <p class="page-subtitle">Resumen ejecutivo de tu negocio de impresión 3D</p>
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
                <td>{{ f.brand }} · {{ f.color }} <span class="text-muted text-sm">({{ f.type }})</span></td>
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
