<script setup>
import { ref, computed, onMounted } from "vue";
import * as historyApi from "../api/history";
import { formatCurrency, formatNumber, formatPercent } from "../utils/format";
import StatCard from "../components/StatCard.vue";
import MonthlyTrendChart from "../components/MonthlyTrendChart.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import SourceBreakdown from "../components/SourceBreakdown.vue";
import { SALE_SOURCES, NO_SALE_SOURCE } from "../api/sales";

const months = ref([]);
const selectedKeys = ref([]);
const loading = ref(true);

function monthKey(m) {
  return `${m.year}-${m.month}`;
}

async function load() {
  loading.value = true;
  try {
    months.value = await historyApi.getMonthlyHistory();
    if (months.value.length) {
      selectedKeys.value = [monthKey(months.value[0])];
    }
  } finally {
    loading.value = false;
  }
}

onMounted(load);

const selectedMonths = computed(() =>
  months.value
    .filter((m) => selectedKeys.value.includes(monthKey(m)))
    .sort((a, b) => a.year - b.year || a.month - b.month)
);

const singleMonth = computed(() => (selectedMonths.value.length === 1 ? selectedMonths.value[0] : null));
const isComparing = computed(() => selectedMonths.value.length >= 2);

const chartCategories = computed(() => selectedMonths.value.map((m) => m.label));
const revenueCostSeries = computed(() => [
  { name: "Ingresos", data: selectedMonths.value.map((m) => Number(m.total_revenue)) },
  { name: "Ganancia", data: selectedMonths.value.map((m) => Number(m.total_profit)) },
  { name: "Costo", data: selectedMonths.value.map((m) => Number(m.total_cost)) },
]);
const marginSeries = computed(() => [
  { name: "Margen promedio (%)", data: selectedMonths.value.map((m) => Number(m.avg_margin_percent)) },
]);

// Mini gráficos del mes elegido: su valor y los meses anteriores con datos (hasta 8).
const sparkFor = (field) => {
  if (!singleMonth.value) return null;
  const upTo = months.value
    .filter((m) => m.year * 12 + m.month <= singleMonth.value.year * 12 + singleMonth.value.month)
    .sort((a, b) => a.year - b.year || a.month - b.month)
    .slice(-8);
  return upTo.length >= 2 ? upTo.map((m) => Number(m[field])) : null;
};

// Ventas por fuente. Un mes: dona. Varios: una barra por canal en cada mes (pedidos).
const sourceItems = (m) =>
  Object.entries(m.by_source || {}).map(([source, t]) => ({ source, jobs: t.jobs, revenue: t.revenue }));
const ALL_SOURCES = [...SALE_SOURCES, NO_SALE_SOURCE];
const sourceSeriesInfo = computed(() =>
  // Solo los canales con ventas en algún mes elegido ("Sin registrar" no aparece si no hay).
  ALL_SOURCES.filter((src) => selectedMonths.value.some((m) => m.by_source?.[src.value]?.jobs))
);
const sourceSeries = computed(() =>
  sourceSeriesInfo.value.map((src) => ({
    name: src.label,
    data: selectedMonths.value.map((m) => m.by_source?.[src.value]?.jobs || 0),
  }))
);
const formatJobs = (v) => `${Math.round(v)}`;

function toggleMonth(m) {
  const key = monthKey(m);
  const idx = selectedKeys.value.indexOf(key);
  if (idx === -1) {
    selectedKeys.value.push(key);
  } else {
    selectedKeys.value.splice(idx, 1);
  }
}
function isSelected(m) {
  return selectedKeys.value.includes(monthKey(m));
}
</script>

<template>
  <div>
    <div class="page-header">
      <p class="page-subtitle">Estadísticas de tu negocio agrupadas por mes — selecciona uno para verlo en detalle, o varios para comparar su evolución. Cuenta los pedidos Entregados, en el mes de su entrega.</p>
    </div>

    <LoadingSkeleton v-if="loading && !months.length" />

    <template v-else>
      <div class="card" style="margin-bottom: 20px">
        <div class="card-header">
          <h3>Meses disponibles</h3>
        </div>
        <div v-if="!months.length" class="empty-state">
          <h3>Todavía no hay ventas registradas</h3>
          <p>Cuando registres ventas, aparecerán aquí agrupadas por mes.</p>
        </div>
        <div v-else class="month-chip-list">
          <button
            v-for="m in months"
            :key="monthKey(m)"
            type="button"
            class="month-chip"
            :class="{ selected: isSelected(m) }"
            @click="toggleMonth(m)"
          >
            {{ m.label }}
            <span class="text-sm" style="opacity: 0.75">· {{ m.total_jobs }}</span>
          </button>
        </div>
      </div>

      <div v-if="!selectedMonths.length" class="card empty-state">
        <h3>Selecciona uno o más meses</h3>
        <p>Elige un mes arriba para ver sus estadísticas, o varios para comparar la evolución.</p>
      </div>

      <template v-else-if="singleMonth">
        <div class="grid grid-cols-4" style="margin-bottom: 20px">
          <StatCard label="Trabajos" :value="formatNumber(singleMonth.total_jobs, 0)" :spark="sparkFor('total_jobs')" />
          <StatCard label="Ingresos" :value="formatCurrency(singleMonth.total_revenue)" :spark="sparkFor('total_revenue')" color="var(--accent)" />
          <StatCard label="Ganancia" :value="formatCurrency(singleMonth.total_profit)" :spark="sparkFor('total_profit')" color="var(--success)" />
          <StatCard
            label="Margen promedio"
            :value="formatPercent(singleMonth.avg_margin_percent)"
            :ring="Number(singleMonth.avg_margin_percent)"
            color="var(--warning)"
          />
          <StatCard label="Costo total" :value="formatCurrency(singleMonth.total_cost)" />
          <StatCard label="Horas impresas" :value="formatNumber(singleMonth.total_print_hours, 1)" :spark="sparkFor('total_print_hours')" color="var(--info)" />
          <StatCard label="Filamento usado" :value="`${formatNumber(singleMonth.total_filament_used_g, 0)} g`" />
        </div>
        <div v-reveal class="card glow">
          <div class="card-header">
            <h3>Ventas por fuente</h3>
            <span class="text-muted text-sm">De dónde llegaron los pedidos entregados de {{ singleMonth.label }}</span>
          </div>
          <SourceBreakdown :items="sourceItems(singleMonth)" />
        </div>
      </template>

      <template v-else-if="isComparing">
        <div class="grid grid-cols-2" style="margin-bottom: 20px; align-items: start">
          <div class="card">
            <div class="card-header">
              <h3>Ingresos, ganancia y costo</h3>
            </div>
            <MonthlyTrendChart type="bar" :categories="chartCategories" :series="revenueCostSeries" :value-formatter="formatCurrency" />
          </div>
          <div class="card">
            <div class="card-header">
              <h3>Margen promedio</h3>
            </div>
            <MonthlyTrendChart type="line" :categories="chartCategories" :series="marginSeries" :value-formatter="formatPercent" />
          </div>
        </div>

        <div v-reveal class="card glow" style="margin-bottom: 20px">
          <div class="card-header">
            <h3>Ventas por fuente</h3>
            <span class="text-muted text-sm">Pedidos entregados de cada canal, mes a mes</span>
          </div>
          <div v-if="!sourceSeries.length" class="empty-state">Sin ventas en estos meses.</div>
          <MonthlyTrendChart
            v-else
            type="bar"
            :categories="chartCategories"
            :series="sourceSeries"
            :colors="sourceSeriesInfo.map((s) => s.color)"
            :value-formatter="formatJobs"
          />
        </div>

        <div class="card">
          <div class="card-header">
            <h3>Comparación mes a mes</h3>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Mes</th>
                  <th class="text-right">Trabajos</th>
                  <th class="text-right">Ingresos</th>
                  <th class="text-right">Ganancia</th>
                  <th class="text-right">Costo</th>
                  <th class="text-right">Margen</th>
                  <th class="text-right">Horas</th>
                  <th class="text-right">Filamento</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in selectedMonths" :key="monthKey(m)">
                  <td><strong>{{ m.label }}</strong></td>
                  <td class="text-right mono">{{ m.total_jobs }}</td>
                  <td class="text-right mono">{{ formatCurrency(m.total_revenue) }}</td>
                  <td class="text-right mono" style="color: var(--success)">{{ formatCurrency(m.total_profit) }}</td>
                  <td class="text-right mono">{{ formatCurrency(m.total_cost) }}</td>
                  <td class="text-right">{{ formatPercent(m.avg_margin_percent) }}</td>
                  <td class="text-right mono">{{ formatNumber(m.total_print_hours, 1) }}</td>
                  <td class="text-right mono">{{ formatNumber(m.total_filament_used_g, 0) }} g</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.month-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.month-chip {
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface-alt);
  color: var(--text);
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}

.month-chip:hover {
  border-color: var(--primary);
}

.month-chip.selected {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
}
</style>
