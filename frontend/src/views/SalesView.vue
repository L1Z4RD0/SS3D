<script setup>
import { ref, reactive, onMounted, computed, watch, nextTick } from "vue";
import * as salesApi from "../api/sales";
import * as calculatorApi from "../api/calculator";
import * as betaApi from "../api/beta";
import { DEFAULT_RISK_LEVEL, riskLevelForPercent } from "../api/calculator";
import * as printersApi from "../api/printers";
import * as inventoryApi from "../api/inventory";
import { PAYMENT_METHODS, GIFT_PAYMENT_METHOD, SALE_SOURCES, NO_SALE_SOURCE, saleSourceInfo } from "../api/sales";
import { formatCurrency, formatPercent, formatDate, todayISO } from "../utils/format";
import { GRAMS_MAX, isValidGrams, isValidNumber, gramsErrorMessage, extractApiError } from "../utils/validation";
import { confirmAction } from "../composables/useConfirm";
import { promptExhaustedFilaments } from "../utils/exhaustedFilaments";
import { useAuthStore } from "../stores/auth";
import { useObservedUsers } from "../composables/useObservedUsers";
import Modal from "../components/Modal.vue";
import Icon from "../components/Icon.vue";
import FilamentPickerModal from "../components/FilamentPickerModal.vue";
import ExtraPlatesEditor from "../components/ExtraPlatesEditor.vue";
import RiskLevelPicker from "../components/RiskLevelPicker.vue";
import SaleSourcePicker from "../components/SaleSourcePicker.vue";
import HoursMinutesInput from "../components/HoursMinutesInput.vue";
import AddPlateModal from "../components/AddPlateModal.vue";
import { platesPayload, platesError } from "../utils/plates";
import OrderStatusModal from "../components/OrderStatusModal.vue";
import { dueInfo, isUnpaid } from "../utils/payment";
import { STATUS_LABELS, NEXT_ACTION, OPEN_STATUSES, statusClass, isOverdue } from "../utils/orderStatus";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import { showToast } from "../composables/useToast";
import { saveBlobResponse } from "../utils/download";
import { useRoute, useRouter } from "vue-router";

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
const limit = 100;
const offset = ref(0);

const printers = ref([]);
const filaments = ref([]);
const supplies = ref([]);

const EMPTY_FILTERS = { date_from: "", date_to: "", client: "", printer_id: "", account_id: "", payment_method: "", sale_source: "", search: "", status: "" };
const filters = reactive({ ...EMPTY_FILTERS });

/* Orden de la hoja: lo resuelve el servidor (así sirve con varias páginas). Se elige en
   "Ordenar por" o tocando el título de una columna (otro toque invierte el orden). */
const SORT_OPTIONS = [
  { by: "fecha", direction: "desc", label: "Más recientes" },
  { by: "fecha", direction: "asc", label: "Más antiguas" },
  { by: "precio", direction: "desc", label: "Precio: mayor a menor" },
  { by: "precio", direction: "asc", label: "Precio: menor a mayor" },
  { by: "ganancia", direction: "desc", label: "Ganancia: mayor a menor" },
  { by: "ganancia", direction: "asc", label: "Ganancia: menor a mayor" },
  { by: "costo", direction: "desc", label: "Costo: mayor a menor" },
  { by: "margen", direction: "desc", label: "Margen: mayor a menor" },
  { by: "entrega", direction: "asc", label: "Entrega más próxima" },
  { by: "cliente", direction: "asc", label: "Trabajo (A-Z)" },
];
const sort = reactive({ by: "fecha", direction: "desc" });
const sortKey = computed({
  get: () => `${sort.by}:${sort.direction}`,
  set: (key) => {
    const [by, direction] = key.split(":");
    Object.assign(sort, { by, direction });
  },
});
// Lo primero que uno espera al tocar cada columna (los montos, de mayor a menor).
const FIRST_DIRECTION = { fecha: "desc", cliente: "asc", precio: "desc", costo: "desc", ganancia: "desc", margen: "desc" };
function sortBy(by) {
  sort.direction = sort.by === by ? (sort.direction === "desc" ? "asc" : "desc") : FIRST_DIRECTION[by];
  sort.by = by;
}
const MONEY_COLUMNS = [
  { by: "precio", label: "Precio" },
  { by: "costo", label: "Costo" },
  { by: "ganancia", label: "Ganancia" },
  { by: "margen", label: "Margen" },
];
const sortArrow = (by) => (sort.by === by ? (sort.direction === "desc" ? "▼" : "▲") : "");
watch(sortKey, () => applyFilters());

const paymentLabel = (v) => PAYMENT_METHODS.find((p) => p.value === v)?.label || v;

// Personas sugeridas para "¿Quién lo lleva?" (los socios; se puede escribir otro nombre).
const deliveryPeople = ref([]);
betaApi
  .getBetaAccess()
  .then((a) => (deliveryPeople.value = a.partners.filter((p) => p !== "Caja")))
  .catch(() => {});

// Planchas de un pedido ya registrado (desde el detalle de costos).
const plateSale = ref(null);
const saleOwnerPrinters = (sale) =>
  printers.value.filter((p) => !auth.isWatcher || auth.isCompany || p.owner_id === sale.owner_id);
const saleOwnerFilaments = (sale) =>
  filaments.value.filter(
    (f) =>
      Number(f.available_g) > 0 &&
      (!auth.isWatcher || auth.isCompany || f.owner_id === sale.owner_id)
  );
const canManagePlates = (sale) => sale.can_edit && OPEN_STATUSES.includes(sale.status) && !sale.warehouse_item_id;

// La fila que acaba de cambiar se ilumina un instante (ver .row-flash en motion.css).
const flashedId = ref(null);
let flashTimer = null;
function flashRow(id) {
  if (!id) return;
  clearTimeout(flashTimer);
  flashedId.value = null;
  nextTick(() => {
    flashedId.value = id;
    flashTimer = setTimeout(() => (flashedId.value = null), 1500);
  });
}

function replaceSale(updated) {
  const i = sales.value.findIndex((x) => x.id === updated.id);
  if (i !== -1) sales.value[i] = updated;
  flashRow(updated.id);
}
async function onPlateSaved(updated) {
  plateSale.value = null;
  replaceSale(updated);
  await promptExhaustedFilaments(updated.exhausted_filaments);
  loadCatalog();
}
async function removePlate(sale, plate) {
  const ok = await confirmAction({
    title: "Quitar plancha",
    message: `¿Quitar "${plate.name}"? Se devuelven su filamento y sus horas, y su costo sale del pedido.`,
    confirmLabel: "Quitar",
    danger: true,
  });
  if (!ok) return;
  try {
    replaceSale(await salesApi.deleteSalePlate(sale.id, plate.id));
    loadCatalog();
  } catch (err) {
    await confirmAction({
      title: "No se pudo quitar la plancha",
      message: extractApiError(err, "Intenta de nuevo."),
      confirmLabel: "Entendido",
    });
  }
}

// Desglose de costos de una venta (se despliega bajo su fila).
const expandedCostId = ref(null);
function toggleCost(id) {
  expandedCostId.value = expandedCostId.value === id ? null : id;
}
function costLines(sale) {
  // Material y horas de todas las planchas (la principal + las adicionales), porque los
  // montos de abajo ya las incluyen.
  const gramsByLabel = new Map();
  const addGrams = (label, grams) => gramsByLabel.set(label, (gramsByLabel.get(label) || 0) + Number(grams));
  (sale.filaments_used || []).forEach((f) => addGrams(f.filament_label, f.grams_used));
  (sale.plates || []).forEach((p) => p.filaments.forEach((f) => addGrams(f.filament_label, f.grams_used)));
  const filamentDetail = [...gramsByLabel]
    .map(([label, grams]) => `${label} (${grams.toLocaleString("es-CL")} g)`)
    .join(" · ");
  const hours = Number(sale.print_hours) + (sale.plates || []).reduce((sum, p) => sum + Number(p.print_hours), 0);
  const inPlates = sale.plates?.length ? `, en ${sale.plates.length + 1} planchas` : "";
  const supplyDetail = (sale.supplies_used || []).map((u) => `${u.supply_name} × ${Number(u.quantity_used)}`).join(" · ");
  const lines = [
    { label: "Material", value: sale.material_cost, detail: filamentDetail || sale.filament_label || "" },
    { label: "Depreciación impresora", value: sale.depreciation_cost, detail: `${Number(hours.toFixed(2))} h de impresión${inPlates}` },
    { label: "Energía", value: sale.energy_cost },
    { label: "Postproceso", value: sale.postprocess_cost, detail: Number(sale.postprocess_hours) ? `${Number(sale.postprocess_hours)} h` : "" },
    {
      label: sale.has_provisional_costs ? "Insumos (provisional)" : "Insumos",
      value: sale.supplies_cost,
      detail: supplyDetail,
      provisional: sale.has_provisional_costs,
    },
    {
      label: "Delivery",
      value: sale.shipping_cost,
      detail: Number(sale.shipping_cost) ? (sale.delivery_by ? `lo llevó ${sale.delivery_by}` : "sin asignar") : "",
    },
  ];
  // Las líneas en $0 sin detalle solo agregan ruido.
  return lines.filter((l) => Number(l.value) !== 0 || l.detail);
}

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
    const params = { limit, offset: offset.value, sort: sort.by, direction: sort.direction };
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

// Excel con todas las ventas que cumplen los filtros (todas las páginas) y el orden actual.
const exporting = ref(false);
const exportError = ref("");
async function exportExcel() {
  exporting.value = true;
  exportError.value = "";
  try {
    const params = { sort: sort.by, direction: sort.direction };
    Object.entries(filters).forEach(([k, v]) => {
      if (v) params[k] = v;
    });
    saveBlobResponse(await salesApi.exportSales(params), `ventas_${todayISO()}.xlsx`);
    showToast("Excel descargado", { detail: `${total.value} venta(s)` });
  } catch {
    exportError.value = "No se pudo descargar el Excel. Intenta de nuevo en unos segundos.";
  } finally {
    exporting.value = false;
  }
}

function applyFilters() {
  offset.value = 0;
  loadSales();
}

// Accesos rápidos de estado (píldora deslizante). Usan el mismo filtro "Estado" de abajo.
const QUICK_STATUS = [
  { value: "", label: "Todas" },
  { value: "abiertos", label: "Abiertas" },
  { value: "entregada", label: "Entregadas" },
];
const quickEl = ref(null);
const quickPill = ref({ left: 0, width: 0, visible: false });
function moveQuickPill() {
  const btn = quickEl.value?.querySelector("button.on");
  quickPill.value = btn ? { left: btn.offsetLeft, width: btn.offsetWidth, visible: true } : { ...quickPill.value, visible: false };
}
watch(() => filters.status, () => nextTick(moveQuickPill));
function setQuickStatus(value) {
  filters.status = value;
  applyFilters();
}

function resetFilters() {
  Object.assign(filters, EMPTY_FILTERS);
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
  printer_id: "",
  print_hours: 0,
  postprocess_hours: 0,
  shipping_cost: 0,
  delivery_by: "",
  risk_level: DEFAULT_RISK_LEVEL,
  payment_method: "efectivo",
  sale_source: "",
  notes: "",
});
const form = reactive(emptyForm());
// Venta que se está editando (para mostrar dueño y quién la registró).
const editingSale = ref(null);

/* Edición según el estado del pedido (el servidor lo valida igual):
   Pendiente: todo. En producción / Lista: la pieza ya se fabrica, no se tocan materiales,
   horas ni el monto del delivery; solo precio, fecha de entrega, trabajo, comprador, pago,
   quién lleva el delivery y notas.
   Entregada: todo como siempre, más la fecha real de entrega. */
const editingStatus = computed(() => editingSale.value?.status || "pendiente");
// Pedido de una pieza del Almacén: la pieza ya existe, nunca se editan materiales ni horas.
const fromWarehouse = computed(() => !!editingSale.value?.warehouse_item_id);
const productionLocked = computed(
  () => fromWarehouse.value || ["en_produccion", "lista"].includes(editingStatus.value)
);

/* -------- Inventario disponible para la venta --------
   La venta es del dueño de la impresora (no de quien la registra). Usuario normal: todo lo
   suyo. Observador: elige la impresora de cualquiera de sus usuarios y usa solo lo de ese
   dueño. La Empresa además puede mezclar filamentos e insumos de otras cuentas (material
   mixto: cada costo queda a cuenta de su dueño). */
const saleOwnerId = computed(() =>
  auth.isWatcher ? printers.value.find((p) => p.id === form.printer_id)?.owner_id || null : null
);
const saleOwnerName = computed(() => (saleOwnerId.value ? ownerName(saleOwnerId.value) : ""));
function ownedBySaleOwner(item) {
  return !auth.isWatcher || item.owner_id === saleOwnerId.value;
}
// La Empresa puede combinar materiales de todos los socios que observa y los propios (ej.
// impresora de Diego + filamento de Sntg). Cada costo queda a cuenta de su dueño.
function usableInSale(item) {
  return auth.isCompany || ownedBySaleOwner(item);
}

// De quién es cada recurso de la venta. Si hay más de un dueño se avisa (y se confirma al
// guardar) para que después no haya confusiones con los costos.
const resourceOwnerSummary = computed(() => {
  if (!auth.isCompany) return [];
  const byOwner = new Map();
  const add = (ownerId, what) => {
    if (!ownerId) return;
    const name = ownerName(ownerId) || "otro usuario";
    if (!byOwner.has(name)) byOwner.set(name, new Set());
    byOwner.get(name).add(what);
  };
  const findIn = (list, id) => list.value.find((x) => x.id === id);
  add(findIn(printers, form.printer_id)?.owner_id, "impresora");
  filamentRows.value.forEach((r) => add(findIn(filaments, r.filament_id)?.owner_id, "filamento"));
  supplyRows.value.forEach((r) => add(findIn(supplies, r.supply_id)?.owner_id, "insumos"));
  if (!editingId.value) {
    extraPlates.value.forEach((p) => {
      add(findIn(printers, p.printer_id)?.owner_id, "impresora");
      p.filaments.forEach((r) => add(findIn(filaments, r.filament_id)?.owner_id, "filamento"));
    });
  }
  return [...byOwner].map(([name, what]) => ({ name, what: [...what] }));
});
const mixedOwners = computed(() => resourceOwnerSummary.value.length > 1);
const mixedOwnersText = computed(() =>
  resourceOwnerSummary.value.map((o) => `${o.name} (${o.what.join(", ")})`).join(" · ")
);
const ownerPrinters = computed(() => printers.value.filter(ownedBySaleOwner));
// Impresora principal de la venta: un observador (y la Empresa, que no tiene impresora
// propia) ve las de todos sus usuarios; la que elija define de quién es la venta.
const salePrinters = computed(() => (auth.isWatcher ? printers.value : ownerPrinters.value));
// Un observador común no mezcla inventarios: sin impresora elegida aún no sabe de quién usar.
const needsPrinterFirst = computed(() => auth.isWatcher && !auth.isCompany && !saleOwnerId.value);
// La Empresa mezcla su filamento con el del socio: el selector muestra de quién es cada uno.
const pickerOwnerNames = computed(() =>
  auth.isCompany ? Object.fromEntries(observedUsers.value.map((u) => [u.id, u.username])) : {}
);
const ownerFilaments = computed(() => filaments.value.filter(usableInSale));
const ownerSupplies = computed(() => supplies.value.filter(usableInSale));

// Un observador común que cambia a la impresora de otro usuario: se vacían los filamentos e
// insumos elegidos (eran del inventario del dueño anterior). La Empresa puede mezclarlos.
watch(saleOwnerId, (now, before) => {
  if (auth.isCompany || !before || now === before || editingId.value) return;
  filamentRows.value = [];
  supplyRows.value = [];
  newFilamentId.value = "";
  newSupplyId.value = "";
});

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
const originalDelivery = ref(null);
let suggestSeq = 0;
let suggestTimer = null;

// Delivery del formulario: va aparte del precio de la impresión.
const formDelivery = computed(() => Math.max(0, Number(form.shipping_cost) || 0));
const pieceOf = (total) => Math.max(0, Number(total) - formDelivery.value);

const selectedScenario = computed(
  () => suggestion.value?.scenarios.find((s) => s.margin_percent === selectedMargin.value) || null
);

const manualPriceBreakdown = computed(() => {
  if (!useManualPrice.value || !isValidNumber(manualPrice.value, { min: 0, allowZero: false })) return null;
  // El precio a mano es el de la impresión: el delivery se suma aparte al total a cobrar.
  const price = Number(manualPrice.value);
  const delivery = formDelivery.value;
  const total = price + delivery;
  const cost = suggestion.value ? Number(suggestion.value.breakdown.total_cost) : null;
  return { price, delivery, total, profit: cost === null ? null : total - cost };
});

// Planchas adicionales de un pedido nuevo. En un pedido ya registrado se gestionan desde
// el detalle de costos (Agregar plancha), pero entran igual en el precio sugerido.
const extraPlates = ref([]);
function storedPlatesAsInput(sale) {
  return (sale?.plates || []).map((p) => ({
    name: p.name,
    printer_id: p.printer_id,
    print_hours: Number(p.print_hours),
    filaments: p.filaments.map((f) => ({ filament_id: f.filament_id, grams_used: Number(f.grams_used) })),
  }));
}

function buildJobPayload() {
  return {
    extra_plates: editingId.value ? storedPlatesAsInput(editingSale.value) : platesPayload(extraPlates.value),
    risk_level: form.risk_level,
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
  manualPrice.value = selectedScenario.value ? Math.round(pieceOf(selectedScenario.value.price)) : null;
});

function resetPricing() {
  suggestion.value = null;
  suggestError.value = "";
  selectedMargin.value = null;
  useManualPrice.value = false;
  manualPrice.value = null;
  originalPrice.value = null;
  originalDelivery.value = null;
}

const isGift = computed(() => form.payment_method === GIFT_PAYMENT_METHOD);

function buildPricingPayload() {
  if (isGift.value) return { price: 0 };
  if (useManualPrice.value) {
    // Precio de la impresión, sin delivery: el servidor le suma el delivery al total.
    const piece = Number(manualPrice.value);
    const sameDelivery = originalDelivery.value !== null && formDelivery.value === originalDelivery.value;
    if (originalPrice.value !== null && piece === originalPrice.value && sameDelivery) return {};
    return { piece_price: piece };
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
// Al editar, lo que la venta ya tenía descontado vuelve antes de descontar lo nuevo.
function alreadyConsumed(supplyId) {
  const line = editingSale.value?.supplies_used.find((u) => u.supply_id === supplyId);
  return line ? Number(line.quantity_used) : 0;
}

// Insumos que no alcanzan: la venta se registra igual, el insumo queda en negativo y su
// costo es provisional hasta que se registre la compra (Reponer en Inventario).
const supplyShortages = computed(() =>
  supplyRows.value
    .map((row) => {
      const s = supplies.value.find((x) => x.id === row.supply_id);
      if (!s) return null;
      const available = Number(s.quantity_available) + alreadyConsumed(row.supply_id);
      const owed = Number(row.quantity) - Math.max(available, 0);
      return owed > 0 ? { name: s.name, owed, available: Math.max(available, 0) } : null;
    })
    .filter(Boolean)
);

function openCreate() {
  editingId.value = null;
  editingSale.value = null;
  Object.assign(form, emptyForm());
  supplyRows.value = [];
  filamentRows.value = [];
  extraPlates.value = [];
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
    printer_id: sale.printer_id,
    print_hours: Number(sale.print_hours),
    postprocess_hours: Number(sale.postprocess_hours),
    shipping_cost: Number(sale.shipping_cost),
    risk_level: riskLevelForPercent(sale.risk_percent),
    payment_method: sale.payment_method,
    sale_source: sale.sale_source || "",
    notes: sale.notes || "",
    promised_delivery_date: sale.promised_delivery_date,
    delivery_by: sale.delivery_by || "",
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
  originalPrice.value = Number(sale.piece_price ?? sale.price);
  originalDelivery.value = Number(sale.shipping_cost) || 0;
  useManualPrice.value = true;
  manualPrice.value = originalPrice.value;
  formError.value = "";
  showModal.value = true;
}

function buildPayload() {
  const orderData = {
    client_name: form.client_name,
    buyer_name: form.buyer_name || null,
    ...buildPricingPayload(),
    payment_method: form.payment_method,
    sale_source: form.sale_source || null,
    delivery_by: form.delivery_by?.trim() || null,
    notes: form.notes || null,
  };
  // En producción / Lista solo viajan los datos del pedido (no materiales ni horas).
  if (productionLocked.value) {
    return editingStatus.value === "entregada"
      ? { ...orderData, delivered_date: form.delivered_date }
      : { ...orderData, promised_delivery_date: form.promised_delivery_date };
  }
  const payload = {
    ...orderData,
    sale_date: form.sale_date,
    // Solo al crear y solo el observador: el dueño no se cambia al editar.
    ...buildJobPayload(),
  };
  // Al editar, las planchas no viajan: se agregan o quitan desde el detalle de costos.
  if (editingId.value) delete payload.extra_plates;
  // El riesgo solo viaja si se cambió: así una venta antigua (sin riesgo) no recibe uno
  // por el simple hecho de editarla.
  if (editingId.value && form.risk_level === riskLevelForPercent(editingSale.value.risk_percent)) {
    delete payload.risk_level;
  }
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
  if (!isValidOrEmpty(form.shipping_cost, { min: 0 })) return "El delivery no puede ser negativo.";
  return "";
}

function validateSaleForm() {
  // Obligatoria en las ventas nuevas; las antiguas pueden seguir sin fuente.
  if (!editingId.value && !form.sale_source) return "Elige la fuente de venta: Instagram, Facebook o Personal.";
  if (!form.printer_id) return "Selecciona una impresora.";
  if (editingStatus.value === "entregada") {
    if (!form.delivered_date) return "Indica la fecha real de entrega.";
  } else if (!form.promised_delivery_date) {
    return "Indica la fecha de entrega comprometida.";
  }
  const jobError = validateJobInputs();
  if (jobError) return jobError;
  if (!editingId.value) {
    const plateError = platesError(extraPlates.value);
    if (plateError) return plateError;
  }
  if (isGift.value) return "";
  if (useManualPrice.value) {
    if (!isValidNumber(manualPrice.value, { min: 0, allowZero: false })) return "Ingresa un precio válido, mayor a 0.";
  } else if (!selectedScenario.value) {
    return suggestError.value || "Elige uno de los precios sugeridos o marca \"Definir yo el precio final\".";
  }
  return "";
}

async function handleSubmit() {
  let validationError = validateSaleForm();
  if (!validationError && !useManualPrice.value && !isGift.value) {
    // Recalcular antes de guardar: si el usuario cambió un dato hace un instante, el
    // escenario en pantalla podría ser del cálculo anterior (el recálculo va con retardo).
    await refreshSuggestion();
    validationError = validateSaleForm();
  }
  if (validationError) {
    formError.value = validationError;
    return;
  }
  if (mixedOwners.value) {
    const ok = await confirmAction({
      title: "Materiales de distintos dueños",
      message:
        `Esta venta usa recursos de ${resourceOwnerSummary.value.length} dueños: ${mixedOwnersText.value}. ` +
        "Se descontará del inventario de cada uno y cada costo quedará a cuenta de su dueño. ¿Registrarla así?",
      confirmLabel: "Sí, registrar",
    });
    if (!ok) return;
  }
  saving.value = true;
  formError.value = "";
  try {
    const sale = editingId.value
      ? await salesApi.updateSale(editingId.value, buildPayload())
      : await salesApi.createSale(buildPayload());
    const wasNew = !editingId.value;
    showModal.value = false;
    await loadSales();
    flashRow(sale.id);
    showToast(wasNew ? "Venta registrada" : "Venta actualizada", {
      detail: sale.client_name,
      celebrate: wasNew,
    });
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
const statusModalDelivers = ref(false);
watch(statusModalSaleId, (id) => {
  if (!id) statusModalDelivers.value = false;
});
// Cambio desde el detalle del pedido. Si se canceló y se rehízo, se muestra el pedido nuevo.
async function onOrderChanged(s) {
  if (s?.redone_as_id) {
    statusModalSaleId.value = null;
    await loadSales();
    flashRow(s.redone_as_id);
    showToast("Pedido rehecho", { detail: "El nuevo ya está En producción" });
    return;
  }
  await loadSales();
  flashRow(s?.id);
}
const advancingId = ref(null);

// Botón rápido para el paso siguiente (el resto de opciones está en el detalle).
async function advance(sale) {
  const next = NEXT_ACTION[sale.status];
  if (!next) return;
  if (next.status === "entregada" && isUnpaid(sale)) {
    // "Por cobrar": se entrega desde el detalle, donde se elige cómo pagó o hasta cuándo tiene plazo.
    statusModalDelivers.value = true;
    statusModalSaleId.value = sale.id;
    return;
  }
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
    flashRow(sale.id);
    showToast(`Pedido: ${STATUS_LABELS[next.status]}`, { detail: sale.client_name });
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

// Botón + de la barra inferior del celular: llega como /ventas?nueva=1.
const route = useRoute();
const router = useRouter();
function openCreateFromQuery() {
  if (!route.query.nueva) return;
  const { nueva, ...rest } = route.query;
  router.replace({ query: rest });
  if (!(auth.isWatcher && !observedUsers.value.length)) openCreate();
}
watch(() => route.query.nueva, openCreateFromQuery);

onMounted(async () => {
  nextTick(moveQuickPill);
  await Promise.all([loadCatalog(), loadObservedUsers()]);
  openCreateFromQuery();
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
      <div class="header-actions">
        <button class="btn btn-secondary" :disabled="exporting || !total" title="Descarga las ventas con los filtros y el orden actuales" @click="exportExcel">
          <Icon name="download" :size="16" /> {{ exporting ? "Preparando..." : "Descargar Excel" }}
        </button>
        <button class="btn btn-primary" :disabled="auth.isWatcher && !observedUsers.length" @click="openCreate">
          <Icon name="plus" :size="16" /> Nueva venta
        </button>
      </div>
    </div>

    <div v-if="exportError" class="alert alert-danger">{{ exportError }}</div>

    <div ref="quickEl" class="quick-status" role="tablist" aria-label="Estado de los pedidos">
      <span
        class="quick-pill"
        :class="{ visible: quickPill.visible }"
        :style="{ transform: `translateX(${quickPill.left}px)`, width: `${quickPill.width}px` }"
        aria-hidden="true"
      ></span>
      <button
        v-for="q in QUICK_STATUS"
        :key="q.value"
        type="button"
        role="tab"
        :class="{ on: filters.status === q.value }"
        :aria-selected="filters.status === q.value"
        @click="setQuickStatus(q.value)"
      >
        {{ q.label }}
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
        <div v-if="observedUsers.length" class="field">
          <label>Cuenta</label>
          <!-- Ventas a nombre de la cuenta o que registró ella (la Empresa vende sin impresora propia). -->
          <select v-model="filters.account_id">
            <option value="">Todas</option>
            <option v-for="u in observedUsers" :key="u.id" :value="u.id">
              {{ u.username }}{{ u.is_self ? " (Empresa)" : "" }}
            </option>
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
          <label>Fuente de venta</label>
          <select v-model="filters.sale_source">
            <option value="">Todas</option>
            <option v-for="src in SALE_SOURCES" :key="src.value" :value="src.value">{{ src.label }}</option>
            <option :value="NO_SALE_SOURCE.value">{{ NO_SALE_SOURCE.label }}</option>
          </select>
        </div>
        <div class="field">
          <label>Ordenar por</label>
          <select v-model="sortKey">
            <option v-for="o in SORT_OPTIONS" :key="`${o.by}:${o.direction}`" :value="`${o.by}:${o.direction}`">{{ o.label }}</option>
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
      <LoadingSkeleton v-if="loading && !sales.length" />
      <div v-else-if="!sales.length" class="empty-state">
        <h3>No hay ventas</h3>
        <p>Ajusta los filtros o crea una venta nueva.</p>
      </div>
      <template v-else>
        <div class="table-wrap sales-table-wrap">
          <table class="sales-table">
            <thead>
              <tr>
                <th><button type="button" class="th-sort" :class="{ on: sort.by === 'fecha' }" @click="sortBy('fecha')">Pedido <span>{{ sortArrow("fecha") }}</span></button></th>
                <th>Estado</th>
                <th><button type="button" class="th-sort" :class="{ on: sort.by === 'cliente' }" @click="sortBy('cliente')">Cliente <span>{{ sortArrow("cliente") }}</span></button></th>
                <th v-if="auth.isWatcher" class="col-owner">Venta de</th>
                <th>Registrada por</th>
                <th class="col-printer">Impresora</th>
                <th v-for="col in MONEY_COLUMNS" :key="col.by" class="text-right">
                  <button type="button" class="th-sort" :class="{ on: sort.by === col.by }" @click="sortBy(col.by)">
                    <span>{{ sortArrow(col.by) }}</span> {{ col.label }}
                  </button>
                </th>
                <th>Pago</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <template v-for="s in sales" :key="s.id">
              <tr class="sale-row" :class="{ 'row-expanded': expandedCostId === s.id, 'row-flash': flashedId === s.id }">
                <td class="c-date" data-label="Pedido">
                  <span class="nowrap">{{ formatDate(s.sale_date) }}</span>
                  <div class="text-sm" :class="isOverdue(s, today) ? 'overdue-text' : 'text-muted'">{{ deliveryLabel(s) }}</div>
                </td>
                <td class="c-status">
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
                <td class="c-client">
                  <strong>{{ s.client_name }}</strong>
                  <span v-if="s.warehouse_item_id" class="badge piece-en_almacen" style="margin-left: 6px">Pieza del Almacén</span>
                  <span v-if="s.payment_method === GIFT_PAYMENT_METHOD" class="badge badge-gift" style="margin-left: 6px">🎁 Regalo</span>
                  <span
                    v-if="s.cost_by_owner?.length > 1"
                    class="badge badge-mixed"
                    style="margin-left: 6px"
                    :title="`Costos: ${s.cost_by_owner.map((o) => o.username).join(', ')}`"
                  >Materiales mixtos</span>
                  <div v-if="s.buyer_name" class="text-muted text-sm">{{ s.buyer_name }}</div>
                  <!-- Notebooks: la impresora (y de quién es la venta) van aquí para que la tabla quepa. -->
                  <div class="text-muted text-sm compact-only">
                    🖨️ {{ s.printer_name }}<template v-if="auth.isWatcher"> · venta de {{ s.owner_username }}</template>
                  </div>
                </td>
                <td v-if="auth.isWatcher" class="c-owner" data-label="Venta de">{{ s.owner_username }}</td>
                <td class="c-seller" data-label="Registrada por">
                  <span class="seller-tag" :class="{ 'is-other': s.created_by_user_id !== s.owner_id }">
                    {{ sellerLabel(s) }}
                  </span>
                </td>
                <td class="c-printer" data-label="Impresora">{{ s.printer_name }}</td>
                <td class="text-right mono c-money c-price" data-label="Precio">
                  {{ formatCurrency(s.piece_price ?? s.price) }}
                  <div v-if="Number(s.shipping_cost) > 0 && Number(s.price) > 0" class="delivery-extra">+ {{ formatCurrency(s.shipping_cost) }} delivery</div>
                </td>
                <td class="text-right c-money c-cost" data-label="Costo">
                  <button
                    type="button"
                    class="cost-toggle mono"
                    :aria-expanded="expandedCostId === s.id"
                    title="Ver el desglose de costos"
                    @click="toggleCost(s.id)"
                  >
                    <span v-if="s.has_provisional_costs" class="provisional-mark" title="Costo provisional: faltan insumos por comprar">≈</span>
                    {{ formatCurrency(s.piece_cost ?? s.total_cost) }}
                    <Icon name="chevronDown" :size="16" :class="{ 'is-open': expandedCostId === s.id }" />
                  </button>
                </td>
                <!-- Un cancelado no dejó ganancia: se muestra su pérdida (si la hubo). -->
                <td v-if="s.status === 'cancelado'" class="text-right mono c-money c-profit" data-label="Pérdida">
                  <span v-if="Number(s.loss_amount) > 0" style="color: var(--danger)" title="Pérdida por la cancelación">
                    −{{ formatCurrency(s.loss_amount) }}
                  </span>
                  <div v-if="s.cancel_printed_percent !== null && s.cancel_printed_percent !== undefined" class="text-muted text-sm">
                    {{ Number(s.cancel_printed_percent) }} % impreso
                  </div>
                  <span v-else class="text-muted">—</span>
                </td>
                <td v-else class="text-right mono c-money c-profit" data-label="Ganancia" :style="{ color: Number(s.profit) < 0 ? 'var(--danger)' : 'var(--success)' }">
                  {{ formatCurrency(s.profit) }}
                </td>
                <td class="text-right c-money c-margin" data-label="Margen">{{ s.status === "cancelado" ? "—" : formatPercent(s.piece_margin_percent ?? s.margin_percent) }}</td>
                <td class="c-pay" data-label="Pago">
                  <span class="badge badge-neutral">{{ paymentLabel(s.payment_method) }}</span>
                  <div v-if="dueInfo(s, today)" class="due-tag" :class="{ 'is-overdue': dueInfo(s, today).overdue }">
                    {{ dueInfo(s, today).text }}
                  </div>
                  <div v-if="s.sale_source" class="source-tag" :style="{ '--source-color': saleSourceInfo(s.sale_source).color }">
                    <Icon :name="saleSourceInfo(s.sale_source).icon" :size="12" />
                    {{ saleSourceInfo(s.sale_source).label }}
                  </div>
                </td>
                <td class="text-right c-actions">
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
              <tr v-if="expandedCostId === s.id" class="cost-detail-row">
                <td :colspan="auth.isWatcher ? 12 : 11">
                  <div class="cost-detail">
                    <div class="cost-lines">
                      <div v-for="line in costLines(s)" :key="line.label" class="cost-line" :class="{ 'is-provisional': line.provisional }">
                        <span class="cost-line-label">{{ line.label }}</span>
                        <span v-if="line.detail" class="text-muted text-sm">{{ line.detail }}</span>
                        <span class="cost-line-value mono">{{ formatCurrency(line.value) }}</span>
                      </div>
                      <div v-if="s.plates?.length || canManagePlates(s)" class="plates-block">
                        <div class="plates-block-head">
                          <span class="cost-line-label">Planchas</span>
                          <span class="text-muted text-sm">
                            Plancha 1: {{ s.printer_name }} · {{ Number(s.print_hours) }} h
                            <template v-if="s.plates?.length"> · las adicionales ya están sumadas arriba</template>
                          </span>
                          <button v-if="canManagePlates(s)" type="button" class="btn btn-secondary btn-sm" @click="plateSale = s">
                            <Icon name="plus" :size="14" /> Plancha / reimpresión
                          </button>
                        </div>
                        <div v-for="p in s.plates" :key="p.id" class="cost-line plate-line" :class="{ 'is-reprint': p.is_reprint }">
                          <span class="cost-line-label">
                            <span v-if="p.is_reprint" class="badge badge-danger">Reimpresión</span>
                            {{ p.name }}
                          </span>
                          <span class="text-muted text-sm">
                            {{ p.printer_name }} · {{ Number(p.print_hours) }} h<template v-if="p.filaments.length">
                              · {{ p.filaments.map((f) => `${f.filament_label} (${Number(f.grams_used)} g)`).join(" · ") }}</template>
                          </span>
                          <span class="cost-line-value mono">{{ formatCurrency(p.total_cost) }}</span>
                          <button
                            v-if="canManagePlates(s)"
                            type="button"
                            class="btn btn-icon btn-ghost btn-sm"
                            title="Quitar plancha"
                            @click="removePlate(s, p)"
                          >
                            <Icon name="close" :size="13" />
                          </button>
                        </div>
                      </div>
                    </div>
                    <div class="cost-summary">
                      <div v-if="s.cost_by_owner?.length > 1" class="owner-costs">
                        <span class="cost-line-label">Costos por cuenta</span>
                        <div v-for="o in s.cost_by_owner" :key="o.user_id" class="cost-line text-sm">
                          <span>
                            {{ o.username }}
                            <span class="text-muted">
                              ({{ [Number(o.machine) && "máquina", Number(o.material) && "material", Number(o.supplies) && "insumos", Number(o.postprocess) && "postprocesado"].filter(Boolean).join(", ") }})
                            </span>
                          </span>
                          <span class="mono">{{ formatCurrency(o.total) }}</span>
                        </div>
                      </div>
                      <div v-if="s.has_provisional_costs" class="provisional-note">
                        Se usaron insumos sin stock: el costo y la ganancia se ajustan al registrar la compra (Reponer).
                      </div>
                      <div v-if="Number(s.shipping_cost) > 0 && Number(s.price) > 0" class="cost-line text-sm text-muted">
                        <span>Impresión {{ formatCurrency(s.piece_price ?? s.price) }} + delivery {{ formatCurrency(s.shipping_cost) }}</span><span></span>
                      </div>
                      <div class="cost-line"><span>Total cobrado</span><span class="mono">{{ formatCurrency(s.price) }}</span></div>
                      <div class="cost-line"><span>Costo total<template v-if="Number(s.shipping_cost) > 0"> (con delivery)</template></span><span class="mono">−{{ formatCurrency(s.total_cost) }}</span></div>
                      <div v-if="Number(s.reprint_cost) > 0" class="cost-line text-sm reprint-note">
                        <span>incluye reimpresiones</span><span class="mono">{{ formatCurrency(s.reprint_cost) }}</span>
                      </div>
                      <div class="cost-line cost-line-total">
                        <span>Ganancia</span>
                        <span class="mono" :style="{ color: Number(s.profit) < 0 ? 'var(--danger)' : 'var(--success)' }">
                          {{ formatCurrency(s.profit) }}
                        </span>
                      </div>
                      <div v-if="Number(s.risk_amount) > 0" class="cost-line text-sm text-muted">
                        <span>incluye reserva por riesgo ({{ Number(s.risk_percent) }}%)</span>
                        <span class="mono">{{ formatCurrency(s.risk_amount) }}</span>
                      </div>
                    </div>
                  </div>
                </td>
              </tr>
              </template>
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

    <Modal persistent v-if="showModal" :title="editingId ? 'Editar venta' : 'Nueva venta'" width="680px" @close="showModal = false">
      <form @submit.prevent="handleSubmit">
        <div v-if="editingSale" class="alert alert-info" style="margin-bottom: 14px">
          Venta de <strong>{{ editingSale.owner_username }}</strong> · Registrada por
          <strong>{{ sellerLabel(editingSale) }}</strong>
        </div>
        <div v-else-if="auth.isWatcher" class="alert alert-info" style="margin-bottom: 14px">
          <span v-if="auth.isCompany">
            La venta es del <strong>dueño de la impresora</strong> que elijas y queda registrada por ti. Puedes usar
            filamentos e insumos de cualquier socio o de la Empresa (material mixto): cada costo queda a cuenta de su
            dueño y se descuenta de su inventario.
          </span>
          <span v-else>
            La venta es del <strong>dueño de la impresora</strong> que elijas y solo usa su inventario. Aparecerá en su
            registro indicando que la hiciste tú ({{ auth.user?.username }}).
          </span>
        </div>
        <div v-if="fromWarehouse" class="alert alert-warning" style="margin-bottom: 14px">
          Pedido de una <strong>pieza del Almacén</strong>: la pieza ya existe, así que no se cambian materiales, horas
          ni delivery (el delivery se cambia desde el estado del pedido). Puedes editar precio, fecha de entrega,
          trabajo, comprador, método de pago y notas.
        </div>
        <div v-else-if="productionLocked" class="alert alert-warning" style="margin-bottom: 14px">
          Pedido <strong>{{ STATUS_LABELS[editingStatus] }}</strong>: la pieza ya se está fabricando, así que no se
          cambian materiales ni horas (el delivery se cambia desde el estado del pedido). Puedes editar precio, fecha de
          entrega, trabajo, comprador, método de pago
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
            <span v-if="form.payment_method === 'por_cobrar'" class="field-hint">
              Se mantiene Por cobrar mientras se fabrica. Al entregarlo se elige cómo pagó o hasta cuándo tiene plazo.
            </span>
          </div>
          <div class="field">
            <label>Trabajo</label>
            <input v-model="form.client_name" required />
          </div>
          <div class="field">
            <label>Comprador (opcional)</label>
            <input v-model="form.buyer_name" />
          </div>
          <SaleSourcePicker v-model="form.sale_source" :required="!editingId" class="form-span" />
          <div class="field">
            <label>Impresora</label>
            <select v-model="form.printer_id" required :disabled="productionLocked">
              <option value="" disabled>Selecciona</option>
              <option v-for="p in salePrinters" :key="p.id" :value="p.id">
                {{ auth.isWatcher ? withOwner(p.name, p.owner_id) : p.name }}
              </option>
            </select>
            <span v-if="auth.isWatcher && saleOwnerName" class="field-hint">
              La venta es de <strong>{{ saleOwnerName }}</strong> (dueño de la impresora). Queda registrada por ti.
            </span>
          </div>
          <div class="field">
            <label>Tiempo de impresión</label>
            <HoursMinutesInput v-model="form.print_hours" :disabled="productionLocked" />
          </div>
          <div class="field">
            <label>Horas de postprocesado</label>
            <input v-model.number="form.postprocess_hours" type="number" min="0" step="0.1" :disabled="productionLocked" />
          </div>
          <div class="field">
            <label>Delivery (CLP)</label>
            <input v-model.number="form.shipping_cost" type="number" min="0" step="1" :disabled="productionLocked" />
            <span class="field-hint">Va aparte del precio de la impresión: lo paga el cliente y se le devuelve a quien lo lleve.</span>
          </div>
          <div class="field">
            <label>¿Quién lo lleva? (opcional)</label>
            <input v-model="form.delivery_by" list="sale-delivery-people" maxlength="60" placeholder="Ej: Omar" />
            <datalist id="sale-delivery-people">
              <option v-for="p in deliveryPeople" :key="p" :value="p" />
            </datalist>
          </div>
        </div>

        <div class="field mt-2">
          <label>Filamentos usados (opcional, puede ser más de uno)</label>
          <div class="flex gap-2 add-row">
            <button
              type="button"
              class="btn btn-secondary"
              style="flex: 1; justify-content: flex-start; overflow: hidden"
              :disabled="productionLocked || needsPrinterFirst"
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
          <div class="flex gap-2 add-row">
            <select v-model="newSupplyId" style="flex: 1" :disabled="productionLocked || needsPrinterFirst">
              <option value="" disabled>Selecciona un insumo</option>
              <option v-for="s in ownerSupplies" :key="s.id" :value="s.id">{{ auth.isCompany ? withOwner(s.name, s.owner_id) : s.name }}</option>
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
          <div v-if="supplyShortages.length && !productionLocked" class="alert alert-warning mt-2">
            <strong>No te alcanzan los insumos:</strong>
            <span v-for="x in supplyShortages" :key="x.name"> {{ x.name }} (hay {{ x.available }}, quedarás debiendo {{ x.owed }}).</span>
            Se descuentan igual y su costo es provisional hasta que registres la compra con <strong>Reponer</strong> en Inventario.
          </div>
        </div>

        <RiskLevelPicker v-if="!productionLocked && !isGift" v-model="form.risk_level" class="mt-2" />

        <ExtraPlatesEditor
          v-if="!editingId"
          v-model="extraPlates"
          class="mt-2"
          :printers="auth.isCompany ? printers : ownerPrinters"
          :filaments="selectableFilaments"
          :owner-names="pickerOwnerNames"
          :default-printer-id="form.printer_id"
          :disabled="needsPrinterFirst"
        />
        <div v-if="mixedOwners" class="alert alert-warning mixed-owners mt-2" role="alert">
          <strong>⚠️ Materiales de {{ resourceOwnerSummary.length }} dueños distintos:</strong> {{ mixedOwnersText }}.
          Se descuenta del inventario de cada uno y cada costo queda a cuenta de su dueño.
        </div>
        <div v-else-if="editingSale?.plates?.length" class="alert alert-info mt-2">
          Este pedido tiene {{ editingSale.plates.length }} plancha(s) adicional(es) (ya incluidas en el costo). Se agregan
          o quitan desde el detalle de costos en la lista de ventas.
        </div>

        <div class="field mt-2">
          <label>Precio de venta</label>
          <span v-if="!form.printer_id" class="field-hint">
            Selecciona una impresora y completa los datos del trabajo para ver el precio sugerido.
          </span>
          <span v-else-if="suggesting && !suggestion" class="field-hint">Calculando precio sugerido...</span>
          <div v-else-if="suggestError" class="alert alert-danger">{{ suggestError }}</div>

          <div v-if="isGift" class="alert alert-info gift-alert">
            <strong>🎁 Regalo:</strong> se registra con precio $0. Los materiales, horas e insumos se descuentan igual y su
            costo<template v-if="suggestion"> (<strong>{{ formatCurrency(suggestion.breakdown.total_cost) }}</strong>)</template>
            queda como pérdida.
          </div>
          <template v-else>
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
                <strong class="mono price-option-total">{{ formatCurrency(pieceOf(s.price)) }}</strong>
                <span v-if="formDelivery > 0" class="price-option-meta">+ {{ formatCurrency(formDelivery) }} delivery = {{ formatCurrency(s.price) }}</span>
                <span class="price-option-meta">Ganancia {{ formatCurrency(s.profit) }}</span>
              </label>
            </div>
            <span class="field-hint">
              Costo del trabajo: {{ formatCurrency(suggestion.breakdown.total_cost) }}. El margen se aplica a material,
              depreciación, energía e insumos; postprocesado, delivery y el riesgo de fallo
              ({{ formatCurrency(suggestion.breakdown.risk_cost) }}) se suman al final sin margen.
              <template v-if="suggesting">Actualizando...</template>
            </span>
          </template>

          <label class="manual-price-toggle flex items-center gap-2 mt-2">
            <input v-model="useManualPrice" type="checkbox" style="width: auto" />
            Definir yo el precio de la impresión
          </label>
          <template v-if="useManualPrice">
            <input
              v-model.number="manualPrice"
              type="number"
              min="0"
              step="1"
              placeholder="Ej: 15000"
              aria-label="Precio de la impresión, sin delivery"
              style="max-width: 200px"
            />
            <div v-if="manualPriceBreakdown" class="alert alert-info">
              Impresión: <strong>{{ formatCurrency(manualPriceBreakdown.price) }}</strong>
              <template v-if="manualPriceBreakdown.delivery > 0">
                + delivery {{ formatCurrency(manualPriceBreakdown.delivery) }} =
                <strong>{{ formatCurrency(manualPriceBreakdown.total) }}</strong> a cobrar
              </template>
              <template v-if="manualPriceBreakdown.profit !== null">
                · Ganancia:
                <span :style="{ color: manualPriceBreakdown.profit < 0 ? 'var(--danger)' : undefined }">
                  {{ formatCurrency(manualPriceBreakdown.profit) }}
                </span>
              </template>
            </div>
            <div v-else class="alert alert-danger">Ingresa el precio de la impresión (sin delivery), mayor a 0.</div>
          </template>
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
      :start-delivery="statusModalDelivers"
      @close="statusModalSaleId = null"
      @changed="onOrderChanged"
    />

    <AddPlateModal
      v-if="plateSale"
      :sale="plateSale"
      :printers="saleOwnerPrinters(plateSale)"
      :filaments="saleOwnerFilaments(plateSale)"
      :owner-names="pickerOwnerNames"
      @close="plateSale = null"
      @saved="onPlateSaved"
    />

    <FilamentPickerModal
      v-if="showFilamentPicker"
      :filaments="ownerFilaments"
      :exclude-ids="filamentRows.map((r) => r.filament_id)"
      :owner-names="pickerOwnerNames"
      title="Seleccionar filamento"
      @select="onFilamentPicked"
      @close="showFilamentPicker = false"
    />
  </div>
</template>

<style scoped>
.header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* Selector de fuente de venta: ocupa toda la fila del formulario. */
.form-span {
  grid-column: 1 / -1;
}

/* Títulos de columna que ordenan la hoja (otro toque invierte el orden). */
.th-sort {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  letter-spacing: inherit;
  text-transform: inherit;
  cursor: pointer;
}
.th-sort:hover,
.th-sort.on {
  color: var(--primary);
}
.th-sort span {
  display: inline-block;
  min-width: 0.7em;
  font-size: 0.7em;
}

/* Fuente de venta bajo el método de pago. */
.source-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  color: var(--source-color);
  font-size: 0.75rem;
  font-weight: 700;
  white-space: nowrap;
}
/* ---- Hoja de ventas: en pantallas angostas (celular, tablet, notebook chico) cada venta es
   una tarjeta (hasta 1380 px) en vez de una fila de 11 columnas que había que desplazar de lado. ---- */
.sales-table .nowrap {
  white-space: nowrap;
}
.sales-table .compact-only {
  display: none;
}
/* Pantallas medianas (1381–1600 px): misma tabla, más compacta. La impresora y "Venta de" pasan bajo
   el cliente, así caben todas las columnas sin desplazar de lado. */
@media (min-width: 1381px) and (max-width: 1600px) {
  .sales-table .col-printer,
  .sales-table .col-owner,
  .sales-table .c-printer,
  .sales-table .c-owner {
    display: none;
  }
  .sales-table .compact-only {
    display: block;
  }
  .sales-table thead th,
  .sales-table tbody td {
    padding-left: 8px;
    padding-right: 8px;
  }
  .sales-table .c-actions .btn-icon {
    width: 30px;
    height: 30px;
  }
  .sales-table .c-actions .flex {
    gap: 2px !important;
  }
}
@media (max-width: 1380px) {
  .sales-table-wrap {
    border: none;
    overflow: visible;
  }
  .sales-table {
    min-width: 0;
  }
  .sales-table thead {
    display: none;
  }
  .sales-table,
  .sales-table tbody {
    display: block;
  }
  .sales-table tr.sale-row {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 10px 14px;
    align-items: start;
    padding: 14px;
    margin-bottom: 12px;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: var(--surface);
  }
  .sales-table tr.sale-row.row-expanded {
    margin-bottom: 0;
    border-bottom-left-radius: 0;
    border-bottom-right-radius: 0;
  }
  .sales-table tr.sale-row:hover {
    background: var(--surface);
  }
  .sales-table tr.sale-row > td {
    display: block;
    min-width: 0;
    padding: 0;
    border: none;
    text-align: left;
  }
  .sales-table td[data-label]::before {
    content: attr(data-label);
    display: block;
    margin-bottom: 2px;
    color: var(--text-muted);
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .sales-table tr.sale-row {
    grid-template-areas:
      "client client client actions"
      "status status date date"
      "price cost profit margin"
      "pay pay seller printer"
      "owner owner . .";
  }
  .sales-table .c-client { grid-area: client; font-size: 0.95rem; }
  .sales-table .c-actions { grid-area: actions; }
  .sales-table .c-status { grid-area: status; }
  .sales-table .c-date { grid-area: date; }
  .sales-table .c-price { grid-area: price; }
  .sales-table .c-cost { grid-area: cost; }
  .sales-table .c-profit { grid-area: profit; }
  .sales-table .c-margin { grid-area: margin; }
  .sales-table .c-pay { grid-area: pay; }
  .sales-table .c-seller { grid-area: seller; }
  .sales-table .c-printer { grid-area: printer; }
  .sales-table .c-owner { grid-area: owner; }
  .sales-table .c-money .cost-toggle {
    padding: 0;
  }
  .sales-table tr.cost-detail-row {
    display: block;
    margin-bottom: 12px;
    border: 1px solid var(--border);
    border-top: none;
    border-radius: 0 0 var(--radius-md) var(--radius-md);
  }
  .sales-table tr.cost-detail-row > td {
    display: block;
    border: none;
  }
}
@media (max-width: 560px) {
  .sales-table tr.sale-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    grid-template-areas:
      "client actions"
      "status date"
      "price cost"
      "profit margin"
      "pay pay"
      "seller printer"
      "owner owner";
  }
}
.due-tag {
  margin-top: 4px;
  max-width: 150px;
  color: var(--warning);
  font-size: 0.75rem;
  font-weight: 700;
  line-height: 1.3;
}
.due-tag.is-overdue {
  color: var(--danger);
}
.quick-status {
  position: relative;
  display: inline-flex;
  margin-bottom: 12px;
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
}
.quick-status button {
  position: relative;
  z-index: 1;
  padding: 7px 16px;
  border: 0;
  border-radius: 9px;
  background: none;
  color: var(--text-muted);
  font: inherit;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: color 0.25s;
}
.quick-status button.on {
  color: #fff;
}
.quick-pill {
  position: absolute;
  top: 4px;
  bottom: 4px;
  left: 0;
  border-radius: 9px;
  background: linear-gradient(135deg, var(--primary), color-mix(in srgb, var(--primary) 70%, #a855f7));
  opacity: 0;
  transition: transform 0.4s var(--ease-spring), width 0.4s var(--ease-spring), opacity 0.2s;
}
.quick-pill.visible {
  opacity: 1;
}
@media (max-width: 640px) {
  .quick-status {
    display: flex;
  }
  .quick-status button {
    flex: 1;
  }
}

.overdue-text {
  color: var(--danger);
  font-weight: 700;
}

/* Quién registró la venta. Resaltado cuando no fue el dueño del inventario (ej. un
   observador), para que el dueño lo note de inmediato. */
.delivery-extra {
  color: var(--text-muted);
  font-size: 0.72rem;
  font-weight: 500;
  white-space: nowrap;
}

.seller-tag {
  display: inline-block;
  max-width: 100%;
  font-size: 0.82rem;
  overflow-wrap: anywhere;
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

.cost-toggle {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px 4px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text);
  font: inherit;
  cursor: pointer;
}
.cost-toggle:hover {
  background: var(--surface-alt);
  color: var(--primary);
}
.cost-toggle svg {
  transition: transform 0.15s ease;
}
.cost-toggle svg.is-open {
  transform: rotate(180deg);
}
tr.row-expanded td {
  border-bottom-color: transparent;
}
.cost-detail-row td {
  background: var(--surface-alt);
}
/* Ancho acotado: si el panel tomara todo el ancho de la fila, estiraría la tabla. */
.cost-detail {
  display: grid;
  grid-template-columns: minmax(0, 520px) 240px;
  gap: 24px;
  max-width: 800px;
  padding: 4px 4px 8px;
}
.cost-lines,
.cost-summary {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cost-line {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.cost-line > :last-child {
  margin-left: auto;
  white-space: nowrap;
}
.cost-line-label {
  font-weight: 600;
  white-space: nowrap;
}
.cost-summary {
  padding-left: 24px;
  border-left: 1px solid var(--border);
}
.cost-line-total {
  padding-top: 6px;
  border-top: 1px solid var(--border);
  font-weight: 700;
}
@media (max-width: 720px) {
  .cost-detail {
    grid-template-columns: 1fr;
  }
  .cost-summary {
    padding-left: 0;
    border-left: none;
  }
}

.badge-gift {
  background: var(--primary-soft);
  color: var(--primary);
}
.gift-alert {
  margin-top: 4px;
}

.cost-line.is-provisional,
.provisional-mark,
.provisional-note {
  color: var(--danger);
}
.provisional-mark {
  font-weight: 700;
}
.provisional-note {
  font-size: 0.8rem;
  margin-bottom: 4px;
}

.plates-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 6px;
  padding-top: 8px;
  border-top: 1px dashed var(--border);
}
.plates-block-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.plates-block-head > :last-child {
  margin-left: auto;
}
.plate-line .cost-line-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
}
.plate-line .cost-line-value {
  margin-left: auto;
}
.cost-line.plate-line > button {
  margin-left: 0;
}
.plate-line.is-reprint .cost-line-value,
.reprint-note {
  color: var(--danger);
}

.owner-costs {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-bottom: 8px;
  margin-bottom: 4px;
  border-bottom: 1px dashed var(--border);
}

.badge-mixed {
  background: var(--warning-soft);
  color: var(--warning);
}
.mixed-owners {
  display: block;
}
</style>
