<script setup>
import PlateFields from "./PlateFields.vue";
import Icon from "./Icon.vue";

// Planchas adicionales de un pedido nuevo (la principal es la impresora/horas/filamentos
// del formulario). Ej: el portallaveros en una plancha y los llaveros en otra.
const plates = defineModel({ type: Array, required: true });
const props = defineProps({
  printers: { type: Array, required: true },
  filaments: { type: Array, required: true },
  defaultPrinterId: { type: String, default: "" },
  disabled: { type: Boolean, default: false },
});

function addPlate() {
  plates.value.push({
    key: crypto.randomUUID(),
    name: `Plancha ${plates.value.length + 2}`,
    printer_id: props.defaultPrinterId || "",
    print_hours: 0,
    filaments: [],
  });
}

function removePlate(key) {
  plates.value = plates.value.filter((p) => p.key !== key);
}
</script>

<template>
  <div class="extra-plates">
    <div class="extra-plates-head">
      <div>
        <strong>Planchas adicionales</strong>
        <span class="field-hint">
          Si el producto se imprime en más de una plancha (incluso en otra impresora). Lo de arriba es la plancha 1.
        </span>
      </div>
      <button type="button" class="btn btn-secondary btn-sm" :disabled="disabled" @click="addPlate">
        <Icon name="plus" :size="14" /> Agregar plancha
      </button>
    </div>
    <div v-for="(p, i) in plates" :key="p.key" class="extra-plate-card">
      <div class="extra-plate-title">
        <span class="badge badge-neutral">Plancha {{ i + 2 }}</span>
        <button type="button" class="btn btn-icon btn-ghost btn-sm" aria-label="Quitar plancha" @click="removePlate(p.key)">
          <Icon name="trash" :size="14" />
        </button>
      </div>
      <PlateFields v-model="plates[i]" :printers="printers" :filaments="filaments" />
    </div>
  </div>
</template>

<style scoped>
.extra-plates {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-md);
}

.extra-plates-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.extra-plates-head .field-hint {
  display: block;
}

.extra-plate-card {
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
}

.extra-plate-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
</style>
