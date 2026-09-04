<script setup>
import { computed } from "vue";
import { formatCurrency, formatDate, formatNumber } from "../utils/format";

const props = defineProps({
  quote: { type: Object, required: true },
  businessName: { type: String, default: "" },
  logoDataUrl: { type: String, default: "" },
});

const quoteNumberLabel = computed(() => `COT-${String(props.quote.quote_number).padStart(4, "0")}`);
</script>

<template>
  <div id="quote-print-area" class="quote-doc">
    <div class="quote-doc-header">
      <div class="quote-doc-brand">
        <img v-if="logoDataUrl" :src="logoDataUrl" alt="Logo" class="quote-doc-logo" />
        <div>
          <div class="quote-doc-business-name">{{ businessName || "Mi negocio" }}</div>
          <div class="quote-doc-tagline">Impresión 3D</div>
        </div>
      </div>
      <div class="quote-doc-meta">
        <div class="quote-doc-number">{{ quoteNumberLabel }}</div>
        <div>Fecha: {{ formatDate(quote.quote_date) }}</div>
      </div>
    </div>

    <div class="quote-doc-client">
      <span class="quote-doc-label">Cliente</span>
      <span>{{ quote.client_name }}</span>
    </div>

    <table class="quote-doc-table">
      <thead>
        <tr>
          <th>Producto</th>
          <th class="text-right">Cantidad</th>
          <th class="text-right">Precio unitario (sin IVA)</th>
          <th class="text-right">Subtotal</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in quote.items" :key="item.id">
          <td>{{ item.description }}</td>
          <td class="text-right">{{ formatNumber(item.quantity, 2) }}</td>
          <td class="text-right">{{ formatCurrency(item.unit_price) }}</td>
          <td class="text-right">{{ formatCurrency(item.subtotal) }}</td>
        </tr>
      </tbody>
    </table>

    <div class="quote-doc-totals">
      <div>
        <span>Total sin IVA</span>
        <span>{{ formatCurrency(quote.subtotal) }}</span>
      </div>
      <div>
        <span>IVA ({{ formatNumber(quote.iva_percent, 0) }}%)</span>
        <span>{{ formatCurrency(quote.iva_amount) }}</span>
      </div>
      <div class="quote-doc-total-final">
        <span>Total con IVA</span>
        <span>{{ formatCurrency(quote.total) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.quote-doc {
  background: #fff;
  color: #16171f;
  padding: 32px;
  font-family: "Inter", sans-serif;
}

.quote-doc-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  border-bottom: 2px solid #16171f;
  padding-bottom: 16px;
  margin-bottom: 20px;
}

.quote-doc-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.quote-doc-logo {
  width: 52px;
  height: 52px;
  object-fit: contain;
  border-radius: 8px;
}

.quote-doc-business-name {
  font-size: 1.2rem;
  font-weight: 800;
}

.quote-doc-tagline {
  font-size: 0.8rem;
  color: #6b7086;
}

.quote-doc-meta {
  text-align: right;
  font-size: 0.85rem;
  color: #333;
}

.quote-doc-number {
  font-size: 1.05rem;
  font-weight: 800;
  color: #5b4bf5;
  margin-bottom: 4px;
}

.quote-doc-client {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  font-size: 0.92rem;
}

.quote-doc-label {
  font-weight: 700;
  color: #6b7086;
}

.quote-doc-table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 20px;
  font-size: 0.88rem;
}

.quote-doc-table th {
  text-align: left;
  background: #f4f5fa;
  padding: 8px 10px;
  border: 1px solid #d8dae4;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: #4a4d63;
}

.quote-doc-table td {
  padding: 8px 10px;
  border: 1px solid #d8dae4;
}

.text-right {
  text-align: right;
}

.quote-doc-totals {
  margin-left: auto;
  width: 280px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 0.9rem;
}

.quote-doc-totals > div {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
}

.quote-doc-total-final {
  border-top: 2px solid #16171f;
  margin-top: 6px;
  padding-top: 8px !important;
  font-weight: 800;
  font-size: 1.05rem;
}
</style>
