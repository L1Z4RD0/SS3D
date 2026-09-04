<script setup>
import { computed } from "vue";
import { Doughnut } from "vue-chartjs";
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from "chart.js";

ChartJS.register(ArcElement, Tooltip, Legend);

const props = defineProps({
  labels: { type: Array, required: true },
  values: { type: Array, required: true },
});

const palette = ["#5b4bf5", "#17b3a3", "#f0ad4e", "#d7473f", "#3567d6", "#9384ff"];

const chartData = computed(() => ({
  labels: props.labels,
  datasets: [
    {
      data: props.values,
      backgroundColor: palette,
      borderWidth: 0,
      hoverOffset: 6,
    },
  ],
}));

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  cutout: "62%",
  plugins: {
    legend: {
      position: "bottom",
      labels: { boxWidth: 10, boxHeight: 10, padding: 14, font: { size: 11 } },
    },
  },
};
</script>

<template>
  <div style="height: 240px">
    <Doughnut :data="chartData" :options="chartOptions" />
  </div>
</template>
