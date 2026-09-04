import client from "./client";

export const listPrinters = (includeInactive = false) =>
  client.get("/api/printers", { params: { include_inactive: includeInactive } }).then((r) => r.data);

export const createPrinter = (payload) => client.post("/api/printers", payload).then((r) => r.data);

export const updatePrinter = (id, payload) => client.put(`/api/printers/${id}`, payload).then((r) => r.data);

export const deletePrinter = (id) => client.delete(`/api/printers/${id}`);
