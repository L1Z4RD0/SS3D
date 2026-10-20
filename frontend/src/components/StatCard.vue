<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { prefersReducedMotion } from "../composables/useMotion";
import { sparkPath } from "../utils/motion";

const props = defineProps({
  label: { type: String, required: true },
  value: { type: String, required: true },
  meta: { type: String, default: "" },
  // Opcionales: valores de los últimos meses para un mini gráfico que se dibuja, o un
  // porcentaje (0-100) para un anillo de progreso junto a la cifra.
  spark: { type: Array, default: null },
  ring: { type: Number, default: null },
  color: { type: String, default: "var(--primary)" },
});

const line = computed(() => (props.spark ? sparkPath(props.spark, 200, 34) : null));
const ringOffset = ref(1);
watch(
  () => props.ring,
  (v) => {
    if (v == null) return;
    // Arranca vacío y se llena en el cuadro siguiente para que se vea el recorrido.
    requestAnimationFrame(() => requestAnimationFrame(() => (ringOffset.value = 1 - Math.min(100, Math.max(0, v)) / 100)));
  },
  { immediate: true }
);

// La cifra "cuenta" hasta su valor al aparecer o al cambiar. El valor llega ya formateado
// (ej. "$1.284.500", "57,3%", "120 g"): se anima solo la parte numérica y se respeta el
// resto del texto. Si no hay número, o el sistema pide reducir movimiento, se muestra tal cual.
const display = ref(props.value);
let frame = null;

function parse(text) {
  const match = /-?\d[\d.]*(?:,\d+)?/.exec(text || "");
  if (!match) return null;
  const [intPart, decPart = ""] = match[0].split(",");
  return {
    number: Number(`${intPart.replace(/\./g, "")}.${decPart || "0"}`),
    decimals: decPart.length,
    index: match.index,
    length: match[0].length,
  };
}

function animate(from, to) {
  cancelAnimationFrame(frame);
  const target = parse(to);
  if (!target || prefersReducedMotion()) {
    display.value = to;
    return;
  }
  const start = parse(from)?.number ?? 0;
  if (start === target.number) {
    display.value = to;
    return;
  }
  const t0 = performance.now();
  const duration = 900;
  const step = (now) => {
    const p = Math.min(1, (now - t0) / duration);
    const eased = 1 - Math.pow(1 - p, 3);
    const current = (start + (target.number - start) * eased).toLocaleString("es-CL", {
      minimumFractionDigits: target.decimals,
      maximumFractionDigits: target.decimals,
    });
    display.value = to.slice(0, target.index) + current + to.slice(target.index + target.length);
    if (p < 1) frame = requestAnimationFrame(step);
    else display.value = to;
  };
  frame = requestAnimationFrame(step);
}

watch(
  () => props.value,
  (to, from) => animate(from ?? "", to),
  { immediate: true }
);
onBeforeUnmount(() => cancelAnimationFrame(frame));
</script>

<template>
  <div class="stat-card glow">
    <span class="stat-label">{{ label }}</span>
    <div v-if="ring != null" class="stat-ring-row">
      <svg class="stat-ring" viewBox="0 0 44 44" aria-hidden="true">
        <circle cx="22" cy="22" r="18" class="track" />
        <circle cx="22" cy="22" r="18" pathLength="1" class="val" :style="{ stroke: color, strokeDashoffset: ringOffset }" />
      </svg>
      <span class="stat-value">{{ display }}</span>
    </div>
    <span v-else class="stat-value">{{ display }}</span>
    <span v-if="meta" class="stat-meta">{{ meta }}</span>
    <svg v-if="line" class="stat-spark" viewBox="0 0 200 34" preserveAspectRatio="none" aria-hidden="true">
      <path class="draw-line" pathLength="1" :d="line.d" :style="{ stroke: color }" />
    </svg>
  </div>
</template>

<style scoped>
.stat-spark {
  display: block;
  width: 100%;
  height: 30px;
  margin-top: 8px;
  overflow: visible;
}
.stat-spark path {
  fill: none;
  stroke-width: 2.5;
  stroke-linecap: round;
}
.stat-ring-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.stat-ring {
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  transform: rotate(-90deg);
}
.stat-ring circle {
  fill: none;
  stroke-width: 5;
}
.stat-ring .track {
  stroke: var(--surface-alt);
}
.stat-ring .val {
  stroke-linecap: round;
  stroke-dasharray: 1;
  transition: stroke-dashoffset 1.4s var(--ease-out) 0.3s;
}
</style>
