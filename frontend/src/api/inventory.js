import client from "./client";

export const listFilaments = (includeInactive = false, includeExhausted = false) =>
  client
    .get("/api/inventory/filaments", {
      params: { include_inactive: includeInactive, include_exhausted: includeExhausted },
    })
    .then((r) => r.data);

export const createFilament = (payload) =>
  client.post("/api/inventory/filaments", payload).then((r) => r.data);

export const updateFilament = (id, payload) =>
  client.put(`/api/inventory/filaments/${id}`, payload).then((r) => r.data);

export const deleteFilament = (id) => client.delete(`/api/inventory/filaments/${id}`);

export const listSupplies = (includeInactive = false) =>
  client.get("/api/inventory/supplies", { params: { include_inactive: includeInactive } }).then((r) => r.data);

export const createSupply = (payload) => client.post("/api/inventory/supplies", payload).then((r) => r.data);

export const updateSupply = (id, payload) =>
  client.put(`/api/inventory/supplies/${id}`, payload).then((r) => r.data);

export const deleteSupply = (id) => client.delete(`/api/inventory/supplies/${id}`);

// Registra una compra del insumo: salda lo que se usó sin stock al precio real y corrige
// el costo de esas ventas. Devuelve { supply, settled_qty, repriced_sales, cost_adjustment }.
export const restockSupply = (id, payload) =>
  client.post(`/api/inventory/supplies/${id}/restock`, payload).then((r) => r.data);
