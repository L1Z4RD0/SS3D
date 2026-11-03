<script setup>
import { computed, watch } from "vue";
import { formatCurrency, formatNumber } from "../utils/format";
import HoursMinutesInput from "./HoursMinutesInput.vue";

/* Pieza dañada a medio imprimir: qué % se alcanzó a imprimir, cuántas horas se usaron y si
   se hizo el postprocesado. Muestra la pérdida estimada con la misma regla del servidor:
   material = % × material; máquina = horas usadas ÷ horas del pedido × (depreciación + luz);
   postprocesado solo si se hizo; insumos solo si ya estaban puestos. */
const props = defineProps({
  sale: { type: Object, required: true },
  suppliesConsumed: { type: Boolean, default: false },
});
const percent = defineModel("percent", { type: [Number, String, null], default: null });
const hours = defineModel("hours", { type: [Number, String, null], default: null });
const postprocess = defineModel("postprocess", { type: Boolean, default: false });

const n = (v) => Number(v) || 0;
const planned = computed(() => n(props.sale.planned_print_hours) || n(props.sale.print_hours));
const validPercent = computed(() => n(percent.value) >= 1 && n(percent.value) <= 100);

// Las horas se sugieren solas según el %; si el usuario las cambia a mano, se respetan.
let lastSuggested = null;
watch(
  percent,
  (p) => {
    if (!validPercent.value) return;
    const suggested = Math.round(planned.value * (n(p) / 100) * 100) / 100;
    if (hours.value === null || hours.value === "" || n(hours.value) === lastSuggested) hours.value = suggested;
    lastSuggested = suggested;
  },
  { immediate: true }
);

const tooManyHours = computed(() => n(hours.value) > planned.value + 0.001);
const parts = computed(() => {
  const s = props.sale;
  const pct = validPercent.value ? n(percent.value) / 100 : 0;
  const ratio = planned.value > 0 ? Math.min(1, n(hours.value) / planned.value) : 0;
  return [
    { label: "Material", value: n(s.material_cost) * pct, hint: `${formatNumber(n(s.grams_used) * pct, 0)} g de ${formatNumber(s.grams_used, 0)} g` },
    { label: "Máquina", value: (n(s.depreciation_cost) + n(s.energy_cost)) * ratio, hint: `${formatNumber(hours.value, 2)} h de ${formatNumber(planned.value, 2)} h` },
    { label: "Postprocesado", value: postprocess.value ? n(s.postprocess_cost) : 0, hint: postprocess.value ? "se hizo" : "no se hizo" },
    { label: "Insumos", value: props.suppliesConsumed ? n(s.supplies_cost) : 0, hint: props.suppliesConsumed ? "ya estaban puestos" : "vuelven al inventario" },
  ];
});
const total = computed(() => parts.value.reduce((acc, p) => acc + p.value, 0));
const valid = computed(() => validPercent.value && !tooManyHours.value && n(hours.value) >= 0);
defineExpose({ valid });
</script>

<template>
  <fieldset class="question partial">
    <legend>¿Cuánto se alcanzó a imprimir?</legend>
    <div class="partial-grid">
      <div class="field">
        <label>% de la pieza impresa</label>
        <div class="percent-row">
          <input v-model.number="percent" type="range" min="1" max="100" step="1" aria-label="% impreso (deslizador)" />
          <div class="percent-input">
            <input v-model.number="percent" type="number" min="1" max="100" step="1" placeholder="1 a 100" aria-label="% impreso" required />
            <span>%</span>
          </div>
        </div>
      </div>
      <div class="field">
        <label>Tiempo de impresión usado</label>
        <HoursMinutesInput v-model="hours" />
        <span v-if="tooManyHours" class="field-hint error">Máximo {{ formatNumber(planned, 2) }} h (las del pedido).</span>
        <span v-else class="field-hint">Sugerido según el %: puedes corregirlo.</span>
      </div>
    </div>
    <label class="option">
      <input v-model="postprocess" type="checkbox" /> Sí se alcanzó a hacer el postprocesado
    </label>
    <div class="estimate">
      <div v-for="p in parts" :key="p.label" class="estimate-line">
        <span>{{ p.label }} <small class="text-muted">· {{ p.hint }}</small></span>
        <span class="mono">{{ formatCurrency(p.value) }}</span>
      </div>
      <div class="estimate-line total">
        <strong>Pérdida estimada</strong>
        <strong class="mono">{{ formatCurrency(total) }}</strong>
      </div>
      <p class="field-hint">
        Lo que no se usó vuelve al inventario y a la impresora. A fin de mes, el Reparto le devuelve esta pérdida a
        quien puso cada recurso.
      </p>
    </div>
  </fieldset>
</template>

<style scoped>
.question {
  margin: 0 0 12px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.question legend {
  padding: 0 4px;
  font-size: 0.88rem;
  font-weight: 700;
}
.partial {
  border-color: color-mix(in srgb, var(--danger) 30%, var(--border));
}
.partial-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.percent-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.percent-row input[type="range"] {
  flex: 1;
  accent-color: var(--primary);
}
.percent-input {
  display: flex;
  align-items: center;
  gap: 4px;
}
.percent-input input {
  width: 72px;
  text-align: right;
}
.option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 0.88rem;
  cursor: pointer;
}
.option input {
  width: auto;
}
.estimate {
  margin-top: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--danger-soft);
}
.estimate-line {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 2px 0;
  font-size: 0.85rem;
}
.estimate-line.total {
  margin-top: 4px;
  padding-top: 6px;
  border-top: 1px solid color-mix(in srgb, var(--danger) 25%, transparent);
  color: var(--danger);
}
.error {
  color: var(--danger);
}
@media (max-width: 640px) {
  .partial-grid {
    grid-template-columns: 1fr;
  }
}
</style>
