<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import VueApexCharts from "vue3-apexcharts";
import { useTheme } from "../composables/useTheme";
import { baseChartOptions } from "../utils/chartTheme";
import { whenVisible } from "../utils/motion";

const props = defineProps({
  type: { type: String, default: "bar" }, // 'bar' | 'line'
  categories: { type: Array, required: true },
  series: { type: Array, required: true }, // [{ name, data: number[] }]
  height: { type: [Number, String], default: 280 },
  valueFormatter: { type: Function, default: (v) => v },
});

const { theme } = useTheme();

// El gráfico se crea recién cuando se ve en pantalla, para que su animación de entrada no
// pase sin que nadie la vea (en el celular el segundo gráfico queda más abajo).
const root = ref(null);
const visible = ref(false);
let stopWatching = () => {};
onMounted(() => (stopWatching = whenVisible(root.value, () => (visible.value = true))));
onBeforeUnmount(() => stopWatching());

// Al cambiar los meses el gráfico se crea de nuevo: vuelve a animarse y conserva el formato
// de los ejes ($, %), que se perdía al actualizar el existente.
const chartKey = computed(() => `${theme.value}|${props.categories.join(",")}`);

// Las líneas se dibujan como área con degradado (la curva aparece de izquierda a derecha)
// y las barras crecen con un degradado hacia arriba, una serie tras otra.
const isLine = computed(() => props.type === "line");
const chartType = computed(() => (isLine.value ? "area" : "bar"));

const chartOptions = computed(() => {
  const base = baseChartOptions(theme.value);
  return {
    ...base,
    chart: {
      ...base.chart,
      type: chartType.value,
      dropShadow: isLine.value
        ? { enabled: true, top: 6, left: 0, blur: 8, opacity: 0.22, color: base.colors[0] }
        : { enabled: false },
    },
    xaxis: {
      categories: props.categories,
      labels: { style: { fontSize: "11px" } },
      axisBorder: { show: false },
      axisTicks: { show: false },
    },
    yaxis: {
      labels: { formatter: props.valueFormatter, style: { fontSize: "11px" } },
    },
    grid: { ...base.grid, strokeDashArray: 4 },
    stroke: isLine.value ? { width: 3, curve: "smooth" } : { width: 0 },
    markers: isLine.value ? { size: 5, strokeWidth: 3, strokeColors: theme.value === "dark" ? "#17182b" : "#fff", hover: { size: 8 } } : {},
    fill: isLine.value
      ? { type: "gradient", gradient: { shadeIntensity: 1, opacityFrom: 0.45, opacityTo: 0.02, stops: [0, 95] } }
      : { type: "gradient", gradient: { type: "vertical", shadeIntensity: 0.35, opacityFrom: 1, opacityTo: 0.75, stops: [0, 100] } },
    plotOptions: { bar: { borderRadius: 6, borderRadiusApplication: "end", columnWidth: "55%" } },
    states: { hover: { filter: { type: "lighten", value: 0.08 } } },
    legend: { position: "bottom", fontSize: "12px", markers: { shape: "circle" } },
    dataLabels: { enabled: false },
    tooltip: { y: { formatter: props.valueFormatter } },
  };
});
</script>

<template>
  <div ref="root" :style="{ height: `${height}px` }">
    <VueApexCharts v-if="visible" :key="chartKey" :type="chartType" :height="height" :options="chartOptions" :series="series" />
  </div>
</template>
