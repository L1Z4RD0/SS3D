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
import { useAuthStore } from "../stores/auth";
import { useObservedUsers } from "../composables/useObservedUsers";
import Modal from "../components/Modal.vue";
import Icon from "../components/Icon.vue";
import FilamentPickerModal from "../components/FilamentPickerModal.vue";
import OrderStatusModal from "../components/OrderStatusModal.vue";
import { STATUS_LABELS, NEXT_ACTION, statusClass, isOverdue } from "../utils/orderStatus";

const auth = useAuthStore();
const today = todayISO();
// Observador: registra ventas para uno de sus usuarios asignados, usando SOLO el
// inventario de ese usuario (los inventarios nunca se mezclan en una venta).
const { observedUsers, loadObservedUsers, ownerName } = useObservedUsers();

function withOwner(label, ownerId) {
  const owner = ownerName(ownerId);
  return owner ? `${label} — de ${owner}` : label;
}

// Quién registró la venta, siempre visible (transparencia con el dueño del inventario).
function sellerLabel(sale) {
  if (!sale.created_by_username) return "Usuario eliminado";
  return sale.created_by_user_id === auth.user?.id ? `${sale.created_by_username} (tú)` : sale.created_by_username;
}

const sales = ref([]);
const total = ref(0);
const loading = ref(true);
const limit = 20;
const offset = ref(0);

const printers = ref([]);
const filaments = ref([]);
const supplies = ref([]);

const filters = reactive({ date_from: "", date_to: "", client: "", printer_id: "", payment_method: "", search: "", status: "" });

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
  Object.assign(filters, { date_from: "", date_to: "", client: "", printer_id: "", payment_method: "", search: "", status: "" });
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
  // Fecha de entrega comprometida (la usa el Calendario); por defecto, hoy.
  promised_delivery_date: todayISO(),
  // Solo en pedidos Entregados: fecha real de entrega (corregible).
  delivered_date: "",
  client_name: "",
  buyer_name: "",
  owner_id: "", // solo observador: de quién es el inventario de esta venta
  printer_id: "",
  print_hours: 0,
  postprocess_hours: 0,
  shipping_cost: 0,
  payment_method: "efectivo",
  notes: "",
});
const form = reactive(emptyForm());
// Venta que se está editando (para mostrar dueño y quién la registró).
const editingSale = ref(null);

/* Edición según el estado del pedido (el servidor lo valida igual):
   Pendiente: todo. En producción / Lista: la pieza ya se fabrica, no se tocan materiales,
   horas ni envío; solo precio, fecha de entrega, trabajo, comprador, pago y notas.
   Entregada: todo como siempre, más la fecha real de entrega. */
const editingStatus = computed(() => editingSale.value?.status || "pendiente");
const productionLocked = computed(() => ["en_produccion", "lista"].includes(editingStatus.value));

/* -------- Inventario disponible para la venta --------
   Usuario normal: todo lo suyo. Observador: solo lo del usuario elegido en "Venta para". */
const saleOwnerId = computed(() => (auth.isWatcher ? form.owner_id : null));
function ownedBySaleOwner(item) {
  return !auth.isWatcher || item.owner_id === saleOwnerId.value;
}
const ownerPrinters = computed(() => printers.value.filter(ownedBySaleOwner));
const ownerFilaments = computed(() => filaments.value.filter(ownedBySaleOwner));
const ownerSupplies = computed(() => supplies.value.filter(ownedBySaleOwner));

// Al cambiar de usuario se vacía lo elegido: eran recursos del inventario anterior.
function onOwnerChange() {
  form.printer_id = "";
  filamentRows.value = [];
  supplyRows.value = [];
  newFilamentId.value = "";
  newSupplyId.value = "";
}

/* -------- Precio: el sistema sugiere, el usuario decide --------
   Con los datos del trabajo se calculan en vivo los mismos escenarios de la
   Calculadora; el usuario elige uno o marca la casilla y escribe su propio precio
   (p. ej. para redondear). La ganancia se calcula igual contra el costo total. */
const suggestion = ref(null); // respuesta de /api/calculator/quote
const suggesting = ref(false);
const suggestError = ref("");
const selectedMargin = ref(null);
const useManualPrice = ref(false);
const manualPrice = ref(null);
// Al editar: precio con que se guardó la venta. Si el usuario lo deja tal cual, no se
// manda precio y el backend conserva exactamente lo cobrado.
const originalPrice = ref(null);
let suggestSeq = 0;
let suggestTimer = null;

const selectedScenario = computed(
  () => suggestion.value?.scenarios.find((s) => s.margin_percent === selectedMargin.value) || null
);

const manualPriceBreakdown = computed(() => {
  if (!useManualPrice.value || !isValidNumber(manualPrice.value, { min: 0, allowZero: false })) return null;
  const price = Number(manualPrice.value);
  const cost = suggestion.value ? Number(suggestion.value.breakdown.total_cost) : null;
  return { price, profit: cost === null ? null : price - cost };
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
  manualPrice.value = selectedScenario.value ? Math.round(Number(selectedScenario.value.price)) : null;
});

function resetPricing() {
  suggestion.value = null;
  suggestError.value = "";
  selectedMargin.value = null;
  useManualPrice.value = false;
  manualPrice.value = null;
  originalPrice.value = null;
}

function buildPricingPayload() {
  if (useManualPrice.value) {
    const price = Number(manualPrice.value);
    if (originalPrice.value !== null && price === originalPrice.value) return {};
    return { price };
  }
  return { price: Number(selectedScenario.value.price) };
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
const selectableFilaments = computed(() => ownerFilaments.value.filter((f) => Number(f.available_g) > 0));

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
  editingSale.value = null;
  Object.assign(form, emptyForm());
  // Con un solo usuario asignado no hay nada que elegir.
  if (auth.isWatcher && observedUsers.value.length === 1) form.owner_id = observedUsers.value[0].id;
  supplyRows.value = [];
  filamentRows.value = [];
  resetPricing();
  formError.value = "";
  showModal.value = true;
}

function openEdit(sale) {
  editingId.value = sale.id;
  editingSale.value = sale;
  Object.assign(form, {
    sale_date: sale.sale_date,
    client_name: sale.client_name,
    buyer_name: sale.buyer_name || "",
    // El dueño de una venta no cambia al editarla.
    owner_id: sale.owner_id,
    printer_id: sale.printer_id,
    print_hours: Number(sale.print_hours),
    postprocess_hours: Number(sale.postprocess_hours),
    shipping_cost: Number(sale.shipping_cost),
    payment_method: sale.payment_method,
    notes: sale.notes || "",
    promised_delivery_date: sale.promised_delivery_date,
    delivered_date: sale.delivered_date || "",
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
  originalPrice.value = Number(sale.price);
  useManualPrice.value = true;
  manualPrice.value = Number(sale.price);
  formError.value = "";
  showModal.value = true;
}

function buildPayload() {
  const orderData = {
    client_name: form.client_name,
    buyer_name: form.buyer_name || null,
    ...buildPricingPayload(),
    payment_method: form.payment_method,
    notes: form.notes || null,
  };
  // En producción / Lista solo viajan los datos del pedido (no materiales ni horas).
  if (productionLocked.value) return { ...orderData, promised_delivery_date: form.promised_delivery_date };
  const payload = {
    ...orderData,
    sale_date: form.sale_date,
    // Solo al crear y solo el observador: el dueño no se cambia al editar.
    ...(auth.isWatcher && !editingId.value ? { owner_id: form.owner_id } : {}),
    ...buildJobPayload(),
  };
  if (editingStatus.value === "entregada") payload.delivered_date = form.delivered_date;
  else payload.promised_delivery_date = form.promised_delivery_date;
  return payload;
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
  if (auth.isWatcher && !form.owner_id) return "Selecciona el usuario para el que registras la venta.";
  if (!form.printer_id) return "Selecciona una impresora.";
  if (editingStatus.value === "entregada") {
    if (!form.delivered_date) return "Indica la fecha real de entrega.";
  } else if (!form.promised_delivery_date) {
    return "Indica la fecha de entrega comprometida.";
  }
  const jobError = validateJobInputs();
  if (jobError) return jobError;
  if (useManualPrice.value) {
    if (!isValidNumber(manualPrice.value, { min: 0, allowZero: false })) return "Ingresa un precio válido, mayor a 0.";
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
    message:
      sale.status === "cancelado"
        ? `¿Eliminar el pedido cancelado "${sale.client_name}"? Se borra del registro como si nunca hubiera existido y se devuelve lo que seguía consumido (lo que ya se devolvió al cancelar no se devuelve dos veces). Si su pieza está en el Almacén, también se elimina.`
        : `¿Eliminar la venta de "${sale.client_name}"? Se borra como si nunca hubiera existido y se restaura el stock y las horas de impresora consumidos. Si el pedido no se va a hacer, usa mejor "Cancelar pedido" (desde el ícono de estado) para que quede registrado.`,
    confirmLabel: "Eliminar",
    danger: true,
  });
  if (!ok) return;
  try {
    await salesApi.deleteSale(sale.id);
  } catch (err) {
    await confirmAction({
      title: "No se pudo eliminar",
      message: extractApiError(err, "Intenta de nuevo."),
      confirmLabel: "Entendido",
    });
  }
  await loadSales();
}

/* -------- Estados del pedido -------- */
const statusModalSaleId = ref(null);
const advancingId = ref(null);

// Botón rápido para el paso siguiente (el resto de opciones está en el detalle).
async function advance(sale) {
  const next = NEXT_ACTION[sale.status];
  if (!next) return;
  if (next.status === "entregada") {
    const ok = await confirmAction({
      title: "Entregar pedido",
      message: `"${sale.client_name}" se marcará como Entregado hoy. Es un estado final y desde ese momento cuenta como ingreso.`,
      confirmLabel: "Marcar entregado",
    });
    if (!ok) return;
  }
  advancingId.value = sale.id;
  try {
    await salesApi.changeSaleStatus(sale.id, { status: next.status, today });
    await loadSales();
  } catch (err) {
    await confirmAction({
      title: "No se pudo cambiar el estado",
      message: extractApiError(err, "Intenta de nuevo."),
      confirmLabel: "Entendido",
    });
  } finally {
    advancingId.value = null;
  }
}

function deliveryLabel(sale) {
  return sale.delivered_date ? `Entregado ${formatDate(sale.delivered_date)}` : `Entrega ${formatDate(sale.promised_delivery_date)}`;
}

const pageLabel = computed(() => {
  if (!total.value) return "0 resultados";
  const from = offset.value + 1;
  const to = Math.min(offset.value + limit, total.value);
  return `${from}-${to} de ${total.value}`;
});

onMounted(async () => {
  await Promise.all([loadCatalog(), loadObservedUsers()]);
  await loadSales();
});
</script>

<template>
  <div>
    <div class="page-header">
      <p v-if="auth.isWatcher" class="page-subtitle">
        Ventas que registraste con el inventario de los usuarios que observas. Cada venta queda en el registro del
        dueño del inventario, indicando que la hiciste tú.
      </p>
      <p v-else class="page-subtitle">Historial de trabajos vendidos, con costos y ganancia calculados automáticamente</p>
      <button class="btn btn-primary" :disabled="auth.isWatcher && !observedUsers.length" @click="openCreate">
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
            <option v-for="p in printers" :key="p.id" :value="p.id">{{ withOwner(p.name, p.owner_id) }}</option>
          </select>
        </div>
        <div class="field">
          <label>Método de pago</label>
          <select v-model="filters.payment_method">
            <option value="">Todos</option>
            <option v-for="pm in PAYMENT_METHODS" :key="pm.value" :value="pm.value">{{ pm.label }}</option>
          </select>
        </div>
        <div class="field">
          <label>Estado</label>
          <select v-model="filters.status">
            <option value="">Todos</option>
            <option value="abiertos">Abiertos (sin entregar)</option>
            <option v-for="(label, key) in STATUS_LABELS" :key="key" :value="key">{{ label }}</option>
          </select>
        </div>
        <div class="field">
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
                <th>Pedido</th>
                <th>Estado</th>
                <th>Cliente</th>
                <th v-if="auth.isWatcher">Inventario de</th>
                <th>Registrada por</th>
                <th>Impresora</th>
                <th class="text-right">Precio</th>
                <th class="text-right">Ganancia</th>
                <th class="text-right">Margen</th>
                <th>Pago</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in sales" :key="s.id">
                <td>
                  {{ formatDate(s.sale_date) }}
                  <div class="text-sm" :class="isOverdue(s, today) ? 'overdue-text' : 'text-muted'">{{ deliveryLabel(s) }}</div>
                </td>
                <td>
                  <div class="flex items-center gap-2" style="flex-wrap: wrap">
                    <span class="badge" :class="statusClass(s.status)">{{ STATUS_LABELS[s.status] }}</span>
                    <span v-if="isOverdue(s, today)" class="badge badge-overdue">Atrasado</span>
                  </div>
                  <button
                    v-if="s.can_edit && NEXT_ACTION[s.status]"
                    type="button"
                    class="btn btn-secondary btn-sm mt-2"
                    :disabled="advancingId === s.id"
                    @click="advance(s)"
                  >
                    {{ NEXT_ACTION[s.status].label }}
                  </button>
                </td>
                <td>
                  <strong>{{ s.client_name }}</strong>
                  <div v-if="s.buyer_name" class="text-muted text-sm">{{ s.buyer_name }}</div>
                </td>
                <td v-if="auth.isWatcher">{{ s.owner_username }}</td>
                <td>
                  <span class="seller-tag" :class="{ 'is-other': s.created_by_user_id !== s.owner_id }">
                    {{ sellerLabel(s) }}
                  </span>
                </td>
                <td>{{ s.printer_name }}</td>
                <td class="text-right mono">{{ formatCurrency(s.price) }}</td>
                <!-- Un cancelado no dejó ganancia: se muestra su pérdida (si la hubo). -->
                <td v-if="s.status === 'cancelado'" class="text-right mono">
                  <span v-if="Number(s.loss_amount) > 0" style="color: var(--danger)" title="Pérdida por la cancelación">
                    −{{ formatCurrency(s.loss_amount) }}
                  </span>
                  <span v-else class="text-muted">—</span>
                </td>
                <td v-else class="text-right mono" style="color: var(--success)">{{ formatCurrency(s.profit) }}</td>
                <td class="text-right">{{ s.status === "cancelado" ? "—" : formatPercent(s.margin_percent) }}</td>
                <td><span class="badge badge-neutral">{{ paymentLabel(s.payment_method) }}</span></td>
                <td class="text-right">
                  <div class="flex gap-2" style="justify-content: flex-end">
                    <button class="btn btn-icon btn-ghost" title="Estado y línea de tiempo" @click="statusModalSaleId = s.id">
                      <Icon name="history" :size="16" />
                    </button>
                    <template v-if="s.can_edit">
                      <button v-if="s.status !== 'cancelado'" class="btn btn-icon btn-ghost" title="Editar" @click="openEdit(s)">
                        <Icon name="edit" :size="16" />
                      </button>
                      <button class="btn btn-icon btn-ghost" title="Eliminar" @click="handleDelete(s)"><Icon name="trash" :size="16" /></button>
                    </template>
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
        <div v-if="editingSale" class="alert alert-info" style="margin-bottom: 14px">
          Inventario de <strong>{{ editingSale.owner_username }}</strong> · Registrada por
          <strong>{{ sellerLabel(editingSale) }}</strong>
        </div>
        <div v-else-if="auth.isWatcher" class="field" style="margin-bottom: 14px">
          <label>Venta para (usuario dueño del inventario)</label>
          <select v-model="form.owner_id" required @change="onOwnerChange">
            <option value="" disabled>Selecciona un usuario</option>
            <option v-for="u in observedUsers" :key="u.id" :value="u.id">{{ u.username }}</option>
          </select>
          <span class="field-hint">
            Solo se usan la impresora, los filamentos y los insumos de este usuario. La venta aparecerá en su registro
            indicando que la hiciste tú ({{ auth.user?.username }}).
          </span>
        </div>
        <div v-if="productionLocked" class="alert alert-warning" style="margin-bottom: 14px">
          Pedido <strong>{{ STATUS_LABELS[editingStatus] }}</strong>: la pieza ya se está fabricando, así que no se
          cambian materiales, horas ni envío. Puedes editar precio, fecha de entrega, trabajo, comprador, método de pago
          y notas.
        </div>
        <div class="form-grid">
          <div class="field">
            <label>Fecha del pedido</label>
            <input v-model="form.sale_date" type="date" required :disabled="productionLocked" />
          </div>
          <div v-if="editingStatus === 'entregada'" class="field">
            <label>Fecha real de entrega</label>
            <input v-model="form.delivered_date" type="date" required />
          </div>
          <div v-else class="field">
            <label>Fecha de entrega comprometida</label>
            <input v-model="form.promised_delivery_date" type="date" required />
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
            <select v-model="form.printer_id" required :disabled="productionLocked || (auth.isWatcher && !form.owner_id)">
              <option value="" disabled>{{ auth.isWatcher && !form.owner_id ? "Primero elige el usuario" : "Selecciona" }}</option>
              <option v-for="p in ownerPrinters" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </div>
          <div class="field">
            <label>Horas de impresión</label>
            <input v-model.number="form.print_hours" type="number" min="0" step="0.1" :disabled="productionLocked" />
          </div>
          <div class="field">
            <label>Horas de postprocesado</label>
            <input v-model.number="form.postprocess_hours" type="number" min="0" step="0.1" :disabled="productionLocked" />
          </div>
          <div class="field" style="grid-column: span 2">
            <label>Envío / embalaje (CLP)</label>
            <input v-model.number="form.shipping_cost" type="number" min="0" step="1" :disabled="productionLocked" />
          </div>
        </div>

        <div class="field mt-2">
          <label>Filamentos usados (opcional, puede ser más de uno)</label>
          <div class="flex gap-2">
            <button
              type="button"
              class="btn btn-secondary"
              style="flex: 1; justify-content: flex-start; overflow: hidden"
              :disabled="productionLocked || (auth.isWatcher && !form.owner_id)"
              @click="showFilamentPicker = true"
            >
              <span v-if="newFilamentId" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap">{{ filamentSummary(newFilamentId) }}</span>
              <span v-else class="text-muted" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap">Selecciona un filamento</span>
            </button>
            <input v-model.number="newFilamentGrams" type="number" min="0.01" :max="GRAMS_MAX" step="0.01" placeholder="Gramos" style="width: 90px" :disabled="productionLocked" />
            <button type="button" class="btn btn-secondary btn-sm" :disabled="productionLocked" @click="addFilamentRow">Agregar</button>
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
              <button v-if="!productionLocked" type="button" class="btn btn-icon btn-ghost btn-sm" @click="removeFilamentRow(row.id)">
                <Icon name="close" :size="13" />
              </button>
            </div>
          </div>
        </div>

        <div class="field mt-2">
          <label>Consumibles usados</label>
          <div class="flex gap-2">
            <select v-model="newSupplyId" style="flex: 1" :disabled="productionLocked">
              <option value="" disabled>Selecciona un insumo</option>
              <option v-for="s in ownerSupplies" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
            <input v-model.number="newSupplyQty" type="number" min="0" step="1" placeholder="Cant." style="width: 70px" :disabled="productionLocked" />
            <button type="button" class="btn btn-secondary btn-sm" :disabled="productionLocked" @click="addSupplyRow">Agregar</button>
          </div>
          <div v-if="supplyRowError" class="alert alert-danger mt-2">{{ supplyRowError }}</div>
          <div v-if="supplyRows.length" class="flex flex-col gap-2 mt-2">
            <div v-for="row in supplyRows" :key="row.supply_id" class="flex items-center justify-between text-sm" style="background: var(--surface-alt); padding: 6px 10px; border-radius: 8px">
              <span>{{ supplyName(row.supply_id) }} × {{ row.quantity }}</span>
              <button v-if="!productionLocked" type="button" class="btn btn-icon btn-ghost btn-sm" @click="removeSupplyRow(row.supply_id)">
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
                <strong class="mono price-option-total">{{ formatCurrency(s.price) }}</strong>
                <span class="price-option-meta">Ganancia {{ formatCurrency(s.profit) }}</span>
              </label>
            </div>
            <span class="field-hint">
              Costo del trabajo: {{ formatCurrency(suggestion.breakdown.total_cost) }}. El margen se aplica a material,
              depreciación y energía; postprocesado, consumibles y envío se suman al final sin margen.
              <template v-if="suggesting">Actualizando...</template>
            </span>
          </template>

          <label class="manual-price-toggle flex items-center gap-2 mt-2">
            <input v-model="useManualPrice" type="checkbox" style="width: auto" />
            Definir yo el precio final
          </label>
          <template v-if="useManualPrice">
            <input
              v-model.number="manualPrice"
              type="number"
              min="0"
              step="1"
              placeholder="Ej: 15000"
              aria-label="Precio final"
              style="max-width: 200px"
            />
            <div v-if="manualPriceBreakdown" class="alert alert-info">
              Precio: <strong>{{ formatCurrency(manualPriceBreakdown.price) }}</strong>
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

    <OrderStatusModal
      v-if="statusModalSaleId"
      :sale-id="statusModalSaleId"
      @close="statusModalSaleId = null"
      @changed="loadSales"
    />

    <FilamentPickerModal
      v-if="showFilamentPicker"
      :filaments="ownerFilaments"
      :exclude-ids="filamentRows.map((r) => r.filament_id)"
      title="Seleccionar filamento"
      @select="onFilamentPicked"
      @close="showFilamentPicker = false"
    />
  </div>
</template>

<style scoped>
.overdue-text {
  color: var(--danger);
  font-weight: 700;
}

/* Quién registró la venta. Resaltado cuando no fue el dueño del inventario (ej. un
   observador), para que el dueño lo note de inmediato. */
.seller-tag {
  font-size: 0.82rem;
  white-space: nowrap;
}

.seller-tag.is-other {
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--primary-soft);
  color: var(--primary);
  font-weight: 700;
}

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
