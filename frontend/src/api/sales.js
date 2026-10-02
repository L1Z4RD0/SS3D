import client from "./client";

export const listSales = (params = {}) => client.get("/api/sales", { params }).then((r) => r.data);

export const createSale = (payload) => client.post("/api/sales", payload).then((r) => r.data);

export const updateSale = (id, payload) => client.put(`/api/sales/${id}`, payload).then((r) => r.data);

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

// Pagar "por cortesía" es regalar: precio $0, los costos se registran igual (el servidor
// fuerza el $0).
export const GIFT_PAYMENT_METHOD = "cortesia";

// Planchas de un pedido ya registrado: otra parte del producto o una reimpresión por fallo
// (suma costo, no cambia el precio). Devuelven el pedido actualizado.
export const addSalePlate = (id, payload) => client.post(`/api/sales/${id}/plates`, payload).then((r) => r.data);
export const deleteSalePlate = (id, plateId) => client.delete(`/api/sales/${id}/plates/${plateId}`).then((r) => r.data);

// Delivery: quién lo hizo y cuánto se le devuelve (solo un registro, no cambia las cifras).
export const setSaleDelivery = (id, payload) => client.put(`/api/sales/${id}/delivery`, payload).then((r) => r.data);
