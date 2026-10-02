<script setup>
import { ref, computed, onMounted } from "vue";
import * as salesApi from "../api/sales";
import * as betaApi from "../api/beta";
import { formatCurrency, formatDate, formatDateTime, todayISO } from "../utils/format";
import { extractApiError } from "../utils/validation";
import { confirmAction } from "../composables/useConfirm";
import { STATUS_LABELS, OPEN_STATUSES, statusClass, statusOptions, isOverdue } from "../utils/orderStatus";
import Modal from "./Modal.vue";
import CancelOrderModal from "./CancelOrderModal.vue";

/* Detalle de un pedido: datos clave, línea de tiempo de estados (cuándo se creó, cómo
   avanzó y quién lo movió) y botones para cambiar de estado. Se usa en Ventas y en el
   Calendario. El servidor valida cada cambio; aquí solo se muestran los permitidos. */
const props = defineProps({
  saleId: { type: String, required: true },
});
const emit = defineEmits(["close", "changed"]);

const sale = ref(null);
const loading = ref(true);
const busy = ref(false);
const error = ref("");

const today = todayISO();
const overdue = computed(() => sale.value && isOverdue(sale.value, today));
const options = computed(() => (sale.value?.can_edit ? statusOptions(sale.value) : []));

async function load() {
  loading.value = true;
  error.value = "";
  try {
    sale.value = await salesApi.getSale(props.saleId);
  } catch (err) {
    error.value = extractApiError(err, "No se pudo cargar el pedido.");
  } finally {
    loading.value = false;
  }
}

async function applyStatus(opt) {
  let skipConfirmed = false;
  if (opt.kind === "skip") {
    const ok = await confirmAction({
      title: "Entregar directo",
      message:
        `El pedido está ${STATUS_LABELS[sale.value.status]}. Se marcará como Entregado hoy y los pasos ` +
        "intermedios quedarán registrados con la misma hora. Desde ese momento cuenta como ingreso.",
      confirmLabel: "Marcar entregado",
    });
    if (!ok) return;
    skipConfirmed = true;
  } else if (opt.status === "entregada") {
    const ok = await confirmAction({
      title: "Entregar pedido",
      message: "Se marcará como Entregado hoy. Es un estado final y desde ese momento cuenta como ingreso.",
      confirmLabel: "Marcar entregado",
    });
    if (!ok) return;
  }
  busy.value = true;
  error.value = "";
  try {
    sale.value = await salesApi.changeSaleStatus(sale.value.id, {
      status: opt.status,
      skip_confirmed: skipConfirmed,
      today,
    });
    emit("changed", sale.value);
  } catch (err) {
    error.value = extractApiError(err, "No se pudo cambiar el estado.");
  } finally {
    busy.value = false;
  }
}

/* -------- Cambiar la fecha de entrega comprometida (solo pedidos abiertos) -------- */
const canMoveDate = computed(() => sale.value?.can_edit && OPEN_STATUSES.includes(sale.value.status));
const editingDate = ref(false);
const newDate = ref("");

function startDateEdit() {
  newDate.value = sale.value.promised_delivery_date;
  editingDate.value = true;
}

async function saveDate() {
  if (!newDate.value) return;
  busy.value = true;
  error.value = "";
  try {
    sale.value = await salesApi.changeDeliveryDate(sale.value.id, newDate.value);
    editingDate.value = false;
    emit("changed", sale.value);
  } catch (err) {
    error.value = extractApiError(err, "No se pudo cambiar la fecha.");
  } finally {
    busy.value = false;
  }
}

/* -------- Delivery --------
   Si el cliente pidió delivery (aunque al principio dijera que retiraba), se registra quién
   lo llevó y cuánto se le devuelve. Es solo un registro: no cambia precio, costos ni ganancia. */
const canEditDelivery = computed(() => sale.value?.can_edit && sale.value.status !== "cancelado");
const editingDelivery = ref(false);
const deliveryForm = ref({ delivery_by: "", delivery_amount: null });
const deliveryPeople = ref([]);

async function startDeliveryEdit() {
  deliveryForm.value = {
    delivery_by: sale.value.delivery_by || "",
    delivery_amount: Number(sale.value.delivery_amount) || null,
  };
  editingDelivery.value = true;
  if (!deliveryPeople.value.length) {
    try {
      deliveryPeople.value = (await betaApi.getBetaAccess()).partners.filter((p) => p !== "Caja");
    } catch {
      // Sin lista sugerida: se escribe el nombre a mano.
    }
  }
}

async function saveDelivery(remove = false) {
  const who = remove ? "" : deliveryForm.value.delivery_by.trim();
  if (!remove && !who) {
    error.value = "Indica quién hizo el delivery.";
    return;
  }
  busy.value = true;
  error.value = "";
  try {
    sale.value = await salesApi.setSaleDelivery(sale.value.id, {
      delivery_by: who || null,
      delivery_amount: remove ? 0 : Number(deliveryForm.value.delivery_amount) || 0,
    });
    editingDelivery.value = false;
    emit("changed", sale.value);
  } catch (err) {
    error.value = extractApiError(err, "No se pudo guardar el delivery.");
  } finally {
    busy.value = false;
  }
}

/* -------- Cancelación -------- */
const showCancel = ref(false);
const PIECE_STATUS = { en_almacen: "En almacén", reservada: "Reservada", vendida: "Vendida", descartada: "Descartada" };

function onCancelled(updated) {
  sale.value = updated;
  showCancel.value = false;
  emit("changed", updated);
}

onMounted(load);
</script>

<template>
  <Modal :title="sale ? sale.client_name : 'Pedido'" subtitle="Estado y línea de tiempo del pedido" width="560px" @close="emit('close')">
    <div v-if="loading" class="empty-state">Cargando...</div>
    <div v-else-if="!sale" class="alert alert-danger">{{ error }}</div>
    <template v-else>
      <div class="order-summary">
        <div>
          <span class="badge" :class="statusClass(sale.status)">{{ STATUS_LABELS[sale.status] }}</span>
          <span v-if="overdue" class="badge badge-overdue" style="margin-left: 6px">Atrasado</span>
        </div>
        <dl>
          <dt>Pedido</dt>
          <dd>{{ formatDate(sale.sale_date) }}</dd>
          <dt>Entrega comprometida</dt>
          <dd>
            <div v-if="editingDate" class="date-edit">
              <input v-model="newDate" type="date" aria-label="Nueva fecha de entrega" />
              <button type="button" class="btn btn-primary btn-sm" :disabled="busy || !newDate" @click="saveDate">Guardar</button>
              <button type="button" class="btn btn-ghost btn-sm" :disabled="busy" @click="editingDate = false">Cancelar</button>
            </div>
            <template v-else>
              <span :class="{ 'text-danger': overdue }">{{ formatDate(sale.promised_delivery_date) }}</span>
              <button v-if="canMoveDate" type="button" class="link-btn" @click="startDateEdit">Cambiar</button>
            </template>
          </dd>
          <template v-if="sale.delivered_date">
            <dt>Entregado</dt>
            <dd>{{ formatDate(sale.delivered_date) }}</dd>
          </template>
          <dt>Precio</dt>
          <dd class="mono">{{ formatCurrency(sale.price) }}</dd>
          <dt>Inventario de</dt>
          <dd>{{ sale.owner_username }}</dd>
          <dt>Registrada por</dt>
          <dd>{{ sale.created_by_username || "Usuario eliminado" }}</dd>
          <template v-if="sale.buyer_name">
            <dt>Comprador</dt>
            <dd>{{ sale.buyer_name }}</dd>
          </template>
          <dt>Delivery</dt>
          <dd>
            <template v-if="!editingDelivery">
              <span v-if="sale.delivery_by">
                🛵 {{ sale.delivery_by }}<template v-if="Number(sale.delivery_amount) > 0">
                  · se le devuelven {{ formatCurrency(sale.delivery_amount) }}</template>
              </span>
              <span v-else-if="Number(sale.delivery_amount) > 0">
                🛵 {{ formatCurrency(sale.delivery_amount) }} · <span class="text-danger">falta indicar quién lo lleva</span>
              </span>
              <span v-else class="text-muted">Retira el cliente</span>
              <button v-if="canEditDelivery" type="button" class="link-btn" @click="startDeliveryEdit">
                {{ sale.delivery_by || Number(sale.delivery_amount) > 0 ? "Cambiar" : "Cambiar a delivery" }}
              </button>
            </template>
            <div v-else class="delivery-edit">
              <input
                v-model="deliveryForm.delivery_by"
                list="delivery-people"
                maxlength="60"
                placeholder="¿Quién lo llevó?"
                aria-label="Quién hizo el delivery"
              />
              <datalist id="delivery-people">
                <option v-for="p in deliveryPeople" :key="p" :value="p" />
              </datalist>
              <input
                v-model.number="deliveryForm.delivery_amount"
                type="number"
                min="0"
                step="100"
                placeholder="Monto del delivery"
                aria-label="Monto del delivery"
              />
              <div class="delivery-edit-actions">
                <button type="button" class="btn btn-primary btn-sm" :disabled="busy" @click="saveDelivery()">Guardar</button>
                <button
                  v-if="sale.delivery_by || Number(sale.delivery_amount) > 0"
                  type="button"
                  class="btn btn-ghost btn-sm"
                  :disabled="busy"
                  @click="saveDelivery(true)"
                >
                  Quitar delivery
                </button>
                <button type="button" class="btn btn-ghost btn-sm" :disabled="busy" @click="editingDelivery = false">Cancelar</button>
              </div>
              <span class="field-hint">
                Lo paga el cliente: se suma al precio del pedido y se le devuelve a quien lo llevó. La ganancia no cambia.
              </span>
            </div>
          </dd>
        </dl>
      </div>

      <div v-if="sale.status === 'cancelado'" class="cancel-box">
        <strong>Pedido cancelado</strong>
        <span v-if="sale.cancel_reason">Motivo: {{ sale.cancel_reason }}</span>
        <span v-if="sale.warehouse_piece">
          Pieza: {{ PIECE_STATUS[sale.warehouse_piece.status] }} · costo {{ formatCurrency(sale.warehouse_piece.cost) }}
        </span>
        <span v-if="Number(sale.loss_amount) > 0">Pérdida: {{ formatCurrency(sale.loss_amount) }}</span>
      </div>

      <div v-if="options.length" class="status-actions">
        <button
          v-for="opt in options"
          :key="opt.status + opt.kind"
          type="button"
          class="btn btn-sm"
          :class="opt.kind === 'next' ? 'btn-primary' : 'btn-secondary'"
          :disabled="busy"
          @click="applyStatus(opt)"
        >
          {{ opt.label }}
        </button>
        <button type="button" class="btn btn-sm btn-ghost cancel-btn" :disabled="busy" @click="showCancel = true">
          Cancelar pedido
        </button>
      </div>
      <p v-else-if="!sale.can_edit" class="field-hint">
        Solo lectura: este pedido lo gestiona {{ sale.owner_username }}.
      </p>

      <div v-if="error" class="alert alert-danger mt-2">{{ error }}</div>

      <h4 class="timeline-title">Línea de tiempo</h4>
      <ol class="timeline">
        <li v-for="(h, i) in sale.status_history" :key="i">
          <span class="timeline-dot" :class="statusClass(h.status)"></span>
          <div>
            <strong>{{ STATUS_LABELS[h.status] }}</strong>
            <span class="text-muted text-sm"> · {{ formatDateTime(h.changed_at) }}</span>
            <div class="text-sm text-muted">
              {{ h.changed_by_username || "—" }}<template v-if="h.note"> · {{ h.note }}</template>
            </div>
          </div>
        </li>
      </ol>

      <div class="form-actions">
        <button type="button" class="btn btn-secondary" @click="emit('close')">Cerrar</button>
      </div>
    </template>
  </Modal>
  <CancelOrderModal v-if="showCancel && sale" :sale="sale" @close="showCancel = false" @cancelled="onCancelled" />
</template>

<style scoped>
.order-summary {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 14px;
}

.order-summary dl {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 4px 14px;
  margin: 0;
  font-size: 0.88rem;
}

.order-summary dt {
  color: var(--text-muted);
}

.order-summary dd {
  margin: 0;
}

.date-edit {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}

.date-edit input {
  width: auto;
  padding: 5px 8px;
}

.link-btn {
  margin-left: 8px;
  padding: 0;
  border: none;
  background: none;
  color: var(--primary);
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
}

.link-btn:hover {
  text-decoration: underline;
}

.text-danger {
  color: var(--danger);
  font-weight: 700;
}

.cancel-box {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--surface-alt);
  border: 1px solid var(--border);
  font-size: 0.86rem;
}

.cancel-btn {
  margin-left: auto;
  color: var(--danger);
}

.status-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 6px;
}

.timeline-title {
  margin: 16px 0 8px;
  font-size: 0.9rem;
}

.timeline {
  list-style: none;
  margin: 0;
  padding: 0 0 0 4px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-left: 2px solid var(--border);
}

.timeline li {
  position: relative;
  display: flex;
  gap: 10px;
  padding-left: 14px;
}

.timeline-dot {
  position: absolute;
  left: -8px;
  top: 4px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid var(--surface);
  /* El color del estado (de la clase status-*) como punto sólido. */
  background: currentColor;
}

.delivery-edit {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.delivery-edit input {
  width: auto;
  flex: 1 1 140px;
  min-width: 0;
}

.delivery-edit-actions {
  display: flex;
  gap: 6px;
  width: 100%;
}
</style>
