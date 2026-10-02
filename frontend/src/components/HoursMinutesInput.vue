<script setup>
import { ref, watch } from "vue";

// Tiempo en dos casillas (horas y minutos) para no convertir los minutos a mano. El valor
// (v-model) sigue siendo horas decimales, que es lo que guarda el servidor: 1 h 30 min = 1.5.
const hours = defineModel({ type: [Number, String, null], default: null });
defineProps({ disabled: { type: Boolean, default: false } });

const h = ref(null);
const m = ref(null);

function split(value) {
  const total = Number(value);
  if (value === null || value === "" || !Number.isFinite(total) || total < 0) return [null, null];
  let whole = Math.floor(total);
  let minutes = Math.round((total - whole) * 60);
  if (minutes === 60) {
    whole += 1;
    minutes = 0;
  }
  return [whole, minutes];
}

// Valor que representan las casillas ahora mismo (null si ambas están vacías).
function combined() {
  const empty = (v) => v === null || v === "" || v === undefined;
  if (empty(h.value) && empty(m.value)) return null;
  // Se guarda con 2 decimales, igual que el servidor (1 h 20 min = 1.33).
  return Math.round(((Number(h.value) || 0) + (Number(m.value) || 0) / 60) * 100) / 100;
}

// Si el valor cambia desde afuera (abrir una venta, limpiar el formulario, borrador), se
// reparte en horas y minutos. Si lo cambiaron estas casillas, no se tocan mientras se escribe.
watch(
  hours,
  (value) => {
    if (combined() === (value === null || value === "" ? null : Number(value))) return;
    [h.value, m.value] = split(value);
  },
  { immediate: true }
);

function update() {
  hours.value = combined();
}

// Al salir de la casilla, 90 minutos se muestran como 1 h 30 min.
function normalize() {
  if (Number(m.value) >= 60 || Number(m.value) < 0) [h.value, m.value] = split(combined());
}
</script>

<template>
  <div class="hm-input">
    <label class="hm-part">
      <input v-model.number="h" type="number" min="0" step="1" placeholder="0" :disabled="disabled" aria-label="Horas" @input="update" />
      <span>h</span>
    </label>
    <label class="hm-part">
      <input
        v-model.number="m"
        type="number"
        min="0"
        max="59"
        step="1"
        placeholder="0"
        :disabled="disabled"
        aria-label="Minutos"
        @input="update"
        @blur="normalize"
      />
      <span>min</span>
    </label>
  </div>
</template>

<style scoped>
.hm-input {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.hm-part {
  position: relative;
  display: block;
  margin: 0;
}

.hm-part input {
  width: 100%;
  min-width: 0;
  padding-right: 34px;
  /* Sin flechitas: en casillas angostas se comían el espacio de los números. */
  -moz-appearance: textfield;
  appearance: textfield;
}

.hm-part input::-webkit-outer-spin-button,
.hm-part input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.hm-part:first-child input {
  padding-right: 24px;
}

.hm-part span {
  position: absolute;
  top: 50%;
  right: 10px;
  transform: translateY(-50%);
  color: var(--text-muted);
  font-size: 0.85rem;
  pointer-events: none;
}
</style>
