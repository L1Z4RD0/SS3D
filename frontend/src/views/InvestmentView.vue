<script setup>
import { ref, computed, nextTick, onMounted } from "vue";
import * as betaApi from "../api/beta";
import { formatCurrency } from "../utils/format";
import { extractApiError } from "../utils/validation";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import CountUp from "../components/CountUp.vue";

/* Mi inversión (BETA): cuánto lleva recuperado cada socio de lo que puso en impresoras y
   filamento, según lo que se cobró en los pedidos entregados. */
const data = ref(null);
const error = ref("");
const loading = ref(true);
const filled = ref(false);
const pctText = (v) => `${v.toLocaleString("es-CL", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;

onMounted(async () => {
  try {
    data.value = await betaApi.getMyInvestment();
    // Las barras y el anillo arrancan vacíos y se llenan apenas se pintan.
    await nextTick();
    requestAnimationFrame(() => requestAnimationFrame(() => (filled.value = true)));
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
    <div v-if="loading" class="card"><LoadingSkeleton :lines="6" /></div>

    <template v-if="data">
      <div class="card total-card glow">
        <svg class="inv-ring" viewBox="0 0 120 120" aria-hidden="true">
          <defs>
            <linearGradient id="inv-grad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stop-color="var(--primary)" />
              <stop offset="1" stop-color="var(--accent)" />
            </linearGradient>
          </defs>
          <circle cx="60" cy="60" r="50" class="track" />
          <circle
            cx="60"
            cy="60"
            r="50"
            pathLength="100"
            class="val"
            :style="{ strokeDashoffset: filled ? 100 - pct(total) : 100 }"
          />
        </svg>
        <div class="inv-total-text">
          <strong>Total recuperado</strong>
          <div class="inv-pct"><CountUp :value="pct(total)" :format="pctText" :duration="1400" :delay="200" /></div>
          <span class="mono">
            <strong><CountUp :value="Number(total.recovered)" :format="formatCurrency" :duration="1400" :delay="200" /></strong>
            de {{ formatCurrency(total.invested) }}
          </span>
        </div>
      </div>

      <div class="grid grid-cols-2 inv-grid">
        <div v-for="(item, i) in items" :key="item.name" v-reveal="i * 0.06" class="card glow">
          <div class="inv-head">
            <strong>{{ item.name }}</strong>
            <span class="text-muted text-sm">{{ item.name === "Filamentos" ? "carretes comprados" : "valor de compra" }}</span>
          </div>
          <div class="bar">
            <div
              class="bar-fill"
              :class="{ done: pct(item) >= 100 }"
              :style="{ width: filled ? `${pct(item)}%` : 0, transitionDelay: `${0.3 + i * 0.1}s` }"
            ></div>
          </div>
          <div class="inv-foot">
            <span class="mono">{{ formatCurrency(item.recovered) }} de {{ formatCurrency(item.invested) }}</span>
            <strong class="inv-item-pct">
              <span v-if="pct(item) >= 100" class="inv-done">✓</span>
              <CountUp :value="pct(item)" :format="pctText" :duration="1200" :delay="300 + i * 100" />
            </strong>
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

.total-card {
  display: flex;
  align-items: center;
  gap: 24px;
}

.inv-ring {
  width: 132px;
  height: 132px;
  flex-shrink: 0;
  transform: rotate(-90deg);
}
.inv-ring circle {
  fill: none;
  stroke-width: 12;
}
.inv-ring .track {
  stroke: var(--surface-alt);
}
.inv-ring .val {
  stroke: url(#inv-grad);
  stroke-linecap: round;
  stroke-dasharray: 100;
  transition: stroke-dashoffset 1.4s var(--ease-out) 0.2s;
}

.inv-total-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.bar {
  height: 12px;
  margin-top: 12px;
  border-radius: 999px;
  background: var(--surface-alt);
  overflow: hidden;
}

.bar-fill {
  position: relative;
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--primary), var(--accent));
  transition: width 1.2s var(--ease-out);
  overflow: hidden;
}
/* Brillo que recorre la barra de vez en cuando. */
.bar-fill::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(100deg, transparent 30%, rgba(255, 255, 255, 0.4) 50%, transparent 70%);
  transform: translateX(-100%);
  animation: inv-shine 3.5s var(--ease-out) 1.6s infinite;
}
@keyframes inv-shine {
  40%,
  100% {
    transform: translateX(100%);
  }
}

.bar-fill.done {
  background: var(--success);
}

.inv-item-pct {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.inv-done {
  display: inline-grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--success);
  color: #fff;
  font-size: 0.7rem;
  animation: zola-pop-in 0.45s var(--ease-spring) 1.4s both;
}

.inv-pct {
  font-size: 2rem;
  font-weight: 800;
  line-height: 1.1;
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
