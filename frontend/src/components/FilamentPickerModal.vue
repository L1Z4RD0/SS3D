<script setup>
import { ref, computed, onMounted, nextTick } from "vue";
import { formatNumber } from "../utils/format";
import { useFilamentCatalog, swatchFor } from "../composables/useFilamentCatalog";
import Modal from "./Modal.vue";
import Icon from "./Icon.vue";
import FilamentSpoolIcon from "./FilamentSpoolIcon.vue";

const props = defineProps({
  filaments: { type: Array, required: true },
  excludeIds: { type: Array, default: () => [] },
  title: { type: String, default: "Seleccionar filamento" },
  subtitle: { type: String, default: "Elige el filamento que deseas usar en tu impresión." },
  // { owner_id: username } — solo para el observador, que ve filamentos de varios
  // usuarios y necesita saber de quién es cada uno. Vacío = no se muestra dueño.
  ownerNames: { type: Object, default: () => ({}) },
});
const emit = defineEmits(["select", "close"]);

const search = ref("");
const materialFilter = ref("");
const ownerFilter = ref("");

const showOwners = computed(() => Object.keys(props.ownerNames).length > 0);
function ownerOf(f) {
  return props.ownerNames[f.owner_id] || "usuario desconocido";
}
const selectedId = ref("");
const { ensureFilamentCatalog } = useFilamentCatalog();

const searchInput = ref(null);

onMounted(() => {
  // Se puede escribir apenas se abre, sin tener que hacer clic en el buscador. El atributo
  // autofocus no sirve en ventanas que aparecen después de cargar la página. En pantallas
  // táctiles no se enfoca, para que el teclado no tape la lista de filamentos.
  if (window.matchMedia("(pointer: fine)").matches) nextTick(() => searchInput.value?.focus());
  // Swatches just fall back to a neutral dot if this fails; not worth blocking the picker over it.
  ensureFilamentCatalog().catch(() => {});
});


const excludeSet = computed(() => new Set(props.excludeIds));

// Agotados (0g) nunca son elegibles aquí, igual que en los selectores que reemplaza.
const pickableFilaments = computed(() =>
  props.filaments.filter((f) => Number(f.available_g) > 0 && !excludeSet.value.has(f.id))
);

const materials = computed(() => [...new Set(pickableFilaments.value.map((f) => f.type))].sort());

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase();
  return pickableFilaments.value.filter((f) => {
    if (materialFilter.value && f.type !== materialFilter.value) return false;
    if (ownerFilter.value && f.owner_id !== ownerFilter.value) return false;
    if (!q) return true;
    const fields = [f.brand, f.type, f.color, f.sku];
    if (showOwners.value) fields.push(ownerOf(f));
    return fields.filter(Boolean).some((v) => String(v).toLowerCase().includes(q));
  });
});

function confirm() {
  const chosen = pickableFilaments.value.find((f) => f.id === selectedId.value);
  if (chosen) emit("select", chosen);
}
</script>

<template>
  <Modal :title="title" :subtitle="subtitle" width="720px" @close="emit('close')">
    <template #icon>
      <div class="picker-header-icon">
        <Icon name="spool" :size="18" />
      </div>
    </template>

    <div class="flex gap-2 picker-toolbar">
      <div class="field" style="flex: 1; margin: 0">
        <input
          ref="searchInput"
          v-model="search"
          type="text"
          :placeholder="showOwners ? 'Buscar por nombre, SKU o dueño...' : 'Buscar por nombre o SKU...'"
        />
      </div>
      <div v-if="showOwners" class="picker-filter">
        <Icon name="users" :size="14" />
        <select v-model="ownerFilter" aria-label="Filtrar por dueño">
          <option value="">Todos los dueños</option>
          <option v-for="(name, id) in ownerNames" :key="id" :value="id">{{ name }}</option>
        </select>
      </div>
      <div class="picker-filter">
        <Icon name="filter" :size="14" />
        <select v-model="materialFilter">
          <option value="">Todos los filamentos</option>
          <option v-for="m in materials" :key="m" :value="m">{{ m }}</option>
        </select>
      </div>
    </div>

    <div v-if="!pickableFilaments.length" class="alert alert-info mt-3">
      No hay filamentos con stock disponible para elegir. Los agotados (0g) no se pueden usar en un nuevo trabajo.
    </div>
    <div v-else-if="!filtered.length" class="alert alert-info mt-3">
      Ningún filamento coincide con la búsqueda.
    </div>
    <div v-else class="picker-grid mt-3">
      <button
        type="button"
        v-for="f in filtered"
        :key="f.id"
        class="picker-card"
        :class="{ selected: selectedId === f.id }"
        @click="selectedId = f.id"
      >
        <div class="picker-card-image">
          <FilamentSpoolIcon :color="swatchFor(f)" :size="90" />
          <span v-if="selectedId === f.id" class="picker-check"><Icon name="check" :size="12" /></span>
        </div>
        <span v-if="showOwners" class="picker-card-owner">De {{ ownerOf(f) }}</span>
        <strong class="picker-card-title">{{ f.brand }} · {{ f.type }}</strong>
        <span v-if="f.sku" class="text-muted text-sm">SKU: {{ f.sku }}</span>
        <span class="picker-card-color">
          <span class="color-dot-sm" :style="{ background: swatchFor(f) }"></span>
          {{ f.color }}
        </span>
        <span class="picker-card-stock">
          <Icon name="lock" :size="12" />
          {{ formatNumber(f.available_g, 0) }} g
        </span>
      </button>
    </div>

    <div class="picker-footer mt-4">
      <span class="text-muted text-sm">
        <Icon name="spool" :size="14" /> {{ pickableFilaments.length }} filamento(s) disponible(s)
      </span>
      <div class="flex gap-2">
        <button type="button" class="btn btn-secondary" @click="emit('close')">Cancelar</button>
        <button type="button" class="btn btn-primary" :disabled="!selectedId" @click="confirm">Seleccionar</button>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
.picker-header-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--primary), var(--accent));
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.picker-filter {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-alt);
  color: var(--text-muted);
  flex-shrink: 0;
}

.picker-filter select {
  border: none;
  background: transparent;
  padding: 10px 0;
  color: var(--text);
}

.picker-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  max-height: 440px;
  overflow-y: auto;
  padding: 2px;
}

.picker-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--surface-alt);
  cursor: pointer;
  text-align: left;
  font: inherit;
  color: inherit;
  transition: border-color 0.1s ease, background 0.1s ease;
}

.picker-card:hover {
  border-color: var(--primary);
}

.picker-card.selected {
  border-color: var(--primary);
  background: var(--primary-soft);
}

.picker-card-image {
  position: relative;
  margin-bottom: 6px;
}

.picker-check {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid var(--surface-alt);
}

.picker-card-title {
  font-size: 0.92rem;
}

.picker-card-owner {
  max-width: 100%;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--primary-soft);
  color: var(--primary);
  font-size: 0.72rem;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.picker-toolbar {
  flex-wrap: wrap;
}

.picker-card-color {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.85rem;
  color: var(--text-muted);
}

.color-dot-sm {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 1px solid var(--border);
  flex-shrink: 0;
}

.picker-card-stock {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 6px;
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--success);
}

.picker-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.picker-footer .text-muted {
  display: flex;
  align-items: center;
  gap: 6px;
}

@media (max-width: 640px) {
  .picker-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
