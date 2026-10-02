<script setup>
import { RISK_LEVELS } from "../api/calculator";

// Riesgo de fallo de la impresión (bajo 10 %, medio 15 %, alto 20 % del costo de
// producción). Se cobra en el precio como reserva, fuera del margen.
const level = defineModel({ type: String, required: true });
defineProps({ disabled: { type: Boolean, default: false } });
</script>

<template>
  <div class="field">
    <label>Riesgo de fallo</label>
    <div class="risk-options" role="radiogroup" aria-label="Riesgo de fallo">
      <label v-for="r in RISK_LEVELS" :key="r.value" class="risk-option" :class="[`risk-${r.value}`, { selected: level === r.value }]">
        <input v-model="level" type="radio" :value="r.value" :disabled="disabled" />
        <span class="risk-name">{{ r.label }}</span>
        <span class="risk-percent">{{ r.percent }}%</span>
      </label>
    </div>
    <span class="field-hint">
      Reserva por si la pieza sale mal: % del costo de producción, se cobra aparte del margen y queda en la ganancia.
    </span>
  </div>
</template>

<style scoped>
.risk-options {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.risk-option {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin: 0;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-alt);
  cursor: pointer;
  font-size: 0.88rem;
}

.risk-option input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.risk-option:focus-within {
  box-shadow: 0 0 0 3px var(--primary-soft);
}

.risk-name {
  font-weight: 600;
}

.risk-percent {
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.risk-option.selected.risk-bajo {
  border-color: var(--success);
  background: var(--success-soft);
}

.risk-option.selected.risk-medio {
  border-color: var(--warning);
  background: var(--warning-soft);
}

.risk-option.selected.risk-alto {
  border-color: var(--danger);
  background: var(--danger-soft);
}
</style>
