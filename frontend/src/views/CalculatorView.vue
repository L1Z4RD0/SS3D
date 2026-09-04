<script setup>
import { ref, reactive, onMounted, computed } from "vue";
import * as calculatorApi from "../api/calculator";
import * as printersApi from "../api/printers";
import * as inventoryApi from "../api/inventory";
import { PAYMENT_METHODS } from "../api/sales";
import { formatCurrency, formatPercent, todayISO } from "../utils/format";
import Modal from "../components/Modal.vue";
import Icon from "../components/Icon.vue";
import DoughnutChart from "../components/DoughnutChart.vue";

const printers = ref([]);
const filaments = ref([]);
const supplies = ref([]);
const settings = ref(null);
const loadingCatalog = ref(true);

const form = reactive({
  printer_id: "",
  filament_id: "",
  grams_used: null,
  print_hours: null,
  postprocess_hours: 0,
  shipping_cost: 0,
});

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
    filament_id: form.filament_id || null,
    grams_used: Number(form.grams_used) || 0,
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

/* -------- Save as sale -------- */
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

/* -------- Settings -------- */
const showSettingsModal = ref(false);
const settingsForm = reactive({ electricity_rate: 0, labor_rate_per_hour: 0, iva_percent: 19, margin_scenarios: "", default_packaging_cost: null });
const settingsSaving = ref(false);
const settingsError = ref("");

function openSettings() {
  Object.assign(settingsForm, {
    electricity_rate: Number(settings.value.electricity_rate),
    labor_rate_per_hour: Number(settings.value.labor_rate_per_hour),
    iva_percent: Number(settings.value.iva_percent),
    margin_scenarios: settings.value.margin_scenarios.join(", "),
    default_packaging_cost: settings.value.default_packaging_cost !== null ? Number(settings.value.default_packaging_cost) : null,
  });
  settingsError.value = "";
  showSettingsModal.value = true;
}

async function submitSettings() {
  settingsSaving.value = true;
  settingsError.value = "";
  try {
    const scenarios = settingsForm.margin_scenarios
      .split(",")
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => !Number.isNaN(n));
    settings.value = await calculatorApi.updateSettings({
      electricity_rate: settingsForm.electricity_rate,
      labor_rate_per_hour: settingsForm.labor_rate_per_hour,
      iva_percent: settingsForm.iva_percent,
      margin_scenarios: scenarios,
      default_packaging_cost: settingsForm.default_packaging_cost,
    });
    showSettingsModal.value = false;
  } catch (err) {
    settingsError.value = err.response?.data?.detail || "No se pudo guardar la configuración";
  } finally {
    settingsSaving.value = false;
  }
}

async function loadCatalog() {
  loadingCatalog.value = true;
  try {
    const [p, f, s, cfg] = await Promise.all([
      printersApi.listPrinters(),
      inventoryApi.listFilaments(),
      inventoryApi.listSupplies(),
      calculatorApi.getSettings(),
    ]);
    printers.value = p;
    filaments.value = f;
    supplies.value = s;
    settings.value = cfg;
  } finally {
    loadingCatalog.value = false;
  }
}

onMounted(loadCatalog);
</script>

<template>
  <div>
    <div class="page-header">
      <p class="page-subtitle">Calcula el costo real de un trabajo y guárdalo directamente como venta</p>
      <button class="btn btn-secondary" @click="openSettings" :disabled="!settings">Configuración</button>
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
          <div class="field">
            <label>Filamento (opcional)</label>
            <select v-model="form.filament_id">
              <option value="">Sin filamento / no descontar stock</option>
              <option v-for="f in filaments" :key="f.id" :value="f.id">{{ f.brand }} · {{ f.color }} ({{ f.available_g }}g disp.)</option>
            </select>
          </div>
          <div class="form-grid">
            <div class="field">
              <label>Gramos usados</label>
              <input v-model.number="form.grams_used" type="number" min="0" step="1" />
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
                    <td><span class="badge badge-neutral">+{{ s.margin_percent }}%</span></td>
                    <td class="text-right mono">{{ formatCurrency(s.base_price) }}</td>
                    <td class="text-right mono">{{ formatCurrency(s.iva_amount) }}</td>
                    <td class="text-right mono"><strong>{{ formatCurrency(s.total_price) }}</strong></td>
                    <td class="text-right mono" style="color: var(--success)">{{ formatCurrency(s.profit) }}</td>
                    <td class="text-right">
                      <button class="btn btn-primary btn-sm" @click="openSaveModal(s)">Guardar como venta</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>
      </div>
    </div>

    <Modal v-if="showSaveModal" title="Guardar cotización como venta" @close="showSaveModal = false">
      <form @submit.prevent="confirmSaveAsSale">
        <div class="alert alert-info mt-2" style="margin-bottom: 14px">
          Margen elegido: +{{ selectedScenario.margin_percent }}% · Total con IVA:
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
            <label>Cliente / trabajo</label>
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

    <Modal v-if="showSettingsModal" title="Configuración de la calculadora" @close="showSettingsModal = false">
      <form @submit.prevent="submitSettings">
        <div class="form-grid">
          <div class="field">
            <label>Tarifa eléctrica ($/kWh)</label>
            <input v-model.number="settingsForm.electricity_rate" type="number" min="0" step="0.01" required />
          </div>
          <div class="field">
            <label>Valor hora mano de obra (CLP)</label>
            <input v-model.number="settingsForm.labor_rate_per_hour" type="number" min="0" step="1" required />
          </div>
          <div class="field">
            <label>IVA (%)</label>
            <input v-model.number="settingsForm.iva_percent" type="number" min="0" max="100" step="0.01" required />
          </div>
          <div class="field">
            <label>Embalaje por defecto (CLP)</label>
            <input v-model.number="settingsForm.default_packaging_cost" type="number" min="0" step="1" />
          </div>
        </div>
        <div class="field mt-2">
          <label>Escenarios de margen (%), separados por coma</label>
          <input v-model="settingsForm.margin_scenarios" placeholder="60, 80, 100, 120, 140, 160, 180, 200" />
        </div>

        <div v-if="settingsError" class="alert alert-danger mt-4">{{ settingsError }}</div>

        <div class="form-actions">
          <button type="button" class="btn btn-secondary" @click="showSettingsModal = false">Cancelar</button>
          <button type="submit" class="btn btn-primary" :disabled="settingsSaving">
            {{ settingsSaving ? "Guardando..." : "Guardar" }}
          </button>
        </div>
      </form>
    </Modal>
  </div>
</template>

<style scoped>
@media (max-width: 1000px) {
  .grid[style*="380px"] {
    grid-template-columns: 1fr !important;
  }
}
</style>
