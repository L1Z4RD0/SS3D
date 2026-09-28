import client from "./client";

export const listPieces = (params = {}) => client.get("/api/warehouse", { params }).then((r) => r.data);

export const updatePiece = (id, payload) => client.patch(`/api/warehouse/${id}`, payload).then((r) => r.data);

export const discardPiece = (id, payload) =>
  client.post(`/api/warehouse/${id}/discard`, payload).then((r) => r.data);

export const sellPiece = (id, payload) => client.post(`/api/warehouse/${id}/sell`, payload).then((r) => r.data);

export const PIECE_STATUS_LABELS = {
  en_almacen: "En almacén",
  reservada: "Reservada",
  vendida: "Vendida",
  descartada: "Descartada",
};

export const DISCARD_REASON_LABELS = {
  regalada: "Regalada",
  danada: "Dañada",
  desechada: "Desechada",
  otro: "Otro",
};
