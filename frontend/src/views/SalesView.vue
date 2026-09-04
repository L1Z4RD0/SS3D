<script setup>
import { ref, reactive, onMounted, computed } from "vue";
import * as salesApi from "../api/sales";
import * as printersApi from "../api/printers";
import * as inventoryApi from "../api/inventory";
import { PAYMENT_METHODS } from "../api/sales";
import { formatCurrency, formatPercent, formatDate, todayISO } from "../utils/format";
import { confirmAction } from "../composables/useConfirm";
import Modal from "../components/Modal.vue";
import Icon from "../components/Icon.vue";

const sales = ref([]);
const total = ref(0);
const loading = ref(true);
const limit = 20;
const offset = ref(0);

const printers = ref([]);
const filaments = ref([]);
const supplies = ref([]);

const filters = reactive({ date_from: "", date_to: "", client: "", printer_id: "", payment_method: "", search: "" });

const paymentLabel = (v) => PAYMENT_METHODS.find((p) => p.value === v)?.label || v;

async function loadCatalog() {
  const [p, f, s] = await Promise.all([
    printersApi.listPrinters(),
    inventoryApi.listFilaments(),
    inventoryApi.listSupplies(),
  ]);
  printers.value = p;
  filaments.value = f;
  supplies.value = s;
}

async function loadSales() {
  loading.value = true;
  try {
    const params = { limit, offset: offset.value };
    Object.entries(filters).forEach(([k, v]) => {
      if (v) params[k] = v;
    });
    const page = await salesApi.listSales(params);
    sales.value = page.items;
    total.value = page.total;
  } finally {
    loading.value = false;
  }
}

function applyFilters() {
  offset.value = 0;
  loadSales();
}

function resetFilters() {
  Object.assign(filters, { date_from: "", date_to: "", client: "", printer_id: "", payment_method: "", search: "" });
  applyFilters();
}

function nextPage() {
  if (offset.value + limit < total.value) {
    offset.value += limit;
    loadSales();
  }
}
function prevPage() {
  if (offset.value > 0) {
    offset.value = Math.max(0, offset.value - limit);
    loadSales();
  }
}

/* -------- Create / edit -------- */
const showModal = ref(false);
const editingId = ref(null);
const saving = ref(false);
const formError = ref("");

const supplyRows = ref([]);
const newSupplyId = ref("");
const newSupplyQty = ref(1);

const filamentRows = ref([]); // { id, filament_id, grams_used }
const newFilamentId = ref("");
const newFilamentGrams = ref(null);

const emptyForm = () => ({
  sale_date: todayISO(),
  client_name: "",
  buyer_name: "",
  printer_id: "",
  print_hours: 0,
  postprocess_hours: 0,
  base_price: null,
  shipping_cost: 0,
  payment_method: "efectivo",
  notes: "",
});
const form = reactive(emptyForm());

function addFilamentRow() {
  if (!newFilamentId.value || !newFilamentGrams.value) return;
  filamentRows.value.push({
    id: crypto.randomUUID(),
    filament_id: newFilamentId.value,
    grams_used: Number(newFilamentGrams.value),
  });
  newFilamentId.value = "";
  newFilamentGrams.value = null;
}
function removeFilamentRow(id) {
  filamentRows.value = filamentRows.value.filter((r) => r.id !== id);
}
function filamentName(id) {
  const f = filaments.value.find((x) => x.id === id);
  return f ? filamentLabel(f) : "";
}
function filamentLabel(f) {
  return f.sku ? `${f.brand} · ${f.color} — ${f.sku}` : `${f.brand} · ${f.color}`;
}

function addSupplyRow() {
  if (!newSupplyId.value) return;
  const exists = supplyRows.value.find((r) => r.supply_id === newSupplyId.value);
  if (exists) {
    exists.quantity += Number(newSupplyQty.value) || 1;
  } else {
    supplyRows.value.push({ supply_id: newSupplyId.value, quantity: Number(newSupplyQty.value) || 1 });
  }
  newSupplyId.value = "";
  newSupplyQty.value = 1;
}
function removeSupplyRow(id) {
  supplyRows.value = supplyRows.value.filter((r) => r.supply_id !== id);
}
function supplyName(id) {
  return supplies.value.find((s) => s.id === id)?.name || "";
}

function openCreate() {
  editingId.value = null;
  Object.assign(form, emptyForm());
  supplyRows.value = [];
  filamentRows.value = [];
  formError.value = "";
  showModal.value = true;
}

function openEdit(sale) {
  editingId.value = sale.id;
  Object.assign(form, {
    sale_date: sale.sale_date,
    client_name: sale.client_name,
    buyer_name: sale.buyer_name || "",
    printer_id: sale.printer_id,
    print_hours: Number(sale.print_hours),
    postprocess_hours: Number(sale.postprocess_hours),
    base_price: Number(sale.base_price),
    shipping_cost: Number(sale.shipping_cost),
    payment_method: sale.payment_method,
    notes: sale.notes || "",
  });
  supplyRows.value = sale.supplies_used.map((s) => ({ supply_id: s.supply_id, quantity: Number(s.quantity_used) }));
  filamentRows.value = sale.filaments_used.map((f) => ({
    id: crypto.randomUUID(),
    filament_id: f.filament_id,
    grams_used: Number(f.grams_used),
  }));
  formError.value = "";
  showModal.value = true;
}

function buildPayload() {
  return {
    sale_date: form.sale_date,
    client_name: form.client_name,
    buyer_name: form.buyer_name || null,
    printer_id: form.printer_id,
    filaments: filamentRows.value.map((r) => ({ filament_id: r.filament_id, grams_used: r.grams_used })),
    print_hours: Number(form.print_hours) || 0,
    postprocess_hours: Number(form.postprocess_hours) || 0,
    base_price: Number(form.base_price) || 0,
    shipping_cost: Number(form.shipping_cost) || 0,
    supplies: supplyRows.value.map((r) => ({ supply_id: r.supply_id, quantity: r.quantity })),
    payment_method: form.payment_method,
    notes: form.notes || null,
  };
}

async function handleSubmit() {
  saving.value = true;
  formError.value = "";
  try {
    if (editingId.value) {
      await salesApi.updateSale(editingId.value, buildPayload());
    } else {
      await salesApi.createSale(buildPayload());
    }
    showModal.value = false;
    await loadSales();
  } catch (err) {
    formError.value = err.response?.data?.detail || "No se pudo guardar la venta";
  } finally {
    saving.value = false;
  }
}

async function handleDelete(sale) {
  const ok = await confirmAction({
    title: "Eliminar venta",
    message: `¿Eliminar la venta de "${sale.client_name}"? Esto restaurará el stock e impresora consumidos.`,
    confirmLabel: "Eliminar",
    danger: true,
  });
  if (!ok) return;
  await salesApi.deleteSale(sale.id);
  await loadSales();
}

const pageLabel = computed(() => {
  if (!total.value) return "0 resultados";
  const from = offset.value + 1;
  const to = Math.min(offset.value + limit, total.value);
  return `${from}-${to} de ${total.value}`;
});

onMounted(async () => {
  await loadCatalog();
  await loadSales();
});
</script>

<template>
  <div>
    <div class="page-header">
      <p class="page-subtitle">Historial de trabajos vendidos, con costos y ganancia calculados automáticamente</p>
      <button class="btn btn-primary" @click="openCreate">
        <Icon name="plus" :size="16" /> Nueva venta
      </button>
    </div>

    <div class="card" style="margin-bottom: 16px">
      <div class="grid grid-cols-4">
        <div class="field">
          <label>Desde</label>
          <input v-model="filters.date_from" type="date" />
        </div>
        <div class="field">
          <label>Hasta</label>
          <input v-model="filters.date_to" type="date" />
        </div>
        <div class="field">
          <label>Impresora</label>
          <select v-model="filters.printer_id">
            <option value="">Todas</option>
            <option v-for="p in printers" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>
        <div class="field">
          <label>Método de pago</label>
          <select v-model="filters.payment_method">
            <option value="">Todos</option>
            <option v-for="pm in PAYMENT_METHODS" :key="pm.value" :value="pm.value">{{ pm.label }}</option>
          </select>
        </div>
        <div class="field" style="grid-column: span 2">
          <label>Buscar (cliente, comprador, notas)</label>
          <input v-model="filters.search" placeholder="Buscar..." />
        </div>
        <div class="flex gap-2" style="align-items: flex-end">
          <button class="btn btn-primary" @click="applyFilters">Filtrar</button>
          <button class="btn btn-secondary" @click="resetFilters">Limpiar</button>
        </div>
      </div>
    </div>

    <div class="card">
      <div v-if="loading" class="empty-state">Cargando...</div>
      <div v-else-if="!sales.length" class="empty-state">
        <h3>No hay ventas</h3>
        <p>Ajusta los filtros o crea una venta nueva.</p>
      </div>
      <template v-else>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Cliente</th>
                <th>Impresora</th>
                <th class="text-right">Precio c/IVA</th>
                <th class="text-right">Ganancia</th>
                <th class="text-right">Margen</th>
                <th>Pago</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in sales" :key="s.id">
                <td>{{ formatDate(s.sale_date) }}</td>
                <td>
                  <strong>{{ s.client_name }}</strong>
                  <div v-if="s.buyer_name" class="text-muted text-sm">{{ s.buyer_name }}</div>
                </td>
                <td>{{ s.printer_name }}</td>
                <td class="text-right mono">{{ formatCurrency(s.total_price) }}</td>
                <td class="text-right mono" style="color: var(--success)">{{ formatCurrency(s.profit) }}</td>
                <td class="text-right">{{ formatPercent(s.margin_percent) }}</td>
                <td><span class="badge badge-neutral">{{ paymentLabel(s.payment_method) }}</span></td>
                <td class="text-right">
                  <div class="flex gap-2" style="justify-content: flex-end">
                    <button class="btn btn-icon btn-ghost" @click="openEdit(s)"><Icon name="edit" :size="16" /></button>
                    <button class="btn btn-icon btn-ghost" @click="handleDelete(s)"><Icon name="trash" :size="16" /></button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="flex items-center justify-between mt-4">
          <span class="text-muted text-sm">{{ pageLabel }}</span>
          <div class="flex gap-2">
            <button class="btn btn-secondary btn-sm" :disabled="offset === 0" @click="prevPage">Anterior</button>
            <button class="btn btn-secondary btn-sm" :disabled="offset + limit >= total" @click="nextPage">Siguiente</button>
          </div>
        </div>
      </template>
    </div>

    <Modal v-if="showModal" :title="editingId ? 'Editar venta' : 'Nueva venta'" width="680px" @close="showModal = false">
      <form @submit.prevent="handleSubmit">
        <div class="form-grid">
          <div class="field">
            <label>Fecha</label>
            <input v-model="form.sale_date" type="date" required />
          </div>
          <div class="field">
            <label>Método de pago</label>
            <select v-model="form.payment_method">
              <option v-for="pm in PAYMENT_METHODS" :key="pm.value" :value="pm.value">{{ pm.label }}</option>
            </select>
          </div>
          <div class="field">
            <label>Trabajo</label>
            <input v-model="form.client_name" required />
          </div>
          <div class="field">
            <label>Comprador (opcional)</label>
            <input v-model="form.buyer_name" />
          </div>
          <div class="field">
            <label>Impresora</label>
            <select v-model="form.printer_id" required>
              <option value="" disabled>Selecciona</option>
              <option v-for="p in printers" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </div>
          <div class="field">
            <label>Horas de impresión</label>
            <input v-model.number="form.print_hours" type="number" min="0" step="0.1" />
          </div>
          <div class="field">
            <label>Horas de postprocesado</label>
            <input v-model.number="form.postprocess_hours" type="number" min="0" step="0.1" />
          </div>
          <div class="field">
            <label>Envío / embalaje (CLP)</label>
            <input v-model.number="form.shipping_cost" type="number" min="0" step="1" />
          </div>
          <div class="field">
            <label>Precio de venta sin IVA (CLP)</label>
            <input v-model.number="form.base_price" type="number" min="0" step="1" required />
            <span class="field-hint">El IVA (19%) se calcula automáticamente.</span>
          </div>
        </div>

        <div class="field mt-2">
          <label>Filamentos usados (opcional, puede ser más de uno)</label>
          <div class="flex gap-2">
            <select v-model="newFilamentId" style="flex: 1">
              <option value="" disabled>Selecciona un filamento</option>
              <option v-for="f in filaments" :key="f.id" :value="f.id">{{ filamentLabel(f) }}</option>
            </select>
            <input v-model.number="newFilamentGrams" type="number" min="0.01" step="0.01" placeholder="Gramos" style="width: 90px" />
            <button type="button" class="btn btn-secondary btn-sm" @click="addFilamentRow">Agregar</button>
          </div>
          <div v-if="filamentRows.length" class="flex flex-col gap-2 mt-2">
            <div v-for="row in filamentRows" :key="row.id" class="flex items-center justify-between text-sm" style="background: var(--surface-alt); padding: 6px 10px; border-radius: 8px">
              <span>{{ filamentName(row.filament_id) }} — {{ row.grams_used }}g</span>
              <button type="button" class="btn btn-icon btn-ghost btn-sm" @click="removeFilamentRow(row.id)">
                <Icon name="close" :size="13" />
              </button>
            </div>
          </div>
        </div>

        <div class="field mt-2">
          <label>Consumibles usados</label>
          <div class="flex gap-2">
            <select v-model="newSupplyId" style="flex: 1">
              <option value="" disabled>Selecciona un insumo</option>
              <option v-for="s in supplies" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
            <input v-model.number="newSupplyQty" type="number" min="1" step="1" style="width: 70px" />
            <button type="button" class="btn btn-secondary btn-sm" @click="addSupplyRow">Agregar</button>
          </div>
          <div v-if="supplyRows.length" class="flex flex-col gap-2 mt-2">
            <div v-for="row in supplyRows" :key="row.supply_id" class="flex items-center justify-between text-sm" style="background: var(--surface-alt); padding: 6px 10px; border-radius: 8px">
              <span>{{ supplyName(row.supply_id) }} × {{ row.quantity }}</span>
              <button type="button" class="btn btn-icon btn-ghost btn-sm" @click="removeSupplyRow(row.supply_id)">
                <Icon name="close" :size="13" />
              </button>
            </div>
          </div>
        </div>

        <div class="field mt-2">
          <label>Notas</label>
          <textarea v-model="form.notes" rows="2" />
        </div>

        <div v-if="formError" class="alert alert-danger mt-4">{{ formError }}</div>

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
