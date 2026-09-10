<script setup>
import { ref, onMounted, reactive } from "vue";
import * as printersApi from "../api/printers";
import { formatCurrency, formatNumber, formatPercent } from "../utils/format";
import { isValidNumber, extractApiError } from "../utils/validation";
import { confirmAction } from "../composables/useConfirm";
import Modal from "../components/Modal.vue";
import Icon from "../components/Icon.vue";

const printers = ref([]);
const loading = ref(true);
const showModal = ref(false);
const editingId = ref(null);
const saving = ref(false);
const errorMessage = ref("");

const emptyForm = () => ({ name: "", purchase_value: null, lifetime_hours: null, power_kw: null });
const form = reactive(emptyForm());

async function load() {
  loading.value = true;
  try {
    printers.value = await printersApi.listPrinters();
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  editingId.value = null;
  Object.assign(form, emptyForm());
  errorMessage.value = "";
  showModal.value = true;
}

function openEdit(printer) {
  editingId.value = printer.id;
  Object.assign(form, {
    name: printer.name,
    purchase_value: Number(printer.purchase_value),
    lifetime_hours: Number(printer.lifetime_hours),
    power_kw: Number(printer.power_kw),
  });
  errorMessage.value = "";
  showModal.value = true;
}

function validatePrinterForm() {
  if (!isValidNumber(form.purchase_value, { min: 0, allowZero: false })) {
    return "El valor de compra debe ser mayor a 0.";
  }
  if (!isValidNumber(form.lifetime_hours, { min: 0, allowZero: false })) {
    return "Las horas de vida útil deben ser mayores a 0.";
  }
  if (!isValidNumber(form.power_kw, { min: 0, allowZero: false })) {
    return "La potencia debe ser mayor a 0.";
  }
  return "";
}

async function handleSubmit() {
  const validationError = validatePrinterForm();
  if (validationError) {
    errorMessage.value = validationError;
    return;
  }
  saving.value = true;
  errorMessage.value = "";
  try {
    if (editingId.value) {
      await printersApi.updatePrinter(editingId.value, form);
    } else {
      await printersApi.createPrinter(form);
    }
    showModal.value = false;
    await load();
  } catch (err) {
    errorMessage.value = extractApiError(err, "No se pudo guardar la impresora.");
  } finally {
    saving.value = false;
  }
}

async function handleDelete(printer) {
  const ok = await confirmAction({
    title: "Eliminar impresora",
    message: `¿Eliminar "${printer.name}"? Si tiene ventas asociadas, se desactivará en lugar de borrarse.`,
    confirmLabel: "Eliminar",
    danger: true,
  });
  if (!ok) return;
  await printersApi.deletePrinter(printer.id);
  await load();
}

onMounted(load);
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <p class="page-subtitle">Ficha técnica, depreciación y vida útil de cada impresora</p>
      </div>
      <button class="btn btn-primary" @click="openCreate">
        <Icon name="plus" :size="16" />
        Nueva impresora
      </button>
    </div>

    <div class="card">
      <div v-if="loading" class="empty-state">Cargando...</div>
      <div v-else-if="!printers.length" class="empty-state">
        <h3>Aún no tienes impresoras</h3>
        <p>Agrega tu primera impresora para empezar a calcular depreciación y costos.</p>
      </div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Impresora</th>
              <th class="text-right">Valor compra</th>
              <th class="text-right">Vida útil (h)</th>
              <th class="text-right">Horas usadas</th>
              <th class="text-right">% vida usada</th>
              <th class="text-right">Depreciación/h</th>
              <th class="text-right">Potencia</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in printers" :key="p.id">
              <td>
                <strong>{{ p.name }}</strong>
                <span v-if="!p.is_active" class="badge badge-neutral" style="margin-left: 8px">Inactiva</span>
              </td>
              <td class="text-right mono">{{ formatCurrency(p.purchase_value) }}</td>
              <td class="text-right mono">{{ formatNumber(p.lifetime_hours, 0) }}</td>
              <td class="text-right mono">{{ formatNumber(p.hours_used, 1) }}</td>
              <td class="text-right">
                <span
                  class="badge"
                  :class="p.life_used_percent >= 90 ? 'badge-danger' : p.life_used_percent >= 70 ? 'badge-warning' : 'badge-success'"
                >
                  {{ formatPercent(p.life_used_percent) }}
                </span>
              </td>
              <td class="text-right mono">{{ formatCurrency(p.depreciation_cost_per_hour) }}</td>
              <td class="text-right mono">{{ formatNumber(p.power_kw, 3) }} kW</td>
              <td class="text-right">
                <div class="flex gap-2" style="justify-content: flex-end">
                  <button class="btn btn-icon btn-ghost" @click="openEdit(p)"><Icon name="edit" :size="16" /></button>
                  <button class="btn btn-icon btn-ghost" @click="handleDelete(p)"><Icon name="trash" :size="16" /></button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <Modal v-if="showModal" :title="editingId ? 'Editar impresora' : 'Nueva impresora'" @close="showModal = false">
      <form @submit.prevent="handleSubmit">
        <div class="flex flex-col gap-3">
          <div class="field">
            <label>Nombre / modelo</label>
            <input v-model="form.name" required placeholder="Ej: Ender 3 V2" />
          </div>
          <div class="form-grid">
            <div class="field">
              <label>Valor de compra (CLP)</label>
              <input v-model.number="form.purchase_value" type="number" min="0" step="1" required />
            </div>
            <div class="field">
              <label>Horas de vida útil</label>
              <input v-model.number="form.lifetime_hours" type="number" min="0" step="1" required />
            </div>
            <div class="field">
              <label>Potencia (kW)</label>
              <input v-model.number="form.power_kw" type="number" min="0.001" step="0.001" required />
              <span class="field-hint">Ej: 0.2 kW = 200 W</span>
            </div>
          </div>
        </div>

        <div v-if="errorMessage" class="alert alert-danger mt-4">{{ errorMessage }}</div>

        <div class="form-actions">
          <button type="button" class="btn btn-secondary" @click="showModal = false">Cancelar</button>
          <button type="submit" class="btn btn-primary" :disabled="saving">
            {{ saving ? "Guardando..." : "Guardar" }}
          </button>
        </div>
      </form>
    </Modal>
  </div>
</template>
