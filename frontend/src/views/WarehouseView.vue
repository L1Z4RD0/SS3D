<script setup>
import { ref, reactive, computed, onMounted, watch } from "vue";
import * as warehouseApi from "../api/warehouse";
import { PIECE_STATUS_LABELS, DISCARD_REASON_LABELS } from "../api/warehouse";
import { PAYMENT_METHODS, GIFT_PAYMENT_METHOD } from "../api/sales";
import { formatCurrency, formatDate, todayISO } from "../utils/format";
import { extractApiError, isValidNumber } from "../utils/validation";
import { useAuthStore } from "../stores/auth";
import { useObservedUsers } from "../composables/useObservedUsers";
import Modal from "../components/Modal.vue";
import OrderStatusModal from "../components/OrderStatusModal.vue";

/* Almacén: piezas de pedidos cancelados que siguen en nuestro poder. Se pueden vender
   (crea un pedido que nace Lista, sin descontar material), editar y descartar (el costo
   pasa a pérdida). El observador las ve por dueño y solo puede venderlas. */
const auth = useAuthStore();
const { observedUsers, loadObservedUsers } = useObservedUsers();

const FILTERS = [
  { key: "en_almacen,reservada", label: "Disponibles" },
  { key: "vendida", label: "Vendidas" },
  { key: "descartada", label: "Descartadas" },
  { key: "todos", label: "Todas" },
];
const filter = ref(FILTERS[0].key);
const ownerId = ref(null); // observador: dueño seleccionado
const pieces = ref([]);
const loading = ref(true);
const error = ref("");
const openSaleId = ref(null);

const available = computed(() => pieces.value.filter((p) => p.status === "en_almacen" || p.status === "reservada"));
const totals = computed(() => ({
  count: available.value.length,
  cost: available.value.reduce((s, p) => s + Number(p.cost), 0),
  price: available.value.reduce((s, p) => s + Number(p.price), 0),
}));

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const params = { status: filter.value };
    if (auth.isWatcher && ownerId.value) params.owner_id = ownerId.value;
    pieces.value = await warehouseApi.listPieces(params);
  } catch (err) {
    error.value = extractApiError(err, "No se pudo cargar el Almacén.");
  } finally {
    loading.value = false;
  }
}

watch([filter, ownerId], load);
onMounted(async () => {
  if (auth.isWatcher) {
    await loadObservedUsers();
    ownerId.value = observedUsers.value[0]?.id ?? null; // el watch de arriba carga las piezas
    if (!ownerId.value) {
      pieces.value = [];
      loading.value = false;
    }
    return;
  }
  await load();
});

const belowCost = (p, price = p.price) => Number(price) < Number(p.cost);

/* -------- Vender -------- */
const sellTarget = ref(null);
const sellForm = reactive({});
const sellBusy = ref(false);
const sellError = ref("");

function openSell(p) {
  sellTarget.value = p;
  Object.assign(sellForm, {
    client_name: p.name,
    buyer_name: "",
    promised_delivery_date: todayISO(),
    payment_method: "efectivo",
    price: Number(p.price),
    notes: "",
  });
  sellError.value = "";
}

const sellIsGift = computed(() => sellForm.payment_method === GIFT_PAYMENT_METHOD);
const sellPrice = computed(() => (sellIsGift.value ? 0 : Number(sellForm.price)));
const sellProfit = computed(() => (sellTarget.value ? sellPrice.value - Number(sellTarget.value.cost) : 0));

async function confirmSell() {
  if (!sellIsGift.value && !isValidNumber(sellForm.price, { min: 0 })) {
    sellError.value = "Ingresa un precio válido.";
    return;
  }
  sellBusy.value = true;
  sellError.value = "";
  try {
    await warehouseApi.sellPiece(sellTarget.value.id, {
      client_name: sellForm.client_name,
      buyer_name: sellForm.buyer_name || null,
      promised_delivery_date: sellForm.promised_delivery_date,
      payment_method: sellForm.payment_method,
      price: sellPrice.value,
      notes: sellForm.notes || null,
      sale_date: todayISO(),
    });
    sellTarget.value = null;
    await load();
  } catch (err) {
    sellError.value = extractApiError(err, "No se pudo registrar la venta.");
  } finally {
    sellBusy.value = false;
  }
}

/* -------- Editar -------- */
const editTarget = ref(null);
const editForm = reactive({ name: "", price: 0, notes: "" });
const editBusy = ref(false);
const editError = ref("");

function openEdit(p) {
  editTarget.value = p;
  Object.assign(editForm, { name: p.name, price: Number(p.price), notes: p.notes || "" });
  editError.value = "";
}

async function confirmEdit() {
  if (!editForm.name.trim() || !isValidNumber(editForm.price, { min: 0 })) {
    editError.value = "Completa un nombre y un precio válido.";
    return;
  }
  editBusy.value = true;
  editError.value = "";
  try {
    await warehouseApi.updatePiece(editTarget.value.id, {
      name: editForm.name.trim(),
      price: Number(editForm.price),
      notes: editForm.notes,
    });
    editTarget.value = null;
    await load();
  } catch (err) {
    editError.value = extractApiError(err, "No se pudo guardar la pieza.");
  } finally {
    editBusy.value = false;
  }
}

/* -------- Descartar -------- */
const discardTarget = ref(null);
const discardForm = reactive({ reason: "", note: "" });
const discardBusy = ref(false);
const discardError = ref("");

function openDiscard(p) {
  discardTarget.value = p;
  Object.assign(discardForm, { reason: "", note: "" });
  discardError.value = "";
}

async function confirmDiscard() {
  if (!discardForm.reason) {
    discardError.value = "Elige el motivo.";
    return;
  }
  discardBusy.value = true;
  discardError.value = "";
  try {
    await warehouseApi.discardPiece(discardTarget.value.id, {
      reason: discardForm.reason,
      note: discardForm.note.trim() || null,
    });
    discardTarget.value = null;
    await load();
  } catch (err) {
    discardError.value = extractApiError(err, "No se pudo descartar la pieza.");
  } finally {
    discardBusy.value = false;
  }
}

const ownerLabel = computed(() => observedUsers.value.find((u) => u.id === ownerId.value)?.username || "");
</script>

<template>
  <div>
    <div class="page-header">
      <p class="page-subtitle">
        Piezas de pedidos cancelados que siguen en nuestro poder. Se pueden vender (sin volver a descontar material),
        editar o descartar.
      </p>
    </div>

    <!-- Observador: un dueño a la vez, como en Inventario -->
    <div v-if="auth.isWatcher" class="card owner-picker">
      <span v-if="!observedUsers.length" class="text-muted text-sm">
        Todavía no tienes usuarios asignados. Pídele al administrador que te asigne a quién observar.
      </span>
      <template v-else>
        <span class="owner-picker-label">Almacén de</span>
        <button
          v-for="u in observedUsers"
          :key="u.id"
          type="button"
          class="owner-chip"
          :class="{ selected: ownerId === u.id }"
          :aria-pressed="ownerId === u.id"
          @click="ownerId = u.id"
        >
          {{ u.username }}
        </button>
      </template>
    </div>

    <div class="warehouse-summary">
      <div class="summary-item">
        <span class="summary-label">Piezas disponibles</span>
        <strong>{{ totals.count }}</strong>
      </div>
      <div class="summary-item">
        <span class="summary-label">Valor en Almacén (costo)</span>
        <strong>{{ formatCurrency(totals.cost) }}</strong>
      </div>
      <div class="summary-item">
        <span class="summary-label">Precio de venta total</span>
        <strong>{{ formatCurrency(totals.price) }}</strong>
      </div>
    </div>
    <p v-if="filter !== FILTERS[0].key" class="field-hint" style="margin: -8px 0 12px">
      Los totales cuentan solo las piezas disponibles de la vista actual.
    </p>

    <div class="card">
      <div class="card-header">
        <div class="seg" role="tablist" aria-label="Filtrar piezas">
          <button
            v-for="f in FILTERS"
            :key="f.key"
            type="button"
            role="tab"
            :aria-selected="filter === f.key"
            :class="{ active: filter === f.key }"
            @click="filter = f.key"
          >
            {{ f.label }}
          </button>
        </div>
      </div>

      <div v-if="error" class="alert alert-danger">{{ error }}</div>
      <div v-else-if="loading" class="empty-state">Cargando...</div>
      <div v-else-if="!pieces.length" class="empty-state">
        <h3>Sin piezas</h3>
        <p>Las piezas llegan aquí al cancelar un pedido En producción o Lista y elegir guardarlas en el Almacén.</p>
      </div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Pieza</th>
              <th>Origen</th>
              <th>Ingreso</th>
              <th class="text-right">Costo</th>
              <th class="text-right">Precio</th>
              <th>Estado</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in pieces" :key="p.id">
              <td>
                <strong>{{ p.name }}</strong>
                <div v-if="p.notes" class="text-muted text-sm notes">{{ p.notes }}</div>
                <div v-if="auth.isWatcher" class="text-muted text-sm">de {{ p.owner_username }}</div>
              </td>
              <td class="text-sm">
                Pedido cancelado «{{ p.origin_client_name }}»
                <div v-if="p.origin_cancelled_at" class="text-muted">{{ formatDate(p.origin_cancelled_at) }}</div>
              </td>
              <td>{{ formatDate(p.entry_date) }}</td>
              <td class="text-right mono">{{ formatCurrency(p.cost) }}</td>
              <td class="text-right mono" :class="{ 'below-cost': belowCost(p) }" :title="belowCost(p) ? 'Precio bajo el costo' : ''">
                {{ formatCurrency(p.price) }}
              </td>
              <td>
                <span class="badge" :class="`piece-${p.status}`">{{ PIECE_STATUS_LABELS[p.status] }}</span>
                <div v-if="p.discard_reason" class="text-muted text-sm">{{ DISCARD_REASON_LABELS[p.discard_reason] }}</div>
              </td>
              <td class="text-right">
                <div class="row-actions">
                  <button v-if="p.status === 'en_almacen'" type="button" class="btn btn-primary btn-sm" @click="openSell(p)">
                    Vender
                  </button>
                  <button v-if="p.active_sale_id" type="button" class="btn btn-secondary btn-sm" @click="openSaleId = p.active_sale_id">
                    Ver pedido
                  </button>
                  <template v-if="p.can_manage">
                    <button
                      v-if="p.status === 'en_almacen' || p.status === 'reservada'"
                      type="button"
                      class="btn btn-ghost btn-sm"
                      @click="openEdit(p)"
                    >
                      Editar
                    </button>
                    <button v-if="p.status === 'en_almacen'" type="button" class="btn btn-ghost btn-sm danger-text" @click="openDiscard(p)">
                      Descartar
                    </button>
                  </template>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Vender -->
    <Modal persistent v-if="sellTarget" title="Vender pieza del Almacén" :subtitle="sellTarget.name" width="560px" @close="sellTarget = null">
      <form @submit.prevent="confirmSell">
        <div class="alert alert-info piece-info">
          Se crea un pedido en estado <strong>Lista</strong>. No descuenta material ni suma horas (ya se usaron en el
          pedido original); su costo es el de la pieza: <strong>{{ formatCurrency(sellTarget.cost) }}</strong>.
          <template v-if="auth.isWatcher"> Venta para <strong>{{ sellTarget.owner_username }}</strong>, registrada por ti.</template>
        </div>
        <div class="form-grid">
          <div class="field">
            <label>Trabajo</label>
            <input v-model="sellForm.client_name" required maxlength="160" />
          </div>
          <div class="field">
            <label>Comprador (opcional)</label>
            <input v-model="sellForm.buyer_name" maxlength="160" />
          </div>
          <div class="field">
            <label>Fecha de entrega comprometida</label>
            <input v-model="sellForm.promised_delivery_date" type="date" required />
          </div>
          <div class="field">
            <label>Método de pago</label>
            <select v-model="sellForm.payment_method">
              <option v-for="pm in PAYMENT_METHODS" :key="pm.value" :value="pm.value">{{ pm.label }}</option>
            </select>
          </div>
          <div v-if="sellIsGift" class="field">
            <label>Precio</label>
            <div class="alert alert-info" style="margin: 0">
              <strong>🎁 Regalo:</strong> precio $0. El costo de la pieza ({{ formatCurrency(sellTarget.cost) }}) queda como
              pérdida.
            </div>
          </div>
          <div v-else class="field">
            <label>Precio</label>
            <input v-model.number="sellForm.price" type="number" min="0" step="1" required :class="{ 'input-below-cost': belowCost(sellTarget, sellForm.price) }" />
            <span class="field-hint" :class="{ 'below-cost': sellProfit < 0 }">
              Ganancia: {{ formatCurrency(sellProfit) }}
            </span>
          </div>
          <div class="field">
            <label>Notas</label>
            <input v-model="sellForm.notes" />
          </div>
        </div>
        <div v-if="sellError" class="alert alert-danger mt-2">{{ sellError }}</div>
        <div class="form-actions">
          <button type="button" class="btn btn-secondary" @click="sellTarget = null">Cancelar</button>
          <button type="submit" class="btn btn-primary" :disabled="sellBusy">{{ sellBusy ? "Registrando..." : "Registrar venta" }}</button>
        </div>
      </form>
    </Modal>

    <!-- Editar -->
    <Modal persistent v-if="editTarget" title="Editar pieza" :subtitle="`Costo ${formatCurrency(editTarget.cost)}`" width="480px" @close="editTarget = null">
      <form @submit.prevent="confirmEdit">
        <div class="field">
          <label>Nombre</label>
          <input v-model="editForm.name" required maxlength="160" />
        </div>
        <div class="field mt-2">
          <label>Precio de venta</label>
          <input v-model.number="editForm.price" type="number" min="0" step="1" required :class="{ 'input-below-cost': belowCost(editTarget, editForm.price) }" />
          <span v-if="belowCost(editTarget, editForm.price)" class="field-hint below-cost">
            El precio está bajo el costo de la pieza ({{ formatCurrency(editTarget.cost) }}).
          </span>
        </div>
        <div class="field mt-2">
          <label>Notas</label>
          <textarea v-model="editForm.notes" rows="2" maxlength="1000" />
        </div>
        <div v-if="editError" class="alert alert-danger mt-2">{{ editError }}</div>
        <div class="form-actions">
          <button type="button" class="btn btn-secondary" @click="editTarget = null">Cancelar</button>
          <button type="submit" class="btn btn-primary" :disabled="editBusy">{{ editBusy ? "Guardando..." : "Guardar" }}</button>
        </div>
      </form>
    </Modal>

    <!-- Descartar -->
    <Modal persistent v-if="discardTarget" title="Descartar pieza" :subtitle="discardTarget.name" width="480px" @close="discardTarget = null">
      <form @submit.prevent="confirmDiscard">
        <div class="alert alert-warning piece-info">
          La pieza sale del Almacén y su costo, <strong>{{ formatCurrency(discardTarget.cost) }}</strong>, pasa a contar
          como <strong>pérdida</strong>. No se puede deshacer.
        </div>
        <div class="field">
          <label>Motivo</label>
          <select v-model="discardForm.reason" required>
            <option value="" disabled>Elige un motivo</option>
            <option v-for="(label, key) in DISCARD_REASON_LABELS" :key="key" :value="key">{{ label }}</option>
          </select>
        </div>
        <div class="field mt-2">
          <label>Detalle (opcional)</label>
          <input v-model="discardForm.note" maxlength="500" placeholder="Ej: se regaló a un cliente frecuente" />
        </div>
        <div v-if="discardError" class="alert alert-danger mt-2">{{ discardError }}</div>
        <div class="form-actions">
          <button type="button" class="btn btn-secondary" @click="discardTarget = null">Volver</button>
          <button type="submit" class="btn btn-danger" :disabled="discardBusy || !discardForm.reason">
            {{ discardBusy ? "Descartando..." : "Descartar pieza" }}
          </button>
        </div>
      </form>
    </Modal>

    <OrderStatusModal v-if="openSaleId" :sale-id="openSaleId" @close="openSaleId = null" @changed="load" />
  </div>
</template>

<style scoped>
.owner-picker {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.owner-picker-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-muted);
}

.owner-chip {
  padding: 7px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

.owner-chip.selected {
  border-color: var(--primary);
  background: var(--primary-soft);
}

.warehouse-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
}

.summary-label {
  font-size: 0.74rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--text-muted);
}

.summary-item strong {
  font-size: 1.3rem;
}

.seg {
  display: inline-flex;
  flex-wrap: wrap;
  padding: 3px;
  border-radius: 999px;
  background: var(--surface-alt);
  border: 1px solid var(--border);
}

.seg button {
  padding: 6px 14px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
}

.seg button.active {
  background: var(--primary);
  color: #fff;
}

.row-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.notes {
  max-width: 260px;
  white-space: pre-line;
}

.below-cost {
  color: var(--danger);
  font-weight: 700;
}

.input-below-cost {
  border-color: var(--danger);
}

.danger-text {
  color: var(--danger);
}

.piece-info {
  display: block;
  line-height: 1.5;
  margin-bottom: 14px;
}

@media (max-width: 640px) {
  .warehouse-summary {
    grid-template-columns: 1fr;
  }
}
</style>
