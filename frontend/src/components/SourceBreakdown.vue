<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { saleSourceInfo } from "../api/sales";
import { formatCurrency } from "../utils/format";
import { whenVisible } from "../utils/motion";
import DoughnutChart from "./DoughnutChart.vue";
import Icon from "./Icon.vue";

// Ventas por fuente (Instagram, Facebook, Personal y "Sin registrar"): dona con la
// cantidad de pedidos y, al lado, una barra por canal con sus pedidos e ingresos.
const props = defineProps({
  // [{ source: "instagram" | ... | null | "sin_registrar", jobs, revenue }]
  items: { type: Array, required: true },
});

const rows = computed(() => {
  const list = props.items
    .map((it) => ({ ...saleSourceInfo(it.source), jobs: Number(it.jobs) || 0, revenue: Number(it.revenue) || 0 }))
    .filter((r) => r.jobs > 0)
    .sort((a, b) => b.jobs - a.jobs || b.revenue - a.revenue);
  const max = Math.max(1, ...list.map((r) => r.jobs));
  return list.map((r) => ({ ...r, width: (r.jobs / max) * 100 }));
});
const total = computed(() => rows.value.reduce((sum, r) => sum + r.jobs, 0));
const jobsText = (n) => `${Math.round(n)} ${Math.round(n) === 1 ? "pedido" : "pedidos"}`;

// Las barras crecen cuando el gráfico entra en pantalla (y de nuevo si cambian los datos).
const root = ref(null);
const drawn = ref(false);
let stopWatching = () => {};
watch(
  () => rows.value.map((r) => `${r.value}:${r.jobs}`).join("|"),
  () => {
    drawn.value = false;
    stopWatching();
    nextTick(() => {
      stopWatching = whenVisible(root.value, () => requestAnimationFrame(() => requestAnimationFrame(() => (drawn.value = true))));
    });
  },
  { immediate: true }
);
onBeforeUnmount(() => stopWatching());
</script>

<template>
  <div v-if="!rows.length" class="empty-state">Sin ventas en este rango.</div>
  <div v-else ref="root" class="source-breakdown" :class="{ drawn }">
    <DoughnutChart
      :labels="rows.map((r) => r.label)"
      :values="rows.map((r) => r.jobs)"
      :colors="rows.map((r) => r.color)"
      center-label="Pedidos"
      :legend="false"
      :format="(v) => String(Math.round(v))"
    />
    <ul class="source-rows">
      <li v-for="(r, i) in rows" :key="r.value" :style="{ '--source-color': r.color, '--d': `${0.15 + i * 0.1}s` }">
        <div class="source-row-head">
          <span class="source-name">
            <Icon v-if="r.icon" :name="r.icon" :size="15" />
            <i v-else class="source-dot"></i>
            {{ r.label }}
          </span>
          <span class="mono">{{ jobsText(r.jobs) }} · {{ Math.round((r.jobs / total) * 100) }}%</span>
        </div>
        <div class="source-track">
          <div class="source-fill" :style="{ width: drawn ? `${r.width}%` : 0 }"></div>
        </div>
        <div class="source-revenue text-muted text-sm mono">{{ formatCurrency(r.revenue) }} en ingresos</div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.source-breakdown {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
  gap: 20px;
  align-items: center;
}

.source-rows {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.source-row-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 0.88rem;
}

.source-name {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 700;
}
.source-name svg {
  color: var(--source-color);
}
.source-dot {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  background: var(--source-color);
}

.source-track {
  height: 10px;
  margin: 6px 0 4px;
  border-radius: 999px;
  background: var(--surface-alt);
  overflow: hidden;
}

.source-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, color-mix(in srgb, var(--source-color) 70%, #fff), var(--source-color));
  transition: width 0.9s var(--ease-out) var(--d);
}
.source-breakdown:not(.drawn) .source-fill {
  transition: none;
}

@media (max-width: 640px) {
  .source-breakdown {
    grid-template-columns: 1fr;
  }
}
</style>
