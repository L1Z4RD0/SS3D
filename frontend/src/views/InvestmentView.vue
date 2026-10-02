<script setup>
import { ref, computed, onMounted } from "vue";
import * as betaApi from "../api/beta";
import { formatCurrency } from "../utils/format";
import { extractApiError } from "../utils/validation";

/* Mi inversión (BETA): cuánto lleva recuperado cada socio de lo que puso en impresoras y
   filamento, según lo que se cobró en los pedidos entregados. */
const data = ref(null);
const error = ref("");
const loading = ref(true);

onMounted(async () => {
  try {
    data.value = await betaApi.getMyInvestment();
  } catch (err) {
    error.value = extractApiError(err, "No se pudo calcular tu inversión.");
  } finally {
    loading.value = false;
  }
});

const pct = (item) => (Number(item.invested) > 0 ? Math.min(100, (Number(item.recovered) / Number(item.invested)) * 100) : 0);
const items = computed(() => (data.value ? [...data.value.printers, data.value.filaments] : []));
const total = computed(() =>
  data.value ? { name: "Total", invested: data.value.total_invested, recovered: data.value.total_recovered } : null
);
</script>

<template>
  <div>
    <div class="page-header">
      <p class="page-subtitle">
        <span class="beta-badge">BETA</span>
        Cuánto llevas recuperado de lo que invertiste, con lo que se cobró en los pedidos entregados.
      </p>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="loading" class="card empty-state">Calculando...</div>

    <template v-if="data">
      <div class="card total-card">
        <div class="inv-head">
          <strong>Total recuperado</strong>
          <span class="mono">
            <strong>{{ formatCurrency(total.recovered) }}</strong> de {{ formatCurrency(total.invested) }}
          </span>
        </div>
        <div class="bar bar-lg"><div class="bar-fill" :style="{ width: `${pct(total)}%` }"></div></div>
        <div class="inv-pct">{{ pct(total).toFixed(1) }}%</div>
      </div>

      <div class="grid grid-cols-2 inv-grid">
        <div v-for="item in items" :key="item.name" class="card">
          <div class="inv-head">
            <strong>{{ item.name }}</strong>
            <span class="text-muted text-sm">{{ item.name === "Filamentos" ? "carretes comprados" : "valor de compra" }}</span>
          </div>
          <div class="bar"><div class="bar-fill" :class="{ done: pct(item) >= 100 }" :style="{ width: `${pct(item)}%` }"></div></div>
          <div class="inv-foot">
            <span class="mono">{{ formatCurrency(item.recovered) }} de {{ formatCurrency(item.invested) }}</span>
            <strong>{{ pct(item).toFixed(1) }}%</strong>
          </div>
        </div>
      </div>

      <ul class="inv-notes">
        <li>
          <strong>Impresoras:</strong> se recupera con la depreciación + luz que se cobró en cada pedido hecho en ellas
          (también los que vendió la Empresa con tu impresora). Al terminar de recuperarla, la depreciación se te sigue
          pagando: es tu impresora.
        </li>
        <li>
          <strong>Filamentos:</strong> se recupera con el material tuyo que se usó. Lo que pague la Empresa con su propio
          filamento no cuenta aquí.
        </li>
        <li>Cuenta todos los pedidos entregados y cobrados registrados en la app (no los "Por cobrar").</li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.beta-badge {
  display: inline-block;
  margin-right: 6px;
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--primary-soft);
  color: var(--primary);
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.05em;
}

.inv-head,
.inv-foot {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
}

.inv-foot {
  margin-top: 8px;
  font-size: 0.88rem;
}

.bar {
  height: 12px;
  margin-top: 12px;
  border-radius: 999px;
  background: var(--surface-alt);
  overflow: hidden;
}

.bar-lg {
  height: 18px;
}

.bar-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--primary), var(--accent));
  transition: width 0.4s ease;
}

.bar-fill.done {
  background: var(--success);
}

.inv-pct {
  margin-top: 8px;
  font-size: 1.6rem;
  font-weight: 800;
}

.inv-grid {
  margin-top: 16px;
}

.inv-notes {
  margin: 16px 0 0;
  padding-left: 18px;
  color: var(--text-muted);
  font-size: 0.84rem;
  line-height: 1.6;
}
</style>
