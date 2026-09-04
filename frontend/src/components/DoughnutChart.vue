<script setup>
import { computed } from "vue";
import VueApexCharts from "vue3-apexcharts";
import { useTheme } from "../composables/useTheme";
import { baseChartOptions } from "../utils/chartTheme";
import { formatCurrency } from "../utils/format";

const props = defineProps({
  labels: { type: Array, required: true },
  values: { type: Array, required: true },
});

const { theme } = useTheme();

const series = computed(() => props.values.map(Number));

const chartOptions = computed(() => ({
  ...baseChartOptions(theme.value),
  labels: props.labels,
  legend: { position: "bottom", fontSize: "12px" },
  dataLabels: { enabled: false },
  stroke: { width: 0 },
  plotOptions: { pie: { donut: { size: "62%" } } },
  tooltip: { y: { formatter: (val) => formatCurrency(val) } },
}));
</script>

<template>
  <div style="height: 240px">
    <VueApexCharts :key="theme" type="donut" height="240" :options="chartOptions" :series="series" />
  </div>
</template>
