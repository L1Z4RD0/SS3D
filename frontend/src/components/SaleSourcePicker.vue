<script setup>
import { SALE_SOURCES } from "../api/sales";
import Icon from "./Icon.vue";

// De dónde salió la venta (Instagram, Facebook o Personal). Se usa para el gráfico
// "Ventas por fuente" del Dashboard y del Historial. Tocar la opción elegida la desmarca
// solo si se permite dejarla vacía (al editar ventas antiguas).
const source = defineModel({ type: String, default: "" });
const props = defineProps({
  required: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
});

function pick(value) {
  if (props.disabled) return;
  source.value = source.value === value && !props.required ? "" : value;
}
</script>

<template>
  <div class="field">
    <label>Fuente de venta<span v-if="!required" class="text-muted"> (opcional)</span></label>
    <div class="source-options" role="radiogroup" aria-label="Fuente de venta">
      <button
        v-for="s in SALE_SOURCES"
        :key="s.value"
        type="button"
        role="radio"
        class="source-option"
        :class="{ selected: source === s.value }"
        :aria-checked="source === s.value"
        :disabled="disabled"
        :style="{ '--source-color': s.color }"
        @click="pick(s.value)"
      >
        <Icon :name="s.icon" :size="16" />
        <span>{{ s.label }}</span>
      </button>
    </div>
    <span class="field-hint">¿De dónde llegó este cliente? Así sabemos qué canal vende más.</span>
  </div>
</template>

<style scoped>
.source-options {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.source-option {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-alt);
  color: var(--text);
  font: inherit;
  font-size: 0.88rem;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s, color 0.2s, transform 0.15s var(--ease-out);
}

.source-option svg {
  color: var(--source-color);
  transition: transform 0.35s var(--ease-spring);
}

/* Solo con mouse: en pantallas táctiles el hover queda "pegado" tras tocar. */
@media (hover: hover) {
  .source-option:hover:not(:disabled) {
    border-color: var(--source-color);
  }
}

.source-option:active:not(:disabled) {
  transform: scale(0.97);
}

.source-option.selected {
  border-color: var(--source-color);
  background: color-mix(in srgb, var(--source-color) 14%, var(--surface));
  color: var(--source-color);
}

.source-option.selected svg {
  transform: scale(1.15);
}

.source-option:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--primary-soft);
}

.source-option:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
