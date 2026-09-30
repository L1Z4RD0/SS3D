<script setup>
import { ref, reactive, computed, watch } from "vue";
import * as salesApi from "../api/sales";
import * as calculatorApi from "../api/calculator";
import { formatCurrency } from "../utils/format";
import { extractApiError } from "../utils/validation";
import { platesError, platesPayload } from "../utils/plates";
import Modal from "./Modal.vue";
import PlateFields from "./PlateFields.vue";

// Agrega una plancha a un pedido ya registrado. Lo típico: una reimpresión porque algunas
// piezas salieron mal (suma costo, el precio no cambia).
const props = defineProps({
  sale: { type: Object, required: true },
  printers: { type: Array, required: true },
  filaments: { type: Array, required: true },
});
const emit = defineEmits(["close", "saved"]);

const isReprint = ref(true);
const plate = reactive({ name: "Reimpresión", printer_id: props.sale.printer_id, print_hours: 0, filaments: [] });
watch(isReprint, (reprint) => {
  if (plate.name === "Reimpresión" || plate.name === "Plancha adicional") {
    plate.name = reprint ? "Reimpresión" : "Plancha adicional";
  }
});

// Costo estimado de la plancha (material + depreciación + energía), con la misma
// calculadora del servidor.
const plateCost = ref(null);
let seq = 0;
watch(
  () => JSON.stringify(platesPayload([plate])[0]),
  async () => {
    const payload = platesPayload([plate])[0];
    const current = ++seq;
    if (!payload.printer_id) {
      plateCost.value = null;
      return;
    }
    try {
      const q = await calculatorApi.computeQuote({
        printer_id: payload.printer_id,
        filaments: payload.filaments,
        print_hours: payload.print_hours,
      });
      if (current === seq) plateCost.value = Number(q.breakdown.margin_base_cost);
    } catch {
      if (current === seq) plateCost.value = null;
    }
  },
  { immediate: true }
);
const profitAfter = computed(() => (plateCost.value === null ? null : Number(props.sale.profit) - plateCost.value));

const saving = ref(false);
const error = ref("");

async function save() {
  error.value = platesError([plate]).replace("la plancha 2", "la plancha");
  if (error.value) return;
  saving.value = true;
  try {
    const updated = await salesApi.addSalePlate(props.sale.id, { ...platesPayload([plate])[0], is_reprint: isReprint.value });
    emit("saved", updated);
  } catch (err) {
    error.value = extractApiError(err, "No se pudo agregar la plancha.");
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Modal persistent title="Agregar plancha" :subtitle="sale.client_name" width="640px" @close="emit('close')">
    <form @submit.prevent="save">
      <div class="plate-kind">
        <label class="plate-kind-option" :class="{ selected: isReprint }">
          <input v-model="isReprint" type="radio" :value="true" />
          <span>
            <strong>Reimpresión por fallo</strong>
            <span class="text-muted text-sm">Piezas que salieron mal y hubo que imprimir de nuevo.</span>
          </span>
        </label>
        <label class="plate-kind-option" :class="{ selected: !isReprint }">
          <input v-model="isReprint" type="radio" :value="false" />
          <span>
            <strong>Plancha adicional</strong>
            <span class="text-muted text-sm">Otra parte del mismo producto (ej. los llaveros del portallaveros).</span>
          </span>
        </label>
      </div>

      <PlateFields v-model="plate" :printers="printers" :filaments="filaments" class="mt-4" />

      <div v-if="plateCost !== null" class="alert alert-info mt-4">
        <span>
          Costo de esta plancha: <strong>{{ formatCurrency(plateCost) }}</strong>. El precio no cambia: la ganancia del
          pedido pasa de {{ formatCurrency(sale.profit) }} a
          <strong :style="{ color: profitAfter < 0 ? 'var(--danger)' : undefined }">{{ formatCurrency(profitAfter) }}</strong>.
        </span>
      </div>
      <div v-if="error" class="alert alert-danger mt-4">{{ error }}</div>

      <div class="form-actions">
        <button type="button" class="btn btn-secondary" @click="emit('close')">Cancelar</button>
        <button type="submit" class="btn btn-primary" :disabled="saving">{{ saving ? "Guardando..." : "Agregar plancha" }}</button>
      </div>
    </form>
  </Modal>
</template>

<style scoped>
.plate-kind {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.plate-kind-option {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  margin: 0;
}

.plate-kind-option input {
  width: auto;
  margin-top: 3px;
}

.plate-kind-option > span {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.plate-kind-option.selected {
  border-color: var(--primary);
  background: var(--primary-soft);
}

@media (max-width: 560px) {
  .plate-kind {
    grid-template-columns: 1fr;
  }
}
</style>
