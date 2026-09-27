<script setup>
import { ref, reactive, onMounted, computed, watch } from "vue";
import * as salesApi from "../api/sales";
import * as calculatorApi from "../api/calculator";
import * as printersApi from "../api/printers";
import * as inventoryApi from "../api/inventory";
import { PAYMENT_METHODS } from "../api/sales";
import { formatCurrency, formatPercent, formatDate, todayISO } from "../utils/format";
import { GRAMS_MAX, isValidGrams, isValidNumber, gramsErrorMessage, extractApiError } from "../utils/validation";
import { confirmAction } from "../composables/useConfirm";
import { promptExhaustedFilaments } from "../utils/exhaustedFilaments";
import { useIva, IVA_PERCENT } from "../composables/useIva";
import Modal from "../components/Modal.vue";
import Icon from "../components/Icon.vue";
import FilamentPickerModal from "../components/FilamentPickerModal.vue";

const { ivaEnabled, ivaRate } = useIva();

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
const newSupplyQty = ref(null);
const supplyRowError = ref("");

const filamentRows = ref([]); // { id, filament_id, grams_used }
const newFilamentId = ref("");
const newFilamentGrams = ref(null);
const filamentRowError = ref("");

const emptyForm = () => ({
  sale_date: todayISO(),
  client_name: "",
  buyer_name: "",
  printer_id: "",
  print_hours: 0,
  postprocess_hours: 0,
  shipping_cost: 0,
  payment_method: "efectivo",
  notes: "",
});
const form = reactive(emptyForm());

/* -------- Precio: el sistema sugiere, el usuario decide --------
   Con los datos del trabajo se calculan en vivo los mismos escenarios de la
   Calculadora; el usuario elige uno o marca la casilla y escribe su propio precio
   final (IVA incluido si está activo), p. ej. para redondear. */
const suggestion = ref(null); // respuesta de /api/calculator/quote
const suggesting = ref(false);
const suggestError = ref("");
const selectedMargin = ref(null);
const useManualPrice = ref(false);
const manualPrice = ref(null);
// Al editar: precio con que se guardó la venta. Si el usuario deja el total tal cual,
// no se manda precio y el backend conserva exactamente lo cobrado (y su IVA original).
const originalPrice = ref(null); // { total, ivaRate }
let suggestSeq = 0;
let suggestTimer = null;

const selectedScenario = computed(
  () => suggestion.value?.scenarios.find((s) => s.margin_percent === selectedMargin.value) || null
);

const manualPriceBreakdown = computed(() => {
  if (!useManualPrice.value || !isValidNumber(manualPrice.value, { min: 0, allowZero: false })) return null;
  const total = Number(manualPrice.value);
  const rate = isOriginalPrice(total) ? originalPrice.value.ivaRate : ivaRate.value;
  const base = total / (1 + rate);
  const cost = suggestion.value ? Number(suggestion.value.breakdown.total_cost) : null;
  return { total, base, iva: total - base, profit: cost === null ? null : base - cost };
});

function buildJobPayload() {
  return {
    printer_id: form.printer_id,
    filaments: filamentRows.value.map((r) => ({ filament_id: r.filament_id, grams_used: r.grams_used })),
    print_hours: Number(form.print_hours) || 0,
    postprocess_hours: Number(form.postprocess_hours) || 0,
    shipping_cost: Number(form.shipping_cost) || 0,
    supplies: supplyRows.value.map((r) => ({ supply_id: r.supply_id, quantity: r.quantity })),
  };
}

async function refreshSuggestion() {
  clearTimeout(suggestTimer);
  const seq = ++suggestSeq;
  if (!form.printer_id || validateJobInputs()) {
    suggestion.value = null;
    suggestError.value = "";
    suggesting.value = false;
    return;
  }
  suggesting.value = true;
  try {
    const result = await calculatorApi.computeQuote(buildJobPayload());
    if (seq !== suggestSeq) return; // llegó tarde, ya hay un cálculo más nuevo en curso
    suggestion.value = result;
    suggestError.value = "";
    if (!result.scenarios.some((s) => s.margin_percent === selectedMargin.value)) {
      // Por defecto "Precio Normal" (el del medio).
      selectedMargin.value = (result.scenarios[1] || result.scenarios[0])?.margin_percent ?? null;
    }
  } catch (err) {
    if (seq !== suggestSeq) return;
    suggestion.value = null;
    suggestError.value = extractApiError(err, "No se pudo calcular el precio sugerido.");
  } finally {
    if (seq === suggestSeq) suggesting.value = false;
  }
}

watch(
  () => (showModal.value ? JSON.stringify(buildJobPayload()) : null),
  (key) => {
    if (key === null) return;
    clearTimeout(suggestTimer);
    suggestTimer = setTimeout(refreshSuggestion, 400);
  }
);

watch(useManualPrice, (on) => {
  if (!on || manualPrice.value) return;
  // Parte del escenario elegido redondeado como guía; el usuario lo ajusta.
  manualPrice.value = selectedScenario.value ? Math.round(Number(selectedScenario.value.total_price)) : null;
});

function resetPricing() {
  suggestion.value = null;
  suggestError.value = "";
  selectedMargin.value = null;
  useManualPrice.value = false;
  manualPrice.value = null;
  originalPrice.value = null;
}

function isOriginalPrice(total) {
  return !!originalPrice.value && total === originalPrice.value.total;
}

function buildPricingPayload() {
  if (useManualPrice.value) {
    const total = Number(manualPrice.value);
    if (isOriginalPrice(total)) return {};
    return { base_price: null, manual_total_price: total };
  }
  return { base_price: Number(selectedScenario.value.base_price), manual_total_price: null };
}

function addFilamentRow() {
  filamentRowError.value = "";
  if (!newFilamentId.value) {
    filamentRowError.value = "Selecciona un filamento.";
    return;
  }
  if (!isValidGrams(newFilamentGrams.value)) {
    filamentRowError.value = gramsErrorMessage(newFilamentGrams.value);
    return;
  }
  const grams = Number(newFilamentGrams.value);
  const existing = filamentRows.value.find((r) => r.filament_id === newFilamentId.value);
  if (existing) {
    const total = existing.grams_used + grams;
    if (!isValidGrams(total)) {
      filamentRowError.value = `Ese filamento ya está en la lista. Sumado (${total}g), ${gramsErrorMessage(total)}`;
      return;
    }
    existing.grams_used = total;
  } else {
    filamentRows.value.push({
      id: crypto.randomUUID(),
      filament_id: newFilamentId.value,
      grams_used: grams,
    });
  }
  newFilamentId.value = "";
  newFilamentGrams.value = null;
}
function removeFilamentRow(id) {
  filamentRows.value = filamentRows.value.filter((r) => r.id !== id);
}
// Filaments at 0g can't be picked for a new sale — they're kept visible in Inventario
// (marked "Agotado") but excluded here so a sale can't be logged against empty stock.
const selectableFilaments = computed(() => filaments.value.filter((f) => Number(f.available_g) > 0));

const availableFilamentOptions = computed(() =>
  selectableFilaments.value.filter((f) => !filamentRows.value.some((r) => r.filament_id === f.id))
);
function filamentName(id) {
  const f = filaments.value.find((x) => x.id === id);
  return f ? filamentLabel(f) : "";
}
function filamentLabel(f) {
  return f.sku ? `${f.brand} · ${f.color} — ${f.sku}` : `${f.brand} · ${f.color}`;
}
// Compacto a propósito: el picker ya mostró marca, material, color, SKU y gramos
// disponibles antes de elegir, así que acá alcanza con lo mínimo para no desbordar
// el botón (que comparte fila con el input de gramos y "Agregar").
function filamentSummary(id) {
  const f = filaments.value.find((x) => x.id === id);
  return f ? `${f.brand} · ${f.color}` : "";
}

/* -------- Filament picker modal -------- */
const showFilamentPicker = ref(false);
function onFilamentPicked(f) {
  newFilamentId.value = f.id;
  showFilamentPicker.value = false;
}

function addSupplyRow() {
  supplyRowError.value = "";
  if (!newSupplyId.value) {
    supplyRowError.value = "Selecciona un insumo.";
    return;
  }
  if (!isValidNumber(newSupplyQty.value, { min: 0, allowZero: false })) {
    supplyRowError.value = "Ingresa una cantidad válida, mayor a 0.";
    return;
  }
  const qty = Number(newSupplyQty.value);
  const exists = supplyRows.value.find((r) => r.supply_id === newSupplyId.value);
  if (exists) {
    exists.quantity += qty;
  } else {
    supplyRows.value.push({ supply_id: newSupplyId.value, quantity: qty });
  }
  newSupplyId.value = "";
  newSupplyQty.value = null;
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
  resetPricing();
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
  resetPricing();
  // La venta ya tiene un precio acordado: se abre con ese precio fijado a mano para
  // no cambiarlo sin querer. Desmarcando la casilla se puede elegir un escenario.
  originalPrice.value = { total: Number(sale.total_price), ivaRate: Number(sale.iva_percent) / 100 };
  useManualPrice.value = true;
  manualPrice.value = Number(sale.total_price);
  formError.value = "";
  showModal.value = true;
}

function buildPayload() {
  return {
    sale_date: form.sale_date,
    client_name: form.client_name,
    buyer_name: form.buyer_name || null,
    ...buildJobPayload(),
    ...buildPricingPayload(),
    payment_method: form.payment_method,
    notes: form.notes || null,
  };
}

function isValidOrEmpty(value, opts) {
  if (value === null || value === undefined || value === "") return true;
  return isValidNumber(value, opts);
}

function validateJobInputs() {
  if (!isValidOrEmpty(form.print_hours, { min: 0 })) return "Las horas de impresión no pueden ser negativas.";
  if (!isValidOrEmpty(form.postprocess_hours, { min: 0 })) return "Las horas de postprocesado no pueden ser negativas.";
  if (!isValidOrEmpty(form.shipping_cost, { min: 0 })) return "El envío/embalaje no puede ser negativo.";
  return "";
}

function validateSaleForm() {
  if (!form.printer_id) return "Selecciona una impresora.";
  const jobError = validateJobInputs();
  if (jobError) return jobError;
  if (useManualPrice.value) {
    if (!isValidNumber(manualPrice.value, { min: 0, allowZero: false })) return "Ingresa un precio final válido, mayor a 0.";
  } else if (!selectedScenario.value) {
    return suggestError.value || "Elige uno de los precios sugeridos o marca \"Definir yo el precio final\".";
  }
  return "";
}

async function handleSubmit() {
  let validationError = validateSaleForm();
  if (!validationError && !useManualPrice.value) {
    // Recalcular antes de guardar: si el usuario cambió un dato hace un instante, el
    // escenario en pantalla podría ser del cálculo anterior (el recálculo va con retardo).
    await refreshSuggestion();
    validationError = validateSaleForm();
  }
  if (validationError) {
    formError.value = validationError;
    return;
  }
  saving.value = true;
  formError.value = "";
  try {
    const sale = editingId.value
      ? await salesApi.updateSale(editingId.value, buildPayload())
      : await salesApi.createSale(buildPayload());
    showModal.value = false;
    await loadSales();
    await loadCatalog();
    await promptExhaustedFilaments(sale.exhausted_filaments);
    await loadCatalog();
  } catch (err) {
    formError.value = extractApiError(err, "No se pudo guardar la venta.");
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
                <th class="text-right">{{ ivaEnabled ? "Precio c/IVA" : "Precio" }}</th>
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
          <div class="field" style="grid-column: span 2">
            <label>Envío / embalaje (CLP)</label>
            <input v-model.number="form.shipping_cost" type="number" min="0" step="1" />
          </div>
        </div>

        <div class="field mt-2">
          <label>Filamentos usados (opcional, puede ser más de uno)</label>
          <div class="flex gap-2">
            <button
              type="button"
              class="btn btn-secondary"
              style="flex: 1; justify-content: flex-start; overflow: hidden"
              @click="showFilamentPicker = true"
            >
              <span v-if="newFilamentId" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap">{{ filamentSummary(newFilamentId) }}</span>
              <span v-else class="text-muted" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap">Selecciona un filamento</span>
            </button>
            <input v-model.number="newFilamentGrams" type="number" min="0.01" :max="GRAMS_MAX" step="0.01" placeholder="Gramos" style="width: 90px" />
            <button type="button" class="btn btn-secondary btn-sm" @click="addFilamentRow">Agregar</button>
          </div>
          <div v-if="!selectableFilaments.length" class="text-sm mt-1" style="color: var(--text-muted)">
            No hay filamentos con stock disponible. Los agotados (0g) no se pueden usar en una nueva venta.
          </div>
          <div v-else-if="!availableFilamentOptions.length" class="text-sm mt-1" style="color: var(--text-muted)">
            Ya agregaste todos tus filamentos disponibles. Para cambiar la cantidad de uno, quítalo de la lista de abajo y vuelve a agregarlo.
          </div>
          <div v-if="filamentRowError" class="alert alert-danger mt-2">{{ filamentRowError }}</div>
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
            <input v-model.number="newSupplyQty" type="number" min="0" step="1" placeholder="Cant." style="width: 70px" />
            <button type="button" class="btn btn-secondary btn-sm" @click="addSupplyRow">Agregar</button>
          </div>
          <div v-if="supplyRowError" class="alert alert-danger mt-2">{{ supplyRowError }}</div>
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
          <label>Precio de venta</label>
          <span v-if="!form.printer_id" class="field-hint">
            Selecciona una impresora y completa los datos del trabajo para ver el precio sugerido.
          </span>
          <span v-else-if="suggesting && !suggestion" class="field-hint">Calculando precio sugerido...</span>
          <div v-else-if="suggestError" class="alert alert-danger">{{ suggestError }}</div>

          <template v-if="suggestion">
            <div class="price-options" :class="{ 'is-disabled': useManualPrice }">
              <label
                v-for="s in suggestion.scenarios"
                :key="s.margin_percent"
                class="price-option"
                :class="{ 'is-selected': !useManualPrice && selectedMargin === s.margin_percent }"
              >
                <input v-model="selectedMargin" type="radio" :value="s.margin_percent" :disabled="useManualPrice" />
                <span class="price-option-title">{{ s.label }} <span class="text-muted">+{{ s.margin_percent }}%</span></span>
                <strong class="mono price-option-total">{{ formatCurrency(s.total_price) }}</strong>
                <span class="price-option-meta">
                  <template v-if="ivaEnabled">Neto {{ formatCurrency(s.base_price) }} · </template>Ganancia {{ formatCurrency(s.profit) }}
                </span>
              </label>
            </div>
            <span class="field-hint">
              Costo del trabajo: {{ formatCurrency(suggestion.breakdown.total_cost) }}<template v-if="ivaEnabled">
                · precios con IVA ({{ IVA_PERCENT }}%) incluido</template>.
              <template v-if="suggesting">Actualizando...</template>
            </span>
          </template>

          <label class="manual-price-toggle flex items-center gap-2 mt-2">
            <input v-model="useManualPrice" type="checkbox" style="width: auto" />
            Definir yo el precio final{{ ivaEnabled ? " (IVA incluido)" : "" }}
          </label>
          <template v-if="useManualPrice">
            <input
              v-model.number="manualPrice"
              type="number"
              min="0"
              step="1"
              placeholder="Ej: 15000"
              :aria-label="ivaEnabled ? 'Precio final con IVA' : 'Precio final'"
              style="max-width: 200px"
            />
            <div v-if="manualPriceBreakdown" class="alert alert-info">
              <template v-if="ivaEnabled">
                Neto {{ formatCurrency(manualPriceBreakdown.base) }} + IVA {{ formatCurrency(manualPriceBreakdown.iva) }} =
              </template>
              <template v-else>Precio:</template>
              <strong>{{ formatCurrency(manualPriceBreakdown.total) }}</strong>
              <template v-if="manualPriceBreakdown.profit !== null">
                · Ganancia:
                <span :style="{ color: manualPriceBreakdown.profit < 0 ? 'var(--danger)' : undefined }">
                  {{ formatCurrency(manualPriceBreakdown.profit) }}
                </span>
              </template>
            </div>
            <div v-else class="alert alert-danger">Ingresa un precio final válido, mayor a 0.</div>
          </template>
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

    <FilamentPickerModal
      v-if="showFilamentPicker"
      :filaments="filaments"
      :exclude-ids="filamentRows.map((r) => r.filament_id)"
      title="Seleccionar filamento"
      @select="onFilamentPicked"
      @close="showFilamentPicker = false"
    />
  </div>
</template>

<style scoped>
.price-options {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.price-options.is-disabled {
  opacity: 0.5;
}

.field .price-option {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text);
  cursor: pointer;
}

.price-options.is-disabled .price-option {
  cursor: not-allowed;
}

.field .price-option.is-selected {
  border-color: var(--primary);
  background: var(--primary-soft);
}

.price-option:focus-within {
  box-shadow: 0 0 0 3px var(--primary-soft);
}

.price-option input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.price-option-total {
  font-size: 1rem;
}

.price-option-meta {
  font-size: 0.72rem;
  font-weight: 400;
  color: var(--text-muted);
}

.field .manual-price-toggle {
  cursor: pointer;
  color: var(--text);
}

@media (max-width: 600px) {
  .price-options {
    grid-template-columns: 1fr;
  }
}
</style>
