<script setup>
import { watch } from "vue";
import { useRoute } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { useSupplyDebt } from "../composables/useSupplyDebt";
import { useObservedUsers } from "../composables/useObservedUsers";
import { formatNumber } from "../utils/format";
import Icon from "./Icon.vue";

// Alerta roja en todas las páginas mientras algún insumo esté en negativo: se usó sin
// tenerlo y hay que comprarlo. Se consulta de nuevo en cada cambio de página.
const route = useRoute();
const auth = useAuthStore();
const { owedSupplies, refreshSupplyDebt } = useSupplyDebt();
const { loadObservedUsers, ownerName } = useObservedUsers();

watch(() => route.fullPath, refreshSupplyDebt, { immediate: true });
loadObservedUsers();

function label(s) {
  const owner = ownerName(s.owner_id);
  return `${s.name} (debes ${formatNumber(s.owed_qty, 0)})${owner ? ` · de ${owner}` : ""}`;
}
</script>

<template>
  <div v-if="owedSupplies.length" class="supply-debt-banner" role="alert">
    <Icon name="alert" :size="18" />
    <div>
      <strong>Tienes que comprar insumos:</strong>
      {{ owedSupplies.map(label).join(" · ") }}.
      <span class="supply-debt-hint">
        Se usaron sin stock y su costo es provisional.
        <template v-if="auth.isWatcher">Avísale al dueño del inventario.</template>
        <template v-else>
          Cuando los compres, regístralo con <strong>Reponer</strong> en
          <router-link to="/inventario">Inventario</router-link> para corregir el costo real.
        </template>
      </span>
    </div>
  </div>
</template>

<style scoped>
.supply-debt-banner {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  margin-bottom: 16px;
  padding: 12px 14px;
  border: 1px solid var(--danger);
  border-radius: var(--radius-sm);
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 0.88rem;
}

.supply-debt-banner svg {
  flex-shrink: 0;
  margin-top: 1px;
}

.supply-debt-hint {
  display: block;
  margin-top: 2px;
  opacity: 0.9;
}

.supply-debt-hint a {
  color: inherit;
  font-weight: 700;
}
</style>
