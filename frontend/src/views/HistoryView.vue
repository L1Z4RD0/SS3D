<script setup>
import { ref, computed, onMounted } from "vue";
import * as historyApi from "../api/history";
import { formatCurrency, formatNumber, formatPercent } from "../utils/format";
import StatCard from "../components/StatCard.vue";
import MonthlyTrendChart from "../components/MonthlyTrendChart.vue";

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
      <p class="page-subtitle">Estadísticas de tu negocio agrupadas por mes — selecciona uno para verlo en detalle, o varios para comparar su evolución.</p>
    </div>

    <div v-if="loading" class="empty-state">Cargando...</div>

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
          <StatCard label="Trabajos" :value="formatNumber(singleMonth.total_jobs, 0)" />
          <StatCard label="Ingresos" :value="formatCurrency(singleMonth.total_revenue)" />
          <StatCard label="Ganancia" :value="formatCurrency(singleMonth.total_profit)" />
          <StatCard label="Margen promedio" :value="formatPercent(singleMonth.avg_margin_percent)" />
          <StatCard label="Costo total" :value="formatCurrency(singleMonth.total_cost)" />
          <StatCard label="IVA cobrado" :value="formatCurrency(singleMonth.total_iva)" />
          <StatCard label="Horas impresas" :value="formatNumber(singleMonth.total_print_hours, 1)" />
          <StatCard label="Filamento usado" :value="`${formatNumber(singleMonth.total_filament_used_g, 0)} g`" />
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
                  <th class="text-right">IVA</th>
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
                  <td class="text-right mono">{{ formatCurrency(m.total_iva) }}</td>
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
