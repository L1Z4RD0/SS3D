<script setup>
import { ref, onMounted, reactive } from "vue";
import * as inventoryApi from "../api/inventory";
import { formatCurrency, formatNumber, formatPercent, formatDate } from "../utils/format";
import { confirmAction } from "../composables/useConfirm";
import { todayISO } from "../utils/format";
import Modal from "../components/Modal.vue";
import Icon from "../components/Icon.vue";

const tab = ref("filaments");

const filaments = ref([]);
const supplies = ref([]);
const loadingFilaments = ref(true);
const loadingSupplies = ref(true);

const statusLabels = { disponible: "Disponible", alerta: "Alerta", critico: "Crítico", vacio: "Vacío" };
const statusBadge = { disponible: "badge-success", alerta: "badge-warning", critico: "badge-danger", vacio: "badge-danger" };

async function loadFilaments() {
  loadingFilaments.value = true;
  try {
    filaments.value = await inventoryApi.listFilaments();
  } finally {
    loadingFilaments.value = false;
  }
}

async function loadSupplies() {
  loadingSupplies.value = true;
  try {
    supplies.value = await inventoryApi.listSupplies();
  } finally {
    loadingSupplies.value = false;
  }
}

onMounted(() => {
  loadFilaments();
  loadSupplies();
});

/* -------- Filaments -------- */
const showFilamentModal = ref(false);
const editingFilamentId = ref(null);
const filamentSaving = ref(false);
const filamentError = ref("");
const emptyFilamentForm = () => ({
  brand: "",
  type: "PLA",
  color: "",
  entry_date: todayISO(),
  spool_weight_g: 1000,
  initial_stock_g: null,
  min_alert_g: 100,
  spool_price: null,
});
const filamentForm = reactive(emptyFilamentForm());

function openCreateFilament() {
  editingFilamentId.value = null;
  Object.assign(filamentForm, emptyFilamentForm());
  filamentError.value = "";
  showFilamentModal.value = true;
}

function openEditFilament(f) {
  editingFilamentId.value = f.id;
  Object.assign(filamentForm, {
    brand: f.brand,
    type: f.type,
    color: f.color,
    entry_date: f.entry_date,
    spool_weight_g: Number(f.spool_weight_g),
    initial_stock_g: Number(f.initial_stock_g),
    min_alert_g: Number(f.min_alert_g),
    spool_price: Number(f.spool_price),
  });
  filamentError.value = "";
  showFilamentModal.value = true;
}

async function submitFilament() {
  filamentSaving.value = true;
  filamentError.value = "";
  try {
    if (editingFilamentId.value) {
      await inventoryApi.updateFilament(editingFilamentId.value, filamentForm);
    } else {
      await inventoryApi.createFilament(filamentForm);
    }
    showFilamentModal.value = false;
    await loadFilaments();
  } catch (err) {
    filamentError.value = err.response?.data?.detail || "No se pudo guardar el filamento";
  } finally {
    filamentSaving.value = false;
  }
}

async function deleteFilament(f) {
  const ok = await confirmAction({
    title: "Eliminar filamento",
    message: `¿Eliminar "${f.brand} ${f.color}"? Si tiene ventas asociadas, se desactivará.`,
    confirmLabel: "Eliminar",
    danger: true,
  });
  if (!ok) return;
  await inventoryApi.deleteFilament(f.id);
  await loadFilaments();
}

/* -------- Supplies -------- */
const showSupplyModal = ref(false);
const editingSupplyId = ref(null);
const supplySaving = ref(false);
const supplyError = ref("");
const emptySupplyForm = () => ({ name: "", category: "", quantity_available: null, min_alert_qty: null, unit_cost: null });
const supplyForm = reactive(emptySupplyForm());

function openCreateSupply() {
  editingSupplyId.value = null;
  Object.assign(supplyForm, emptySupplyForm());
  supplyError.value = "";
  showSupplyModal.value = true;
}

function openEditSupply(s) {
  editingSupplyId.value = s.id;
  Object.assign(supplyForm, {
    name: s.name,
    category: s.category,
    quantity_available: Number(s.quantity_available),
    min_alert_qty: s.min_alert_qty !== null ? Number(s.min_alert_qty) : null,
    unit_cost: s.unit_cost !== null ? Number(s.unit_cost) : null,
  });
  supplyError.value = "";
  showSupplyModal.value = true;
}

async function submitSupply() {
  supplySaving.value = true;
  supplyError.value = "";
  try {
    if (editingSupplyId.value) {
      await inventoryApi.updateSupply(editingSupplyId.value, supplyForm);
    } else {
      await inventoryApi.createSupply(supplyForm);
    }
    showSupplyModal.value = false;
    await loadSupplies();
  } catch (err) {
    supplyError.value = err.response?.data?.detail || "No se pudo guardar el insumo";
  } finally {
    supplySaving.value = false;
  }
}

async function deleteSupply(s) {
  const ok = await confirmAction({
    title: "Eliminar insumo",
    message: `¿Eliminar "${s.name}"? Si tiene ventas asociadas, se desactivará.`,
    confirmLabel: "Eliminar",
    danger: true,
  });
  if (!ok) return;
  await inventoryApi.deleteSupply(s.id);
  await loadSupplies();
}
</script>

<template>
  <div>
    <div class="page-header">
      <p class="page-subtitle">Stock de filamentos e insumos, con alertas automáticas de nivel mínimo</p>
    </div>

    <div class="tabs">
      <button class="tab-btn" :class="{ active: tab === 'filaments' }" @click="tab = 'filaments'">Filamentos</button>
      <button class="tab-btn" :class="{ active: tab === 'supplies' }" @click="tab = 'supplies'">Insumos</button>
    </div>

    <div v-if="tab === 'filaments'" class="card">
      <div class="card-header">
        <h3>Filamentos</h3>
        <button class="btn btn-primary btn-sm" @click="openCreateFilament">
          <Icon name="plus" :size="15" /> Nuevo filamento
        </button>
      </div>

      <div v-if="loadingFilaments" class="empty-state">Cargando...</div>
      <div v-else-if="!filaments.length" class="empty-state">
        <h3>Sin filamentos registrados</h3>
        <p>Agrega tu primer carrete para empezar a llevar el stock.</p>
      </div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Filamento</th>
              <th>Ingreso</th>
              <th class="text-right">Disponible</th>
              <th class="text-right">% stock</th>
              <th>Estado</th>
              <th class="text-right">Precio carrete</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="f in filaments" :key="f.id">
              <td>
                <strong>{{ f.brand }} · {{ f.color }}</strong>
                <div class="text-muted text-sm">{{ f.type }}</div>
              </td>
              <td>{{ formatDate(f.entry_date) }}</td>
              <td class="text-right mono">{{ formatNumber(f.available_g, 0) }} g</td>
              <td class="text-right mono">{{ formatPercent(f.stock_percent) }}</td>
              <td><span class="badge" :class="statusBadge[f.stock_status]">{{ statusLabels[f.stock_status] }}</span></td>
              <td class="text-right mono">{{ formatCurrency(f.spool_price) }}</td>
              <td class="text-right">
                <div class="flex gap-2" style="justify-content: flex-end">
                  <button class="btn btn-icon btn-ghost" @click="openEditFilament(f)"><Icon name="edit" :size="16" /></button>
                  <button class="btn btn-icon btn-ghost" @click="deleteFilament(f)"><Icon name="trash" :size="16" /></button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-else class="card">
      <div class="card-header">
        <h3>Insumos y accesorios</h3>
        <button class="btn btn-primary btn-sm" @click="openCreateSupply">
          <Icon name="plus" :size="15" /> Nuevo insumo
        </button>
      </div>

      <div v-if="loadingSupplies" class="empty-state">Cargando...</div>
      <div v-else-if="!supplies.length" class="empty-state">
        <h3>Sin insumos registrados</h3>
        <p>Agrega argollas, imanes, pegamento u otros consumibles.</p>
      </div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Insumo</th>
              <th>Categoría</th>
              <th class="text-right">Cantidad disponible</th>
              <th class="text-right">Costo unitario</th>
              <th>Estado</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in supplies" :key="s.id">
              <td><strong>{{ s.name }}</strong></td>
              <td>{{ s.category }}</td>
              <td class="text-right mono">{{ formatNumber(s.quantity_available, 0) }}</td>
              <td class="text-right mono">{{ s.unit_cost !== null ? formatCurrency(s.unit_cost) : "-" }}</td>
              <td>
                <span v-if="s.low_stock" class="badge badge-warning">Stock bajo</span>
                <span v-else class="badge badge-success">OK</span>
              </td>
              <td class="text-right">
                <div class="flex gap-2" style="justify-content: flex-end">
                  <button class="btn btn-icon btn-ghost" @click="openEditSupply(s)"><Icon name="edit" :size="16" /></button>
                  <button class="btn btn-icon btn-ghost" @click="deleteSupply(s)"><Icon name="trash" :size="16" /></button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <Modal v-if="showFilamentModal" :title="editingFilamentId ? 'Editar filamento' : 'Nuevo filamento'" @close="showFilamentModal = false">
      <form @submit.prevent="submitFilament">
        <div class="form-grid">
          <div class="field">
            <label>Marca</label>
            <input v-model="filamentForm.brand" required />
          </div>
          <div class="field">
            <label>Tipo</label>
            <input v-model="filamentForm.type" placeholder="PLA, PETG, ABS..." required />
          </div>
          <div class="field">
            <label>Color</label>
            <input v-model="filamentForm.color" required />
          </div>
          <div class="field">
            <label>Fecha de ingreso</label>
            <input v-model="filamentForm.entry_date" type="date" required />
          </div>
          <div class="field">
            <label>Peso del carrete (g)</label>
            <input v-model.number="filamentForm.spool_weight_g" type="number" min="1" step="1" required />
          </div>
          <div class="field">
            <label>Precio del carrete (CLP)</label>
            <input v-model.number="filamentForm.spool_price" type="number" min="0" step="1" required />
          </div>
          <div class="field">
            <label>Stock inicial (g)</label>
            <input v-model.number="filamentForm.initial_stock_g" type="number" min="0" step="1" required />
          </div>
          <div class="field">
            <label>Alerta mínima (g)</label>
            <input v-model.number="filamentForm.min_alert_g" type="number" min="0" step="1" required />
          </div>
        </div>

        <div v-if="filamentError" class="alert alert-danger mt-4">{{ filamentError }}</div>

        <div class="form-actions">
          <button type="button" class="btn btn-secondary" @click="showFilamentModal = false">Cancelar</button>
          <button type="submit" class="btn btn-primary" :disabled="filamentSaving">
            {{ filamentSaving ? "Guardando..." : "Guardar" }}
          </button>
        </div>
      </form>
    </Modal>

    <Modal v-if="showSupplyModal" :title="editingSupplyId ? 'Editar insumo' : 'Nuevo insumo'" @close="showSupplyModal = false">
      <form @submit.prevent="submitSupply">
        <div class="form-grid">
          <div class="field">
            <label>Nombre</label>
            <input v-model="supplyForm.name" required />
          </div>
          <div class="field">
            <label>Categoría</label>
            <input v-model="supplyForm.category" placeholder="Argollas, imanes, pegamento..." required />
          </div>
          <div class="field">
            <label>Cantidad disponible</label>
            <input v-model.number="supplyForm.quantity_available" type="number" min="0" step="1" required />
          </div>
          <div class="field">
            <label>Alerta mínima</label>
            <input v-model.number="supplyForm.min_alert_qty" type="number" min="0" step="1" />
          </div>
          <div class="field">
            <label>Costo unitario (CLP)</label>
            <input v-model.number="supplyForm.unit_cost" type="number" min="0" step="1" />
          </div>
        </div>

        <div v-if="supplyError" class="alert alert-danger mt-4">{{ supplyError }}</div>

        <div class="form-actions">
          <button type="button" class="btn btn-secondary" @click="showSupplyModal = false">Cancelar</button>
          <button type="submit" class="btn btn-primary" :disabled="supplySaving">
            {{ supplySaving ? "Guardando..." : "Guardar" }}
          </button>
        </div>
      </form>
    </Modal>
  </div>
</template>
