<script setup>
import { ref, reactive, onMounted, computed } from "vue";
import * as calculatorApi from "../api/calculator";
import * as printersApi from "../api/printers";
import * as inventoryApi from "../api/inventory";
import * as quotesApi from "../api/quotes";
import * as businessProfileApi from "../api/businessProfile";
import { PAYMENT_METHODS } from "../api/sales";
import { formatCurrency, todayISO } from "../utils/format";
import Modal from "../components/Modal.vue";
import Icon from "../components/Icon.vue";
import DoughnutChart from "../components/DoughnutChart.vue";
import QuoteDocument from "../components/QuoteDocument.vue";

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

function addFilamentRow() {
  if (!newFilamentRowId.value || !newFilamentRowGrams.value) return;
  filamentRows.value.push({
    id: crypto.randomUUID(),
    filament_id: newFilamentRowId.value,
    grams_used: Number(newFilamentRowGrams.value),
  });
  newFilamentRowId.value = "";
  newFilamentRowGrams.value = null;
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
const newSupplyQty = ref(1);

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

async function handleCalculate() {
  if (!form.printer_id) {
    calcError.value = "Selecciona una impresora";
    return;
  }
  calculating.value = true;
  calcError.value = "";
  try {
    quote.value = await calculatorApi.computeQuote(buildQuotePayload());
  } catch (err) {
    calcError.value = err.response?.data?.detail || "No se pudo calcular la cotización";
  } finally {
    calculating.value = false;
  }
}

/* -------- Save as sale (only for single/no filament jobs) -------- */
const showSaveModal = ref(false);
const selectedScenario = ref(null);
const saveForm = reactive({ sale_date: todayISO(), client_name: "", buyer_name: "", payment_method: "efectivo", notes: "" });
const saving = ref(false);
const saveError = ref("");
const saveSuccess = ref("");

function openSaveModal(scenario) {
  selectedScenario.value = scenario;
  saveError.value = "";
  saveSuccess.value = "";
  showSaveModal.value = true;
}

async function confirmSaveAsSale() {
  saving.value = true;
  saveError.value = "";
  try {
    await calculatorApi.saveQuoteAsSale({
      ...buildQuotePayload(),
      sale_date: saveForm.sale_date,
      client_name: saveForm.client_name,
      buyer_name: saveForm.buyer_name || null,
      payment_method: saveForm.payment_method,
      notes: saveForm.notes || null,
      chosen_margin_percent: selectedScenario.value.margin_percent,
    });
    showSaveModal.value = false;
    saveSuccess.value = "Venta guardada correctamente en el Registro de Ventas.";
    await loadCatalog();
  } catch (err) {
    saveError.value = err.response?.data?.detail || "No se pudo guardar la venta";
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
    unit_price: Number(scenario.base_price),
  });
}

function removeFromCart(id) {
  cartItems.value = cartItems.value.filter((i) => i.id !== id);
}

const cartSubtotal = computed(() =>
  cartItems.value.reduce((sum, i) => sum + (Number(i.quantity) || 0) * (Number(i.unit_price) || 0), 0)
);
const cartIvaAmount = computed(() => cartSubtotal.value * 0.19);
const cartTotal = computed(() => cartSubtotal.value + cartIvaAmount.value);

/* -------- Generate quote (Cotización) -------- */
const showQuoteFormModal = ref(false);
const quoteForm = reactive({ client_name: "", quote_date: todayISO() });
const businessForm = reactive({ business_name: "", logo_data_url: "" });
const generatingQuote = ref(false);
const quoteFormError = ref("");
const generatedQuote = ref(null);
const showQuoteDocument = ref(false);
const LOGO_MAX_BYTES = 500_000;

function openQuoteForm() {
  quoteFormError.value = "";
  showQuoteFormModal.value = true;
}

function handleLogoUpload(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (file.size > LOGO_MAX_BYTES) {
    quoteFormError.value = "El logo es muy pesado (máximo ~500KB). Prueba con una imagen más liviana.";
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    businessForm.logo_data_url = reader.result;
  };
  reader.readAsDataURL(file);
}

function removeLogo() {
  businessForm.logo_data_url = "";
}

async function confirmGenerateQuote() {
  if (cartItems.value.some((i) => !i.description.trim())) {
    quoteFormError.value = "Todos los productos de la cotización necesitan un nombre — revisa la lista de arriba.";
    return;
  }
  generatingQuote.value = true;
  quoteFormError.value = "";
  try {
    await businessProfileApi.updateBusinessProfile({
      business_name: businessForm.business_name || null,
      logo_data_url: businessForm.logo_data_url || null,
    });
    const created = await quotesApi.createQuote({
      client_name: quoteForm.client_name,
      quote_date: quoteForm.quote_date,
      items: cartItems.value.map((i) => ({
        description: i.description,
        quantity: i.quantity,
        unit_price: i.unit_price,
      })),
    });
    generatedQuote.value = created;
    showQuoteFormModal.value = false;
    showQuoteDocument.value = true;
    cartItems.value = [];
  } catch (err) {
    quoteFormError.value = err.response?.data?.detail || "No se pudo generar la cotización";
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
    const [p, f, s, profile] = await Promise.all([
      printersApi.listPrinters(),
      inventoryApi.listFilaments(),
      inventoryApi.listSupplies(),
      businessProfileApi.getBusinessProfile(),
    ]);
    printers.value = p;
    filaments.value = f;
    supplies.value = s;
    businessForm.business_name = profile.business_name || "";
    businessForm.logo_data_url = profile.logo_data_url || "";
  } finally {
    loadingCatalog.value = false;
  }
}

onMounted(loadCatalog);
</script>

<template>
  <div>
    <div class="page-header">
      <p class="page-subtitle">Calcula el costo real de un trabajo, guárdalo como venta o agrégalo a una cotización</p>
    </div>

    <div v-if="loadingCatalog" class="empty-state">Cargando...</div>

    <div v-else class="grid" style="grid-template-columns: 380px 1fr">
      <div class="card">
        <h3 class="mt-2" style="margin-bottom: 16px">Datos del trabajo</h3>
        <div class="flex flex-col gap-3">
          <div class="field">
            <label>Impresora</label>
            <select v-model="form.printer_id">
              <option value="" disabled>Selecciona una impresora</option>
              <option v-for="p in printers" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </div>

          <label class="flex items-center gap-2 text-sm" style="cursor: pointer; font-weight: 600">
            <input v-model="isMulticolor" type="checkbox" style="width: auto" />
            ¿Trabajo multicolor?
          </label>

          <div v-if="!isMulticolor" class="form-grid">
            <div class="field" style="grid-column: span 2">
              <label>Filamento (opcional)</label>
              <select v-model="singleFilamentId">
                <option value="">Sin filamento / no descontar stock</option>
                <option v-for="f in filaments" :key="f.id" :value="f.id">{{ filamentLabel(f) }} ({{ f.available_g }}g disp.)</option>
              </select>
            </div>
            <div class="field" style="grid-column: span 2">
              <label>Gramos usados</label>
              <input v-model.number="singleGramsUsed" type="number" min="0" step="0.01" />
            </div>
          </div>

          <div v-else class="field">
            <label>Filamentos usados</label>
            <div class="flex gap-2">
              <select v-model="newFilamentRowId" style="flex: 1">
                <option value="" disabled>Selecciona un filamento</option>
                <option v-for="f in filaments" :key="f.id" :value="f.id">{{ filamentLabel(f) }}</option>
              </select>
              <input v-model.number="newFilamentRowGrams" type="number" min="0.01" step="0.01" placeholder="Gramos" style="width: 90px" />
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
            <div class="grid grid-cols-2" style="align-items: center">
              <DoughnutChart :labels="breakdownLabels" :values="breakdownValues" />
              <table style="min-width: unset">
                <tbody>
                  <tr><td>Material</td><td class="text-right mono">{{ formatCurrency(quote.breakdown.material_cost) }}</td></tr>
                  <tr><td>Depreciación</td><td class="text-right mono">{{ formatCurrency(quote.breakdown.depreciation_cost) }}</td></tr>
                  <tr><td>Energía</td><td class="text-right mono">{{ formatCurrency(quote.breakdown.energy_cost) }}</td></tr>
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
            </div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Escenario</th>
                    <th>Margen</th>
                    <th class="text-right">Precio sin IVA</th>
                    <th class="text-right">IVA</th>
                    <th class="text-right">Precio con IVA</th>
                    <th class="text-right">Ganancia</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="s in quote.scenarios" :key="s.margin_percent">
                    <td><strong>{{ s.label }}</strong></td>
                    <td><span class="badge badge-neutral">+{{ s.margin_percent }}%</span></td>
                    <td class="text-right mono">{{ formatCurrency(s.base_price) }}</td>
                    <td class="text-right mono">{{ formatCurrency(s.iva_amount) }}</td>
                    <td class="text-right mono"><strong>{{ formatCurrency(s.total_price) }}</strong></td>
                    <td class="text-right mono" style="color: var(--success)">{{ formatCurrency(s.profit) }}</td>
                    <td class="text-right">
                      <div class="flex gap-2" style="justify-content: flex-end">
                        <button class="btn btn-primary btn-sm" @click="openSaveModal(s)">Guardar como venta</button>
                        <button class="btn btn-secondary btn-sm" @click="addToCart(s)">Agregar a cotización</button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
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
                      <td class="text-right"><input v-model.number="item.quantity" type="number" min="0.01" step="1" style="width: 70px; text-align: right" /></td>
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
                <span class="text-sm text-muted">Subtotal: {{ formatCurrency(cartSubtotal) }}</span>
                <span class="text-sm text-muted">IVA (19%): {{ formatCurrency(cartIvaAmount) }}</span>
                <span style="font-weight: 700">Total: {{ formatCurrency(cartTotal) }}</span>
                <button class="btn btn-primary mt-2" @click="openQuoteForm">Generar cotización</button>
              </div>
            </template>
          </div>
        </template>
      </div>
    </div>

    <Modal v-if="showSaveModal" title="Guardar cotización como venta" @close="showSaveModal = false">
      <form @submit.prevent="confirmSaveAsSale">
        <div class="alert alert-info mt-2" style="margin-bottom: 14px">
          {{ selectedScenario.label }} (+{{ selectedScenario.margin_percent }}%) · Total con IVA:
          <strong>{{ formatCurrency(selectedScenario.total_price) }}</strong>
        </div>
        <div class="form-grid">
          <div class="field">
            <label>Fecha</label>
            <input v-model="saveForm.sale_date" type="date" required />
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
          <label>Notas</label>
          <textarea v-model="saveForm.notes" rows="2" />
        </div>

        <div v-if="saveError" class="alert alert-danger mt-4">{{ saveError }}</div>

        <div class="form-actions">
          <button type="button" class="btn btn-secondary" @click="showSaveModal = false">Cancelar</button>
          <button type="submit" class="btn btn-primary" :disabled="saving">
            {{ saving ? "Guardando..." : "Confirmar venta" }}
          </button>
        </div>
      </form>
    </Modal>

    <Modal v-if="showQuoteFormModal" title="Generar cotización" width="620px" @close="showQuoteFormModal = false">
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

        <h3 class="mt-4" style="font-size: 0.95rem; margin-bottom: 10px">Datos del negocio (para el documento)</h3>
        <div class="form-grid">
          <div class="field">
            <label>Nombre del negocio</label>
            <input v-model="businessForm.business_name" placeholder="Ej: Zola 3D Prints" />
          </div>
          <div class="field">
            <label>Logo</label>
            <input type="file" accept="image/*" @change="handleLogoUpload" />
          </div>
        </div>
        <div v-if="businessForm.logo_data_url" class="flex items-center gap-3 mt-2">
          <img :src="businessForm.logo_data_url" alt="Logo" style="width: 48px; height: 48px; object-fit: contain; border-radius: 8px; border: 1px solid var(--border)" />
          <button type="button" class="btn btn-ghost btn-sm" @click="removeLogo">Quitar logo</button>
        </div>

        <div class="alert alert-info mt-4">
          {{ cartItems.length }} ítem(s) · Total con IVA: <strong>{{ formatCurrency(cartTotal) }}</strong>
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
          :business-name="businessForm.business_name"
          :logo-data-url="businessForm.logo_data_url"
        />
        <div class="form-actions no-print" style="padding: 0 24px 24px">
          <button class="btn btn-secondary" @click="showQuoteDocument = false">Cerrar</button>
          <button class="btn btn-primary" @click="printQuote">Imprimir / Descargar PDF</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
@media (max-width: 1000px) {
  .grid[style*="380px"] {
    grid-template-columns: 1fr !important;
  }
}
</style>
