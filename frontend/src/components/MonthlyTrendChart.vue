<script setup>
import { computed } from "vue";
import VueApexCharts from "vue3-apexcharts";
import { useTheme } from "../composables/useTheme";
import { baseChartOptions } from "../utils/chartTheme";

const props = defineProps({
  type: { type: String, default: "bar" }, // 'bar' | 'line'
  categories: { type: Array, required: true },
  series: { type: Array, required: true }, // [{ name, data: number[] }]
  height: { type: [Number, String], default: 280 },
  valueFormatter: { type: Function, default: (v) => v },
});

const { theme } = useTheme();

const chartOptions = computed(() => ({
  ...baseChartOptions(theme.value),
  chart: { ...baseChartOptions(theme.value).chart, type: props.type },
  xaxis: {
    categories: props.categories,
    labels: { style: { fontSize: "11px" } },
  },
  yaxis: {
    labels: { formatter: props.valueFormatter, style: { fontSize: "11px" } },
  },
  stroke: props.type === "line" ? { width: 3, curve: "smooth" } : { width: 0 },
  markers: props.type === "line" ? { size: 4 } : {},
  plotOptions: { bar: { borderRadius: 4, columnWidth: "55%" } },
  legend: { position: "bottom", fontSize: "12px" },
  dataLabels: { enabled: false },
  tooltip: { y: { formatter: props.valueFormatter } },
}));
</script>

<template>
  <div :style="{ height: `${height}px` }">
    <VueApexCharts :key="theme" :type="type" :height="height" :options="chartOptions" :series="series" />
  </div>
</template>
