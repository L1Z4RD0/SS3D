<script setup>
import { onBeforeUnmount, ref, watch } from "vue";

const props = defineProps({
  label: { type: String, required: true },
  value: { type: String, required: true },
  meta: { type: String, default: "" },
});

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
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  if (!target || reduce) {
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
  <div class="stat-card">
    <span class="stat-label">{{ label }}</span>
    <span class="stat-value">{{ display }}</span>
    <span v-if="meta" class="stat-meta">{{ meta }}</span>
  </div>
</template>
