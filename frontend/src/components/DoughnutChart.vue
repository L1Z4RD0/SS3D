<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { CHART_PALETTE } from "../utils/chartTheme";
import { formatCurrency } from "../utils/format";
import CountUp from "./CountUp.vue";
import { whenVisible } from "../utils/motion";

// Dona animada (SVG propio): cada parte se dibuja una tras otra, el total del centro cuenta
// hasta su valor y al pasar el mouse (o tocar) una parte se destaca y el centro muestra su
// detalle. Las partes en 0 no se dibujan ni salen en la leyenda.
const props = defineProps({
  labels: { type: Array, required: true },
  values: { type: Array, required: true },
  centerLabel: { type: String, default: "Total" },
  format: { type: Function, default: formatCurrency },
});

const GAP = 0.8; // separación entre partes, en % de la vuelta

const total = computed(() => props.values.reduce((sum, v) => sum + Math.max(0, Number(v) || 0), 0));
const parts = computed(() => {
  let start = 0;
  return props.values
    .map((v, i) => ({ label: props.labels[i], value: Math.max(0, Number(v) || 0), color: CHART_PALETTE[i % CHART_PALETTE.length] }))
    .filter((p) => p.value > 0)
    .map((p, i, list) => {
      const pct = total.value ? (p.value / total.value) * 100 : 0;
      const part = { ...p, i, pct, start, len: Math.max(0.01, pct - (list.length > 1 ? GAP : 0)) };
      start += pct;
      return part;
    });
});

// Al aparecer o al cambiar los valores (ej. recalcular), la dona se vuelve a dibujar.
// Se dibuja cuando la dona entra en pantalla, y de nuevo cada vez que cambian los valores
// (ej. recalcular). Mientras se dibuja cada parte espera su turno; después (settled)
// responden al instante.
const root = ref(null);
const drawn = ref(false);
const settled = ref(false);
let settleTimer = null;
let stopWatching = () => {};
function draw() {
  drawn.value = false;
  settled.value = false;
  clearTimeout(settleTimer);
  stopWatching();
  nextTick(() => {
    stopWatching = whenVisible(root.value, () =>
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          drawn.value = true;
          settleTimer = setTimeout(() => (settled.value = true), 1600);
        })
      )
    );
  });
}
watch(() => props.values.join("|"), draw, { immediate: true });
onBeforeUnmount(() => {
  clearTimeout(settleTimer);
  stopWatching();
});

const active = ref(null);
const activePart = computed(() => parts.value.find((p) => p.i === active.value) || null);
const toggle = (i) => (active.value = active.value === i ? null : i);
const pctText = (p) => `${p.pct.toLocaleString("es-CL", { maximumFractionDigits: p.pct < 10 ? 1 : 0 })}%`;
</script>

<template>
  <div ref="root" class="mdonut" :class="{ drawn, focus: activePart }">
    <div class="mdonut-ring">
      <svg viewBox="0 0 120 120" role="img" :aria-label="`${centerLabel}: ${format(total)}`">
        <circle class="mdonut-track" cx="60" cy="60" r="46" />
        <circle
          v-for="p in parts"
          :key="p.label"
          class="mdonut-seg"
          :class="{ on: p.i === active }"
          cx="60"
          cy="60"
          r="46"
          pathLength="100"
          :style="{
            stroke: p.color,
            strokeDasharray: drawn ? `${p.len} ${100 - p.len}` : `0 100`,
            strokeDashoffset: -p.start,
            transitionDelay: settled ? '0s' : `${0.1 + p.i * 0.12}s`,
          }"
          @mouseenter="active = p.i"
          @mouseleave="active = null"
          @click="toggle(p.i)"
        />
      </svg>
      <div class="mdonut-center">
        <Transition name="mdonut-swap" mode="out-in">
          <div v-if="activePart" :key="activePart.label">
            <span class="mdonut-cap">{{ activePart.label }}</span>
            <strong class="mono">{{ format(activePart.value) }}</strong>
            <span class="mdonut-pct" :style="{ color: activePart.color }">{{ pctText(activePart) }}</span>
          </div>
          <div v-else key="total">
            <span class="mdonut-cap">{{ centerLabel }}</span>
            <strong class="mono"><CountUp :value="drawn ? total : 0" :format="format" :delay="150" /></strong>
          </div>
        </Transition>
      </div>
    </div>
    <ul class="mdonut-legend" :class="{ shown: drawn }">
      <li
        v-for="p in parts"
        :key="p.label"
        :class="{ on: p.i === active }"
        :style="{ '--d': `${0.25 + p.i * 0.07}s` }"
        @mouseenter="active = p.i"
        @mouseleave="active = null"
        @click="toggle(p.i)"
      >
        <i :style="{ background: p.color }"></i>{{ p.label }}
        <span class="mono">{{ pctText(p) }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.mdonut {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 6px 0;
}

.mdonut-ring {
  position: relative;
  width: min(200px, 100%);
  aspect-ratio: 1;
}

.mdonut-ring svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
  overflow: visible;
}

.mdonut-track {
  fill: none;
  stroke: var(--surface-alt);
  stroke-width: 14;
}

.mdonut-seg {
  fill: none;
  stroke-width: 14;
  cursor: pointer;
  transition: stroke-dasharray 0.75s var(--ease-out), stroke-width 0.3s var(--ease-spring), opacity 0.25s;
}

/* Al volver a dibujar (valores nuevos) arranca vacía de inmediato, sin deshacerse de a poco. */
.mdonut:not(.drawn) .mdonut-seg {
  transition: none;
}

/* Al destacar una parte: crece y el resto se atenúa. */
.mdonut.focus .mdonut-seg {
  opacity: 0.35;
}
.mdonut.focus .mdonut-seg.on {
  opacity: 1;
  stroke-width: 19;
}

.mdonut-center {
  position: absolute;
  inset: 22%;
  display: grid;
  place-items: center;
  text-align: center;
  pointer-events: none;
}
.mdonut-center > div {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.mdonut-cap {
  font-size: 0.72rem;
  color: var(--text-muted);
  font-weight: 600;
}
.mdonut-center strong {
  font-size: 1.05rem;
  line-height: 1.2;
}
.mdonut-pct {
  font-size: 0.8rem;
  font-weight: 800;
}

.mdonut-swap-enter-active,
.mdonut-swap-leave-active {
  transition: opacity 0.15s, transform 0.2s var(--ease-out);
}
.mdonut-swap-enter-from {
  opacity: 0;
  transform: scale(0.85);
}
.mdonut-swap-leave-to {
  opacity: 0;
  transform: scale(1.1);
}

.mdonut-legend {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.mdonut-legend li {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 9px;
  border-radius: 999px;
  border: 1px solid var(--border);
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  opacity: 0;
  transition: border-color 0.2s, background 0.2s;
}
.mdonut-legend.shown li {
  animation: zola-rise 0.4s var(--ease-out) var(--d) forwards;
}
.mdonut-legend li.on {
  border-color: var(--primary);
  background: var(--primary-soft);
}
.mdonut-legend i {
  width: 8px;
  height: 8px;
  border-radius: 3px;
}
.mdonut-legend .mono {
  color: var(--text-muted);
}
</style>
