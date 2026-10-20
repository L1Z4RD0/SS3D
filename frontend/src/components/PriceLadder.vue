<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { formatCurrency } from "../utils/format";
import CountUp from "./CountUp.vue";
import { whenVisible } from "../utils/motion";

// Barras de los escenarios de precio: cada una muestra cuánto del precio es costo y cuánto
// ganancia. Crecen una tras otra al calcular; el precio manual se mueve mientras se escribe.
const props = defineProps({
  cost: { type: Number, required: true },
  scenarios: { type: Array, required: true }, // [{ label, price, profit, manual? }]
});

const max = computed(() => Math.max(props.cost, ...props.scenarios.map((s) => Number(s.price) || 0), 1));
const rows = computed(() =>
  props.scenarios.map((s) => {
    const price = Math.max(0, Number(s.price) || 0);
    return {
      key: s.manual ? "manual" : s.label,
      label: s.label,
      manual: !!s.manual,
      price,
      loss: price < props.cost,
      costW: (Math.min(price, props.cost) / max.value) * 100,
      profitW: (Math.max(0, price - props.cost) / max.value) * 100,
    };
  })
);

// Crecen cuando entran en pantalla, y de nuevo desde cero al recalcular (llegan escenarios
// nuevos), no al escribir el precio manual.
const root = ref(null);
const drawn = ref(false);
const run = ref(0);
let stopWatching = () => {};
watch(
  () => props.scenarios[0],
  () => {
    drawn.value = false;
    run.value++;
    stopWatching();
    nextTick(() => {
      stopWatching = whenVisible(root.value, () =>
        requestAnimationFrame(() => requestAnimationFrame(() => (drawn.value = true)))
      );
    });
  },
  { immediate: true }
);
onBeforeUnmount(() => stopWatching());
</script>

<template>
  <div :key="run" ref="root" class="ladder" :class="{ drawn }">
    <div v-for="(r, i) in rows" :key="r.key" class="ladder-row" :class="{ manual: r.manual, loss: r.loss }" :style="{ '--d': `${0.1 + i * 0.14}s` }">
      <span class="ladder-label">{{ r.label }}</span>
      <div class="ladder-track">
        <div class="ladder-cost" :style="{ width: drawn ? `${r.costW}%` : 0 }"></div>
        <div class="ladder-profit" :style="{ width: drawn ? `${r.profitW}%` : 0 }"></div>
      </div>
      <strong class="ladder-price mono">
        <CountUp :value="drawn ? r.price : 0" :format="formatCurrency" :delay="r.manual ? 0 : (0.1 + i * 0.14) * 1000" />
      </strong>
    </div>
    <div class="ladder-legend">
      <span><i class="k-cost"></i>Costo</span>
      <span><i class="k-profit"></i>Ganancia</span>
    </div>
  </div>
</template>

<style scoped>
.ladder {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 16px;
}

.ladder-row {
  display: grid;
  grid-template-columns: 160px 1fr 110px;
  align-items: center;
  gap: 12px;
  opacity: 0;
}
.ladder.drawn .ladder-row {
  animation: zola-rise 0.4s var(--ease-out) var(--d) forwards;
}

.ladder-label {
  font-size: 0.84rem;
  font-weight: 700;
}

.ladder-track {
  display: flex;
  height: 14px;
  border-radius: 999px;
  background: var(--surface-alt);
  overflow: hidden;
}

.ladder-cost,
.ladder-profit {
  height: 100%;
  transition: width 0.8s var(--ease-out);
  transition-delay: var(--d);
}
/* La ganancia arranca cuando el costo ya llegó. */
.ladder-profit {
  transition-delay: calc(var(--d) + 0.35s);
}
/* Al recalcular vuelven a cero de inmediato y crecen de nuevo. */
.ladder:not(.drawn) .ladder-cost,
.ladder:not(.drawn) .ladder-profit {
  transition: none;
}
/* Mientras se escribe el precio manual o tras dibujarse, sin esperas. */
.ladder.drawn .manual .ladder-cost,
.ladder.drawn .manual .ladder-profit {
  transition-duration: 0.45s;
  transition-delay: 0s;
}

.ladder-cost {
  background: color-mix(in srgb, var(--text-muted) 45%, var(--surface-alt));
}
.ladder-profit {
  position: relative;
  overflow: hidden;
  background: linear-gradient(90deg, var(--success), color-mix(in srgb, var(--success) 55%, var(--accent)));
}
/* Brillo que recorre la ganancia una vez dibujada. */
.ladder-profit::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(100deg, transparent 30%, rgba(255, 255, 255, 0.45) 50%, transparent 70%);
  transform: translateX(-100%);
}
.ladder.drawn .ladder-profit::after {
  animation: ladder-shine 1.1s var(--ease-out) calc(var(--d) + 1.1s) forwards;
}
@keyframes ladder-shine {
  to {
    transform: translateX(100%);
  }
}

.ladder-row.loss .ladder-cost {
  background: var(--danger);
}
.ladder-row.manual .ladder-label {
  color: var(--primary);
}

.ladder-price {
  text-align: right;
  font-size: 0.92rem;
}

.ladder-legend {
  display: flex;
  gap: 14px;
  font-size: 0.75rem;
  color: var(--text-muted);
}
.ladder-legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.ladder-legend i {
  width: 10px;
  height: 10px;
  border-radius: 3px;
}
.k-cost {
  background: color-mix(in srgb, var(--text-muted) 45%, var(--surface-alt));
}
.k-profit {
  background: var(--success);
}

@media (max-width: 640px) {
  .ladder-row {
    grid-template-columns: 1fr auto;
    row-gap: 6px;
  }
  .ladder-track {
    grid-column: 1 / -1;
    grid-row: 2;
  }
}
</style>
