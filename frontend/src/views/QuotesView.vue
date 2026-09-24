<script setup>
import { ref, onMounted } from "vue";
import * as quotesApi from "../api/quotes";
import { formatCurrency, formatDate } from "../utils/format";
import { extractApiError } from "../utils/validation";
import Modal from "../components/Modal.vue";

const quotes = ref([]);
const total = ref(0);
const loading = ref(true);
const loadError = ref("");
const limit = 20;
const offset = ref(0);

const selected = ref(null);
const showDocument = ref(false);

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    const page = await quotesApi.listQuotes({ limit, offset: offset.value });
    quotes.value = page.items;
    total.value = page.total;
  } catch (err) {
    loadError.value = extractApiError(err, "No se pudieron cargar las cotizaciones.");
  } finally {
    loading.value = false;
  }
}

function openDocument(quote) {
  selected.value = quote;
  showDocument.value = true;
}

function printDocument() {
  window.print();
}

function nextPage() {
  if (offset.value + limit < total.value) {
    offset.value += limit;
    load();
  }
}

function prevPage() {
  if (offset.value > 0) {
    offset.value = Math.max(0, offset.value - limit);
    load();
  }
}

onMounted(load);
</script>

<template>
  <div>
    <div class="page-header">
      <p class="page-subtitle">Respaldo de todas las cotizaciones que generaste, con su comprobante</p>
    </div>

    <div v-if="loading" class="empty-state">Cargando...</div>
    <div v-else-if="loadError" class="alert alert-danger">{{ loadError }}</div>
    <div v-else-if="!quotes.length" class="card empty-state">
      <h3>Todavía no generaste cotizaciones</h3>
      <p>Cuando generes una desde la Calculadora, va a quedar guardada acá con su comprobante.</p>
    </div>

    <div v-else class="card">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>N°</th>
              <th>Cliente</th>
              <th>Fecha</th>
              <th class="text-right">Neto</th>
              <th class="text-right">IVA</th>
              <th class="text-right">Total</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="q in quotes" :key="q.id">
              <td><strong>#{{ q.quote_number }}</strong></td>
              <td>{{ q.client_name }}</td>
              <td>{{ formatDate(q.quote_date) }}</td>
              <td class="text-right mono">{{ formatCurrency(q.subtotal) }}</td>
              <td class="text-right mono">{{ formatCurrency(q.iva_amount) }}</td>
              <td class="text-right mono"><strong>{{ formatCurrency(q.total) }}</strong></td>
              <td class="text-right">
                <button class="btn btn-secondary btn-sm" @click="openDocument(q)">Ver comprobante</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="flex items-center justify-between mt-4">
        <span class="text-muted text-sm">{{ total }} cotización(es) en total</span>
        <div class="flex gap-2">
          <button class="btn btn-secondary btn-sm" :disabled="offset === 0" @click="prevPage">Anterior</button>
          <button
            class="btn btn-secondary btn-sm"
            :disabled="offset + limit >= total"
            @click="nextPage"
          >
            Siguiente
          </button>
        </div>
      </div>
    </div>

    <Modal
      v-if="showDocument && selected"
      :title="`Cotización #${selected.quote_number}`"
      :subtitle="`${selected.client_name} · ${formatDate(selected.quote_date)}`"
      width="640px"
      @close="showDocument = false"
    >
      <pre v-if="selected.document_snapshot" class="quote-snapshot">{{ selected.document_snapshot }}</pre>
      <div v-else class="alert alert-info">
        Esta cotización se generó antes de que guardáramos el comprobante, así que solo está el detalle de
        abajo.
      </div>

      <div class="table-wrap mt-3">
        <table>
          <thead>
            <tr>
              <th>Producto</th>
              <th class="text-right">Cant.</th>
              <th class="text-right">Precio unit.</th>
              <th class="text-right">Subtotal</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in selected.items" :key="item.id">
              <td>{{ item.description }}</td>
              <td class="text-right mono">{{ item.quantity }}</td>
              <td class="text-right mono">{{ formatCurrency(item.unit_price) }}</td>
              <td class="text-right mono">{{ formatCurrency(item.subtotal) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="form-actions no-print">
        <button class="btn btn-secondary" @click="showDocument = false">Cerrar</button>
        <button class="btn btn-primary" @click="printDocument">Imprimir</button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.quote-snapshot {
  background: var(--surface-alt);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 14px;
  font-size: 0.82rem;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}
</style>
