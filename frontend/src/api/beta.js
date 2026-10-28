import client from "./client";

// Módulo BETA de Reparto e Inversión: una guía aproximada, no cambia nada del resto de la app.
export const getBetaAccess = () => client.get("/api/beta/access").then((r) => r.data);
export const getMonthlySplit = (month) => client.get("/api/beta/split", { params: { month } }).then((r) => r.data);
export const listExpenses = (month) => client.get("/api/beta/expenses", { params: { month } }).then((r) => r.data);
export const createExpense = (payload) => client.post("/api/beta/expenses", payload).then((r) => r.data);
export const deleteExpense = (id) => client.delete(`/api/beta/expenses/${id}`);
// Excel del Reparto del mes con las fórmulas y de dónde sale cada monto (guía beta).
export const exportMonthlySplit = (month) =>
  client.get("/api/beta/split/export.xlsx", { params: { month }, responseType: "blob" });
export const getMyInvestment = () => client.get("/api/beta/investment").then((r) => r.data);
