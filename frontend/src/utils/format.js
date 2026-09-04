const currencyFormatter = new Intl.NumberFormat("es-CL", {
  style: "currency",
  currency: "CLP",
  maximumFractionDigits: 0,
});

const numberFormatter = new Intl.NumberFormat("es-CL", {
  maximumFractionDigits: 2,
});

export function formatCurrency(value) {
  const n = Number(value ?? 0);
  return currencyFormatter.format(n);
}

export function formatNumber(value, decimals = 2) {
  const n = Number(value ?? 0);
  return n.toLocaleString("es-CL", { maximumFractionDigits: decimals, minimumFractionDigits: 0 });
}

export function formatPercent(value) {
  const n = Number(value ?? 0);
  return `${numberFormatter.format(n)}%`;
}

export function formatDate(value) {
  if (!value) return "-";
  const d = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return d.toLocaleDateString("es-CL", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatDateTime(value) {
  if (!value) return "-";
  const d = new Date(value);
  return d.toLocaleString("es-CL", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function todayISO() {
  return new Date().toISOString().slice(0, 10);
}
