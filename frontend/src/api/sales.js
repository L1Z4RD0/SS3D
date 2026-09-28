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

export const changeSaleStatus = (id, payload) =>
  client.post(`/api/sales/${id}/status`, payload).then((r) => r.data);

export const PAYMENT_METHODS = [
  { value: "efectivo", label: "Efectivo" },
  { value: "transferencia", label: "Transferencia" },
  { value: "debito", label: "Débito" },
  { value: "credito", label: "Crédito" },
  { value: "por_cobrar", label: "Por cobrar" },
  { value: "cortesia", label: "Cortesía" },
];
