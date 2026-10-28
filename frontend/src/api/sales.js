import client from "./client";

export const listSales = (params = {}) => client.get("/api/sales", { params }).then((r) => r.data);

export const createSale = (payload) => client.post("/api/sales", payload).then((r) => r.data);

export const updateSale = (id, payload) => client.put(`/api/sales/${id}`, payload).then((r) => r.data);

// Excel con todas las ventas que cumplen los filtros y el orden (no solo la página visible).
export const exportSales = (params = {}) => client.get("/api/sales/export.xlsx", { params, responseType: "blob" });

export const deleteSale = (id) => client.delete(`/api/sales/${id}`);

export const getSale = (id) => client.get(`/api/sales/${id}`).then((r) => r.data);

export const calendarOrders = (params = {}) =>
  client.get("/api/sales/calendar", { params }).then((r) => r.data);

export const changeDeliveryDate = (id, promisedDeliveryDate) =>
  client.patch(`/api/sales/${id}/delivery-date`, { promised_delivery_date: promisedDeliveryDate }).then((r) => r.data);

export const cancelSale = (id, payload) => client.post(`/api/sales/${id}/cancel`, payload).then((r) => r.data);

export const changeSaleStatus = (id, payload) =>
  client.post(`/api/sales/${id}/status`, payload).then((r) => r.data);

export const PAYMENT_METHODS = [
  { value: "efectivo", label: "Efectivo" },
  { value: "transferencia", label: "Transferencia" },
  { value: "debito", label: "Débito" },
  { value: "credito", label: "Crédito" },
  { value: "por_cobrar", label: "Por cobrar" },
  { value: "cortesia", label: "Cortesía (regalo)" },
];

// De dónde salió la venta. Las ventas anteriores a este campo no tienen fuente ("Sin
// registrar"). color: el de cada red, para los gráficos.
export const SALE_SOURCES = [
  { value: "instagram", label: "Instagram", icon: "instagram", color: "#d62976" },
  { value: "facebook", label: "Facebook", icon: "facebook", color: "#1877f2" },
  { value: "personal", label: "Personal", icon: "person", color: "#17b3a3" },
];
export const NO_SALE_SOURCE = { value: "sin_registrar", label: "Sin registrar", icon: null, color: "#9aa0b4" };
export const saleSourceInfo = (value) => SALE_SOURCES.find((s) => s.value === value) || NO_SALE_SOURCE;

// Pagar "por cortesía" es regalar: precio $0, los costos se registran igual (el servidor
// fuerza el $0).
export const GIFT_PAYMENT_METHOD = "cortesia";

// Planchas de un pedido ya registrado: otra parte del producto o una reimpresión por fallo
// (suma costo, no cambia el precio). Devuelven el pedido actualizado.
export const addSalePlate = (id, payload) => client.post(`/api/sales/${id}/plates`, payload).then((r) => r.data);
export const deleteSalePlate = (id, plateId) => client.delete(`/api/sales/${id}/plates/${plateId}`).then((r) => r.data);

// Delivery: quién lo hizo y cuánto se le devuelve (solo un registro, no cambia las cifras).
export const setSaleDelivery = (id, payload) => client.put(`/api/sales/${id}/delivery`, payload).then((r) => r.data);
