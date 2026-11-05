import { formatLongDate } from "./format";

// "Por cobrar": se mantiene durante la producción y al entregarlo se elige cómo pagó o, si
// aún no paga, hasta cuándo tiene plazo.
export const UNPAID_PAYMENT_METHOD = "por_cobrar";
// Cómo puede pagar al entregar (o después, al registrar el pago).
export const DELIVERY_PAYMENT_CHOICES = [
  { value: "efectivo", label: "Efectivo" },
  { value: "transferencia", label: "Transferencia" },
];

export const isUnpaid = (sale) => sale?.payment_method === UNPAID_PAYMENT_METHOD;

/* Aviso de cobro de un pedido entregado sin pagar: "Cobrar el 12 de noviembre" (vencido si
   ya pasó la fecha). null si no corresponde. */
export function dueInfo(sale, today) {
  if (!isUnpaid(sale) || sale.status !== "entregada") return null;
  if (!sale.payment_due_date) return { text: "Por cobrar (sin fecha)", overdue: false };
  const overdue = sale.payment_due_date < today;
  const when = formatLongDate(sale.payment_due_date);
  if (sale.payment_due_date === today) return { text: "Cobrar hoy", overdue: false, today: true };
  return { text: overdue ? `Cobro vencido: ${when}` : `Cobrar el ${when}`, overdue };
}
