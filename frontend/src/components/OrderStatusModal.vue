<script setup>
import { ref, reactive, computed, onMounted } from "vue";
import * as salesApi from "../api/sales";
import * as betaApi from "../api/beta";
import { formatCurrency, formatDate, formatDateTime, formatLongDate, formatNumber, todayISO } from "../utils/format";
import { DELIVERY_PAYMENT_CHOICES, dueInfo, isUnpaid } from "../utils/payment";
import { extractApiError } from "../utils/validation";
import { confirmAction } from "../composables/useConfirm";
import { STATUS_LABELS, OPEN_STATUSES, statusClass, statusOptions, isOverdue } from "../utils/orderStatus";
import Modal from "./Modal.vue";
import CancelOrderModal from "./CancelOrderModal.vue";
import PartialPrintFields from "./PartialPrintFields.vue";
import LoadingSkeleton from "./LoadingSkeleton.vue";

/* Detalle de un pedido: datos clave, línea de tiempo de estados (cuándo se creó, cómo
   avanzó y quién lo movió) y botones para cambiar de estado. Se usa en Ventas y en el
   Calendario. El servidor valida cada cambio; aquí solo se muestran los permitidos. */
const props = defineProps({
  saleId: { type: String, required: true },
  // Abre directo el paso de entrega (botón rápido "Entregar" de un pedido Por cobrar).
  startDelivery: { type: Boolean, default: false },
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
    if (props.startDelivery && isUnpaid(sale.value)) {
      const opt = options.value.find((o) => o.status === "entregada");
      if (opt) applyStatus(opt);
    }
  } catch (err) {
    error.value = extractApiError(err, "No se pudo cargar el pedido.");
  } finally {
    loading.value = false;
  }
}

async function applyStatus(opt) {
  // "Por cobrar": al entregar es obligatorio decir cómo pagó o hasta cuándo tiene plazo.
  if (opt.status === "entregada" && isUnpaid(sale.value)) {
    Object.assign(payForm, { choice: "", due_date: "" });
    deliveryPrompt.value = opt;
    return;
  }
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
  } else if (opt.kind === "undo") {
    const ok = await confirmAction({
      title: "Volver a Lista",
      message:
        "El pedido vuelve a Lista y deja de contar como ingreso (Dashboard, Historial y Reparto). " +
        "Si lo vuelves a entregar, vuelve a contar con la fecha de ese día.",
      confirmLabel: "Volver a Lista",
    });
    if (!ok) return;
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

/* -------- Pago de un pedido "Por cobrar" -------- */
const paymentInfo = computed(() => dueInfo(sale.value, today));
const deliveryPrompt = ref(null); // opción "Entregar" que espera el pago
const payForm = reactive({ choice: "", due_date: "" }); // choice: efectivo | transferencia | pendiente
const payFormError = computed(() => {
  if (!payForm.choice) return "Elige cómo pagó o si aún no paga.";
  if (payForm.choice === "pendiente" && !payForm.due_date) return "Indica la fecha máxima de pago.";
  if (payForm.choice === "pendiente" && payForm.due_date < today) return "La fecha máxima no puede ser anterior a hoy.";
  return "";
});

async function confirmDeliveryWithPayment() {
  if (payFormError.value) return;
  const opt = deliveryPrompt.value;
  busy.value = true;
  error.value = "";
  try {
    sale.value = await salesApi.changeSaleStatus(sale.value.id, {
      status: "entregada",
      skip_confirmed: opt.kind === "skip",
      today,
      ...(payForm.choice === "pendiente" ? { payment_due_date: payForm.due_date } : { payment_method: payForm.choice }),
    });
    deliveryPrompt.value = null;
    emit("changed", sale.value);
  } catch (err) {
    error.value = extractApiError(err, "No se pudo entregar el pedido.");
  } finally {
    busy.value = false;
  }
}

// Cobro posterior de un pedido entregado sin pagar.
const registeringPayment = ref(false);
const paymentForm = reactive({ payment_method: "", paid_date: today });
function startRegisterPayment() {
  Object.assign(paymentForm, { payment_method: "", paid_date: today });
  registeringPayment.value = true;
}
async function savePayment() {
  if (!paymentForm.payment_method || !paymentForm.paid_date) return;
  busy.value = true;
  error.value = "";
  try {
    sale.value = await salesApi.registerPayment(sale.value.id, { ...paymentForm });
    registeringPayment.value = false;
    emit("changed", sale.value);
  } catch (err) {
    error.value = extractApiError(err, "No se pudo registrar el pago.");
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
const PAYMENT_LABEL = Object.fromEntries(salesApi.PAYMENT_METHODS.map((m) => [m.value, m.label]));
const PIECE_STATUS = { en_almacen: "En almacén", reservada: "Reservada", vendida: "Vendida", descartada: "Descartada" };

/* -------- Corregir la pérdida de un cancelado (solo en su mes) -------- */
const DISCARD_LABELS = { regalada: "Regalada", danada: "Dañada", desechada: "Desechada", otro: "Otro" };
const editingLoss = ref(false);
const lossFields = ref(null);
const lossForm = reactive({ percent: 100, hours: null, postprocess: false });
function startLossEdit() {
  const s = sale.value;
  Object.assign(lossForm, {
    percent: s.cancel_printed_percent !== null ? Number(s.cancel_printed_percent) : 100,
    hours: s.cancel_print_hours !== null ? Number(s.cancel_print_hours) : null,
    postprocess: !!s.cancel_postprocess_done,
  });
  editingLoss.value = true;
}
async function saveLoss() {
  busy.value = true;
  error.value = "";
  try {
    sale.value = await salesApi.editCancellationLoss(sale.value.id, {
      printed_percent: Number(lossForm.percent),
      print_hours_used: Number(lossForm.hours) || 0,
      postprocess_done: lossForm.postprocess,
      today,
    });
    editingLoss.value = false;
    emit("changed", sale.value);
  } catch (err) {
    error.value = extractApiError(err, "No se pudo corregir la pérdida.");
  } finally {
    busy.value = false;
  }
}

function onCancelled(updated) {
  sale.value = updated;
  showCancel.value = false;
  emit("changed", updated);
}

onMounted(load);
</script>

<template>
  <Modal :title="sale ? sale.client_name : 'Pedido'" subtitle="Estado y línea de tiempo del pedido" width="560px" @close="emit('close')">
    <LoadingSkeleton v-if="loading && !sale" />
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
          <dd class="mono">
            {{ formatCurrency(sale.piece_price ?? sale.price) }}
            <span v-if="Number(sale.shipping_cost) > 0 && Number(sale.price) > 0" class="text-muted text-sm">
              + {{ formatCurrency(sale.shipping_cost) }} delivery = {{ formatCurrency(sale.price) }}
            </span>
          </dd>
          <dt>Pago</dt>
          <dd>
            <template v-if="isUnpaid(sale)">
              <span v-if="paymentInfo" class="pay-due" :class="{ 'is-overdue': paymentInfo.overdue }">{{ paymentInfo.text }}</span>
              <span v-else>Por cobrar <span class="text-muted">(se elige cómo pagó al entregarlo)</span></span>
              <button
                v-if="sale.status === 'entregada' && sale.can_edit && !registeringPayment"
                type="button"
                class="link-btn"
                @click="startRegisterPayment"
              >
                Registrar pago
              </button>
            </template>
            <template v-else>
              {{ PAYMENT_LABEL[sale.payment_method] || sale.payment_method }}
              <span v-if="sale.paid_date" class="text-muted">· cobrado el {{ formatLongDate(sale.paid_date) }}</span>
            </template>
            <div v-if="registeringPayment" class="delivery-edit pay-register">
              <select v-model="paymentForm.payment_method" aria-label="Cómo pagó">
                <option value="" disabled>¿Cómo pagó?</option>
                <option v-for="c in DELIVERY_PAYMENT_CHOICES" :key="c.value" :value="c.value">{{ c.label }}</option>
              </select>
              <input
                v-model="paymentForm.paid_date"
                type="date"
                :min="sale.delivered_date"
                :max="today"
                aria-label="Día en que pagó"
              />
              <div class="delivery-edit-actions">
                <button
                  type="button"
                  class="btn btn-primary btn-sm"
                  :disabled="busy || !paymentForm.payment_method || !paymentForm.paid_date"
                  @click="savePayment"
                >
                  Guardar pago
                </button>
                <button type="button" class="btn btn-ghost btn-sm" :disabled="busy" @click="registeringPayment = false">Cancelar</button>
              </div>
              <span class="field-hint">En el Reparto cuenta en el mes en que pagó.</span>
            </div>
          </dd>
          <dt>Venta de</dt>
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
        <span v-if="sale.cancel_discard_reason">Pieza descartada: {{ DISCARD_LABELS[sale.cancel_discard_reason] || sale.cancel_discard_reason }}</span>
        <span v-if="sale.cancel_printed_percent !== null">
          Se alcanzó a imprimir el {{ formatNumber(sale.cancel_printed_percent, 0) }} % ·
          {{ formatNumber(sale.cancel_print_hours, 2) }} h de {{ formatNumber(sale.planned_print_hours, 2) }} h ·
          {{ sale.cancel_postprocess_done ? "con" : "sin" }} postprocesado
        </span>
        <span v-if="Number(sale.loss_amount) > 0"><strong>Pérdida: {{ formatCurrency(sale.loss_amount) }}</strong> · se devuelve a cada dueño en el Reparto del mes</span>
        <button v-if="sale.loss_editable && sale.can_edit && !editingLoss" type="button" class="link-btn" @click="startLossEdit">
          Corregir pérdida
        </button>
      </div>

      <div v-if="editingLoss" class="loss-edit">
        <PartialPrintFields
          ref="lossFields"
          v-model:percent="lossForm.percent"
          v-model:hours="lossForm.hours"
          v-model:postprocess="lossForm.postprocess"
          :sale="sale"
          :supplies-consumed="sale.cancel_supplies_consumed"
        />
        <div class="delivery-edit-actions">
          <button type="button" class="btn btn-primary btn-sm" :disabled="busy || !lossFields?.valid" @click="saveLoss">
            Guardar pérdida
          </button>
          <button type="button" class="btn btn-ghost btn-sm" :disabled="busy" @click="editingLoss = false">Cancelar</button>
        </div>
        <p class="field-hint">Solo se puede corregir durante el mes en que se canceló. Ajusta el inventario según el cambio.</p>
      </div>

      <div v-if="deliveryPrompt" class="pay-prompt">
        <strong>¿Cómo pagó?</strong>
        <p class="field-hint">El pedido está <strong>Por cobrar</strong>: para entregarlo indica cómo pagó o, si aún no paga, hasta cuándo tiene plazo.</p>
        <div class="pay-choices" role="radiogroup" aria-label="Pago al entregar">
          <label v-for="c in DELIVERY_PAYMENT_CHOICES" :key="c.value" class="pay-choice" :class="{ active: payForm.choice === c.value }">
            <input v-model="payForm.choice" type="radio" :value="c.value" /> {{ c.label }}
          </label>
          <label class="pay-choice" :class="{ active: payForm.choice === 'pendiente' }">
            <input v-model="payForm.choice" type="radio" value="pendiente" /> Aún no paga
          </label>
        </div>
        <div v-if="payForm.choice === 'pendiente'" class="field pay-due-field">
          <label for="pay-due">Fecha máxima de pago</label>
          <input id="pay-due" v-model="payForm.due_date" type="date" :min="today" />
          <span v-if="payForm.due_date && payForm.due_date >= today" class="pay-due">
            Cobrar el {{ formatLongDate(payForm.due_date) }}
          </span>
          <span class="field-hint">Queda Por cobrar y no entra al Reparto hasta que registres el pago.</span>
        </div>
        <div class="delivery-edit-actions">
          <button type="button" class="btn btn-primary btn-sm" :disabled="busy || !!payFormError" @click="confirmDeliveryWithPayment">
            {{ deliveryPrompt.kind === "skip" ? "Entregar directo" : "Marcar entregado" }}
          </button>
          <button type="button" class="btn btn-ghost btn-sm" :disabled="busy" @click="deliveryPrompt = null">Cancelar</button>
        </div>
      </div>

      <div v-else-if="options.length" class="status-actions">
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
        <button
          v-if="OPEN_STATUSES.includes(sale.status)"
          type="button"
          class="btn btn-sm btn-ghost cancel-btn"
          :disabled="busy"
          @click="showCancel = true"
        >
          Cancelar pedido
        </button>
      </div>
      <p v-else-if="!sale.can_edit && !deliveryPrompt" class="field-hint">
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
.pay-prompt {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
  padding: 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--primary);
  background: var(--surface-alt);
}

.pay-prompt .field-hint {
  margin: 0;
}

.pay-choices {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.pay-choice {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface);
  font-size: 0.88rem;
  font-weight: 600;
  cursor: pointer;
}

.pay-choice.active {
  border-color: var(--primary);
  color: var(--primary);
}

.pay-choice input {
  width: auto;
  margin: 0;
}

.pay-due-field input {
  width: auto;
}

.pay-due {
  font-weight: 700;
  color: var(--warning, #b7791f);
}

.pay-due.is-overdue {
  color: var(--danger);
}

.pay-register {
  margin-top: 6px;
}

.pay-register select {
  width: auto;
}

.loss-edit {
  margin: 12px 0;
}

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
