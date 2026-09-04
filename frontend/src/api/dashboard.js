import client from "./client";

export const getSummary = (params = {}) =>
  client.get("/api/dashboard/summary", { params }).then((r) => r.data);

export const getByPrinter = (params = {}) =>
  client.get("/api/dashboard/by-printer", { params }).then((r) => r.data);

export const getByPaymentMethod = (params = {}) =>
  client.get("/api/dashboard/by-payment-method", { params }).then((r) => r.data);

export const getStockAlerts = () => client.get("/api/dashboard/stock-alerts").then((r) => r.data);
