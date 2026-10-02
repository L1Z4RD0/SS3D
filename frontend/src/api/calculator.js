import client from "./client";

export const computeQuote = (payload) =>
  client.post("/api/calculator/quote", payload).then((r) => r.data);

export const saveQuoteAsSale = (payload) =>
  client.post("/api/calculator/quote/save-as-sale", payload).then((r) => r.data);

// Riesgo de fallo: % del costo de producción que se cobra como reserva, fuera del margen.
export const RISK_LEVELS = [
  { value: "bajo", label: "Bajo", percent: 10 },
  { value: "medio", label: "Medio", percent: 15 },
  { value: "alto", label: "Alto", percent: 20 },
];
export const DEFAULT_RISK_LEVEL = "bajo";
export const riskLevelForPercent = (percent) =>
  RISK_LEVELS.find((r) => r.percent === Number(percent))?.value || DEFAULT_RISK_LEVEL;
