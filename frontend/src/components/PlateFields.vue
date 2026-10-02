<script setup>
import { ref } from "vue";
import { GRAMS_MAX, isValidGrams, gramsErrorMessage } from "../utils/validation";
import FilamentPickerModal from "./FilamentPickerModal.vue";
import Icon from "./Icon.vue";
import HoursMinutesInput from "./HoursMinutesInput.vue";

// Datos de UNA plancha: nombre, impresora, horas y filamentos. El objeto se edita en el
// lugar: { name, printer_id, print_hours, filaments: [{ filament_id, grams_used }] }.
const plate = defineModel({ type: Object, required: true });
defineProps({
  printers: { type: Array, required: true },
  filaments: { type: Array, required: true },
  namePlaceholder: { type: String, default: "Ej: Llaveros" },
});

const showPicker = ref(false);
const pickedId = ref("");
const grams = ref(null);
const rowError = ref("");

function filamentLabel(id, list) {
  const f = list.find((x) => x.id === id);
  if (!f) return "Filamento";
  return f.sku ? `${f.brand} · ${f.color} — ${f.sku}` : `${f.brand} · ${f.color}`;
}

function addFilament() {
  rowError.value = "";
  if (!pickedId.value) {
    rowError.value = "Selecciona un filamento.";
    return;
  }
  if (!isValidGrams(grams.value)) {
    rowError.value = gramsErrorMessage(grams.value);
    return;
  }
  const g = Number(grams.value);
  const existing = plate.value.filaments.find((r) => r.filament_id === pickedId.value);
  if (existing) existing.grams_used = Number(existing.grams_used) + g;
  else plate.value.filaments.push({ filament_id: pickedId.value, grams_used: g });
  pickedId.value = "";
  grams.value = null;
}

function removeFilament(id) {
  plate.value.filaments = plate.value.filaments.filter((r) => r.filament_id !== id);
}
</script>

<template>
  <div class="plate-fields">
    <div class="plate-grid">
      <div class="field">
        <label>Nombre de la plancha</label>
        <input v-model="plate.name" maxlength="80" :placeholder="namePlaceholder" required />
      </div>
      <div class="field">
        <label>Impresora</label>
        <select v-model="plate.printer_id" required>
          <option value="" disabled>Selecciona</option>
          <option v-for="p in printers" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
      </div>
      <div class="field plate-time">
        <label>Tiempo de impresión</label>
        <HoursMinutesInput v-model="plate.print_hours" />
      </div>
    </div>
    <div class="field mt-2">
      <label>Filamentos de esta plancha</label>
      <div class="flex gap-2 plate-filament-row">
        <button type="button" class="btn btn-secondary plate-picker-btn" @click="showPicker = true">
          <span v-if="pickedId">{{ filamentLabel(pickedId, filaments) }}</span>
          <span v-else class="text-muted">Selecciona un filamento</span>
        </button>
        <input v-model.number="grams" class="plate-grams" type="number" min="0.01" :max="GRAMS_MAX" step="0.01" placeholder="Gramos" />
        <button type="button" class="btn btn-secondary btn-sm" @click="addFilament">Agregar</button>
      </div>
      <div v-if="rowError" class="alert alert-danger mt-2">{{ rowError }}</div>
      <div v-if="plate.filaments.length" class="flex flex-col gap-2 mt-2">
        <div v-for="row in plate.filaments" :key="row.filament_id" class="plate-row text-sm">
          <span>{{ filamentLabel(row.filament_id, filaments) }} · {{ row.grams_used }} g</span>
          <button type="button" class="btn btn-icon btn-ghost btn-sm" aria-label="Quitar filamento" @click="removeFilament(row.filament_id)">
            <Icon name="close" :size="13" />
          </button>
        </div>
      </div>
    </div>

    <FilamentPickerModal
      v-if="showPicker"
      :filaments="filaments"
      :exclude-ids="plate.filaments.map((r) => r.filament_id)"
      title="Filamento de la plancha"
      @select="(f) => { pickedId = f.id; showPicker = false; }"
      @close="showPicker = false"
    />
  </div>
</template>

<style scoped>
/* Nombre e impresora arriba; el tiempo en su propia fila para que horas y minutos tengan
   espacio de sobra (en la ventana de venta la plancha es angosta). */
.plate-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.plate-time {
  grid-column: 1 / -1;
  max-width: 340px;
}

.plate-grams {
  width: 120px;
  flex-shrink: 0;
}

.plate-picker-btn {
  flex: 1;
  justify-content: flex-start;
  overflow: hidden;
}

.plate-picker-btn span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plate-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  border-radius: 8px;
  background: var(--surface-alt);
}

@media (max-width: 640px) {
  .plate-grid {
    grid-template-columns: 1fr;
  }

  .plate-time {
    max-width: none;
  }

  /* En celular el filamento va en su propia línea y debajo los gramos + Agregar. */
  .plate-filament-row {
    flex-wrap: wrap;
  }

  .plate-picker-btn {
    flex-basis: 100%;
  }

  .plate-grams {
    width: auto;
    flex: 1;
  }
}
</style>
