import * as inventoryApi from "../api/inventory";
import { confirmAction } from "../composables/useConfirm";

// Shared by Calculadora (guardar cotización como venta) and Ventas (crear/editar venta):
// after a sale consumes the last grams of a filament, ask once per filament whether to
// remove it from inventory or keep the empty record (e.g. the user plans to restock it).
// The filament stays at 0g either way — it's already excluded from selection dropdowns
// by the available_g > 0 filter, so "keep" doesn't need any extra state.
export async function promptExhaustedFilaments(exhaustedFilaments) {
  for (const f of exhaustedFilaments || []) {
    const shouldDelete = await confirmAction({
      title: "Filamento agotado",
      message: `El filamento ${f.filament_label} se quedó en 0g disponibles. ¿Deseas eliminarlo del inventario?`,
      confirmLabel: "Eliminar",
      cancelLabel: "Mantener en inventario",
      danger: true,
    });
    if (shouldDelete) {
      try {
        await inventoryApi.deleteFilament(f.filament_id);
      } catch {
        // If it can't be deleted (e.g. already removed), just leave it — not worth blocking the flow.
      }
    }
  }
}
