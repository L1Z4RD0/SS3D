<script setup>
import { ref, computed } from "vue";
import * as salesApi from "../api/sales";
import { formatCurrency, formatNumber, todayISO } from "../utils/format";
import { extractApiError } from "../utils/validation";
import { STATUS_LABELS } from "../utils/orderStatus";
import Modal from "./Modal.vue";

/* Flujo de cancelación. Cancelar es un hecho del negocio: el pedido queda registrado
   como Cancelado (no se borra) y nunca cuenta como ingreso. Según el estado se pregunta
   qué pasa con las horas y con la pieza; el servidor aplica las mismas reglas. */
const props = defineProps({
  sale: { type: Object, required: true },
});
const emit = defineEmits(["close", "cancelled"]);

const DISCARD_REASONS = [
  { value: "regalada", label: "Regalada" },
  { value: "danada", label: "Dañada" },
  { value: "desechada", label: "Desechada" },
  { value: "otro", label: "Otro" },
];

const status = computed(() => props.sale.status);
const fromAlmacen = computed(() => !!props.sale.warehouse_item_id);
const inProduction = computed(() => status.value === "en_produccion" && !fromAlmacen.value);
const ready = computed(() => status.value === "lista" && !fromAlmacen.value);
const asksQuestions = computed(() => inProduction.value || ready.value);

const keepHours = ref(true);
// En producción: "almacen" | "inutilizable". Lista: "almacen" | "descartar".
const pieceOutcome = ref("almacen");
const discardReason = ref("");
const reason = ref("");
const busy = ref(false);
const error = ref("");

const n = (v) => Number(v) || 0;
const suppliesCount = computed(() => props.sale.supplies_used.reduce((s, x) => s + n(x.quantity_used), 0));

// Misma regla que el servidor: material + postprocesado + insumos (solo si se consumen,
// es decir desde Lista) + depreciación y energía (solo si se dejan las horas). Sin envío.
const pieceCost = computed(() => {
  const s = props.sale;
  let cost = n(s.material_cost) + n(s.postprocess_cost);
  if (ready.value) cost += n(s.supplies_cost);
  if (keepHours.value) cost += n(s.depreciation_cost) + n(s.energy_cost);
  return cost;
});

const outcomeText = computed(() => {
  if (!asksQuestions.value) return "";
  if (pieceOutcome.value === "almacen") {
    return `La pieza entra al Almacén con costo ${formatCurrency(pieceCost.value)} y precio de venta ${formatCurrency(props.sale.price)} (editable después).`;
  }
  if (pieceOutcome.value === "descartar") return `La pieza se descarta: ${formatCurrency(pieceCost.value)} quedan como pérdida.`;
  return `La pieza no sirve: ${formatCurrency(pieceCost.value)} quedan como pérdida.`;
});

// Pieza dañada: En producción y no sirve, o Lista y descartada por "Dañada". Solo entonces
// se ofrece rehacer el pedido (uno igual, directo En producción).
const damaged = computed(
  () =>
    (inProduction.value && pieceOutcome.value === "inutilizable") ||
    (ready.value && pieceOutcome.value === "descartar" && discardReason.value === "danada")
);
const redo = ref(null); // null = sin responder
const willRedo = computed(() => damaged.value && redo.value === true);

const canSubmit = computed(
  () => !(ready.value && pieceOutcome.value === "descartar" && !discardReason.value) && !(damaged.value && redo.value === null)
);

async function submit() {
  if (!canSubmit.value) return;
  busy.value = true;
  error.value = "";
  try {
    const payload = { reason: reason.value.trim() || null, today: todayISO() };
    if (asksQuestions.value) {
      payload.keep_hours = keepHours.value;
      payload.piece_outcome = pieceOutcome.value;
      if (pieceOutcome.value === "descartar") payload.discard_reason = discardReason.value;
      if (willRedo.value) payload.redo = true;
    }
    const updated = await salesApi.cancelSale(props.sale.id, payload);
    emit("cancelled", updated);
  } catch (err) {
    const msg = extractApiError(err, "No se pudo cancelar el pedido.");
    // Si no se pudo rehacer (ej. falta filamento) no se canceló nada: se avisa claro.
    error.value = willRedo.value ? `${msg} No se canceló el pedido: puedes cancelarlo sin rehacerlo.` : msg;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <Modal persistent title="Cancelar pedido" :subtitle="`${sale.client_name} · ${STATUS_LABELS[sale.status]}`" width="560px" @close="emit('close')">
    <form @submit.prevent="submit">
      <!-- Pedido de una pieza del Almacén -->
      <div v-if="fromAlmacen" class="alert alert-info cancel-info">
        Este pedido vendía una pieza del Almacén: la pieza vuelve a estar disponible en el Almacén. No hay nada que
        devolver al inventario.
      </div>

      <!-- Pendiente -->
      <div v-else-if="status === 'pendiente'" class="alert alert-info cancel-info">
        Todavía no se empezó a fabricar, así que se devuelve todo al inventario:
        <strong>{{ formatNumber(sale.grams_used, 0) }} g</strong> de filamento<template v-if="suppliesCount">,
        <strong>{{ formatNumber(suppliesCount, 0) }}</strong> insumo(s)</template> y
        <strong>{{ formatNumber(sale.print_hours, 1) }} h</strong> de la impresora. Sin pérdida.
      </div>

      <!-- En producción / Lista -->
      <template v-else>
        <div class="alert alert-warning cancel-info">
          La pieza ya se fabricó (o se está fabricando): los
          <strong>{{ formatNumber(sale.grams_used, 0) }} g</strong> de filamento quedan consumidos.
          <template v-if="inProduction && suppliesCount">Los insumos se devuelven al inventario.</template>
          <template v-if="ready && suppliesCount">Los insumos quedan consumidos (ya se pusieron).</template>
        </div>

        <fieldset class="question">
          <legend>¿Dejar registradas las {{ formatNumber(sale.print_hours, 1) }} h de impresión en la impresora?</legend>
          <label class="option"><input v-model="keepHours" type="radio" :value="true" /> Sí, dejarlas (recomendado)</label>
          <label class="option"><input v-model="keepHours" type="radio" :value="false" /> No, devolverlas</label>
          <p class="field-hint">
            La impresora sí trabajó esas horas. Si no las registras, su % de vida usada quedará subestimado.
          </p>
        </fieldset>

        <fieldset v-if="inProduction" class="question">
          <legend>¿La pieza quedó utilizable?</legend>
          <label class="option"><input v-model="pieceOutcome" type="radio" value="almacen" /> Sí, guardarla en el Almacén</label>
          <label class="option"><input v-model="pieceOutcome" type="radio" value="inutilizable" /> No, no sirve</label>
        </fieldset>

        <fieldset v-else class="question">
          <legend>¿Qué hacemos con la pieza?</legend>
          <label class="option"><input v-model="pieceOutcome" type="radio" value="almacen" /> Enviarla al Almacén</label>
          <label class="option"><input v-model="pieceOutcome" type="radio" value="descartar" /> Descartarla</label>
          <select v-if="pieceOutcome === 'descartar'" v-model="discardReason" class="mt-2" required aria-label="Motivo del descarte">
            <option value="" disabled>Motivo del descarte</option>
            <option v-for="r in DISCARD_REASONS" :key="r.value" :value="r.value">{{ r.label }}</option>
          </select>
        </fieldset>

        <div class="outcome" :class="pieceOutcome === 'almacen' ? 'is-warehouse' : 'is-loss'">{{ outcomeText }}</div>

        <Transition name="redo-q">
          <fieldset v-if="damaged" class="question redo-question">
            <legend>¿Volver a generar el pedido?</legend>
            <label class="option">
              <input v-model="redo" type="radio" :value="true" /> Sí, rehacerlo y pasarlo directo a En producción
            </label>
            <label class="option"><input v-model="redo" type="radio" :value="false" /> No, solo cancelar</label>
            <p class="field-hint">
              Se crea un pedido nuevo igual (mismo trabajo, cliente, precio, pago y fecha de entrega) que vuelve a
              descontar <strong>{{ formatNumber(sale.grams_used, 0) }} g</strong> de filamento<template
                v-if="suppliesCount">, los insumos</template> y <strong>{{ formatNumber(sale.print_hours, 1) }} h</strong> de la
              impresora. El pedido dañado queda Cancelado con su pérdida.
            </p>
          </fieldset>
        </Transition>
      </template>

      <div class="field mt-4">
        <label>Motivo de la cancelación (opcional)</label>
        <textarea v-model="reason" rows="2" maxlength="500" placeholder="Ej: el cliente se arrepintió" />
      </div>

      <p class="field-hint mt-2">
        El pedido queda registrado como <strong>Cancelado</strong> (no se borra) y nunca cuenta como ingreso.
      </p>

      <div v-if="error" class="alert alert-danger mt-2">{{ error }}</div>

      <div class="form-actions">
        <button type="button" class="btn btn-secondary" :disabled="busy" @click="emit('close')">Volver</button>
        <button type="submit" class="btn btn-danger" :disabled="busy || !canSubmit">
          {{ busy ? "Cancelando..." : willRedo ? "Cancelar y rehacer" : "Cancelar pedido" }}
        </button>
      </div>
    </form>
  </Modal>
</template>

<style scoped>
.cancel-info {
  display: block;
  line-height: 1.5;
  margin-bottom: 12px;
}

.question {
  margin: 0 0 12px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.question legend {
  padding: 0 4px;
  font-size: 0.88rem;
  font-weight: 700;
}

.option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 0.88rem;
  cursor: pointer;
}

.option input {
  width: auto;
}

.redo-question {
  margin-top: 12px;
  border-color: color-mix(in srgb, var(--primary) 35%, var(--border));
  background: var(--primary-soft);
}

.redo-q-enter-active {
  transition: opacity 0.25s, transform 0.3s var(--ease-out);
}
.redo-q-enter-from {
  opacity: 0;
  transform: translateY(-6px);
}

.outcome {
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  font-size: 0.86rem;
  font-weight: 600;
}

.outcome.is-warehouse {
  background: var(--accent-soft);
  color: var(--accent);
}

.outcome.is-loss {
  background: var(--danger-soft);
  color: var(--danger);
}
</style>
