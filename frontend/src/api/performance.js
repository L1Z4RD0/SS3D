import client from "./client";

// Rendimiento por cuenta (solo la cuenta Empresa): ingresos al dueño de cada venta (sin delivery)
// y costos a quien puso cada recurso. También lo usa el Dashboard de la Empresa (central).
export const getPerformance = (params = {}) => client.get("/api/performance", { params }).then((r) => r.data);
