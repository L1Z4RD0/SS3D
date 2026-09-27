// Ciclo de vida de un pedido. Debe coincidir con backend/app/services/order_status.py
// (el servidor valida todo; esto solo decide qué botones mostrar).

export const ORDER_STATUSES = ["pendiente", "en_produccion", "lista", "entregada", "cancelado"];
export const OPEN_STATUSES = ["pendiente", "en_produccion", "lista"];

export const STATUS_LABELS = {
  pendiente: "Pendiente",
  en_produccion: "En producción",
  lista: "Lista",
  entregada: "Entregada",
  cancelado: "Cancelado",
};

// Texto del botón para avanzar al siguiente estado.
export const NEXT_ACTION = {
  pendiente: { status: "en_produccion", label: "Iniciar producción" },
  en_produccion: { status: "lista", label: "Marcar lista" },
  lista: { status: "entregada", label: "Entregar" },
};

const PREV = { en_produccion: "pendiente", lista: "en_produccion" };

export function statusClass(status) {
  return `status-${status}`;
}

export function isFinal(status) {
  return status === "entregada" || status === "cancelado";
}

// "Atrasado" no es un estado: la fecha comprometida ya pasó y el pedido sigue abierto.
export function isOverdue(sale, todayISO) {
  return OPEN_STATUSES.includes(sale.status) && sale.promised_delivery_date < todayISO;
}

// Cambios de estado disponibles para un pedido (Cancelar tiene su propio flujo).
export function statusOptions(sale) {
  const opts = [];
  const next = NEXT_ACTION[sale.status];
  if (next) opts.push({ status: next.status, label: next.label, kind: "next" });
  if (PREV[sale.status] && !sale.warehouse_item_id) {
    opts.push({ status: PREV[sale.status], label: `Volver a ${STATUS_LABELS[PREV[sale.status]]}`, kind: "back" });
  }
  if (sale.status === "pendiente" || sale.status === "en_produccion") {
    opts.push({ status: "entregada", label: "Entregar directo (saltar pasos)", kind: "skip" });
  }
  return opts;
}
