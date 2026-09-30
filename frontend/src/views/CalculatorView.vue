<script setup>
import { ref, reactive, onMounted, computed, watch, nextTick } from "vue";
import * as calculatorApi from "../api/calculator";
import * as printersApi from "../api/printers";
import * as inventoryApi from "../api/inventory";
import * as quotesApi from "../api/quotes";
import { PAYMENT_METHODS } from "../api/sales";
import { BUSINESS_NAME, BUSINESS_LOGO_URL } from "../utils/business";
import { formatCurrency, todayISO } from "../utils/format";
import { GRAMS_MAX, isValidGrams, isValidNumber, gramsErrorMessage, extractApiError } from "../utils/validation";
import { promptExhaustedFilaments } from "../utils/exhaustedFilaments";
import { useAuthStore } from "../stores/auth";
import Modal from "../components/Modal.vue";
import Icon from "../components/Icon.vue";
import DoughnutChart from "../components/DoughnutChart.vue";
import QuoteDocument from "../components/QuoteDocument.vue";
import FilamentPickerModal from "../components/FilamentPickerModal.vue";
import { useObservedUsers } from "../composables/useObservedUsers";

const auth = useAuthStore();
// Observador: cotiza con recursos de varios usuarios (puede mezclarlos), así que cada
// impresora/filamento/insumo muestra de quién es. Para los demás roles no aparece nada.
const { namesById, loadObservedUsers, ownerName } = useObservedUsers();

function withOwner(label, ownerId, sep = " — ") {
  const owner = ownerName(ownerId);
  return owner ? `${label}${sep}de ${owner}` : label;
}

const printers = ref([]);
const filaments = ref([]);
const supplies = ref([]);
const loadingCatalog = ref(true);

const form = reactive({
  printer_id: "",
  print_hours: null,
  postprocess_hours: 0,
  shipping_cost: 0,
});

/* -------- Filament selection (single vs multicolor) -------- */
const isMulticolor = ref(false);
const singleFilamentId = ref("");
const singleGramsUsed = ref(null);

const filamentRows = ref([]); // { id, filament_id, grams_used }
const newFilamentRowId = ref("");
const newFilamentRowGrams = ref(null);
const filamentRowError = ref("");

/* -------- Filament picker modal (shared by single mode and multicolor rows) -------- */
const showFilamentPicker = ref(false);
const filamentPickerTarget = ref(null); // "single" | "row"

function openFilamentPicker(target) {
  filamentPickerTarget.value = target;
  showFilamentPicker.value = true;
}
function onFilamentPicked(f) {
  if (filamentPickerTarget.value === "single") {
    singleFilamentId.value = f.id;
  } else {
    newFilamentRowId.value = f.id;
  }
  showFilamentPicker.value = false;
}

function addFilamentRow() {
  filamentRowError.value = "";
  if (!newFilamentRowId.value) {
    filamentRowError.value = "Selecciona un filamento.";
    return;
  }
  if (!isValidGrams(newFilamentRowGrams.value)) {
    filamentRowError.value = gramsErrorMessage(newFilamentRowGrams.value);
    return;
  }
  const grams = Number(newFilamentRowGrams.value);
  const existing = filamentRows.value.find((r) => r.filament_id === newFilamentRowId.value);
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
      filament_id: newFilamentRowId.value,
      grams_used: grams,
    });
  }
  newFilamentRowId.value = "";
  newFilamentRowGrams.value = null;
}

// Filaments at 0g can't be picked for a new job — they're kept visible in Inventario
// (marked "Agotado") but excluded here so nothing gets calculated against empty stock.
const selectableFilaments = computed(() => filaments.value.filter((f) => Number(f.available_g) > 0));

const availableFilamentOptions = computed(() =>
  selectableFilaments.value.filter((f) => !filamentRows.value.some((r) => r.filament_id === f.id))
);

function removeFilamentRow(id) {
  filamentRows.value = filamentRows.value.filter((r) => r.id !== id);
}

function filamentName(id) {
  const f = filaments.value.find((x) => x.id === id);
  return f ? filamentLabel(f) : "";
}

// Dueño del filamento elegido (solo observador), para mostrarlo junto al botón.
function filamentOwner(id) {
  const f = filaments.value.find((x) => x.id === id);
  return f ? ownerName(f.owner_id) : "";
}

function printerLabel(p) {
  return withOwner(p.name, p.owner_id);
}

// Compacto a propósito: el picker ya mostró marca, material, color, SKU y gramos
// disponibles antes de elegir, así que acá alcanza con lo mínimo para no desbordar
// el botón (que comparte fila con el input de gramos y "Agregar").
function filamentSummary(id) {
  const f = filaments.value.find((x) => x.id === id);
  return f ? `${f.brand} · ${f.color}` : "";
}

function filamentLabel(f) {
  return f.sku ? `${f.brand} · ${f.color} — ${f.sku}` : `${f.brand} · ${f.color}`;
}

function buildFilamentsPayload() {
  if (isMulticolor.value) {
    return filamentRows.value.map((r) => ({ filament_id: r.filament_id, grams_used: r.grams_used }));
  }
  if (singleFilamentId.value && singleGramsUsed.value) {
    return [{ filament_id: singleFilamentId.value, grams_used: Number(singleGramsUsed.value) }];
  }
  return [];
}

/* -------- Supplies -------- */
const supplyRows = ref([]); // { supply_id, quantity }
const newSupplyId = ref("");
const newSupplyQty = ref(null);
const supplyRowError = ref("");

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

function supplyOwner(id) {
  const s = supplies.value.find((x) => x.id === id);
  return s ? ownerName(s.owner_id) : "";
}

// Texto de <option>: un <select> nativo no admite etiquetas, así que el dueño va en el texto.
function supplyLabel(s) {
  return withOwner(s.name, s.owner_id);
}

/* Resumen de a quién pertenece cada recurso usado en el cálculo (solo observador):
   puede combinar filamentos de distintos dueños, y tiene que saber de quién es cada uno. */
const resourceOwners = computed(() => {
  if (!auth.isWatcher) return [];
  const lines = [];
  const printer = printers.value.find((p) => p.id === form.printer_id);
  if (printer) lines.push({ kind: "Impresora", label: printer.name, owner: ownerName(printer.owner_id) });
  for (const usage of buildFilamentsPayload()) {
    const f = filaments.value.find((x) => x.id === usage.filament_id);
    if (f) lines.push({ kind: "Filamento", label: `${filamentLabel(f)} (${usage.grams_used}g)`, owner: ownerName(f.owner_id) });
  }
  for (const row of supplyRows.value) {
    const s = supplies.value.find((x) => x.id === row.supply_id);
    if (s) lines.push({ kind: "Insumo", label: `${s.name} × ${row.quantity}`, owner: ownerName(s.owner_id) });
  }
  return lines;
});

/* -------- Compute quote -------- */
const quote = ref(null);
const calculating = ref(false);
const calcError = ref("");

const breakdownLabels = ["Material", "Depreciación", "Energía", "Postprocesado", "Consumibles", "Envío"];
const breakdownValues = computed(() => {
  if (!quote.value) return [];
  const b = quote.value.breakdown;
  return [b.material_cost, b.depreciation_cost, b.energy_cost, b.postprocess_cost, b.supplies_cost, b.shipping_cost].map(Number);
});

function buildQuotePayload() {
  return {
    printer_id: form.printer_id,
    filaments: buildFilamentsPayload(),
    print_hours: Number(form.print_hours) || 0,
    postprocess_hours: Number(form.postprocess_hours) || 0,
    shipping_cost: Number(form.shipping_cost) || 0,
    supplies: supplyRows.value.map((r) => ({ supply_id: r.supply_id, quantity: r.quantity })),
  };
}

/** Optional numeric fields default to 0 when left empty — only reject a value
 * the user actually typed in that turns out to be negative/non-numeric. */
function isValidOrEmpty(value, opts) {
  if (value === null || value === undefined || value === "") return true;
  return isValidNumber(value, opts);
}

function validateJobInputs() {
  if (!form.printer_id) return "Selecciona una impresora.";
  if (!isMulticolor.value && singleFilamentId.value && !isValidGrams(singleGramsUsed.value)) {
    return gramsErrorMessage(singleGramsUsed.value);
  }
  if (isMulticolor.value && filamentRows.value.length === 0) {
    return "Agrega al menos un filamento para el trabajo multicolor.";
  }
  if (!isValidOrEmpty(form.print_hours, { min: 0 })) return "Las horas de impresión no pueden ser negativas.";
  if (!isValidOrEmpty(form.postprocess_hours, { min: 0 })) return "Las horas de postprocesado no pueden ser negativas.";
  if (!isValidOrEmpty(form.shipping_cost, { min: 0 })) return "El envío/embalaje no puede ser negativo.";
  return "";
}

/* -------- Precio manual en la tabla de escenarios --------
   El sistema sugiere los escenarios, pero el usuario decide el precio que se usa tanto
   para guardar la venta como para la cotización. La ganancia se calcula igual. */
const useCustomPrice = ref(false);
const customPrice = ref(null);

function round2(n) {
  return Math.round(n * 100) / 100;
}

// Recargo equivalente sobre la base del margen (material + depreciación + energía),
// para comparar un precio manual con los escenarios 90/140/190. Los extras
// (postprocesado, consumibles, envío) no llevan margen, así que se descuentan.
function markupPercent(price, breakdown) {
  const marginBase = Number(breakdown.margin_base_cost);
  if (marginBase <= 0) return 0;
  return Math.round(((price - Number(breakdown.extras_cost)) / marginBase - 1) * 100);
}

// Escenario "virtual" con la misma forma que los del backend, para reutilizar
// openSaveModal/addToCart tal cual.
const customScenario = computed(() => {
  if (!quote.value || !useCustomPrice.value) return null;
  if (!isValidNumber(customPrice.value, { min: 0, allowZero: false })) return null;
  const price = round2(Number(customPrice.value));
  return {
    manual: true,
    label: "Precio manual",
    margin_percent: markupPercent(price, quote.value.breakdown),
    price,
    profit: round2(price - Number(quote.value.breakdown.total_cost)),
  };
});

watch(useCustomPrice, (on) => {
  if (!on || customPrice.value || !quote.value) return;
  // Parte del "Precio Normal" redondeado como guía; el usuario lo ajusta a su gusto.
  const reference = quote.value.scenarios[1] || quote.value.scenarios[0];
  customPrice.value = reference ? Math.round(Number(reference.price)) : null;
});

async function handleCalculate() {
  const validationError = validateJobInputs();
  if (validationError) {
    calcError.value = validationError;
    return;
  }
  calculating.value = true;
  calcError.value = "";
  try {
    quote.value = await calculatorApi.computeQuote(buildQuotePayload());
  } catch (err) {
    calcError.value = extractApiError(err, "No se pudo calcular la cotización.");
  } finally {
    calculating.value = false;
  }
}

/* -------- Save as sale (only for single/no filament jobs) -------- */
const showSaveModal = ref(false);
const selectedScenario = ref(null);
const saveForm = reactive({
  sale_date: todayISO(),
  // El pedido nace Pendiente con esta fecha de entrega comprometida (la usa el Calendario).
  promised_delivery_date: todayISO(),
  client_name: "",
  buyer_name: "",
  payment_method: "efectivo",
  notes: "",
});
const saving = ref(false);
const saveError = ref("");
const saveSuccess = ref("");

/* Precio manual: el usuario fija el precio a su criterio para publicar un número
   redondo, en vez de quedarse con el que sale del margen (ej. $15.000 y no $15.351). */
const useManualPrice = ref(false);
const manualPrice = ref(null);

const manualPriceBreakdown = computed(() => {
  if (!useManualPrice.value || !isValidNumber(manualPrice.value, { min: 0, allowZero: false })) return null;
  const price = Number(manualPrice.value);
  const cost = quote.value ? Number(quote.value.breakdown.total_cost) : 0;
  return { price, profit: price - cost };
});

/* Una venta usa solo el inventario de un dueño. El observador puede cotizar mezclando
   recursos de varios usuarios, pero para guardar como venta todo debe ser del dueño de
   la impresora. Para los demás roles todo es propio y esto no aplica. */
const saleOwnerId = computed(() => printers.value.find((p) => p.id === form.printer_id)?.owner_id || null);
const saleOwnerMismatch = computed(() => {
  if (!auth.isWatcher || !saleOwnerId.value) return false;
  const filamentOwners = buildFilamentsPayload().map((u) => filaments.value.find((f) => f.id === u.filament_id)?.owner_id);
  const supplyOwners = supplyRows.value.map((r) => supplies.value.find((s) => s.id === r.supply_id)?.owner_id);
  return [...filamentOwners, ...supplyOwners].some((id) => id && id !== saleOwnerId.value);
});

function openSaveModal(scenario) {
  selectedScenario.value = scenario;
  useManualPrice.value = !!scenario?.manual;
  manualPrice.value = scenario?.manual
    ? Number(scenario.price)
    : scenario
      ? Math.round(Number(scenario.price))
      : null;
  saveError.value = "";
  saveSuccess.value = "";
  showSaveModal.value = true;
}

async function confirmSaveAsSale() {
  if (saleOwnerMismatch.value) {
    saveError.value = "Para guardar como venta, la impresora, los filamentos y los insumos deben ser del mismo usuario.";
    return;
  }
  if (useManualPrice.value && !isValidNumber(manualPrice.value, { min: 0, allowZero: false })) {
    saveError.value = "Ingresa un precio válido, mayor a 0.";
    return;
  }
  saving.value = true;
  saveError.value = "";
  try {
    const sale = await calculatorApi.saveQuoteAsSale({
      ...buildQuotePayload(),
      sale_date: saveForm.sale_date,
      promised_delivery_date: saveForm.promised_delivery_date,
      client_name: saveForm.client_name,
      buyer_name: saveForm.buyer_name || null,
      payment_method: saveForm.payment_method,
      notes: saveForm.notes || null,
      chosen_margin_percent: selectedScenario.value.margin_percent,
      manual_price: useManualPrice.value ? Number(manualPrice.value) : null,
    });
    showSaveModal.value = false;
    saveSuccess.value =
      "Pedido creado en estado Pendiente. Lo verás en Ventas; cuenta como ingreso cuando lo marques como Entregado.";
    clearDraft();
    await loadCatalog();
    await promptExhaustedFilaments(sale.exhausted_filaments);
    await loadCatalog();
  } catch (err) {
    saveError.value = extractApiError(err, "No se pudo guardar la venta.");
  } finally {
    saving.value = false;
  }
}

/* -------- Quote cart (Cotización) -------- */
const cartItems = ref([]); // { id, description, quantity, unit_price }

function addToCart(scenario) {
  cartItems.value.push({
    id: crypto.randomUUID(),
    description: "",
    quantity: 1,
    unit_price: Number(scenario.price),
  });
}

function removeFromCart(id) {
  cartItems.value = cartItems.value.filter((i) => i.id !== id);
}

// Sin IVA: el total es lo que el usuario puso por producto, tal cual.
const cartTotal = computed(() =>
  cartItems.value.reduce((sum, i) => sum + (Number(i.quantity) || 0) * (Number(i.unit_price) || 0), 0)
);

/* -------- Generate quote (Cotización) -------- */
const showQuoteFormModal = ref(false);
const quoteForm = reactive({ client_name: "", quote_date: todayISO() });
const generatingQuote = ref(false);
const quoteFormError = ref("");
const generatedQuote = ref(null);
const showQuoteDocument = ref(false);

function openQuoteForm() {
  quoteFormError.value = "";
  showQuoteFormModal.value = true;
}

/* Respaldo en texto del comprobante, para poder reimprimirlo/consultarlo después sin
   depender de guardar un PDF (la base es relacional y guarda texto plano). */
function buildQuoteSnapshot(clientName, quoteDate, items) {
  const lines = [
    BUSINESS_NAME,
    `Cotización para: ${clientName}`,
    `Fecha: ${quoteDate}`,
    "",
    "Detalle:",
  ];
  let subtotal = 0;
  for (const i of items) {
    const lineTotal = Number(i.quantity) * Number(i.unit_price);
    subtotal += lineTotal;
    lines.push(
      `- ${i.description} | ${i.quantity} x ${formatCurrency(i.unit_price)} = ${formatCurrency(lineTotal)}`
    );
  }
  lines.push("", `TOTAL: ${formatCurrency(subtotal)}`);
  return lines.join("\n");
}

async function confirmGenerateQuote() {
  if (cartItems.value.some((i) => !i.description.trim())) {
    quoteFormError.value = "Todos los productos de la cotización necesitan un nombre — revisa la lista de arriba.";
    return;
  }
  if (cartItems.value.some((i) => !isValidNumber(i.quantity, { min: 0, allowZero: false }))) {
    quoteFormError.value = "Todas las cantidades deben ser mayores a 0 — revisa la lista de arriba.";
    return;
  }
  if (cartItems.value.some((i) => !isValidNumber(i.unit_price, { min: 0 }))) {
    quoteFormError.value = "Ningún precio unitario puede ser negativo — revisa la lista de arriba.";
    return;
  }
  generatingQuote.value = true;
  quoteFormError.value = "";
  try {
    const items = cartItems.value.map((i) => ({
      description: i.description,
      quantity: i.quantity,
      unit_price: i.unit_price,
    }));
    const created = await quotesApi.createQuote({
      client_name: quoteForm.client_name,
      quote_date: quoteForm.quote_date,
      items,
      document_snapshot: buildQuoteSnapshot(quoteForm.client_name, quoteForm.quote_date, items),
    });
    generatedQuote.value = created;
    showQuoteFormModal.value = false;
    showQuoteDocument.value = true;
    cartItems.value = [];
  } catch (err) {
    quoteFormError.value = extractApiError(err, "No se pudo generar la cotización.");
  } finally {
    generatingQuote.value = false;
  }
}

function printQuote() {
  window.print();
}

async function loadCatalog() {
  loadingCatalog.value = true;
  try {
    const [p, f, s] = await Promise.all([
      printersApi.listPrinters(),
      inventoryApi.listFilaments(),
      inventoryApi.listSupplies(),
    ]);
    printers.value = p;
    filaments.value = f;
    supplies.value = s;
  } finally {
    loadingCatalog.value = false;
  }
}

/* -------- Draft persistence: survives a tab switch or an accidental F5 -------- */
const DRAFT_KEY = "zola:calculator:draft:v1";
let restoringDraft = false;

function saveDraft() {
  try {
    localStorage.setItem(
      DRAFT_KEY,
      JSON.stringify({
        form: { ...form },
        isMulticolor: isMulticolor.value,
        singleFilamentId: singleFilamentId.value,
        singleGramsUsed: singleGramsUsed.value,
        filamentRows: filamentRows.value,
        newFilamentRowId: newFilamentRowId.value,
        newFilamentRowGrams: newFilamentRowGrams.value,
        supplyRows: supplyRows.value,
        newSupplyId: newSupplyId.value,
        newSupplyQty: newSupplyQty.value,
      })
    );
  } catch {
    // localStorage lleno o no disponible (modo privado) -- no vale la pena romper la
    // Calculadora por esto, el usuario simplemente pierde el borrador en ese caso.
  }
}

function clearDraft() {
  try {
    localStorage.removeItem(DRAFT_KEY);
  } catch {
    // ignorar
  }
}

async function restoreDraft() {
  let draft = null;
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    draft = raw ? JSON.parse(raw) : null;
  } catch {
    draft = null;
  }
  if (!draft) return;

  restoringDraft = true;
  Object.assign(form, draft.form || {});
  isMulticolor.value = !!draft.isMulticolor;
  singleFilamentId.value = draft.singleFilamentId || "";
  singleGramsUsed.value = draft.singleGramsUsed ?? null;
  filamentRows.value = Array.isArray(draft.filamentRows) ? draft.filamentRows : [];
  newFilamentRowId.value = draft.newFilamentRowId || "";
  newFilamentRowGrams.value = draft.newFilamentRowGrams ?? null;
  supplyRows.value = Array.isArray(draft.supplyRows) ? draft.supplyRows : [];
  newSupplyId.value = draft.newSupplyId || "";
  newSupplyQty.value = draft.newSupplyQty ?? null;
  // Wait for the watcher below to flush before lifting the guard, otherwise it would
  // immediately re-save the exact same draft it just restored (harmless, but wasteful).
  await nextTick();
  restoringDraft = false;
}

function resetForm() {
  form.printer_id = "";
  form.print_hours = null;
  form.postprocess_hours = 0;
  form.shipping_cost = 0;
  isMulticolor.value = false;
  singleFilamentId.value = "";
  singleGramsUsed.value = null;
  filamentRows.value = [];
  newFilamentRowId.value = "";
  newFilamentRowGrams.value = null;
  filamentRowError.value = "";
  supplyRows.value = [];
  newSupplyId.value = "";
  newSupplyQty.value = null;
  supplyRowError.value = "";
  quote.value = null;
  calcError.value = "";
  useCustomPrice.value = false;
  customPrice.value = null;
  clearDraft();
}

watch(
  () => ({
    form: { ...form },
    isMulticolor: isMulticolor.value,
    singleFilamentId: singleFilamentId.value,
    singleGramsUsed: singleGramsUsed.value,
    filamentRows: filamentRows.value,
    newFilamentRowId: newFilamentRowId.value,
    newFilamentRowGrams: newFilamentRowGrams.value,
    supplyRows: supplyRows.value,
    newSupplyId: newSupplyId.value,
    newSupplyQty: newSupplyQty.value,
  }),
  () => {
    if (restoringDraft) return;
    saveDraft();
  },
  { deep: true }
);

onMounted(() => {
  loadObservedUsers();
  restoreDraft();
  loadCatalog();
});
</script>

<template>
  <div>
    <div class="page-header">
      <p v-if="auth.isWatcher" class="page-subtitle">
        Calcula el costo real de un trabajo con los recursos de los usuarios que observas, guárdalo como venta o
        agrégalo a una cotización
      </p>
      <p v-else class="page-subtitle">Calcula el costo real de un trabajo, guárdalo como venta o agrégalo a una cotización</p>
    </div>

    <div v-if="loadingCatalog" class="empty-state">Cargando...</div>

    <div v-else class="grid calculator-grid">
      <div class="card">
        <div class="flex items-center justify-between mt-2" style="margin-bottom: 16px">
          <h3 style="margin: 0">Datos del trabajo</h3>
          <button type="button" class="btn btn-ghost btn-sm" @click="resetForm">Limpiar formulario</button>
        </div>
        <div class="flex flex-col gap-3">
          <div class="field">
            <label>Impresora</label>
            <select v-model="form.printer_id">
              <option value="" disabled>Selecciona una impresora</option>
              <option v-for="p in printers" :key="p.id" :value="p.id">{{ printerLabel(p) }}</option>
            </select>
          </div>

          <label class="flex items-center gap-2 text-sm" style="cursor: pointer; font-weight: 600">
            <input v-model="isMulticolor" type="checkbox" style="width: auto" />
            ¿Trabajo multicolor?
          </label>

          <div v-if="!isMulticolor" class="form-grid">
            <div class="field" style="grid-column: span 2">
              <label>Filamento (opcional)</label>
              <div class="flex items-center gap-2">
                <button
                  type="button"
                  class="btn btn-secondary"
                  style="flex: 1; justify-content: flex-start; overflow: hidden"
                  @click="openFilamentPicker('single')"
                >
                  <span v-if="singleFilamentId && filamentOwner(singleFilamentId)" class="owner-tag">de {{ filamentOwner(singleFilamentId) }}</span>
                  <span v-if="singleFilamentId" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap">{{ filamentSummary(singleFilamentId) }}</span>
                  <span v-else class="text-muted" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap">Sin filamento / no descontar stock</span>
                </button>
                <button
                  v-if="singleFilamentId"
                  type="button"
                  class="btn btn-icon btn-ghost btn-sm"
                  title="Quitar filamento"
                  @click="singleFilamentId = ''"
                >
                  <Icon name="close" :size="13" />
                </button>
              </div>
            </div>
            <div class="field" style="grid-column: span 2">
              <label>Gramos usados</label>
              <input v-model.number="singleGramsUsed" type="number" min="0" :max="GRAMS_MAX" step="0.01" />
            </div>
          </div>

          <div v-else class="field">
            <label>Filamentos usados</label>
            <div class="flex gap-2">
              <button
                type="button"
                class="btn btn-secondary"
                style="flex: 1; justify-content: flex-start; overflow: hidden"
                @click="openFilamentPicker('row')"
              >
                <span v-if="newFilamentRowId && filamentOwner(newFilamentRowId)" class="owner-tag">de {{ filamentOwner(newFilamentRowId) }}</span>
                <span v-if="newFilamentRowId" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap">{{ filamentSummary(newFilamentRowId) }}</span>
                <span v-else class="text-muted" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap">Selecciona un filamento</span>
              </button>
              <input v-model.number="newFilamentRowGrams" type="number" min="0.01" :max="GRAMS_MAX" step="0.01" placeholder="Gramos" style="width: 90px" />
              <button type="button" class="btn btn-secondary btn-sm" @click="addFilamentRow">Agregar</button>
            </div>
            <div v-if="!selectableFilaments.length" class="text-sm mt-1" style="color: var(--text-muted)">
              No hay filamentos con stock disponible. Los agotados (0g) no se pueden usar en un nuevo trabajo.
            </div>
            <div v-else-if="!availableFilamentOptions.length" class="text-sm mt-1" style="color: var(--text-muted)">
              Ya agregaste todos tus filamentos disponibles. Para cambiar la cantidad de uno, quítalo de la lista de abajo y vuelve a agregarlo.
            </div>
            <div v-if="filamentRowError" class="alert alert-danger mt-2">{{ filamentRowError }}</div>
            <div v-if="filamentRows.length" class="flex flex-col gap-2 mt-2">
              <div v-for="row in filamentRows" :key="row.id" class="flex items-center justify-between text-sm" style="background: var(--surface-alt); padding: 6px 10px; border-radius: 8px">
                <span class="flex items-center gap-2">
                  <span v-if="filamentOwner(row.filament_id)" class="owner-tag">de {{ filamentOwner(row.filament_id) }}</span>
                  <span>{{ filamentName(row.filament_id) }} — {{ row.grams_used }}g</span>
                </span>
                <button type="button" class="btn btn-icon btn-ghost btn-sm" @click="removeFilamentRow(row.id)">
                  <Icon name="close" :size="13" />
                </button>
              </div>
            </div>
            <span v-else class="field-hint">Agrega al menos un filamento para el trabajo multicolor.</span>
          </div>

          <div class="form-grid">
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

          <div class="field">
            <label>Consumibles usados</label>
            <div class="flex gap-2">
              <select v-model="newSupplyId" style="flex: 1">
                <option value="" disabled>Selecciona un insumo</option>
                <option v-for="s in supplies" :key="s.id" :value="s.id">{{ supplyLabel(s) }}</option>
              </select>
              <input v-model.number="newSupplyQty" type="number" min="0" step="1" placeholder="Cant." style="width: 70px" />
              <button type="button" class="btn btn-secondary btn-sm" @click="addSupplyRow">Agregar</button>
            </div>
            <div v-if="supplyRowError" class="alert alert-danger mt-2">{{ supplyRowError }}</div>
            <div v-if="supplyRows.length" class="flex flex-col gap-2 mt-2">
              <div v-for="row in supplyRows" :key="row.supply_id" class="flex items-center justify-between text-sm" style="background: var(--surface-alt); padding: 6px 10px; border-radius: 8px">
                <span class="flex items-center gap-2">
                  <span v-if="supplyOwner(row.supply_id)" class="owner-tag">de {{ supplyOwner(row.supply_id) }}</span>
                  <span>{{ supplyName(row.supply_id) }} × {{ row.quantity }}</span>
                </span>
                <button type="button" class="btn btn-icon btn-ghost btn-sm" @click="removeSupplyRow(row.supply_id)">
                  <Icon name="close" :size="13" />
                </button>
              </div>
            </div>
          </div>

          <div v-if="calcError" class="alert alert-danger">{{ calcError }}</div>

          <button class="btn btn-primary w-full mt-2" @click="handleCalculate" :disabled="calculating">
            {{ calculating ? "Calculando..." : "Calcular costos" }}
          </button>
        </div>
      </div>

      <div class="flex flex-col gap-4">
        <div v-if="saveSuccess" class="alert alert-info">{{ saveSuccess }}</div>

        <div v-if="!quote" class="card empty-state">
          <h3>Completa los datos y calcula</h3>
          <p>Verás aquí el desglose de costos y los escenarios de precio.</p>
        </div>

        <template v-else>
          <div class="card">
            <div class="card-header">
              <h3>Desglose de costos</h3>
              <span class="badge badge-info">Costo base: {{ formatCurrency(quote.breakdown.total_cost) }}</span>
            </div>
            <div v-if="resourceOwners.length" class="resource-owners">
              <span class="resource-owners-title">Recursos usados en esta cotización</span>
              <ul>
                <li v-for="(r, i) in resourceOwners" :key="i">
                  <span class="text-muted">{{ r.kind }}:</span> {{ r.label }}
                  <span class="owner-tag">de {{ r.owner }}</span>
                </li>
              </ul>
            </div>
            <div class="grid grid-cols-2" style="align-items: center">
              <DoughnutChart :labels="breakdownLabels" :values="breakdownValues" />
              <table style="min-width: unset">
                <tbody>
                  <tr class="breakdown-group"><td colspan="2">Con margen (90 / 140 / 190%)</td></tr>
                  <tr><td>Material</td><td class="text-right mono">{{ formatCurrency(quote.breakdown.material_cost) }}</td></tr>
                  <tr><td>Depreciación</td><td class="text-right mono">{{ formatCurrency(quote.breakdown.depreciation_cost) }}</td></tr>
                  <tr><td>Energía</td><td class="text-right mono">{{ formatCurrency(quote.breakdown.energy_cost) }}</td></tr>
                  <tr class="breakdown-group"><td colspan="2">Extras (se suman al final, sin margen)</td></tr>
                  <tr><td>Postprocesado</td><td class="text-right mono">{{ formatCurrency(quote.breakdown.postprocess_cost) }}</td></tr>
                  <tr><td>Consumibles</td><td class="text-right mono">{{ formatCurrency(quote.breakdown.supplies_cost) }}</td></tr>
                  <tr><td>Envío</td><td class="text-right mono">{{ formatCurrency(quote.breakdown.shipping_cost) }}</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="card">
            <div class="card-header">
              <h3>Escenarios de precio</h3>
              <label class="flex items-center gap-2 text-sm" style="cursor: pointer; font-weight: 600">
                <input v-model="useCustomPrice" type="checkbox" style="width: auto" />
                Definir yo el precio final
              </label>
            </div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Escenario</th>
                    <th>Margen</th>
                    <th class="text-right">Precio</th>
                    <th class="text-right">Ganancia</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="s in quote.scenarios" :key="s.margin_percent">
                    <td><strong>{{ s.label }}</strong></td>
                    <td><span class="badge badge-neutral">+{{ s.margin_percent }}%</span></td>
                    <td class="text-right mono"><strong>{{ formatCurrency(s.price) }}</strong></td>
                    <td class="text-right mono" style="color: var(--success)">{{ formatCurrency(s.profit) }}</td>
                    <td class="text-right">
                      <div class="flex flex-col gap-2" style="align-items: flex-end">
                        <button class="btn btn-primary btn-sm" style="width: 100%" @click="openSaveModal(s)">Guardar como venta</button>
                        <button class="btn btn-secondary btn-sm" style="width: 100%" @click="addToCart(s)">Agregar a cotización</button>
                      </div>
                    </td>
                  </tr>
                  <tr v-if="useCustomPrice" class="custom-price-row">
                    <td><strong>Precio manual</strong></td>
                    <td>
                      <span v-if="customScenario" class="badge badge-neutral">+{{ customScenario.margin_percent }}%</span>
                    </td>
                    <td class="text-right">
                      <input
                        v-model.number="customPrice"
                        type="number"
                        min="0"
                        step="1"
                        placeholder="Ej: 15000"
                        aria-label="Precio final"
                        style="width: 120px; text-align: right"
                      />
                    </td>
                    <td
                      class="text-right mono"
                      :style="{ color: customScenario && customScenario.profit < 0 ? 'var(--danger)' : 'var(--success)' }"
                    >
                      {{ customScenario ? formatCurrency(customScenario.profit) : "—" }}
                    </td>
                    <td class="text-right">
                      <div class="flex flex-col gap-2" style="align-items: flex-end">
                        <button class="btn btn-primary btn-sm" style="width: 100%" :disabled="!customScenario" @click="openSaveModal(customScenario)">Guardar como venta</button>
                        <button class="btn btn-secondary btn-sm" style="width: 100%" :disabled="!customScenario" @click="addToCart(customScenario)">Agregar a cotización</button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p v-if="useCustomPrice" class="field-hint mt-2">
              Escribe el precio que quieres cobrar, guiándote por los escenarios. Ese es el precio que se guarda
              en la venta y el que aparece en la cotización; la ganancia se calcula contra el costo total.
              <span v-if="customScenario && customScenario.profit < 0" style="color: var(--danger)">
                Ojo: con este precio vendes bajo el costo.
              </span>
            </p>
          </div>

          <div class="card">
            <div class="card-header">
              <h3>Cotización en construcción</h3>
              <span class="badge badge-neutral">{{ cartItems.length }} ítem(s)</span>
            </div>
            <div v-if="!cartItems.length" class="empty-state">
              <p>Agrega escenarios calculados arriba para ir armando una cotización con varios trabajos.</p>
            </div>
            <template v-else>
              <div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Producto</th>
                      <th class="text-right">Cantidad</th>
                      <th class="text-right">Precio unitario</th>
                      <th class="text-right">Subtotal</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in cartItems" :key="item.id">
                      <td><input v-model="item.description" placeholder="Nombre del producto" style="min-width: 220px" /></td>
                      <td class="text-right"><input v-model.number="item.quantity" type="number" min="0" step="1" style="width: 70px; text-align: right" /></td>
                      <td class="text-right"><input v-model.number="item.unit_price" type="number" min="0" step="1" style="width: 110px; text-align: right" /></td>
                      <td class="text-right mono">{{ formatCurrency(item.quantity * item.unit_price) }}</td>
                      <td class="text-right">
                        <button class="btn btn-icon btn-ghost" @click="removeFromCart(item.id)"><Icon name="trash" :size="15" /></button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="flex flex-col gap-1 mt-4" style="align-items: flex-end">
                <span style="font-weight: 700">Total: {{ formatCurrency(cartTotal) }}</span>
                <button class="btn btn-primary mt-2" @click="openQuoteForm">Generar cotización</button>
              </div>
            </template>
          </div>
        </template>
      </div>
    </div>

    <Modal persistent v-if="showSaveModal" title="Guardar cotización como venta" @close="showSaveModal = false">
      <form @submit.prevent="confirmSaveAsSale">
        <div class="alert alert-info mt-2" style="margin-bottom: 14px">
          <template v-if="selectedScenario.manual">Precio manual</template>
          <template v-else>{{ selectedScenario.label }} (+{{ selectedScenario.margin_percent }}%)</template>
          · Precio:
          <strong>{{ formatCurrency(selectedScenario.price) }}</strong>
        </div>
        <template v-if="auth.isWatcher">
          <div v-if="saleOwnerMismatch" class="alert alert-danger" style="margin-bottom: 14px">
            Esta cotización mezcla recursos de distintos usuarios. Para guardarla como venta, la impresora, los
            filamentos y los insumos deben ser del mismo usuario.
          </div>
          <div v-else class="alert alert-info" style="margin-bottom: 14px">
            Venta para <strong>{{ ownerName(saleOwnerId) }}</strong>: se descuenta de su inventario y quedará registrada
            como hecha por ti ({{ auth.user?.username }}).
          </div>
        </template>
        <div class="form-grid">
          <div class="field">
            <label>Fecha del pedido</label>
            <input v-model="saveForm.sale_date" type="date" required />
          </div>
          <div class="field">
            <label>Fecha de entrega comprometida</label>
            <input v-model="saveForm.promised_delivery_date" type="date" required />
          </div>
          <div class="field">
            <label>Método de pago</label>
            <select v-model="saveForm.payment_method">
              <option v-for="pm in PAYMENT_METHODS" :key="pm.value" :value="pm.value">{{ pm.label }}</option>
            </select>
          </div>
          <div class="field">
            <label>Trabajo</label>
            <input v-model="saveForm.client_name" required />
          </div>
          <div class="field">
            <label>Comprador (opcional)</label>
            <input v-model="saveForm.buyer_name" />
          </div>
        </div>
        <div class="field mt-2">
          <label class="flex items-center gap-2" style="cursor: pointer; font-weight: 600">
            <input v-model="useManualPrice" type="checkbox" style="width: auto" />
            Definir yo el precio final
          </label>
          <span class="field-hint">Para cobrar un número redondo o a tu criterio.</span>
          <input
            v-if="useManualPrice"
            v-model.number="manualPrice"
            type="number"
            min="0"
            step="1"
            placeholder="Ej: 15000"
            class="mt-2"
            style="max-width: 200px"
          />
          <div v-if="manualPriceBreakdown" class="alert alert-info mt-2">
            Precio: <strong>{{ formatCurrency(manualPriceBreakdown.price) }}</strong>
            · Ganancia:
            <span :style="{ color: manualPriceBreakdown.profit < 0 ? 'var(--danger)' : undefined }">
              {{ formatCurrency(manualPriceBreakdown.profit) }}
            </span>
          </div>
          <div v-else-if="useManualPrice" class="alert alert-danger mt-2">
            Ingresa un precio válido, mayor a 0.
          </div>
        </div>

        <div class="field mt-2">
          <label>Notas</label>
          <textarea v-model="saveForm.notes" rows="2" />
        </div>

        <div v-if="saveError" class="alert alert-danger mt-4">{{ saveError }}</div>

        <div class="form-actions">
          <button type="button" class="btn btn-secondary" @click="showSaveModal = false">Cancelar</button>
          <button type="submit" class="btn btn-primary" :disabled="saving || saleOwnerMismatch">
            {{ saving ? "Guardando..." : "Confirmar venta" }}
          </button>
        </div>
      </form>
    </Modal>

    <Modal persistent v-if="showQuoteFormModal" title="Generar cotización" width="620px" @close="showQuoteFormModal = false">
      <form @submit.prevent="confirmGenerateQuote">
        <div class="form-grid">
          <div class="field">
            <label>Cliente</label>
            <input v-model="quoteForm.client_name" required />
          </div>
          <div class="field">
            <label>Fecha</label>
            <input v-model="quoteForm.quote_date" type="date" required />
          </div>
        </div>

        <div class="alert alert-info mt-4">
          {{ cartItems.length }} ítem(s) · Total: <strong>{{ formatCurrency(cartTotal) }}</strong>
        </div>

        <div v-if="quoteFormError" class="alert alert-danger mt-4">{{ quoteFormError }}</div>

        <div class="form-actions">
          <button type="button" class="btn btn-secondary" @click="showQuoteFormModal = false">Cancelar</button>
          <button type="submit" class="btn btn-primary" :disabled="generatingQuote">
            {{ generatingQuote ? "Generando..." : "Generar cotización" }}
          </button>
        </div>
      </form>
    </Modal>

    <div v-if="showQuoteDocument" class="modal-backdrop" @click.self="showQuoteDocument = false">
      <div class="modal" style="max-width: 780px; padding: 0">
        <div class="modal-header no-print" style="padding: 18px 24px 0">
          <h3>Cotización generada</h3>
          <button class="btn btn-icon btn-ghost" @click="showQuoteDocument = false">✕</button>
        </div>
        <QuoteDocument
          v-if="generatedQuote"
          :quote="generatedQuote"
          :business-name="BUSINESS_NAME"
          :logo-data-url="BUSINESS_LOGO_URL"
        />
        <div class="form-actions no-print" style="padding: 0 24px 24px">
          <button class="btn btn-secondary" @click="showQuoteDocument = false">Cerrar</button>
          <button class="btn btn-primary" @click="printQuote">Imprimir / Descargar PDF</button>
        </div>
      </div>
    </div>

    <FilamentPickerModal
      v-if="showFilamentPicker"
      :filaments="filaments"
      :owner-names="namesById"
      :exclude-ids="filamentPickerTarget === 'row' ? filamentRows.map((r) => r.filament_id) : []"
      title="Seleccionar filamento"
      @select="onFilamentPicked"
      @close="showFilamentPicker = false"
    />
  </div>
</template>

<style scoped>
.calculator-grid {
  grid-template-columns: 460px 1fr;
}

.custom-price-row td {
  background: var(--primary-soft);
}

.breakdown-group td {
  padding-top: 10px;
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

/* Dueño de un recurso (solo lo ve el observador). */
.owner-tag {
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--primary-soft);
  color: var(--primary);
  font-size: 0.72rem;
  font-weight: 700;
  white-space: nowrap;
}

.resource-owners {
  margin-bottom: 16px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--surface-alt);
  font-size: 0.84rem;
}

.resource-owners-title {
  display: block;
  margin-bottom: 6px;
  font-size: 0.78rem;
  font-weight: 700;
  color: var(--text-muted);
}

.resource-owners ul {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* Below this width, a side-by-side 460px form + results column leaves the pricing
   table (7 columns, incl. two full-width action buttons) too narrow to avoid its own
   horizontal scroll -- stacking both to full width instead gives the table enough
   room to lay out without scrolling on typical laptop screens (~1366-1440px). */
@media (max-width: 1650px) {
  .calculator-grid {
    grid-template-columns: 1fr;
  }
}
</style>
