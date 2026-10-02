<script setup>
import { ref, reactive, computed, watch, onMounted } from "vue";
import * as betaApi from "../api/beta";
import { formatCurrency, formatDate, todayISO } from "../utils/format";
import { isValidNumber, extractApiError } from "../utils/validation";
import { confirmAction } from "../composables/useConfirm";
import StatCard from "../components/StatCard.vue";
import Icon from "../components/Icon.vue";

/* Reparto del mes (BETA): una guía de lo que le correspondería a cada socio. Solo lee
   ventas e inventario; lo único que se guarda aquí son los gastos de la Empresa. */
const month = ref(todayISO().slice(0, 7));
const report = ref(null);
const expenses = ref([]);
const partners = ref([]);
const loading = ref(true);
const error = ref("");

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const [rep, exps] = await Promise.all([betaApi.getMonthlySplit(month.value), betaApi.listExpenses(month.value)]);
    report.value = rep;
    expenses.value = exps;
  } catch (err) {
    error.value = extractApiError(err, "No se pudo calcular el reparto.");
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  try {
    partners.value = (await betaApi.getBetaAccess()).partners;
  } catch {
    partners.value = ["Caja"];
  }
  await load();
});
watch(month, load);

const shareLabel = computed(() =>
  report.value ? `${report.value.parts} partes iguales (${Math.round(100 / report.value.parts)}% c/u)` : ""
);
const refundNames = computed(() => {
  const names = new Set();
  for (const s of report.value?.sales || []) Object.keys(s.refunds).forEach((n) => names.add(n));
  return [...names];
});
const paymentLabel = { efectivo: "Efectivo", transferencia: "Transferencia", debito: "Débito", credito: "Crédito", cortesia: "Regalo" };

/* -------- Gastos de la Empresa -------- */
const emptyExpense = () => ({ expense_date: todayISO(), concept: "", amount: null, paid_by: "Caja" });
const expenseForm = reactive(emptyExpense());
const expenseError = ref("");
const savingExpense = ref(false);

async function addExpense() {
  expenseError.value = "";
  if (!expenseForm.concept.trim()) {
    expenseError.value = "Escribe qué se compró.";
    return;
  }
  if (!isValidNumber(expenseForm.amount, { min: 0, allowZero: false })) {
    expenseError.value = "Ingresa un monto mayor a 0.";
    return;
  }
  savingExpense.value = true;
  try {
    await betaApi.createExpense({ ...expenseForm, amount: Number(expenseForm.amount) });
    Object.assign(expenseForm, emptyExpense());
    if (expenseForm.expense_date.slice(0, 7) !== month.value) expenseForm.expense_date = `${month.value}-01`;
    await load();
  } catch (err) {
    expenseError.value = extractApiError(err, "No se pudo guardar el gasto.");
  } finally {
    savingExpense.value = false;
  }
}

async function removeExpense(e) {
  const ok = await confirmAction({
    title: "Eliminar gasto",
    message: `¿Eliminar "${e.concept}" (${formatCurrency(e.amount)})?`,
    confirmLabel: "Eliminar",
    danger: true,
  });
  if (!ok) return;
  await betaApi.deleteExpense(e.id);
  await load();
}
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <p class="page-subtitle">
          <span class="beta-badge">BETA</span>
          Guía aproximada de lo que le corresponde a cada uno en el mes. No reemplaza la contabilidad ni cambia nada
          del resto de la app.
        </p>
      </div>
      <label class="month-picker">
        <Icon name="calendar" :size="16" />
        <input v-model="month" type="month" aria-label="Mes" />
      </label>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="loading && !report" class="card empty-state">Calculando...</div>

    <template v-if="report">
      <div class="grid grid-cols-4 stats">
        <StatCard label="Cobrado en el mes" :value="formatCurrency(report.collected_revenue)" :meta="`${report.sales.length} pedido(s) entregados y cobrados`" />
        <StatCard label="Costos devueltos a socios" :value="formatCurrency(report.partner_cost_refunds)" meta="Máquina, material e insumos de cada uno" />
        <StatCard label="Gastos de la Empresa" :value="formatCurrency(report.expenses_total)" :meta="`${expenses.length} compra(s) del mes`" />
        <StatCard label="Ganancia neta a repartir" :value="formatCurrency(report.net)" :meta="shareLabel" />
      </div>

      <div class="card">
        <div class="card-header">
          <h3>A cada uno</h3>
          <span class="text-muted text-sm">Su parte + lo que puso de su bolsillo + sus deliveries</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Quién</th>
                <th class="text-right">Su parte</th>
                <th class="text-right">Costos devueltos</th>
                <th class="text-right">Gastos que pagó</th>
                <th class="text-right">Deliveries</th>
                <th class="text-right">Total a recibir</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in report.partners" :key="p.name">
                <td>
                  <strong>{{ p.name }}</strong>
                  <span v-if="p.is_cash_box" class="text-muted text-sm"> · caja de la Empresa</span>
                </td>
                <td class="text-right mono">{{ formatCurrency(p.share) }}</td>
                <td class="text-right mono">{{ Number(p.cost_refund) ? formatCurrency(p.cost_refund) : "—" }}</td>
                <td class="text-right mono">{{ Number(p.expense_refund) ? formatCurrency(p.expense_refund) : "—" }}</td>
                <td class="text-right mono">{{ Number(p.delivery_refund) ? formatCurrency(p.delivery_refund) : "—" }}</td>
                <td class="text-right mono"><strong>{{ formatCurrency(p.total) }}</strong></td>
              </tr>
            </tbody>
          </table>
        </div>
        <ul class="split-notes">
          <li>
            Solo cuentan los pedidos <strong>entregados y cobrados</strong> del mes. Por cobrar:
            <strong>{{ formatCurrency(report.pending_total) }}</strong> ({{ report.pending.length }} pedido(s)), entra el mes en
            que se cobre.
          </li>
          <li>
            A cada socio se le devuelve lo que puso: máquina (depreciación + luz) de sus impresoras y su material e
            insumos. El material de la Empresa (<strong>{{ formatCurrency(report.company_absorbed_cost) }}</strong>) no se
            devuelve: ya está en los gastos de la Empresa.
          </li>
          <li>
            El <strong>delivery</strong> lo paga el cliente y se le devuelve a quien lo llevó
            (<strong>{{ formatCurrency(report.deliveries_total) }}</strong> este mes): no se reparte.
          </li>
          <li>El postprocesado y la reserva por riesgo de fallo son ganancia común.</li>
        </ul>
      </div>

      <div class="card">
        <div class="card-header">
          <h3>Gastos de la Empresa del mes</h3>
          <span class="text-muted text-sm">Compras de la caja (bolsas, argollas, filamento...)</span>
        </div>
        <form class="expense-form" @submit.prevent="addExpense">
          <input v-model="expenseForm.expense_date" type="date" required aria-label="Fecha" />
          <input v-model="expenseForm.concept" maxlength="160" placeholder="Ej: Bolsas M" aria-label="Concepto" />
          <input v-model.number="expenseForm.amount" type="number" min="1" step="1" placeholder="Monto" aria-label="Monto" />
          <select v-model="expenseForm.paid_by" aria-label="Pagado por">
            <option v-for="p in partners" :key="p" :value="p">{{ p === "Caja" ? "Pagó la Caja" : `Pagó ${p}` }}</option>
          </select>
          <button type="submit" class="btn btn-primary btn-sm" :disabled="savingExpense">
            <Icon name="plus" :size="14" /> Agregar
          </button>
        </form>
        <div v-if="expenseError" class="alert alert-danger mt-2">{{ expenseError }}</div>
        <div v-if="!expenses.length" class="text-muted text-sm mt-2">Sin gastos registrados este mes.</div>
        <div v-else class="table-wrap mt-2">
          <table>
            <tbody>
              <tr v-for="e in expenses" :key="e.id">
                <td>{{ formatDate(e.expense_date) }}</td>
                <td>{{ e.concept }}</td>
                <td class="text-muted">{{ e.paid_by === "Caja" ? "Caja" : `Pagó ${e.paid_by} (se le devuelve)` }}</td>
                <td class="text-right mono">{{ formatCurrency(e.amount) }}</td>
                <td class="text-right">
                  <button class="btn btn-icon btn-ghost" title="Eliminar" @click="removeExpense(e)"><Icon name="trash" :size="15" /></button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3>Pedidos que entran en el reparto</h3>
        </div>
        <div v-if="!report.sales.length" class="text-muted text-sm">No hay pedidos entregados y cobrados en este mes.</div>
        <div v-else class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Entregado</th>
                <th>Pedido</th>
                <th>Impresora de</th>
                <th>Pago</th>
                <th class="text-right">Cobrado</th>
                <th v-for="n in refundNames" :key="n" class="text-right">Se le devuelve a {{ n }}</th>
                <th class="text-right">Puso la Empresa</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in report.sales" :key="s.id">
                <td>{{ formatDate(s.delivered_date) }}</td>
                <td>
                  {{ s.client_name }}
                  <div v-if="s.created_by_username && s.created_by_username !== s.owner_username" class="text-muted text-sm">
                    registrada por {{ s.created_by_username }}
                  </div>
                </td>
                <td>{{ s.owner_username }}</td>
                <td>{{ paymentLabel[s.payment_method] || s.payment_method }}</td>
                <td class="text-right mono">{{ formatCurrency(s.price) }}</td>
                <td v-for="n in refundNames" :key="n" class="text-right mono">
                  {{ s.refunds[n] ? formatCurrency(s.refunds[n]) : "—" }}
                </td>
                <td class="text-right mono text-muted">{{ Number(s.company_cost) ? formatCurrency(s.company_cost) : "—" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="grid grid-cols-2">
        <div class="card">
          <div class="card-header"><h3>Por cobrar</h3></div>
          <div v-if="!report.pending.length" class="text-muted text-sm">Nada pendiente de cobro este mes.</div>
          <div v-for="p in report.pending" :key="p.id" class="mini-line">
            <span>{{ formatDate(p.delivered_date) }} · {{ p.client_name }}</span>
            <span class="mono">{{ formatCurrency(p.price) }}</span>
          </div>
        </div>
        <div class="card">
          <div class="card-header"><h3>Deliveries a devolver</h3></div>
          <div v-if="Number(report.unassigned_delivery) > 0" class="alert alert-warning" style="margin-bottom: 8px">
            {{ formatCurrency(report.unassigned_delivery) }} de delivery sin asignar: indica quién lo llevó en el estado de
            cada pedido para que se le devuelva.
          </div>
          <div v-if="!report.deliveries.length" class="text-muted text-sm">No hubo deliveries cobrados este mes.</div>
          <div v-for="d in report.deliveries" :key="d.id" class="mini-line">
            <span>
              {{ formatDate(d.delivered_date) }} · {{ d.client_name }} ·
              <template v-if="d.delivery_by">{{ d.delivery_by }}</template>
              <span v-else class="text-danger">sin asignar</span>
            </span>
            <span class="mono">{{ formatCurrency(d.amount) }}</span>
          </div>
        </div>
      </div>
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

.month-picker {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-muted);
}

.month-picker input {
  width: auto;
  border: none;
  background: transparent;
  padding: 9px 0;
}

.stats {
  margin-bottom: 16px;
}

.card + .card,
.card + .grid,
.grid + .card {
  margin-top: 16px;
}

.split-notes {
  margin: 14px 0 0;
  padding-left: 18px;
  color: var(--text-muted);
  font-size: 0.84rem;
  line-height: 1.6;
}

.expense-form {
  display: grid;
  grid-template-columns: 150px minmax(0, 1fr) 120px 170px auto;
  gap: 8px;
}

.mini-line {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  font-size: 0.88rem;
}

.mini-line:last-child {
  border-bottom: none;
}

@media (max-width: 900px) {
  .expense-form {
    grid-template-columns: 1fr 1fr;
  }
}

.text-danger {
  color: var(--danger);
}
</style>
