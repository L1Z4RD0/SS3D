import { ref, computed } from "vue";
import * as inventoryApi from "../api/inventory";

// Insumos que se deben (stock en negativo). Singleton de módulo: la alerta global y el
// Inventario comparten la misma lista, y el Inventario la refresca tras reponer.
const owedSupplies = ref([]);

export function useSupplyDebt() {
  async function refreshSupplyDebt() {
    try {
      const supplies = await inventoryApi.listSupplies();
      owedSupplies.value = supplies.filter((s) => Number(s.owed_qty) > 0);
    } catch {
      // La alerta es informativa: si falla la consulta, la página sigue funcionando.
    }
  }
  return { owedSupplies: computed(() => owedSupplies.value), refreshSupplyDebt };
}
