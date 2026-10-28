import client from "./client";

// Rendimiento por cuenta (solo la cuenta Empresa): ingresos a quien registró cada venta y
// costos a quien puso cada recurso.
export const getPerformance = (params = {}) => client.get("/api/performance", { params }).then((r) => r.data);
