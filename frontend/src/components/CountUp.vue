<script setup>
import { onBeforeUnmount, ref, watch } from "vue";
import { prefersReducedMotion } from "../composables/useMotion";

// Número que "cuenta" desde su valor anterior (o desde 0 al aparecer) hasta el nuevo.
// format recibe el número y devuelve el texto (ej. formatCurrency).
const props = defineProps({
  value: { type: Number, required: true },
  format: { type: Function, default: (v) => Math.round(v).toLocaleString("es-CL") },
  duration: { type: Number, default: 900 },
  delay: { type: Number, default: 0 },
});

const shown = ref(props.format(0));
let frame = null;
let timer = null;
let current = 0;

function run(to) {
  cancelAnimationFrame(frame);
  clearTimeout(timer);
  if (prefersReducedMotion() || !Number.isFinite(to)) {
    current = to;
    shown.value = props.format(to);
    return;
  }
  const from = current;
  timer = setTimeout(() => {
    const t0 = performance.now();
    const step = (now) => {
      const p = Math.min(1, (now - t0) / props.duration);
      current = from + (to - from) * (1 - Math.pow(1 - p, 3));
      shown.value = props.format(p < 1 ? current : to);
      if (p < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
  }, props.delay);
}

watch(() => props.value, run, { immediate: true });
onBeforeUnmount(() => {
  cancelAnimationFrame(frame);
  clearTimeout(timer);
});
</script>

<template>
  <span>{{ shown }}</span>
</template>
